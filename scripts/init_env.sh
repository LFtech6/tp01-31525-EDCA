#!/usr/bin/env bash
# Cria o .env a partir do .env.example com segredos aleatórios.
# Não imprime segredos. Não sobrescreve um .env existente.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [ -f "$ENV_FILE" ]; then
  echo ".env já existe — nada alterado."
  exit 0
fi

gen() { openssl rand -base64 33 | tr -d '/+=\n' | cut -c1-32; }

sed -e "s|^PG_PASSWORD=.*|PG_PASSWORD=$(gen)|" \
    -e "s|^PG_RO_PASSWORD=.*|PG_RO_PASSWORD=$(gen)|" \
    -e "s|^OPS_API_TOKEN=.*|OPS_API_TOKEN=$(gen)|" \
    "$ROOT/.env.example" > "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo ".env criado com segredos aleatórios (permissões 600)."
