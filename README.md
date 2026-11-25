# Mapa de respondentes – Comitê Popular do Lula

Painel público com a distribuição das pessoas voluntárias por cidade, os grupos regionais e o mapa-múndi, atualizado a partir da exportação diária do formulário.

**Os dados pessoais nunca saem da máquina de quem roda o processamento.** O painel publica só cidade, UF, país, número do grupo e contagens.

```
exportação do formulário (CSV com dados pessoais)          ← privado/entrada/   (fora do Git)
        │
        ▼  python pipeline/processar.py
  ┌───────────────────────────────────────────┐
  │ 1. lê só: id, data, cidade/UF, consentimento│
  │ 2. descarta repetidos (hash de e-mail/tel.)  │
  │ 3. normaliza cidade e UF (base IBGE)         │
  │ 4. mantém o grupo de quem já tinha           │
  │ 5. coloca as pessoas novas no grupo da região│
  │ 6. confere que nada pessoal vai ser publicado│
  └───────────────────────────────────────────┘
        │                                   │
        ▼                                   ▼
docs/data/*.json, base_publica.csv     privado/atribuicoes.csv, privado/relatorios/
(público, vai para o GitHub Pages)     (privado, fica só na máquina)
```

## Estrutura

| Pasta | Conteúdo | Vai para o GitHub? |
|---|---|---|
| `pipeline/` | Código Python: `processar.py` (principal), `normalizacao.py`, `atribuicao.py` | Sim |
| `referencia/` | Municípios do IBGE, regiões metropolitanas, correções manuais, lista de grupos, configuração | Sim |
| `docs/` | O site (HTML/CSS/JS) e os dados públicos em `docs/data/` | Sim (é o GitHub Pages) |
| `scripts/` | `atualizar.sh` (rotina diária) e `verificar_publico.py` (trava de privacidade) | Sim |
| `tests/` | Testes de normalização e de escolha de grupo | Sim |
| `privado/` | Exportações, `atribuicoes.csv` (grupo de cada resposta) e relatórios | **Não** (ignorada pelo Git) |

## Instalação

Precisa só de **Python 3.10+**, sem bibliotecas extras.

```bash
git clone https://github.com/SEU-USUARIO/comite-mapa.git
cd comite-mapa
python3 scripts/verificar_publico.py --instalar   # trava que bloqueia commit de dados pessoais
mkdir -p privado/entrada
```

Copie para `privado/atribuicoes.csv` o arquivo de estado inicial (entregue à parte, **não** pelo GitHub). Ele contém o grupo das pessoas que já foram distribuídas; sem ele, o programa não sabe quem já tem grupo.

## Rotina diária

1. Exporte o CSV do formulário e salve em `privado/entrada/` (qualquer nome terminado em `.csv`).
2. Rode:

```bash
./scripts/atualizar.sh
```

O script processa o CSV mais recente, gera `docs/data/`, confere a privacidade, faz o commit só de `docs/data/` e envia para o GitHub. O site se atualiza em cerca de 1 minuto.

Para só processar, sem publicar: `python3 pipeline/processar.py`. Para testar sem gravar o estado: `python3 pipeline/processar.py --simular`.

Para rodar sozinho todo dia (Linux/macOS), adicione ao `crontab -e`:

```
0 7 * * * cd /caminho/para/comite-mapa && ./scripts/atualizar.sh >> privado/cron.log 2>&1
```

Depois de cada execução, leia o relatório em `privado/relatorios/`. Ele mostra quantas pessoas entraram em cada grupo, os grupos que passaram de 120 ou ficaram abaixo de 90 e os textos de cidade que o programa não entendeu.

## Como as pessoas novas entram nos grupos

Quem já tem grupo **nunca muda** automaticamente. Para cada pessoa nova:

1. **Mora no exterior:** vai para o grupo do exterior.
2. **A cidade já tem gente em algum grupo:** entra nesse grupo. Se a cidade estiver em mais de um grupo (por exemplo, a capital de SP), entra no menor deles.
3. **A cidade é nova:** entra no grupo mais próximo do mesmo estado e da mesma região. As regiões são definidas em `referencia/config.json`:
   - em **SP** e **MG**, região metropolitana da capital ou resto do estado;
   - no **RJ**, capital ou resto do estado;
   - nos outros estados, o estado inteiro.
