"""Renderer-independent drawing primitives. Coordinates are sheet millimetres on paper (origin lower-left, y up).

One list of primitives feeds both renderers (DXF/DWG and PDF). `sheet=True` marks the frame and title block, which the PDF
renderer takes from the TechDraw template instead. Dimensions are drawn by us (extension lines, dimension line, 45-degree
ticks, text) with the same expansion for both outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tcvn import ARIAL_CAP


@dataclass(kw_only=True)
class Prim:
    layer: str
    tag: str = ""
    sheet: bool = False


@dataclass(kw_only=True)
class Line(Prim):
    p1: tuple
    p2: tuple


@dataclass(kw_only=True)
class Rect(Prim):
    p0: tuple
    p1: tuple


@dataclass(kw_only=True)
class Circle(Prim):
    c: tuple
    r: float


@dataclass(kw_only=True)
class Text(Prim):
    s: str
    pos: tuple            # baseline anchor
    h: float              # cap height on paper, mm
    rot: float = 0.0      # degrees, counter-clockwise
    halign: str = "left"  # left | center | right
    bold: bool = False


@dataclass(kw_only=True)
class Dim:
    """Linear dimension between two measured points (sheet mm). kind 'h': line_pos is the sheet y of the dimension line;
    kind 'v': line_pos is the sheet x. ext_from = coordinate (perpendicular to the line) where the extension lines start."""
    kind: str
    p1: tuple
    p2: tuple
    line_pos: float
    value: float          # real mm
    ext_from: float
    layer: str
    role: str = "chain"   # chain | overall | single
    ext_lines: bool = True


def fmt_value(v: float) -> str:
    """DIMDEC = 0: integer millimetres."""
    return f"{round(v):d}"


def expand_dim(d: Dim, P: dict) -> list[Prim]:
    """Dimension -> lines + ticks + text."""
    exo, exe, asz, gap, h = P["kt_exo"], P["kt_exe"], P["kt_mui_ten"], P["kt_khe_chu"], P["cao_chu_kich_thuoc"]
    out: list[Prim] = []
    tag = f"dim_{d.role}"
    if d.kind == "h":
        ly = d.line_pos
        sgn = -1.0 if ly < d.ext_from else 1.0
        for p in (d.p1, d.p2):
            if d.ext_lines:
                out.append(Line(layer=d.layer, tag=tag + "_ext", p1=(p[0], d.ext_from + sgn * exo), p2=(p[0], ly + sgn * exe)))
            out.append(Line(layer=d.layer, tag=tag + "_tick", p1=(p[0] - asz / 2, ly - asz / 2), p2=(p[0] + asz / 2, ly + asz / 2)))
        out.append(Line(layer=d.layer, tag=tag + "_line", p1=(d.p1[0], ly), p2=(d.p2[0], ly)))
        out.append(Text(layer=d.layer, tag=tag + "_text", s=fmt_value(d.value), pos=((d.p1[0] + d.p2[0]) / 2, ly + gap), h=h, halign="center"))
    else:
        lx = d.line_pos
        sgn = -1.0 if lx < d.ext_from else 1.0
        for p in (d.p1, d.p2):
            if d.ext_lines:
                out.append(Line(layer=d.layer, tag=tag + "_ext", p1=(d.ext_from + sgn * exo, p[1]), p2=(lx + sgn * exe, p[1])))
            out.append(Line(layer=d.layer, tag=tag + "_tick", p1=(lx - asz / 2, p[1] - asz / 2), p2=(lx + asz / 2, p[1] + asz / 2)))
        out.append(Line(layer=d.layer, tag=tag + "_line", p1=(lx, d.p1[1]), p2=(lx, d.p2[1])))
        out.append(Text(layer=d.layer, tag=tag + "_text", s=fmt_value(d.value), pos=(lx - gap, (d.p1[1] + d.p2[1]) / 2), h=h, rot=90.0, halign="center"))
    return out


@dataclass
class Drawing:
    name: str
    scale: int
    origin: tuple                      # sheet position of the model origin (axis 1/A): DXF = (sheet - origin) * scale
    prims: list = field(default_factory=list)
    dims: list = field(default_factory=list)
    fields: dict = field(default_factory=dict)    # title-block editable texts (field name -> text)
    info: dict = field(default_factory=dict)

    def add(self, *ps):
        self.prims.extend(ps)

    def add_dim(self, d: Dim, P: dict):
        self.dims.append(d)
        self.prims.extend(expand_dim(d, P))

    def by_tag(self, tag):
        return [p for p in self.prims if p.tag == tag]


def cap_to_em(h: float) -> float:
    """SVG font-size (em) that gives capital/digit height h."""
    return h / ARIAL_CAP
