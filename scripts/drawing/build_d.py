"""Drawing type D: purlin plan of the roof of a single-span steel building (grid + columns of type B, purlin lines on layer XA-GO) -> primitives.

Model (real mm): axis 1 / axis A is the origin, N vertical axes spaced buoc_cot, horizontal axes A (y = 0) and B (y = nhip), a column at every intersection (as type B).
Purlins run along the building (x = 0 .. dai_nha). Roof 1 rises from axis A: its k-th purlin (k = 0..n) stands at y = k * half / n (half = nhip/2 with 2 roofs, nhip with 1 roof);
with 2 roofs roof 2 is the mirror image about the ridge y = nhip/2 and the two ridge purlins coincide in plan (drawn once). Layout: one view on one sheet, the largest standard scale
that fits (scale.place_rects, as type C). Right of the plan: the purlin spacing chain (n segments of half/n, total half = nhip/2 or nhip) then the span nhip.
Primitive tags: column, col_label, axis_v / axis_h, bubble / bubble_text, purlin (layer XA-GO), ridge_label, dim_* (dimension lines) and dim_ext_custom (extension lines of the span
dimension, drawn by hand), title, scale_note, col_note, note_purlin, note_count, note_real, note_proj.
"""
from __future__ import annotations

import string
from fractions import Fraction

import titleblock as TBK
from build_a import _moved, _moved_dim
from build_b import NEEDED_LAYERS as NEEDED_B
from primitives import Circle, Dim, Drawing, Line, Rect, Text, cap_to_em, drawing_extent, expand_dim
from scale import place_rects, sheet_scale_candidates
from spec_b import SpecError
from spec_c import percent_text, round_half_up
from spec_d import fmt_len
from tcvn import ARIAL_CAP, SHEETS, est_width, LAYER_AXIS, LAYER_BUBBLE, LAYER_COLUMN, LAYER_DIM, LAYER_TEXT

LAYER_PURLIN = "XA-GO"
NEEDED_LAYERS = NEEDED_B + (LAYER_PURLIN,)
VIEW_TITLE = "MẶT BẰNG XÀ GỒ MÁI"
RIDGE_LABEL = "TIM NÓC (HAI XÀ GỒ NÓC TRÙNG NHAU)"
SHEET_SCALE_LIMIT = 200          # A2 / A1 are used only when A3 does not hold the drawing at 1:200 or finer
DEFAULT_SHEET_NO = "KC-04"       # drawing number used when khung_ten.ky_hieu_ban_ve is empty
LABEL_CLEAR = 3.0                # paper mm kept free around a purlin-spacing label along its dimension line: two 45-degree ticks (2.5 mm bbox) + 0.5 mm


def spacing_label(sp: dict) -> str:
    return str(round_half_up(sp["proj_spacing"]))          # DIMDEC = 0 (as every dimension); the exact value is in the note and in the warning


def note_lines(sp: dict) -> list[tuple[str, str]]:
    """[(tag, text)] printed under the scale note, top to bottom."""
    n, m, half = sp["n"], sp["so_mai"], sp["half"]
    pur = sp["xa_go"]["text"] + (" (MẶC ĐỊNH)" if sp["xa_go_mac_dinh"] else "")
    if m == 2:
        count = f"SỐ LƯỢNG: 2 x {n + 1} = {2 * (n + 1)} XÀ GỒ (2 MÁI)"
    else:
        count = f"SỐ LƯỢNG: {n + 1} XÀ GỒ (1 MÁI, DỐC LÊN TRỤC B)"
    p = sp["proj_spacing"]
    proj = (f"{n} x {fmt_len(p)} = {fmt_len(half)}" if p.denominator == 1 else f"{fmt_len(half)}/{n} ≈ {fmt_len(p)}")
    real = f"KHOẢNG CÁCH THỰC DỌC MÁI: {sp['real_spacing_text']} MM (TỐI ĐA {sp['buoc_xa_go']:g} MM)"
    deg = f"{sp['theta_deg']:.1f}".replace(".", ",")
    slope = f"CHIẾU: {proj} MM; ĐỘ DỐC MÁI: {percent_text(sp['do_doc_mai'])}% ({deg}°)"
    return [("col_note", f"TẤT CẢ CỘT: {sp['section']['text']}"), ("note_purlin", f"XÀ GỒ {pur}"), ("note_count", count), ("note_real", real), ("note_proj", slope)]