4. **Só informou o estado:** conta como morador da capital.
5. **Inscrição repetida** (mesmo e-mail ou telefone): conta uma vez só, pela primeira resposta.
6. **Sem consentimento** ou formulário não finalizado: fica fora da contagem.
7. **Texto inválido:** a pessoa fica sem grupo e o texto aparece no relatório.

## Corrigir uma cidade que o programa não entendeu

Adicione uma linha em `referencia/correcoes.csv`. Na coluna `texto`, escreva o que a pessoa digitou, em minúsculas e sem acento. Nas outras colunas, informe para onde a resposta deve ir:

| texto | cidade | uf | pais | lat | lon |
|---|---|---|---|---|---|
| `sampa` | São Paulo | SP | Brasil | | |
| `porto portugal` | Porto | EX | Portugal | 41.1579 | -8.6291 |
| `minas gerais` | | MG | Brasil | | |
| `hah` | | | | | |

- **Cidade no Brasil:** deixe `lat` e `lon` vazios. As coordenadas vêm da base do IBGE.
- **Exterior:** use `EX` na coluna `uf` e preencha o país e as coordenadas.
- **Só o estado:** deixe a cidade vazia e preencha só a UF.
- **Texto inválido:** deixe todas as colunas vazias, menos `texto`.

**Nunca coloque nesse arquivo textos com e-mail, telefone ou nome.** Respostas assim já são descartadas automaticamente.

Na execução seguinte, quem estava sem grupo por causa desse texto entra no grupo certo.

## Mudar os grupos

- **Renomear um grupo:** edite `referencia/grupos.csv`.
- **Mover pessoas de grupo ou refazer a divisão:** edite `privado/atribuicoes.csv`, que traz o grupo de cada `response_id`. Faça um backup antes.
- **Criar um grupo:** acrescente uma linha em `referencia/grupos.csv` e atribua pessoas a ele em `atribuicoes.csv`.

## Privacidade

- **O que o programa lê:** de cada linha do CSV, só o id da resposta, a data, a cidade/UF, o consentimento e o status de finalização. E-mail e telefone viram um hash (SHA-256) que existe apenas na memória, durante a execução, para encontrar inscrições repetidas.
- **O que fica fora do Git:** `privado/` e qualquer CSV fora de `referencia/` e `docs/data/base_publica.csv` são ignorados (`.gitignore`).
- **Antes de gravar o painel:** `processar.py` confere os arquivos públicos e para se encontrar "@", sequências longas de dígitos ou ids de resposta.
- **Antes de cada commit:** `scripts/verificar_publico.py` (pre-commit) bloqueia arquivos de `privado/`, CSVs soltos e textos com cabeçalhos da exportação ou e-mails.
- **Cidades com 1 pessoa:** aparecem no mapa, como no painel atual. Se a coordenação preferir, dá para agrupar essas cidades como "outras cidades do estado" em `gerar_publico()`.

## Publicar no GitHub Pages

1. Crie o repositório e envie o projeto: `git init`, `git add .`, `git commit`, `git push`.
2. No GitHub, vá em **Settings → Pages → Build and deployment**, escolha **Deploy from a branch**, branch `main` e pasta **/docs**.
3. O endereço fica `https://SEU-USUARIO.github.io/comite-mapa/`.

> Para o painel não ser público, publique `docs/` atrás de login (Netlify/Cloudflare Access, servidor próprio) em vez do GitHub Pages. Repositórios privados só têm Pages restrito no GitHub Enterprise.

## Testes

```bash
python3 -m unittest discover tests
```

## Créditos dos dados

- Municípios, códigos e coordenadas: [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros) (licença MIT; dados do IBGE).
- Contornos dos estados: [codeforgermany/click_that_hood](https://github.com/codeforgermany/click_that_hood). Contornos dos países: [johan/world.geo.json](https://github.com/johan/world.geo.json). Ambos foram simplificados.
- Gráficos: [D3.js](https://d3js.org) v7 (licença ISC, em `docs/vendor/`).
