"""Drawing type C: cross-section of a steel portal frame (one view on one A3 sheet) -> primitives.

Model (real mm): axis A at x = 0, axis B at x = nhip, ground y = 0. Members are strips centred on their axes: two columns (strip width = column
section height h) and one or two rafters (strip width = rafter section height h, measured perpendicular to the rafter axis). At each node
(knees, ridge) the two members are cut along the BISECTOR of the angle between their axes; the drawn outline is the UNION of the members: edges
hidden inside the joint are not drawn. When the two depths differ, the exposed part of the cut line is drawn as a short step ("joint_step").
Column feet lie on the ground line (no separate foot edges). Drawing area / scale: one view, largest standard scale that fits (scale.place_rects).

Primitive tags: ground, col_edge (COT), raf_edge / joint_step (KEO), axis_v (TRUC), bubble / bubble_text, member_axis (NET-TAM, optional),
level_line / level_tri / level_bar / level_text, section_label, slope_text, title, scale_note, dim_* (dimension lines) and dim_ext_custom
(extension lines that start at the measured node, drawn by hand because a Dim has one start coordinate).
"""
from __future__ import annotations

import dataclasses
import math

import titleblock as TBK
from build_a import _moved, _moved_dim
from primitives import Circle, Dim, Drawing, Line, Text, cap_to_em, drawing_extent, expand_dim, fmt_dec, fmt_value
from scale import SCALES, place_rects
from spec_b import SpecError
from spec_c import level_text, percent_text, round_half_up
from tcvn import ARIAL_CAP, est_width, LAYER_AXIS, LAYER_BUBBLE, LAYER_COLUMN, LAYER_DIM, LAYER_FRAME, LAYER_TEXT, LAYER_THIN

LAYER_MAIN, LAYER_RAFTER, LAYER_LEVEL = "NET-CHINH", "KEO", "NET-TAM"
NEEDED_LAYERS = (LAYER_MAIN, LAYER_RAFTER, LAYER_LEVEL, LAYER_COLUMN, LAYER_AXIS, LAYER_BUBBLE, LAYER_DIM, LAYER_TEXT, LAYER_FRAME, LAYER_THIN)
VIEW_TITLE = "MẶT CẮT NGANG KHUNG"
LEVEL_NOTE = "CAO ĐỘ TÍNH THEO GIAO ĐIỂM TRỤC"       # printed above the top level: levels are those of the axis intersections
DEFAULT_SHEET_NO = "KC-02"       # drawing number used when khung_ten.ky_hieu_ban_ve is empty
SYMBOL_BAR, SYMBOL_TRI = 19.0, 3.0          # level symbol (paper mm), same as type A


# ---------------------------------------------------------------- geometry in real mm (analytic line intersections)
def nodes_of(sp: dict):
    H, nh, rise = sp["cao_cot"], sp["nhip"], sp["rise"]
    return [(0.0, H), (nh / 2.0, H + rise), (nh, H)] if sp["so_mai"] == 2 else [(0.0, H), (nh, H + rise)]


def _unit(vx, vy):
    n = math.hypot(vx, vy)
    return vx / n, vy / n


def _intersect(p0, d, q0, e):
    """Point where the line p0 + t d meets q0 + u e."""
    det = d[0] * (-e[1]) - d[1] * (-e[0])
    t = ((q0[0] - p0[0]) * (-e[1]) - (q0[1] - p0[1]) * (-e[0])) / det
    return p0[0] + t * d[0], p0[1] + t * d[1]


