"""S2 prep: list the TechDraw Python API relevant to dimensions (console run: run_spike.ps1 -Name s2_api_probe -Console)."""
import os
import sys

sys.path.insert(0, os.environ.get("SPIKE_DIR", os.path.dirname(os.path.abspath(__file__))))
import _common as C  # noqa: E402


def main():
    C.start("s2_api_probe")
    import FreeCAD
    import Part
    import TechDraw

    C.log("TechDraw dim-ish functions:", [a for a in dir(TechDraw) if "im" in a.lower() or "make" in a.lower()])
    doc = FreeCAD.newDocument("P")
    page, _tmpl = C.new_page(doc, C.write_template(os.path.join(C.OUT, "A3_TCVN5571_template.svg")))
    view = doc.addObject("TechDraw::DrawViewPart", "View")
    page.addView(view)
    dim = doc.addObject("TechDraw::DrawViewDimension", "Dim")
    page.addView(dim)
    C.log("DrawViewDimension properties:", dim.PropertiesList)
    C.log("Type enum:", dim.getEnumerationsOfProperty("Type"))
    for p in ("ArrowStyle", "Arrowheads", "ArrowTailLength", "FormatSpec", "Fontsize", "Font", "Arbitrary", "UseDefaultDecimals", "Decimals", "FormatSpecOverTolerance"):
        if p in dim.PropertiesList:
            try:
                C.log(f"  {p} =", getattr(dim, p), "| enum:", dim.getEnumerationsOfProperty(p) if dim.getTypeIdOfProperty(p) == "App::PropertyEnumeration" else "")
            except Exception as exc:  # noqa: BLE001
                C.log("  ", p, "err", exc)
    C.log("view props with 'Cosmetic|Line|Hidden|Center|Style':", [p for p in view.PropertiesList if any(k in p for k in ("Cosmetic", "Line", "Hidden", "Center", "Style", "Smooth", "Iso"))])
    C.log("view methods:", [a for a in dir(view) if any(k in a.lower() for k in ("cosmetic", "center", "geom", "edge", "vertex"))])
    prm = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions")
    C.log("Dimensions param group keys (Int/Bool/Float/String):", prm.GetInts(), prm.GetBools(), prm.GetFloats(), prm.GetStrings())
    return True


C.run(main)
