#!/bin/bash
# Backup locale: push su remote `backup` + copia dei file segreti (non in git).
# Da rilanciare a fine sessione: bash scripts/backup_locale.sh
set -euo pipefail
cd "$(dirname "$0")/.."

DEST="$HOME/Backups/Toto_Amici/segreti"

# 1. Tutti i branch e i tag sul repo bare locale
git push backup --all
git push backup --tags

# 2. Segreti (gitignored), con gli stessi percorsi relativi. Mai stampati.
mkdir -p "$DEST" && chmod 700 "$DEST"
for f in credenziali.json chiave_api.txt .env .streamlit/secrets.toml; do
  [ -f "$f" ] && rsync -a --relative "$f" "$DEST/"
done
find "$DEST" -type f -exec chmod 600 {} +
find "$DEST" -type d -exec chmod 700 {} +
echo "Backup completato in ~/Backups/Toto_Amici"