def outline(sp: dict):
    """Union outline of the frame in real mm. Returns (segments, nodes) with segments = [(tag, p, q)] (tags col_edge / raf_edge / joint_step)."""
    nodes = nodes_of(sp)
    hc, hr, nh = sp["col"]["h"], sp["raf"]["h"], sp["nhip"]
    pts = [(0.0, 0.0)] + nodes + [(nh, 0.0)]
    members = []
    for k in range(len(pts) - 1):
        a, b = pts[k], pts[k + 1]
        d = _unit(b[0] - a[0], b[1] - a[1])
        kind = "col" if k in (0, len(pts) - 2) else "raf"
        members.append(dict(kind=kind, a=a, b=b, d=d, nl=(-d[1], d[0]), hw=(hc if kind == "col" else hr) / 2.0))
    cuts = []
    for k, n in enumerate(nodes):
        m1, m2 = members[k], members[k + 1]
        u1, u2 = (-m1["d"][0], -m1["d"][1]), m2["d"]
        cuts.append((n, _unit(u1[0] + u2[0], u1[1] + u2[1])))
    segs = []
    ends = {}            # (member, side) -> (start point, end point)
    for k, m in enumerate(members):
        for side, sg in (("out", 1.0), ("in", -1.0)):
            p0 = (m["a"][0] + sg * m["nl"][0] * m["hw"], m["a"][1] + sg * m["nl"][1] * m["hw"])        # a point on the edge line
            start = p0 if k == 0 else _intersect(p0, m["d"], *cuts[k - 1])
            end = p0 if k == len(members) - 1 else _intersect(p0, m["d"], *cuts[k])
            if k == len(members) - 1:                    # foot of the last column: point on the ground
                end = (m["b"][0] + sg * m["nl"][0] * m["hw"], 0.0)
            if k == 0:
                start = (m["a"][0] + sg * m["nl"][0] * m["hw"], 0.0)
            ends[(k, side)] = (start, end)
            segs.append(("col_edge" if m["kind"] == "col" else "raf_edge", start, end))
    for k in range(len(nodes)):
        for side in ("out", "in"):
            p, q = ends[(k, side)][1], ends[(k + 1, side)][0]
            if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-9:
                segs.append(("joint_step", p, q))
    return segs, nodes


def _fmt_deg(v):
    return fmt_dec(v, 1)


