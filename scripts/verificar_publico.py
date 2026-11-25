"""Trava de privacidade para o Git: impede commit de dados pessoais.

Verifica os arquivos que estão no "stage" (git add). Bloqueia o commit se algum:
- estiver dentro de privado/ (exceto privado/LEIAME.md);
- for um CSV fora de referencia/ e docs/data/base_publica.csv;
- tiver cabeçalho típico da exportação do formulário (Nome, E-mail, WhatsApp, Response ID, Ip Address);
- tiver um endereço de e-mail.

Instalação (uma vez por clone):
    python scripts/verificar_publico.py --instalar
"""
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROIBIDO_NO_TEXTO = ['Response ID', 'Ip Address', '2. E-mail', '3. WhatsApp', '1. Nome']
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')


def arquivos_no_stage():
    out = subprocess.run(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
                         capture_output=True, text=True, cwd=RAIZ, check=True).stdout
    return [l for l in out.splitlines() if l.strip()]


def problemas(caminho):
    p = caminho.replace('\\', '/')
    if p.startswith('privado/') and p != 'privado/LEIAME.md':
        return 'arquivo da pasta privado/'
    if p.endswith('.csv') and not (p.startswith('referencia/') or p == 'docs/data/base_publica.csv'):
        return 'CSV fora dos lugares públicos'
    arq = RAIZ / p
    if arq.suffix in ('.csv', '.json', '.md', '.txt', '.html', '.js') and arq.exists():
        txt = arq.read_text(encoding='utf-8', errors='ignore')
        for termo in PROIBIDO_NO_TEXTO:
            if termo in txt and p not in ('scripts/verificar_publico.py', 'referencia/config.json', 'README.md',
                                          'pipeline/processar.py', 'privado/LEIAME.md'):
                return f'contém "{termo}" (parece a exportação bruta)'
        if p.startswith(('docs/', 'referencia/')) and EMAIL.search(txt):
            return 'contém um endereço de e-mail'
    return None


def instalar():
    hook = RAIZ / '.git' / 'hooks' / 'pre-commit'
    hook.write_text('#!/bin/sh\npython3 scripts/verificar_publico.py || exit 1\n', encoding='utf-8')
    hook.chmod(0o755)
    print('Trava instalada em .git/hooks/pre-commit')


def main():
    if '--instalar' in sys.argv:
        return instalar()
    ruins = [(a, m) for a in arquivos_no_stage() if (m := problemas(a))]
    if ruins:
        print('COMMIT BLOQUEADO – possível dado pessoal:')
        for a, m in ruins:
            print(f'  {a}: {m}')
        print('Tire esses arquivos do commit: git restore --staged <arquivo>  (no primeiro commit: git rm --cached <arquivo>).')
        sys.exit(1)


if __name__ == '__main__':
    main()
