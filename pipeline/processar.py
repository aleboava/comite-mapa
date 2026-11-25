"""Processa a exportação diária do formulário e atualiza os dados públicos do painel.

Uso:
    python pipeline/processar.py                      # usa o CSV mais recente em privado/entrada/
    python pipeline/processar.py --entrada caminho.csv

Entra:   privado/entrada/*.csv          (exportação bruta, com dados pessoais – nunca vai para o Git)
         privado/atribuicoes.csv        (grupo de cada resposta já processada – privado)
         referencia/*                   (municípios, correções, grupos, configuração – públicos)
Sai:     docs/data/*.json, docs/data/base_publica.csv   (só cidade, UF, grupo e contagens)
         privado/atribuicoes.csv        (atualizado com as pessoas novas)
         privado/relatorios/AAAA-MM-DD.md  (novas pessoas, textos não reconhecidos, alertas)

Dos dados brutos, o programa lê só: id da resposta, data, cidade/UF, consentimento,
status de finalização e, apenas para achar inscrições repetidas, um hash do e-mail/telefone
(o hash fica só na memória). Nome, e-mail, telefone, IP e demais respostas são descartados.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizacao import Normalizador, NOME_ESTADO  # noqa: E402
from atribuicao import Atribuidor  # noqa: E402

PRIVADO = RAIZ / 'privado'
PUBLICO = RAIZ / 'docs' / 'data'
REF = RAIZ / 'referencia'
CAMPOS_ESTADO = ['response_id', 'grupo', 'desde']


# ---------------------------------------------------------------- leitura
def ler_bruto(caminho, cfg):
    col = cfg['colunas']
    with open(caminho, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        falt = [c for k, c in col.items() if k in ('id', 'cidade') and c not in r.fieldnames]
        if falt:
            sys.exit(f'Colunas obrigatórias ausentes no CSV: {falt}')
        pessoas = []
        for linha in r:
            ident = None
            email = (linha.get(col.get('email', ''), '') or '').strip().lower()
            fone = re.sub(r'\D', '', linha.get(col.get('telefone', ''), '') or '')[-9:]
            if email or fone:
                ident = hashlib.sha256((email or ('tel:' + fone)).encode()).hexdigest()
            pessoas.append({
                'id': linha[col['id']].strip(),
                'texto': linha[col['cidade']],
                'data': linha.get(col.get('data', ''), '') or '',
                'consentiu': (linha.get(col.get('consentimento', ''), cfg.get('consentimento_aceito')) or '') == cfg.get('consentimento_aceito', 'accepted')
                              if col.get('consentimento') in r.fieldnames else True,
                'finalizou': (linha.get(col.get('finalizado', ''), '') or '') == cfg.get('finalizado_sim', 'Yes')
                             if col.get('finalizado') in r.fieldnames else True,
                'ident': ident,
            })
    return pessoas


def ler_estado():
    arq = PRIVADO / 'atribuicoes.csv'
    if not arq.exists():
        sys.exit('Falta privado/atribuicoes.csv (grupo de quem já foi processado). Veja o README.')
    with open(arq, encoding='utf-8', newline='') as f:
        return {r['response_id']: r for r in csv.DictReader(f)}


def ler_grupos():
    with open(REF / 'grupos.csv', encoding='utf-8', newline='') as f:
        return {r['grupo']: {'nome': r['nome'], 'tipo': r['tipo']} for r in csv.DictReader(f)}


# ---------------------------------------------------------------- dados públicos
def gerar_publico(pessoas, grupos, agora):
    """Só cidade, UF, país, grupo e contagens. Nada que identifique uma resposta."""
    PUBLICO.mkdir(parents=True, exist_ok=True)
    br = [p for p in pessoas if p['loc'].valido and not p['loc'].exterior]
    ext = [p for p in pessoas if p['loc'].exterior]
    inval = [p for p in pessoas if not p['loc'].valido]
    so_uf = [p for p in br if not p['loc'].cidade]
    com_cid = [p for p in br if p['loc'].cidade]

    cid = Counter((p['loc'].cidade, p['loc'].uf) for p in com_cid)
    pos = {(p['loc'].cidade, p['loc'].uf): (p['loc'].lat, p['loc'].lon) for p in com_cid}
    cidades = [{'cidade': c, 'uf': u, 'pessoas': n, 'lat': pos[(c, u)][0], 'lon': pos[(c, u)][1]}
               for (c, u), n in sorted(cid.items(), key=lambda kv: (-kv[1], kv[0][0]))]
    resumo = {'total': len(pessoas), 'no_mapa': len(com_cid), 'cidades': len(cid), 'exterior': len(ext),
              'sem_cidade': len(so_uf) + len(inval), 'so_uf': len(so_uf), 'invalidas': len(inval),
              'atualizado_em': agora}

    # grupos x cidade
    gc = Counter(); gpos = {}
    for p in pessoas:
        if not p['grupo'] or p['loc'].exterior:
            continue
        nome = p['loc'].cidade or '(só UF)'
        k = (p['grupo'], nome, p['loc'].uf); gc[k] += 1; gpos[k] = (p['loc'].lat, p['loc'].lon)
    grupos_cidades = [{'grupo': g, 'grupo_nome': grupos[g]['nome'], 'cidade': c, 'uf': u, 'pessoas': n,
                       'lat': gpos[(g, c, u)][0], 'lon': gpos[(g, c, u)][1]} for (g, c, u), n in sorted(gc.items())]
    por_grupo = defaultdict(lambda: {'pessoas': 0, 'cid': Counter(), 'ufs': set()})
    for p in pessoas:
        if not p['grupo']:
            continue
        s = por_grupo[p['grupo']]; s['pessoas'] += 1
        if not p['loc'].exterior:
            s['cid'][p['loc'].cidade or '(só UF)'] += 1; s['ufs'].add(p['loc'].uf)
    grupos_resumo = [{'grupo': g, 'grupo_nome': grupos[g]['nome'], 'pessoas': s['pessoas'], 'cidades': len(s['cid']),
                      'ufs': ', '.join(sorted(s['ufs'])) or 'Exterior',
                      'principais': ', '.join(f'{k} ({v})' for k, v in s['cid'].most_common(3)) or 'Vários países'}
                     for g, s in sorted(por_grupo.items())]
    tam_br = [s['pessoas'] for g, s in por_grupo.items() if grupos[g]['tipo'] != 'exterior']
    com_grupo = sum(s['pessoas'] for s in por_grupo.values())
    grupos_geral = {'grupos': len(por_grupo), 'grupos_brasil': len(tam_br), 'menor': min(tam_br), 'maior': max(tam_br),
                    'exterior': sum(s['pessoas'] for g, s in por_grupo.items() if grupos[g]['tipo'] == 'exterior'),
                    'com_grupo': com_grupo, 'sem_grupo': len(pessoas) - com_grupo}

    # exterior
    lug = Counter(); info = {}
    for p in ext:
        l = p['loc']
        if l.lat is None:
            continue
        k = (l.cidade or '(só o país)', l.pais); lug[k] += 1
        info[k] = (l.lat, l.lon, 'cidade' if l.cidade else 'país')
    exterior = [{'local': k[0], 'pais': k[1], 'pessoas': n, 'lat': info[k][0], 'lon': info[k][1], 'precisao': info[k][2]}
                for k, n in sorted(lug.items(), key=lambda kv: (-kv[1], kv[0]))]
    pa = {}
    for e in exterior:
        o = pa.setdefault(e['pais'], {'pais': e['pais'], 'pessoas': 0, 'locais': []})
        o['pessoas'] += e['pessoas']
        o['locais'].append(f"sem cidade ({e['pessoas']})" if e['local'] == '(só o país)'
                           else e['local'] + (f" ({e['pessoas']})" if e['pessoas'] > 1 else ''))
    paises = sorted(({**o, 'locais': ', '.join(o['locais'])} for o in pa.values()), key=lambda o: (-o['pessoas'], o['pais']))
    mundo_resumo = {'brasil': len(com_cid), 'exterior_mapa': sum(e['pessoas'] for e in exterior), 'paises': len(pa),
                    'exterior_sem': len(ext) - sum(e['pessoas'] for e in exterior), 'sem_cidade': len(so_uf)}

    saidas = {'resumo.json': resumo, 'cidades.json': cidades, 'grupos_cidades.json': grupos_cidades,
              'grupos_resumo.json': grupos_resumo, 'grupos_geral.json': grupos_geral, 'exterior.json': exterior,
              'paises.json': paises, 'mundo_resumo.json': mundo_resumo}
    for nome, obj in saidas.items():
        (PUBLICO / nome).write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    # base pública em CSV: uma linha por grupo + cidade, com a contagem
    base = Counter()
    for p in pessoas:
        l = p['loc']
        base[(p['grupo'], l.cidade or ('(só o estado)' if l.uf and not l.exterior else ''),
              l.uf if not l.exterior else '', l.pais)] += 1
    with open(PUBLICO / 'base_publica.csv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['grupo', 'nome_do_grupo', 'cidade', 'uf', 'pais', 'pessoas'])
        for (g, c, u, pais), n in sorted(base.items(), key=lambda kv: (kv[0][0] or 'ZZ', kv[0][2], kv[0][1])):
            w.writerow([g, grupos[g]['nome'] if g else 'Sem grupo', c, u, pais, n])
    return resumo, grupos_geral


def verificar_publico(ids):
    """Trava de segurança: nenhum arquivo público pode ter e-mail, telefone ou id de resposta."""
    problemas = []
    for arq in PUBLICO.glob('*'):
        if arq.suffix not in ('.json', '.csv'):
            continue
        txt = arq.read_text(encoding='utf-8')
        if '@' in txt:
            problemas.append(f'{arq.name}: contém "@"')
        if re.search(r'\d{8,}', txt.replace('.', '')) and arq.name not in ('estados.geojson', 'mundo.geojson'):
            problemas.append(f'{arq.name}: contém sequência longa de dígitos')
        achados = [i for i in ids if i and i in txt]
        if achados:
            problemas.append(f'{arq.name}: contém {len(achados)} id(s) de resposta')
    if problemas:
        for p in problemas:
            print('ERRO DE PRIVACIDADE:', p)
        sys.exit('Os dados públicos não foram aprovados na verificação. Nada deve ser publicado.')


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--entrada', help='CSV exportado do formulário (padrão: o mais recente em privado/entrada/)')
    ap.add_argument('--simular', action='store_true', help='não grava o estado privado (só mostra o que faria)')
    args = ap.parse_args()

    cfg = json.loads((REF / 'config.json').read_text(encoding='utf-8'))
    entrada = Path(args.entrada) if args.entrada else max((PRIVADO / 'entrada').glob('*.csv'), key=lambda p: p.stat().st_mtime, default=None)
    if not entrada or not entrada.exists():
        sys.exit('Nenhum CSV de entrada. Coloque a exportação em privado/entrada/ ou use --entrada.')

    N = Normalizador()
    grupos = ler_grupos()
    estado = ler_estado()
    bruto = ler_bruto(entrada, cfg)
    agora = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')

    validas = [p for p in bruto if p['consentiu'] and p['finalizou']]
    excluidas = len(bruto) - len(validas)

    # inscrições repetidas (mesmo e-mail ou telefone): conta a pessoa uma vez só
    duplicadas = []
    if cfg.get('remover_duplicadas', True):
        por_ident = defaultdict(list)
        sem_ident = []
        for p in validas:
            (por_ident[p['ident']] if p['ident'] else sem_ident).append(p)
        unicas = list(sem_ident)
        for lista in por_ident.values():
            lista.sort(key=lambda p: (p['id'] not in estado or not estado[p['id']]['grupo'], p['data']))
            unicas.append(lista[0]); duplicadas += lista[1:]
    else:
        unicas = validas
    for p in bruto:
        p.pop('ident', None)          # o hash não sai daqui

    A = Atribuidor(N, grupos, cfg)
    for p in unicas:
        p['loc'] = N.normalizar(p['texto'])
    # quem já tem grupo mantém; quem já foi visto sem grupo só é refeito se o local agora for válido
    antigos = [p for p in unicas if p['id'] in estado and (estado[p['id']]['grupo'] in grupos or not p['loc'].valido)]
    ids_antigos = {p['id'] for p in antigos}
    novos = sorted((p for p in unicas if p['id'] not in ids_antigos), key=lambda p: p['data'])
    for p in antigos:
        p['grupo'] = estado[p['id']]['grupo'] if estado[p['id']]['grupo'] in grupos else ''
        p['motivo'] = 'mantido'
        A.registrar(p['grupo'], p['loc'])
    for p in novos:
        p['grupo'], p['motivo'] = A.escolher(p['loc'])
        A.registrar(p['grupo'], p['loc'])

    pessoas = antigos + novos
    resumo, geral = gerar_publico(pessoas, grupos, agora)
    verificar_publico({p['id'] for p in bruto})

    # estado privado
    hoje = agora[:10]
    novo_estado = dict(estado)
    for p in novos:
        novo_estado[p['id']] = {'response_id': p['id'], 'grupo': p['grupo'],
                                'desde': estado.get(p['id'], {}).get('desde') or hoje}
    if not args.simular:
        with open(PRIVADO / 'atribuicoes.csv', 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS_ESTADO); w.writeheader()
            w.writerows(sorted(novo_estado.values(), key=lambda r: (r['desde'], r['response_id'])))

    # relatório privado
    tam = Counter(p['grupo'] for p in pessoas if p['grupo'])
    entrou = Counter(p['grupo'] or 'sem grupo' for p in novos)
    pend = [p for p in novos if not p['grupo'] or p['loc'].como in ('nao_encontrado', 'aproximado', 'ambiguo')]
    L = [f'# Relatório de {agora}', '', f'Arquivo: `{entrada.name}`', '',
         f'- Respostas no arquivo: {len(bruto)}',
         f'- Fora da contagem (sem consentimento ou não finalizadas): {excluidas}',
         f'- Inscrições repetidas (mesmo e-mail/telefone), contadas uma vez: {len(duplicadas)}',
         f'- Pessoas consideradas: {len(pessoas)} ({len(antigos)} já processadas antes, {len(novos)} novas ou recolocadas)', '',
         '## Pessoas novas por grupo', '']
    L += [f'- {g}: +{n}' for g, n in sorted(entrou.items())] or ['- nenhuma']
    L += ['', '## Tamanho dos grupos', '']
    for g in sorted(grupos):
        n = tam.get(g, 0); alerta = ''
        if grupos[g]['tipo'] != 'exterior':
            if n > cfg['limite_grupo']:
                alerta = f'  ⚠ acima de {cfg["limite_grupo"]}'
            elif n < cfg['minimo_grupo']:
                alerta = f'  (abaixo de {cfg["minimo_grupo"]})'
        L.append(f'- {g} {grupos[g]["nome"]}: {n}{alerta}')
    L += ['', '## Para revisar', '',
          'Textos que o programa não reconheceu com certeza. Para corrigir, adicione uma linha em',
          '`referencia/correcoes.csv` (texto em minúsculas e sem acento → cidade, UF) e rode de novo.',
          'Nunca copie para lá textos com dados pessoais (e-mail, telefone).', '']
    for p in pend:
        txt = '(texto com dado pessoal – omitido)' if not p['loc'].valido and ('@' in p['texto'] or re.search(r'\d{8,}', re.sub(r'\D', '', p['texto']))) else p['texto']
        L.append(f'- `{p["id"]}` "{txt}" → {p["loc"].cidade or "?"}/{p["loc"].uf or "?"} ({p["loc"].como}) → grupo {p["grupo"] or "nenhum"}')
    if not pend:
        L.append('- nada')
    rel = PRIVADO / 'relatorios'; rel.mkdir(parents=True, exist_ok=True)
    (rel / f"{agora.replace(' ', '_').replace(':', '')}.md").write_text('\n'.join(L) + '\n', encoding='utf-8')

    print(f'{len(novos)} pessoa(s) nova(s); {len(duplicadas)} repetida(s); {len(pend)} para revisar.')
    print(f"Painel: {resumo['total']} pessoas, {geral['grupos']} grupos. Relatório: privado/relatorios/{agora.replace(' ', '_').replace(':', '')}.md")
    if args.simular:
        print('(simulação: privado/atribuicoes.csv não foi alterado)')


if __name__ == '__main__':
    main()