def layout(sp: dict, s: int):
    """All primitives for scale 1:s, axis A at ground at paper (0, 0). Returns (prims, dims, meta)."""
    P = sp["params"]
    X = lambda v: v / s
    hc, hr, nh, H = sp["col"]["h"], sp["raf"]["h"], sp["nhip"], sp["cao_cot"]
    th = math.atan(sp["i"])
    segs, nodes = outline(sp)
    ov, gp, dia = P["truc_vuon_qua"], P["khe_vong_truc"], P["duong_kinh_vong_truc"]
    rb, hb = dia / 2.0, P["cao_chu_vong_truc"]
    g = P["nen_keo_dai"]
    exo, exe = P["kt_exo"], P["kt_exe"]
    prims, dims = [], []
    add = prims.append
    layer_of = {"col_edge": LAYER_COLUMN, "raf_edge": LAYER_RAFTER, "joint_step": LAYER_RAFTER}
    for tag, p, q in segs:
        add(Line(layer=layer_of[tag], tag=tag, p1=(X(p[0]), X(p[1])), p2=(X(q[0]), X(q[1]))))
    # ground line (thick, longer than the frame)
    gx0, gx1 = X(-hc / 2.0) - g, X(nh + hc / 2.0) + g
    add(Line(layer=LAYER_MAIN, tag="ground", p1=(gx0, 0.0), p2=(gx1, 0.0)))
    ymax = max(max(p[1], q[1]) for _, p, q in segs)
    y_ax_top = X(ymax) + ov
    # axes A, B + bubbles at the top
    for xr, letter in ((0.0, "A"), (nh, "B")):
        add(Line(layer=LAYER_AXIS, tag="axis_v", p1=(X(xr), -ov), p2=(X(xr), y_ax_top)))
        cy = y_ax_top + gp + rb
        add(Circle(layer=LAYER_BUBBLE, tag="bubble", c=(X(xr), cy), r=rb))
        add(Text(layer=LAYER_BUBBLE, tag="bubble_text", s=letter, pos=(X(xr), cy - hb / 2.0), h=hb, halign="center"))
    if sp["ve_truc"]:
        for a, b in zip(nodes, nodes[1:]):
            add(Line(layer=LAYER_LEVEL, tag="member_axis", p1=(X(a[0]), X(a[1])), p2=(X(b[0]), X(b[1]))))
    # ---- dimensions: span (bottom), vertical chain + overall (left)
    chain_y = -(ov + P["kt_dau_tien"])
    dims.append(Dim(kind="h", p1=(0.0, 0.0), p2=(X(nh), 0.0), line_pos=chain_y, value=nh, ext_from=-ov, layer=LAYER_DIM, role="single", text=fmt_value(nh)))
    lx1 = gx0
    lx2 = lx1 - P["kt_giua_cac_duong"]
    y_cot, y_top = X(H), X(sp["y_top"])
    sin_t = math.sin(th)
    d_exit = hr / (2.0 * sin_t)          # distance from the top node along x to where y = y_top leaves the rafter's upper edge (may exceed the member for shallow slopes)
    x_node_top = nodes[1][0] if sp["so_mai"] == 2 else nodes[-1][0]
    x_top_start = X(max(x_node_top - d_exit, -hc / 2.0))          # clamped to the outer face of column A
    dims.append(Dim(kind="v", p1=(lx1, 0.0), p2=(lx1, y_cot), line_pos=lx1, value=H, ext_from=lx1, layer=LAYER_DIM, role="chain", ext_lines=False, text=fmt_value(H)))
    dims.append(Dim(kind="v", p1=(lx1, y_cot), p2=(lx1, y_top), line_pos=lx1, value=sp["rise"], ext_from=lx1, layer=LAYER_DIM, role="chain", ext_lines=False,
                    text=str(round_half_up(sp["rise_exact"]))))
    dims.append(Dim(kind="v", p1=(lx2, 0.0), p2=(lx2, y_top), line_pos=lx2, value=sp["y_top"], ext_from=lx2, layer=LAYER_DIM, role="overall", ext_lines=False,
                    text=str(round_half_up(sp["y_top_exact"]))))
    for y, x_from, x_to in ((0.0, lx1 - exo, lx2 - exe), (y_cot, X(-hc / 2.0) - exo, lx1 - exe), (y_top, x_top_start - exo, lx2 - exe)):
        add(Line(layer=LAYER_DIM, tag="dim_ext_custom", p1=(x_from, y), p2=(x_to, y)))
    # ---- level markers on the right (datum lines from the structure to the symbol)
    x_m = X(nh + hc / 2.0) + g - 4.0
    x_col_out = X(nh + hc / 2.0)
    x_top_line = X(min(nodes[1][0] + d_exit, nh + hc / 2.0)) if sp["so_mai"] == 2 else x_col_out
    stack_h = SYMBOL_TRI + 0.8 + hb + 1.0                       # vertical room one level symbol + text needs
    stagger = (y_top - y_cot) < stack_h                          # rise too small on paper: put the top symbol further right instead of on top of the eave one
    for y, label, x0, xm in ((0.0, "+0.000", None, x_m), (y_cot, level_text(H), x_col_out, x_m),
                             (y_top, level_text(sp["y_top_exact"]), x_top_line, x_m + (SYMBOL_BAR + 3.0 if stagger else 0.0))):
        if x0 is not None:
            add(Line(layer=LAYER_LEVEL, tag="level_line", p1=(x0, y), p2=(xm, y)))
        add(Line(layer=LAYER_TEXT, tag="level_tri", p1=(xm, y), p2=(xm - 1.5, y + SYMBOL_TRI)))
        add(Line(layer=LAYER_TEXT, tag="level_tri", p1=(xm, y), p2=(xm + 1.5, y + SYMBOL_TRI)))
        add(Line(layer=LAYER_TEXT, tag="level_bar", p1=(xm - 1.5, y + SYMBOL_TRI), p2=(xm - 1.5 + SYMBOL_BAR, y + SYMBOL_TRI)))
        add(Text(layer=LAYER_TEXT, tag="level_text", s=label, pos=(xm - 1.0, y + SYMBOL_TRI + 0.8), h=hb))
    cap, kn = P["cao_chu_so_lieu"], P["khoang_cach_nhan"]
    xm_top = x_m + (SYMBOL_BAR + 3.0 if stagger else 0.0)
    add(Text(layer=LAYER_TEXT, tag="level_note", s=LEVEL_NOTE, pos=(xm_top - 1.0, y_top + SYMBOL_TRI + 0.8 + hb + 1.5), h=cap))
    # ---- section labels and slope texts
    add(Text(layer=LAYER_TEXT, tag="section_label", s=sp["col"]["text"], pos=(X(hc / 2.0) + kn, X(H) / 2.0), h=cap))
    add(Text(layer=LAYER_TEXT, tag="section_label", s=sp["col"]["text"], pos=(X(nh - hc / 2.0) - kn, X(H) / 2.0), h=cap, halign="right"))
    slope_txt = f"i = {percent_text(sp['do_doc_mai'])}% ({_fmt_deg(sp['theta_deg'])}°)"
    def clear_of_datum(px, py, w_txt, ang):
        """True when the text box (centre-anchored baseline at (px, py), rotated by ang) keeps 0.6 mm from the horizontal datum line at y_top."""
        half = w_txt / 2.0 * abs(math.sin(ang))
        lo, hi = py - half - 0.3 * cap, py + half + 1.2 * cap * math.cos(ang) + 0.3 * cap
        return not (lo - 0.6 <= y_top <= hi + 0.6)

    for a, b in zip(nodes, nodes[1:]):
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        nl = (-math.sin(ang), math.cos(ang))
        hw = X(hr) / 2.0
        deg = math.degrees(ang)
        w_lab, w_slope = est_width(sp["raf"]["text"], cap_to_em(cap)), est_width(slope_txt, cap_to_em(cap))

        def spot(t, off, w_txt):
            px, py = X(a[0] + (b[0] - a[0]) * t), X(a[1] + (b[1] - a[1]) * t)
            return px + nl[0] * off, py + nl[1] * off

        # section label above the rafter (slid along it, away from the top datum line); when no spot is clear (shallow roofs) both texts go below the rafter
        lab_pos = None
        for t in (0.5, 0.6, 0.4, 0.7, 0.3, 0.8, 0.2):
            cand = spot(t, hw + kn, w_lab)
            if clear_of_datum(cand[0], cand[1], w_lab, ang):
                lab_pos = cand
                break
        below1, below2 = -(hw + kn + cap), -(hw + kn + 2 * cap + 1.5)
        if lab_pos is None:
            lab_pos = spot(0.5, below1, w_lab)
            slope_off = below2
        else:
            slope_off = below1
        add(Text(layer=LAYER_TEXT, tag="section_label", s=sp["raf"]["text"], pos=lab_pos, h=cap, rot=deg, halign="center"))
        add(Text(layer=LAYER_TEXT, tag="slope_text", s=slope_txt, pos=spot(0.5, slope_off, w_slope), h=cap, rot=deg, halign="center"))
    # ---- title + scale below the span dimension
    cap_t, cap_n = P["cao_chu_tieu_de"], P["cao_chu_ghi_chu"]
    xc = X(nh) / 2.0
    t_base = chain_y - exe - P["khoang_tieu_de"] - cap_t
    add(Text(layer=LAYER_TEXT, tag="title", s=VIEW_TITLE, pos=(xc, t_base), h=cap_t, halign="center", bold=True))
    add(Text(layer=LAYER_TEXT, tag="scale_note", s=f"TỶ LỆ 1:{s}", pos=(xc, t_base - P["khoang_ghi_chu"] - cap_n), h=cap_n, halign="center"))
    meta = dict(nodes=nodes, theta_deg=sp["theta_deg"], y_top=sp["y_top"], rise=sp["rise"], scale=s, slope_text=slope_txt, n_segments=len(segs),
                ground=(gx0, gx1), dim_x=(lx1, lx2))
    return prims, dims, meta


