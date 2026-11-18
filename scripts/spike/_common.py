"""Shared helpers for the T5 spikes (run inside FreeCAD via scripts/spike/run_spike.ps1).

Geometry: A3 landscape, drawing frame 390x277 (left margin 20, other margins 10), title block
180x65 in the bottom-right corner (TCVN 5571:2012, figure 2). All SVG coordinates are mm, y down.
"""
from __future__ import annotations

import os
import time
import traceback
from xml.sax.saxutils import escape

OUT = os.path.abspath(os.environ.get("SPIKE_OUT", os.path.join(os.getcwd(), "out", "spike")))
os.makedirs(OUT, exist_ok=True)
T0 = time.perf_counter()
_LOG: str | None = None

# ---------------------------------------------------------------- geometry (mm)
SHEET_W, SHEET_H = 420.0, 297.0
FRAME_X, FRAME_Y, FRAME_W, FRAME_H = 20.0, 10.0, 390.0, 277.0
TB_W, TB_H = 180.0, 65.0
TB_X0 = FRAME_X + FRAME_W - TB_W      # 230
TB_Y0 = FRAME_Y + FRAME_H - TB_H      # 222
W_FRAME = 0.7                         # frame and title-block outline (same weight, TCVN 5571)
W_THIN = 0.25                         # inner dividers

# Cells: id -> (x, y, w, h) relative to the title block's top-left corner.
# Left block (x 0..90): top cell 1 (16 high) then 7 rows x 7 high, 3 columns 30/30/30 (cells 8-14).
# Right block (x 90..180): cell 2 (16), cell 3 (28), cell 7 (25x14), cell 5 (40x14), cell 4 (25x21),
# cell 15 (25x7), cell 6 (40x7). Column order in the bottom right is an assumption (see report).
CELLS = {
    "1": (0, 0, 90, 16),
    "2": (90, 0, 90, 16),
    "3": (90, 16, 90, 28),
    "7": (90, 44, 25, 14),
    "5": (115, 44, 40, 14),
    "4": (155, 44, 25, 21),
    "15": (90, 58, 25, 7),
    "6": (115, 58, 40, 7),
}
# Editable text fields: name -> (cell, centre-x offset in cell, baseline offset in cell, size mm, bold)
FIELDS = {
    "cell1_l1": ("1", 45, 6.5, 3.5, True),
    "cell1_l2": ("1", 45, 12.0, 3.5, False),
    "cell2_l1": ("2", 45, 6.5, 3.5, True),
    "cell2_l2": ("2", 45, 12.0, 3.5, False),
    "cell3_l1": ("3", 45, 12.0, 5.0, True),
    "cell3_l2": ("3", 45, 20.0, 5.0, True),
    "cell4": ("4", 12.5, 15.5, 5.0, True),
    "cell5": ("5", 20, 10.5, 3.5, False),
    "cell6": ("6", 20, 5.0, 3.5, False),
    "cell7": ("7", 12.5, 10.5, 3.5, False),
    "cell15": ("15", 12.5, 5.0, 3.5, False),
}
# Non-editable captions (size 2.5): (cell, x offset, baseline offset, text)
CAPTIONS = [
    ("3", 1.5, 3.4, "Tên bản vẽ"),
    ("7", 1.5, 3.4, "Tỷ lệ"),
    ("5", 1.5, 3.4, "Loại hồ sơ"),
    ("4", 1.5, 3.4, "Số hiệu"),
]


def log(*a: object) -> None:
    line = f"[{time.perf_counter() - T0:6.1f}s] " + " ".join(str(x) for x in a)
    try:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)   # console may be cp1252
    except Exception:  # noqa: BLE001
        pass
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def start(name: str) -> None:
    global _LOG
    _LOG = os.path.join(OUT, name + ".log")
    open(_LOG, "w", encoding="utf-8").close()
    log("start", name, "| out:", OUT)


def run(fn) -> None:
    """Run fn(); log exceptions; always end the process with os._exit (no user.cfg writes, no dialogs)."""
    code = 1
    try:
        res = fn()
        code = 0 if res in (None, True) else 1
    except Exception:  # noqa: BLE001
        log("EXCEPTION\n" + traceback.format_exc())
    finally:
        log("EXIT", code)
        os._exit(code)


# ---------------------------------------------------------------- template
def _line(x1, y1, x2, y2, w):
    return f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" style="stroke-width:{w:g}"/>'


