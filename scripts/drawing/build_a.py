"""Drawing type A: single-flight straight steel stair -> primitives (plan + longitudinal section 1-1 on one A3 sheet).

Geometry (real mm, run direction +x, elevation z, width y):
  n risers of height h = cao_tang / n (exact, never rounded); n-1 treads of depth b; run L = (n-1) b.
  Section (cut along the stair axis, looking toward +y): saw-tooth profile  riser i at x = (i-1)b from z = (i-1)h to i h,
  tread i at z = i h from x = (i-1)b to i b; floors at z = 0 (x <= 0) and z = H (x >= L); two box stringers (visible, behind
  the cut plane) under the nosing line z = h + (h/b) x; level lines (CENTER) at z = 0 and z = H with level symbols.
  Plan: rectangle L x w, tread edges, hidden inner stringer edges, step numbers 1..n-1, UP arrow, section mark 1-1.
Two independent blocks (section block with its title/notes, plan block with its dimensions/title) are placed on the A3 sheet in one of
two arrangements: "chong" (plan below the section, x = 0 of both views on one vertical axis) or "ngang" (plan to the right of the section,
title baselines aligned). Scales: one common scale, or - with ty_le "auto" and ty_le_rieng true - a plan at a smaller scale than the
section (plan scale >= section scale, same standard series). The DXF/DWG are written at the SECTION scale (the sheet scale), so the
section is real size in the DXF and a plan at a smaller scale is reduced by section_scale/plan_scale there (dimension texts keep the real values).
The layout and scales are chosen by solve(): the best (plan scale, section scale), then common scale, then "chong".
"""
from __future__ import annotations

import dataclasses
import math

import titleblock as TBK
from primitives import Circle, Dim, Drawing, Line, Rect, Text, cap_to_em, drawing_extent, expand_dim, fmt_dec, fmt_value
from scale import SCALES, ScaleReject, place_rects
from spec_b import SpecError
from tcvn import LAYER_DIM, LAYER_FRAME, LAYER_TEXT, LAYER_THIN, est_width

# The profile has no stair/beam layer; KEO is "rafters / roof trusses". The stringers are visible steel outlines -> NET-CHINH ("Nét cơ bản (thấy) - đậm", 0.5 mm).
LAYER_MAIN, LAYER_STRINGER, LAYER_LEVEL, LAYER_HIDDEN = "NET-CHINH", "NET-CHINH", "NET-TAM", "NET-KHUAT"
NEEDED_LAYERS = (LAYER_MAIN, LAYER_STRINGER, LAYER_LEVEL, LAYER_HIDDEN, LAYER_THIN, LAYER_DIM, LAYER_TEXT, LAYER_FRAME)
VIEW_TITLE_PLAN, VIEW_TITLE_SECTION = "MẶT BẰNG THANG", "MẶT CẮT 1-1"
DEFAULT_TITLE = "MẶT BẰNG VÀ MẶT CẮT CẦU THANG"
DEFAULT_SHEET_NO = "KC-03"       # drawing number used when khung_ten.ky_hieu_ban_ve is empty
EXT = 4.0              # level lines run this far (paper mm) past the floor stubs
SYMBOL_BAR, SYMBOL_TRI = 19.0, 3.0       # level symbol: bar length and triangle height (paper mm)


def _moved(p, dx, dy):
    if isinstance(p, Line):
        return dataclasses.replace(p, p1=(p.p1[0] + dx, p.p1[1] + dy), p2=(p.p2[0] + dx, p.p2[1] + dy))
    if isinstance(p, Rect):
        return dataclasses.replace(p, p0=(p.p0[0] + dx, p.p0[1] + dy), p1=(p.p1[0] + dx, p.p1[1] + dy))
    if isinstance(p, Circle):
        return dataclasses.replace(p, c=(p.c[0] + dx, p.c[1] + dy))
    return dataclasses.replace(p, pos=(p.pos[0] + dx, p.pos[1] + dy))


