"""Verification specific to drawing type A (steel stair). Expected values are computed here FROM THE SPEC with independent formulas,
then compared with the primitives, the DXF entities and the 3D model; nothing is compared with a value derived from itself.
Tolerances: geometry in real mm 1e-6 (floating point only: h = cao_tang / so_bac is never rounded), DXF 1e-3 mm, 3D 1e-3 mm.
"""
from __future__ import annotations

import math

import re

from primitives import Circle, Line, Rect, Text, expand_dim, fmt_dec, prim_bbox
from scale import SCALES
from tcvn import SHEETS
from readers import f
from verify import Checks, check_expressions, close, greedy_match, text_min_gap

TOL = 1e-6
TOL_DXF = 1e-3


def _hl(h: float) -> str:
    """Label of the riser height: integer mm when exact, otherwise 1 decimal with a comma (explicit, geometry stays exact)."""
    return f"{round(h):d}" if abs(h - round(h)) < 1e-9 else f"{h:.1f}".replace(".", ",")


def _height_note(n: int, H: float, h: float) -> str:
    """Integer h: 'n x h = H' (exact product); otherwise the division form, never 'n x rounded h = H' (which would be a false equation)."""
    if abs(h - round(h)) < 1e-9:
        return f"{n} x {round(h):d} = {round(H):d}"
    return f"{n} BẬC: h = {round(H):d}/{n} ≈ {f'{h:.1f}'.replace('.', ',')} MM"


def expected_texts(sp: dict) -> dict:
    n, H, b, t = sp["so_bac"], sp["cao_tang"], sp["b"], sp["t"]
    h, L = H / n, (n - 1) * b
    th = math.degrees(math.atan(h / b))
    return dict(
        notes=[f"THÉP TẤM DÀY {f'{t:g}'.replace('.', ',')} MM", _height_note(n, H, h), f"{n - 1} x {round(b):d} = {round(L):d}"],
        angle=f"GÓC DỐC {f'{th:.1f}'.replace('.', ',')}°", levels=["+0.000", f"+{H / 1000:.3f}"], h_label=_hl(h), steps=[str(i) for i in range(1, n)])


def _seg_ends(p):
    return (p.p1, p.p2)


def _same_seg(a, b, tol):
    (a1, a2), (b1, b2) = a, b
    d = lambda p, q: close(p[0], q[0], tol) and close(p[1], q[1], tol)
    return (d(a1, b1) and d(a2, b2)) or (d(a1, b2) and d(a2, b1))


# ------------------------------------------------------------------ 1. primitives
def check_primitives_a(C: Checks, D, sp):
    M = D.meta
    s = D.view_scale("section")           # section scale (= sheet scale: the DXF section is real size)
    sp_ = D.view_scale("plan")            # plan scale (>= section scale)
    ox, oy = M["section_origin"]
    px, py = M["plan_origin"]
    n, H, b, w, t = sp["so_bac"], sp["cao_tang"], sp["b"], sp["w"], sp["t"]
    h, L = H / n, (n - 1) * b
    ds = sp["dam_con"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)          # section: real (x, z)
    PL = lambda p: ((p[0] - px) * sp_, (p[1] - py) * sp_)     # plan: real (x, y)
    by = lambda tag: [p for p in D.prims if p.tag == tag]
    ln = lambda p: math.hypot(p.p2[0] - p.p1[0], p.p2[1] - p.p1[1]) * s
    lnp = lambda p: math.hypot(p.p2[0] - p.p1[0], p.p2[1] - p.p1[1]) * sp_
    ris, tre = by("riser"), by("tread")
    ok1 = len(ris) == n and all(close(ln(r), h, TOL) for r in ris) and close(sum(ln(r) for r in ris), H, TOL)
    C.add(1, "1.1", "chiều cao bậc: mỗi riser dài H/so_bac và tổng h × so_bac = cao_tang (sai số ≤ 1e-6 mm)", ok1,
          f"{len(ris)} riser; h = {h:.6f} mm; tổng {sum(ln(r) for r in ris):.6f} mm; cao_tang {H:g}; riser đầu {ln(ris[0]):.6f}" if ris else "không có riser")
    C.add(1, "1.2", "số mặt bậc = so_bac − 1 và mỗi mặt bậc dài b", len(tre) == n - 1 and all(close(ln(x), b, TOL) for x in tre), f"{len(tre)} mặt bậc (so_bac − 1 = {n - 1}); b = {b:g} mm")
    exp_r = [((( i - 1) * b, (i - 1) * h), ((i - 1) * b, i * h)) for i in range(1, n + 1)]
    exp_t = [(((i - 1) * b, i * h), (i * b, i * h)) for i in range(1, n)]
    got = [(R(p.p1), R(p.p2)) for p in ris + tre]
    n_ok, miss = greedy_match(exp_r + exp_t, got, lambda e, g: _same_seg(e, g, TOL))
    C.add(1, "1.3", "đỉnh răng cưa từng bậc: mọi đoạn riser/mặt bậc đúng vị trí theo công thức ((i−1)b, i·h)", n_ok == len(exp_r) + len(exp_t) == len(got), f"{n_ok}/{len(exp_r) + len(exp_t)} đoạn đúng vị trí; thiếu {miss[:2]}")
    outline = by("plan_outline")
    ok4 = len(outline) == 1 and close((outline[0].p1[0] - outline[0].p0[0]) * sp_, L, TOL) and close((outline[0].p1[1] - outline[0].p0[1]) * sp_, w, TOL) and close(outline[0].p0[0], px, 1e-9)
    tl = by("plan_tread_line")
    n_t, _ = greedy_match([i * b for i in range(1, n - 1)], tl, lambda e, g: close(PL(g.p1)[0], e, TOL) and close(PL(g.p2)[0], e, TOL) and close(lnp(g), w, TOL))
    C.add(1, "1.4", "mặt bằng (theo tỷ lệ riêng của hình): dài (so_bac − 1) × b, rộng w; n − 2 đường mặt bậc đúng vị trí", ok4 and n_t == n - 2 == len(tl),
          f"dài {(outline[0].p1[0] - outline[0].p0[0]) * sp_:.3f} (cần {L:g}), rộng {(outline[0].p1[1] - outline[0].p0[1]) * sp_:.3f} (cần {w:g}); {n_t}/{n - 2} đường mặt bậc" if outline else "không có hình chữ nhật mặt bằng")
    X = expected_texts(sp)
    steps = by("step_no")
    n_s, _ = greedy_match([(str(i), (i - 0.5) * b) for i in range(1, n)], steps, lambda e, g: g.s == e[0] and close(PL(g.pos)[0], e[1], TOL))
    C.add(1, "1.5", "đánh số bậc 1..(so_bac − 1) đúng chữ và đúng giữa mặt bậc", n_s == n - 1 == len(steps), f"{n_s}/{n - 1} số bậc đúng")
    top, low = by("stringer_top"), by("stringer_low")
    slope_ok = len(top) == 1 and close(math.atan2(R(top[0].p2)[1] - R(top[0].p1)[1], R(top[0].p2)[0] - R(top[0].p1)[0]), math.atan(h / b), 1e-9)
    ang = by("angle_text")
    ang_ok = len(ang) == 1 and ang[0].s == X["angle"] and close(ang[0].rot, math.degrees(math.atan(h / b)), 1e-9)
    dist_ok = pos_ok = False
    ex6 = _strip_expect(sp)                  # lower edge through the riser feet; top edge o above it, cut flat at the upper floor level when o > h
    if len(low) == 1 and len(top) == 1:
        (xt1, zt1), (xt2, zt2) = R(top[0].p1), R(top[0].p2)
        x2, z2 = R(low[0].p2)
        z_top = zt1 + (zt2 - zt1) * (x2 - xt1) / (xt2 - xt1) if xt2 != xt1 else float("nan")        # the line of the drawn top edge, measured where the lower edge ends
        dist_ok = close(z_top - z2, ex6["od"], TOL)                      # vertical distance of the two edges = the drawn depth (o = bd / cos theta; snug: h)
        pos_ok = _same_seg((R(top[0].p1), R(top[0].p2)), ex6["top"], TOL) and _same_seg((R(low[0].p1), R(low[0].p2)), ex6["low"], TOL)
    C.add(1, "1.6", "góc dốc = atan(h/b) (đo trên dầm cốn), chữ góc 1 chữ số thập phân; khoảng cách đứng hai mép dầm cốn = độ sâu dải vẽ (o = bd/cosθ; dầm sâu hơn bậc ≤ 10 mm vẽ khít = h); mép dưới đi qua chân bậc từ gốc (0, 0)",
          slope_ok and ang_ok and dist_ok and pos_ok,
          f"góc {math.degrees(math.atan(h / b)):.4f}°, chữ {ang[0].s if ang else None!r}; khoảng cách đứng hai mép {ex6['od']:.3f} mm (khai báo {ds['bd']:g} mm vuông góc, o = {ex6['o']:.3f}{', vẽ khít' if ex6['snug'] else ''}): {dist_ok}; vị trí hai mép: {pos_ok}")
    lv = by("level_line")
    zs = sorted(round(R(p.p1)[1], 6) for p in lv)
    lvt = sorted(p.s for p in by("level_text"))
    C.add(1, "1.7", "hai đường cao độ (CENTER) tại z = 0 và z = cao_tang; chữ cao độ +0.000 / +cao_tang/1000", zs == [0.0, round(H, 6)] and all(p.layer == "NET-TAM" for p in lv) and lvt == sorted(X["levels"]),
          f"z = {zs}; chữ {lvt}")
    exp_v = [("v", h), ("v", H), ("h", b), ("h", L), ("v", w)]
    if M["chain_collapsed"]:
        exp_v.append(("h", L))
    else:
        exp_v += [("h", b)] * (n - 1) + [("h", L)]
    got_v = [(d.kind, d.value) for d in D.dims]
    n_d, miss_d = greedy_match(exp_v, got_v, lambda e, g: e[0] == g[0] and close(e[1], g[1], TOL))
    geo_ok = all(close((abs(d.p2[0] - d.p1[0]) if d.kind == "h" else abs(d.p2[1] - d.p1[1])) * D.view_scale(d.view), d.value, TOL) for d in D.dims)
    hdim = [d for d in D.dims if d.kind == "v" and abs(d.value - h) < 1e-9]
    C.add(1, "1.8", "kích thước: h (chính xác, không làm tròn), b, cao_tang, tổng chiều dài, w, chuỗi/gộp chuỗi; độ dài hình học = giá trị", n_d == len(exp_v) == len(got_v) and geo_ok and len(hdim) == 1 and hdim[0].text == X["h_label"],
          f"{n_d}/{len(exp_v)} kích thước đúng; nhãn h = {hdim[0].text if hdim else None!r} (h chính xác = {h:.6f}); chuỗi bị gộp: {M['chain_collapsed']}")
    notes = [p.s for p in by("note")]
    C.add(1, "1.9", "ghi chú: tấm thép dày đúng chieu_day_tam; 'so_bac x h = cao_tang'; '(so_bac−1) x b = dài'", notes == X["notes"], f"{notes}")
    cl = by("cut_label")
    yc = [PL(p.p1)[1] for p in by("cut_stroke")]
    ok10 = [p.s for p in cl] == ["1", "1"] and len(yc) == 2 and all(close(y, w / 2, TOL) for y in yc) and [p.s for p in by("title_section")] == ["MẶT CẮT 1-1"] and [p.s for p in by("title_plan")] == ["MẶT BẰNG THANG"]
    C.add(1, "1.10", "ký hiệu vết cắt 1-1 trên mặt bằng (2 đầu, nhãn 1, ở giữa bề rộng) và tên hai hình", ok10, f"nhãn {[p.s for p in cl]}, y vết cắt {[round(y, 3) for y in yc]} (w/2 = {w / 2:g})")
    check_layout_a(C, D, sp)
    check_dim_text_clear(C, D)
    check_extras_a(C, D, sp)
    check_dam_label(C, D, sp)
    check_stringer_covers_a(C, D, sp)
    check_steps_inside_a(C, D, sp)
    check_strip_closed_a(C, D, sp)
    check_strip_origin_a(C, D, sp)
    check_strip_below_floor_a(C, D, sp)
    check_section_exact_a(C, D, sp)
    check_strip_snug_a(C, D, sp)
    segs = [(g.p1, g.p2) for g in D.prims if isinstance(g, Line) and not g.sheet and not g.tag.startswith("dim_")]
    for r_ in (p for p in D.prims if isinstance(p, Rect) and not p.sheet):
        (ax_, ay_), (bx_, by_) = r_.p0, r_.p1
        segs += [((ax_, ay_), (bx_, ay_)), ((bx_, ay_), (bx_, by_)), ((bx_, by_), (ax_, by_)), ((ax_, by_), (ax_, ay_))]
    steps_ = [t for t in D.prims if isinstance(t, Text) and t.tag == "step_no"]
    gmin, gtxt = text_min_gap(steps_, segs)
    min_gap = D.info["params"]["khe_so_bac"]
    C.add(1, "1.22", f"khoảng hở giữa chữ số bậc và mọi nét ≥ {min_gap:g} mm giấy (khung chữ ước lượng nên thiên về an toàn)", bool(steps_) and gmin >= min_gap - 1e-9,
          f"{len(steps_)} số bậc; khoảng hở nhỏ nhất {gmin:.2f} mm (số {gtxt})")
    st_l = [(p.tag, p.layer) for p in D.prims if p.tag.startswith("stringer_")]
    wrong = [x for x in st_l if x[1] != "NET-CHINH"] + [(p.tag, p.layer) for p in D.prims if p.layer in ("KEO", "COT")]
    C.add(1, "1.21", "dầm cốn (stringer_*) nằm trên layer NET-CHINH (nét cơ bản, thấy); không có nét nào của thang trên layer KEO (kèo) hoặc COT (cột)", bool(st_l) and not wrong,
          f"{len(st_l)} nét dầm cốn; sai layer: {wrong[:3]}")
    check_expressions(C, [p.s for p in D.prims if isinstance(p, Text)], 1, "1.20", "chữ trên bản vẽ")
    if sp.get("warnings"):
        C.info(1, "1.11", "cảnh báo mềm (không phải lỗi)", " | ".join(sp["warnings"]))
    else:
        C.info(1, "1.11", "cảnh báo mềm 2h + b", f"2h + b = {sp['two_h_b']:.1f} mm, trong khoảng {sp['params']['nguong_2hb_min']:g}-{sp['params']['nguong_2hb_max']:g} mm (quy tắc kinh nghiệm, không phải điều khoản TCVN)")


