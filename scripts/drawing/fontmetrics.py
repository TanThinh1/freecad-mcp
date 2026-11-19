"""Arial text widths (advance widths from the TrueType 'hmtx' table), stdlib only.

Two sources that must agree:
  * the real TrueType file (C:\\Windows\\Fonts\\arial.ttf / arialbd.ttf; folder overridable with the FONT_DIR environment variable) read by the small parser
    below: used by verify.py as the independent measurement;
  * the embedded table arial_widths.py (generated from those files by `python fontmetrics.py --generate`): used by the drawing code, so a drawing
    gives the same result on a machine without Arial and in tests.

Width of a string at em size `em` and DXF width factor `wf`:  sum(advance) / unitsPerEm * em * wf  (no kerning: AutoCAD/ZWCAD TEXT does not kern).
"""
from __future__ import annotations

import os
import struct
import sys

FONT_FILES = {False: "arial.ttf", True: "arialbd.ttf"}
CODEPOINT_RANGES = [(0x20, 0x24F), (0x1E00, 0x1EFF), (0x2010, 0x2122), (0x2190, 0x21FF), (0x2200, 0x22FF)]     # Latin + Vietnamese + punctuation + arrows + maths


def font_dir() -> str:
    return os.environ.get("FONT_DIR") or os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def font_path(bold: bool = False) -> str:
    return os.path.join(font_dir(), FONT_FILES[bool(bold)])


class TTF:
    """Just enough of a TrueType reader: unitsPerEm, cmap (formats 4 and 12) and hmtx advance widths."""

    def __init__(self, path: str):
        self.path = path
        d = open(path, "rb").read()
        self.d = d
        n = struct.unpack(">H", d[4:6])[0]
        self.tables = {}
        for i in range(n):
            tag, _, off, ln = struct.unpack(">4sIII", d[12 + 16 * i: 28 + 16 * i])
            self.tables[tag.decode("latin-1")] = (off, ln)
        self.upem = struct.unpack(">H", d[self.tables["head"][0] + 18: self.tables["head"][0] + 20])[0]
        h = self.tables["hhea"][0]
        self.n_hm = struct.unpack(">H", d[h + 34: h + 36])[0]
        self.hmtx = self.tables["hmtx"][0]
        self.cmap = self._read_cmap()
        self.cache: dict = {}

    def _read_cmap(self) -> dict:
        d = self.d
        off = self.tables["cmap"][0]
        n = struct.unpack(">H", d[off + 2: off + 4])[0]
        subs = [struct.unpack(">HHI", d[off + 4 + 8 * i: off + 12 + 8 * i]) for i in range(n)]
        best = None
        for pid, eid, so in subs:
            if (pid, eid) in ((3, 10), (0, 4), (0, 6)):
                best = so
                break
            if (pid, eid) in ((3, 1), (0, 3)) and best is None:
                best = so
        if best is None:
            raise ValueError("no Unicode cmap in " + self.path)
        o = off + best
        fmt = struct.unpack(">H", d[o: o + 2])[0]
        m: dict = {}
        if fmt == 4:
            segx2 = struct.unpack(">H", d[o + 6: o + 8])[0]
            seg = segx2 // 2
            ends = struct.unpack(f">{seg}H", d[o + 14: o + 14 + segx2])
            starts = struct.unpack(f">{seg}H", d[o + 16 + segx2: o + 16 + 2 * segx2])
            deltas = struct.unpack(f">{seg}h", d[o + 16 + 2 * segx2: o + 16 + 3 * segx2])
            ro_pos = o + 16 + 3 * segx2
            ros = struct.unpack(f">{seg}H", d[ro_pos: ro_pos + segx2])
            for i in range(seg):
                for c in range(starts[i], ends[i] + 1):
                    if c == 0xFFFF:
                        continue
                    if ros[i] == 0:
                        g = (c + deltas[i]) & 0xFFFF
                    else:
                        p = ro_pos + 2 * i + ros[i] + 2 * (c - starts[i])
                        g = struct.unpack(">H", d[p: p + 2])[0]
                        g = (g + deltas[i]) & 0xFFFF if g else 0
                    if g:
                        m[c] = g
        elif fmt == 12:
            ng = struct.unpack(">I", d[o + 12: o + 16])[0]
            for i in range(ng):
                s, e, g0 = struct.unpack(">III", d[o + 16 + 12 * i: o + 28 + 12 * i])
                for c in range(s, e + 1):
                    m[c] = g0 + c - s
        else:
            raise ValueError(f"unsupported cmap format {fmt}")
        return m

    def advance_units(self, ch: str):
        """Advance width in font units, or None when the font has no glyph for `ch`."""
        g = self.cmap.get(ord(ch))
        if g is None:
            return None
        k = min(g, self.n_hm - 1)
        return struct.unpack(">H", self.d[self.hmtx + 4 * k: self.hmtx + 4 * k + 2])[0]

    def advance_em(self, ch: str):
        a = self.advance_units(ch)
        return None if a is None else a / self.upem