def _moved_dim(d: Dim, dx, dy):
    if d.kind == "h":
        return dataclasses.replace(d, p1=(d.p1[0] + dx, d.p1[1] + dy), p2=(d.p2[0] + dx, d.p2[1] + dy), line_pos=d.line_pos + dy, ext_from=d.ext_from + dy)
    return dataclasses.replace(d, p1=(d.p1[0] + dx, d.p1[1] + dy), p2=(d.p2[0] + dx, d.p2[1] + dy), line_pos=d.line_pos + dx, ext_from=d.ext_from + dx)


def _is_int(v):
    return abs(v - round(v)) < 1e-9


def _num_g(v):
    return f"{v:g}".replace(".", ",")


def height_note(n: int, H: float, h: float) -> str:
    """Note for the riser height. Integer h: 'n x h = H' (true arithmetic). Non-integer h: no multiplication of a rounded value -
    'n BẬC: h = H/n ≈ h(1 decimal) MM' (the approximation sign is explicit)."""
    if _is_int(h):
        return f"{n} x {fmt_value(h)} = {fmt_value(H)}"
    return f"{n} BẬC: h = {fmt_value(H)}/{n} ≈ {fmt_dec(h, 1)} MM"


def section_block(sp: dict, s: int):
    """Section 1-1 with level lines, dimensions, slope text, title, scale and notes; origin = lower floor edge at paper (0, 0).
    Returns (prims, dims, meta)."""
    P = sp["params"]
    H, n, b, t = sp["cao_tang"], sp["so_bac"], sp["b"], sp["t"]
    h, L, ds = sp["h"], sp["L"], sp["dam_con"]
    X = lambda v: v / s
    stub = P["doan_san"]
    ov = []
    add = ov.append
    dims: list[Dim] = []
    theta = math.atan2(h, b)
    o = ds["bd"] / math.cos(theta)           # vertical offset of the stringer's lower edge below the nosing line (real mm)
    if H - o < 0:
        raise SpecError([f"dam_con cao {ds['bd']:g} mm quá lớn so với cao_tang = {H:g} mm (mép dưới dầm cốn ở đầu trên thấp hơn sàn dưới)."])
    add(Line(layer=LAYER_MAIN, tag="floor_lower", p1=(-stub, 0.0), p2=(0.0, 0.0)))
    add(Line(layer=LAYER_MAIN, tag="floor_upper", p1=(X(L), X(H)), p2=(X(L) + stub, X(H))))
    for i in range(1, n + 1):
        add(Line(layer=LAYER_MAIN, tag="riser", p1=(X((i - 1) * b), X((i - 1) * h)), p2=(X((i - 1) * b), X(i * h))))
    for i in range(1, n):
        add(Line(layer=LAYER_MAIN, tag="tread", p1=(X((i - 1) * b), X(i * h)), p2=(X(i * b), X(i * h))))
    # stringers (visible behind the cut plane): nosing line and parallel lower edge
    add(Line(layer=LAYER_STRINGER, tag="stringer_top", p1=(X(0.0), X(h)), p2=(X(L), X(H))))
    if h - o >= 0:
        low0 = (0.0, h - o)
    else:
        low0 = ((o - h) * b / h, 0.0)
    add(Line(layer=LAYER_STRINGER, tag="stringer_low", p1=(X(low0[0]), X(low0[1])), p2=(X(L), X(H - o))))
    if o > h and H - o < (n - 1) * h:
        add(Line(layer=LAYER_STRINGER, tag="stringer_end", p1=(X(L), X(H - o)), p2=(X(L), X((n - 1) * h))))
    # level lines (CENTER) + level symbols
    xl0, xl1 = -(stub + EXT), X(L) + stub + EXT
    hb = P["cao_chu_vong_truc"]
    for z, label in ((0.0, "+0.000"), (H, f"+{H / 1000:.3f}")):
        add(Line(layer=LAYER_LEVEL, tag="level_line", p1=(xl0, X(z)), p2=(xl1, X(z))))
        xa = xl0 - 2.0
        add(Line(layer=LAYER_TEXT, tag="level_tri", p1=(xa, X(z)), p2=(xa - 1.5, X(z) + SYMBOL_TRI)))
        add(Line(layer=LAYER_TEXT, tag="level_tri", p1=(xa, X(z)), p2=(xa + 1.5, X(z) + SYMBOL_TRI)))
        add(Line(layer=LAYER_TEXT, tag="level_bar", p1=(xa - SYMBOL_BAR + 1.5, X(z) + SYMBOL_TRI), p2=(xa + 1.5, X(z) + SYMBOL_TRI)))
        add(Text(layer=LAYER_TEXT, tag="level_text", s=label, pos=(xa - SYMBOL_BAR + 2.0, X(z) + SYMBOL_TRI + 0.8), h=hb))
    # dimensions
    h_txt = fmt_value(h) if _is_int(h) else fmt_dec(h, 1)
    b_fits = est_width(fmt_value(b), cap_to_em(P["cao_chu_kich_thuoc"])) <= X(b) - P["kt_mui_ten"] - 1.0
    exo, exe = P["kt_exo"], P["kt_exe"]
    yb = X(2 * h) + 8.0
    dims.append(Dim(kind="h", p1=(X(0.0), X(h)), p2=(X(b), X(h)), line_pos=yb, value=b, ext_from=X(2 * h), layer=LAYER_DIM, role="single", text=fmt_value(b),
                    ext_lines=False, text_side=not b_fits, view="section"))
    # hand-made extension lines: they start at the measured points (start of tread 1 on the nosing line; top of riser 2), not floating above
    add(Line(layer=LAYER_DIM, tag="dim_single_ext", p1=(X(0.0), X(h) + exo), p2=(X(0.0), yb + exe)))
    add(Line(layer=LAYER_DIM, tag="dim_single_ext", p1=(X(b), X(2 * h) + exo), p2=(X(b), yb + exe)))
    # the riser-height label goes beside the dimension line when it does not fit between the two ticks (it used to run over a tick / extension line)
    h_fits = est_width(h_txt, cap_to_em(P["cao_chu_kich_thuoc"])) <= X(h) - P["kt_mui_ten"] - 1.0
    xh = X(L) + 8.0
    dims.append(Dim(kind="v", p1=(X(L), X((n - 2) * h)), p2=(X(L), X((n - 1) * h)), line_pos=xh, value=h, ext_from=X(L), layer=LAYER_DIM, role="single", text=h_txt,
                    ext_lines=False, text_side=not h_fits, view="section"))
    # upper point: foot of the last riser; lower point: end of tread n-2 (the extension line runs below the stringer to the dimension line)
    add(Line(layer=LAYER_DIM, tag="dim_single_ext", p1=(X(L) + exo, X((n - 1) * h)), p2=(xh + exe, X((n - 1) * h))))
    add(Line(layer=LAYER_DIM, tag="dim_single_ext", p1=(X((n - 2) * b) + exo, X((n - 2) * h)), p2=(xh + exe, X((n - 2) * h))))
    ext_h = X(L) + stub + EXT
    dims.append(Dim(kind="v", p1=(X(L), 0.0), p2=(X(L), X(H)), line_pos=ext_h + 8.0, value=H, ext_from=ext_h, layer=LAYER_DIM, role="overall", text=fmt_value(H), view="section"))
    dims.append(Dim(kind="h", p1=(X(0.0), X(H)), p2=(X(L), X(H)), line_pos=X(H) + 10.0, value=L, ext_from=X(H), layer=LAYER_DIM, role="overall", text=fmt_value(L), view="section"))
    # slope text along the stringer
    mx, mz = X(L) / 2, (X(h) + X(H)) / 2
    th_deg = math.degrees(theta)
    nx, nz = -math.sin(theta), math.cos(theta)
    add(Text(layer=LAYER_TEXT, tag="angle_text", s=f"GÓC DỐC {fmt_dec(th_deg, 1)}°", pos=(mx + nx * 3.0, mz + nz * 3.0), h=P["cao_chu_ghi_chu"], rot=th_deg, halign="center"))
    # title, scale and notes below the section
    xc = X(L) / 2
    cap_t, cap_n = P["cao_chu_tieu_de"], P["cao_chu_ghi_chu"]
    y_title = -(P["khoang_tieu_de"] + cap_t)
    add(Text(layer=LAYER_TEXT, tag="title_section", s=VIEW_TITLE_SECTION, pos=(xc, y_title), h=cap_t, halign="center", bold=True))
    y_note = y_title - P["khoang_ghi_chu"] - cap_n
    add(Text(layer=LAYER_TEXT, tag="scale_note", s=f"TỶ LỆ 1:{s}", pos=(xc, y_note), h=cap_n, halign="center"))
    notes = [f"THÉP TẤM DÀY {_num_g(t)} MM", height_note(n, H, h), f"{n - 1} x {fmt_value(b)} = {fmt_value(L)}"]
    y = y_note - 2.0
    for txt in notes:
        y -= 4.5
        add(Text(layer=LAYER_TEXT, tag="note", s=txt, pos=(xc, y), h=cap_n, halign="center"))
    meta = dict(notes=notes, h_text=h_txt, angle_text=f"GÓC DỐC {fmt_dec(th_deg, 1)}°", stringer_offset=o, scale=s, title_y=y_title)
    return ov, dims, meta


