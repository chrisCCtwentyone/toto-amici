#!/usr/bin/env bash
# Pubblica il sito (frontend/) su Cloudflare Workers: prima i test, poi build e deploy.
# Si ferma al primo errore: un test rosso non arriva mai online.
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm run typecheck
npm test
npm run build
npx wrangler deploy
