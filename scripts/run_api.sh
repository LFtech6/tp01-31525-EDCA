#!/usr/bin/env bash
# Arranca o serviço FastAPI apenas em 127.0.0.1 (nunca exposto à rede).
# Uso: ./scripts/run_api.sh        (Ctrl+C para parar)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env"; set +a
cd "$ROOT/ai-engine"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT:-8000}"
