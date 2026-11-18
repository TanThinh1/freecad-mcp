"""Drawing type A: single-flight straight steel stair -> primitives (plan + longitudinal section 1-1 on one A3 sheet).

Geometry (real mm, run direction +x, elevation z, width y):
  n risers of height h = cao_tang / n (exact, never rounded); n-1 treads of depth b; run L = (n-1) b.
  Section (cut along the stair axis, looking toward +y): saw-tooth profile  riser i at x = (i-1)b from z = (i-1)h to i h,
  tread i at z = i h from x = (i-1)b to i b; floors at z = 0 (x <= 0) and z = H (x >= L); two box stringers (visible, behind
  the cut plane) under the nosing line z = h + (h/b) x; level lines (CENTER) at z = 0 and z = H with level symbols.
  Plan: rectangle L x w, tread edges, hidden inner stringer edges, step numbers 1..n-1, UP arrow, section mark 1-1.
Section on top, plan below, same x origin (aligned). One common scale for both views, chosen with the real extents (scale.fit_scale).
"""
from __future__ import annotations

import dataclasses
import math

import titleblock as TBK
from primitives import Circle, Dim, Drawing, Line, Rect, Text, cap_to_em, drawing_extent, expand_dim, fmt_dec, fmt_value
from scale import ScaleReject, fit_scale
from spec_b import SpecError
from tcvn import ARIAL_CAP, LAYER_DIM, LAYER_FRAME, LAYER_TEXT, LAYER_THIN, est_width

LAYER_MAIN, LAYER_STRINGER, LAYER_LEVEL, LAYER_HIDDEN = "NET-CHINH", "KEO", "NET-TAM", "NET-KHUAT"
NEEDED_LAYERS = (LAYER_MAIN, LAYER_STRINGER, LAYER_LEVEL, LAYER_HIDDEN, LAYER_THIN, LAYER_DIM, LAYER_TEXT, LAYER_FRAME)
VIEW_TITLE_PLAN, VIEW_TITLE_SECTION = "MẶT BẰNG THANG", "MẶT CẮT 1-1"
DEFAULT_TITLE = "MẶT BẰNG VÀ MẶT CẮT CẦU THANG"
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