SNUG_MAX = 10.0          # a stringer deeper than one riser by at most this much (vertical, real mm; o = h included) is drawn "snug": exactly one riser high


def _strip_expect(sp):
    """The stringer strip from the spec formulas (real mm, section coordinates, independent of the builder): the lower edge always runs through the feet of the risers,
    (0, 0) to (L, (n-1)h); the top edge is the drawn depth od above it. o = bd / cos(theta). o < h: od = o, top edge (0, o) to (L, (n-1)h + o). 0 <= o - h <= SNUG_MAX ("snug",
    o = h included): od = h, the top edge is the nosing line (0, h) to (L, H), nothing else. o - h > SNUG_MAX: od = o, top edge (0, o) to (xt, H) cut flat at the upper floor level,
    xt = (H - o) b / h, plus the cap (xt, H)-(L, H) and the left end (0, h)-(0, o) (in line with riser 1)."""
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    h, L = H / n, (n - 1) * b
    o = sp["dam_con"]["bd"] * math.hypot(b, h) / b
    snug = -1e-9 <= o - h <= SNUG_MAX + 1e-9
    od = h if snug else o
    low = ((0.0, 0.0), (L, (n - 1) * h))
    extras = []
    if od <= h + 1e-9:
        top = ((0.0, od), (L, (n - 1) * h + od))
    else:
        xt = (H - o) * b / h
        top = ((0.0, o), (xt, H))
        if L - xt > 1e-9:
            extras.append(((xt, H), (L, H)))
        extras.append(((0.0, h), (0.0, o)))
    return dict(o=o, od=od, snug=snug, top=top, low=low, extras=extras, deep=o > h + 1e-9)


def _expected_section_lines(sp, stub_real):
    """Every NET-CHINH line of the section (real mm): saw-tooth, the two floor stubs and the stringer strip."""
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    h, L = H / n, (n - 1) * b
    ex = _strip_expect(sp)
    out = [(((i - 1) * b, (i - 1) * h), ((i - 1) * b, i * h)) for i in range(1, n + 1)] + [(((i - 1) * b, i * h), (i * b, i * h)) for i in range(1, n)]
    out += [((-stub_real, 0.0), (0.0, 0.0)), ((L, H), (L + stub_real, H)), ex["top"], ex["low"]] + ex["extras"]
    return out


def _in_section_region(g, sp, stub_real):
    """True for a segment inside the section block (real mm): the plan block lies below it or to its right, outside this window."""
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    L = (n - 1) * b
    return all(-stub_real - 1.0 <= q[0] <= L + stub_real + 1.0 and -1.0 <= q[1] <= 2.0 * H for q in g)


