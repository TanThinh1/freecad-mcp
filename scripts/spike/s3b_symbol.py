"""S3b: draw lines/text ourselves as an SVG symbol (TechDraw::DrawViewSymbol) so dash patterns, weights and text are fully controlled.

Run: powershell -NoProfile -File scripts\\spike\\run_spike.ps1 -Name s3b_symbol
Check: python -I scripts\\spike\\pdf_probe.py out\\spike\\s3b_symbol.pdf --min-area 900 --text
"""
import os
import sys

sys.path.insert(0, os.environ.get("SPIKE_DIR", os.path.dirname(os.path.abspath(__file__))))
import _common as C  # noqa: E402

# name, dasharray (paper mm), stroke width (paper mm)
LINES = [("liền đậm", "", 0.5), ("liền mảnh", "", 0.25), ("HIDDEN nét đứt", "3 1", 0.25), ("CENTER chấm gạch", "12 1.5 2 1.5", 0.25)]


def symbol_svg() -> str:
    rows = []
    for i, (label, dash, w) in enumerate(LINES):
        y = 8 + 10 * i
        d = f' stroke-dasharray="{dash}"' if dash else ""
        rows.append(f'<line x1="0" y1="{y}" x2="100" y2="{y}" stroke="#000" stroke-width="{w}"{d}/>')
        rows.append(f'<text x="104" y="{y + 1.2}" font-family="Arial" font-size="3.5" fill="#000">{label}</text>')
    rows.append('<text x="0" y="3" font-family="Arial" font-size="3.5" fill="#000">Ắ Ằ Ẳ Ẵ Ặ Ơ Ư Đ ướ ượ</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="160mm" height="45mm" viewBox="0 0 160 45">' + "".join(rows) + "</svg>")


def main():
    C.start("s3b_symbol")
    import FreeCAD

    C.white_paper()
    doc = FreeCAD.newDocument("S3b")
    page, tmpl = C.new_page(doc, C.write_template(os.path.join(C.OUT, "A3_TCVN5571_template.svg")))
    tmpl.EditableTexts = {"cell3_l1": "S3B SYMBOL", "cell4": "S3b"}
    sym = doc.addObject("TechDraw::DrawViewSymbol", "Sym")
    page.addView(sym)
    sym.Symbol = symbol_svg()
    sym.Scale = 1.0
    sym.X, sym.Y = 150.0, 150.0
    doc.recompute()
    C.pump(1.0)
    out = C.export_page(page, "s3b_symbol")
    return os.path.isfile(out["pdf"])


C.run(main)