def _extent(prims, dims, P):
    allp = list(prims)
    for d in dims:
        allp.extend(expand_dim(d, P))
    return drawing_extent(allp)


def labels_overlap(sp: dict, s: int):
    """Reason string when, at scale 1:s, the section labels / slope texts cannot fit (columns too close, rafter shorter than its texts); else ''."""
    P = sp["params"]
    cap, kn = P["cao_chu_so_lieu"], P["khoang_cach_nhan"]
    em = cap_to_em(cap)
    hc, nh = sp["col"]["h"], sp["nhip"]
    w_col = est_width(sp["col"]["text"], em)
    free = (nh - hc) / s - 2 * kn
    if free < 2 * w_col + 2.0:
        return f"hai nhãn cột ({w_col:.0f} mm mỗi nhãn) không vừa khoảng trống giữa hai cột ({free:.0f} mm trên giấy)"
    slope_txt = f"i = {percent_text(sp['do_doc_mai'])}% ({_fmt_deg(sp['theta_deg'])}°)"
    need = max(est_width(sp["raf"]["text"], em), est_width(slope_txt, em)) + 4.0
    if sp["raf_len"] / s < need:
        return f"chiều dài kèo trên giấy {sp['raf_len'] / s:.0f} mm ngắn hơn nhãn kèo/độ dốc ({need:.0f} mm)"
    return ""


