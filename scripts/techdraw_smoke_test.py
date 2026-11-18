"""Headless TechDraw smoke test for the 2D drawing layer.

Run with FreeCAD's console executable (no GUI needed)::

    FreeCADCmd scripts/techdraw_smoke_test.py

Environment variables (all optional):

* ``TD_OUT_DIR``  output directory (default: ``./out`` relative to the CWD)
* ``TD_TEMPLATE`` template path relative to FreeCAD's ``Mod/TechDraw/Templates``
                  (default: ``ISO/A4_Landscape_ISO5457_minimal.svg``)

What it checks: ``import TechDraw`` works, a box with a through hole can be
projected onto an A4 page with three views, and the page exports to DXF.
Full-page SVG/PDF export needs the GUI layer (``TechDrawGui``), which is not
importable in FreeCADCmd; see ``scripts/techdraw_export_gui.py``.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import traceback

T0 = time.perf_counter()


def log(*args: object) -> None:
    print(f"[{time.perf_counter() - T0:5.1f}s]", *args, flush=True)


import FreeCAD  # noqa: E402
import Part  # noqa: E402
import TechDraw  # noqa: E402

log("FreeCAD", ".".join(FreeCAD.Version()[:3]), "| python", sys.version.split()[0], "| TechDraw import OK")

OUT_DIR = os.path.abspath(os.environ.get("TD_OUT_DIR", "out"))
TEMPLATE_REL = os.environ.get("TD_TEMPLATE", "ISO/A4_Landscape_ISO5457_minimal.svg")
TEMPLATE = os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw", "Templates", *TEMPLATE_REL.split("/"))
os.makedirs(OUT_DIR, exist_ok=True)
if not os.path.isfile(TEMPLATE):
    raise SystemExit(f"Template not found: {TEMPLATE}")
log("template:", TEMPLATE_REL)

# --- model: 50 x 30 x 10 box with a through hole D8 in the middle ---------------------------
doc = FreeCAD.newDocument("TD_Smoke")
box = doc.addObject("Part::Box", "Box")
box.Length, box.Width, box.Height = 50, 30, 10
hole = doc.addObject("Part::Cylinder", "Hole")
hole.Radius, hole.Height = 4, 12
hole.Placement.Base = FreeCAD.Vector(25, 15, -1)
part = doc.addObject("Part::Cut", "BoxWithHole")
part.Base, part.Tool = box, hole
doc.recompute()
shape = part.Shape
log(f"model: valid={shape.isValid()} volume={shape.Volume:.1f} (expected {50 * 30 * 10 - 3.14159265 * 16 * 10:.1f})")

# --- page + template -----------------------------------------------------------------------
page = doc.addObject("TechDraw::DrawPage", "Page")
tmpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
tmpl.Template = TEMPLATE
page.Template = tmpl

# --- three views: try an ISO first-angle projection group, else fall back to 3 single views ---
route = None
views = []
try:
    grp = doc.addObject("TechDraw::DrawProjGroup", "ProjGroup")
    page.addView(grp)
    grp.Source = [part]
    grp.ProjectionType = "First angle"
    grp.ScaleType = "Custom"
    grp.Scale = 2.0
    for name in ("Front", "Top", "Right"):
        grp.addProjection(name)
    # X/Y = centre of the Front (anchor) view, in mm from the page's lower-left corner. First angle
    # puts Top below Front and Right to the left of Front; keep them clear of the ISO5457 title
    # block (bottom-right, roughly x>105 mm and y<60 mm) and inside the frame.
    grp.X, grp.Y = 165, 150
    doc.recompute()
    views = list(grp.Views)
    route = "DrawProjGroup(first angle)"
except Exception:  # noqa: BLE001
    log("DrawProjGroup route failed, falling back:\n" + traceback.format_exc(limit=3))
    route = None

if route is None or len(views) != 3:
    for o in [o for o in doc.Objects if o.TypeId in ("TechDraw::DrawProjGroup", "TechDraw::DrawProjGroupItem")]:
        try:
            doc.removeObject(o.Name)
        except Exception:  # noqa: BLE001
            pass
    spec = [
        ("Front", (0, -1, 0), (1, 0, 0), 165, 150),
        ("Top", (0, 0, 1), (1, 0, 0), 165, 102),
        ("Right", (1, 0, 0), (0, 1, 0), 77, 150),
    ]
    views = []
    for name, d, xd, x, y in spec:
        v = doc.addObject("TechDraw::DrawViewPart", name)
        page.addView(v)
        v.Source = [part]
        v.Direction = FreeCAD.Vector(*d)
        v.XDirection = FreeCAD.Vector(*xd)
        v.Scale = 2.0
        v.X, v.Y = x, y
        views.append(v)
    doc.recompute()
    route = "3x DrawViewPart"

log(f"views route: {route} | views={len(views)}")
for v in views:
    try:
        n_vis = len(v.getVisibleEdges()) if hasattr(v, "getVisibleEdges") else -1
    except Exception as exc:  # noqa: BLE001
        n_vis = f"err:{type(exc).__name__}"
    log(f"  view {v.Name}: type={v.TypeId} visible_edges={n_vis}")

doc.recompute()
page.recompute(True) if hasattr(page, "recompute") else None

# --- exports ------------------------------------------------------------------------------
results: dict[str, str] = {}
# In FreeCADCmd the full-page SVG (page.PageResult) is normally empty: it is built by the GUI layer
# (TechDrawGui). Record it as an informational result, not a failure; PDF/SVG come from
# scripts/techdraw_export_gui.py. Per-view SVG fragments are available headless via viewPartAsSvg.
svg_src = getattr(page, "PageResult", "") or ""
log("PageResult (full-page SVG):", svg_src if svg_src else "(empty in console mode - expected)")
if svg_src and os.path.isfile(svg_src):
    svg_out = os.path.join(OUT_DIR, "box_a4_headless.svg")
    shutil.copyfile(svg_src, svg_out)
    results["svg_headless"] = svg_out
for v in views:
    try:
        frag = TechDraw.viewPartAsSvg(v)
        log(f"  viewPartAsSvg({v.Name}) -> {len(frag)} chars")
    except Exception as exc:  # noqa: BLE001
        log(f"  viewPartAsSvg({v.Name}) failed: {type(exc).__name__}: {exc}")

dxf_out = os.path.join(OUT_DIR, "box_a4.dxf")
try:
    TechDraw.writeDXFPage(page, dxf_out)
    results["dxf"] = dxf_out
except Exception:  # noqa: BLE001
    log("DXF export FAILED:\n" + traceback.format_exc(limit=3))

for kind, path in results.items():
    log(f"OUTPUT {kind}: {os.path.basename(path)} {os.path.getsize(path)} bytes")

fcstd = os.path.join(OUT_DIR, "box_a4.FCStd")
doc.saveAs(fcstd)
log("saved", os.path.basename(fcstd))
log("RESULT", "PASS" if "dxf" in results and len(views) == 3 else "FAIL")
