"""Desenha as transformações (.ktr) e o Job (.kjb) a partir do XML, nas posições do canvas do Spoon.

Hops normais a preto, hops de erro a vermelho tracejado (transformações);
no Job: verde = em caso de sucesso, vermelho = em caso de falha, preto = incondicional (como no Spoon).
Uso: python3 docs/diagrams/render_etl_diagrams.py   (requer Graphviz: dot/neato)
"""
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SCALE = 0.75  # px do Spoon → pt

COLORS = {  # por família de step
    "input": ("#dbeafe", ("CsvInput", "TableInput", "YamlInput", "getXMLData", "JsonInput", "RowGenerator", "Rest")),
    "output": ("#dcfce7", ("TableOutput", "InsertUpdate", "TextFileOutput", "JsonOutput", "ExecSQL", "SetVariable")),
    "lookup": ("#fef3c7", ("StreamLookup", "DBLookup", "MergeJoin")),
    "flow": ("#f3e8ff", ("FilterRows", "BlockUntilStepsFinish", "SortRows", "Unique", "UniqueRowsByHashSet", "GroupBy")),
}


def fill(step_type):
    for color, types in COLORS.values():
        if step_type in types:
            return color
    return "#f1f5f9"


def node(name, label, x, y, color, shape="box"):
    return (f'  "{name}" [pos="{x * SCALE:.0f},{-y * SCALE:.0f}!", shape={shape}, style="rounded,filled", '
            f'fillcolor="{color}", label="{label}"];\n')


def render(dot_src, out_png):
    src = OUT / (out_png.stem + ".dot")
    src.write_text(dot_src, encoding="utf-8")
    subprocess.run(["neato", "-n2", "-Tpng", "-Gdpi=150", str(src), "-o", str(out_png)], check=True)
    src.unlink()


def header():
    return ('digraph G {\n  graph [splines=true, overlap=false, outputorder=edgesfirst, pad=0.3];\n'
            '  node [fontname="Helvetica", fontsize=9, width=1.3, height=0.45, margin="0.05,0.03"];\n'
            '  edge [arrowsize=0.6, penwidth=1.1];\n')


def ktr(path):
    r = ET.parse(path).getroot()
    g = header()
    for s in r.findall("./step"):
        name, typ = s.findtext("name"), s.findtext("type")
        x, y = int(s.findtext("GUI/xloc")), int(s.findtext("GUI/yloc"))
        g += node(name, f"{name}\\n[{typ}]", x, y, fill(typ))
    errors = {(e.findtext("source_step"), e.findtext("target_step")) for e in r.findall("./step_error_handling/error")}
    for h in r.findall("./order/hop"):
        a, b = h.findtext("from"), h.findtext("to")
        style = 'color="#dc2626", style=dashed' if (a, b) in errors else 'color="#334155"'
        g += f'  "{a}" -> "{b}" [{style}];\n'
    render(g + "}\n", OUT / f"{Path(path).stem}.png")


def kjb(path):
    r = ET.parse(path).getroot()
    g = header()
    for e in r.findall("./entries/entry"):
        name, typ = e.findtext("name"), e.findtext("type")
        x, y = int(e.findtext("xloc")), int(e.findtext("yloc"))
        color = {"TRANS": "#dbeafe", "SQL": "#f1f5f9", "MAIL": "#fef3c7", "ABORT": "#fee2e2", "SUCCESS": "#dcfce7",
                 "SPECIAL": "#dcfce7", "WEBSERVICE_AVAILABLE": "#f3e8ff", "ADD_RESULT_FILENAMES": "#fef3c7"}.get(typ, "#f1f5f9")
        g += node(name, f"{name}\\n[{typ}]", x, y, color)
    for h in r.findall("./hops/hop"):
        a, b = h.findtext("from"), h.findtext("to")
        if h.findtext("unconditional") == "Y":
            style = 'color="#334155"'
        elif h.findtext("evaluation") == "Y":
            style = 'color="#16a34a"'
        else:
            style = 'color="#dc2626", style=dashed'
        g += f'  "{a}" -> "{b}" [{style}];\n'
    render(g + "}\n", OUT / f"{Path(path).stem}.png")


if __name__ == "__main__":
    for f in sorted((ROOT / "etl" / "transformations").glob("*.ktr")):
        ktr(f)
    kjb(ROOT / "etl" / "jobs" / "jb_sentinel_main.kjb")
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))))