def purlin_positions(sp: dict) -> list[Fraction]:
    """Distinct plan positions (real mm from axis A) of the purlin lines, ascending."""
    n, half, nhip = sp["n"], sp["half"], Fraction(int(sp["nhip"]))
    ys = [half * k / n for k in range(n + 1)]
    if sp["so_mai"] == 2:
        ys += [nhip - y for y in ys[:-1]]
    return sorted(ys)


def labels_fit(sp: dict, s: int) -> str:
    """Reason when, at scale 1:s, a purlin spacing label (read along the dimension line) does not fit between its ticks; else ''."""
    P = sp["params"]
    need = est_width(spacing_label(sp), cap_to_em(P["cao_chu_kich_thuoc"])) + LABEL_CLEAR
    have = float(sp["proj_spacing"]) / s
    return "" if have >= need else f"nhãn khoảng cách xà gồ '{spacing_label(sp)}' dài {need - LABEL_CLEAR:.1f} mm không vừa khoảng {have:.1f} mm giữa hai xà gồ trên giấy"


def layout(sp: dict, s: int):
    """All primitives for scale 1:s with axis 1 / axis A at paper (0, 0). Returns (prims, dims, meta)."""
    P, sec = sp["params"], sp["section"]
    b, h, N = sec["b"], sec["h"], sp["so_truc_doc"]
    nhip, dai, buoc, n = sp["nhip"], sp["dai_nha"], sp["buoc_cot"], sp["n"]
    X = lambda v: float(v) / s
    ov, gp, dia = P["truc_vuon_qua"], P["khe_vong_truc"], P["duong_kinh_vong_truc"]
    rb, hb = dia / 2, P["cao_chu_vong_truc"]
    exo, exe = P["kt_exo"], P["kt_exe"]
    hx, hy = X(b / 2), X(h / 2)
    xs = [X(i * buoc) for i in range(N)]
    ys = [0.0, X(nhip)]
    prims, dims = [], []
    add = prims.append
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            add(Rect(layer=LAYER_COLUMN, tag="column", p0=(x - hx, y - hy), p1=(x + hx, y + hy)))
            if i == 0 and j == 0:
                add(Text(layer=LAYER_TEXT, tag="col_label", s=sec["text"], pos=(x + hx + 2.0, y + 1.2), h=P["cao_chu_nhan"]))
    y_bot, y_top = ys[0] - hy - ov, ys[1] + hy + ov
    for i, x in enumerate(xs):
        add(Line(layer=LAYER_AXIS, tag="axis_v", p1=(x, y_bot), p2=(x, y_top)))
        cy = y_top + gp + rb
        add(Circle(layer=LAYER_BUBBLE, tag="bubble", c=(x, cy), r=rb))
        add(Text(layer=LAYER_BUBBLE, tag="bubble_text", s=str(i + 1), pos=(x, cy - hb / 2), h=hb, halign="center"))
    x_left, x_right = xs[0] - hx - ov, xs[-1] + hx + ov
    for j, y in enumerate(ys):
        add(Line(layer=LAYER_AXIS, tag="axis_h", p1=(x_left, y), p2=(x_right, y)))
        cx = x_left - gp - rb
        add(Circle(layer=LAYER_BUBBLE, tag="bubble", c=(cx, y), r=rb))
        add(Text(layer=LAYER_BUBBLE, tag="bubble_text", s=string.ascii_uppercase[j], pos=(cx, y - hb / 2), h=hb, halign="center"))
    # ---- purlins: one line per distinct plan position, along the whole building length (axis 1 .. axis N)
    for y in purlin_positions(sp):
        add(Line(layer=LAYER_PURLIN, tag="purlin", p1=(xs[0], X(y)), p2=(xs[-1], X(y))))
    if sp["so_mai"] == 2:
        add(Text(layer=LAYER_TEXT, tag="ridge_label", s=RIDGE_LABEL, pos=(xs[-1] - 3.0, X(sp["half"]) + 1.2), h=P["cao_chu_ghi_chu"], halign="right"))
    # ---- dimensions: bottom chain + overall (as type B)
    chain_y = y_bot - P["kt_dau_tien"]
    overall_y = chain_y - P["kt_giua_cac_duong"]
    if N == 2:
        dims.append(Dim(kind="h", p1=(xs[0], y_bot), p2=(xs[1], y_bot), line_pos=chain_y, value=dai, ext_from=y_bot, layer=LAYER_DIM, role="single"))
        dim_bottom = chain_y - exe
    else:
        for i in range(N - 1):
            dims.append(Dim(kind="h", p1=(xs[i], y_bot), p2=(xs[i + 1], y_bot), line_pos=chain_y, value=buoc, ext_from=y_bot, layer=LAYER_DIM, role="chain"))
        dims.append(Dim(kind="h", p1=(xs[0], y_bot), p2=(xs[-1], y_bot), line_pos=overall_y, value=dai, ext_from=chain_y - exe + exo, layer=LAYER_DIM, role="overall"))
        dim_bottom = overall_y - exe
    # ---- right: purlin spacing chain (roof 1 from its eave axis; 2 roofs: the other roof mirrors it), then the span
    chain_x = x_right + P["kt_dau_tien"]
    span_x = chain_x + P["kt_giua_cac_duong"]
    label = spacing_label(sp)
    for k in range(n):
        y0, y1 = sp["half"] * k / n, sp["half"] * (k + 1) / n
        dims.append(Dim(kind="v", p1=(x_right, X(y0)), p2=(x_right, X(y1)), line_pos=chain_x, value=float(sp["proj_spacing"]), ext_from=x_right, layer=LAYER_DIM, role="chain", text=label,
                        ext_lines=False))
    for k in range(n + 1):             # one extension line per purlin (adjacent segments share it, so it is drawn once)
        add(Line(layer=LAYER_DIM, tag="dim_chain_ext", p1=(x_right + exo, X(sp["half"] * k / n)), p2=(chain_x + exe, X(sp["half"] * k / n))))
    dims.append(Dim(kind="v", p1=(x_right, ys[0]), p2=(x_right, ys[1]), line_pos=span_x, value=nhip, ext_from=chain_x, layer=LAYER_DIM, role="overall", ext_lines=False))
    top_from = chain_x + exe if sp["so_mai"] == 1 else x_right + exo      # 2 roofs: the chain stops at the ridge, so the extension line of axis B starts at the plan
    for y, x_from in ((ys[0], chain_x + exe), (ys[1], top_from)):
        add(Line(layer=LAYER_DIM, tag="dim_ext_custom", p1=(x_from, y), p2=(span_x + exe, y)))
    # ---- title, scale note, purlin / column notes
    xc = (xs[0] + xs[-1]) / 2
    cap_t, cap_n = P["cao_chu_tieu_de"], P["cao_chu_ghi_chu"]
    t_base = dim_bottom - P["khoang_tieu_de"] - cap_t
    add(Text(layer=LAYER_TEXT, tag="title", s=VIEW_TITLE, pos=(xc, t_base), h=cap_t, halign="center", bold=True))
    n_base = t_base - P["khoang_ghi_chu"] - cap_n * ARIAL_CAP
    add(Text(layer=LAYER_TEXT, tag="scale_note", s=f"TỶ LỆ 1:{s}", pos=(xc, n_base), h=cap_n, halign="center"))
    for tag, txt in note_lines(sp):
        n_base -= 2.0 + cap_n
        add(Text(layer=LAYER_TEXT, tag=tag, s=txt, pos=(xc, n_base), h=cap_n, halign="center"))
    meta = dict(scale=s, xs=xs, ys=ys, x_right=x_right, chain_x=chain_x, span_x=span_x, title_base=t_base, note_base=n_base)
    return prims, dims, meta


