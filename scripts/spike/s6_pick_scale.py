"""S6: choose the drawing scale for an A3 TCVN sheet.

The drawing area is the frame (390 x 277) minus the title-block corner (180 x 65, bottom right): an L-shape. A rectangle
fits the L-shape iff it fits the top band (390 x 212) or the left band (210 x 277).

    pick_scale(bbox_mm, dims_margin_mm=15, gap_mm=5) -> int      # denominator, e.g. 100 for 1:100
    layout_scale(...) -> dict(scale, band, paper_w, paper_h)

bbox_mm = (width, height) of the model in real mm as it will appear on the sheet (no automatic rotation).
dims_margin_mm = paper mm reserved on EACH side for dimension chains / axis bubbles (scalar or (left, right, bottom, top)).
gap_mm = clear gap between that extent and the frame / title block.
Self-test: python -I scripts\\spike\\s6_pick_scale.py
"""
from __future__ import annotations

FRAME_W, FRAME_H = 390.0, 277.0
TB_W, TB_H = 180.0, 65.0
SCALES = (20, 25, 50, 100, 200, 500)


def _margins(m):
    if isinstance(m, (int, float)):
        return (float(m),) * 4
    left, right, bottom, top = m
    return float(left), float(right), float(bottom), float(top)


def layout_scale(bbox_mm, dims_margin_mm=15.0, gap_mm=5.0, scales=SCALES):
    w, h = bbox_mm
    ml, mr, mb, mt = _margins(dims_margin_mm)
    for s in sorted(scales):
        pw = w / s + ml + mr + 2 * gap_mm
        ph = h / s + mb + mt + 2 * gap_mm
        if pw <= FRAME_W and ph <= FRAME_H - TB_H:
            return dict(scale=s, band="top", paper_w=pw, paper_h=ph)
        if pw <= FRAME_W - TB_W and ph <= FRAME_H:
            return dict(scale=s, band="left", paper_w=pw, paper_h=ph)
    raise ValueError(f"does not fit at 1:{max(scales)}: need {w / max(scales) + ml + mr + 2 * gap_mm:.0f} x {h / max(scales) + mb + mt + 2 * gap_mm:.0f} mm")


def pick_scale(bbox_mm, dims_margin_mm=15.0, gap_mm=5.0, scales=SCALES) -> int:
    return layout_scale(bbox_mm, dims_margin_mm, gap_mm, scales)["scale"]


def _selftest():
    # house 16500 x 31750 mm (long side horizontal) -> 1:100 ; twice as large -> 1:200
    assert pick_scale((31750, 16500)) == 100, layout_scale((31750, 16500))
    assert pick_scale((63500, 33000)) == 200, layout_scale((63500, 33000))
    # small part: 3000 x 1500 -> the largest scale in the list
    assert pick_scale((3000, 1500)) == 20
    # 6000 x 4000: 1:20 is 300x200 (+40) -> too high for the top band -> 1:25
    assert pick_scale((6000, 4000)) == 25
    # tall plan 15000 x 20000 at 1:100 is 150 x 200 (+40 mm) = 190 x 240: too tall for the top band (212), fits the LEFT band
    r = layout_scale((15000, 20000))
    assert (r["scale"], r["band"]) == (100, "left"), r
    # beyond 1:500 -> error
    try:
        pick_scale((300000, 200000))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    # bigger dimension margin pushes to a smaller scale
    assert pick_scale((31750, 16500), dims_margin_mm=25) == 200
    print("pick_scale self-test: OK")
    for name, bb in (("house 31750x16500", (31750, 16500)), ("house x2 63500x33000", (63500, 33000)), ("3000x1500", (3000, 1500)), ("6000x4000", (6000, 4000))):
        print(f"  {name:<22} -> {layout_scale(bb)}")


if __name__ == "__main__":
    _selftest()
