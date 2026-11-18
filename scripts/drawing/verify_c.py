"""Verification specific to drawing type C (cross-section of a steel portal frame). Every expected value is derived HERE from the spec with
independent formulas (never from build_c.py): members are long strips cut by half-planes along the bisector at the nodes (Sutherland-Hodgman),
the outline is the boundary of their UNION, compared with the drawn segments in BOTH directions. Tolerances: geometry 1e-6 mm real (floating
point only), DXF 1e-3 mm real. Details say "suy luận" for anything inferred and not measured.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal
from fractions import Fraction

from primitives import Circle, Line, Rect, Text, drawing_extent, prim_bbox
from readers import f, unesc
from tcvn import SHEETS, read_profile
from verify import Checks, check_expressions, close
from verify_a import _hits_text

TOL = 1e-6
TOL_DXF = 1e-3
SCALES_C = (20, 50, 100, 200, 500)
TITLE = "MẶT CẮT NGANG KHUNG"
OUTLINE_TAGS = ("col_edge", "raf_edge", "joint_step")
EXP_LAYER = {"col_edge": "COT", "raf_edge": "KEO", "joint_step": "KEO"}


# ------------------------------------------------------------------ exact helpers
def _fr(x) -> Fraction:
    """Exact value of the decimal that a float / int prints as (spec numbers are decimals)."""
    return Fraction(repr(float(x))) if not isinstance(x, Fraction) else x


def half_up(x) -> int:
    return math.floor(_fr(x) + Fraction(1, 2))


def lvl_text(x) -> str:
    m = half_up(x)
    return f"+{m // 1000}.{m % 1000:03d}"


def exact_text(x: Fraction) -> str:
    d = Decimal(x.numerator) / Decimal(x.denominator)
    return format(d.normalize(), "f")


def expect_values(sp: dict) -> dict:
    """All expected numbers from the spec (own formulas)."""
    n, H, hc, hr = _fr(sp["nhip"]), _fr(sp["cao_cot"]), sp["col"]["h"], sp["raf"]["h"]
    i = _fr(sp["do_doc_mai"]) / 100
    two = sp["so_mai"] == 2
    run = n / 2 if two else n
    rise = run * i
    top = H + rise
    th = math.atan(float(i))
    return dict(n=float(n), H=float(H), hc=float(hc), hr=float(hr), i=float(i), two=two, run=float(run), rise=float(rise), top=float(top), rise_fr=rise, top_fr=top,
                theta=th, theta_deg=math.degrees(th), raf_len=math.hypot(float(run), float(rise)))


def percent_str(p: float) -> str:
    return f"{p:g}".replace(".", ",")


def nodes_of(X: dict):
    """Rafter axes [(a, b)] and nodes (real mm)."""
    n, H, T = X["n"], X["H"], X["top"]
    if X["two"]:
        return [((0.0, H), (n / 2, T)), ((n / 2, T), (n, H))]
    return [((0.0, H), (n, T))]


# ------------------------------------------------------------------ polygons: members, union, boundary
def _clip(poly, p0, nrm):
    out = []
    for k in range(len(poly)):
        a, b = poly[k], poly[(k + 1) % len(poly)]
        da = (a[0] - p0[0]) * nrm[0] + (a[1] - p0[1]) * nrm[1]
        db = (b[0] - p0[0]) * nrm[0] + (b[1] - p0[1]) * nrm[1]
        if da >= 0:
            out.append(a)
        if (da > 0 and db < 0) or (da < 0 and db > 0):
            t = da / (da - db)
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return out


def _unit(v):
    L = math.hypot(*v)
    return (v[0] / L, v[1] / L)


def member_polys(X: dict):
    """[(name, polygon)] : 2 columns + rafters, each a long strip clipped by the bisector half-plane at its nodes."""
    n, H, T, hc, hr, th = X["n"], X["H"], X["top"], X["hc"], X["hr"], X["theta"]
    c, s = math.cos(th), math.sin(th)
    E = 60.0 * (hc + hr + 1.0)
    down = (0.0, -1.0)
    # node -> {member: direction away from the node}
    if X["two"]:
        nodeA, nodeR, nodeB = (0.0, H), (n / 2, T), (n, H)
        away = {("A", "colA"): down, ("A", "rafL"): (c, s), ("R", "rafL"): (-c, -s), ("R", "rafR"): (c, -s), ("B", "rafR"): (-c, s), ("B", "colB"): down}
        pos = {"A": nodeA, "R": nodeR, "B": nodeB}
        raf = {"rafL": (nodeA, nodeR), "rafR": (nodeR, nodeB)}
        cols = {"colA": (0.0, "A"), "colB": (n, "B")}
    else:
        nodeA, nodeB = (0.0, H), (n, T)
        away = {("A", "colA"): down, ("A", "raf"): (c, s), ("B", "raf"): (-c, -s), ("B", "colB"): down}
        pos = {"A": nodeA, "B": nodeB}
        raf = {"raf": (nodeA, nodeB)}
        cols = {"colA": (0.0, "A"), "colB": (n, "B")}

    def cut(poly, name):
        for (nd, m), dm in away.items():
            if m != name:
                continue
            other = [d for (nd2, m2), d in away.items() if nd2 == nd and m2 != m][0]
            nrm = (dm[0] - other[0], dm[1] - other[1])
            poly = _clip(poly, pos[nd], nrm)
        return poly

    out = []
    for name, (xc, nd) in cols.items():
        yt = pos[nd][1] + E
        poly = [(xc - hc / 2, 0.0), (xc + hc / 2, 0.0), (xc + hc / 2, yt), (xc - hc / 2, yt)]
        out.append((name, cut(poly, name)))
    for name, (a, b) in raf.items():
        d = _unit((b[0] - a[0], b[1] - a[1]))
        m = (-d[1], d[0])
        p0 = (a[0] - E * d[0], a[1] - E * d[1])
        p1 = (b[0] + E * d[0], b[1] + E * d[1])
        poly = [(p0[0] - hr / 2 * m[0], p0[1] - hr / 2 * m[1]), (p1[0] - hr / 2 * m[0], p1[1] - hr / 2 * m[1]),
                (p1[0] + hr / 2 * m[0], p1[1] + hr / 2 * m[1]), (p0[0] + hr / 2 * m[0], p0[1] + hr / 2 * m[1])]
        out.append((name, cut(poly, name)))
    return out


def _inside(poly, p, tol=0.0):
    k = len(poly)
    for a in range(k):
        q, r = poly[a], poly[(a + 1) % k]
        if (r[0] - q[0]) * (p[1] - q[1]) - (r[1] - q[1]) * (p[0] - q[0]) < -tol:
            return False
    return True


def in_union(polys, p):
    return any(_inside(pl, p) for _, pl in polys)


def _on_seg(p, a, b, tol=1e-7):
    ab = (b[0] - a[0], b[1] - a[1])
    L2 = ab[0] ** 2 + ab[1] ** 2
    t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2
    q = (a[0] + t * ab[0], a[1] + t * ab[1])
    return t, math.hypot(p[0] - q[0], p[1] - q[1])


def _seg_dist(p, a, b):
    """Distance from p to the SEGMENT a-b (parameter clamped to [0, 1])."""
    ab = (b[0] - a[0], b[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / (ab[0] ** 2 + ab[1] ** 2)))
    return math.hypot(p[0] - (a[0] + t * ab[0]), p[1] - (a[1] + t * ab[1]))


def _seg_cross(a, b, c, d):
    """parameter t on a-b where it properly crosses c-d, else None"""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12 * math.hypot(*r) * math.hypot(*s):
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        return t
    return None


def union_boundary(polys):
    """Boundary of the union of convex polygons as merged maximal collinear segments [(p, q)], edges on y = 0 dropped."""
    edges = []
    for _, pl in polys:
        for k in range(len(pl)):
            edges.append((pl[k], pl[(k + 1) % len(pl)]))
    pieces = []
    for a, b in edges:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-9:
            continue
        ts = {0.0, 1.0}
        for c, d in edges:
            if (c, d) == (a, b):
                continue
            t = _seg_cross(a, b, c, d)
            if t is not None:
                ts.add(t)
            for p in (c, d):
                t2, dist = _on_seg(p, a, b)
                if dist < 1e-7 and 0 < t2 < 1:
                    ts.add(t2)
        ts = sorted(ts)
        for t0, t1 in zip(ts, ts[1:]):
            p = (a[0] + t0 * (b[0] - a[0]), a[1] + t0 * (b[1] - a[1]))
            q = (a[0] + t1 * (b[0] - a[0]), a[1] + t1 * (b[1] - a[1]))
            ln = (t1 - t0) * L
            if ln < 1e-6:
                continue
            if abs(p[1]) < 1e-9 and abs(q[1]) < 1e-9:
                continue
            m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            nrm = ((q[1] - p[1]) / ln, -(q[0] - p[0]) / ln)
            eps = 1e-3 * min(1.0, ln / 4)
            i1 = in_union(polys, (m[0] + eps * nrm[0], m[1] + eps * nrm[1]))
            i2 = in_union(polys, (m[0] - eps * nrm[0], m[1] - eps * nrm[1]))
            if i1 != i2:
                pieces.append((p, q))
    return merge_collinear(pieces)


def merge_collinear(segs, tol=1e-6):
    segs = [(tuple(p), tuple(q)) for p, q in segs]
    out = []
    used = [False] * len(segs)
    for i0, (p0, q0) in enumerate(segs):
        if used[i0]:
            continue
        used[i0] = True
        d = _unit((q0[0] - p0[0], q0[1] - p0[1]))
        base = p0
        iv = [(0.0, math.hypot(q0[0] - p0[0], q0[1] - p0[1]))]
        grew = True
        while grew:
            grew = False
            for j, (p, q) in enumerate(segs):
                if used[j]:
                    continue
                if abs(d[0] * (q[1] - p[1]) - d[1] * (q[0] - p[0])) > 1e-9 * math.hypot(q[0] - p[0], q[1] - p[1]):
                    continue
                if abs(d[0] * (p[1] - base[1]) - d[1] * (p[0] - base[0])) > tol:
                    continue
                t0 = (p[0] - base[0]) * d[0] + (p[1] - base[1]) * d[1]
                t1 = (q[0] - base[0]) * d[0] + (q[1] - base[1]) * d[1]
                lo, hi = min(t0, t1), max(t0, t1)
                if any(lo <= b + tol and hi >= a - tol for a, b in iv):
                    iv.append((lo, hi))
                    used[j] = True
                    grew = True
        lo, hi = min(a for a, _ in iv), max(b for _, b in iv)
        out.append(((base[0] + lo * d[0], base[1] + lo * d[1]), (base[0] + hi * d[0], base[1] + hi * d[1])))
    return out


def classify(seg, X):
    """Expected tag of an outline piece: vertical = col_edge, parallel to a rafter axis = raf_edge, otherwise (cut along the bisector) = joint_step."""
    (p, q) = seg
    d = _unit((q[0] - p[0], q[1] - p[1]))
    if abs(d[0]) < 1e-9:
        return "col_edge"
    for a, b in nodes_of(X):
        u = _unit((b[0] - a[0], b[1] - a[1]))
        if abs(u[0] * d[1] - u[1] * d[0]) < 1e-9:
            return "raf_edge"
    return "joint_step"


def compare_segments(expected, drawn, tol):
    """Both directions. expected: [(p, q)]; drawn: [(p, q, tag)] (real mm). Returns dict(extra, missing, dup, n_cov, drawn_len, exp_len)."""
    extra, owner = [], [[] for _ in expected]
    for k, (p, q, tag) in enumerate(drawn):
        hit = None
        for j, (a, b) in enumerate(expected):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            ta, da = _on_seg(p, a, b)
            tb, db = _on_seg(q, a, b)
            if da <= tol and db <= tol and -tol / L <= ta <= 1 + tol / L and -tol / L <= tb <= 1 + tol / L:
                hit = j
                owner[j].append((min(ta, tb) * L, max(ta, tb) * L, tag))
                break
        if hit is None:
            extra.append((tag, tuple(round(v, 3) for v in (*p, *q))))
    missing, dup, n_cov = [], [], 0
    for j, (a, b) in enumerate(expected):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        iv = sorted(owner[j])
        cur, gap = 0.0, False
        for lo, hi, _ in iv:
            if lo > cur + tol:
                gap = True
            if lo < cur - tol:
                dup.append((tuple(round(v, 3) for v in (*a, *b)), round(cur - lo, 3)))
            cur = max(cur, hi)
        if gap or cur < L - tol or not iv:
            missing.append(tuple(round(v, 3) for v in (*a, *b)))
        else:
            n_cov += 1
    drawn_len = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q, _ in drawn)
    exp_len = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in expected)
    return dict(extra=extra, missing=missing, dup=dup, n_cov=n_cov, drawn_len=drawn_len, exp_len=exp_len)


# ------------------------------------------------------------------ sheet <-> real
def _tools(D):
    ox, oy = D.origin
    s = D.scale
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    return R


def _profile():
    try:
        return read_profile()
    except Exception:  # noqa: BLE001
        return None


def _by(D, *tags):
    return [p for p in D.prims if p.tag in tags]


def _fits(w, h, g=5.0, sheet="A3"):
    """Can a w x h paper rectangle be placed in the frame inner area of `sheet` (clearance g) clear of the 180x65 title block (L-shaped region)."""
    sh = SHEETS[sheet]
    iw, ih = sh.frame_w - 2 * g, sh.frame_h - 2 * g
    top_h = (sh.y1 - g) - (sh.tb_y1 + g)
    left_w = (sh.tb_x0 - g) - (sh.x0 + g)
    return (w <= iw and h <= top_h) or (w <= left_w and h <= ih)


LEVEL_NOTE = "CAO ĐỘ TÍNH THEO GIAO ĐIỂM TRỤC"


def check_level_note(C: Checks, D, sp, X):
    """1.19: the note that levels are measured to the axis intersections: exactly one text, 2.5 mm, layer CHU, aligned with the top level text and
    5 mm above it, and not running over any line or other text (measured on the text box including diacritics)."""
    P = sp["params"]
    notes = [p for p in D.prims if isinstance(p, Text) and p.s == LEVEL_NOTE]
    s = D.scale
    ok = len(notes) == 1
    detail = f"{len(notes)} chữ ghi chú"
    if ok:
        t = notes[0]
        lt = [p for p in D.prims if isinstance(p, Text) and p.tag == "level_text" and p.s == lvl_text(X["top_fr"])]
        near = bool(lt) and abs(t.pos[0] - lt[0].pos[0]) <= 1.0 and 3.0 <= t.pos[1] - lt[0].pos[1] <= 8.0
        size = close(t.h, 2.5, 1e-9) and t.layer == "CHU" and t.rot == 0
        lines = [p for p in D.prims if isinstance(p, Line) and not p.sheet]
        hit_l = [p.tag for p in lines if _hits_text(t, p, v_hi=1.45)]
        bb = _tbox(t)
        hit_t = [p.s for p in D.prims if isinstance(p, Text) and p is not t and not p.sheet and _boxes_overlap(bb, _tbox(p))]
        ok = near and size and not hit_l and not hit_t
        detail = (f"1 chữ {t.s!r} cao {t.h:g} mm lớp {t.layer}; cạnh chữ cao độ đỉnh {near} (cùng lề trái, cao hơn 3-8 mm); đè nét: {sorted(set(hit_l))}; đè chữ: {hit_t}")
    C.add(1, "1.19", "ghi chú 'CAO ĐỘ TÍNH THEO GIAO ĐIỂM TRỤC': đúng một chữ cao 2,5 mm, cạnh cao độ đỉnh, không đè nét/chữ khác", ok, detail)


def _tbox(t):
    """Tight box of a text: width from est_width, height from the baseline up to the cap height (1.45 x cap when it has Vietnamese diacritics)."""
    from primitives import cap_to_em
    from tcvn import est_width
    w = est_width(t.s, cap_to_em(t.h), t.bold)
    x0, x1 = {"left": (0.0, w), "center": (-w / 2, w / 2), "right": (-w, 0.0)}[t.halign]
    hi = 1.45 if any(ord(c) > 127 for c in t.s) else 1.05
    c, s_ = math.cos(math.radians(t.rot)), math.sin(math.radians(t.rot))
    pts = [(t.pos[0] + u * c - v * s_, t.pos[1] + u * s_ + v * c) for u in (x0, x1) for v in (-0.05 * t.h, hi * t.h)]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def _boxes_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


# ------------------------------------------------------------------ 1. primitives
def check_primitives_c(C: Checks, D, sp):
    X = expect_values(sp)
    n, H, T, hc, hr, th = X["n"], X["H"], X["top"], X["hc"], X["hr"], X["theta"]
    s = D.scale
    R = _tools(D)
    prof = _profile()
    P = sp["params"]
    by = lambda *t: _by(D, *t)

    # ---- 1.1 formulas from the spec
    ok = (close(sp["y_top"], T, 1e-9) and close(sp["rise"], X["rise"], 1e-9) and close(sp["theta_deg"], X["theta_deg"], 1e-9) and close(sp["raf_len"], X["raf_len"], 1e-9)
          and sp["y_top_exact"] == X["top_fr"] and sp["rise_exact"] == X["rise_fr"])
    ok = ok and close(math.tan(th), X["i"], 1e-12) and close(X["raf_len"], math.hypot(X["run"], X["top"] - H), 1e-9)
    C.add(1, "1.1", "công thức từ spec: cao đỉnh = cao_cột + (nhịp/2 hoặc nhịp) × i, góc = atan(i), chiều dài kèo = √(run² + nhô²)", ok,
          f"đỉnh {exact_text(X['top_fr'])} mm (sp {sp['y_top']:.6f}), nhô {exact_text(X['rise_fr'])} (sp {sp['rise']:.6f}), góc {X['theta_deg']:.6f}° (sp {sp['theta_deg']:.6f}), "
          f"dài kèo {X['raf_len']:.6f} mm (sp {sp['raf_len']:.6f}); {sp['so_mai']} mái")

    # ---- expected union
    polys = member_polys(X)
    exp_seg = union_boundary(polys)
    drawn = []
    for p in D.prims:
        if p.tag in OUTLINE_TAGS and isinstance(p, Line):
            drawn.append((R(p.p1), R(p.p2), p.tag))
    cmp_ = compare_segments(exp_seg, drawn, TOL)
    n_exp_pieces = len(exp_seg)
    ok = not cmp_["extra"] and not cmp_["missing"] and not cmp_["dup"] and close(cmp_["drawn_len"], cmp_["exp_len"], 1e-5 * max(1, len(drawn)))
    C.add(1, "1.2", "đường bao = HỢP các cấu kiện (cột/kèo cắt theo phân giác tại nút): mọi đoạn vẽ nằm trên biên hợp, mọi đoạn biên hợp đều được vẽ, không trùng lặp (±1e-6 mm)", ok,
          f"{len(drawn)} đoạn vẽ; biên hợp {n_exp_pieces} đoạn ({cmp_['exp_len']:.3f} mm), {cmp_['n_cov']} được phủ; tổng dài vẽ {cmp_['drawn_len']:.3f}; thừa {cmp_['extra'][:3]}; thiếu {cmp_['missing'][:3]}; trùng {cmp_['dup'][:2]}")

    # ---- 1.3 tags / layers match the geometry class
    bad = []
    for p, q, tag in drawn:
        want = classify((p, q), X)
        if tag != want:
            bad.append((tag, want, tuple(round(v, 1) for v in (*p, *q))))
    lay_bad = [(pp.tag, pp.layer) for pp in D.prims if pp.tag in OUTLINE_TAGS and pp.layer != EXP_LAYER[pp.tag]]
    n_steps = sum(1 for e in exp_seg if classify(e, X) == "joint_step")
    got_steps = len(by("joint_step"))
    C.add(1, "1.3", "phân loại đoạn bao: đứng = col_edge (lớp COT), song song trục kèo = raf_edge, cạnh cắt phân giác = joint_step (lớp KEO); số bậc ở nút = số đoạn joint_step", not bad and not lay_bad and got_steps >= n_steps and (n_steps == 0) == (got_steps == 0),
          f"sai tag {bad[:2]}; sai lớp {lay_bad[:2]}; bậc kỳ vọng {n_steps} đoạn, vẽ {got_steps} đoạn joint_step (độ sâu cột {hc:g}, kèo {hr:g})")

    # ---- 1.4 no hidden / inner edge: every drawn outline piece is a boundary of the union (sampled points, both sides tested)
    inner, floating = [], []
    for p, q, tag in drawn:
        ln = math.hypot(q[0] - p[0], q[1] - p[1])
        if ln < 1e-9:
            continue
        nrm = ((q[1] - p[1]) / ln, -(q[0] - p[0]) / ln)
        for fr in (0.05, 0.3, 0.5, 0.7, 0.95):
            m = (p[0] + fr * (q[0] - p[0]), p[1] + fr * (q[1] - p[1]))
            a = in_union(polys, (m[0] + 1e-3 * nrm[0], m[1] + 1e-3 * nrm[1]))
            b = in_union(polys, (m[0] - 1e-3 * nrm[0], m[1] - 1e-3 * nrm[1]))
            if a and b:
                inner.append((tag, tuple(round(v, 2) for v in m)))
                break
            if not a and not b and not (abs(m[1]) < 1e-6):
                floating.append((tag, tuple(round(v, 2) for v in m)))
                break
    C.add(1, "1.4", "không có cạnh khuất/cạnh trong tại mối nối: mỗi đoạn bao có hợp cấu kiện ở đúng một phía (lấy mẫu 5 điểm/đoạn)", not inner and not floating,
          f"{len(drawn)} đoạn đã thử; nằm trong hợp (cạnh trong) {inner[:3]}; nằm ngoài hợp {floating[:3]}")

    # ---- 1.5 columns (measured on the drawn vertical edges)
    vcol = [(p, q) for p, q, tag in drawn if tag == "col_edge"]
    xs_exp = [-hc / 2, hc / 2, n - hc / 2, n + hc / 2]
    cols = {}
    for xe in xs_exp:
        seg = [(min(p[1], q[1]), max(p[1], q[1])) for p, q in vcol if close(p[0], xe, TOL) and close(q[0], xe, TOL)]
        cols[xe] = (min((a for a, _ in seg), default=None), max((b for _, b in seg), default=None))
    feet = all(v[0] is not None and close(v[0], 0.0, TOL) for v in cols.values())
    # expected top of each column edge from the union (independent of the drawing)
    exp_tops = {}
    for xe in xs_exp:
        ys = [max(a[1], b[1]) for a, b in exp_seg if abs(a[0] - xe) < 1e-9 and abs(b[0] - xe) < 1e-9]
        exp_tops[xe] = max(ys) if ys else None
    tops_ok = all(cols[xe][1] is not None and exp_tops[xe] is not None and close(cols[xe][1], exp_tops[xe], TOL) for xe in xs_exp)
    same = True
    if X["two"]:
        same = close(cols[-hc / 2][1] or -1, cols[n + hc / 2][1] or -2, TOL) and close(cols[hc / 2][1] or -1, cols[n - hc / 2][1] or -2, TOL)
    C.add(1, "1.5", "cột: 4 cạnh đứng tại x = ±h/2 quanh trục A và B, chân ở y = 0, đỉnh cạnh theo biên hợp; hai cột cao bằng nhau khi 2 mái", feet and tops_ok and same,
          "; ".join(f"x={xe:g}: y {cols[xe][0]}..{None if cols[xe][1] is None else round(cols[xe][1], 3)} (kỳ vọng đỉnh {None if exp_tops[xe] is None else round(exp_tops[xe], 3)})" for xe in xs_exp) + f"; cột bằng nhau: {same if X['two'] else 'không áp dụng (1 mái)'}")

    # ---- 1.6 rafters: measured depth / slope / axis height from the drawn edges
    ok6, det6, nodes_meas = True, [], []
    for a, b in nodes_of(X):
        d = _unit((b[0] - a[0], b[1] - a[1]))
        nrm = (-d[1], d[0])
        up, dn = [], []
        for p, q, tag in drawn:
            if tag != "raf_edge":
                continue
            u = _unit((q[0] - p[0], q[1] - p[1]))
            if abs(u[0] * d[1] - u[1] * d[0]) > 1e-9:
                continue
            off = (p[0] - a[0]) * nrm[0] + (p[1] - a[1]) * nrm[1]
            (up if off > 0 else dn).append((off, p, q))
        if not up or not dn:
            ok6 = False
            det6.append(f"kèo {tuple(round(v) for v in a)}->{tuple(round(v) for v in b)}: thiếu mép")
            continue
        ou, od = sorted(o for o, _, _ in up)[0], sorted(o for o, _, _ in dn)[0]
        longest_u = max(up, key=lambda t: math.hypot(t[2][0] - t[1][0], t[2][1] - t[1][1]))
        slope_deg = math.degrees(math.atan2(abs(longest_u[2][1] - longest_u[1][1]), abs(longest_u[2][0] - longest_u[1][0])))
        # axis = midline of the two edges: its height at the node abscissae
        yu = lambda x: longest_u[1][1] + (x - longest_u[1][0]) * (longest_u[2][1] - longest_u[1][1]) / (longest_u[2][0] - longest_u[1][0])
        longest_d = max(dn, key=lambda t: math.hypot(t[2][0] - t[1][0], t[2][1] - t[1][1]))
        yd = lambda x: longest_d[1][1] + (x - longest_d[1][0]) * (longest_d[2][1] - longest_d[1][1]) / (longest_d[2][0] - longest_d[1][0])
        ya, yb = (yu(a[0]) + yd(a[0])) / 2, (yu(b[0]) + yd(b[0])) / 2
        nodes_meas.append(((a[0], ya), (b[0], yb)))
        okr = close(ou - od, hr, TOL) and close(ou, hr / 2, TOL) and close(slope_deg, X["theta_deg"], 1e-7) and close(ya, a[1], TOL) and close(yb, b[1], TOL)
        ok6 &= okr
        det6.append(f"kèo x {a[0]:g}→{b[0]:g}: bề dày đo {ou - od:.6f} (h {hr:g}), độ dốc đo {slope_deg:.6f}° (cần {X['theta_deg']:.6f}°), cao độ trục đo {ya:.4f} → {yb:.4f} (cần {a[1]:.4f} → {b[1]:.4f})")
    C.add(1, "1.6", "kèo đo trên hình: bề dày đúng h, trục ở giữa hai mép, góc dốc = atan(i), cao độ trục tại nút = cao_cột / cao đỉnh", ok6, "; ".join(det6))

    # ---- 1.7 node positions: intersection of column axis (midline of its vertical edges) and rafter axis
    det7, ok7 = [], True
    colmid = {"A": (cols[-hc / 2][0] is not None and 0.0), "B": 0.0}
    xa = (xs_exp[0] + xs_exp[1]) / 2
    xb = (xs_exp[2] + xs_exp[3]) / 2
    ok7 = close(xa, 0.0, TOL) and close(xb, n, TOL)
    meas = {}
    for (a, b) in nodes_meas:
        meas[(round(a[0], 6))] = a
        meas[(round(b[0], 6))] = b
    for name, nd in (("nút gối A", (0.0, H)), ("nút gối B", (n, H if X["two"] else T))) + ((("nút đỉnh", (n / 2, T)),) if X["two"] else ()):
        mp = meas.get(round(nd[0], 6))
        good = mp is not None and close(mp[1], nd[1], TOL)
        ok7 &= good
        det7.append(f"{name} ({nd[0]:g}; {nd[1]:.4f}) đo ({None if mp is None else round(mp[0], 4)}; {None if mp is None else round(mp[1], 4)})")
    C.add(1, "1.7", "vị trí nút (giao trục cột và trục kèo) đo từ hình: gối A tại (0, cao_cột), gối B / đỉnh nóc theo công thức", ok7, "; ".join(det7) + f"; trục cột đo x = {xa:g}, {xb:g}")

    # ---- 1.8 axes A, B and bubbles
    axes = by("axis_v")
    axx = sorted(R(p.p1)[0] for p in axes if isinstance(p, Line))
    ymax_out = max(max(a[1], b[1]) for a, b in exp_seg)
    ax_ok = (len(axes) == 2 and all(isinstance(p, Line) and p.layer == "TRUC" and close(R(p.p1)[0], R(p.p2)[0], TOL) for p in axes) and len(axx) == 2 and close(axx[0], 0.0, TOL) and close(axx[1], n, TOL))
    ext_ok = all(min(R(p.p1)[1], R(p.p2)[1]) <= 0 + TOL and max(R(p.p1)[1], R(p.p2)[1]) >= ymax_out - TOL for p in axes if isinstance(p, Line))
    cen = prof is not None and prof["TRUC"]["ltype"] == "CENTER"
    circ = by("bubble")
    btxt = by("bubble_text")
    bub_ok = len(circ) == 2 and len(btxt) == 2 and all(isinstance(c, Circle) and c.layer == "TRUC-KYHIEU" for c in circ) and sorted(t.s for t in btxt) == ["A", "B"]
    bub_det = []
    if bub_ok:
        for c in circ:
            cx, cy = R(c.c)
            lab = "A" if close(cx, 0.0, TOL) else "B" if close(cx, n, TOL) else "?"
            t = [t for t in btxt if t.s == lab]
            good = lab != "?" and len(t) == 1 and math.hypot(t[0].pos[0] - c.c[0], t[0].pos[1] - c.c[1]) <= c.r and t[0].halign == "center" and close(c.r, P["duong_kinh_vong_truc"] / 2, 1e-9)
            ax = [p for p in axes if close(R(p.p1)[0], cx, TOL)]
            if ax:
                ends = [p.p1[1] for p in ax] + [p.p2[1] for p in ax]
                dist = min(abs(c.c[1] - e) for e in ends)
                good = good and close(dist, P["khe_vong_truc"] + c.r, 1e-6) and (c.c[1] > max(ends) or c.c[1] < min(ends))
                bub_det.append(f"{lab}: tâm x {cx:.4f}, cách đầu trục {dist:.3f} mm giấy (cần {P['khe_vong_truc'] + c.r:g}), r {c.r:g}")
            else:
                good = False
            bub_ok &= good
    C.add(1, "1.8", "trục A, B: 2 đường đứng tại x = 0 và x = nhịp, lớp TRUC (CENTER), vượt từ nền lên quá đỉnh; vòng tròn ký hiệu A, B đúng tâm, đường kính và khe", ax_ok and ext_ok and cen and bub_ok,
          f"x trục {[round(v, 6) for v in axx]}; lớp CENTER: {cen}; phủ y ≤ 0 .. ≥ {ymax_out:.1f}: {ext_ok}; {'; '.join(bub_det)}; bubble ok {bub_ok}")

    # ---- 1.9 ground line
    gl = [p for p in by("ground") if isinstance(p, Line)]
    g_ok = len(gl) == 1 and gl[0].layer == "NET-CHINH"
    gd = ""
    if g_ok:
        a, b = R(gl[0].p1), R(gl[0].p2)
        x0, x1 = min(a[0], b[0]), max(a[0], b[0])
        need = P["nen_keo_dai"] * s
        g_ok = close(a[1], 0.0, TOL) and close(b[1], 0.0, TOL) and x0 <= -hc / 2 - need + TOL and x1 >= n + hc / 2 + need - TOL
        gd = f"x {x0:.3f}..{x1:.3f} (khung {-hc / 2:.1f}..{n + hc / 2:.1f}, kéo dài thêm ≥ {need:g} mm thật), y {a[1]:.6f}"
    thick = prof is not None and prof["NET-CHINH"]["lw"] >= 50 and prof["NET-CHINH"]["lw"] > prof["KICH-THUOC"]["lw"]
    C.add(1, "1.9", "đường đất ±0.000: một đường NET-CHINH (nét đậm) tại y = 0, dài hơn khung (vượt mép cột ngoài ≥ nen_keo_dai)", g_ok and thick, f"{len(gl)} đường; {gd}; nét đậm {thick}")

    # ---- 1.10 levels
    lv = [p for p in by("level_line") if isinstance(p, Line)]
    lys = sorted(round(R(p.p1)[1], 6) for p in lv)
    want_y = sorted({0.0, round(H, 6), round(T, 6)})
    # +0.000 is marked on the (thick) ground line itself: a NET-TAM level line at y = 0 is allowed but not required; +cao_cot and +cao đỉnh need their own line
    lv_ok = {round(H, 6), round(T, 6)} <= set(lys) <= set(want_y) and len(lys) == len(set(lys)) and all(close(R(p.p1)[1], R(p.p2)[1], TOL) and p.layer == "NET-TAM" for p in lv)
    texts = sorted(p.s for p in by("level_text"))
    want_t = sorted({"+0.000", lvl_text(H), lvl_text(X["top_fr"])})
    txt_ok = texts == want_t and all(p.layer == "CHU" for p in by("level_text", "level_tri", "level_bar"))
    # each level has its symbol (triangle / bar) and its text next to the line (paper mm, suy luận about the attachment rule: within 10 mm)
    near_ok = True
    pair_bad = []
    lvl_tol = 3.0 + 0.8 + 1.0          # the text baseline sits 3 (triangle) + 0.8 mm above its level; any other level is >= 3 mm farther unless staggered (suy luận: layout rule of the builder)
    for yv, want_s in [(0.0, "+0.000"), (H, lvl_text(H)), (T, lvl_text(X["top_fr"]))]:
        ysh = D.origin[1] + float(yv) / s
        sym = [p for p in by("level_tri", "level_bar") if prim_bbox(p)[1] - 1e-6 <= ysh <= prim_bbox(p)[3] + 1e-6]
        tx = [p for p in by("level_text") if abs(p.pos[1] - (ysh + 3.0 + 0.8)) <= 0.05]       # the text of THIS level: baseline exactly 3.8 mm above the datum
        near_ok &= bool(sym) and len(tx) >= 1
        if not any(p.s == want_s for p in tx):
            pair_bad.append((want_s, [p.s for p in tx]))
    near_ok &= not pair_bad
    C.add(1, "1.10", "cao độ: đường NET-TAM tại y = cao_cột và cao đỉnh (mức 0 là đường đất); chữ +0.000 / +cao_cột / +cao đỉnh (3 số lẻ, làm tròn nửa lên); mỗi mức có ký hiệu và chữ gần đường", lv_ok and txt_ok and near_ok,
          f"y đường {lys} (cần {want_y}); chữ {texts} (cần {want_t}); ký hiệu/chữ gần đường và đúng chữ của từng mức: {near_ok}; chữ gắn nhầm mức: {pair_bad}")

    # ---- 1.11 dimensions
    exp_dims = [("h", n, (0.0, n), "span"), ("v", H, (0.0, H), "cao_cot"), ("v", T, (0.0, T), "top"), ("v", X["rise"], (H, T), "rise")]
    lines = [p for p in D.prims if isinstance(p, Line) and p.tag.startswith("dim_") and p.tag.endswith("_line")]
    dtexts = [p for p in D.prims if isinstance(p, Text) and p.tag.startswith("dim_") and p.tag.endswith("_text")]
    got = []
    for ln in lines:
        a, b = R(ln.p1), R(ln.p2)
        kind = "h" if close(a[1], b[1], 1e-9) else "v"
        rng = tuple(sorted((a[0], b[0]) if kind == "h" else (a[1], b[1])))
        mid = ((ln.p1[0] + ln.p2[0]) / 2, (ln.p1[1] + ln.p2[1]) / 2)
        lab = [t for t in dtexts if (t.rot == 0.0) == (kind == "h") and math.hypot(t.pos[0] - mid[0], t.pos[1] - mid[1]) < 3.0]
        got.append((kind, rng, [t.s for t in lab], ln))
    used, dim_bad = set(), []
    for kind, val, rng, nm in exp_dims:
        for k, (kd, rg, lab, ln) in enumerate(got):
            if k in used or kd != kind or not (close(rg[0], rng[0], TOL) and close(rg[1], rng[1], TOL)):
                continue
            used.add(k)
            want = str(half_up(_fr(val)) if nm in ("span", "cao_cot") else half_up(X["top_fr"] if nm == "top" else X["rise_fr"]))
            if lab != [want]:
                dim_bad.append(f"{nm}: nhãn {lab} (cần {want})")
            if ln.layer != "KICH-THUOC":
                dim_bad.append(f"{nm}: lớp {ln.layer}")
            break
        else:
            dim_bad.append(f"{nm}: không có đường kích thước đúng {kind} {rng}")
    dim_bad += [f"đường thừa {g[0]} {g[1]}" for k, g in enumerate(got) if k not in used]
    ticks = [p for p in D.prims if isinstance(p, Line) and p.tag.startswith("dim_") and p.tag.endswith("_tick")]
    tick_ok = len(ticks) == 8 and all(close(abs(p.p2[0] - p.p1[0]), 2.5, 1e-6) and close(abs(p.p2[1] - p.p1[1]), 2.5, 1e-6) for p in ticks)
    dig_ok = bool(dtexts) and all(close(t.h, 2.5, 1e-9) for t in dtexts) and len(dtexts) == 4
    lay_ok = all(p.layer == "KICH-THUOC" for p in D.prims if p.tag.startswith("dim_"))
    # tick centres sit on the dimension line ends
    endpts = [(round(ln.p1[0], 6), round(ln.p1[1], 6)) for ln in lines] + [(round(ln.p2[0], 6), round(ln.p2[1], 6)) for ln in lines]
    cen_ok = sorted(((round((p.p1[0] + p.p2[0]) / 2, 6), round((p.p1[1] + p.p2[1]) / 2, 6)) for p in ticks)) == sorted(endpts)
    dd = [(d.kind, round(d.value, 4), d.text) for d in D.dims]
    meta_ok = sorted((d.kind, round(d.value, 6)) for d in D.dims) == sorted((k, round(v, 6)) for k, v, _, _ in exp_dims)
    C.add(1, "1.11", "kích thước: nhịp, cao_cột, tổng cao, nhô của kèo (so_mai 2: nhịp/2·i) — đường dài đúng giá trị thật tại đúng toạ độ, nhãn đúng (làm tròn nửa lên), mũi tên 2.5, chữ 2.5, lớp KICH-THUOC",
          not dim_bad and tick_ok and dig_ok and lay_ok and cen_ok and meta_ok,
          f"{len(lines)} đường; D.dims {dd}; lỗi {dim_bad[:4]}; tick {len(ticks)} ok={tick_ok}, tâm tick trùng đầu đường {cen_ok}; chữ {[t.s for t in dtexts]} cao {sorted({t.h for t in dtexts})}")

    # ---- 1.12 soft warning when the top is not whole mm
    whole = X["top_fr"].denominator == 1
    w = sp.get("warnings", [])
    infow = D.info.get("warnings", None) if isinstance(D.info, dict) else None
    ex = exact_text(X["top_fr"])
    if whole:
        w_ok = not w
    else:
        w_ok = bool(w) and any(ex in x for x in w) and infow is not None and any(ex in x for x in infow) and any(str(half_up(X["top_fr"])) in x for x in w)
    C.add(1, "1.12", "cao đỉnh không nguyên mm → có cảnh báo mềm nêu giá trị chính xác và giá trị làm tròn (sp['warnings'] và báo cáo D.info); nguyên mm → không cảnh báo", w_ok,
          f"đỉnh {ex} mm ({'nguyên' if whole else 'không nguyên'}); cảnh báo sp: {w}; trong D.info: {infow}")

    # ---- 1.13 slope text
    st = by("slope_text")
    pct, ang = percent_str(sp["do_doc_mai"]), f"{X['theta_deg']:.1f}".replace(".", ",")
    pat = re.compile(r"i = (\d+(?:,\d+)?)% \((\d+,\d)°\)")
    sl_bad = [t.s for t in st if not (pat.fullmatch(t.s) and pat.fullmatch(t.s).group(1) == pct and pat.fullmatch(t.s).group(2) == ang)]
    axl = nodes_of(X)
    # placement (paper mm): the text is parallel to its rafter (rot = +-theta, sign of the rafter slope) and lies within 12 mm of the rafter axis; one text per roof
    pl_bad = []
    kn, cap = P["khoang_cach_nhan"], P["cao_chu_so_lieu"]
    lim_sl = hr / (2.0 * s) + kn + 2 * cap + 2.0      # paper mm: baseline offset <= half rafter depth + gap + 2 cap heights + 1.5 (second slot below the rafter) (+ 0.5 tolerance)
    owner = []
    for t in st:
        best = None
        for k, (a, b) in enumerate(axl):
            A, B = R_inv(D, a), R_inv(D, b)
            tt, dist = _on_seg(t.pos, A, B)
            if best is None or dist < best[0]:
                best = (dist, 1.0 if b[1] > a[1] else -1.0, 0 <= tt <= 1, k)
        owner.append(best[3] if best else None)
        if best is None or best[0] > lim_sl or not best[2] or not close(t.rot, best[1] * X["theta_deg"], 1e-6):
            pl_bad.append((t.s, None if best is None else round(best[0], 2), round(t.rot, 3)))
    one_each = sorted(o for o in owner if o is not None) == list(range(len(axl)))          # exactly one text on every rafter
    sl_ok = len(st) >= 1 and not sl_bad and not pl_bad and all(isinstance(t, Text) and t.layer == "CHU" for t in st) and len(st) == len(axl) and one_each
    C.add(1, "1.13", "chữ độ dốc: đúng dạng 'i = N% (góc°)' với N = do_doc_mai và góc = atan(i) 1 chữ số thập phân (dấu phẩy), lớp CHU, song song kèo, mỗi kèo đúng một chữ, cách trục kèo ≤ nửa h kèo + khoảng cách nhãn + cao chữ", sl_ok,
          f"{len(st)} chữ: {[t.s for t in st]}; cần 'i = {pct}% ({ang}°)'; hướng chữ {[round(t.rot, 3) for t in st]}; vị trí sai {pl_bad}")

    # ---- 1.14 member labels: each member (2 columns, every rafter) has a label with its own section text close to it (paper mm)
    sl = by("section_label")
    ct, rt = sp["col"]["text"], sp["raf"]["text"]
    ok14 = bool(sl) and all(isinstance(t, Text) and t.layer == "CHU" and (ct in t.s or rt in t.s) for t in sl)
    miss14 = []
    lim_c, lim_r = hc / (2.0 * s) + P["khoang_cach_nhan"] + 0.5, hr / (2.0 * s) + P["khoang_cach_nhan"] + P["cao_chu_so_lieu"] + 0.5      # paper mm from the member axis (rafter label: above, or first slot below)
    pool14 = list(sl)
    for name, txt_, (a, b), lim in [("cột A", ct, ((0.0, 0.0), (0.0, H)), lim_c), ("cột B", ct, ((n, 0.0), (n, H if X["two"] else T)), lim_c)] +             [(f"kèo {k + 1}", rt, ab, lim_r) for k, ab in enumerate(axl)]:
        A, B = R_inv(D, a), R_inv(D, b)
        hit = next((t for t in pool14 if txt_ in t.s and _seg_dist(t.pos, A, B) <= lim), None)
        if hit is None:
            miss14.append(name)
        else:
            pool14.remove(hit)          # one distinct label per member
    C.add(1, "1.14", "nhãn tiết diện: mỗi cột có nhãn đúng chuỗi tiết diện cột cách trục ≤ nửa h cột + khoảng cách nhãn, mỗi kèo có nhãn đúng chuỗi tiết diện kèo cách trục ≤ nửa h kèo + khoảng cách nhãn (khoảng cách tới đoạn trục, mỗi cấu kiện một nhãn riêng), lớp CHU", ok14 and not miss14,
          f"{[(t.s, round(t.rot, 1)) for t in sl]}; cột {ct!r}, kèo {rt!r}; thiếu nhãn gần: {miss14}")

    # ---- 1.15 title and scale texts
    ti = by("title")
    sn = by("scale_note")
    m = [re.fullmatch(r"(?:TỶ LỆ )?1:(\d+)", t.s) for t in sn]
    ts_ok = [t.s for t in ti] == [TITLE] and len(sn) == 1 and m[0] is not None and int(m[0].group(1)) == D.scale
    if D.fields.get("cell7") is not None:
        ts_ok = ts_ok and D.fields.get("cell7") == f"1:{D.scale}"
    C.add(1, "1.15", "tên hình 'MẶT CẮT NGANG KHUNG' và ghi chú tỷ lệ 1:N (N = tỷ lệ bản vẽ, ô tỷ lệ khung tên khớp)", ts_ok, f"tiêu đề {[t.s for t in ti]}; tỷ lệ {[t.s for t in sn]}; D.scale {D.scale}; ô 7 {D.fields.get('cell7')!r}")

    # ---- 1.16 / 1.17 scale and layout
    check_layout_c(C, D, sp, X)
    check_level_note(C, D, sp, X)

    # ---- 1.18 optional member axes
    ma = [p for p in by("member_axis") if isinstance(p, Line)]
    if sp["ve_truc"]:
        axl = nodes_of(X)
        ok18 = len(ma) == len(axl) and all(p.layer == "NET-TAM" for p in ma)
        for a, b in axl:
            d = _unit((b[0] - a[0], b[1] - a[1]))
            ok18 &= any(abs(_cross(d, _unit((R(p.p2)[0] - R(p.p1)[0], R(p.p2)[1] - R(p.p1)[1]))) < 1e-9) and _on_seg(R(p.p1), a, b)[1] < TOL and _on_seg(R(p.p2), a, b)[1] < TOL for p in ma)
        C.add(1, "1.18", "trục kèo (ve_truc_cau_kien = true): mỗi mái một đường NET-TAM trùng trục kèo", ok18, f"{len(ma)} đường; cần {len(axl)}")
    else:
        C.add(1, "1.18", "không vẽ trục kèo khi ve_truc_cau_kien = false (không có member_axis)", not ma, f"{len(ma)} đường member_axis")

    check_expressions(C, [p.s for p in D.prims if isinstance(p, Text)], 1, "1.20", "chữ trên bản vẽ")


def R_inv(D, p):
    """real mm -> sheet mm"""
    return (D.origin[0] + p[0] / D.scale, D.origin[1] + p[1] / D.scale)


def _cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def check_layout_c(C: Checks, D, sp, X):
    s = D.scale
    ext = drawing_extent(D.prims)
    w, h = ext[2] - ext[0], ext[3] - ext[1]
    # the whole drawing (annotated) must lie inside the frame (clear 5 mm) and clear of the title block
    g = 5.0
    sh = SHEETS[D.sheet]
    inside = ext[0] >= sh.x0 + g - 1e-6 and ext[2] <= sh.x1 - g + 1e-6 and ext[1] >= sh.y0 + g - 1e-6 and ext[3] <= sh.y1 - g + 1e-6
    tb_clear = max(sh.tb_x0 - ext[2], ext[1] - sh.tb_y1) >= g - 1e-6
    # real extent of the structure (outline + ground-free) scales with 1/s, annotations are constant paper mm: model W(s') = (W - Wr/s) + Wr/s'
    polys = member_polys(X)
    pts = [p for _, pl in polys for p in pl if abs(p[1]) < 1e-6 or p[1] <= X["top"] + 3 * (X["hc"] + X["hr"])]
    xs = [-X["hc"] / 2, X["n"] + X["hc"] / 2]
    ys = [0.0, max(max(a[1], b[1]) for a, b in union_boundary(polys))]
    wr, hr_ = xs[1] - xs[0], ys[1] - ys[0]
    # candidate order of the sheet policy (written here from the requirement): A3, A2, A1 in turn; within a sheet the largest scale first;
    # scales up to 1:100 on every sheet before any coarser scale. An explicit ty_le / kho_giay restricts the list.
    sheets = [sp["kho_giay"]] if sp.get("kho_giay", "auto") != "auto" else ["A3", "A2", "A1"]
    scs = [sp["scale"]] if sp.get("scale") else list(SCALES_C)
    order = [(sh_, sc) for sh_ in sheets for sc in scs if sc <= 100 or sp.get("scale")] + ([] if sp.get("scale") else [(sh_, sc) for sh_ in sheets for sc in scs if sc > 100])
    est = {sc: ((w - wr / s) + wr / sc, (h - hr_ / s) + hr_ / sc) for sc in SCALES_C}
    fits = {sc: (est[sc][0], est[sc][1]) for sc in SCALES_C}
    if (D.sheet, D.scale) in order:
        k = order.index((D.sheet, D.scale))
        earlier = order[:k]
        # the chosen pair must fit (measured); every earlier pair must NOT fit, with a 2 mm margin on the modelled size (suy luận)
        sc_ok = _fits(w, h, g, D.sheet) and all(not _fits(est[sc][0] - 2.0, est[sc][1] - 2.0, g, sh_) for sh_, sc in earlier if sc != D.scale or sh_ != D.sheet)
        why = ("tỷ lệ/khổ chỉ định" if (sp.get("scale") or sp.get("kho_giay", "auto") != "auto") else "mô hình (suy luận): các cặp khổ/tỷ lệ đứng trước đều không vừa")
    else:
        sc_ok, why = False, f"cặp ({D.sheet}, 1:{D.scale}) không nằm trong danh sách ứng viên {order[:6]}…"
    if sp.get("scale"):
        sc_ok = sc_ok and D.scale == sp["scale"]
    C.add(1, "1.16", "khổ giấy + tỷ lệ theo quy tắc: ưu tiên A3, lên A2 rồi A1 chỉ khi khổ nhỏ hơn không vừa ở tỷ lệ ≤ 1:100; tỷ lệ lớn nhất trong 20/50/100/200/500 còn vừa vùng vẽ (khung trừ góc khung tên 180×65); đo: vừa ở cặp đã chọn, suy luận: các cặp đứng trước không vừa", sc_ok,
          f"khổ {D.sheet}, tỷ lệ 1:{D.scale}, hình {w:.1f}×{h:.1f} mm giấy (đo); {why}")
    C.add(1, "1.17", "bố cục: toàn bộ nét/chữ nằm trong khung (cách mép ≥ 5 mm) và cách khung tên 180×65 ≥ 5 mm, không xoay tờ giấy (chữ chỉ nằm ngang, đứng hoặc song song kèo)", inside and tb_clear and all(min(abs(abs(getattr(p, "rot", 0.0)) - v) for v in (0.0, 90.0, X["theta_deg"])) < 1e-6 for p in D.prims),
          f"bbox {tuple(round(v, 1) for v in ext)}; trong khung {inside}; cách khung tên {max(sh.tb_x0 - ext[2], ext[1] - sh.tb_y1):.1f} mm")


# ------------------------------------------------------------------ 2. DXF (independent of primitives, real mm)
def check_dxf_c(C: Checks, D, sp, dx):
    X = expect_values(sp)
    n, H, T, hc, hr = X["n"], X["H"], X["top"], X["hc"], X["hr"]
    P = sp["params"]
    lines = {}
    for e in dx["ents"]:
        if e["type"] == "LINE":
            r = e["rec"]
            lines.setdefault(e["layer"], []).append(((f(r, 10), f(r, 20)), (f(r, 11), f(r, 21))))
    polys = member_polys(X)
    exp_seg = union_boundary(polys)
    # ---- 2.7 geometry
    axes = [g for g in lines.get("TRUC", []) if close(g[0][0], g[1][0], 1e-6)]
    axx = sorted(g[0][0] for g in axes)
    ymax = max(max(a[1], b[1]) for a, b in exp_seg)
    ax_ok = len(lines.get("TRUC", [])) == 2 and len(axx) == 2 and close(axx[0], 0.0, TOL_DXF) and close(axx[1], n, TOL_DXF) and \
        all(min(g[0][1], g[1][1]) <= TOL_DXF and max(g[0][1], g[1][1]) >= ymax - TOL_DXF for g in axes) and dx["layers"].get("TRUC", {}).get("ltype") == "CENTER"
    gr = lines.get("NET-CHINH", [])
    need = P["nen_keo_dai"] * D.scale
    gr_ok = len(gr) == 1 and close(gr[0][0][1], 0.0, TOL_DXF) and close(gr[0][1][1], 0.0, TOL_DXF) and min(gr[0][0][0], gr[0][1][0]) <= -hc / 2 - need + TOL_DXF and max(gr[0][0][0], gr[0][1][0]) >= n + hc / 2 + need - TOL_DXF
    drawn = [(a, b, "col_edge" if lay == "COT" else "keo") for lay in ("COT", "KEO") for a, b in lines.get(lay, [])]
    cmp_ = compare_segments(exp_seg, drawn, TOL_DXF)
    lay_bad = []
    for a, b, tag in drawn:
        cls = classify((a, b), X)
        if (cls == "col_edge") != (tag == "col_edge"):
            lay_bad.append((tag, cls, tuple(round(v, 1) for v in (*a, *b))))
    out_ok = not cmp_["extra"] and not cmp_["missing"] and not cmp_["dup"] and not lay_bad
    lv = [g for g in lines.get("NET-TAM", [])]
    want_y = sorted({0.0, round(H, 6), round(T, 6)})
    lv_h = sorted(round(g[0][1], 6) for g in lv if close(g[0][1], g[1][1], 1e-6))
    member_axes = [g for g in lv if not close(g[0][1], g[1][1], 1e-6)]
    ma_ok = not member_axes
    if sp["ve_truc"]:
        ma_ok = len(member_axes) == len(nodes_of(X))
        for a, b in nodes_of(X):
            d = _unit((b[0] - a[0], b[1] - a[1]))
            ma_ok &= any(abs(_cross(d, _unit((g[1][0] - g[0][0], g[1][1] - g[0][1])))) < 1e-9 and _on_seg(g[0], a, b)[1] <= TOL_DXF and _on_seg(g[1], a, b)[1] <= TOL_DXF for g in member_axes)
    lv_ok = {round(H, 6), round(T, 6)} <= set(lv_h) <= set(want_y) and len(lv_h) == len(set(lv_h)) and ma_ok and dx["layers"].get("NET-TAM", {}).get("ltype") == "CENTER"
    dl = lines.get("KICH-THUOC", [])
    dim_exp = [("h", 0.0, n), ("v", 0.0, H), ("v", 0.0, T), ("v", H, T)]
    dim_found = []
    for kind, a0, a1 in dim_exp:
        ok_ = False
        for g in dl:
            if kind == "h" and close(g[0][1], g[1][1], 1e-6) and close(min(g[0][0], g[1][0]), a0, TOL_DXF) and close(max(g[0][0], g[1][0]), a1, TOL_DXF):
                ok_ = True
            if kind == "v" and close(g[0][0], g[1][0], 1e-6) and close(min(g[0][1], g[1][1]), a0, TOL_DXF) and close(max(g[0][1], g[1][1]), a1, TOL_DXF):
                ok_ = True
        dim_found.append(ok_)
    circ = [e for e in dx["ents"] if e["type"] == "CIRCLE" and e["layer"] == "TRUC-KYHIEU"]
    cx = sorted(f(e["rec"], 10) for e in circ)
    circ_ok = len(circ) == 2 and close(cx[0], 0.0, TOL_DXF) and close(cx[1], n, TOL_DXF)
    C.add(2, "2.7", "DXF (mm thật, gốc ở giao trục A với nền): trục A/B (CENTER), đường đất y = 0, đường bao = hợp cấu kiện (2 chiều, ±1e-3), cao độ, 4 đường kích thước, 2 vòng tròn ký hiệu trục",
          ax_ok and gr_ok and out_ok and lv_ok and all(dim_found) and circ_ok,
          f"trục x {axx} ok {ax_ok}; đất {gr_ok}; bao: {cmp_['n_cov']}/{len(exp_seg)} đoạn biên phủ, {len(drawn)} đoạn vẽ, thừa {cmp_['extra'][:2]}, thiếu {cmp_['missing'][:2]}, trùng {cmp_['dup'][:1]}, sai lớp {lay_bad[:2]}; "
          f"cao độ y {lv_h} (cần {want_y}) ok {lv_ok}; kích thước {dim_found}; tâm vòng tròn x {[round(v, 4) for v in cx]}")
    # ---- 2.8 texts
    txt = [(lay, t) for lay, t in dx["texts"]]
    dim_txt = sorted(t for lay, t in txt if lay == "KICH-THUOC")
    want_dim = sorted(str(half_up(v)) for v in (_fr(sp["nhip"]), _fr(sp["cao_cot"]), X["top_fr"], X["rise_fr"]))
    lvl_txt = sorted(t for lay, t in txt if re.fullmatch(r"\+\d+\.\d{3}", t))
    want_lvl = sorted({"+0.000", lvl_text_(H), lvl_text_(X["top_fr"])})
    lvl_pos = []                       # (text, real y) of every level text entity: each level's own text must sit 3.8 mm (paper) above its datum
    for e in dx["ents"]:
        if e["type"] == "TEXT" and re.fullmatch(r"\+\d+\.\d{3}", unesc_(e)):
            r_ = e["rec"]
            lvl_pos.append((unesc_(e), (f(r_, 21) if 21 in r_ else f(r_, 20))))
    lvl_pair_ok = all(any(t_ == w_ and abs(y_ - (float(lv_) + 3.8 * D.scale)) <= 1e-3 for t_, y_ in lvl_pos) for lv_, w_ in [(0.0, "+0.000"), (H, lvl_text_(H)), (X["top_fr"], lvl_text_(X["top_fr"]))])
    pct, ang = percent_str(sp["do_doc_mai"]), f"{X['theta_deg']:.1f}".replace(".", ",")
    slope = [t for lay, t in txt if t.startswith("i = ")]
    slope_ok = len(slope) == len(nodes_of(X)) and all(t == f"i = {pct}% ({ang}°)" for t in slope)          # one text per rafter
    labs, lab_ok = [], True
    ctx, rtx = sp["col"]["text"], sp["raf"]["text"]
    for e in dx["ents"]:
        if e["type"] == "TEXT" and (ctx in unesc_(e) or rtx in unesc_(e)):
            r = e["rec"]
            pos = (f(r, 11), f(r, 21)) if 11 in r else (f(r, 10), f(r, 20))
            labs.append((unesc_(e), pos))
    sc_ = D.scale
    kn_, hc_, hr_ = P["khoang_cach_nhan"], hc, hr
    lim_c_, lim_r_ = hc_ / (2.0 * sc_) + kn_ + 0.5, hr_ / (2.0 * sc_) + kn_ + P["cao_chu_so_lieu"] + 0.5
    members = [("cột A", ctx, ((0.0, 0.0), (0.0, H)), lim_c_), ("cột B", ctx, ((n, 0.0), (n, H if X["two"] else T)), lim_c_)] + [(f"kèo {k + 1}", rtx, ab_, lim_r_) for k, ab_ in enumerate(nodes_of(X))]
    pool = list(labs)
    miss_l = []
    for nm, tx, (a_, b_), lim in members:        # one distinct label per member, close to its axis (paper mm x scale)
        hit = next((q for q in pool if tx in q[0] and _seg_dist(q[1], a_, b_) <= lim * sc_), None)
        if hit is None:
            miss_l.append(nm)
        else:
            pool.remove(hit)
    lab_ok = not miss_l
    labs = [t for t, _ in labs] + ([f"thiếu nhãn gần {miss_l}"] if miss_l else [])
    ab = sorted(t for lay, t in txt if t in ("A", "B"))
    scn = [t for lay, t in txt if t.startswith("TỶ LỆ ")]
    plain = [t for lay, t in txt if re.fullmatch(r"1:\d+", t)]
    sc_ok = scn == [f"TỶ LỆ 1:{D.scale}"] and all(t == f"1:{D.scale}" for t in plain)
    note_ok = sum(1 for lay, t in txt if t == LEVEL_NOTE) == 1
    ti = [t for lay, t in txt if t == TITLE]          # the view title (+ the same words in the title-block cell 3 when khung_ten.ten_ban_ve says so)
    C.add(2, "2.8", "DXF: chữ kích thước (nhịp, cao_cột, cao đỉnh, nhô — làm tròn nửa lên), cao độ +0.000/+cao_cột/+cao đỉnh, chữ độ dốc, nhãn tiết diện, A/B, tên hình và tỷ lệ",
          dim_txt == want_dim and lvl_txt == want_lvl and lvl_pair_ok and slope_ok and lab_ok and ab == ["A", "B"] and sc_ok and note_ok and len(ti) >= 1,
          f"kích thước {dim_txt} (cần {want_dim}); cao độ {lvl_txt} (cần {want_lvl}; mỗi chữ đúng mức: {lvl_pair_ok}); độ dốc {slope}; nhãn {labs}; A/B {ab}; tên hình {len(ti)}; tỷ lệ {sc_ok}; ghi chú cao độ đúng 1 chữ {note_ok}")


def unesc_(e):
    return unesc(e["rec"].get(1, [""])[0])


def lvl_text_(x):
    return lvl_text(x)
