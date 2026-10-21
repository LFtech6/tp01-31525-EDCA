#!/usr/bin/env bash
# Verificação do ambiente Sentinel-AI. Apenas leitura: não instala nem altera nada.
# Uso: ./scripts/check_env.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

PDI_HOME="${PDI_HOME:-$HOME/pentaho/data-integration}"
PG_HOST="${PG_HOST:-localhost}"; PG_PORT="${PG_PORT:-5432}"
PG_DB="${PG_DB:-sentinel}"; PG_USER="${PG_USER:-sentinel}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:4b-instruct}"

fails=0; warns=0
pass() { printf "  [ OK ] %s\n" "$1"; }
warn() { printf "  [WARN] %s\n" "$1"; warns=$((warns+1)); }
fail() { printf "  [FAIL] %s\n" "$1"; fails=$((fails+1)); }

echo "== Sistema"
[ "$(uname -m)" = "arm64" ] && pass "Apple Silicon (arm64)" || warn "Arquitetura $(uname -m)"
mem_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
[ "$mem_gb" -ge 16 ] && pass "RAM ${mem_gb} GB" || warn "RAM ${mem_gb} GB: evitar Docker Desktop e Spoon aberto durante a inferência"

echo "== Java / Pentaho"
if [ -x "$PDI_HOME/pan.sh" ] && [ -x "$PDI_HOME/kitchen.sh" ]; then
  ver=$(ls "$PDI_HOME/lib" | sed -n 's/^kettle-core-\(.*\)\.jar$/\1/p')
  pass "PDI em $PDI_HOME (versão $ver)"
  pan_out=$("$PDI_HOME/pan.sh" -version 2>&1)
  echo "$pan_out" | grep -q "Kettle version" && pass "Pan (headless) arranca" || fail "Pan não arranca"
else
  fail "PDI não encontrado em $PDI_HOME"
fi
java -version 2>&1 | head -1 | sed 's/^/  [INFO] java no PATH: /'
ls "$PDI_HOME/lib" 2>/dev/null | grep -q '^postgresql-.*\.jar$' \
  && pass "Driver JDBC PostgreSQL: $(ls "$PDI_HOME/lib" | grep '^postgresql-')" \
  || fail "Driver JDBC PostgreSQL ausente em $PDI_HOME/lib"

echo "== PostgreSQL"
if pg_isready -h "$PG_HOST" -p "$PG_PORT" >/dev/null 2>&1; then
  pass "Servidor a responder em $PG_HOST:$PG_PORT"
  if PGPASSWORD="${PG_PASSWORD:-}" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -Atc "select 1" >/dev/null 2>&1; then
    pass "Ligação a $PG_DB como $PG_USER"
  else
    warn "Base '$PG_DB' / role '$PG_USER' ainda não existe ou credenciais erradas (etapa 1)"
  fi
else
  fail "PostgreSQL não responde em $PG_HOST:$PG_PORT"
fi

echo "== Python"
command -v uv >/dev/null && pass "uv $(uv --version | awk '{print $2}')" || warn "uv não instalado"
uv python find 3.12 >/dev/null 2>&1 && pass "Python 3.12 disponível para o venv" || warn "Python 3.12 não encontrado pelo uv"
[ -x "$ROOT/ai-engine/.venv/bin/python" ] && pass "venv ai-engine criado" || warn "venv ai-engine ainda não criado (etapa 3)"

echo "== Ollama"
if command -v ollama >/dev/null; then
  pass "ollama $(ollama --version 2>/dev/null | awk '{print $NF}')"
  if curl -fsS "$OLLAMA_URL/api/version" >/dev/null 2>&1; then
    pass "Servidor Ollama ativo em $OLLAMA_URL"
    ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "$OLLAMA_MODEL" \
      && pass "Modelo $OLLAMA_MODEL presente" || warn "Modelo $OLLAMA_MODEL não descarregado"
  else
    warn "Servidor Ollama parado (ollama serve / brew services start ollama)"
  fi
else
  warn "ollama não instalado (etapa 3)"
fi

echo "== Serviço FastAPI"
curl -fsS "http://${API_HOST:-127.0.0.1}:${API_PORT:-8000}/health" >/dev/null 2>&1 \
  && pass "API /health responde" || warn "API ainda não está a correr"

echo "== SMTP (notificações)"
nc -z -G 5 "${SMTP_HOST:-smtp.office365.com}" "${SMTP_PORT:-587}" >/dev/null 2>&1 \
  && pass "Servidor SMTP acessível em ${SMTP_HOST:-smtp.office365.com}:${SMTP_PORT:-587}" \
  || warn "Servidor SMTP inacessível: o Job corre, mas a etapa NOTIFY fica FAILED"
[ "${SMTP_USER:-change_me}" != "change_me" ] && [ "${SMTP_PASSWORD:-change_me}" != "change_me" ] \
  && pass "Credenciais SMTP definidas no .env" || warn "SMTP_USER/SMTP_PASSWORD por preencher no .env"

echo
echo "Resumo: $fails falha(s), $warns aviso(s)."
[ "$fails" -eq 0 ]