def plan_block(sp: dict, s: int):
    """Plan with tread lines, step numbers, UP arrow, section mark 1-1, dimensions, title and scale; origin = lower-left corner of the
    plan rectangle at paper (0, 0) (x = 0 is the stair's first riser). Raises ScaleReject when the step numbers would overlap."""
    P = sp["params"]
    n, b, w = sp["so_bac"], sp["b"], sp["w"]
    L, ds = sp["L"], sp["dam_con"]
    X = lambda v: v / s
    ov = []
    add = ov.append
    dims: list[Dim] = []
    hb = P["cao_chu_vong_truc"]
    cap_t, cap_n = P["cao_chu_tieu_de"], P["cao_chu_ghi_chu"]
    wk = X(w)
    ytop = wk
    add(Rect(layer=LAYER_MAIN, tag="plan_outline", p0=(0.0, 0.0), p1=(X(L), ytop)))
    for yy in (X(ds["bw"]), ytop - X(ds["bw"])):
        add(Line(layer=LAYER_HIDDEN, tag="plan_stringer", p1=(0.0, yy), p2=(X(L), yy)))
    for i in range(1, n - 1):
        add(Line(layer=LAYER_THIN, tag="plan_tread_line", p1=(X(i * b), 0.0), p2=(X(i * b), ytop)))
    hn = P["cao_chu_so_bac"]
    if X(b) < est_width(str(n - 1), cap_to_em(hn)) + 0.8:
        raise ScaleReject(f"số bậc chồng lên nhau (bước bậc {X(b):.1f} mm trên giấy < chữ số)")
    for i in range(1, n):
        add(Text(layer=LAYER_TEXT, tag="step_no", s=str(i), pos=(X((i - 0.5) * b), wk * 0.58), h=hn, halign="center"))
    ya = wk * 0.25
    xa0, xa1 = X(0.5 * b), X(L) - X(0.5 * b)
    add(Line(layer=LAYER_THIN, tag="plan_arrow", p1=(xa0, ya), p2=(xa1, ya)))
    add(Line(layer=LAYER_THIN, tag="plan_arrow", p1=(xa1, ya), p2=(xa1 - 3.0, ya + 1.0)))
    add(Line(layer=LAYER_THIN, tag="plan_arrow", p1=(xa1, ya), p2=(xa1 - 3.0, ya - 1.0)))
    # "LÊN" sits outside the plan, left of the arrow tail, so it never overlaps the step numbers or the arrow
    add(Text(layer=LAYER_TEXT, tag="up_text", s="LÊN", pos=(-2.0, ya - 0.9), h=hn, halign="right"))
    # section mark 1-1 across the plan axis
    yc = wk / 2
    for xs, xe in ((-12.0, -4.0), (X(L) + 14.0, X(L) + 22.0)):
        add(Line(layer=LAYER_MAIN, tag="cut_stroke", p1=(xs, yc), p2=(xe, yc)))
        xs_stem = xs if xs < 0 else xe
        add(Line(layer=LAYER_MAIN, tag="cut_arrow", p1=(xs_stem, yc), p2=(xs_stem, yc + 5.0)))
        add(Line(layer=LAYER_MAIN, tag="cut_arrow", p1=(xs_stem, yc + 5.0), p2=(xs_stem - 1.0, yc + 2.5)))
        add(Line(layer=LAYER_MAIN, tag="cut_arrow", p1=(xs_stem, yc + 5.0), p2=(xs_stem + 1.0, yc + 2.5)))
        add(Text(layer=LAYER_TEXT, tag="cut_label", s="1", pos=(xs_stem, yc + 6.0), h=hb, halign="center"))
    # plan dimensions
    chain_y = -P["kt_dau_tien"]
    overall_y = chain_y - P["kt_giua_cac_duong"]
    collapsed = X(b) < est_width(fmt_value(b), cap_to_em(P["cao_chu_kich_thuoc"])) + 1.5
    if collapsed:
        dims.append(Dim(kind="h", p1=(0.0, 0.0), p2=(X(L), 0.0), line_pos=chain_y, value=L, ext_from=0.0, layer=LAYER_DIM, role="single",
                        text=f"{n - 1} x {fmt_value(b)} = {fmt_value(L)}", view="plan"))
        dim_bottom = chain_y - P["kt_exe"]
    else:
        for i in range(n - 1):
            dims.append(Dim(kind="h", p1=(X(i * b), 0.0), p2=(X((i + 1) * b), 0.0), line_pos=chain_y, value=b, ext_from=0.0, layer=LAYER_DIM, role="chain",
                            text=fmt_value(b), view="plan"))
        dims.append(Dim(kind="h", p1=(0.0, 0.0), p2=(X(L), 0.0), line_pos=overall_y, value=L, ext_from=chain_y - P["kt_exe"] + P["kt_exo"], layer=LAYER_DIM, role="overall",
                        text=fmt_value(L), view="plan"))
        dim_bottom = overall_y - P["kt_exe"]
    dims.append(Dim(kind="v", p1=(X(L), 0.0), p2=(X(L), ytop), line_pos=X(L) + 10.0, value=w, ext_from=X(L), layer=LAYER_DIM, role="single", text=fmt_value(w), view="plan"))
    xc = X(L) / 2
    t_base = dim_bottom - P["khoang_tieu_de"] - cap_t
    add(Text(layer=LAYER_TEXT, tag="title_plan", s=VIEW_TITLE_PLAN, pos=(xc, t_base), h=cap_t, halign="center", bold=True))
    add(Text(layer=LAYER_TEXT, tag="scale_note", s=f"TỶ LỆ 1:{s}", pos=(xc, t_base - P["khoang_ghi_chu"] - cap_n), h=cap_n, halign="center"))
    meta = dict(chain_collapsed=collapsed, scale=s, title_y=t_base)
    return ov, dims, meta


