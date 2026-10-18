#!/usr/bin/env bash
# Abre o psql na base do projeto com as credenciais do .env (sem as mostrar).
# Uso: ./scripts/sql.sh                      (consola interativa)
#      ./scripts/sql.sh -c "select count(*) from zone"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env"; set +a
PGPASSWORD="$PG_PASSWORD" exec psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" "$@"