def _extent(prims, dims, P):
    allp = list(prims)
    for d in dims:
        allp.extend(expand_dim(d, P))
    return drawing_extent(allp)


def build(sp: dict, profile: dict) -> Drawing:
    missing = [nm for nm in NEEDED_LAYERS if nm not in profile]
    if missing:
        raise SpecError([f"profile.yaml thiếu layer chuẩn cần dùng: {', '.join(missing)}."])
    P = sp["params"]
    gap = P["khe_vung_ve"]
    tried, chosen = [], None
    only_sheet = None if sp["kho_giay"] == "auto" else sp["kho_giay"]
    cache: dict = {}
    for sh, sc in sheet_scale_candidates(sp["scale"], only_sheet, limit=SHEET_SCALE_LIMIT):
        bad = labels_fit(sp, sc)
        if bad:
            if sh == "A3":
                tried.append(f"1:{sc} bị loại: {bad}")
            continue
        if sc not in cache:
            prims, dims, meta = layout(sp, sc)
            cache[sc] = (prims, dims, meta, _extent(prims, dims, P))
        prims, dims, meta, bb = cache[sc]
        t = place_rects([bb], gap, SHEETS[sh])
        w, hh = bb[2] - bb[0] + 2 * gap, bb[3] - bb[1] + 2 * gap
        if t is None:
            if sc == (sp["scale"] or SHEET_SCALE_LIMIT) or (not sp["scale"] and sc == 500):
                tried.append(f"{sh} ở 1:{sc} cần {w:.0f}×{hh:.0f} mm (khung {SHEETS[sh].frame_w:g}×{SHEETS[sh].frame_h:g} trừ góc khung tên 180×65)")
            continue
        chosen = (sh, sc, prims, dims, meta, bb, t, w, hh)
        break
    if chosen is None:
        raise SpecError(["Không vừa vùng vẽ của khổ giấy nào đã thử: " + "; ".join(tried) + ". Không tự xoay hình."])
    sheet_name, s, prims, dims, meta, bb, (tx, ty), w, hh = chosen
    sheet = SHEETS[sheet_name]
    reason = (f"khổ {sheet_name}, tỷ lệ 1:{s} " + ("do người dùng chọn" if sp["scale"] else "là tỷ lệ lớn nhất còn vừa") +
              f"; hình cần {w:.0f}×{hh:.0f} mm gồm chuỗi kích thước xà gồ, ký hiệu trục, tên hình, ghi chú, nằm trong vùng vẽ (khung {sheet.frame_w:g}×{sheet.frame_h:g} trừ góc khung tên 180×65)." +
              ("" if sp["scale"] else f" Quy tắc: ưu tiên A3, chỉ dùng A2 rồi A1 khi khổ nhỏ hơn không vừa ở tỷ lệ ≤ 1:{SHEET_SCALE_LIMIT}") +
              (f"; không khổ nào vừa ở tỷ lệ ≤ 1:{SHEET_SCALE_LIMIT} nên dùng 1:{s}" if (s > SHEET_SCALE_LIMIT and not sp["scale"]) else "") +
              (f"; không vừa: {'; '.join(tried)}" if tried else ""))
    D = Drawing(name=sp["ten"], scale=s, origin=(tx, ty), kind="D", sheet=sheet_name)      # axis 1 / axis A on the sheet = (tx, ty)
    D.prims.extend(_moved(p, tx, ty) for p in prims)
    for d in dims:
        D.add_dim(_moved_dim(d, tx, ty), P)
    kt = dict(sp["khung_ten"])
    if not kt.get("ky_hieu_ban_ve"):
        kt["ky_hieu_ban_ve"] = DEFAULT_SHEET_NO
    if not kt.get("ten_ban_ve"):
        kt["ten_ban_ve"] = VIEW_TITLE
    D.fields = TBK.fields_from_meta(kt, f"1:{s}")
    D.prims.extend(TBK.primitives(D.fields, sheet))
    meta.update(origin=(tx, ty))
    D.meta = meta
    defaults = [k for k, flag in (("tiet_dien_cot", sp["cot_mac_dinh"]), ("tiet_dien_xa_go", sp["xa_go_mac_dinh"])) if flag]
    D.info = dict(scale=s, sheet=sheet_name, reason=reason, band="L", N=sp["so_truc_doc"], n_columns=2 * sp["so_truc_doc"], warnings=sp["warnings"], params=P, extents_paper=(w, hh),
                  extent_sheet=(bb[0] + tx, bb[1] + ty, bb[2] + tx, bb[3] + ty), n_spans=sp["n"], n_purlins=sp["n_purlins_total"], real_spacing=sp["real_spacing"], proj_spacing=float(sp["proj_spacing"]),
                  slope_length=sp["L"], so_mai=sp["so_mai"], defaults=defaults,
                  convention=("2 mái: đường tim nóc ở giữa nhịp; xà gồ nóc của hai mái trùng nhau trên mặt bằng (vẽ một đường); mỗi mái n + 1 xà gồ" if sp["so_mai"] == 2 else
                              "1 mái: kèo dốc từ trục A (thấp) lên trục B (cao); n + 1 xà gồ"))
    return D
