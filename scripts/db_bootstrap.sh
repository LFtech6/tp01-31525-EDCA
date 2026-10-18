#!/usr/bin/env bash
# Cria roles + base (00_bootstrap.sql) e aplica o schema (01_schema.sql).
# Os segredos são lidos do .env e passados ao psql por stdin, não pela linha de comandos.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env"; set +a

ADMIN_DB="${PG_ADMIN_DB:-postgres}"

{
  printf '\\set app_user %s\n' "$PG_USER"
  printf '\\set app_password %s\n' "$PG_PASSWORD"
  printf '\\set ro_user %s\n' "$PG_RO_USER"
  printf '\\set ro_password %s\n' "$PG_RO_PASSWORD"
  printf '\\set db_name %s\n' "$PG_DB"
  cat "$ROOT/database/00_bootstrap.sql"
} | psql -h "$PG_HOST" -p "$PG_PORT" -d "$ADMIN_DB" -v ON_ERROR_STOP=1 -q

PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
  -v ON_ERROR_STOP=1 -q -v ro_user="$PG_RO_USER" -f "$ROOT/database/01_schema.sql"

echo "Bootstrap + schema aplicados em $PG_DB@$PG_HOST:$PG_PORT"
