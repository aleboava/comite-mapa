#!/usr/bin/env bash
# Atualização diária: processa a exportação mais recente e publica só os dados públicos.
#
# Uso:   ./scripts/atualizar.sh                 (usa o CSV mais recente em privado/entrada/)
#        ./scripts/atualizar.sh caminho/do.csv  (usa este arquivo; ele é copiado para privado/entrada/)
#
# Para rodar todo dia às 7h (Linux/macOS), adicione ao crontab (crontab -e):
#   0 7 * * * cd /caminho/para/comite-mapa && ./scripts/atualizar.sh >> privado/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" != "" ]; then
  mkdir -p privado/entrada
  cp "$1" "privado/entrada/$(date +%Y-%m-%d_%H%M)_$(basename "$1")"
fi

python3 pipeline/processar.py

# publica apenas a pasta docs/data (cidade, UF, grupo e contagens)
git add docs/data
if git diff --cached --quiet; then
  echo "Nada mudou nos dados públicos."
  exit 0
fi
python3 scripts/verificar_publico.py
git commit -m "Atualiza dados do painel ($(date +%Y-%m-%d))"
git push
