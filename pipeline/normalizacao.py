"""Normalização do campo livre "Cidade e UF" para (cidade, UF) oficiais do IBGE.

Ordem de decisão para cada texto:
1. referencia/correcoes.csv – correções manuais (exterior, respostas só com o estado,
   textos inválidos e casos que pedem leitura humana). É o lugar para resolver
   qualquer texto novo que o programa não entenda.
2. Separação do texto em partes (/, vírgula, hífen, parênteses) e reconhecimento da UF
   (sigla ou nome do estado), inclusive no fim do texto ("Campinas SP", "Recife Pernambuco").
3. Busca do município na base do IBGE (sem acento e sem diferença de maiúsculas), com
   apelidos conhecidos (BH, POA...) e aproximação para erros pequenos de digitação.
"""
import csv
import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / 'referencia'

ESTADOS = {'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amazonas': 'AM', 'bahia': 'BA', 'ceara': 'CE',
           'distrito federal': 'DF', 'espirito santo': 'ES', 'goias': 'GO', 'maranhao': 'MA', 'mato grosso': 'MT',
           'mato grosso do sul': 'MS', 'minas gerais': 'MG', 'para': 'PA', 'paraiba': 'PB', 'parana': 'PR',
           'pernambuco': 'PE', 'piaui': 'PI', 'rio de janeiro': 'RJ', 'rio grande do norte': 'RN',
           'rio grande do sul': 'RS', 'rondonia': 'RO', 'roraima': 'RR', 'santa catarina': 'SC',
           'santana catarina': 'SC', 'sao paulo': 'SP', 'sergipe': 'SE', 'tocantins': 'TO'}
NOME_ESTADO = {'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia', 'CE': 'Ceará',
               'DF': 'Distrito Federal', 'ES': 'Espírito Santo', 'GO': 'Goiás', 'MA': 'Maranhão', 'MT': 'Mato Grosso',
               'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais', 'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná',
               'PE': 'Pernambuco', 'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
               'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina', 'SP': 'São Paulo',
               'SE': 'Sergipe', 'TO': 'Tocantins'}
UFS = set(NOME_ESTADO)


def chave(texto: str) -> str:
    """Texto sem acento, minúsculo, com espaços simples (usado para comparar nomes)."""
    t = unicodedata.normalize('NFKD', texto or '')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.replace('’', "'").replace('`', "'")
    return re.sub(r'\s+', ' ', t).strip().lower()


def chave_nome(texto: str) -> str:
    """Como `chave`, mas também ignora hífen e apóstrofo (Embu-Guaçu, d'Oeste)."""
    return re.sub(r"[\s\-']+", ' ', chave(texto)).strip()


def parece_dado_pessoal(texto: str) -> bool:
    """E-mail ou telefone digitado no campo de cidade: nunca é tratado como lugar."""
    return '@' in (texto or '') or len(re.sub(r'\D', '', texto or '')) >= 8


@dataclass
class Local:
    cidade: str = ''        # nome oficial do município (ou cidade no exterior); vazio se não informado
    uf: str = ''            # sigla da UF; 'EX' para exterior; vazio se inválido
    pais: str = ''          # 'Brasil', nome do país, ou vazio
    lat: float | None = None
    lon: float | None = None
    como: str = ''          # como foi resolvido: correcao, exato, ambiguo, aproximado, so_uf, nao_encontrado, invalido

    @property
    def exterior(self):
        return self.uf == 'EX'

    @property
    def valido(self):
        return bool(self.uf)


