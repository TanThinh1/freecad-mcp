"""Scale selection for the A3 TCVN sheet.

The drawing area is the frame (390 x 277) minus the title-block corner (180 x 65): an L-shape. A rectangle fits the
L-shape iff it fits the top band (390 x 212) or the left band (210 x 277).
"""
from __future__ import annotations

from tcvn import A3, FRAME_X0, FRAME_X1, FRAME_Y0, FRAME_Y1, SHEET_ORDER, SHEETS, TB_H, TB_W, TB_X0, TB_Y1

SCALES = (20, 50, 100, 200, 500)       # TCVN 7286:2003 reduction series available on an A3-A1 drawing (profile.yaml: 1:20, 1:50, 1:100, 1:200, 1:500)
FRAME_W, FRAME_H = FRAME_X1 - FRAME_X0, FRAME_Y1 - FRAME_Y0
# usable regions in sheet coordinates (x0, y0, x1, y1)
BAND_TOP = (FRAME_X0, TB_Y1, FRAME_X1, FRAME_Y1)
BAND_LEFT = (FRAME_X0, FRAME_Y0, TB_X0, FRAME_Y1)


def fit_in_sheet(pw, ph, sheet=A3):
    """(band, region) of the L-shaped drawing area of `sheet` that holds a pw x ph (paper mm) block, or None. Top band = above the title block, left band = left of it."""
    if pw <= sheet.frame_w and ph <= sheet.frame_h - sheet.tb_h:
        return "top", (sheet.x0, sheet.tb_y1, sheet.x1, sheet.y1)
    if pw <= sheet.frame_w - sheet.tb_w and ph <= sheet.frame_h:
        return "left", (sheet.x0, sheet.y0, sheet.tb_x0, sheet.y1)
    return None


def sheet_scale_candidates(only_scale=None, only_sheet=None, limit=None, scales=SCALES):
    """Order in which (sheet name, scale) pairs are tried: sheets A3 -> A2 -> A1; within a sheet the largest scale first.
    Phase 1 uses only scales up to 1:limit (the finest scales, 1:20 ... 1:limit); only when no sheet fits there, phase 2 tries all scales (1:500 too)
    on A3, A2, A1 in turn. only_scale / only_sheet restrict the search (explicit ty_le / kho_giay)."""
    sheets = [only_sheet] if only_sheet else list(SHEET_ORDER)
    scs = [only_scale] if only_scale else sorted(scales)
    out = []
    if only_scale or limit is None:
        return [(sh, sc) for sh in sheets for sc in scs]
    out += [(sh, sc) for sh in sheets for sc in scs if sc <= limit]
    out += [(sh, sc) for sh in sheets for sc in scs if sc > limit]
    return out


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


class ScaleReject(Exception):
    """Raised by an extent function when a scale is unusable for a reason other than size (e.g. step numbers would overlap)."""


def fit_scale(extent_at, gap_mm=5.0, scales=SCALES, only=None):
    """Same L-shaped drawing area, but the annotated extents come from the real layout: extent_at(scale) -> (paper_w, paper_h).

    only: a single scale to test (explicit ty_le). Returns dict(scale, band, region, paper_w, paper_h, reason); ValueError if nothing fits.
    No rotation of the drawing is attempted.
    """
    tried = []
    for s in ([only] if only else sorted(scales)):
        try:
            pw, ph = extent_at(s)
        except ScaleReject as e:
            tried.append(f"1:{s} bị loại: {e}")
            continue
        pw, ph = pw + 2 * gap_mm, ph + 2 * gap_mm
        if pw <= FRAME_W and ph <= FRAME_H - TB_H:
            band, region = "top", BAND_TOP
        elif pw <= FRAME_W - TB_W and ph <= FRAME_H:
            band, region = "left", BAND_LEFT
        else:
            tried.append(f"1:{s} cần {pw:.0f}×{ph:.0f} mm")
            continue
        why = (f"1:{s} " + ("(người dùng chọn) " if only else f"là tỷ lệ lớn nhất trong dãy {'/'.join(map(str, scales))} mà bố cục tổng hợp ") +
               f"({pw:.0f}×{ph:.0f} mm gồm cả kích thước và tên hình) nằm trong " +
               ("dải trên 390×212" if band == "top" else "dải trái 210×277") + " mm của vùng vẽ (khung 390×277 trừ góc khung tên 180×65)")
        if tried:
            why += "; không vừa: " + ", ".join(tried)
        return dict(scale=s, band=band, region=region, paper_w=pw, paper_h=ph, reason=why)
    raise ValueError("Không vừa vùng vẽ A3 (khung 390×277 trừ góc khung tên 180×65): " + ", ".join(tried) + ". Không tự xoay hình.")


