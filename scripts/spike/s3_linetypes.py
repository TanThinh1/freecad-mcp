"""S3: line types in PDF and DXF.

(a) TechDraw: one view with 6 straight edges formatted with formatGeometricEdge (styles 1..5 + a thick solid) -> PDF + TechDraw DXF.
(b) Draft: four layers (solid thick / solid thin / dashed / dash-dot) with one line each -> importDXF.export.
Check afterwards:
    python -I scripts\\spike\\pdf_probe.py out\\spike\\s3_linetypes.pdf --min-area 900
    python -I scripts\\spike\\dxf_check.py out\\spike\\s3_techdraw.dxf
    python -I scripts\\spike\\dxf_check.py out\\spike\\s3_draft.dxf
Run: powershell -NoProfile -File scripts\\spike\\run_spike.ps1 -Name s3_linetypes
"""
import os
import sys

sys.path.insert(0, os.environ.get("SPIKE_DIR", os.path.dirname(os.path.abspath(__file__))))
import _common as C  # noqa: E402

# style number -> (weight mm); styles 1..5 tried at 0.25 mm, plus one 0.5 mm solid
SPEC = [(1, 0.5), (1, 0.25), (2, 0.25), (3, 0.25), (4, 0.25), (5, 0.25)]


def techdraw_part(doc):
    import Part
    import TechDraw
    from FreeCAD import Vector as V

    C.white_paper()
    edges = [Part.makePolygon([V(0, 8.0 * i, 0), V(100, 8.0 * i, 0)]) for i in range(len(SPEC))]
    obj = doc.addObject("Part::Feature", "Lines")
    obj.Shape = Part.makeCompound(edges)
    page, tmpl = C.new_page(doc, C.write_template(os.path.join(C.OUT, "A3_TCVN5571_template.svg")))
    tmpl.EditableTexts = {"cell3_l1": "S3 LOAI NET", "cell4": "S3"}
    view = doc.addObject("TechDraw::DrawViewPart", "View")
    page.addView(view)
    view.Source = [obj]
    view.Direction = V(0, 0, 1)
    view.XDirection = V(1, 0, 0)
    view.Scale = 1.0
    view.X, view.Y = 150.0, 150.0
    doc.recompute()
    C.pump(1.0)
    view.touch()
    doc.recompute()
    C.pump(1.0)
    ed = view.getVisibleEdges()
    C.log("visible edges:", len(ed))
    # view coordinates have Y flipped: the edge at model y=8*i has view y = ymax - 8*i
    ys = sorted(((e.BoundBox.YMin + e.BoundBox.YMax) / 2, i) for i, e in enumerate(ed))
    ys_desc = list(reversed(ys))      # model y ascending == view y descending
    for rank, (yy, idx) in enumerate(ys_desc):
        style, weight = SPEC[rank]
        C.log(f"  edge #{idx} view-y={yy:.1f} (model y={8 * rank}) -> style={style} weight={weight}")
        view.formatGeometricEdge(idx, style, weight, (0.0, 0.0, 0.0, 1.0), True)
    doc.recompute()
    C.pump(1.0)
    out = C.export_page(page, "s3_linetypes")
    dxf = os.path.join(C.OUT, "s3_techdraw.dxf")
    TechDraw.writeDXFPage(page, dxf)
    C.log("TechDraw DXF:", dxf, os.path.getsize(dxf), "bytes")
    return out


def draft_part(doc):
    import Draft
    import importDXF
    from FreeCAD import Vector as V

    specs = [("NET-CHINH", "Solid", 3.0), ("NET-MANH", "Solid", 1.0), ("NET-KHUAT", "Dashed", 1.0), ("NET-TAM", "Dashdot", 1.0)]
    objs = []
    for i, (name, style, width) in enumerate(specs):
        lay = Draft.make_layer(name, line_color=(0.0, 0.0, 0.0), shape_color=(0.8, 0.8, 0.8), line_width=width, draw_style=style)
        ln = Draft.make_line(V(0, 10.0 * i, 0), V(100, 10.0 * i, 0))
        lay.Proxy.addObject(lay, ln) if hasattr(lay, "Proxy") and hasattr(lay.Proxy, "addObject") else None
        objs.append(ln)
        C.log(f"draft layer {name}: DrawStyle={lay.ViewObject.DrawStyle} LineWidth={lay.ViewObject.LineWidth}; line in layers: {[o.Name for o in ln.InList]}")
    doc.recompute()
    path = os.path.join(C.OUT, "s3_draft.dxf")
    importDXF.export(objs, path)
    C.log("Draft DXF:", path, os.path.getsize(path), "bytes")


def main():
    C.start("s3_linetypes")
    import FreeCAD

    doc = FreeCAD.newDocument("S3")
    out = techdraw_part(doc)
    doc2 = FreeCAD.newDocument("S3b")
    FreeCAD.setActiveDocument(doc2.Name)
    try:
        draft_part(doc2)
    except Exception as exc:  # noqa: BLE001
        import traceback
        C.log("Draft route failed:", exc, "\n" + traceback.format_exc(limit=4))
    return os.path.isfile(out["pdf"])


C.run(main)
