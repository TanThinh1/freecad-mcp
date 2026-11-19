"""Minimal DXF writer (AC1015 / R2000, ASCII, stdlib only) used by the T5 spikes.

Why: FreeCAD's DXF exporters (TechDraw writeDXFPage, Draft importDXF.export) write only CONTINUOUS linetypes, colour 7,
no lineweights and object names as layer names (see S3). This writer gives full control of layers, linetypes (LTYPE with
dash patterns), lineweights, ACI colours and Unicode text (non-ASCII characters are written as \\U+XXXX, so the file is
pure ASCII and cannot trigger encoding errors).

Entities: LINE, CIRCLE, ARC, LWPOLYLINE, TEXT. No DIMENSION (it needs an anonymous block); dimensions are drawn as
lines + ticks + text by the caller.
"""
from __future__ import annotations

import math


def esc(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        out.append(ch if 32 <= o < 127 else f"\\U+{o:04X}" if o > 126 else " ")
    return "".join(out)


class Dxf:
    def __init__(self, ltscale: float = 1.0, insunits: int = 4, utf8: bool = False):
        """utf8=False: AC1015, pure ASCII with \\U+XXXX escapes. utf8=True: AC1021 (R2007), UTF-8 text without escapes."""
        self.ltscale, self.insunits, self.utf8 = ltscale, insunits, utf8
        self._h = 0x30
        self.ltypes = {"BYBLOCK": ("", []), "BYLAYER": ("", []), "CONTINUOUS": ("Solid line", [])}
        self.layers: dict[str, dict] = {"0": dict(color=7, ltype="CONTINUOUS", lw=25, plot=True)}
        self.styles = {"STANDARD": "arial.ttf"}
        self.ents: list[list[tuple[int, object]]] = []
        self.ext = [1e30, 1e30, -1e30, -1e30]

    def _e(self, s: str) -> str:
        return s if self.utf8 else esc(s)

    # ---- definitions
    def add_ltype(self, name: str, desc: str, pattern: list[float]) -> None:
        """pattern in drawing-independent mm: positive = dash, negative = gap (e.g. [3, -1]). Scaled by $LTSCALE."""
        self.ltypes[name.upper()] = (desc, pattern)

    def add_layer(self, name: str, color: int = 7, ltype: str = "CONTINUOUS", lw: int = 25, plot: bool = True) -> None:
        """lw in 1/100 mm (25 = 0.25 mm). 1-char layer names allowed; plot=False -> not plotted."""
        self.layers[name] = dict(color=color, ltype=ltype.upper(), lw=lw, plot=plot)

    def add_style(self, name: str, font: str = "arial.ttf") -> None:
        self.styles[name] = font

    # ---- entities
    def _handle(self) -> str:
        self._h += 1
        return f"{self._h:X}"

    def _grow(self, *pts) -> None:
        for x, y in pts:
            self.ext = [min(self.ext[0], x), min(self.ext[1], y), max(self.ext[2], x), max(self.ext[3], y)]

    def _ent(self, kind: str, layer: str, sub: list[tuple[int, object]]) -> None:
        if layer not in self.layers:
            raise KeyError(f"layer not defined: {layer}")
        self.ents.append([(0, kind), (5, self._handle()), (330, "MS"), (100, "AcDbEntity"), (8, layer)] + sub)

    def line(self, layer, p1, p2):
        self._grow(p1, p2)
        self._ent("LINE", layer, [(100, "AcDbLine"), (10, p1[0]), (20, p1[1]), (30, 0.0), (11, p2[0]), (21, p2[1]), (31, 0.0)])

    def circle(self, layer, c, r):
        self._grow((c[0] - r, c[1] - r), (c[0] + r, c[1] + r))
        self._ent("CIRCLE", layer, [(100, "AcDbCircle"), (10, c[0]), (20, c[1]), (30, 0.0), (40, r)])

    def arc(self, layer, c, r, a0_deg, a1_deg):
        self._grow((c[0] - r, c[1] - r), (c[0] + r, c[1] + r))
        self._ent("ARC", layer, [(100, "AcDbCircle"), (10, c[0]), (20, c[1]), (30, 0.0), (40, r), (100, "AcDbArc"), (50, a0_deg), (51, a1_deg)])

    def lwpolyline(self, layer, pts, closed=False):
        self._grow(*pts)
        sub = [(100, "AcDbPolyline"), (90, len(pts)), (70, 1 if closed else 0)]
        for x, y in pts:
            sub += [(10, x), (20, y)]
        self._ent("LWPOLYLINE", layer, sub)

    def rect(self, layer, x0, y0, x1, y1):
        self.lwpolyline(layer, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True)

    def text(self, layer, s, pos, height, rot=0.0, style="STANDARD", halign="left", wf=1.0):
        self._grow(pos)
        hj = {"left": 0, "center": 1, "right": 2}[halign]
        sub = [(100, "AcDbText"), (10, pos[0]), (20, pos[1]), (30, 0.0), (40, height), (1, self._e(s)), (50, rot)]
        if abs(wf - 1.0) > 1e-9:
            sub.append((41, float(wf)))                    # relative X scale (width factor)
        sub.append((7, style))
        if hj:
            sub += [(72, hj), (11, pos[0]), (21, pos[1]), (31, 0.0)]
        sub += [(100, "AcDbText"), (73, 0)]
        self._ent("TEXT", layer, sub)

    # ---- output
    def _w(self, out, code, val):
        if isinstance(val, float):
            val = f"{val:.6f}".rstrip("0").rstrip(".") or "0"
            if val in ("-0",):
                val = "0"
        out.append(f"{code:>3}\r\n{val}\r\n")

    def save(self, path: str) -> str:
        out: list[str] = []
        w = lambda c, v: self._w(out, c, v)
        hseed = 0
        # handles for table structure
        th = {n: f"{i:X}" for i, n in enumerate(["VPORT", "LTYPE", "LAYER", "STYLE", "APPID", "BLOCK_RECORD", "MS", "PS", "ROOT", "GROUP"], start=0x10)}
        # HEADER
        w(0, "SECTION"); w(2, "HEADER")
        for k, vals in [("$ACADVER", [(1, "AC1021" if self.utf8 else "AC1015")]), ("$HANDSEED", [(5, "FFFF")]), ("$INSUNITS", [(70, self.insunits)]),
                        ("$MEASUREMENT", [(70, 1)]), ("$LUNITS", [(70, 2)]), ("$LUPREC", [(70, 0)]),
                        ("$LTSCALE", [(40, float(self.ltscale))]), ("$TEXTSTYLE", [(7, "STANDARD")]), ("$CLAYER", [(8, "0")]),
                        ("$DWGCODEPAGE", [(3, "ANSI_1252")]),
                        ("$EXTMIN", [(10, self.ext[0] if self.ents else 0.0), (20, self.ext[1] if self.ents else 0.0), (30, 0.0)]),
                        ("$EXTMAX", [(10, self.ext[2] if self.ents else 0.0), (20, self.ext[3] if self.ents else 0.0), (30, 0.0)])]:
            w(9, k)
            for c, v in vals:
                w(c, v)
        w(0, "ENDSEC")
        # TABLES
        w(0, "SECTION"); w(2, "TABLES")

        def table(name, count, rows):
            w(0, "TABLE"); w(2, name); w(5, th[name]); w(330, 0); w(100, "AcDbSymbolTable"); w(70, count)
            for r in rows:
                for c, v in r:
                    w(c, v)
            w(0, "ENDTAB")

        table("VPORT", 0, [])
        lrows = []
        for n, (desc, pat) in self.ltypes.items():
            row = [(0, "LTYPE"), (5, self._handle()), (330, th["LTYPE"]), (100, "AcDbSymbolTableRecord"), (100, "AcDbLinetypeTableRecord"),
                   (2, n), (70, 0), (3, desc), (72, 65), (73, len(pat)), (40, float(sum(abs(p) for p in pat)))]
            for p in pat:
                row += [(49, float(p)), (74, 0)]
            lrows.append(row)
        table("LTYPE", len(lrows), lrows)
        yrows = []
        for n, a in self.layers.items():
            yrows.append([(0, "LAYER"), (5, self._handle()), (330, th["LAYER"]), (100, "AcDbSymbolTableRecord"), (100, "AcDbLayerTableRecord"),
                          (2, self._e(n)), (70, 0), (62, a["color"]), (6, a["ltype"]), (290, 1 if a["plot"] else 0), (370, a["lw"])])
        table("LAYER", len(yrows), yrows)
        srows = [[(0, "STYLE"), (5, self._handle()), (330, th["STYLE"]), (100, "AcDbSymbolTableRecord"), (100, "AcDbTextStyleTableRecord"),
                  (2, n), (70, 0), (40, 0.0), (41, 1.0), (50, 0.0), (71, 0), (42, 2.5), (3, f), (4, "")] for n, f in self.styles.items()]
        table("STYLE", len(srows), srows)
        table("APPID", 1, [[(0, "APPID"), (5, self._handle()), (330, th["APPID"]), (100, "AcDbSymbolTableRecord"), (100, "AcDbRegAppTableRecord"), (2, "ACAD"), (70, 0)]])
        table("BLOCK_RECORD", 2, [
            [(0, "BLOCK_RECORD"), (5, th["MS"]), (330, th["BLOCK_RECORD"]), (100, "AcDbSymbolTableRecord"), (100, "AcDbBlockTableRecord"), (2, "*Model_Space")],
            [(0, "BLOCK_RECORD"), (5, th["PS"]), (330, th["BLOCK_RECORD"]), (100, "AcDbSymbolTableRecord"), (100, "AcDbBlockTableRecord"), (2, "*Paper_Space")]])
        w(0, "ENDSEC")
        # BLOCKS
        w(0, "SECTION"); w(2, "BLOCKS")
        for nm, key in (("*Model_Space", "MS"), ("*Paper_Space", "PS")):
            w(0, "BLOCK"); w(5, self._handle()); w(330, th[key]); w(100, "AcDbEntity"); w(8, "0"); w(100, "AcDbBlockBegin")
            w(2, nm); w(70, 0); w(10, 0.0); w(20, 0.0); w(30, 0.0); w(3, nm); w(1, "")
            w(0, "ENDBLK"); w(5, self._handle()); w(330, th[key]); w(100, "AcDbEntity"); w(8, "0"); w(100, "AcDbBlockEnd")
        w(0, "ENDSEC")
        # ENTITIES
        w(0, "SECTION"); w(2, "ENTITIES")
        for e in self.ents:
            for c, v in e:
                w(c, th["MS"] if (c == 330 and v == "MS") else (self._e(v) if c == 8 else v))
        w(0, "ENDSEC")
        # OBJECTS
        w(0, "SECTION"); w(2, "OBJECTS")
        w(0, "DICTIONARY"); w(5, th["ROOT"]); w(330, 0); w(100, "AcDbDictionary"); w(281, 1); w(3, "ACAD_GROUP"); w(350, th["GROUP"])
        w(0, "DICTIONARY"); w(5, th["GROUP"]); w(330, th["ROOT"]); w(100, "AcDbDictionary"); w(281, 1)
        w(0, "ENDSEC")
        w(0, "EOF")
        text = "".join(out).replace("FFFF", f"{self._h + 0x10:X}", 1)
        with open(path, "w", encoding="utf-8" if self.utf8 else "ascii", newline="") as fh:
            fh.write(text)
        return path