def layout(sp: dict, s: int, profile: dict):
    """All primitives for scale 1:s with the section origin (lower floor edge, z = 0) at paper (0, 0). Returns (prims, dims, meta)."""
    P = sp["params"]
    H, n, b, w, t = sp["cao_tang"], sp["so_bac"], sp["b"], sp["w"], sp["t"]
    h, L, ds = sp["h"], sp["L"], sp["dam_con"]
    k = 1.0 / s
    X = lambda v: v * k
    stub = P["doan_san"]
    ov = []
    add = ov.append
    dims: list[Dim] = []
    theta = math.atan2(h, b)
    o = ds["bd"] / math.cos(theta)           # vertical offset of the stringer's lower edge below the nosing line (real mm)
    if H - o < 0:
        raise SpecError([f"dam_con cao {ds['bd']:g} mm quá lớn so với cao_tang = {H:g} mm (mép dưới dầm cốn ở đầu trên thấp hơn sàn dưới)."])

    # ---------------- section (origin at (0, 0))
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
    dims.append(Dim(kind="h", p1=(X(0.0), X(h)), p2=(X(b), X(h)), line_pos=X(2 * h) + 8.0, value=b, ext_from=X(2 * h), layer=LAYER_DIM, role="single", text=fmt_value(b)))
    dims.append(Dim(kind="v", p1=(X(L), X((n - 2) * h)), p2=(X(L), X((n - 1) * h)), line_pos=X(L) + 8.0, value=h, ext_from=X(L), layer=LAYER_DIM, role="single", text=h_txt))
    ext_h = X(L) + stub + EXT
    dims.append(Dim(kind="v", p1=(X(L), 0.0), p2=(X(L), X(H)), line_pos=ext_h + 8.0, value=H, ext_from=ext_h, layer=LAYER_DIM, role="overall", text=fmt_value(H)))
    dims.append(Dim(kind="h", p1=(X(0.0), X(H)), p2=(X(L), X(H)), line_pos=X(H) + 10.0, value=L, ext_from=X(H), layer=LAYER_DIM, role="overall", text=fmt_value(L)))
    # slope text along the stringer
    mx, mz = X(L) / 2, (X(h) + X(H)) / 2
    th_deg = math.degrees(theta)
    nx, nz = -math.sin(theta), math.cos(theta)
    add(Text(layer=LAYER_TEXT, tag="angle_text", s=f"GÓC DỐC {fmt_dec(th_deg, 1)}°", pos=(mx + nx * 3.0, mz + nz * 3.0), h=P["cao_chu_ghi_chu"], rot=th_deg, halign="center"))
    # titles + notes below the section
    xc = X(L) / 2
    cap_t, cap_n = P["cao_chu_tieu_de"], P["cao_chu_ghi_chu"]
    y_title = -(P["khoang_tieu_de"] + cap_t)
    add(Text(layer=LAYER_TEXT, tag="title_section", s=VIEW_TITLE_SECTION, pos=(xc, y_title), h=cap_t, halign="center", bold=True))
    y_note = y_title - P["khoang_ghi_chu"] - cap_n
    add(Text(layer=LAYER_TEXT, tag="scale_note", s=f"TỶ LỆ 1:{s}", pos=(xc, y_note), h=cap_n, halign="center"))
    notes = [f"THÉP TẤM DÀY {_num_g(t)} MM", f"{n} x {h_txt} = {fmt_value(H)}", f"{n - 1} x {fmt_value(b)} = {fmt_value(L)}"]
    y = y_note - 2.0
    for txt in notes:
        y -= 4.5
        add(Text(layer=LAYER_TEXT, tag="note", s=txt, pos=(xc, y), h=cap_n, halign="center"))
    y_sec_bottom = y - 1.0

    # ---------------- plan (origin (0, oy_p) = lower-left corner)
    wk = X(w)
    extra = max(0.0, wk / 2 + 5.0 + 4.5 - wk)
    oy_p = y_sec_bottom - 8.0 - extra - wk
    ytop = oy_p + wk
    add(Rect(layer=LAYER_MAIN, tag="plan_outline", p0=(0.0, oy_p), p1=(X(L), ytop)))
    for yy in (oy_p + X(ds["bw"]), ytop - X(ds["bw"])):
        add(Line(layer=LAYER_HIDDEN, tag="plan_stringer", p1=(0.0, yy), p2=(X(L), yy)))
    for i in range(1, n - 1):
        add(Line(layer=LAYER_THIN, tag="plan_tread_line", p1=(X(i * b), oy_p), p2=(X(i * b), ytop)))
    hn = P["cao_chu_so_bac"]
    if X(b) < est_width(str(n - 1), cap_to_em(hn)) + 0.8:
        raise ScaleReject(f"số bậc chồng lên nhau (bước bậc {X(b):.1f} mm trên giấy < chữ số)")
    for i in range(1, n):
        add(Text(layer=LAYER_TEXT, tag="step_no", s=str(i), pos=(X((i - 0.5) * b), oy_p + wk * 0.58), h=hn, halign="center"))
    ya = oy_p + wk * 0.25
    xa0, xa1 = X(0.5 * b), X(L) - X(0.5 * b)
    add(Line(layer=LAYER_THIN, tag="plan_arrow", p1=(xa0, ya), p2=(xa1, ya)))
    add(Line(layer=LAYER_THIN, tag="plan_arrow", p1=(xa1, ya), p2=(xa1 - 3.0, ya + 1.0)))
    add(Line(layer=LAYER_THIN, tag="plan_arrow", p1=(xa1, ya), p2=(xa1 - 3.0, ya - 1.0)))
    # "LÊN" sits outside the plan, left of the arrow tail, so it never overlaps the step numbers or the arrow
    add(Text(layer=LAYER_TEXT, tag="up_text", s="LÊN", pos=(-2.0, ya - 0.9), h=hn, halign="right"))
    # section mark 1-1 across the plan axis
    yc = oy_p + wk / 2
    for xs, xe in ((-12.0, -4.0), (X(L) + 14.0, X(L) + 22.0)):
        add(Line(layer=LAYER_MAIN, tag="cut_stroke", p1=(xs, yc), p2=(xe, yc)))
        xs_stem = xs if xs < 0 else xe
        add(Line(layer=LAYER_MAIN, tag="cut_arrow", p1=(xs_stem, yc), p2=(xs_stem, yc + 5.0)))
        add(Line(layer=LAYER_MAIN, tag="cut_arrow", p1=(xs_stem, yc + 5.0), p2=(xs_stem - 1.0, yc + 2.5)))
        add(Line(layer=LAYER_MAIN, tag="cut_arrow", p1=(xs_stem, yc + 5.0), p2=(xs_stem + 1.0, yc + 2.5)))
        add(Text(layer=LAYER_TEXT, tag="cut_label", s="1", pos=(xs_stem, yc + 6.0), h=hb, halign="center"))
    # plan dimensions
    chain_y = oy_p - P["kt_dau_tien"]
    overall_y = chain_y - P["kt_giua_cac_duong"]
    collapsed = X(b) < est_width(fmt_value(b), cap_to_em(P["cao_chu_kich_thuoc"])) + 1.5
    if collapsed:
        dims.append(Dim(kind="h", p1=(0.0, oy_p), p2=(X(L), oy_p), line_pos=chain_y, value=L, ext_from=oy_p, layer=LAYER_DIM, role="single",
                        text=f"{n - 1} x {fmt_value(b)} = {fmt_value(L)}"))
        dim_bottom = chain_y - P["kt_exe"]
    else:
        for i in range(n - 1):
            dims.append(Dim(kind="h", p1=(X(i * b), oy_p), p2=(X((i + 1) * b), oy_p), line_pos=chain_y, value=b, ext_from=oy_p, layer=LAYER_DIM, role="chain",
                            text=fmt_value(b)))
        dims.append(Dim(kind="h", p1=(0.0, oy_p), p2=(X(L), oy_p), line_pos=overall_y, value=L, ext_from=chain_y - P["kt_exe"] + P["kt_exo"], layer=LAYER_DIM, role="overall",
                        text=fmt_value(L)))
        dim_bottom = overall_y - P["kt_exe"]
    dims.append(Dim(kind="v", p1=(X(L), oy_p), p2=(X(L), ytop), line_pos=X(L) + 10.0, value=w, ext_from=X(L), layer=LAYER_DIM, role="single", text=fmt_value(w)))
    t_base = dim_bottom - P["khoang_tieu_de"] - cap_t
    add(Text(layer=LAYER_TEXT, tag="title_plan", s=VIEW_TITLE_PLAN, pos=(xc, t_base), h=cap_t, halign="center", bold=True))
    add(Text(layer=LAYER_TEXT, tag="scale_note", s=f"TỶ LỆ 1:{s}", pos=(xc, t_base - P["khoang_ghi_chu"] - cap_n), h=cap_n, halign="center"))
    meta = dict(section_origin=(0.0, 0.0), plan_origin=(0.0, oy_p), chain_collapsed=collapsed, notes=notes, h_text=h_txt, angle_text=f"GÓC DỐC {fmt_dec(th_deg, 1)}°",
                stringer_offset=o, scale=s)
    return ov, dims, meta


