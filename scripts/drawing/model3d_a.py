"""3D model of the stair from the SAME spec, built with Part (for demonstration and checking only; the drawings never use it).

Run inside FreeCADCmd:  FreeCADCmd model3d_a.py   with env MODEL_JOB = path of a JSON job:
  {n, H, b, w, t, bw, bd, fcstd, result}
Geometry (mm): run +x, width +y, elevation +z; n-1 steel-plate treads (b x w x t, top at z = i*h) and two box stringers
(solid prisms of width bw, depth bd measured perpendicular to the slope) along y in [0, bw] and [w-bw, w].
Writes the FCStd, a preview PNG (software-rendered, job["png"]) and a result JSON (bounding box, counts, tread tops, volumes).
"""
import json
import math
import os
import sys
import traceback

res = {"ok": False}
try:
    import FreeCAD
    import Part

    job = json.load(open(os.environ["MODEL_JOB"], encoding="utf-8"))
    n, H, b, w, t, bw, bd = (job[k] for k in ("n", "H", "b", "w", "t", "bw", "bd"))
    h, L = H / n, (n - 1) * b
    V = FreeCAD.Vector
    doc = FreeCAD.newDocument("Stair")
    treads = []
    for i in range(1, n):
        o = doc.addObject("Part::Feature", f"Tread{i:02d}")
        o.Shape = Part.makeBox(b, w, t, V((i - 1) * b, 0, i * h - t))
        treads.append(o)
    theta = math.atan2(h, b)
    off = bd / math.cos(theta)
    if h - off >= 0:
        poly = [(0, h - off), (0, h), (L, H), (L, H - off)]
    else:
        x0 = (off - h) * b / h
        poly = [(0, 0), (0, h), (L, H), (L, H - off), (x0, 0)]
    stringers = []
    for k, y0 in enumerate((0.0, w - bw), start=1):
        wire = Part.makePolygon([V(x, y0, z) for x, z in poly] + [V(poly[0][0], y0, poly[0][1])])
        o = doc.addObject("Part::Feature", f"Stringer{k}")
        o.Shape = Part.Face(wire).extrude(V(0, bw, 0))
        stringers.append(o)
    doc.recompute()
    bb = FreeCAD.BoundBox()
    for o in treads + stringers:
        bb.add(o.Shape.BoundBox)
    res.update(ok=True, n_treads=len(treads), n_stringers=len(stringers),
               bbox=dict(xmin=bb.XMin, xmax=bb.XMax, ymin=bb.YMin, ymax=bb.YMax, zmin=bb.ZMin, zmax=bb.ZMax),
               tread_tops=[o.Shape.BoundBox.ZMax for o in treads], tread_volume=sum(o.Shape.Volume for o in treads),
               stringer_volume=sum(o.Shape.Volume for o in stringers), valid=all(o.Shape.isValid() for o in treads + stringers))
    doc.saveAs(job["fcstd"])
    res["fcstd"] = job["fcstd"]
    # Preview image: software renderer (tessellated Part shapes, axonometric projection, flat shading) - the hidden GUI has no
    # OpenGL context, so a normal 3D-view screenshot comes out blank.
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF

        a, e = math.radians(-25.0), math.radians(40.0)
        light = (-0.35, -0.55, 0.76)
        ln = math.sqrt(sum(c * c for c in light))
        light = tuple(c / ln for c in light)
        tris = []
        for o, base in [(o, (150, 165, 185)) for o in treads] + [(o, (95, 105, 125)) for o in stringers]:
            verts, faces = o.Shape.tessellate(1.0)
            todo = [[(verts[i].x, verts[i].y, verts[i].z) for i in fa] for fa in faces]
            pieces = []
            while todo:  # split long triangles so the painter's sort by depth stays correct
                p = todo.pop()
                el = max(math.dist(p[i], p[(i + 1) % 3]) for i in range(3))
                if el > 150.0:
                    m = [tuple((p[i][k] + p[(i + 1) % 3][k]) / 2 for k in range(3)) for i in range(3)]
                    todo += [[p[0], m[0], m[2]], [m[0], p[1], m[1]], [m[2], m[1], p[2]], [m[0], m[1], m[2]]]
                else:
                    pieces.append(p)
            for p in pieces:
                ux, uy, uz = (p[1][k] - p[0][k] for k in range(3))
                vx, vy, vz = (p[2][k] - p[0][k] for k in range(3))
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                shade = 0.40 + 0.60 * abs((nx * light[0] + ny * light[1] + nz * light[2]) / nl)
                scr = []
                depth = 0.0
                for (x, y, z) in p:
                    xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
                    scr.append((xr, z * math.cos(e) + yr * math.sin(e)))
                    depth += yr * math.cos(e) - z * math.sin(e)
                tris.append((depth / 3.0, scr, tuple(min(255, int(c * shade)) for c in base)))
        xs = [q[0] for _, s_, _ in tris for q in s_]
        ys = [q[1] for _, s_, _ in tris for q in s_]
        W, Hh, M = 1600, 1000, 60
        sc = min((W - 2 * M) / (max(xs) - min(xs)), (Hh - 2 * M) / (max(ys) - min(ys)))
        img = QImage(W, Hh, QImage.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        pt = QPainter(img)
        pt.setRenderHint(QPainter.Antialiasing, True)
        pt.setPen(QPen(QColor(40, 45, 55), 0.8))
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        for _, s_, col in sorted(tris, key=lambda t_: -t_[0]):
            poly = QPolygonF([QPointF(W / 2 + (q[0] - cx) * sc, Hh / 2 - (q[1] - cy) * sc) for q in s_])
            pt.setBrush(QBrush(QColor(*col)))
            pt.setPen(QPen(QColor(*col), 0.6))
            pt.drawPolygon(poly)
        pt.end()
        if img.save(job["png"]):
            nonwhite = sum(1 for yy in range(0, Hh, 9) for xx in range(0, W, 9) if img.pixel(xx, yy) & 0xFFFFFF != 0xFFFFFF)
            if nonwhite > 50:
                res["png"] = job["png"]
            else:
                res["png_error"] = "ảnh trắng"
    except Exception:  # noqa: BLE001
        res["png_error"] = traceback.format_exc(limit=3)[-300:]
except Exception:  # noqa: BLE001
    res["error"] = traceback.format_exc(limit=5)
with open(json.load(open(os.environ["MODEL_JOB"], encoding="utf-8"))["result"], "w", encoding="utf-8") as fh:
    json.dump(res, fh)
sys.stdout.flush()
os._exit(0)
