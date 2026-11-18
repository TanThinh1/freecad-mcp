"""Drawing type B: grid axes + columns plan of a single-span steel building -> list of primitives.

Model: N = dai_nha / buoc_cot + 1 vertical axes (numbered 1..N, spacing buoc_cot) and 2 horizontal axes (A at y = 0, B at
y = nhip). A column at every intersection (2N columns), drawn as the section rectangle b (along x) by h (along y): the web
lies in the frame plane (across the span). The model origin (0,0) is the intersection of axis 1 and axis A.
Axis bubbles: numbers on top, letters on the left. Dimensions: chain + overall along the bottom, span on the right.
"""
from __future__ import annotations

import string

import titleblock as TBK
from primitives import Circle, Dim, Drawing, Line, Rect, Text, cap_to_em
from scale import BAND_LEFT, BAND_TOP, FRAME_H, FRAME_W, layout_scale, paper_size
from spec_b import SpecError
from tcvn import ARIAL_CAP, FRAME_X0, FRAME_X1, FRAME_Y0, FRAME_Y1, LAYER_AXIS, LAYER_BUBBLE, LAYER_COLUMN, LAYER_DIM, LAYER_TEXT, TB_H, TB_W

VIEW_TITLE = "MẶT BẰNG LƯỚI TRỤC VÀ CỘT"
DEFAULT_SHEET_NO = "KC-01"       # drawing number used when khung_ten.ky_hieu_ban_ve is empty
NEEDED_LAYERS = (LAYER_AXIS, LAYER_BUBBLE, LAYER_COLUMN, LAYER_DIM, LAYER_TEXT, "KHUNG-TEN", "NET-MANH")


def label_width(sec: dict, P: dict) -> float:
    """Estimated paper width of the column section label (Arial, cap height cao_chu_nhan)."""
    return TBK.est_width(sec["text"], cap_to_em(P["cao_chu_nhan"]))


def span_offset(P: dict, label_w: float) -> float:
    """Distance from the right axis end to the span dimension line: at least kt_dau_tien, and beyond the last column's label.
    The label starts 2 mm to the right of the column's right edge (= axis + hx) and the axis end is hx + truc_vuon_qua right
    of the axis, so the column half-width cancels: label end - axis end = label_w + 2 - truc_vuon_qua; +2 mm clearance."""
    return max(P["kt_dau_tien"], label_w + 4.0 - P["truc_vuon_qua"])


def margins_paper(P: dict, label_w: float = 0.0):
    """Paper mm reserved around the column bounding box: (left, right, bottom, top)."""
    ov, gap, dia = P["truc_vuon_qua"], P["khe_vong_truc"], P["duong_kinh_vong_truc"]
    bubble = ov + gap + dia
    right = ov + span_offset(P, label_w) + P["kt_exe"]
    bottom = (ov + P["kt_dau_tien"] + P["kt_giua_cac_duong"] + P["kt_exe"] + P["khoang_tieu_de"] + P["cao_chu_tieu_de"]
              + P["khoang_ghi_chu"] + P["cao_chu_ghi_chu"] * ARIAL_CAP)
    return bubble, right, bottom, bubble


