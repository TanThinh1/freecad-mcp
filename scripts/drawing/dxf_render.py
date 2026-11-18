"""Renderer (a): primitives -> DXF AC1021 (UTF-8) via dxfw.py. Model coordinates are real mm (origin = axis 1 / axis A):
DXF = (sheet - origin) * scale, so the frame and title block appear at drawing scale around the building, as in a
model-space sheet. Text height = paper cap height * scale. $LTSCALE = scale with linetype patterns in paper mm."""
from __future__ import annotations

from dxfw import Dxf
from primitives import Circle, Drawing, Line, Rect, Text
from tcvn import LTYPES

STYLE = "TCVN-ARIAL"


def render_dxf(D: Drawing, profile: dict, path: str) -> str:
    s = D.scale
    ox, oy = D.origin
    T = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    d = Dxf(ltscale=float(s), utf8=True)
    for name, (desc, pat) in LTYPES.items():
        d.add_ltype(name, desc, pat)
    d.add_style(STYLE, "arial.ttf")
    for name, a in profile.items():
        d.add_layer(name, color=a["color"], ltype=a["ltype"], lw=a["lw"], plot=a["plot"])
    for p in D.prims:
        if isinstance(p, Line):
            d.line(p.layer, T(p.p1), T(p.p2))
        elif isinstance(p, Rect):
            a, b = T(p.p0), T(p.p1)
            d.rect(p.layer, a[0], a[1], b[0], b[1])
        elif isinstance(p, Circle):
            d.circle(p.layer, T(p.c), p.r * s)
        elif isinstance(p, Text):
            d.text(p.layer, p.s, T(p.pos), p.h * s, rot=p.rot, style=STYLE, halign=p.halign)
        else:
            raise TypeError(f"unsupported primitive {type(p).__name__}")
    return d.save(path)


def expected_counts(D: Drawing):
    """{(layer, DXF type): n} the DXF must contain."""
    names = {Line: "LINE", Rect: "LWPOLYLINE", Circle: "CIRCLE", Text: "TEXT"}
    out: dict = {}
    for p in D.prims:
        k = (p.layer, names[type(p)])
        out[k] = out.get(k, 0) + 1
    return out