def _match_all(exp, got, tol):
    """One-to-one match of expected segments with drawn ones: (missing expected, extra drawn)."""
    used, missing = set(), []
    for e in exp:
        for i, g in enumerate(got):
            if i not in used and _same_seg(e, g, tol):
                used.add(i)
                break
        else:
            missing.append(tuple(round(v, 3) for q in e for v in q))
    extra = [tuple(round(v, 3) for q in g for v in q) for i, g in enumerate(got) if i not in used]
    return missing, extra


def _cover_gap(segs, lo, hi):
    """Length of [lo, hi] not covered by the intervals `segs` [(a, b)] (any order of a, b)."""
    iv = sorted((max(lo, min(a, c)), min(hi, max(a, c))) for a, c in segs if max(a, c) > lo and min(a, c) < hi)
    pos, gap = lo, 0.0
    for a, c in iv:
        if a > pos:
            gap += a - pos
        pos = max(pos, c)
    return gap + max(0.0, hi - pos)


def _stringer_cover(top, low, n, b, h, tol, Hcap=None):
    """Feet of the risers F_i = ((i-1)b, (i-1)h), i = 1..n (the inner corners of the saw-tooth) against the stringer strip given by its top and lower edge
    ((x1, z1), (x2, z2)) in real mm. The strip covers a corner when low(x) <= z <= top(x); the top boundary is capped at the upper floor level Hcap (the strip is cut flat there).
    Returns (worst amount in mm a corner sticks out below the lower edge or above the top edge, [(i, amount)])."""
    (xt1, zt1), (xt2, zt2) = top
    (xl1, zl1), (xl2, zl2) = low
    zt = lambda x: min(zt1 + (zt2 - zt1) * (x - xt1) / (xt2 - xt1), Hcap if Hcap is not None else 1e18)
    zl = lambda x: 0.0 if x < min(xl1, xl2) - 1e-9 else zl1 + (zl2 - zl1) * (x - xl1) / (xl2 - xl1)
    out = []
    for i in range(1, n + 1):
        x, z = (i - 1) * b, (i - 1) * h
        d = max(zl(x) - z, z - zt(x))
        if d > tol:
            out.append((i, round(d, 3)))
    return (max((d for _, d in out), default=0.0)), out


def _steps_inside(top, low, n, b, h, tol, Hcap=None):
    """Whole saw-tooth against the stringer strip (top / lower edge as ((x1, z1), (x2, z2)), real mm): the nosings N_i = (i b, (i+1) h), i = 0..n-1, must not stand above the top edge
    (capped at the upper floor level Hcap) and the feet F_i = ((i-1) b, (i-1) h), i = 1..n, must not hang below the lower edge.
    Returns (worst nosing above the top edge, worst foot below the lower edge, [(kind, i, amount)]), amounts in mm."""
    (xt1, zt1), (xt2, zt2) = top
    (xl1, zl1), (xl2, zl2) = low
    zt = lambda x: min(zt1 + (zt2 - zt1) * (x - xt1) / (xt2 - xt1), Hcap if Hcap is not None else 1e18)
    zl = lambda x: 0.0 if x < min(xl1, xl2) - 1e-9 else zl1 + (zl2 - zl1) * (x - xl1) / (xl2 - xl1)
    bad, wn, wf = [], 0.0, 0.0
    for i in range(n):
        d = (i + 1) * h - zt(i * b)                            # nosing above the top edge
        wn = max(wn, d)
        if d > tol:
            bad.append(("mũi", i, round(d, 3)))
    for i in range(1, n + 1):
        d = zl((i - 1) * b) - (i - 1) * h                      # foot below the lower edge
        wf = max(wf, d)
        if d > tol:
            bad.append(("chân", i, round(d, 3)))
    return wn, wf, bad


def _strip_closure(top, low, lines, n, b, h, H, tol=1e-6):
    """Is the strip closed at both ends? top / low = the drawn edges ((x1, z1), (x2, z2)) left to right; lines = NET-CHINH segments of the section (real mm).
    Left: the top edge starts on x = 0 and x = 0 is drawn from the floor up to its start (riser 1 + the end in line with it). Right: the lower edge ends at the foot of riser n,
    the top edge ends on riser n (x = L) or on the upper floor level z = H, in which case z = H is drawn from its end to x = L (the cap); riser n closes the right end.
    Returns a list of problems."""
    L = (n - 1) * b
    vert = lambda x: [(g[0][1], g[1][1]) for g in lines if abs(g[0][0] - x) <= tol and abs(g[1][0] - x) <= tol]
    horz = lambda z: [(g[0][0], g[1][0]) for g in lines if abs(g[0][1] - z) <= tol and abs(g[1][1] - z) <= tol]
    (xs, zs), (xe, ze) = top
    (xl, zl0), (xr, zlr) = low
    prob = []
    if abs(xs) > tol:
        prob.append(f"mép trên bắt đầu ở x = {xs:.3f} (cần 0)")
    else:
        g = _cover_gap(vert(0.0), 0.0, zs)
        if g > tol:
            prob.append(f"đầu dưới hở {g:.3f} mm (x = 0, từ z = 0 tới {zs:.3f})")
    if abs(xr - L) > tol or abs(zlr - (n - 1) * h) > tol:
        prob.append(f"mép dưới kết thúc ở ({xr:.3f}; {zlr:.3f}), cần chân bậc cuối ({L:g}; {(n - 1) * h:.3f})")
    if abs(xe - L) <= tol:
        g = _cover_gap(vert(L), zlr, ze)
        if g > tol:
            prob.append(f"đầu trên hở {g:.3f} mm (x = L, từ z = {zlr:.3f} tới {ze:.3f})")
    elif abs(ze - H) <= tol:
        g1, g2 = _cover_gap(horz(H), xe, L), _cover_gap(vert(L), zlr, H)
        if g1 > tol:
            prob.append(f"đầu trên hở {g1:.3f} mm (z = H, từ x = {xe:.3f} tới {L:g})")
        if g2 > tol:
            prob.append(f"đầu trên hở {g2:.3f} mm (x = L, từ z = {zlr:.3f} tới {H:g})")
    else:
        prob.append(f"mép trên kết thúc ở ({xe:.3f}; {ze:.3f}): không chạm bậc cuối (x = {L:g}) cũng không ở sàn tầng trên (z = {H:g})")
    return prob


def _shallow_info(sp):
    """(is_deep, text) of the stringer against the steps: deep = o >= h (vertical depth o = bd / cos theta), the strip then holds the whole saw-tooth."""
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    h = H / n
    bd, bw, t = sp["dam_con"]["bd"], sp["dam_con"]["bw"], sp["dam_con"]["t"]
    need = h * b / math.hypot(b, h)
    o = bd * math.hypot(b, h) / b
    z = math.ceil(need / 10 - 1e-9) * 10
    return o >= h - 1e-9, (f"dầm cao {bd:g} mm (đứng {o:.1f} mm) không che trọn bậc: mũi bậc nhô {h - o:.1f} mm trên mép trên dầm, chân bậc vẫn nằm trên mép dưới (dải đã hạ); "
                           f"cần >= {need:.1f} mm vuông góc (gợi ý H{bw:g}x{z:g}x{t:g})")