def _extent(prims, dims, P):
    allp = list(prims)
    for d in dims:
        allp.extend(expand_dim(d, P))
    return drawing_extent(allp)


def _shift(r, dx, dy):
    return (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)


def compose(kind: str, sec: dict, pl: dict, gap: float):
    """Relative arrangement of the two blocks. Returns (plan offset (dx, dy), [section bbox, plan bbox], union (w, h)).
    chong: plan below the section, same x origin; ngang: plan right of the section, view-title baselines on one line."""
    sb, pb = sec["bbox"], pl["bbox"]
    if kind == "chong":
        off = (0.0, sb[1] - gap - pb[3])
    else:
        off = (sb[2] + gap - pb[0], sec["meta"]["title_y"] - pl["meta"]["title_y"])
    rects = [sb, _shift(pb, *off)]
    u = (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))
    return off, rects, (u[2] - u[0], u[3] - u[1])


KIND_NAME = {"chong": "xếp chồng (mặt bằng dưới mặt cắt)", "ngang": "xếp ngang (mặt bằng bên phải mặt cắt)"}


def solve(sp: dict):
    """Choose arrangement + scales. Candidates (kind, s_sec, s_plan): s_plan >= s_sec (plan never larger than the section), equal when the scale
    is common. Best = smallest s_plan, then smallest s_sec, then common scale, then 'chong'."""
    P = sp["params"]
    gap, gv = P["khe_vung_ve"], P["khoang_giua_hinh"]
    cache: dict = {}

    def block(which, s):
        key = (which, s)
        if key not in cache:
            try:
                prims, dims, meta = (section_block if which == "sec" else plan_block)(sp, s)
                cache[key] = dict(prims=prims, dims=dims, meta=meta, bbox=_extent(prims, dims, P))
            except ScaleReject as e:
                cache[key] = e
        return cache[key]

    kinds = [sp["bo_cuc"]] if sp["bo_cuc"] != "auto" else ["chong", "ngang"]
    if sp["scale"]:
        pairs = [(sp["scale"], sp["scale"])]
    elif sp["ty_le_rieng"]:
        pairs = [(a, b) for a in SCALES for b in SCALES if b >= a]
    else:
        pairs = [(a, a) for a in SCALES]
    order = sorted(((b, a, 0 if a == b else 1, 0 if k == "chong" else 1, k) for (a, b) in pairs for k in kinds))
    needs = {}           # (kind, s) -> needed size of the common-scale candidates (to report what did not fit)
    sizes = {}           # (kind, s_sec, s_plan) -> needed size text, every candidate
    for b_, a_, _, _, k in order:
        sec, pl = block("sec", a_), block("plan", b_)
        if isinstance(sec, ScaleReject) or isinstance(pl, ScaleReject):
            txt = "bị loại: " + str(sec if isinstance(sec, ScaleReject) else pl)
        else:
            _, _, (uw, uh) = compose(k, sec, pl, gv)
            txt = f"{uw + 2 * gap:.0f}×{uh + 2 * gap:.0f} mm"
        sizes[(k, a_, b_)] = txt
        if a_ == b_:
            needs[(k, a_)] = txt
    for s_pl, s_sec, _, _, k in order:
        sec, pl = block("sec", s_sec), block("plan", s_pl)
        if isinstance(sec, ScaleReject) or isinstance(pl, ScaleReject):
            continue
        off, rects, (uw, uh) = compose(k, sec, pl, gv)
        t = place_rects(rects, gap)
        if t is None:
            continue
        return dict(kind=k, s_sec=s_sec, s_pl=s_pl, off=off, t=t, sec=sec, plan=pl, union=(uw, uh), needs=needs, sizes=sizes, rects=rects)
    lines = [f"{KIND_NAME[k]} 1:{s}: cần {v}" for (k, s), v in sorted(needs.items(), key=lambda kv: (kv[0][0], kv[0][1]))]
    raise SpecError(["Không vừa vùng vẽ A3 (khung 390×277 trừ góc khung tên 180×65) ở bất kỳ bố cục/tỷ lệ nào: " + "; ".join(lines) + ". Không tự xoay hình."])