class Normalizador:
    def __init__(self, ref: Path = REF):
        self.mun = {}          # chave_nome -> [(nome, uf, lat, lon)]
        self.capital = {}      # uf -> (nome, lat, lon)
        with open(ref / 'municipios.csv', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                item = (r['nome'], r['uf'], float(r['lat']), float(r['lon']))
                self.mun.setdefault(chave_nome(r['nome']), []).append(item)
                if r['capital'] == '1':
                    self.capital[r['uf']] = item
        self.pos = {(n, u): (la, lo) for v in self.mun.values() for n, u, la, lo in v}
        ap = json.loads((ref / 'apelidos.json').read_text(encoding='utf-8'))
        self.apelidos = {chave_nome(k): v for k, v in ap['apelidos_cidade'].items()}
        self.uf_padrao = {chave_nome(k): v for k, v in ap['uf_padrao_cidade_ambigua'].items()}
        self.correcoes = {}
        with open(ref / 'correcoes.csv', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                self.correcoes[chave(r['texto'])] = r

    # ---------- auxiliares ----------
    def _estado(self, tok):
        t = chave(tok).strip(' .')
        if len(t) == 2 and t.upper() in UFS:
            return t.upper()
        return ESTADOS.get(t)

    def _local(self, nome, uf, como):
        la, lo = self.pos.get((nome, uf), (None, None))
        return Local(nome, uf, 'Brasil', la, lo, como)

    def _municipio(self, nome, uf=None):
        k = chave_nome(nome).strip(' .')
        k = chave_nome(self.apelidos.get(k, k))
        cands = self.mun.get(k, [])
        if uf:
            m = [c for c in cands if c[1] == uf]
            if m:
                return m[0], 'exato'
            if len(cands) == 1:          # UF informada errada (ex.: "Osasco/SO")
                return cands[0], 'uf_corrigida'
        elif len(cands) == 1:
            return cands[0], 'exato'
        elif cands:
            padrao = self.uf_padrao.get(k)
            m = [c for c in cands if c[1] == padrao]
            return (m[0] if m else max(cands, key=lambda c: c[1] == 'SP')), 'ambiguo'
        # aproximação para erros pequenos de digitação
        pool = [kk for kk, v in self.mun.items() if not uf or any(c[1] == uf for c in v)]
        best = difflib.get_close_matches(k, pool, n=1, cutoff=0.88)
        if best:
            m = [c for c in self.mun[best[0]] if not uf or c[1] == uf]
            if m:
                return m[0], 'aproximado'
        return None, 'nao_encontrado'

    # ---------- principal ----------
    def normalizar(self, texto: str) -> Local:
        k = chave(texto)
        if parece_dado_pessoal(texto):
            return Local(como='invalido')
        if k in self.correcoes:
            c = self.correcoes[k]
            if not c['uf']:
                return Local(como='invalido')
            if c['uf'] == 'EX':
                return Local(c['cidade'], 'EX', c['pais'], float(c['lat']) if c['lat'] else None,
                             float(c['lon']) if c['lon'] else None, 'correcao')
            if not c['cidade']:
                return self._so_uf(c['uf'])
            if c['lat']:
                return Local(c['cidade'], c['uf'], 'Brasil', float(c['lat']), float(c['lon']), 'correcao')
            return self._local(c['cidade'], c['uf'], 'correcao')
        if not k:
            return Local(como='invalido')

        s = re.sub(r'[()]', '/', texto)
        partes = [p.strip(' .') for p in re.split(r'/+|,|\s-\s?|-\s|\s?-(?=[A-Za-z]{2}$)|-(?=[A-Z][a-z]$)|\)', s)
                  if p.strip(' .')]
        uf, resto = None, []
        for p in partes:
            st = self._estado(p)
            if st and uf is None and (resto or len(partes) > 1) and not (chave(p) in ('sao paulo', 'rio de janeiro') and not resto):
                uf = st
            else:
                resto.append(p)
        if not resto:
            return self._so_uf(uf) if uf else Local(como='invalido')

        c = resto[0]
        if uf and self._estado(c) == uf and len(c.strip()) == 2:   # "SP/SP", "RJ/RJ": a capital
            return self._local(self.capital[uf][0], uf, 'exato')
        if uf is None and chave_nome(c) not in self.mun:
            m = re.match(r'^(.*\S)\s+([A-Za-z]{2})$', c)
            if m and m.group(2).upper() in UFS:
                c, uf = m.group(1), m.group(2).upper()
            else:
                for nome, sig in sorted(ESTADOS.items(), key=lambda x: -len(x[0])):
                    kk = chave(c)
                    if kk.endswith(' ' + nome) and len(kk) > len(nome) + 1:
                        c, uf = c[:len(c) - len(nome)].strip(), sig
                        break
            if uf is None and re.match(r'^.*[a-zí][A-Z]{2}$', c) and c[-2:] in UFS:   # "GuaíbaRS"
                c, uf = c[:-2], c[-2:]
        hit, como = self._municipio(c, uf)
        if hit:
            return Local(hit[0], hit[1], 'Brasil', hit[2], hit[3], como)
        if uf:   # não achou a cidade, mas sabe o estado
            loc = self._so_uf(uf)
            loc.como = 'nao_encontrado'
            return loc
        return Local(como='nao_encontrado')

    def _so_uf(self, uf):
        """Só o estado informado: a pessoa fica sem cidade, posicionada na capital."""
        nome, uf, la, lo = self.capital[uf]
        return Local('', uf, 'Brasil', la, lo, 'so_uf')

    def capital_de(self, uf):
        return self.capital[uf][0]