def _extent(prims, dims, P):
    allp = list(prims)
    for d in dims:
        allp.extend(expand_dim(d, P))
    return drawing_extent(allp)


def build(sp: dict, profile: dict) -> Drawing:
    missing = [n for n in NEEDED_LAYERS if n not in profile]
    if missing:
        raise SpecError([f"profile.yaml thiếu layer chuẩn cần dùng: {', '.join(missing)}."])
    P = sp["params"]
    cache: dict = {}

    def extent_at(s):
        prims, dims, meta = layout(sp, s, profile)
        x0, y0, x1, y1 = _extent(prims, dims, P)
        cache[s] = (prims, dims, meta, (x0, y0, x1, y1))
        return x1 - x0, y1 - y0

    try:
        fit = fit_scale(extent_at, gap_mm=P["khe_vung_ve"], only=sp["scale"])
    except ValueError as e:
        raise SpecError([str(e)])
    s = fit["scale"]
    prims, dims, meta, (x0, y0, x1, y1) = cache[s]
    rx0, ry0, rx1, ry1 = fit["region"]
    dx = rx0 + ((rx1 - rx0) - (x1 - x0)) / 2 - x0
    dy = ry0 + ((ry1 - ry0) - (y1 - y0)) / 2 - y0
    D = Drawing(name=sp["ten"], scale=s, origin=(dx, dy), kind="A")
    D.prims.extend(_moved(p, dx, dy) for p in prims)
    for d in dims:
        D.add_dim(_moved_dim(d, dx, dy), P)
    kt = dict(sp["khung_ten"])
    kt.setdefault("ten_ban_ve", DEFAULT_TITLE)
    if not kt.get("ten_ban_ve"):
        kt["ten_ban_ve"] = DEFAULT_TITLE
    D.fields = TBK.fields_from_meta(kt, f"1:{s}")
    D.prims.extend(TBK.primitives(D.fields))
    meta["section_origin"] = (dx, dy)
    meta["plan_origin"] = (dx, meta["plan_origin"][1] + dy)
    meta.update(n=sp["so_bac"], h=sp["h"], b=sp["b"], w=sp["w"], H=sp["cao_tang"], L=sp["L"], t=sp["t"], theta_deg=sp["theta_deg"], stringer=sp["dam_con"], n_treads=sp["n_treads"],
                two_h_b=sp["two_h_b"])
    D.meta = meta
    D.info = dict(scale=s, reason=fit["reason"], band=fit["band"], N=sp["so_bac"], n_columns=sp["n_treads"], warnings=sp["warnings"], params=P, h=sp["h"], extents_paper=(x1 - x0, y1 - y0))
    return D