def _reason(res: dict, sp: dict) -> str:
    k, a, b, needs = res["kind"], res["s_sec"], res["s_pl"], res["needs"]
    uw, uh = res["union"]
    gap = sp["params"]["khe_vung_ve"]
    size = f"cần {uw + 2 * gap:.0f}×{uh + 2 * gap:.0f} mm gồm kích thước, tên hình, ghi chú, nằm trong vùng vẽ (khung 390×277 trừ góc khung tên 180×65)"
    if sp["scale"]:
        head = f"tỷ lệ chung 1:{a} do người dùng chọn; bố cục {KIND_NAME[k]}; {size}"
    elif a == b:
        head = f"tỷ lệ chung 1:{a}; bố cục {KIND_NAME[k]}; {size}"
    else:
        head = (f"mặt cắt 1:{a}, mặt bằng 1:{b} (tỷ lệ riêng từng hình); bố cục {KIND_NAME[k]}; {size}. Thứ tự chọn: tỷ lệ mặt bằng lớn nhất, "
                f"rồi tỷ lệ mặt cắt lớn nhất, ưu tiên tỷ lệ chung rồi xếp chồng")
    miss = [f"{KIND_NAME[kk].split(' (')[0]} 1:{s} cần {v}" for (kk, s), v in sorted(needs.items(), key=lambda kv: (kv[0][1], kv[0][0])) if s < b]
    if miss and not sp["scale"]:
        head += "; tỷ lệ chung lớn hơn không vừa: " + "; ".join(miss)
    finer = [a2 for a2 in SCALES if a2 < a]
    if finer and not sp["scale"]:
        a2 = max(finer)
        alt = [f"{KIND_NAME[kk].split(' (')[0]} {txt}" for (kk, aa, bb), txt in sorted(res["sizes"].items()) if aa == a2 and bb == b]
        if alt:
            head += f"; mặt cắt 1:{a2} với mặt bằng 1:{b} không vừa: " + "; ".join(alt)
    return head


