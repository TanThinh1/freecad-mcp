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
    dist_ok = False
    if len(low) == 1 and len(top) == 1:
        x2, z2 = R(low[0].p2)
        z_top = h + (h / b) * x2
        dist_ok = close((z_top - z2) * math.cos(math.atan(h / b)), ds["bd"], TOL)
    C.add(1, "1.6", "góc dốc = atan(h/b) (đo trên dầm cốn), chữ góc 1 chữ số thập phân; khoảng cách hai mép dầm cốn = chiều cao hộp", slope_ok and ang_ok and dist_ok,
          f"góc {math.degrees(math.atan(h / b)):.4f}°, chữ {ang[0].s if ang else None!r}; khoảng cách mép dầm {ds['bd']:g} mm: {dist_ok}")
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


SECTION_TAGS = {"floor_lower", "floor_upper", "riser", "tread", "stringer_top", "stringer_low", "stringer_end", "level_line", "level_tri", "level_bar", "level_text",
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
    top_ok = any(_same_seg(g, ((0.0, h), (L, H)), TOL_DXF) for g in st)
    cos_t = math.cos(math.atan(h / b))
    low_ok = any(abs(g[1][0] - L) < TOL_DXF and abs(g[1][0] - g[0][0]) > 1e-9 and close((H - g[1][1]) * cos_t, ds["bd"], TOL_DXF)
                 and close((g[1][1] - g[0][1]) / (g[1][0] - g[0][0]), h / b, 1e-9) for g in st)
    C.add(2, "2.7", "DXF (mm thật, gốc ở mép sàn dưới): răng cưa đúng công thức, đường cao độ z = 0 và z = cao_tang, dầm cốn đúng độ dốc và chiều cao",
          n_ok == len(exp) and lv_ok and top_ok and low_ok and not stray,
          f"{n_ok}/{len(exp)} đoạn răng cưa; cao độ {lv_ok}; mép trên dầm {top_ok}; mép dưới dầm {low_ok} (dầm cốn trên layer NET-CHINH, không có gì trên layer KEO/COT: {not stray}); thiếu {miss[:2]}")
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
