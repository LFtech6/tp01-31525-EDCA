#!/usr/bin/env bash
# Gera o PDF do relatório (docs/report/31525_doc.pdf) a partir de report.html, com o Chrome em modo headless.
# Os campos {{...}} vêm de docs/report/report.vars (AUTHOR_NAME, REPO_URL, VIDEO_URL).
# O QR code do vídeo é lido de docs/report/img/qr_video.png, se existir.
# Campos por preencher ficam assinalados a amarelo no PDF.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[ -f "$DIR/report.vars" ] && . "$DIR/report.vars"

todo() { printf '<span class="todo">%s</span>' "$1"; }
AUTHOR_NAME="${AUTHOR_NAME:-$(todo '[nome completo]')}"
REPO_URL="${REPO_URL:-$(todo '[ligação do repositório Git]')}"
VIDEO_URL="${VIDEO_URL:-$(todo '[ligação do vídeo]')}"
if [ -f "$DIR/img/qr_video.png" ]; then QR_IMG='<img src="img/qr_video.png" alt="QR code do vídeo">'
else QR_IMG="$(todo 'QR code do vídeo')"; fi

TMP="$DIR/.report.build.html"
python3 - "$DIR/report.html" "$TMP" <<EOF
import sys, html
src, dst = sys.argv[1], sys.argv[2]
t = open(src, encoding="utf-8").read()
for k, v in {"AUTHOR_NAME": """$AUTHOR_NAME""", "REPO_URL": """$REPO_URL""", "VIDEO_URL": """$VIDEO_URL""", "QR_IMG": """$QR_IMG"""}.items():
    t = t.replace("{{" + k + "}}", v)
open(dst, "w", encoding="utf-8").write(t)
EOF
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --allow-file-access-from-files \
  --print-to-pdf="$DIR/31525_doc.pdf" "file://$TMP" >/dev/null 2>&1
rm -f "$TMP"
echo "PDF: $DIR/31525_doc.pdf"
