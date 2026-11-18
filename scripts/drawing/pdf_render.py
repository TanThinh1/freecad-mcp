"""Renderer (b): primitives -> PDF through a TechDraw page (A3 template + one SVG symbol holding the drawing).

Two parts:
  * symbol_svg(D, profile)  - plain Python: SVG of the non-sheet primitives in sheet mm (420 x 297 viewBox); line weights and
    dash patterns come from the layer table / linetype patterns (same values as the DXF).
  * main()                   - runs INSIDE FreeCAD (freecad.exe --hidden scripts/drawing/pdf_render.py, job in the
    DRAWING_JOB environment variable): builds the TechDraw page, fills the template and exports PDF + SVG.
Text in the PDF becomes outlines (TechDraw/Qt behaviour measured in the spikes); text in DXF/DWG stays real text.
"""
from __future__ import annotations

import json
import os
import sys
import time
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.environ.get("PYTHONPATH", "."))


def symbol_svg(D, profile) -> str:
    from primitives import Circle, Line, Rect, Text, cap_to_em
    from tcvn import SHEETS, layer_style

    SHEET_W, SHEET_H = SHEETS[D.sheet].w, SHEETS[D.sheet].h

    fy = lambda y: SHEET_H - y
    rows = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_W:g}mm" height="{SHEET_H:g}mm" viewBox="0 0 {SHEET_W:g} {SHEET_H:g}">']
    for p in D.prims:
        if p.sheet:
            continue
        lw, pat = layer_style(profile, p.layer)
        dash = (' stroke-dasharray="' + " ".join(f"{abs(x):g}" for x in pat) + '"') if pat else ""
        stroke = f'fill="none" stroke="#000000" stroke-width="{lw:g}" stroke-linecap="butt"{dash}'
        if isinstance(p, Line):
            rows.append(f'<line x1="{p.p1[0]:.4f}" y1="{fy(p.p1[1]):.4f}" x2="{p.p2[0]:.4f}" y2="{fy(p.p2[1]):.4f}" {stroke}/>')
        elif isinstance(p, Rect):
            rows.append(f'<rect x="{p.p0[0]:.4f}" y="{fy(p.p1[1]):.4f}" width="{p.p1[0] - p.p0[0]:.4f}" height="{p.p1[1] - p.p0[1]:.4f}" {stroke}/>')
        elif isinstance(p, Circle):
            rows.append(f'<circle cx="{p.c[0]:.4f}" cy="{fy(p.c[1]):.4f}" r="{p.r:.4f}" {stroke}/>')
        elif isinstance(p, Text):
            anchor = {"left": "start", "center": "middle", "right": "end"}[p.halign]
            w = ' font-weight="bold"' if p.bold else ""
            rows.append(f'<text transform="translate({p.pos[0]:.4f},{fy(p.pos[1]):.4f}) rotate({-p.rot:g})" x="0" y="0" font-family="Arial" '
                        f'font-size="{cap_to_em(p.h):.4f}" text-anchor="{anchor}"{w} fill="#000000">{escape(p.s)}</text>')
    rows.append("</svg>")
    return "\n".join(rows)


# ---------------------------------------------------------------- inside FreeCAD
def _log(path, *a):
    line = " ".join(str(x) for x in a)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main():
    job = json.load(open(os.environ["DRAWING_JOB"], encoding="utf-8"))
    logp = job["log"]
    open(logp, "w", encoding="utf-8").close()
    code = 1
    try:
        import FreeCAD
        import FreeCADGui
        import TechDrawGui

        def pump(sec):
            end = time.perf_counter() + sec
            while time.perf_counter() < end:
                FreeCADGui.updateGui()
                time.sleep(0.05)

        pr = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Colors")
        for k in ("PageColor", "PaperColor", "FaceColor"):
            pr.SetUnsigned(k, 0xFFFFFFFF)
        doc = FreeCAD.newDocument("Drawing")
        page = doc.addObject("TechDraw::DrawPage", "Page")
        tmpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        tmpl.Template = job["template"]
        page.Template = tmpl
        tmpl.EditableTexts = job["texts"]
        sym = doc.addObject("TechDraw::DrawViewSymbol", "Plan")
        page.addView(sym)
        sym.Symbol = open(job["symbol"], encoding="utf-8").read()
        sym.Scale = 1.0
        sym.X, sym.Y = job.get("sheet_w", 420.0) / 2, job.get("sheet_h", 297.0) / 2
        doc.recompute()
        pump(1.0)
        page.ViewObject.doubleClicked()
        pump(2.0)
        page.touch()
        doc.recompute()
        pump(3.0)
        for key, fn in (("pdf", TechDrawGui.exportPageAsPdf), ("svg", TechDrawGui.exportPageAsSvg)):
            if os.path.isfile(job[key]):
                os.remove(job[key])
            fn(page, job[key])
            _log(logp, key, os.path.getsize(job[key]) if os.path.isfile(job[key]) else "MISSING")
        code = 0 if os.path.isfile(job["pdf"]) and os.path.getsize(job["pdf"]) > 0 else 1
    except Exception:  # noqa: BLE001
        import traceback

        _log(logp, "EXCEPTION", traceback.format_exc())
    finally:
        _log(logp, "EXIT", code)
        os._exit(code)


if os.environ.get("DRAWING_JOB"):
    main()
