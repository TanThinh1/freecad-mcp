"""Scale selection for the A3 TCVN sheet.

The drawing area is the frame (390 x 277) minus the title-block corner (180 x 65): an L-shape. A rectangle fits the
L-shape iff it fits the top band (390 x 212) or the left band (210 x 277).
"""
from __future__ import annotations

from tcvn import FRAME_X0, FRAME_X1, FRAME_Y0, FRAME_Y1, TB_H, TB_W, TB_X0, TB_Y1

SCALES = (20, 25, 50, 100, 200, 500)
FRAME_W, FRAME_H = FRAME_X1 - FRAME_X0, FRAME_Y1 - FRAME_Y0
# usable regions in sheet coordinates (x0, y0, x1, y1)
BAND_TOP = (FRAME_X0, TB_Y1, FRAME_X1, FRAME_Y1)
BAND_LEFT = (FRAME_X0, FRAME_Y0, TB_X0, FRAME_Y1)


def _margins(m):
    if isinstance(m, (int, float)):
        return (float(m),) * 4
    left, right, bottom, top = m
    return float(left), float(right), float(bottom), float(top)


def paper_size(bbox_mm, scale, dims_margin_mm, gap_mm):
    w, h = bbox_mm
    ml, mr, mb, mt = _margins(dims_margin_mm)
    return w / scale + ml + mr + 2 * gap_mm, h / scale + mb + mt + 2 * gap_mm


def layout_scale(bbox_mm, dims_margin_mm=15.0, gap_mm=5.0, scales=SCALES):
    """Largest scale (smallest denominator) whose drawing + dimension margins fit the L-shaped area.

    bbox_mm = (width, height) of the model in real mm (no rotation); dims_margin_mm = paper mm reserved on each side
    (scalar or (left, right, bottom, top)); gap_mm = clearance to the frame/title block.
    Returns dict(scale, band, region, paper_w, paper_h, reason).
    """
    w, h = bbox_mm
    tried = []
    for s in sorted(scales):
        pw, ph = paper_size(bbox_mm, s, dims_margin_mm, gap_mm)
        if pw <= FRAME_W and ph <= FRAME_H - TB_H:
            band, region = "top", BAND_TOP
        elif pw <= FRAME_W - TB_W and ph <= FRAME_H:
            band, region = "left", BAND_LEFT
        else:
            tried.append(f"1:{s} cần {pw:.0f}×{ph:.0f} mm")
            continue
        why = f"1:{s} là tỷ lệ lớn nhất trong dãy {'/'.join(map(str, scales))} mà hình + chuỗi kích thước ({pw:.0f}×{ph:.0f} mm) nằm trong " \
              f"{'dải trên 390×212' if band == 'top' else 'dải trái 210×277'} mm của vùng vẽ (khung 390×277 trừ góc khung tên 180×65)"
        if tried:
            why += "; không vừa: " + ", ".join(tried)
        return dict(scale=s, band=band, region=region, paper_w=pw, paper_h=ph, reason=why)
    raise ValueError(f"Không vừa khung A3 ở tỷ lệ nhỏ nhất 1:{max(scales)} ({', '.join(tried[-2:])}).")


def pick_scale(bbox_mm, dims_margin_mm=15.0, gap_mm=5.0, scales=SCALES) -> int:
    return layout_scale(bbox_mm, dims_margin_mm, gap_mm, scales)["scale"]


if __name__ == "__main__":
    assert pick_scale((3000, 1500)) == 20
    r = layout_scale((15000, 20000))
    assert (r["scale"], r["band"]) == (100, "left"), r
    print("scale.py self-test OK;", layout_scale((36000, 16500), (15, 16.25, 41, 15))["reason"])