def _overlaps_tb(r, tx, ty, gap, sheet=A3):
    """True when rect r (x0, y0, x1, y1) translated by (tx, ty) and grown by gap overlaps the title-block corner (open test: touching is fine)."""
    return (r[2] + tx + gap > sheet.tb_x0 and r[0] + tx - gap < sheet.x1 and r[1] + ty - gap < sheet.tb_y1 and r[3] + ty + gap > sheet.y0)


def _clearance(rects, tx, ty, sheet=A3):
    """Smallest distance (mm) from any rect to the frame edges or to the title-block corner (negative = overlap)."""
    c = 1e9
    for r in rects:
        c = min(c, r[0] + tx - sheet.x0, sheet.x1 - (r[2] + tx), r[1] + ty - sheet.y0, sheet.y1 - (r[3] + ty), max(sheet.tb_x0 - (r[2] + tx), (r[1] + ty) - sheet.tb_y1))
    return c


def place_rects(rects, gap_mm=5.0, sheet=A3):
    """Translate a group of rigid rectangles (x0, y0, x1, y1; relative positions fixed) into the L-shaped drawing area.

    Every rectangle must keep gap_mm to the frame and to the title-block corner. Returns the translation (tx, ty) with the largest
    minimum clearance (ties: closest to the middle of the frame), or None if the group does not fit. Never rotates anything.
    """
    ux0, uy0 = min(r[0] for r in rects), min(r[1] for r in rects)
    ux1, uy1 = max(r[2] for r in rects), max(r[3] for r in rects)
    tx_lo, tx_hi = sheet.x0 + gap_mm - ux0, sheet.x1 - gap_mm - ux1
    ty_lo, ty_hi = sheet.y0 + gap_mm - uy0, sheet.y1 - gap_mm - uy1
    if tx_lo > tx_hi + 1e-9 or ty_lo > ty_hi + 1e-9:
        return None
    xs, ys = {tx_lo, tx_hi}, {ty_lo, ty_hi}
    for r in rects:
        xs.add(sheet.tb_x0 - gap_mm - r[2])
        ys.add(sheet.tb_y1 + gap_mm - r[1])
    cand = [(x, y) for x in xs for y in ys if tx_lo - 1e-9 <= x <= tx_hi + 1e-9 and ty_lo - 1e-9 <= y <= ty_hi + 1e-9
            and not any(_overlaps_tb(r, x, y, gap_mm - 1e-9, sheet) for r in rects)]
    if not cand:
        return None
    cx, cy = (sheet.x0 + sheet.x1) / 2, (sheet.y0 + sheet.y1) / 2
    best, best_key = None, None
    x = tx_lo
    nx = max(1, int((tx_hi - tx_lo) / 1.0))
    ny = max(1, int((ty_hi - ty_lo) / 1.0))
    for i in range(nx + 1):
        x = tx_lo + (tx_hi - tx_lo) * i / nx
        for j in range(ny + 1):
            y = ty_lo + (ty_hi - ty_lo) * j / ny
            if any(_overlaps_tb(r, x, y, gap_mm - 1e-9, sheet) for r in rects):
                continue
            key = (round(_clearance(rects, x, y, sheet), 6), -(abs((ux0 + ux1) / 2 + x - cx) + abs((uy0 + uy1) / 2 + y - cy)))
            if best_key is None or key > best_key:
                best, best_key = (x, y), key
    return best or cand[0]


if __name__ == "__main__":
    assert pick_scale((3000, 1500)) == 20
    r = layout_scale((15000, 20000))
    assert (r["scale"], r["band"]) == (100, "left"), r
    print("scale.py self-test OK;", layout_scale((36000, 16500), (15, 16.25, 41, 15))["reason"])