def template_svg(defaults: dict[str, str] | None = None) -> str:
    """A3 landscape template: frame 390x277 + TCVN 5571 title block 180x65 with editable text cells."""
    defaults = defaults or {}
    x0, y0 = TB_X0, TB_Y0
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:freecad="https://www.freecad.org/wiki/index.php?title=Svg_Namespace" '
        f'width="{SHEET_W:g}mm" height="{SHEET_H:g}mm" viewBox="0 0 {SHEET_W:g} {SHEET_H:g}" version="1.1">',
        '<g id="drawing_frame" style="fill:none;stroke:#000000;stroke-linecap:butt;stroke-linejoin:miter">',
        f'<rect x="{FRAME_X:g}" y="{FRAME_Y:g}" width="{FRAME_W:g}" height="{FRAME_H:g}" style="stroke-width:{W_FRAME:g}"/>',
        "</g>",
        '<g id="title_block" style="fill:none;stroke:#000000;stroke-linecap:butt;stroke-linejoin:miter">',
        f'<rect x="{x0:g}" y="{y0:g}" width="{TB_W:g}" height="{TB_H:g}" style="stroke-width:{W_FRAME:g}"/>',
    ]
    L = []
    # horizontal lines across the full width: below the 16 mm top row
    L.append(_line(x0, y0 + 16, x0 + 180, y0 + 16, W_THIN))
    # left block: 6 internal horizontal lines (rows of 7), 2 vertical lines (30/30/30)
    for k in range(1, 7):
        L.append(_line(x0, y0 + 16 + 7 * k, x0 + 90, y0 + 16 + 7 * k, W_THIN))
    for cx in (30, 60):
        L.append(_line(x0 + cx, y0 + 16, x0 + cx, y0 + 65, W_THIN))
    # dividers between the left and right blocks (and in the top row)
    L.append(_line(x0 + 90, y0, x0 + 90, y0 + 65, W_THIN))
    # right block: cell 3 / cells 7,5,4 / row 14 split
    L.append(_line(x0 + 90, y0 + 44, x0 + 180, y0 + 44, W_THIN))      # below cell 3
    L.append(_line(x0 + 90, y0 + 58, x0 + 155, y0 + 58, W_THIN))      # between rows 12-13 and row 14
    L.append(_line(x0 + 115, y0 + 44, x0 + 115, y0 + 65, W_THIN))     # 25 | 40
    L.append(_line(x0 + 155, y0 + 44, x0 + 155, y0 + 65, W_THIN))     # 40 | 25 (cell 4)
    parts += L
    parts.append("</g>")
    parts.append('<g id="title_block_text" style="fill:#000000;stroke:none;font-family:Arial">')
    for cell, dx, dy, txt in CAPTIONS:
        cx, cy, _, _ = CELLS[cell]
        parts.append(f'<text x="{x0 + cx + dx:g}" y="{y0 + cy + dy:g}" style="font-size:2.5px">{escape(txt)}</text>')
    for name, (cell, dx, dy, size, bold) in FIELDS.items():
        cx, cy, _, _ = CELLS[cell]
        w = "font-weight:bold;" if bold else ""
        parts.append(
            f'<text id="{name}_field" x="{x0 + cx + dx:g}" y="{y0 + cy + dy:g}" freecad:editable="{name}" '
            f'style="{w}font-size:{size:g}px;text-anchor:middle"><tspan>{escape(defaults.get(name, ""))}</tspan></text>'
        )
    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def write_template(path: str, defaults: dict[str, str] | None = None) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(template_svg(defaults))
    return path


# ---------------------------------------------------------------- GUI helpers (need freecad.exe --hidden)
def white_paper() -> None:
    """In-process only (the process ends with os._exit, so user.cfg is never written)."""
    import FreeCAD

    p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Colors")
    for k in ("PageColor", "PaperColor", "FaceColor"):
        p.SetUnsigned(k, 0xFFFFFFFF)
    FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Colors").SetBool("ClearFace", True)


def pump(seconds: float) -> None:
    import FreeCADGui

    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        FreeCADGui.updateGui()
        time.sleep(0.05)


def new_page(doc, template_path: str, name: str = "Page"):
    page = doc.addObject("TechDraw::DrawPage", name)
    tmpl = doc.addObject("TechDraw::DrawSVGTemplate", name + "Template")
    tmpl.Template = template_path
    page.Template = tmpl
    return page, tmpl


def export_page(page, base: str) -> dict[str, str]:
    """Open the page MDI view first (otherwise only the template is exported), then write PDF + SVG."""
    import FreeCAD
    import TechDrawGui

    doc = page.Document
    page.ViewObject.doubleClicked()
    pump(2.0)
    page.touch()
    doc.recompute()
    pump(3.0)
    out = {}
    for ext, fn in (("pdf", TechDrawGui.exportPageAsPdf), ("svg", TechDrawGui.exportPageAsSvg)):
        p = os.path.join(OUT, f"{base}.{ext}")
        if os.path.isfile(p):
            os.remove(p)
        fn(page, p)
        out[ext] = p
        log(f"exported {ext}: {os.path.getsize(p) if os.path.isfile(p) else 'MISSING'} bytes")
    return out
