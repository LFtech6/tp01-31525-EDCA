#!/usr/bin/env bash
# Servidor SMTP local para as notificações do Job (Mailpit, instalado com: brew install mailpit).
# Só escuta em 127.0.0.1. Exige autenticação SMTP com SMTP_USER/SMTP_PASSWORD do .env
# (sem TLS, por ser apenas local). Os e-mails ficam numa caixa de entrada visível em
# http://127.0.0.1:${MAILPIT_UI_PORT}; nada é enviado para fora da máquina.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env"; set +a

STATE="$ROOT/.mailpit"            # ignorado pelo Git (ficheiro de credenciais + caixa de correio)
mkdir -p "$STATE"; chmod 700 "$STATE"
( umask 077; printf '%s:%s\n' "$SMTP_USER" "$SMTP_PASSWORD" > "$STATE/smtp-auth" )

exec mailpit \
  --smtp "127.0.0.1:${SMTP_PORT}" \
  --listen "127.0.0.1:${MAILPIT_UI_PORT}" \
  --smtp-auth-file "$STATE/smtp-auth" \
  --smtp-auth-allow-insecure \
  --database "$STATE/mailpit.db"
