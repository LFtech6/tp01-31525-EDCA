#!/usr/bin/env bash
# Prepara a entrega do TP1: dist/tp01-31525/ e dist/31525.zip, com a organização pedida pelos docentes.
#   README.md · doc/31525_doc.pdf · dataintegration/ · data/input/ · data/output/ · src/ (projeto executável)
# O projeto é copiado a partir do último commit (git archive): .env, kettle-home, .venv e node_modules nunca entram.
# Autor, ligação do vídeo e do repositório: docs/report/report.vars.
# No fim procura no pacote todos os segredos do .env e falha se encontrar algum.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NUM=31525
DIST="$ROOT/dist"; PKG="$DIST/tp01-$NUM"
set -a; . "$ROOT/.env"; set +a
[ -f "$ROOT/docs/report/report.vars" ] && . "$ROOT/docs/report/report.vars"

cd "$ROOT"
[ -z "$(git status --porcelain -- etl data/raw data/test_scenarios database ai-engine node-red scripts docs README.md ':!docs/report/31525_doc.pdf')" ] \
  || { echo "Há alterações por fazer commit: o pacote é construído a partir do último commit." >&2; exit 1; }

rm -rf "$PKG" "$DIST/$NUM.zip"; mkdir -p "$PKG/src" "$PKG/doc" "$PKG/dataintegration" "$PKG/data/input" "$PKG/data/output/database"

# src/: projeto completo tal como está no repositório
git archive HEAD | tar -x -C "$PKG/src"
find "$PKG/src" -name .gitkeep -delete

# README com os campos preenchidos (raiz do pacote e src/)
fill() {
  python3 - "$1" "${AUTHOR_NAME:-[A PREENCHER: nome]}" "${VIDEO_URL:-[A PREENCHER: ligação do vídeo]}" \
            "${REPO_URL:-[A PREENCHER: repositório Git]}" <<'EOF'
import sys
f, name, video, repo = sys.argv[1:]
t = open(f, encoding="utf-8").read()
t = t.replace("{{AUTHOR_NAME}}", name).replace("{{VIDEO_URL}}", video).replace("{{REPO_URL}}", repo)
open(f, "w", encoding="utf-8").write(t)
EOF
}
fill "$PKG/src/README.md"; cp "$PKG/src/README.md" "$PKG/README.md"

# doc/: relatório
"$ROOT/docs/report/build_report.sh" >/dev/null
cp "$ROOT/docs/report/31525_doc.pdf" "$PKG/doc/${NUM}_doc.pdf"
cp "$ROOT/docs/report/31525_doc.pdf" "$PKG/src/docs/report/31525_doc.pdf"

# dataintegration/: transformações, Job e SQL dos Table input (cópia para consulta)
cp -R "$PKG/src/etl/transformations" "$PKG/src/etl/jobs" "$PKG/src/etl/sql" "$PKG/dataintegration/"

# data/input e data/output (cópias para consulta)
cp "$PKG/src/data/raw/"* "$PKG/data/input/"
cp -R "$PKG/src/data/test_scenarios" "$PKG/data/input/"
cp -R "$PKG/src/results/exports" "$PKG/src/results/evaluation" "$PKG/data/output/"
PGPASSWORD="$PG_PASSWORD" pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
  --no-owner --no-privileges -f "$PKG/data/output/database/sentinel_dump.sql"

# Verificação de segredos: nenhum valor de *PASSWORD*/*TOKEN* do .env pode aparecer no pacote
fail=0
for key in $(grep -E '^[A-Z_]*(PASSWORD|TOKEN)[A-Z_]*=' "$ROOT/.env" | cut -d= -f1); do
  val="${!key:-}"; [ -z "$val" ] || [ "$val" = change_me ] && continue
  if grep -rqF -- "$val" "$PKG"; then echo "SEGREDO ENCONTRADO no pacote: $key" >&2; fail=1; fi
done
[ -e "$PKG/src/.env" ] && { echo ".env no pacote" >&2; fail=1; }
[ "$fail" -eq 0 ] || { rm -rf "$PKG"; exit 1; }

grep -rl "A PREENCHER" "$PKG/README.md" >/dev/null && echo "AVISO: README ainda tem campos por preencher (docs/report/report.vars)."
PDF_TXT="$(pdftotext "$PKG/doc/${NUM}_doc.pdf" - 2>/dev/null || true)"
grep -qE '\[nome completo\]|\[ligação do vídeo\]|QR code do vídeo' <<<"$PDF_TXT" \
  && echo "AVISO: o relatório ainda tem campos por preencher (nome, vídeo ou QR code)."

(cd "$DIST" && zip -qr "$NUM.zip" "tp01-$NUM" -x '*.DS_Store')
echo "Pacote: $PKG"
echo "ZIP:    $DIST/$NUM.zip ($(du -h "$DIST/$NUM.zip" | cut -f1))"
