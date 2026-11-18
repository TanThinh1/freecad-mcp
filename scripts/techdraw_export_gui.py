"""Export the TechDraw page saved by techdraw_smoke_test.py to PDF and SVG using the GUI layer.

Run with the FreeCAD GUI executable in hidden mode (no window)::

    freecad.exe --hidden scripts/techdraw_export_gui.py

Environment: ``TD_OUT_DIR`` (default ``./out``). Reads ``box_a4.FCStd`` from it and writes
``box_a4.pdf`` and ``box_a4.svg``. The process ends itself with ``os._exit`` so that no
user settings are written and no dialog can block it.
"""
from __future__ import annotations

import os
import time
import traceback

T0 = time.perf_counter()
OUT_DIR = os.path.abspath(os.environ.get("TD_OUT_DIR", "out"))
LOG = os.path.join(OUT_DIR, "techdraw_export_gui.log")


def log(*args: object) -> None:
    line = f"[{time.perf_counter() - T0:5.1f}s] " + " ".join(str(a) for a in args)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


code = 1
try:
    os.makedirs(OUT_DIR, exist_ok=True)
    open(LOG, "w").close()
    import FreeCAD
    import FreeCADGui
    import TechDrawGui

    log("FreeCAD", ".".join(FreeCAD.Version()[:3]), "| TechDrawGui import OK")
    doc = FreeCAD.openDocument(os.path.join(OUT_DIR, "box_a4.FCStd"))
    doc.recompute()
    page = next(o for o in doc.Objects if o.TypeId == "TechDraw::DrawPage")

    def pump(seconds: float) -> None:
        """Let the Qt event loop run so the page scene and its views get built."""
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            FreeCADGui.updateGui()
            time.sleep(0.05)

    # Without an MDI view for the page the exported scene contains only the template.
    page.ViewObject.doubleClicked()
    pump(2.0)
    page.touch()
    doc.recompute()
    pump(3.0)
    log("MDI view opened; views on page:", len(page.Views))

    pdf = os.path.join(OUT_DIR, "box_a4.pdf")
    svg = os.path.join(OUT_DIR, "box_a4.svg")
    for p in (pdf, svg):
        if os.path.isfile(p):
            os.remove(p)
    TechDrawGui.exportPageAsPdf(page, pdf)
    log("pdf:", os.path.getsize(pdf) if os.path.isfile(pdf) else "MISSING")
    TechDrawGui.exportPageAsSvg(page, svg)
    log("svg:", os.path.getsize(svg) if os.path.isfile(svg) else "MISSING")

    # Guard against a "template only" export: the SVG must have more paths than the template alone.
    def n_paths(path: str) -> int:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().count("<path")

    base = n_paths(page.Template.Template)
    got = n_paths(svg) if os.path.isfile(svg) else 0
    log(f"svg <path> count: template={base} exported={got} -> views_present={got > base}")
    ok = all(os.path.isfile(p) and os.path.getsize(p) > 0 for p in (pdf, svg)) and got > base
    log("RESULT", "PASS" if ok else "FAIL")
    code = 0 if ok else 1
except Exception:  # noqa: BLE001
    log("EXCEPTION:\n" + traceback.format_exc())
finally:
    os._exit(code)