def build(sp: dict, profile: dict) -> Drawing:
    missing = [n for n in NEEDED_LAYERS if n not in profile]
    if missing:
        raise SpecError([f"profile.yaml thiếu layer chuẩn cần dùng: {', '.join(missing)}."])
    P, sec = sp["params"], sp["section"]
    b, h = sec["b"], sec["h"]
    nhip, dai, buoc, N = sp["nhip"], sp["dai_nha"], sp["buoc_cot"], sp["so_truc_doc"]
    bbox = (dai + b, nhip + h)
    lw_lab = label_width(sec, P)
    mg = margins_paper(P, lw_lab)
    gap = P["khe_vung_ve"]

    # ---- scale
    if sp["scale"]:
        s = sp["scale"]
        pw, ph = paper_size(bbox, s, mg, gap)
        if pw <= FRAME_W and ph <= FRAME_H - TB_H:
            band, region = "top", BAND_TOP
        elif pw <= FRAME_W - TB_W and ph <= FRAME_H:
            band, region = "left", BAND_LEFT
        else:
            raise SpecError([f"ty_le = 1:{s} không vừa vùng vẽ: hình + kích thước cần {pw:.0f}×{ph:.0f} mm, vùng vẽ là khung 390×277 trừ góc khung tên 180×65."])
        reason = f"tỷ lệ do người dùng chọn 1:{s}; cần {pw:.0f}×{ph:.0f} mm, vừa " + ("dải trên 390×212" if band == "top" else "dải trái 210×277") + " mm"
    else:
        try:
            r = layout_scale(bbox, mg, gap)
        except ValueError as e:
            raise SpecError([str(e)])
        s, band, region, pw, ph, reason = r["scale"], r["band"], r["region"], r["paper_w"], r["paper_h"], r["reason"]

    # ---- placement: centre the annotated extents in the band
    ew, eh = bbox[0] / s + mg[0] + mg[1], bbox[1] / s + mg[2] + mg[3]
    rx0, ry0, rx1, ry1 = region
    ex0 = rx0 + ((rx1 - rx0) - ew) / 2
    ey0 = ry0 + ((ry1 - ry0) - eh) / 2
    ox = ex0 + mg[0] + (b / 2) / s          # sheet position of axis 1 / axis A
    oy = ey0 + mg[2] + (h / 2) / s
    sx = lambda x: ox + x / s
    sy = lambda y: oy + y / s
    D = Drawing(name=sp["ten"], scale=s, origin=(ox, oy))

    ov, gp, dia = P["truc_vuon_qua"], P["khe_vong_truc"], P["duong_kinh_vong_truc"]
    rb, hb = dia / 2, P["cao_chu_vong_truc"]
    hx, hy = (b / 2) / s, (h / 2) / s
    xs = [sx(i * buoc) for i in range(N)]
    ys = [sy(0.0), sy(nhip)]

    # ---- columns + labels
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            D.add(Rect(layer=LAYER_COLUMN, tag="column", p0=(x - hx, y - hy), p1=(x + hx, y + hy)))
            # label starts 2 mm to the right of the column's right edge, just above the horizontal axis
            D.add(Text(layer=LAYER_TEXT, tag="col_label", s=sec["text"], pos=(x + hx + 2.0, y + 1.2), h=P["cao_chu_nhan"]))
    # ---- axes + bubbles
    y_bot, y_top = ys[0] - hy - ov, ys[1] + hy + ov
    for i, x in enumerate(xs):
        D.add(Line(layer=LAYER_AXIS, tag="axis_v", p1=(x, y_bot), p2=(x, y_top)))
        cy = y_top + gp + rb
        D.add(Circle(layer=LAYER_BUBBLE, tag="bubble", c=(x, cy), r=rb))
        D.add(Text(layer=LAYER_BUBBLE, tag="bubble_text", s=str(i + 1), pos=(x, cy - hb / 2), h=hb, halign="center"))
    x_left, x_right = xs[0] - hx - ov, xs[-1] + hx + ov
    for j, y in enumerate(ys):
        D.add(Line(layer=LAYER_AXIS, tag="axis_h", p1=(x_left, y), p2=(x_right, y)))
        cx = x_left - gp - rb
        D.add(Circle(layer=LAYER_BUBBLE, tag="bubble", c=(cx, y), r=rb))
        D.add(Text(layer=LAYER_BUBBLE, tag="bubble_text", s=string.ascii_uppercase[j], pos=(cx, y - hb / 2), h=hb, halign="center"))

    # ---- dimensions: bottom chain + overall, right span
    chain_y = y_bot - P["kt_dau_tien"]
    overall_y = chain_y - P["kt_giua_cac_duong"]
    if N == 2:
        D.add_dim(Dim(kind="h", p1=(xs[0], y_bot), p2=(xs[1], y_bot), line_pos=chain_y, value=dai, ext_from=y_bot, layer=LAYER_DIM, role="single"), P)
        dim_bottom = chain_y - P["kt_exe"]
    else:
        for i in range(N - 1):
            D.add_dim(Dim(kind="h", p1=(xs[i], y_bot), p2=(xs[i + 1], y_bot), line_pos=chain_y, value=buoc, ext_from=y_bot, layer=LAYER_DIM, role="chain"), P)
        D.add_dim(Dim(kind="h", p1=(xs[0], y_bot), p2=(xs[-1], y_bot), line_pos=overall_y, value=dai, ext_from=chain_y - P["kt_exe"] + P["kt_exo"],
                      layer=LAYER_DIM, role="overall"), P)
        dim_bottom = overall_y - P["kt_exe"]
    span_off = span_offset(P, lw_lab)      # clears the last column's label
    D.add_dim(Dim(kind="v", p1=(x_right, ys[0]), p2=(x_right, ys[1]), line_pos=x_right + span_off, value=nhip, ext_from=x_right,
                  layer=LAYER_DIM, role="single"), P)

    # ---- view title + scale note
    xc = (xs[0] + xs[-1]) / 2
    cap_t = P["cao_chu_tieu_de"]
    t_base = dim_bottom - P["khoang_tieu_de"] - cap_t
    D.add(Text(layer=LAYER_TEXT, tag="title", s=VIEW_TITLE, pos=(xc, t_base), h=cap_t, halign="center", bold=True))
    n_base = t_base - P["khoang_ghi_chu"] - P["cao_chu_ghi_chu"] * ARIAL_CAP
    D.add(Text(layer=LAYER_TEXT, tag="scale_note", s=f"TỶ LỆ 1:{s}", pos=(xc, n_base), h=P["cao_chu_ghi_chu"], halign="center"))

    # ---- frame + title block (sheet=True: DXF only; PDF takes them from the template)
    meta = dict(sp["khung_ten"])
    if not meta.get("ten_ban_ve"):
        meta["ten_ban_ve"] = VIEW_TITLE
    if not meta.get("ky_hieu_ban_ve"):
        meta["ky_hieu_ban_ve"] = DEFAULT_SHEET_NO
    D.fields = TBK.fields_from_meta(meta, f"1:{s}")
    D.prims.extend(TBK.primitives(D.fields))

    D.info = dict(scale=s, reason=reason, band=band, N=N, n_columns=N * 2, n_axes=N + 2, section=sec["text"], column_b=b, column_h=h,
                  bbox_real=bbox, margins=mg, extents_paper=(ew, eh), origin=(ox, oy), nhip=nhip, dai_nha=dai, buoc_cot=buoc, params=P,
                  geometry=dict(y_bot=y_bot, y_top=y_top, x_left=x_left, x_right=x_right, xs=xs, ys=ys, title_base=t_base, note_base=n_base))
    # sanity: annotated content must stay inside the drawing frame
    low = n_base - 0.5
    if low < FRAME_Y0 or ex0 < FRAME_X0 - 1e-6 or ex0 + ew > FRAME_X1 + 1e-6:
        raise SpecError([f"nội bộ: nội dung vượt khung (đáy {low:.1f} mm, x {ex0:.1f}..{ex0 + ew:.1f})."])
    return D
