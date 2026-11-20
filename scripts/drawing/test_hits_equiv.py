"""Equivalence test: Sheetwork.hits() with the far-line shortcut must return exactly what the plain version returns, on every call made while building every type E example.

    python scripts/drawing/test_hits_equiv.py        (needs TCVN_PROFILE)
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import build_e  # noqa: E402
from build_e import Sheetwork, _seg_rect_gap, box_hits_circle, boxes_overlap, TEXT_GAP  # noqa: E402
from primitives import Circle, Line, Rect  # noqa: E402
from spec_b import SpecError  # noqa: E402
from spec_e import validate  # noqa: E402
from tcvn import read_profile  # noqa: E402


def plain_hits(self, box, exclude_tag="", m=None):
    """hits() as it was before the shortcut (every primitive measured)."""
    m = self.P["le_chu"] if m is None else m
    for p in self.prims:
        if exclude_tag and p.tag.startswith(exclude_tag):
            continue
        if isinstance(p, Line):
            if _seg_rect_gap(p.p1, p.p2, box) < m:
                return p.tag or "nét"
        elif isinstance(p, Rect):
            x0, y0, x1, y1 = p.p0[0], p.p0[1], p.p1[0], p.p1[1]
            if any(_seg_rect_gap(a, b, box) < m for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))):
                return p.tag or "hình chữ nhật"
        elif isinstance(p, Circle):
            if box_hits_circle(box, p.c, p.r, m):
                return p.tag or "vòng tròn"
    return "chữ khác" if any(boxes_overlap(box, b, TEXT_GAP) for b in self.boxes) else ""


def main():
    profile = read_profile()
    fast = Sheetwork.hits
    stats = dict(calls=0, hit=0, diff=0)

    def both(self, box, exclude_tag="", m=None):
        a, b = fast(self, box, exclude_tag, m), plain_hits(self, box, exclude_tag, m)
        stats["calls"] += 1
        stats["hit"] += bool(a)
        if a != b:
            stats["diff"] += 1
            print(f"DIFFERENT: fast {a!r} plain {b!r} box {box} m {m}")
        return a

    Sheetwork.hits = both
    built, skipped = 0, 0
    for path in sorted(glob.glob(os.path.join(HERE, "examples", "*.json"))):
        raw = json.load(open(path, encoding="utf-8"))
        if raw.get("loai") != "E":
            continue
        try:
            build_e.build(validate(raw), profile)
            built += 1
        except (SpecError, build_e.Unplaceable):
            skipped += 1                              # error examples stop early; the calls made before the error are still compared
    Sheetwork.hits = fast
    print(f"{built} ví dụ dựng được, {skipped} dừng do lỗi; {stats['calls']} lần gọi hits(), {stats['hit']} lần chạm, {stats['diff']} khác nhau")
    return 1 if stats["diff"] or not stats["calls"] else 0


if __name__ == "__main__":
    sys.exit(main())
