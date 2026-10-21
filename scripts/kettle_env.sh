#!/usr/bin/env bash
# Prepara o KETTLE_HOME local ao projeto (não toca em ~/.kettle).
# Gera etl/kettle-home/.kettle/kettle.properties a partir do .env (ficheiro ignorado pelo Git).
# Uso: source scripts/kettle_env.sh   (é chamado pelos wrappers spoon/pan/kitchen)

SENTINEL_HOME="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
set -a; . "$SENTINEL_HOME/.env"; set +a
# Configuração de e-mail definida no dashboard (passada pela API /ops em OVERRIDE_*; só existe em memória)
for k in SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD MAIL_FROM MAIL_TO; do
  o="OVERRIDE_$k"; [ -n "${!o:-}" ] && export "$k=${!o}"
done

export KETTLE_HOME="$SENTINEL_HOME/etl/kettle-home"
PROPS="$KETTLE_HOME/.kettle/kettle.properties"
mkdir -p "$KETTLE_HOME/.kettle"

cat > "$PROPS" <<EOF
# GERADO por scripts/kettle_env.sh a partir do .env — não editar à mão
SENTINEL_HOME=$SENTINEL_HOME
SENTINEL_DATA=$SENTINEL_HOME/data
SENTINEL_RESULTS=$SENTINEL_HOME/results
PG_HOST=$PG_HOST
PG_PORT=$PG_PORT
PG_DB=$PG_DB
PG_USER=$PG_USER
PG_PASSWORD=$PG_PASSWORD
API_URL=http://$API_HOST:$API_PORT
CORRELATION_GAP_MIN=$CORRELATION_GAP_MIN
CORRELATION_MAX_SPAN_MIN=$CORRELATION_MAX_SPAN_MIN
PROMPT_VERSION=$PROMPT_VERSION
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
MAIL_FROM=$MAIL_FROM
MAIL_TO=$MAIL_TO
EOF
chmod 600 "$PROPS"
