#!/usr/bin/env bash
# Gera o PDF do relatório (docs/report/31525_doc.pdf) a partir de report.html, com o Chrome em modo headless.
# Os campos {{...}} vêm de docs/report/report.vars (AUTHOR_NAME, REPO_URL, VIDEO_URL).
# O QR code do vídeo é lido de docs/report/img/qr_video.png, se existir.
# O índice ({{TOC}}) é gerado automaticamente a partir dos títulos <h2>/<h3>, com ligações e n.º de página:
#   1.ª passagem gera o PDF, as páginas de cada título são lidas com pdftotext, 2.ª passagem gera o PDF final.
# Campos por preencher ficam assinalados a amarelo no PDF.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[ -f "$DIR/report.vars" ] && . "$DIR/report.vars"

todo() { printf '<span class="todo">%s</span>' "$1"; }
export AUTHOR_NAME="${AUTHOR_NAME:-$(todo '[nome completo]')}"
export REPO_URL="${REPO_URL:-$(todo '[ligação do repositório Git]')}"
export VIDEO_URL="${VIDEO_URL:-$(todo '[ligação do vídeo]')}"
if [ -f "$DIR/img/qr_video.png" ]; then export QR_IMG='<img src="img/qr_video.png" alt="QR code do vídeo">'
else export QR_IMG="$(todo 'QR code do vídeo')"; fi

TMP="$DIR/.report.build.html"; PDF="$DIR/31525_doc.pdf"
render() {
  "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --allow-file-access-from-files \
    --print-to-pdf="$PDF" "file://$TMP" >/dev/null 2>&1
}

# $1 = PDF da passagem anterior (vazio na 1.ª passagem)
build_html() {
  python3 - "$DIR/report.html" "$TMP" "${1:-}" <<'EOF'
import html, os, re, subprocess, sys
src, dst, pdf = sys.argv[1:]
t = open(src, encoding="utf-8").read()
for k in ("AUTHOR_NAME", "REPO_URL", "VIDEO_URL", "QR_IMG"):
    t = t.replace("{{" + k + "}}", os.environ[k])

# Títulos depois do índice: id para as ligações e texto simples
body_start = t.index("{{TOC}}")
heads = []
def tag(m):
    level, text = m.group(1), m.group(2)
    if m.start() < body_start:
        return m.group(0)
    hid = f"sec-{len(heads) + 1}"
    heads.append((level, hid, html.unescape(re.sub(r"<[^>]+>", "", text)).strip()))
    return f'<h{level} id="{hid}">{text}</h{level}>'
t = re.sub(r"<h([23])>(.*?)</h\1>", tag, t)

# Página de cada título (procura por ordem, a partir da página do título anterior)
pages = [""] * len(heads)
if pdf:
    norm = lambda s: re.sub(r"\s+", "", s)
    txt = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout
    page_txt = [norm(p) for p in txt.split("\f")]
    cur = 2  # índice 0 = capa, 1 = índice
    for i, (_, _, text) in enumerate(heads):
        key = norm(text)[:25]
        for p in range(cur, len(page_txt)):
            if key in page_txt[p]:
                pages[i], cur = str(p + 1), p
                break

items, open_sub = [], False
for (level, hid, text), page in zip(heads, pages):
    entry = f'<li><a href="#{hid}"><span class="t">{html.escape(text)}</span><span class="d"></span><span class="p">{page}</span></a>'
    if level == "2":
        if open_sub: items.append("</ol></li>"); open_sub = False
        elif items: items.append("</li>")
        items.append(entry)
    else:
        if not open_sub: items.append("<ol>"); open_sub = True
        items.append(entry + "</li>")
items.append("</ol></li>" if open_sub else "</li>")
t = t.replace("{{TOC}}", "<ol>" + "".join(items) + "</ol>")
open(dst, "w", encoding="utf-8").write(t)
EOF
}

build_html ""; render
build_html "$PDF"; render
rm -f "$TMP"
echo "PDF: $PDF"
