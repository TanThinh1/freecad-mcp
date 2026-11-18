"""S2: TechDraw dimensions from Python: overall, chain, radius; DIMDEC=0, tick arrows, 2.5 mm text; export PDF/SVG.

Run: powershell -NoProfile -File scripts\\spike\\run_spike.ps1 -Name s2_dimensions
"""
import os
import sys

sys.path.insert(0, os.environ.get("SPIKE_DIR", os.path.dirname(os.path.abspath(__file__))))
import _common as C  # noqa: E402

SCALE = 50.0
FONTSIZE = 2.57


def main():
    C.start("s2_dimensions")
    import FreeCAD
    import Part
    import TechDraw
    from FreeCAD import Vector as V

    C.white_paper()
    doc = FreeCAD.newDocument("S2")
    # --- geometry: rectangle 3000 x 1500 split into 3 bottom edges (chain), plus a 180-degree arc R500
    pts = [V(0, 0, 0), V(1000, 0, 0), V(2000, 0, 0), V(3000, 0, 0), V(3000, 1500, 0), V(0, 1500, 0), V(0, 0, 0)]
    rect = doc.addObject("Part::Feature", "Rect")
    rect.Shape = Part.makePolygon(pts)
    arc = doc.addObject("Part::Feature", "Arc")
    arc.Shape = Part.ArcOfCircle(Part.Circle(V(4500, 750, 0), V(0, 0, 1), 500), 0.0, 3.141592653589793).toShape()
    doc.recompute()

    page, tmpl = C.new_page(doc, C.write_template(os.path.join(C.OUT, "A3_TCVN5571_template.svg")))
    tmpl.EditableTexts = {"cell3_l1": "S2 KÍCH THƯỚC", "cell7": "1:50", "cell4": "S2"}
    view = doc.addObject("TechDraw::DrawViewPart", "View")
    page.addView(view)
    view.Source = [rect, arc]
    view.Direction = V(0, 0, 1)
    view.XDirection = V(1, 0, 0)
    view.ScaleType = "Custom"
    view.Scale = 1.0 / SCALE
    view.X, view.Y = 130.0, 150.0
    doc.recompute()
    C.pump(1.0)
    view.touch()
    doc.recompute()
    C.pump(1.0)
    C.log("sources:", [(o.Name, o.Shape.ShapeType, len(o.Shape.Edges)) for o in view.Source], "| view state:", view.State)

    verts = view.getVisibleVertexes()
    edges = view.getVisibleEdges()
    C.log(f"view vertices={len(verts)} edges={len(edges)}")
    for i, v in enumerate(verts):
        C.log(f"  Vertex{i}: ({v.x:.3f}, {v.y:.3f}) view-units")
    for i, e in enumerate(edges):
        C.log(f"  Edge{i}: type={e.Curve.TypeId if hasattr(e, 'Curve') else '?'} len={e.Length:.3f} bbox=({e.BoundBox.XMin:.2f},{e.BoundBox.YMin:.2f})-({e.BoundBox.XMax:.2f},{e.BoundBox.YMax:.2f})")

    # rectangle vertices: those on the left part, identified by (x,y) relative to the minimum corner
    x0 = min(v.x for v in verts)
    ymax = max(v.y for v in verts)   # TechDraw view coordinates have Y flipped w.r.t. the model

    def find_vertex(px_mm, py_mm):
        """Vertex index nearest to (px,py) given in model mm relative to the rectangle's (0,0) corner."""
        best, bi = 1e9, None
        for i, v in enumerate(verts):
            d = abs(v.x - x0 - px_mm / SCALE) + abs(v.y - ymax + py_mm / SCALE)
            if d < best:
                best, bi = d, i
        return bi, best

    def make_dim(kind, refs, name):
        d = doc.addObject("TechDraw::DrawViewDimension", name)
        page.addView(d)
        d.Type = kind
        d.MeasureType = "Projected"
        d.References2D = refs
        d.FormatSpec = "%.0f"          # DIMDEC = 0
        d.ShowUnits = False
        return d

    dims = []
    vi = {n: find_vertex(*xy) for n, xy in {"A": (0, 0), "B": (1000, 0), "C": (2000, 0), "D": (3000, 0), "E": (3000, 1500), "F": (0, 1500)}.items()}
    C.log("vertex mapping (index, match error):", vi)
    ids = {k: v[0] for k, v in vi.items()}
    ref = lambda i: (view, f"Vertex{i}")
    dims.append(make_dim("DistanceX", [ref(ids["A"]), ref(ids["B"])], "ChainAB"))
    dims.append(make_dim("DistanceX", [ref(ids["B"]), ref(ids["C"])], "ChainBC"))
    dims.append(make_dim("DistanceX", [ref(ids["C"]), ref(ids["D"])], "ChainCD"))
    dims.append(make_dim("DistanceX", [ref(ids["A"]), ref(ids["D"])], "Overall"))
    dims.append(make_dim("DistanceY", [ref(ids["D"]), ref(ids["E"])], "Height"))
    # radius on the arc: find the edge index of the arc
    arc_i = next((i for i, e in enumerate(edges) if "Circle" in getattr(e.Curve, "TypeId", type(e.Curve).__name__) or "Circle" in type(e.Curve).__name__), None)
    C.log("arc edge index:", arc_i)
    if arc_i is not None:
        dims.append(make_dim("Radius", [(view, f"Edge{arc_i}")], "Rad"))
    doc.recompute()

    # --- positions (view-local mm; negative Y = below) and view-provider formatting
    vp0 = dims[0].ViewObject
    C.log("ViewProvider props:", vp0.PropertiesList)
    for p in ("ArrowStyle", "Fontsize", "Font", "LineWidth", "StandardAndStyle", "RenderingExtent", "Color", "Arrowsize"):
        if p in vp0.PropertiesList:
            try:
                en = vp0.getEnumerationsOfProperty(p) if vp0.getTypeIdOfProperty(p) == "App::PropertyEnumeration" else ""
            except Exception:  # noqa: BLE001
                en = ""
            C.log(f"  VP.{p} = {getattr(vp0, p)!r} {('enum=' + str(en)) if en else ''}")
    for d in dims:
        vp = d.ViewObject
        if "Fontsize" in vp.PropertiesList:
            # Measured: Fontsize 2.5 -> em 3.40 mm -> Arial digit height 2.43 mm. For a 2.5 mm digit height use 2.57.
            vp.Fontsize = FONTSIZE
        if "Font" in vp.PropertiesList:
            vp.Font = "Arial"
        if "ArrowStyle" in vp.PropertiesList:
            opts = vp.getEnumerationsOfProperty("ArrowStyle")
            pick = next((o for o in opts if "tick" in o.lower()), next((o for o in opts if "slash" in o.lower()), None))
            if pick:
                vp.ArrowStyle = pick
        if "LineWidth" in vp.PropertiesList:
            vp.LineWidth = 0.25
        if "Arrowsize" in vp.PropertiesList:
            vp.Arrowsize = 2.5
    C.log("dimension values (getValue if available):", {d.Name: (d.getValue() if hasattr(d, "getValue") else "n/a") for d in dims})
    # place labels (view-local mm, Y up; the rectangle spans x -50..10, y -15..15 at 1:50)
    mid = {"ChainAB": -40.0, "ChainBC": -20.0, "ChainCD": 0.0}
    for d in dims:
        if d.Name in mid:
            d.X, d.Y = mid[d.Name], -18.0
        elif d.Name == "Overall":
            d.X, d.Y = -20.0, -28.0
        elif d.Name == "Height":
            d.X, d.Y = 18.0, 0.0
        elif d.Name == "Rad":
            d.X, d.Y = 46.5, 6.5
            d.FormatSpec = "R%.0f"
    doc.recompute()
    out = C.export_page(page, "s2_dimensions")
    doc.saveAs(os.path.join(C.OUT, "s2_dimensions.FCStd"))
    return os.path.isfile(out["pdf"])


C.run(main)