def build(sp: dict, profile: dict) -> Drawing:
    missing = [n for n in NEEDED_LAYERS if n not in profile]
    if missing:
        raise SpecError([f"profile.yaml thiếu layer chuẩn cần dùng: {', '.join(missing)}."])
    P = sp["params"]
    gap = P["khe_vung_ve"]
    tried, chosen = [], None
    for s in ([sp["scale"]] if sp["scale"] else sorted(SCALES)):
        bad = labels_overlap(sp, s)
        if bad:
            tried.append(f"1:{s} bị loại: {bad}")
            continue
        prims, dims, meta = layout(sp, s)
        bb = _extent(prims, dims, P)
        t = place_rects([bb], gap)
        w, h = bb[2] - bb[0] + 2 * gap, bb[3] - bb[1] + 2 * gap
        if t is None:
            tried.append(f"1:{s} cần {w:.0f}×{h:.0f} mm")
            continue
        chosen = (s, prims, dims, meta, bb, t, w, h)
        break
    if chosen is None:
        raise SpecError(["Không vừa vùng vẽ A3 (khung 390×277 trừ góc khung tên 180×65): " + "; ".join(tried) + ". Không tự xoay hình."])
    s, prims, dims, meta, bb, (tx, ty), w, h = chosen
    reason = (f"1:{s} " + ("do người dùng chọn" if sp["scale"] else f"là tỷ lệ lớn nhất trong dãy {'/'.join(map(str, SCALES))} mà hình") +
              f" cần {w:.0f}×{h:.0f} mm gồm kích thước, ký hiệu trục, tên hình, nằm trong vùng vẽ (khung 390×277 trừ góc khung tên 180×65)" + (f"; không vừa: {'; '.join(tried)}" if tried else ""))
    D = Drawing(name=sp["ten"], scale=s, origin=(tx, ty), kind="C")      # axis A at ground on the sheet = (tx, ty)
    D.prims.extend(_moved(p, tx, ty) for p in prims)
    for d in dims:
        D.add_dim(_moved_dim(d, tx, ty), P)
    kt = dict(sp["khung_ten"])
    if not kt.get("ky_hieu_ban_ve"):
        kt["ky_hieu_ban_ve"] = DEFAULT_SHEET_NO
    if not kt.get("ten_ban_ve"):
        kt["ten_ban_ve"] = VIEW_TITLE
    D.fields = TBK.fields_from_meta(kt, f"1:{s}")
    D.prims.extend(TBK.primitives(D.fields))
    meta.update(origin=(tx, ty))
    D.meta = meta
    D.info = dict(scale=s, reason=reason, band="L", N=2, n_columns=2, warnings=sp["warnings"], params=P, extents_paper=(w, h), extent_sheet=(bb[0] + tx, bb[1] + ty, bb[2] + tx, bb[3] + ty),
                  y_top=sp["y_top"], rise=sp["rise"], theta_deg=sp["theta_deg"], rafter_length=sp["raf_len"], so_mai=sp["so_mai"],
                  convention=("2 mái: đỉnh tại giữa nhịp, cao đỉnh = cao_cot + nhip/2 × do_doc_mai/100" if sp["so_mai"] == 2 else
                              "1 mái: kèo dốc từ trục A (thấp, cao_cot) lên trục B (cao), cao đỉnh = cao_cot + nhip × do_doc_mai/100"))
    return D