def build(sp: dict, profile: dict) -> Drawing:
    missing = [n for n in NEEDED_LAYERS if n not in profile]
    if missing:
        raise SpecError([f"profile.yaml thiếu layer chuẩn cần dùng: {', '.join(missing)}."])
    P = sp["params"]
    res = solve(sp)
    s, s_pl, kind = res["s_sec"], res["s_pl"], res["kind"]
    tx, ty = res["t"]
    odx, ody = res["off"]
    D = Drawing(name=sp["ten"], scale=s, origin=(tx, ty), kind="A")        # section origin (lower floor edge) on the sheet = (tx, ty)
    D.prims.extend(_moved(p, tx, ty) for p in res["sec"]["prims"])
    for d in res["sec"]["dims"]:
        D.add_dim(_moved_dim(d, tx, ty), P)
    px, py = tx + odx, ty + ody
    D.prims.extend(_moved(p, px, py) for p in res["plan"]["prims"])
    for d in res["plan"]["dims"]:
        D.add_dim(_moved_dim(d, px, py), P)
    kt = dict(sp["khung_ten"])
    if not kt.get("ky_hieu_ban_ve"):
        kt["ky_hieu_ban_ve"] = DEFAULT_SHEET_NO
    if not kt.get("ten_ban_ve"):
        kt["ten_ban_ve"] = DEFAULT_TITLE
    scale_text = f"1:{s}" if s == s_pl else f"1:{s} / 1:{s_pl}"
    D.fields = TBK.fields_from_meta(kt, scale_text)
    D.prims.extend(TBK.primitives(D.fields))
    meta = dict(res["sec"]["meta"])
    meta.update(plan_meta=res["plan"]["meta"], chain_collapsed=res["plan"]["meta"]["chain_collapsed"], section_origin=(tx, ty), plan_origin=(px, py),
                scale_sec=s, scale_pl=s_pl, view_scales={"section": s, "plan": s_pl}, layout=kind, plan_factor=s / s_pl, scale_text=scale_text,
                n=sp["so_bac"], h=sp["h"], b=sp["b"], w=sp["w"], H=sp["cao_tang"], L=sp["L"], t=sp["t"], theta_deg=sp["theta_deg"], stringer=sp["dam_con"],
                n_treads=sp["n_treads"], two_h_b=sp["two_h_b"])
    D.meta = meta
    ux0 = min(r[0] for r in res["rects"]) + tx
    ux1 = max(r[2] for r in res["rects"]) + tx
    uy0 = min(r[1] for r in res["rects"]) + ty
    uy1 = max(r[3] for r in res["rects"]) + ty
    D.info = dict(scale=s, scale_plan=s_pl, layout=kind, reason=_reason(res, sp), band="L", N=sp["so_bac"], n_columns=sp["n_treads"], warnings=sp["warnings"], params=P, h=sp["h"],
                  extents_paper=(res["union"][0], res["union"][1]), extent_sheet=(ux0, uy0, ux1, uy1), needs={f"{k}/1:{s_}": v for (k, s_), v in res["needs"].items()})
    return D