_FONTS: dict = {}


def load_font(bold: bool = False):
    """The real TrueType font, or None when it is not installed."""
    key = (bool(bold), font_path(bold))
    if key not in _FONTS:
        try:
            _FONTS[key] = TTF(key[1])
        except (OSError, ValueError, KeyError, struct.error):
            _FONTS[key] = None
    return _FONTS[key]


def _table(bold: bool) -> dict:
    import arial_widths
    return arial_widths.BOLD if bold else arial_widths.REGULAR


def widest_capital_em(bold: bool = False) -> float:
    """Advance width (em) of the widest Vietnamese capital letter (W in Arial): the fallback for a character that has no measured width."""
    t = _table(bold)
    return max(t[ord(c)] for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZĐ") / t[0]


def char_em(ch: str, bold: bool = False, source: str = "table") -> float:
    if source == "ttf":
        f = load_font(bold)
        if f is not None:
            a = f.advance_em(ch)
            if a is not None:
                return a
    t = _table(bold)
    w = t.get(ord(ch))
    return widest_capital_em(bold) if w is None else w / t[0]


def text_em(s: str, bold: bool = False, source: str = "table") -> float:
    """Width of `s` in em (font size 1, width factor 1). source: "table" (embedded) or "ttf" (the installed font file, falls back to the table when it is missing)."""
    return sum(char_em(c, bold, source) for c in s)


def have_ttf(bold: bool = False) -> bool:
    return load_font(bold) is not None


def generate(path: str) -> None:
    out = ['"""Arial advance widths (font units, 2048 per em) generated by `python fontmetrics.py --generate` from arial.ttf / arialbd.ttf. Key 0 = unitsPerEm."""',
           "from __future__ import annotations", ""]
    for name, bold in (("REGULAR", False), ("BOLD", True)):
        f = load_font(bold)
        if f is None:
            raise SystemExit(f"{font_path(bold)} not found (set FONT_DIR)")
        items = [(0, f.upem)]
        for lo, hi in CODEPOINT_RANGES:
            for c in range(lo, hi + 1):
                a = f.advance_units(chr(c))
                if a is not None:
                    items.append((c, a))
        out.append(f"{name} = {{")
        row = []
        for c, a in items:
            row.append(f"{c}: {a}")
            if len(row) == 12:
                out.append("    " + ", ".join(row) + ",")
                row = []
        if row:
            out.append("    " + ", ".join(row) + ",")
        out += ["}", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))


if __name__ == "__main__":
    if "--generate" in sys.argv:
        target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arial_widths.py")
        generate(target)
        print("written", target)
    else:
        for s in sys.argv[1:] or ["NGUYỄN VĂN A"]:
            print(repr(s), "table", round(text_em(s), 4), "em; ttf", round(text_em(s, source="ttf"), 4), "em")
