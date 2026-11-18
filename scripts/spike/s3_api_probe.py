"""S3 prep: how can a TechDraw view get dashed / dash-dot edges? (console: run_spike.ps1 -Name s3_api_probe -Console)"""
import os
import sys

sys.path.insert(0, os.environ.get("SPIKE_DIR", os.path.dirname(os.path.abspath(__file__))))
import _common as C  # noqa: E402


def main():
    C.start("s3_api_probe")
    import FreeCAD
    import Part
    from FreeCAD import Vector as V

    doc = FreeCAD.newDocument("P")
    page, _ = C.new_page(doc, C.write_template(os.path.join(C.OUT, "A3_TCVN5571_template.svg")))
    obj = doc.addObject("Part::Feature", "L")
    obj.Shape = Part.makePolygon([V(0, 0, 0), V(100, 0, 0)])
    view = doc.addObject("TechDraw::DrawViewPart", "View")
    page.addView(view)
    view.Source = [obj]
    doc.recompute()
    for fn in ("formatGeometricEdge", "makeCosmeticLine", "getCosmeticEdge", "makeCenterLine", "getCenterLine"):
        C.log(fn, "doc:", (getattr(view, fn).__doc__ or "").strip().replace("\n", " ")[:300])
    tag = view.makeCosmeticLine(V(0, 10, 0), V(100, 10, 0))
    C.log("cosmetic line tag:", tag)
    ce = view.getCosmeticEdge(tag)
    C.log("cosmetic edge obj:", type(ce), [a for a in dir(ce) if not a.startswith("_")])
    C.log("view.GeomFormats:", view.GeomFormats, "| CosmeticEdges:", view.CosmeticEdges)
    return True


C.run(main)
