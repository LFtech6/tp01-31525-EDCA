#!/usr/bin/env bash
# Arranca o Node-RED do projeto (editor: http://127.0.0.1:1880 · dashboard: http://127.0.0.1:1880/dashboard).
# As variáveis do .env (API_URL, OPS_API_TOKEN, PG_RO_*) ficam disponíveis aos fluxos via env.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env"; set +a
export API_URL="http://${API_HOST:-127.0.0.1}:${API_PORT:-8000}"
cd "$ROOT/node-red"
[ -d node_modules ] || npm install --no-audit --no-fund
exec ./node_modules/.bin/node-red --userDir . --settings ./settings.js