def _section_lines_prims(D, sp):
    s = D.view_scale("section")
    ox, oy = D.meta["section_origin"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    stub = sp["params"]["doan_san"] * s
    return [(R(p.p1), R(p.p2)) for p in D.prims if isinstance(p, Line) and not p.sheet and p.layer == "NET-CHINH" and _in_section_region((R(p.p1), R(p.p2)), sp, stub)], stub


def check_steps_inside_a(C: Checks, D, sp):
    """1.25: the whole saw-tooth lies inside the stringer strip (nosings not above the top edge, feet not below the lower edge) when the stringer is at least one riser deep;
    a shallower stringer (o < h) is NOT an error: INFO with the soft warning (the strip is lowered so the feet are still covered, see 1.24)."""
    s = D.view_scale("section")
    ox, oy = D.meta["section_origin"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    h = H / n
    top = [p for p in D.prims if p.tag == "stringer_top"]
    low = [p for p in D.prims if p.tag == "stringer_low"]
    deep, msg = _shallow_info(sp)
    if len(top) != 1 or len(low) != 1:
        C.add(1, "1.25", "bậc nằm trọn trong dải dầm cốn", False, "không có đúng một mép trên và một mép dưới dầm cốn")
        return
    wn, wf, bad = _steps_inside(top=(R(top[0].p1), R(top[0].p2)), low=(R(low[0].p1), R(low[0].p2)), n=n, b=b, h=h, tol=TOL, Hcap=H)
    if deep:
        C.add(1, "1.25", "bậc nằm trọn trong dải dầm cốn: mọi mũi bậc không cao hơn mép trên dầm, mọi chân bậc không thấp hơn mép dưới dầm (dầm cao hơn một bậc)", not bad,
              f"{n} mũi + {n} chân bậc; mũi nhô trên mép trên tối đa {max(wn, 0.0):.6f} mm, chân nhô dưới mép dưới tối đa {max(wf, 0.0):.6f} mm; vi phạm: {bad[:3]}")
    else:
        C.info(1, "1.25", "bậc nằm trọn trong dải dầm cốn (dầm quá nông: không phải lỗi, chỉ cảnh báo)", f"{msg}; đo: mũi nhô {wn:.3f} mm, chân nhô {max(wf, 0.0):.3f} mm")


def check_strip_closed_a(C: Checks, D, sp):
    """1.26: the strip is closed at both ends with no gap (1e-6 mm): at the foot the top edge starts on x = 0 and x = 0 is drawn up to it (riser 1 and, when the stringer is deeper than
    one riser, the short end in line with it); at the top the lower edge ends at the foot of riser n and the top edge ends on riser n or on the upper floor level with the cap to riser n."""
    s = D.view_scale("section")
    ox, oy = D.meta["section_origin"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    h = H / n
    top = [p for p in D.prims if p.tag == "stringer_top"]
    low = [p for p in D.prims if p.tag == "stringer_low"]
    if len(top) != 1 or len(low) != 1:
        C.add(1, "1.26", "dải dầm khép kín ở hai đầu", False, "không có đúng một mép trên và một mép dưới dầm cốn")
        return
    orient = lambda a, c: (a, c) if a[0] <= c[0] else (c, a)
    lines, _ = _section_lines_prims(D, sp)
    prob = _strip_closure(orient(R(top[0].p1), R(top[0].p2)), orient(R(low[0].p1), R(low[0].p2)), lines, n, b, h, H)
    C.add(1, "1.26", "dải dầm khép kín ở hai đầu (khe hở ≤ 1e-6 mm): đầu dưới mép trên bắt đầu trên x = 0 và x = 0 được vẽ liền tới đó; đầu trên mép dưới kết thúc ở chân bậc cuối, "
          "mép trên kết thúc trên nét đứng bậc cuối hoặc cắt phẳng ở sàn tầng trên và nét nắp nối tới nét đứng bậc cuối", not prob, f"{len(lines)} nét NET-CHINH của mặt cắt; vấn đề: {prob[:3]}")


def check_strip_origin_a(C: Checks, D, sp):
    """1.27: the lower edge of the stringer starts at the origin (0, 0) (within 0.1 mm real)."""
    s = D.view_scale("section")
    ox, oy = D.meta["section_origin"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    low = [p for p in D.prims if p.tag == "stringer_low"]
    ok, d = False, "không có đúng một mép dưới dầm cốn"
    if len(low) == 1:
        a, c = R(low[0].p1), R(low[0].p2)
        left = a if a[0] <= c[0] else c
        dist = math.hypot(left[0], left[1])
        ok = dist <= 0.1
        d = f"đầu dưới của mép dưới dầm ở ({left[0]:.4f}; {left[1]:.4f}) mm thật, cách gốc {dist:.4f} mm (≤ 0,1)"
    C.add(1, "1.27", "đầu dưới của mép dưới dầm cốn trùng gốc (0, 0) (sai số ≤ 0,1 mm thật)", ok, d)


def check_strip_below_floor_a(C: Checks, D, sp):
    """1.28: no stringer line rises above the upper floor level z = H (the strip is cut flat there)."""
    s = D.view_scale("section")
    ox, oy = D.meta["section_origin"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    H = sp["cao_tang"]
    sl = [p for p in D.prims if p.tag.startswith("stringer_") and isinstance(p, Line)]
    zmax = max((max(R(p.p1)[1], R(p.p2)[1]) for p in sl), default=float("nan"))
    C.add(1, "1.28", "dải dầm cốn không vượt quá cao độ sàn tầng trên z = cao_tang (cắt phẳng tại sàn)", bool(sl) and zmax <= H + 1e-6, f"{len(sl)} nét dầm cốn; cao nhất z = {zmax:.6f} mm (sàn trên {H:g})")


def check_section_exact_a(C: Checks, D, sp):
    """1.29: the NET-CHINH lines of the section are exactly the saw-tooth, the two floor stubs and the stringer strip (top and lower edge, cap, end): none missing, none extra."""
    lines, stub = _section_lines_prims(D, sp)
    exp = _expected_section_lines(sp, stub)
    missing, extra = _match_all(exp, lines, TOL)
    C.add(1, "1.29", "nét NET-CHINH của mặt cắt đúng bằng: răng cưa, 2 đoạn sàn, dải dầm cốn (mép trên, mép dưới, nét nắp / đầu nếu cần): không thiếu, không thừa nét nào", not missing and not extra,
          f"{len(lines)} nét vẽ / {len(exp)} nét cần; thiếu {missing[:2]}; thừa {extra[:2]}")


def _snug_problems(top, low, n, b, h, H, tol):
    """"Snug" strip (real mm, edges left to right): every nosing (i b, (i+1) h) lies ON the top edge and every foot ((i-1) b, (i-1) h) ON the lower edge (within tol), the top edge starts at
    (0, h) and ends at (L, H) (the corner of the upper floor), the lower edge runs from (0, 0) to (L, (n-1) h). Returns (worst deviation, [problems])."""
    L = (n - 1) * b
    (xt1, zt1), (xt2, zt2) = top
    (xl1, zl1), (xl2, zl2) = low
    zt = lambda x: zt1 + (zt2 - zt1) * (x - xt1) / (xt2 - xt1)
    zl = lambda x: zl1 + (zl2 - zl1) * (x - xl1) / (xl2 - xl1)
    prob, worst = [], 0.0
    for i in range(n):
        d = abs((i + 1) * h - zt(i * b))
        worst = max(worst, d)
        if d > tol:
            prob.append(f"mũi {i + 1} cách mép trên {d:.3f} mm")
    for i in range(1, n + 1):
        d = abs((i - 1) * h - zl((i - 1) * b))
        worst = max(worst, d)
        if d > tol:
            prob.append(f"chân {i} cách mép dưới {d:.3f} mm")
    for nm, got, want in (("đầu trái mép trên", (xt1, zt1), (0.0, h)), ("đầu phải mép trên (góc sàn tầng trên)", (xt2, zt2), (L, H)),
                          ("đầu trái mép dưới", (xl1, zl1), (0.0, 0.0)), ("đầu phải mép dưới", (xl2, zl2), (L, (n - 1) * h))):
        d = math.hypot(got[0] - want[0], got[1] - want[1])
        worst = max(worst, d)
        if d > tol:
            prob.append(f"{nm} ở ({got[0]:.3f}; {got[1]:.3f}), cần ({want[0]:.3f}; {want[1]:.3f})")
    return worst, prob


def check_strip_snug_a(C: Checks, D, sp):
    """1.32: when the declared stringer is deeper than one riser by at most 10 mm (o = h included) the strip is drawn snug: nosings exactly on the top edge, feet exactly on the lower edge
    (0.01 mm real), top edge from the top of riser 1 to the corner (L, H) of the upper floor, no cap and no end line. Otherwise not applicable (INFO). 1.33 (INFO): the note shown to the user."""
    ex = _strip_expect(sp)
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    h = H / n
    o = ex["o"]
    if ex["snug"]:
        s = D.view_scale("section")
        ox, oy = D.meta["section_origin"]
        R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
        top = [p for p in D.prims if p.tag == "stringer_top"]
        low = [p for p in D.prims if p.tag == "stringer_low"]
        extra = [p.tag for p in D.prims if p.tag in ("stringer_cap", "stringer_end", "stringer_foot")]
        ok, d = False, "không có đúng một mép trên và một mép dưới dầm cốn"
        if len(top) == 1 and len(low) == 1:
            orient = lambda a, c: (a, c) if a[0] <= c[0] else (c, a)
            worst, prob = _snug_problems(orient(R(top[0].p1), R(top[0].p2)), orient(R(low[0].p1), R(low[0].p2)), n, b, h, H, 0.01)
            ok = not prob and not extra
            d = f"{n} mũi + {n} chân bậc, lệch lớn nhất {worst:.4f} mm thật (≤ 0,01); nét thừa (nắp / nét đứng ngắn / nét đáy): {extra}; vấn đề: {prob[:3]}"
        C.add(1, "1.32", "dải dầm vẽ khít bậc (dầm sâu hơn một bậc ≤ 10 mm): mũi bậc nằm đúng trên mép trên, chân bậc đúng trên mép dưới (0,01 mm), mép trên chạm góc sàn tầng trên (L, tổng cao), không có nét nắp / nét đứng ngắn", ok, d)
    else:
        C.info(1, "1.32", "dải dầm vẽ khít bậc", f"không áp dụng: o = {o:.2f} mm, h = {h:.2f} mm (o − h = {o - h:.2f} mm; chỉ vẽ khít khi 0 ≤ o − h ≤ {SNUG_MAX:g} mm)")
    if sp.get("ghi_chu"):
        C.info(1, "1.33", "ghi chú dải dầm vẽ khít bậc", " | ".join(sp["ghi_chu"]))


def check_stringer_covers_a(C: Checks, D, sp):
    """1.24: the stringer strip (top and lower edge of the primitives) covers every inner corner (foot of each riser): no corner sticks out below the lower edge."""
    s = D.view_scale("section")
    ox, oy = D.meta["section_origin"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    h = H / n
    top = [p for p in D.prims if p.tag == "stringer_top"]
    low = [p for p in D.prims if p.tag == "stringer_low"]
    ok, detail = False, "không có đúng một mép trên và một mép dưới dầm cốn"
    if len(top) == 1 and len(low) == 1:
        worst, bad = _stringer_cover((R(top[0].p1), R(top[0].p2)), (R(low[0].p1), R(low[0].p2)), n, b, h, TOL, Hcap=H)
        ok = not bad
        detail = f"{n} chân bậc; lòi ra khỏi dầm lớn nhất {worst:.3f} mm; chân lòi ra: {bad[:3]}"
    C.add(1, "1.24", "dầm cốn che hết góc trong (chân bậc) của răng cưa: mọi chân bậc ((i−1)b, (i−1)h) nằm trong dải giữa mép dưới và mép trên dầm", ok, detail)


SECTION_TAGS = {"floor_lower", "floor_upper", "riser", "tread", "stringer_top", "stringer_low", "stringer_end", "stringer_cap", "level_line", "level_tri", "level_bar", "level_text",
                "angle_text", "title_section", "note", "dam_label", "dam_leader"}


def _group_bboxes(D):
    """Annotated bounding box (sheet mm) of the section view and of the plan view, from primitives + expanded dimensions."""
    P = D.info["params"]
    groups = {"section": [], "plan": []}
    for p in D.prims:
        if p.sheet or p.tag.startswith("dim_"):
            continue
        if p.tag == "scale_note":
            continue
        groups["section" if p.tag in SECTION_TAGS else "plan"].append(p)
    for d in D.dims:
        groups[d.view].extend(expand_dim(d, P))
    titles = {v: next(p for p in D.prims if p.tag == t) for v, t in (("section", "title_section"), ("plan", "title_plan"))}
    for p in (q for q in D.prims if q.tag == "scale_note"):
        v = min(titles, key=lambda k: math.hypot(titles[k].pos[0] - p.pos[0], titles[k].pos[1] - p.pos[1]))
        groups[v].append(p)
    out = {}
    for v, ps in groups.items():
        bbs = [prim_bbox(p) for p in ps]
        out[v] = (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs))
    return out


def _hits_text(t, line, step=0.05, v_hi=1.05):
    """True when the segment passes through the (digit-height) text box of t; sampled every `step` mm paper."""
    from primitives import cap_to_em
    from tcvn import est_width
    w = est_width(t.s, cap_to_em(t.h), t.bold)
    x0, x1 = {"left": (0.0, w), "center": (-w / 2, w / 2), "right": (-w, 0.0)}[t.halign]
    c, s_ = math.cos(math.radians(t.rot)), math.sin(math.radians(t.rot))
    (ax, ay), (bx, by) = line.p1, line.p2
    n = max(2, int(math.hypot(bx - ax, by - ay) / step))
    for i in range(n + 1):
        px, py = ax + (bx - ax) * i / n - t.pos[0], ay + (by - ay) * i / n - t.pos[1]
        u, v = px * c + py * s_, -px * s_ + py * c
        if x0 <= u <= x1 and -0.05 * t.h <= v <= v_hi * t.h:
            return True
    return False


def check_dim_text_clear(C: Checks, D):
    """1.14: no dimension text runs over a tick or an extension line (measured on the text box, digit height)."""
    segs = [p for p in D.prims if isinstance(p, Line) and p.tag.startswith("dim_") and (p.tag.endswith("_ext") or p.tag.endswith("_tick") or p.tag.endswith("_line"))]
    texts = [p for p in D.prims if isinstance(p, Text) and p.tag.startswith("dim_") and p.tag.endswith("_text")]
    bad = [(t.s, round(t.pos[0], 1), round(t.pos[1], 1)) for t in texts if any(_hits_text(t, sg) for sg in segs)]
    C.add(1, "1.14", "chữ kích thước không đè lên tick, đường gióng hay đường kích thước (đo theo khung chữ)", not bad, f"{len(texts)} chữ kích thước, {len(segs)} tick/đường gióng; chữ bị đè: {bad}")


def _pt_seg(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    L2 = ab[0] ** 2 + ab[1] ** 2
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2))
    return math.hypot(p[0] - (a[0] + t * ab[0]), p[1] - (a[1] + t * ab[1]))


def _label_of(v):
    return f"{round(v):d}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}".replace(".", ",")


def _coord(p, kind):
    """coordinate along the dimension (x for 'h', y for 'v') and across it"""
    return (p[0], p[1]) if kind == "h" else (p[1], p[0])


def check_extras_a(C: Checks, D, sp):
    """1.15 dimension structure / extension lines touch the geometry, 1.16 UP text + arrow, 1.17 text height / clearance / step numbers inside the plan,
    1.18 each level text on its own level line + floor stubs + level symbols, 1.19 every dimension label matches its value."""
    M = D.meta
    n, H, b = sp["so_bac"], sp["cao_tang"], sp["b"]
    L = (n - 1) * b
    s, sp_ = D.view_scale("section"), D.view_scale("plan")
    by = lambda *tags: [p for p in D.prims if p.tag in tags]
    lines = [p for p in D.prims if isinstance(p, Line) and not p.sheet]
    geo = [p for p in lines if not p.tag.startswith("dim_")]
    for r_ in (p for p in D.prims if isinstance(p, Rect) and not p.sheet):          # rectangle edges count as geometry too (the plan outline)
        (ax_, ay_), (bx_, by_) = r_.p0, r_.p1
        geo += [Line(layer=r_.layer, tag="rect_edge", p1=a_, p2=b_) for a_, b_ in (((ax_, ay_), (bx_, ay_)), ((bx_, ay_), (bx_, by_)), ((bx_, by_), (ax_, by_)), ((ax_, by_), (ax_, ay_)))]
    # ---- 1.15
    bad15 = []
    for d in D.dims:
        r = d.role
        ticks = [p for p in lines if p.tag == f"dim_{r}_tick"]
        exts = [p for p in lines if p.tag == f"dim_{r}_ext"]
        along = lambda p: p[0] if d.kind == "h" else p[1]          # coordinate along the dimension
        across = lambda p: p[1] if d.kind == "h" else p[0]         # coordinate across (the dimension line position)
        dl = [p for p in lines if p.tag == f"dim_{r}_line" and abs(across(p.p1) - d.line_pos) < 1e-9 and abs(across(p.p2) - d.line_pos) < 1e-9
              and {round(along(p.p1), 6), round(along(p.p2), 6)} == {round(along(d.p1), 6), round(along(d.p2), 6)}]
        if not dl:
            bad15.append((d.text, "thiếu đường kích thước"))
            continue
        for e in (d.p1, d.p2):
            c = along(e)
            tk = [t for t in ticks if abs((along(t.p1) + along(t.p2)) / 2 - c) < 1e-6 and abs((across(t.p1) + across(t.p2)) / 2 - d.line_pos) < 1e-6]
            ex = [x for x in exts if abs(along(x.p1) - c) < 1e-6 and abs(along(x.p2) - c) < 1e-6 and min(abs(across(x.p1) - d.line_pos), abs(across(x.p2) - d.line_pos)) < 2.0]
            if not tk:
                bad15.append((d.text, "thiếu tick"))
            if len(ex) != 1:
                bad15.append((d.text, f"{len(ex)} đường gióng tại một đầu"))
                continue
            x = ex[0]
            far = x.p1 if abs(across(x.p1) - d.line_pos) > abs(across(x.p2) - d.line_pos) else x.p2
            dist = min((_pt_seg(far, g.p1, g.p2) for g in geo), default=99.0)
            if dist > 1.5:
                bad15.append((d.text, f"đường gióng cách hình {dist:.1f} mm"))
    C.add(1, "1.15", "mỗi kích thước có đường kích thước, 2 tick, 2 đường gióng; đường gióng bắt đầu sát hình đo (≤ 1,5 mm), không lơ lửng", not bad15, f"{len(D.dims)} kích thước; lỗi: {bad15[:4]}")
    # ---- 1.16
    up = by("up_text")
    arrow = [p for p in by("plan_arrow") if isinstance(p, Line)]
    outl = by("plan_outline")
    ok16 = len(up) == 1 and up[0].s == "LÊN" and len(arrow) == 3 and len(outl) == 1
    d16 = f"{len(up)} chữ LÊN, {len(arrow)} nét mũi tên"
    if ok16:
        r_ = outl[0]
        x0, y0, x1, y1 = min(r_.p0[0], r_.p1[0]), min(r_.p0[1], r_.p1[1]), max(r_.p0[0], r_.p1[0]), max(r_.p0[1], r_.p1[1])
        shaft = [a for a in arrow if abs(a.p1[1] - a.p2[1]) < 1e-9]
        heads = [a for a in arrow if abs(a.p1[1] - a.p2[1]) >= 1e-9]
        ok16 = (len(shaft) == 1 and len(heads) == 2 and all(abs(hd.p1[0] - shaft[0].p2[0]) < 1e-6 and abs(hd.p1[1] - shaft[0].p1[1]) < 1e-6 for hd in heads)
                and y0 < shaft[0].p1[1] < y1 and abs((shaft[0].p2[0] - shaft[0].p1[0]) * sp_ - (L - b)) < 1e-3 and up[0].pos[0] < x0 and y0 <= up[0].pos[1] <= y1)
        d16 += f"; thân mũi tên dài {(shaft[0].p2[0] - shaft[0].p1[0]) * sp_:.1f} mm thật (cần {L - b:g})" if shaft else "; thiếu thân mũi tên"
    C.add(1, "1.16", "mặt bằng: chữ 'LÊN' nằm ngoài hình chữ nhật bên trái và mũi tên (thân + 2 cánh) nằm trong hình, thân dài (n−2)·b", ok16, d16)
    # ---- 1.17
    texts = [p for p in D.prims if isinstance(p, Text) and not p.sheet]
    small = [(t.s, t.h) for t in texts if t.h < 2.0 - 1e-9]
    inside = True
    if outl:
        r_ = outl[0]
        x0, y0, x1, y1 = min(r_.p0[0], r_.p1[0]), min(r_.p0[1], r_.p1[1]), max(r_.p0[0], r_.p1[0]), max(r_.p0[1], r_.p1[1])
        inside = all(x0 <= t.pos[0] <= x1 and ((y0 <= t.pos[1] and t.pos[1] + t.h <= y1) or 1.4 <= t.pos[1] - y1 <= 5.0) for t in by("step_no"))          # inside a cell, or just above the plan
    over = []
    for t in texts:
        if t.tag in ("step_no", "cut_label") or t.tag.startswith("dim_"):
            continue
        if any(_hits_text(t, g, v_hi=1.45 if any(ord(c) > 127 for c in t.s) else 1.05) for g in lines):
            over.append(t.s)
    C.add(1, "1.17", "chữ: cao ≥ 2,0 mm giấy; số bậc nằm trong ô bậc hoặc ngay phía trên mặt bằng; chữ (trừ số bậc/kích thước) không đè lên nét nào", not small and inside and not over,
          f"{len(texts)} chữ; quá nhỏ: {small[:3]}; số bậc trong hình: {inside}; chữ đè nét: {over[:3]}")
    # ---- 1.18
    X = expected_texts(sp)
    ox, oy = M["section_origin"]
    lv = [p for p in by("level_line") if isinstance(p, Line)]
    lt = by("level_text")
    pair_bad = []
    for z, lab in ((0.0, X["levels"][0]), (H, X["levels"][1])):
        ys = [p.p1[1] for p in lv if abs((p.p1[1] - oy) * s - z) < 1e-3]
        if len(ys) != 1 or not lt:
            pair_bad.append((lab, "không có đúng một đường"))
            continue
        near = min(lt, key=lambda t: abs(t.pos[1] - ys[0]))
        if near.s != lab:
            pair_bad.append((lab, near.s))
    fl, fu = by("floor_lower"), by("floor_upper")
    stub_ok = (len(fl) == 1 and len(fu) == 1 and abs(fl[0].p2[0] - ox) < 1e-6 and abs(fl[0].p1[1] - oy) < 1e-6 and fl[0].p1[0] < ox - 1.0
               and abs(fu[0].p1[0] - (ox + L / s)) < 1e-6 and abs(fu[0].p1[1] - (oy + H / s)) < 1e-6 and fu[0].p2[0] > fu[0].p1[0] + 1.0)
    tri, bar = by("level_tri"), by("level_bar")
    sym_ok = (len(tri) == 4 and len(bar) == 2 and all(any(abs(t.p1[1] - y) < 1e-6 for t in tri) for y in (oy, oy + H / s))
              and all(any(abs(x.p1[1] - y - 3.0) < 1e-6 for x in bar) for y in (oy, oy + H / s)))
    C.add(1, "1.18", "cao độ: mỗi chữ cao độ nằm sát đúng đường của nó; sàn dưới/trên có đoạn nét đậm tại z = 0 / z = cao_tang; mỗi mức có ký hiệu (2 nét tam giác + thanh)",
          not pair_bad and stub_ok and sym_ok, f"gắn nhầm: {pair_bad}; đoạn sàn {stub_ok}; ký hiệu {len(tri)} nét tam giác, {len(bar)} thanh: {sym_ok}")
    # ---- 1.19
    got = sorted(t.s for t in D.prims if isinstance(t, Text) and t.tag.startswith("dim_") and t.tag.endswith("_text"))
    want = []
    for d in D.dims:
        if d.view == "plan" and d.role == "single" and d.kind == "h" and d.text and " x " in d.text:
            want.append(f"{n - 1} x {round(b):d} = {round(L):d}")
        else:
            want.append(_label_of(d.value))
    C.add(1, "1.19", "mọi chữ kích thước in ra đúng giá trị của kích thước (nguyên mm, hoặc 1 số lẻ dấu phẩy khi không nguyên; chuỗi gộp 'n x b = L')", got == sorted(want), f"in {got}; cần {sorted(want)}")


def check_dam_label(C: Checks, D, sp):
    """1.23: one label 'DẦM CỐN <dam_con>' (existing note size) with a leader whose tip is on the stringer's lower edge, clear of every other line."""
    P = D.info["params"]
    want = f"DẦM CỐN {sp['dam_con']['text']}"
    lab = [p for p in D.prims if isinstance(p, Text) and p.tag == "dam_label"]
    lead = [p for p in D.prims if isinstance(p, Line) and p.tag == "dam_leader"]
    low = [p for p in D.prims if isinstance(p, Line) and p.tag == "stringer_low"]
    ok = len(lab) == 1 and lab[0].s == want and len(lead) == 1 and len(low) == 1 and abs(lab[0].h - P["cao_chu_ghi_chu"]) < 1e-9
    detail = f"{len(lab)} nhãn {[t.s for t in lab]} (cần {want!r}), {len(lead)} đường dẫn"
    if ok:
        ld, lw, t = lead[0], low[0], lab[0]
        tip_d = min(_pt_seg(ld.p1, lw.p1, lw.p2), _pt_seg(ld.p2, lw.p1, lw.p2))
        tip = ld.p1 if _pt_seg(ld.p1, lw.p1, lw.p2) <= _pt_seg(ld.p2, lw.p1, lw.p2) else ld.p2
        other = ld.p2 if tip is ld.p1 else ld.p1
        near_text = math.hypot(other[0] - t.pos[0], other[1] - (t.pos[1] + t.h / 2)) <= 1.5
        length = math.hypot(ld.p2[0] - ld.p1[0], ld.p2[1] - ld.p1[1])
        others = [g for g in D.prims if isinstance(g, Line) and not g.sheet and g is not ld]
        clear = True
        for i in range(1, 41):                                  # sample the leader away from its tip: >= 0.3 mm from every other line
            f_ = 0.08 + 0.92 * i / 40
            pt = (tip[0] + (other[0] - tip[0]) * f_, tip[1] + (other[1] - tip[1]) * f_)
            if any(_pt_seg(pt, g.p1, g.p2) < 0.3 for g in others):
                clear = False
                break
        ok = tip_d < 1e-6 and near_text and length >= 3.0 and clear
        detail += f"; đầu mũi dẫn cách mép dưới dầm {tip_d:.6f} mm; đầu kia sát chữ {near_text}; dài {length:.1f} mm; không chạm nét khác {clear}"
    C.add(1, "1.23", "mặt cắt: nhãn tiết diện cốn 'DẦM CỐN <dam_con>' (cỡ chữ ghi chú sẵn có) với đường dẫn chạm mép dưới cốn, không chạm nét nào khác", ok, detail)


def check_layout_a(C: Checks, D, sp):
    """1.12 scales of the two views / 1.13 arrangement on the sheet."""
    M, P = D.meta, D.info["params"]
    notes = sorted(p.s for p in D.prims if p.tag == "scale_note")
    found = sorted(int(m.group(1)) for t in notes for m in [re.fullmatch(r"TỶ LỆ 1:(\d+)", t)] if m)
    s_sec, s_pl = D.view_scale("section"), D.view_scale("plan")
    ok = (len(found) == 2 and found == sorted([s_sec, s_pl]) and s_sec in SCALES and s_pl in SCALES and s_sec <= s_pl and D.scale == s_sec
          and D.fields.get("cell7") == (f"1:{s_sec}" if s_sec == s_pl else f"1:{s_sec} / 1:{s_pl}"))
    if sp.get("scale"):
        ok = ok and s_sec == s_pl == sp["scale"]
    elif not sp.get("ty_le_rieng", True):
        ok = ok and s_sec == s_pl
    C.add(1, "1.12", "tỷ lệ từng hình: ghi dưới mỗi hình, thuộc dãy chuẩn, mặt bằng không lớn hơn mặt cắt, ô tỷ lệ khung tên khớp, tỷ lệ bản vẽ DXF = tỷ lệ mặt cắt", ok,
          f"ghi chú {notes}; mặt cắt 1:{s_sec}, mặt bằng 1:{s_pl}; ô 7 = {D.fields.get('cell7')!r}; tỷ lệ DXF 1:{D.scale}")
    g = _group_bboxes(D)
    a, b = g["section"], g["plan"]
    sep_x, sep_y = max(a[0] - b[2], b[0] - a[2]), max(a[1] - b[3], b[1] - a[3])
    sep = max(sep_x, sep_y)
    gap = P["khoang_giua_hinh"]
    kind = "chong" if sep_y >= sep_x else "ngang"
    clear_ok = True
    sh = SHEETS[D.sheet]
    for v, r in g.items():
        clear_ok &= (r[0] >= sh.x0 + P["khe_vung_ve"] - 1e-6 and r[2] <= sh.x1 - P["khe_vung_ve"] + 1e-6 and r[1] >= sh.y0 + P["khe_vung_ve"] - 1e-6
                     and r[3] <= sh.y1 - P["khe_vung_ve"] + 1e-6 and max(sh.tb_x0 - r[2], r[1] - sh.tb_y1) >= P["khe_vung_ve"] - 1e-6)
    mode_ok = sp.get("bo_cuc", "auto") in ("auto", kind)
    if kind == "chong":
        pos_ok = b[3] <= a[1] - gap + 1e-6 and close(D.meta["plan_origin"][0], D.meta["section_origin"][0], 1e-9)
    else:
        pos_ok = b[0] >= a[2] + gap - 1e-6
    C.add(1, "1.13", "bố cục tờ giấy: hai hình không chồng nhau (cách ≥ khoang_giua_hinh), mỗi hình cách khung/khung tên ≥ khe_vung_ve, đúng bố cục yêu cầu", sep >= gap - 1e-6 and clear_ok and pos_ok and mode_ok,
          f"bố cục {kind}; khoảng cách hai hình {sep:.2f} mm (yêu cầu ≥ {gap:g}); mặt cắt bbox {tuple(round(x, 1) for x in a)}, mặt bằng bbox {tuple(round(x, 1) for x in b)}")


# ------------------------------------------------------------------ 2. DXF (independent of primitives)
def check_dxf_a(C: Checks, D, sp, dx):
    n, H, b, w = sp["so_bac"], sp["cao_tang"], sp["b"], sp["w"]
    h, L = H / n, (n - 1) * b
    ds = sp["dam_con"]
    X = expected_texts(sp)

    def seg(e):
        r = e["rec"]
        return ((f(r, 10), f(r, 20)), (f(r, 11), f(r, 21)))

    ents = {}
    for e in dx["ents"]:
        if e["type"] == "LINE":
            ents.setdefault(e["layer"], []).append(seg(e))
    main = ents.get("NET-CHINH", [])
    exp = [(((i - 1) * b, (i - 1) * h), ((i - 1) * b, i * h)) for i in range(1, n + 1)] + [(((i - 1) * b, i * h), (i * b, i * h)) for i in range(1, n)]
    n_ok, miss = greedy_match(exp, main, lambda e, g: _same_seg(e, g, TOL_DXF))
    lv = ents.get("NET-TAM", [])
    lv_ok = sorted(round(g[0][1], 3) for g in lv if close(g[0][1], g[1][1], 1e-6)) == [0.0, round(H, 3)]
    st = ents.get("NET-CHINH", [])
    stray = [lay for lay in ("KEO", "COT") if ents.get(lay)]          # the stair has no rafters / columns: nothing may be on those layers
    cos_t = math.cos(math.atan(h / b))
    ex = _strip_expect(sp)                           # from the spec formulas: lower edge through the riser feet, top edge o = bd / cos(theta) above it (cut flat at the floor when o > h)
    stub_r = sp["params"]["doan_san"] * D.scale
    top_ok = any(_same_seg(g, ex["top"], TOL_DXF) for g in st)
    low_ok = any(_same_seg(g, ex["low"], TOL_DXF) for g in st)
    C.add(2, "2.7", "DXF (mm thật, gốc ở mép sàn dưới): răng cưa đúng công thức, đường cao độ z = 0 và z = cao_tang, dầm cốn đúng độ dốc và chiều cao",
          n_ok == len(exp) and lv_ok and top_ok and low_ok and not stray,
          f"{n_ok}/{len(exp)} đoạn răng cưa; cao độ {lv_ok}; mép trên dầm {top_ok}; mép dưới dầm {low_ok} (dầm cốn trên layer NET-CHINH, không có gì trên layer KEO/COT: {not stray}); thiếu {miss[:2]}")
    region = [g for g in st if _in_section_region(g, sp, stub_r)]
    # 2.15: independent of the spec's stringer formula: the two sloped NET-CHINH edges must cover every foot of a riser (real mm)
    slope = [g for g in region if abs(g[1][0] - g[0][0]) > 1.0 and close((g[1][1] - g[0][1]) / (g[1][0] - g[0][0]), h / b, 1e-4)]       # the strip edges are the only sloped NET-CHINH lines of the section
    ok15, d15 = False, f"{len(slope)} đoạn dầm cốn nghiêng trên NET-CHINH (cần 2)"
    ends = None
    if len(slope) == 2:
        ends = sorted(((g[0], g[1]) if g[0][0] <= g[1][0] else (g[1], g[0]) for g in slope), key=lambda g: -g[1][1])     # higher edge first (compared at the upper end)
        worst, bad = _stringer_cover(ends[0], ends[1], n, b, h, 1e-6, Hcap=H)
        ok15 = not bad
        d15 = f"{n} chân bậc; lòi ra khỏi dầm lớn nhất {worst:.3f} mm; chân lòi ra: {bad[:3]}"
    C.add(2, "2.15", "DXF (mm thật): hai mép dầm cốn che hết mọi chân bậc ((i−1)b, (i−1)h): không chân nào lòi ra dưới mép dưới hoặc trên mép trên", ok15, d15)
    bad_two = f"{len(slope)} đoạn dầm cốn nghiêng trên NET-CHINH (cần 2)"
    # 2.16: the whole saw-tooth (nosings and feet) inside the strip, real mm; a stringer shallower than one riser only gives INFO (see 1.25)
    deep16, msg16 = _shallow_info(sp)
    if ends:
        wn16, wf16, bad16 = _steps_inside(ends[0], ends[1], n, b, h, 1e-6, Hcap=H)
        if deep16:
            C.add(2, "2.16", "DXF (mm thật): bậc nằm trọn trong dải dầm (mọi mũi bậc không cao hơn mép trên, mọi chân bậc không thấp hơn mép dưới; dầm cao hơn một bậc)", not bad16,
                  f"{n} mũi + {n} chân bậc; mũi nhô trên mép trên tối đa {max(wn16, 0.0):.6f} mm, chân nhô dưới mép dưới tối đa {max(wf16, 0.0):.6f} mm; vi phạm: {bad16[:3]}")
        else:
            C.info(2, "2.16", "DXF (mm thật): bậc nằm trọn trong dải dầm (dầm quá nông: chỉ cảnh báo)", f"{msg16}; đo: mũi nhô {wn16:.3f} mm, chân nhô {max(wf16, 0.0):.3f} mm")
    else:
        C.add(2, "2.16", "DXF (mm thật): bậc nằm trọn trong dải dầm", False, bad_two)
    # 2.17: strip closed at both ends (real mm), no gap
    if ends:
        prob17 = _strip_closure(ends[0], ends[1], region, n, b, h, H)
        C.add(2, "2.17", "DXF (mm thật): dải dầm khép kín ở hai đầu (khe hở ≤ 1e-6 mm): mép trên bắt đầu trên x = 0 và x = 0 được vẽ liền tới đó; mép dưới kết thúc ở chân bậc cuối, mép trên kết thúc trên nét đứng bậc cuối hoặc "
              "cắt phẳng ở sàn tầng trên với nét nắp nối tới nét đứng bậc cuối", not prob17, f"vấn đề: {prob17[:3]}")
    else:
        C.add(2, "2.17", "DXF (mm thật): dải dầm khép kín ở hai đầu", False, bad_two)
    # 2.18: lower edge starts at the origin; 2.19: nothing above the upper floor level; 2.20: the NET-CHINH lines of the section are exactly the expected ones
    if ends:
        left = ends[1][0]
        dist18 = math.hypot(left[0], left[1])
        C.add(2, "2.18", "DXF (mm thật): đầu dưới của mép dưới dầm cốn trùng gốc (0, 0) (sai số ≤ 0,1 mm thật)", dist18 <= 0.1, f"đầu dưới ở ({left[0]:.4f}; {left[1]:.4f}), cách gốc {dist18:.4f} mm")
    else:
        C.add(2, "2.18", "DXF (mm thật): đầu dưới của mép dưới dầm cốn trùng gốc (0, 0)", False, bad_two)
    # 2.21: snug strip (declared stringer deeper than one riser by at most 10 mm): nosings and feet exactly on the edges, top edge from (0, h) to the corner (L, H), nothing else (real mm, 0.01 mm)
    if ex["snug"]:
        if ends:
            worst21, prob21 = _snug_problems(ends[0], ends[1], n, b, h, H, 0.01)
            C.add(2, "2.21", "DXF (mm thật): dải dầm vẽ khít bậc (dầm sâu hơn một bậc ≤ 10 mm): mũi bậc đúng trên mép trên, chân bậc đúng trên mép dưới (0,01 mm), mép trên chạm góc sàn tầng trên (L, tổng cao)",
                  not prob21, f"{n} mũi + {n} chân bậc, lệch lớn nhất {worst21:.4f} mm thật; vấn đề: {prob21[:3]}")
        else:
            C.add(2, "2.21", "DXF (mm thật): dải dầm vẽ khít bậc", False, bad_two)
    else:
        C.info(2, "2.21", "DXF (mm thật): dải dầm vẽ khít bậc", f"không áp dụng: o − h = {ex['o'] - h:.2f} mm (chỉ vẽ khít khi 0 ≤ o − h ≤ {SNUG_MAX:g} mm)")
    zmax19 = max((max(g[0][1], g[1][1]) for g in region), default=float("nan"))
    C.add(2, "2.19", "DXF (mm thật): dải dầm cốn không vượt quá cao độ sàn tầng trên z = cao_tang (cắt phẳng tại sàn)", bool(region) and zmax19 <= H + 1e-6, f"nét NET-CHINH của mặt cắt cao nhất z = {zmax19:.6f} mm (sàn trên {H:g})")
    missing20, extra20 = _match_all(_expected_section_lines(sp, stub_r), region, TOL_DXF)
    C.add(2, "2.20", "DXF (mm thật): nét NET-CHINH của mặt cắt đúng bằng: răng cưa, 2 đoạn sàn, dải dầm cốn (nét nắp / đầu nếu cần): không thiếu, không thừa nét nào", not missing20 and not extra20,
          f"{len(region)} nét vẽ; thiếu {missing20[:2]}; thừa {extra20[:2]}")
    polys = [e for e in dx["ents"] if e["type"] == "LWPOLYLINE" and e["layer"] == "NET-CHINH"]
    plan = []
    for e in polys:
        xs, ys = [float(v) for v in e["rec"][10]], [float(v) for v in e["rec"][20]]
        plan.append((min(xs), min(ys), max(xs), max(ys)))
    # Scales are read from the DXF's own "TỶ LỆ 1:n" notes (independent of the metadata): section = the finer one (the DXF scale), plan >= section.
    scl = sorted(int(m.group(1)) for _, t in dx["texts"] for m in [re.fullmatch(r"TỶ LỆ 1:(\d+)", t)] if m)
    fac = (scl[0] / scl[-1]) if len(scl) == 2 else float("nan")          # plan size in the DXF = real size x s_sec / s_plan
    plan_ok = len(plan) == 1 and close(plan[0][2] - plan[0][0], L * fac, TOL_DXF) and close(plan[0][3] - plan[0][1], w * fac, TOL_DXF) and \
        ((close(plan[0][0], 0.0, TOL_DXF) and plan[0][3] < 0) or plan[0][0] > L)          # below the section on the same x origin, or to its right
    hid = ents.get("NET-KHUAT", [])
    hid_ok = bool(plan) and len(hid) == 2 and all(close(abs(g[1][0] - g[0][0]), L * fac, TOL_DXF) for g in hid) and \
        sorted(round(g[0][1] - plan[0][1], 3) for g in hid) == sorted([round(ds["bw"] * fac, 3), round((w - ds["bw"]) * fac, 3)])
    txt = [t for lay, t in dx["texts"]]
    texts_ok = all(txt.count(x) >= 1 for x in X["notes"] + X["levels"] + [X["angle"], "MẶT CẮT 1-1", "MẶT BẰNG THANG"]) and all(str(i) in txt for i in range(1, n))
    C.add(2, "2.8", "DXF: hình chữ nhật mặt bằng (n−1)·b × w (nhân s_cắt/s_bằng nếu mặt bằng nhỏ hơn), dưới hoặc bên phải mặt cắt; 2 mép dầm cốn khuất cách mép bw; chữ ghi chú/cao độ/góc/số bậc",
          plan_ok and hid_ok and texts_ok, f"mặt bằng {plan} (hệ số {fac:.3f}); dầm khuất {hid_ok}; chữ {texts_ok}")


# ------------------------------------------------------------------ 6. 3D model
def check_3d_a(C: Checks, D, sp, res: dict):
    s = D.scale
    ox, oy = D.meta["section_origin"]
    n, H, b, w, t = sp["so_bac"], sp["cao_tang"], sp["b"], sp["w"], sp["t"]
    h, L = H / n, (n - 1) * b
    if not res or not res.get("ok"):
        C.add(6, "6.1", "mô hình 3D dựng được trong FreeCAD", False, f"{(res or {}).get('error', 'không có kết quả')}")
        return
    C.add(6, "6.1", "3D: số mặt bậc = so_bac − 1; 2 dầm cốn", res["n_treads"] == n - 1 and res["n_stringers"] == 2, f"{res['n_treads']} mặt bậc, {res['n_stringers']} dầm cốn")
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    secs = [p for p in D.prims if p.tag in ("tread", "stringer_top", "stringer_low")]
    xs = [R(q)[0] for p in secs for q in (p.p1, p.p2)]
    zs = [R(q)[1] for p in secs for q in (p.p1, p.p2)]
    tread_z = [R(p.p1)[1] for p in D.prims if p.tag == "tread"]
    exp = dict(xmin=min(xs), xmax=max(xs), ymin=0.0, ymax=w, zmin=min(min(zs), min(tread_z) - t), zmax=max(zs))
    bb = res["bbox"]
    diffs = {k: round(bb[k] - exp[k], 6) for k in exp}
    C.add(6, "6.2", "3D: bounding box (dài × rộng × cao) khớp primitives ±0,001 mm", all(abs(v) <= 1e-3 for v in diffs.values()),
          f"3D {bb['xmax'] - bb['xmin']:.3f} × {bb['ymax'] - bb['ymin']:.3f} × {bb['zmax'] - bb['zmin']:.3f} mm; lệch {diffs}")
    tops = sorted(res["tread_tops"])
    C.add(6, "6.3", "3D: cao độ mặt từng bậc = i·h và khớp các đường mặt bậc trong primitives (±0,001 mm)",
          len(tops) == n - 1 and all(close(a, i * h, 1e-3) for i, a in enumerate(tops, 1)) and all(close(a, z, 1e-3) for a, z in zip(tops, sorted(tread_z))), f"{len(tops)} bậc; đầu {tops[:2]}, cuối {tops[-1:]}")
    C.add(6, "6.4", "3D: tổng thể tích thép tấm mặt bậc = (so_bac − 1)·b·w·t", close(res["tread_volume"], (n - 1) * b * w * t, 1e-3 * (n - 1) * b * w * t), f"{res['tread_volume']:.1f} mm3 (cần {(n - 1) * b * w * t:.1f})")
    C.info(6, "6.5", "ảnh 3D", f"{res.get('png') or 'không dựng được ảnh (' + str(res.get('png_error', '')) + ')'}")
