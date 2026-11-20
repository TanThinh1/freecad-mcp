"""Verification specific to drawing type E ("ve_tu_do"). Every expected value is derived HERE from the spec with its own code (never from build_e / spec_e helpers): exact Fractions for
the wall bodies and their outline (edge splitting + point sampling, not the builder's coordinate compression), measured dimension values from the references, areas by the shoelace
formula, label strings; fixed paper sizes (bubbles, ticks, offsets) are multiplied by the scale. The expected geometry (real mm) is compared in BOTH directions with the drawn primitives
(1.50-1.54), with the LINE / LWPOLYLINE / CIRCLE entities of the DXF (2.30-2.32), of the DXF read back from the DWG (3.20) and with the strokes of the PDF (5.20). Text rules are
measured with the real Arial widths (as check 1.45 of type D): no text box crosses a drawn line (0.3 mm), no two text boxes overlap. New ids only: 1.50-1.69 (phase 2: 1.63-1.69), 2.30-2.37, 3.20-3.26, 5.20 (2.37 / 3.26: legend line samples, verify_e3; 1.78: level marks vs datum heights).
"""
from __future__ import annotations

import collections
import math
import re
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from fractions import Fraction

from primitives import Circle, Line, Rect, Text, prim_bbox
from readers import f
from tcvn import ARIAL_CAP, SHEETS
from verify import Checks, check_expressions, close, _seg_rect_gap
from verify_d import _box, _real_width, dxf_text_boxes
import verify_e2
import verify_e3

TOL = 1e-6              # real mm, floating point
TOL_DXF = 1e-3
TOL_PDF = 0.06
TEXT_MARGIN = 0.3       # mm paper between a text box and any line
MARGIN = 5.0
SCALE_LIMIT = 200
AUTO = (20, 50, 100, 200, 500)
FURN = {"giuong": (1600, 2000, "GIƯỜNG"), "ban": (1200, 600, "BÀN"), "ghe": (450, 450, "GHẾ"), "tu": (1200, 600, "TỦ"), "bep": (2000, 600, "BẾP"),
        "bon_rua": (800, 500, "BỒN RỬA"), "bon_cau": (400, 700, "BỒN CẦU"), "lavabo": (500, 400, "LAVABO")}
FAMILY_OF_TAG = (("sym:", "1.73"), ("nut:", "1.74"), ("ong:", "1.74"), ("legend_", "1.76"), ("hatch:", "1.63"), ("lop:", "1.64"), ("kc:", "1.64"), ("mong:", "1.64"), ("cot:", "1.64"), ("cd:", "1.65"), ("mai:", "1.65"), ("lc:", "1.65"), ("bt:", "1.65"),
                 ("lv:", "1.66"), ("cut", "1.66"), ("gio_", "1.66"), ("leader:", "1.66"), ("axis_", "1.50"), ("bubble", "1.50"), ("wall_", "1.51"), ("door_", "1.52"), ("win_", "1.52"), ("furn:", "1.53"), ("raw_", "1.53"), ("bac_", "1.53"), ("dim:", "1.54"))


def F(x):
    return float(x)


def sg(x):
    return (x > 0) - (x < 0)


# ------------------------------------------------------------------ expected geometry (real mm)
def legs_of(w):
    p = w["diem"]
    segs = [(p[i], p[i + 1]) for i in range(len(p) - 1)] + ([(p[-1], p[0])] if w["kin"] else [])
    day = Fraction(w["day"])
    lo, hi = {"giua": (-day / 2, day / 2), "trai": (Fraction(0), day), "phai": (-day, Fraction(0))}[w["can"]]
    out = []
    for i, (a, b) in enumerate(segs):
        dx, dy = sg(b[0] - a[0]), sg(b[1] - a[1])
        last = len(segs) - 1
        e0 = day / 2 if (w["can"] == "giua" and (w["kin"] or i > 0)) else Fraction(0)
        e1 = day / 2 if (w["can"] == "giua" and (w["kin"] or i < last)) else Fraction(0)
        out.append((a, (dx, dy), (-dy, dx), abs(b[0] - a[0]) + abs(b[1] - a[1]), lo, hi, e0, e1))
    return out


def body_rects(view):
    rects, ops = [], collections.defaultdict(list)
    for o in view["elems"]:
        if o["t"] in ("cua_di", "cua_so", "o_trong"):
            ops[(o["tuong"], o["doan"])].append((o["vi_tri"], o["vi_tri"] + o["rong"]))
    for w in (e for e in view["elems"] if e["t"] == "tuong" and e["kieu"] == "2_net"):
        for k, (a, d, n, length, lo, hi, e0, e1) in enumerate(legs_of(w)):
            cur = -e0
            spans = []
            for v0, v1 in sorted(ops.get((w["id"], k), [])):
                if v0 > cur:
                    spans.append((cur, v0))
                cur = v1
            if length + e1 > cur:
                spans.append((cur, length + e1))
            for t0, t1 in spans:
                cs = [(a[0] + d[0] * t + n[0] * o, a[1] + d[1] * t + n[1] * o) for t in (t0, t1) for o in (lo, hi)]
                rects.append((min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs)))
    return rects


def inside(rects, x, y):
    return any(r[0] < x < r[2] and r[1] < y < r[3] for r in rects)


def outline_edges(rects):
    """Boundary of the union by edge splitting: every rectangle edge is cut at the coordinates of the rectangles that touch it; a piece is boundary when exactly one side
    of its midpoint (offset by a tiny exact epsilon) lies inside the union. -> sorted list of merged ((x0, y0), (x1, y1)) Fractions."""
    eps = Fraction(1, 10_000)
    pieces = set()
    for (x0, y0, x1, y1) in rects:
        for horiz, k, lo, hi in ((True, y0, x0, x1), (True, y1, x0, x1), (False, x0, y0, y1), (False, x1, y0, y1)):
            near = [r for r in rects if (r[1] - eps <= k <= r[3] + eps if horiz else r[0] - eps <= k <= r[2] + eps) and (r[2] > lo and r[0] < hi if horiz else r[3] > lo and r[1] < hi)]
            cuts = {lo, hi}
            for r in near:
                for c in ((r[0], r[2]) if horiz else (r[1], r[3])):
                    if lo < c < hi:
                        cuts.add(c)
            cs = sorted(cuts)
            for a, b in zip(cs, cs[1:]):
                m = (a + b) / 2
                s1 = inside(near, m, k + eps) if horiz else inside(near, k + eps, m)
                s2 = inside(near, m, k - eps) if horiz else inside(near, k - eps, m)
                if s1 != s2:
                    pieces.add((horiz, k, a, b))
    out = []
    lines = collections.defaultdict(list)
    for horiz, k, a, b in pieces:
        lines[(horiz, k)].append((a, b))
    for (horiz, k), parts in lines.items():
        parts.sort()
        cur = list(parts[0])
        for a, b in parts[1:]:
            if a <= cur[1]:
                cur[1] = max(cur[1], b)
            else:
                out.append(((cur[0], k), (cur[1], k)) if horiz else ((k, cur[0]), (k, cur[1])))
                cur = [a, b]
        out.append(((cur[0], k), (cur[1], k)) if horiz else ((k, cur[0]), (k, cur[1])))
    return out


def ref_value(view, ref):
    """exact scalar of a reference (own implementation of the grammar in spec_e)."""
    if isinstance(ref, (int, float)):
        return Fraction(repr(float(ref))) if isinstance(ref, float) else Fraction(ref)
    head, anchor = ref.rsplit(":", 1)
    if head == "truc":
        g = next(e for e in view["elems"] if e["t"] == "truc")
        return next(v for t, v in g["dung"] + g["ngang"] if t == anchor)
    k = 0
    if "#" in head:
        head, ks = head.split("#")
        k = int(ks)
    e = next(x for x in view["elems"] if x.get("id") == head)
    if e["t"] == "tuong":
        a, d, n, length, lo, hi, _, _ = legs_of(e)[k]
        horiz = d[1] == 0
        if anchor in ("trai", "phai", "giua"):
            off = {"trai": hi, "phai": lo, "giua": Fraction(0)}[anchor]
            return a[1] + n[1] * off if horiz else a[0] + n[0] * off
        end = (a[0] + d[0] * length, a[1] + d[1] * length)
        p = a if anchor == "dau" else end
        return p[0] if horiz else p[1]
    if e["t"] in ("cua_di", "cua_so", "o_trong"):
        w = next(x for x in view["elems"] if x.get("id") == e["tuong"])
        a, d, n, length, lo, hi, _, _ = legs_of(w)[e["doan"]]
        t = e["vi_tri"] if anchor == "dau" else e["vi_tri"] + e["rong"]
        return a[0] + d[0] * t if d[1] == 0 else a[1] + d[1] * t
    if e["t"] == "phong":
        xs, ys = [p[0] for p in e["da_giac"]], [p[1] for p in e["da_giac"]]
        box = (min(xs), min(ys), max(xs), max(ys))
    elif e["t"] == "noi_that_co_ban":
        box = furn_box(e)
    elif e["t"] in ("tron", "cung"):
        c, r = e["tam"], e["ban_kinh"]
        box = (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
    else:
        box = e["box"]                      # rectangle-like phase 2 elements: bounding box measured from their own spec numbers
    return {"tay": box[0], "dong": box[2], "nam": box[1], "bac": box[3]}[anchor]


def furn_box(e):
    w, d, _ = FURN[e["kieu"]]
    w, d = (Fraction(e["w"]), Fraction(e["d"])) if e.get("w") else (Fraction(w), Fraction(d))
    if e["xoay"] in (90, 270):
        w, d = d, w
    x, y = e["vi_tri"]
    return (x, y, x + w, y + d)


def sqrt_half_up(v):
    d = (Decimal(v.numerator) / Decimal(v.denominator)).sqrt()
    return int((d + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR))


def area_text(poly):
    s = Fraction(0)
    for i in range(len(poly)):
        s += poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
    m2 = abs(s) / 2 / 1_000_000
    c = (Decimal(m2.numerator) / Decimal(m2.denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"DT: {c:f}".replace(".", ",") + " m²"


def expected(sp, s):
    """-> dict(shapes=[(family, layer, kind, data)], texts=[(layer, string)], extent, dim_texts=[(id, string)])  real mm."""
    view, P = sp["views"][0], sp["params"]
    sh, tx = [], []
    ov, gp, rb = P["truc_vuon_qua"] * s, P["khe_vong_truc"] * s, P["duong_kinh_vong_truc"] * s / 2
    by = {e["id"]: e for e in view["elems"] if e.get("id")}

    def seg(fam, layer, p, q):
        sh.append((fam, layer, "seg", ((F(p[0]), F(p[1])), (F(q[0]), F(q[1])))))

    g = next((e for e in view["elems"] if e["t"] == "truc"), None)
    if g:
        xs, ys = [F(v) for _, v in g["dung"]], [F(v) for _, v in g["ngang"]]
        for t, x in g["dung"]:
            seg("truc", "TRUC", (x, min(ys) - ov), (x, max(ys) + ov))
            sh.append(("truc", "TRUC-KYHIEU", "circ", ((F(x), max(ys) + ov + gp + rb), rb)))
            tx.append(("TRUC-KYHIEU", t))
        for t, y in g["ngang"]:
            seg("truc", "TRUC", (min(xs) - ov, y), (max(xs) + ov, y))
            sh.append(("truc", "TRUC-KYHIEU", "circ", ((min(xs) - ov - gp - rb, F(y)), rb)))
            tx.append(("TRUC-KYHIEU", t))
    for a, b in outline_edges(body_rects(view)):
        seg("tuong", "NET-CHINH", a, b)
    for w in (e for e in view["elems"] if e["t"] == "tuong" and e["kieu"] == "1_net"):
        ops = collections.defaultdict(list)
        for o in view["elems"]:
            if o["t"] in ("cua_di", "cua_so", "o_trong") and o["tuong"] == w["id"]:
                ops[o["doan"]].append((o["vi_tri"], o["vi_tri"] + o["rong"]))
        for k, (a, d, n, length, lo, hi, e0, e1) in enumerate(legs_of(w)):
            cur = -e0
            for v0, v1 in sorted(ops[k]) + [(length + e1, None)]:
                if v0 > cur:
                    seg("tuong", "NET-CHINH", (a[0] + d[0] * cur, a[1] + d[1] * cur), (a[0] + d[0] * v0, a[1] + d[1] * v0))
                cur = v1 if v1 is not None else cur
    for o in view["elems"]:
        if o["t"] not in ("cua_di", "cua_so"):
            continue
        w = by[o["tuong"]]
        a, d, n, length, lo, hi, _, _ = legs_of(w)[o["doan"]]
        P_ = lambda t, off: (a[0] + d[0] * t + n[0] * off, a[1] + d[1] * t + n[1] * off)
        v, r = o["vi_tri"], o["rong"]
        if o["t"] == "cua_so":
            for fr in ((Fraction(1, 3), Fraction(2, 3)) if o["ky_hieu"] == "kep" else (Fraction(0), Fraction(1, 2), Fraction(1))):
                seg("cua", "NET-MANH", P_(v, lo + fr * (hi - lo)), P_(v + r, lo + fr * (hi - lo)))
            continue
        for off in (lo, hi):
            seg("cua", "NET-MANH", P_(v, off), P_(v + r, off))
        th = v if o["ban_le"] == "dau" else v + r
        sw = 1 if o["mo_ve"] == "trai" else -1
        H = P_(th, hi if o["mo_ve"] == "trai" else lo)
        ns = (sw * n[0], sw * n[1])
        dc = d if o["ban_le"] == "dau" else (-d[0], -d[1])
        seg("cua", "NET-MANH", H, (H[0] + ns[0] * r, H[1] + ns[1] * r))
        a0, a1 = math.atan2(dc[1], dc[0]), math.atan2(ns[1], ns[0])
        dl = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        pts = [(F(H[0]) + F(r) * math.cos(a0 + dl * k / 24), F(H[1]) + F(r) * math.sin(a0 + dl * k / 24)) for k in range(25)]
        for p, q in zip(pts, pts[1:]):
            seg("cua", "NET-MANH", p, q)
    for e in view["elems"]:
        t = e["t"]
        if t == "noi_that_co_ban":
            b = furn_box(e)
            sh.append(("noi_that", "NET-MANH", "rect", tuple(F(v) for v in b)))
        elif t == "duong":
            seg("tho", e["lop"], e["tu"], e["den"])
        elif t == "polyline":
            p = e["diem"] + ([e["diem"][0]] if e["kin"] else [])
            for q, r_ in zip(p, p[1:]):
                seg("tho", e["lop"], q, r_)
        elif t == "tron":
            sh.append(("tho", e["lop"], "circ", ((F(e["tam"][0]), F(e["tam"][1])), F(e["ban_kinh"]))))
        elif t == "cung":
            sweep = (Fraction(e["goc_cuoi"]) - Fraction(e["goc_dau"])) % 360
            n = max(2, math.ceil(24 * F(sweep) / 90))
            a0 = math.radians(F(e["goc_dau"]))
            pts = [(F(e["tam"][0]) + F(e["ban_kinh"]) * math.cos(a0 + math.radians(F(sweep)) * k / n), F(e["tam"][1]) + F(e["ban_kinh"]) * math.sin(a0 + math.radians(F(sweep)) * k / n)) for k in range(n + 1)]
            for p, q in zip(pts, pts[1:]):
                seg("tho", e["lop"], p, q)
        elif t == "mui_ten_bac":
            R, c = P["ban_kinh_mui_ten_bac"] * s, (F(e["vi_tri"][0]), F(e["vi_tri"][1]))
            ph = math.radians(F(e["goc"]))
            u, pp = (-math.sin(ph), math.cos(ph)), (math.cos(ph), math.sin(ph))
            tip = (c[0] + u[0] * R * 0.9, c[1] + u[1] * R * 0.9)
            b1 = (c[0] - u[0] * R * 0.5 + pp[0] * R * 0.35, c[1] - u[1] * R * 0.5 + pp[1] * R * 0.35)
            b2 = (c[0] - u[0] * R * 0.5 - pp[0] * R * 0.35, c[1] - u[1] * R * 0.5 - pp[1] * R * 0.35)
            sh.append(("bac", "NET-MANH", "circ", (c, R)))
            for p, q in ((tip, b1), (tip, b2), (b1, b2)):
                seg("bac", "NET-MANH", p, q)
            tx.append(("CHU", "B"))
        elif t == "phong":
            tx.append(("CHU", e["ten"]))
            tx.append(("CHU", area_text(e["da_giac"])))
    for e in view["elems"]:
        if e["t"] == "noi_that_co_ban":
            tx.append(("CHU", FURN[e["kieu"]][2]))
        elif e["t"] == "ghi_chu":
            tx.extend(("CHU", ln) for ln in e["dong"])
        elif e["t"] == "chu":
            tx.append(("CHU", e["chu"]))
    verify_e2.add_expected(view, s, P, sh, tx)
    verify_e3.add_expected(view, s, P, sh, tx)
    # ---- extent of the geometry (what the dimensions are offset from)
    xs, ys = [], []
    for fam, layer, kind, d in sh:
        if fam == "bac":
            continue
        if kind == "seg":
            xs += [d[0][0], d[1][0]]
            ys += [d[0][1], d[1][1]]
        elif kind == "rect":
            xs += [d[0], d[2]]
            ys += [d[1], d[3]]
        else:
            xs += [d[0][0] - d[1], d[0][0] + d[1]]
            ys += [d[0][1] - d[1], d[0][1] + d[1]]
    ext = (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)
    dim_texts = dims_expected(view, ext, s, P, sh, by)
    tx.extend(("KICH-THUOC", t) for _, t in dim_texts)
    tx.append(("CHU", next((e["chu"] for e in view["elems"] if e["t"] == "tieu_de_hinh" and e["chu"]), view["ten"])))
    tx.append(("CHU", f"TỶ LỆ 1:{s}"))
    return dict(shapes=sh, texts=tx, extent=ext, dim_texts=dim_texts)


def dims_expected(view, ext, s, P, sh, by):
    exo, exe, asz = P["kt_exo"] * s, P["kt_exe"] * s, P["kt_mui_ten"] * s
    texts = []
    done_ext, done_tick = {}, set()

    def seg(p, q):
        sh.append(("kich_thuoc", "KICH-THUOC", "seg", ((F(p[0]), F(p[1])), (F(q[0]), F(q[1])))))

    def tick(c, key):
        if key not in done_tick:
            done_tick.add(key)
            seg((c[0] - asz / 2, c[1] - asz / 2), (c[0] + asz / 2, c[1] + asz / 2))

    dims = [e for e in view["elems"] if e["t"] == "kich_thuoc"]
    for e in sorted((q for q in dims if q["kieu"] in ("ngang", "doc", "chuoi")), key=lambda q: (q["lop"], q["idx"])):
        horiz = e["huong"] == "ngang"
        vals = [ref_value(view, r) for r in e["tham_chieu"]]
        if e["kieu"] != "chuoi":
            vals.sort()
        off = (P["kt_dau_tien"] + (e["lop"] - 1) * P["kt_giua_cac_duong"]) * s
        low = e["phia"] in ("duoi", "trai")
        edge = (ext[1] if horiz else ext[0]) if low else (ext[3] if horiz else ext[2])
        ly = edge - off if low else edge + off
        sgn = -1.0 if low else 1.0
        for a, b in (list(zip(vals, vals[1:])) if e["kieu"] == "chuoi" else [tuple(vals)]):
            a, b = min(a, b), max(a, b)
            for v in (a, b):
                key = (horiz, e["phia"], v)
                end = ly + sgn * exe
                if key not in done_ext or (end - done_ext[key]) * sgn > 1e-9:
                    st = done_ext.get(key, edge + sgn * exo)
                    seg((F(v), st), (F(v), end)) if horiz else seg((st, F(v)), (end, F(v)))
                    done_ext[key] = end
                tick((F(v), ly) if horiz else (ly, F(v)), (horiz, ly, v))
            seg((F(a), ly), (F(b), ly)) if horiz else seg((ly, F(a)), (ly, F(b)))
            texts.append((e["id"], str(math.floor(b - a + Fraction(1, 2)))))
    for e in dims:
        k = e["kieu"]
        if k == "song_song":
            (x1, y1), (x2, y2) = [(F(p[0]), F(p[1])) for p in e["p"]]
            L = math.hypot(x2 - x1, y2 - y1)
            u = ((x2 - x1) / L, (y2 - y1) / L)
            nl = (-u[1], u[0]) if e["phia"] == "trai" else (u[1], -u[0])
            off = F(e["khoang"]) * s
            q1, q2 = (x1 + nl[0] * off, y1 + nl[1] * off), (x2 + nl[0] * off, y2 + nl[1] * off)
            for p, q in (((x1, y1), q1), ((x2, y2), q2)):
                seg((p[0] + nl[0] * exo, p[1] + nl[1] * exo), (q[0] + nl[0] * exe, q[1] + nl[1] * exe))
            seg(q1, q2)
            tk = asz / 2
            for q in (q1, q2):
                seg((q[0] - tk * (u[0] - u[1]), q[1] - tk * (u[1] + u[0])), (q[0] + tk * (u[0] - u[1]), q[1] + tk * (u[1] + u[0])))
            texts.append((e["id"], str(sqrt_half_up((Fraction(e["p"][1][0]) - Fraction(e["p"][0][0])) ** 2 + (Fraction(e["p"][1][1]) - Fraction(e["p"][0][1])) ** 2))))
        elif k in ("ban_kinh", "duong_kinh"):
            c = by[e["phan_tu"]]
            cx, cy, r = F(c["tam"][0]), F(c["tam"][1]), F(c["ban_kinh"])
            th = math.radians(F(e["goc"]))
            dx, dy = math.cos(th), math.sin(th)
            Q = (cx + r * dx, cy + r * dy)
            Eo = (cx + (r + 12.0 * s) * dx, cy + (r + 12.0 * s) * dy)
            st = Q if k == "ban_kinh" else (cx - r * dx, cy - r * dy)
            seg(st, Eo)
            tick(Q, ("c", e["id"], 0))
            if k == "duong_kinh":
                tick(st, ("c", e["id"], 1))
            val = Fraction(c["ban_kinh"]) * (1 if k == "ban_kinh" else 2)
            texts.append((e["id"], ("R" if k == "ban_kinh" else "Ø") + str(math.floor(val + Fraction(1, 2)))))
        elif k == "goc":
            (vx, vy), (ax, ay), (bx, by_) = [(F(e[n][0]), F(e[n][1])) for n in ("dinh", "tia1", "tia2")]
            a1, a2 = math.atan2(ay - vy, ax - vx), math.atan2(by_ - vy, bx - vx)
            dl = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
            R = F(e["ban_kinh_cung"]) * s
            n = max(2, math.ceil(24 * abs(math.degrees(dl)) / 90))
            pts = [(vx + R * math.cos(a1 + dl * j / n), vy + R * math.sin(a1 + dl * j / n)) for j in range(n + 1)]
            for p, q in zip(pts, pts[1:]):
                seg(p, q)
            for p in (pts[0], pts[-1]):
                tick(p, ("g", e["id"], round(p[0], 6), round(p[1], 6)))
            deg = Decimal(repr(abs(math.degrees(dl)))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            texts.append((e["id"], f"{deg:f}".replace(".", ",") + "°"))
    return texts


# ------------------------------------------------------------------ matching
def drawn_shapes(D):
    s, (ox, oy) = D.scale, D.origin
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    out = []
    for p in D.prims:
        if p.sheet:
            continue
        if isinstance(p, Line):
            out.append((p.tag, p.layer, "seg", (R(p.p1), R(p.p2))))
        elif isinstance(p, Rect):
            a, b = R(p.p0), R(p.p1)
            out.append((p.tag, p.layer, "rect", (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))))
        elif isinstance(p, Circle):
            out.append((p.tag, p.layer, "circ", (R(p.c), p.r * s)))
    return out


def same(kind, a, b, tol):
    if kind == "seg":
        return all(close(a[i][j], b[i][j], tol) for i in (0, 1) for j in (0, 1)) or all(close(a[i][j], b[1 - i][j], tol) for i in (0, 1) for j in (0, 1))
    if kind == "rect":
        return all(close(x, y, tol) for x, y in zip(a, b))
    return close(a[0][0], b[0][0], tol) and close(a[0][1], b[0][1], tol) and close(a[1], b[1], tol)


def two_way(exp, got, tol):
    """exp = [(family, layer, kind, data)], got = [(label, layer, kind, data)]. -> (unmatched expected, unmatched got)."""
    pool = collections.defaultdict(list)
    for i, (lab, layer, kind, d) in enumerate(got):
        pool[(layer, kind)].append(i)
    used, miss = set(), []
    for fam, layer, kind, d in exp:
        for i in pool[(layer, kind)]:
            if i not in used and same(kind, d, got[i][3], tol):
                used.add(i)
                break
        else:
            miss.append((fam, layer, kind))
    extra = [got[i][0] for i in range(len(got)) if i not in used]
    return miss, extra


def family_id(tag):
    for pre, cid in FAMILY_OF_TAG:
        if tag.startswith(pre):
            return cid
    return None


EXP_FAMILY = {"kyhieu": "1.73", "ong": "1.74", "legend": "1.76", "hatch": "1.63", "kc": "1.64", "dung": "1.65", "dau": "1.66", "truc": "1.50", "tuong": "1.51", "cua": "1.52", "noi_that": "1.53", "tho": "1.53", "bac": "1.53", "kich_thuoc": "1.54"}
NAMES = {"1.73": "ký hiệu điện / nước (ổ cắm, công tắc, đèn, quạt, bảng điện, bồn cầu, chậu rửa, vòi, van, đồng hồ): đúng hình, kích thước cố định trên giấy, vị trí và chiều xoay", "1.74": "đường dây điện, ống cấp, ống thoát và nút nối: đúng toạ độ, đúng layer theo loại (NET-TAM, NET-CHINH, NET-KHUAT)", "1.76": "chú giải tự sinh: ký hiệu và nét mẫu đúng vị trí (và chữ ở 1.55, thứ tự ở 1.76 đo riêng)", "1.63": "hatch vật liệu: đúng mẫu (góc, khoảng cách, mốc theo gốc toạ độ) và đúng đoạn cắt theo hình chữ nhật của lớp (hai chiều)", "1.64": "lớp vật liệu / sàn / dầm / cột / móng / cột chi tiết: hình chữ nhật, thép đai và tròn thép đúng vị trí, kích thước",
         "1.65": "cửa đứng, mái (bằng, 1 mái, 2 mái, độ dốc, bề dày), lan can, bậc thang đúng toạ độ", "1.66": "cao độ, đường dẫn ghi chú, dấu cắt, tuyến gió đúng vị trí và đúng số lượng nét", "1.50": "lưới trục + vòng ký hiệu (vị trí, độ dài trục, tâm vòng)", "1.51": "đường bao tường = biên của hợp các thân tường (cắt bởi cửa), chiều hai chiều", "1.52": "ký hiệu cửa đi (khung, cánh, cung mở) và cửa sổ đúng vị trí, nằm trọn trong tường",
         "1.53": "nội thất, phần tử thô (đường, polyline, cung, tròn) và mũi tên bắc", "1.54": "kích thước đo từ tham chiếu (đường, gióng, mũi tên đúng toạ độ và đúng giá trị)"}


# ------------------------------------------------------------------ text rules
def segs_for_texts(D):
    """obstacle lines/circles of the drawn primitives in paper mm: (tag, kind, data)."""
    out = []
    for p in D.prims:
        if p.sheet:
            continue
        if isinstance(p, Line):
            out.append((p.tag, "seg", (p.p1, p.p2)))
        elif isinstance(p, Rect):
            x0, y0, x1, y1 = p.p0[0], p.p0[1], p.p1[0], p.p1[1]
            for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                out.append((p.tag, "seg", (a, b)))
        elif isinstance(p, Circle):
            out.append((p.tag, "circ", (p.c, p.r)))
    return out


def crossing_findings(boxes, obstacles, margin, own):
    """boxes = [(text, tag, box)]; obstacles = [(tag, kind, data)]; own(tag_text, tag_obstacle) -> True when the obstacle belongs to the text itself. -> (list of crossings, smallest gap)."""
    bad, best = [], 1e9
    for txt, ttag, box in boxes:
        for otag, kind, data in obstacles:
            if own(ttag, otag):
                continue
            if kind == "seg":
                g = _seg_rect_gap(data[0], data[1], box)
            else:
                (cx, cy), r = data
                dx, dy = max(box[0] - cx, 0.0, cx - box[2]), max(box[1] - cy, 0.0, cy - box[3])
                dmax = max(math.hypot(x - cx, y - cy) for x in (box[0], box[2]) for y in (box[1], box[3]))
                dmin = math.hypot(dx, dy)
                g = 0.0 if dmin <= r <= dmax else (dmin - r if dmin > r else r - dmax)
            best = min(best, g)
            if g < margin:
                bad.append((txt, otag))
    return bad, best


def overlap_findings(boxes, margin=0.0):
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][2], boxes[j][2]
            if a[0] - margin < b[2] and b[0] - margin < a[2] and a[1] - margin < b[3] and b[1] - margin < a[3]:
                bad.append((boxes[i][0], boxes[j][0]))
    return bad


def own_dim(ttag, otag):
    """a dimension / level / leader / section-marker text may touch the lines of its OWN element (adjacent by construction)."""
    tp, op = ttag.split(":"), otag.split(":")
    pairs = {"dim": "dim", "leader_text": "leader", "cut_text": "cut_arm", "lv_text": "lv"}
    return tp[0] in pairs and op[0] == pairs[tp[0]] and len(tp) > 1 and len(op) > 1 and tp[1] == op[1]


# ------------------------------------------------------------------ 1. primitives
def check_primitives_e(C: Checks, D, sp):
    s, P = D.scale, D.info["params"]
    view = sp["views"][0]
    X = expected(sp, s)
    got = drawn_shapes(D)
    miss, extra_tags = two_way(X["shapes"], got, TOL)
    extras = collections.defaultdict(list)
    used_labels = [g[0] for g in got]
    # the 'extra' labels are tags of drawn shapes without an expected partner
    for t in extra_tags:
        extras[family_id(t) or "?"].append(t)
    by_fam = collections.defaultdict(list)
    for fam, layer, kind in miss:
        by_fam[EXP_FAMILY[fam]].append(f"{fam}/{layer}/{kind}")
    counts = collections.Counter(EXP_FAMILY[x[0]] for x in X["shapes"])
    for cid in ("1.50", "1.51", "1.52", "1.53", "1.54", "1.63", "1.64", "1.65", "1.66", "1.73", "1.74", "1.76"):
        C.add(1, cid, NAMES[cid], not by_fam[cid] and not extras[cid] and not extras["?"],
              f"{counts[cid]} nét/hình mong đợi; thiếu {len(by_fam[cid])} {by_fam[cid][:2]}; thừa {len(extras[cid])} {extras[cid][:3]}" + (f"; thừa không rõ nguồn {extras['?'][:3]}" if extras["?"] and cid == "1.50" else ""))
    verify_e2.check_phase2(C, D, sp)
    verify_e3.check_phase3(C, D, sp)
    # ---- texts: strings
    want = collections.Counter(X["texts"])
    drawn = [t for t in D.prims if isinstance(t, Text) and not t.sheet]
    gotc = collections.Counter((t.layer, t.s) for t in drawn)
    C.add(1, "1.55", "chữ trên bản vẽ: đúng tập chuỗi và lớp (tên trục, nhãn phòng + diện tích tính bằng công thức shoelace, nhãn nội thất, ghi chú, chữ thô, nhãn kích thước đo từ tham chiếu, tên hình, tỷ lệ)",
          want == gotc, f"{sum(gotc.values())} chuỗi; thiếu {list((want - gotc).elements())[:3]}; thừa {list((gotc - want).elements())[:3]}")
    # ---- rooms: label inside its room
    room_ok, room_det = True, []
    for e in (q for q in view["elems"] if q["t"] == "phong"):
        for string in (e["ten"], area_text(e["da_giac"])):          # two rooms may print the same area: it is enough that one such text lies inside this room
            ins = [point_in(e["da_giac"], Fraction((t.pos[0] - D.origin[0]) * s).limit_denominator(10 ** 6), Fraction((t.pos[1] - D.origin[1]) * s).limit_denominator(10 ** 6)) for t in drawn if t.s == string]
            if not any(ins):
                room_ok = False
                room_det.append(f"{e['id']}:{string}")
    # ---- text boxes vs lines / other texts
    boxes = text_boxes_paper(drawn)
    obst = segs_for_texts(D)
    bad, best = crossing_findings(boxes, obst, TEXT_MARGIN, own_dim)
    C.add(1, "1.56", f"không chuỗi chữ nào có hộp bao (độ rộng Arial thật) cắt hoặc chạm (≤ {TEXT_MARGIN:g} mm giấy) một nét hay vòng tròn của bản vẽ (tường, trục, cửa, nội thất, kích thước khác); nhãn phòng nằm trong phòng",
          not bad and room_ok and bool(boxes), f"{len(boxes)} chuỗi, {len(obst)} nét/vòng; cắt/chạm: {bad[:3]}; khoảng cách nhỏ nhất {best if best < 1e8 else 'không có'} mm; nhãn phòng ngoài phòng: {room_det}")
    ov = overlap_findings(boxes)
    C.add(1, "1.57", "không hai chuỗi chữ nào có hộp bao chồng nhau", not ov, f"chồng nhau: {ov[:3]}")
    # ---- layers, elements, duplicates
    layers_ok = all(p.layer in P.get("_layers", ALLOWED_LAYERS) for p in D.prims if not p.sheet)
    text_layers_ok = all(t.layer in ("CHU", "TRUC-KYHIEU", "KICH-THUOC") for t in drawn)
    dup = [k for k, v in collections.Counter((p.layer, round(p.p1[0], 6), round(p.p1[1], 6), round(p.p2[0], 6), round(p.p2[1], 6)) for p in D.prims if isinstance(p, Line) and not p.sheet).items() if v > 1]
    zero = [p.tag for p in D.prims if isinstance(p, Line) and not p.sheet and math.hypot(p.p2[0] - p.p1[0], p.p2[1] - p.p1[1]) < 1e-9]
    n_el = sum(len(v["elems"]) for v in sp["views"])
    C.add(1, "1.58", "lớp hợp lệ (trong profile, chữ chỉ ở CHU / TRUC-KYHIEU / KICH-THUOC), không nét trùng lặp, không nét dài 0, số phần tử ≤ 2000 và khớp báo cáo",
          layers_ok and text_layers_ok and not dup and not zero and n_el <= 2000 and D.info.get("n_elements") == n_el, f"lớp {layers_ok}/{text_layers_ok}; trùng {len(dup)}; dài 0 {len(zero)}; phần tử {n_el} (báo cáo {D.info.get('n_elements')})")
    # ---- layout
    sh = SHEETS[D.sheet]
    inside_ok, tb_clear, rot_ok = True, True, True
    for p in D.prims:
        if p.sheet:
            continue
        bb = prim_bbox(p)
        inside_ok &= bb[0] >= sh.x0 + MARGIN - 1e-6 and bb[2] <= sh.x1 - MARGIN + 1e-6 and bb[1] >= sh.y0 + MARGIN - 1e-6 and bb[3] <= sh.y1 - MARGIN + 1e-6
        tb_clear &= bb[2] <= sh.tb_x0 - MARGIN + 1e-6 or bb[1] >= sh.tb_y1 + MARGIN - 1e-6
    C.add(1, "1.59", "bố cục: mọi nét/chữ trong khung (cách mép ≥ 5 mm) và cách khung tên 180×65 ≥ 5 mm", inside_ok and tb_clear, f"trong khung {inside_ok}; cách khung tên {tb_clear}")
    check_policy_e(C, D, sp)
    # ---- warnings
    w_exp = []
    for e in view["elems"]:
        if e["t"] == "cua_di" and e["rong"] < 700:
            w_exp.append(e["id"])
        if e["t"] == "tuong" and not (100 <= e["day"] <= 500):
            w_exp.append(e["id"])
    got_w = D.info.get("warnings", [])
    w_exp += verify_e2.soft_warning_ids(view)
    pairs = [(f["id"], d["id"]) for f in view["elems"] if f["t"] == "noi_that_co_ban" for d in view["elems"] if d["t"] == "cua_di" and sweep_hit(view, d, furn_box(f))]
    soft = [w for w in got_w if "vùng quét của cánh cửa" in w]
    ok_pairs = len(soft) == len(pairs) and all(any(f"{a!r}" in w and f"{b!r}" in w for w in soft) for a, b in pairs)
    got_w = [w for w in got_w if "vùng quét của cánh cửa" not in w]
    lv_exp = verify_e2.level_warning_idx(view)
    lv = [w for w in got_w if "ký hiệu cao độ" in w]
    ok_lv = len(lv) == len(lv_exp) and all(any(f"phan_tu[{i}]" in w for w in lv) for i in lv_exp) and all("KHÔNG phải điều khoản TCVN" in w for w in lv)
    got_w = [w for w in got_w if "ký hiệu cao độ" not in w]
    ok_w = ok_pairs and ok_lv and len(got_w) == len(w_exp) and all(any(f"{i!r}" in w or f"id={i!r}" in w for w in got_w) for i in w_exp) and all("KHÔNG phải điều khoản TCVN" in w for w in got_w)
    C.add(1, "1.61", "cảnh báo mềm (cửa đi hẹp hơn 700 mm, tường dày ngoài 100-500 mm, lan can/bậc thang ngoài khoảng thường dùng: kinh nghiệm thực tế, không phải điều khoản TCVN; nội thất nằm trong vùng quét của cánh cửa đi; ký hiệu cao độ không trùng mốc nào của hình): đúng phần tử, không thừa không thiếu", ok_w,
          f"cần {w_exp}; nội thất-cửa {pairs}; cao độ lệch mốc {lv_exp}; có {len(got_w)} cảnh báo + {len(soft)} cảnh báo vùng quét + {len(lv)} cảnh báo cao độ")
    check_centering(C, D)
    check_leaders(C, D)
    check_bubbles(C, D)
    check_expressions(C, [t.s for t in drawn], 1, "1.62", "chữ trên bản vẽ")
    check_room_name_height(C, D)


def sweep_hit(view, door, box):
    """Own test (global axes): does the rectangle meet the quarter disc swept by the door leaf? The disc lies in the quadrant spanned by the closed direction and the swing normal."""
    w = next(x for x in view["elems"] if x.get("id") == door["tuong"])
    a, d, n, length, lo, hi, _, _ = legs_of(w)[door["doan"]]
    v, r = door["vi_tri"], door["rong"]
    t = v if door["ban_le"] == "dau" else v + r
    off = hi if door["mo_ve"] == "trai" else lo
    hx, hy = a[0] + d[0] * t + n[0] * off, a[1] + d[1] * t + n[1] * off
    sgn = 1 if door["mo_ve"] == "trai" else -1
    closed = d if door["ban_le"] == "dau" else (-d[0], -d[1])
    sx, sy = closed[0] + sgn * n[0], closed[1] + sgn * n[1]
    x0, x1 = (max(box[0], hx), box[2]) if sx > 0 else (box[0], min(box[2], hx))
    y0, y1 = (max(box[1], hy), box[3]) if sy > 0 else (box[1], min(box[3], hy))
    if x0 >= x1 or y0 >= y1:
        return False
    px, py = min(max(hx, x0), x1), min(max(hy, y0), y1)
    return (px - hx) ** 2 + (py - hy) ** 2 < r * r


def check_centering(C, D):
    """1.70: the drawing (all non-sheet primitives, text boxes estimated) is centred in the band it fits: the band above the title block, else the band left of it."""
    sh = SHEETS[D.sheet]
    bbs = [prim_bbox(p) for p in D.prims if not p.sheet]
    x0, y0, x1, y1 = min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs)
    w, h = x1 - x0 + 2 * MARGIN, y1 - y0 + 2 * MARGIN
    if w <= sh.frame_w and h <= sh.frame_h - sh.tb_h:
        reg = (sh.x0, sh.tb_y1, sh.x1, sh.y1)
    elif w <= sh.frame_w - sh.tb_w and h <= sh.frame_h:
        reg = (sh.x0, sh.y0, sh.tb_x0, sh.y1)
    else:
        reg = None
    dx = dy = None
    if reg:
        dx, dy = (x0 + x1) / 2 - (reg[0] + reg[2]) / 2, (y0 + y1) / 2 - (reg[1] + reg[3]) / 2
    C.add(1, "1.70", "hình căn giữa trong vùng vẽ (dải trên khung tên, hoặc dải trái khung tên khi không vừa dải trên), sai số ≤ 0,2 mm giấy", reg is not None and abs(dx) <= 0.2 and abs(dy) <= 0.2,
          "không vừa dải nào" if reg is None else f"lệch tâm ({dx:.3f}, {dy:.3f}) mm; vùng {tuple(round(v, 1) for v in reg)}")


def _inter(p, q, a, b):
    """touching / crossing point of segments pq and ab by Cramer's rule, None when they miss (parallel ones are ignored)."""
    r1, r2 = q[0] - p[0], q[1] - p[1]
    s1, s2 = b[0] - a[0], b[1] - a[1]
    den = r1 * s2 - r2 * s1
    if abs(den) < 1e-12:
        return None
    t = ((a[0] - p[0]) * s2 - (a[1] - p[1]) * s1) / den
    u = ((a[0] - p[0]) * r2 - (a[1] - p[1]) * r1) / den
    return (p[0] + t * r1, p[1] + t * r2) if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9 else None


def check_leaders(C, D):
    """1.71: no leader line (ghi_chu_dan) crosses another line, rectangle edge or circle except hatch; it may end ON the line it points at (within 0.3 mm of its arrow tick centre)."""
    leaders = [p for p in D.prims if isinstance(p, Line) and p.tag.startswith("leader:") and not p.tag.endswith(":tick")]
    bad = []
    for ld in leaders:
        key = ld.tag.split(":")[1]
        tick = next((t for t in D.prims if isinstance(t, Line) and t.tag == f"leader:{key}:tick"), None)
        tip = ((tick.p1[0] + tick.p2[0]) / 2, (tick.p1[1] + tick.p2[1]) / 2) if tick else ld.p1
        for p in D.prims:
            if p.sheet or p.tag.startswith(("hatch:", f"leader:{key}")):
                continue
            segs = [(p.p1, p.p2)] if isinstance(p, Line) else ([((p.p0[0], p.p0[1]), (p.p1[0], p.p0[1])), ((p.p1[0], p.p0[1]), (p.p1[0], p.p1[1])), ((p.p1[0], p.p1[1]), (p.p0[0], p.p1[1])), ((p.p0[0], p.p1[1]), (p.p0[0], p.p0[1]))] if isinstance(p, Rect) else [])
            for a, b in segs:
                x = _inter(ld.p1, ld.p2, a, b)
                if x is not None and math.hypot(x[0] - tip[0], x[1] - tip[1]) > 0.3:
                    bad.append((key, p.tag))
            if isinstance(p, Circle):
                da, db = math.hypot(ld.p1[0] - p.c[0], ld.p1[1] - p.c[1]), math.hypot(ld.p2[0] - p.c[0], ld.p2[1] - p.c[1])
                if min(da, db) < p.r < max(da, db):
                    bad.append((key, p.tag))
    C.add(1, "1.71", "đường dẫn ghi chú (ghi_chu_dan) không cắt qua nét, cạnh hình chữ nhật hay vòng tròn khác (trừ hatch); đầu mũi tên được nằm trên nét cần chỉ", not bad, f"{len(leaders)} đường dẫn; cắt: {bad[:3]}")


def check_bubbles(C, D):
    """1.72: no grid / wind-axis bubble touches (≤ 0.3 mm) another line, rectangle, circle or text (its own text excluded)."""
    circles = [p for p in D.prims if isinstance(p, Circle) and p.layer == "TRUC-KYHIEU" and not p.sheet]
    texts = text_boxes_paper([t for t in D.prims if isinstance(t, Text) and not t.sheet])
    bad = []
    for c in circles:
        for p in D.prims:
            if p is c or p.sheet:
                continue
            segs = [(p.p1, p.p2)] if isinstance(p, Line) else ([((p.p0[0], p.p0[1]), (p.p1[0], p.p0[1])), ((p.p1[0], p.p0[1]), (p.p1[0], p.p1[1])), ((p.p1[0], p.p1[1]), (p.p0[0], p.p1[1])), ((p.p0[0], p.p1[1]), (p.p0[0], p.p0[1]))] if isinstance(p, Rect) else [])
            for a, b in segs:
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy
                t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((c.c[0] - a[0]) * dx + (c.c[1] - a[1]) * dy) / L2))
                if math.hypot(c.c[0] - (a[0] + t * dx), c.c[1] - (a[1] + t * dy)) < c.r + TEXT_MARGIN:
                    bad.append((p.tag, "nét"))
            if isinstance(p, Circle) and math.hypot(p.c[0] - c.c[0], p.c[1] - c.c[1]) < p.r + c.r + TEXT_MARGIN:
                bad.append((p.tag, "vòng"))
        for txt, tag, box in texts:
            if box[0] <= c.c[0] <= box[2] and box[1] <= c.c[1] <= box[3]:
                continue
            cx, cy = c.c
            dmin = math.hypot(max(box[0] - cx, 0.0, cx - box[2]), max(box[1] - cy, 0.0, cy - box[3]))
            if dmin < c.r + TEXT_MARGIN:
                bad.append((tag, "chữ"))
    C.add(1, "1.72", "vòng ký hiệu trục lưới và tuyến gió không chồng hoặc chạm (≤ 0,3 mm giấy) nét, hình chữ nhật, vòng tròn hay chữ khác", not bad, f"{len(circles)} vòng; chạm: {bad[:3]}")


ALLOWED_LAYERS = ("TRUC", "TRUC-KYHIEU", "NET-CHINH", "NET-MANH", "NET-KHUAT", "NET-TAM", "KICH-THUOC", "CHU", "KHUNG-TEN", "MAT-CAT")


def text_boxes_paper(drawn):
    out = []
    for t in drawn:
        w = _real_width(t.s, t.bold, t.h / ARIAL_CAP, t.wf)
        off = {"left": 0.0, "center": w / 2, "right": w}[t.halign]
        c, sn = math.cos(math.radians(t.rot)), math.sin(math.radians(t.rot))
        out.append((t.s, t.tag, _box(t.pos[0] - off * c, t.pos[1] - off * sn, w, t.h, t.rot)))
    return out


def point_in(poly, x, y):
    ins = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (x2 - x1) * (y - y1) == (y2 - y1) * (x - x1) and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
            return True
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            ins = not ins
    return ins


def check_policy_e(C, D, sp):
    import build_e
    from scale import place_rects, sheet_scale_candidates
    P = D.info["params"]
    kho = sp["kho_giay"]
    want = sp["scale"] or sp["views"][0]["scale"]
    cands = sheet_scale_candidates(want, None if kho == "auto" else kho, limit=SCALE_LIMIT, scales=AUTO)
    why, found = [], False
    for sh_, sc in cands:
        if (sh_, sc) == (D.sheet, D.scale):
            found = True
            break
        try:
            prims, _ = build_e.layout(sp, sc)
        except build_e.Unplaceable:
            continue
        if place_rects([build_e._extent(prims)], P["khe_vung_ve"], SHEETS[sh_]) is not None:
            why.append(f"{sh_} 1:{sc} vẫn vừa")
    C.add(1, "1.60", "khổ giấy + tỷ lệ theo quy tắc: ưu tiên A3, lên A2 rồi A1 chỉ khi khổ nhỏ hơn không vừa ở tỷ lệ ≤ 1:200; tỷ lệ lớn nhất còn vừa; khớp ty_le/kho_giay do người dùng chọn; đo: vừa cặp đã chọn, suy luận: các cặp đứng trước không vừa (dùng lại hàm bố cục)",
          found and not why and (not want or D.scale == want) and (kho == "auto" or D.sheet == kho), f"chọn {D.sheet} 1:{D.scale}; cặp đứng trước vẫn vừa: {why[:3]}")


# ------------------------------------------------------------------ room-name height (only for drawings whose room names were lowered below the default)
ROOM_NAME_MIN = 2.5                                # mm paper: the smallest standard text height; a lowered room name never goes under it


def room_name_lowered(D):
    """True when a room name is drawn lower than the default height `cao_chu_ten_phong` (measured from the primitives) or the builder reported it. Only then 1.78 / 2.38 / 3.27 run,
    so a drawing without lowered labels keeps its old list of checks."""
    P = D.info["params"]
    return bool(D.info.get("nhan_ha_co")) or any(t.h < P["cao_chu_ten_phong"] - 1e-9 for t in D.prims if isinstance(t, Text) and not t.sheet and t.tag.startswith("room_name:"))


def check_room_name_height(C, D):
    if not room_name_lowered(D):
        return
    P = D.info["params"]
    got = {t.tag.split(":", 1)[1]: t.h for t in D.prims if isinstance(t, Text) and not t.sheet and t.tag.startswith("room_name:")}
    rec = {r["id"]: r for r in D.info.get("nhan_ha_co", []) if r["loai"] == "ten_phong"}
    low = [i for i, h in got.items() if h < ROOM_NAME_MIN - 1e-6]
    unreported = [i for i, h in got.items() if h < P["cao_chu_ten_phong"] - 1e-9 and (i not in rec or abs(rec[i]["cao_moi"] - h) > 1e-9)]
    stale = [i for i, r in rec.items() if i not in got or abs(got[i] - r["cao_moi"]) > 1e-9]
    C.add(1, "1.78", f"tên phòng không bao giờ nhỏ hơn {ROOM_NAME_MIN:g} mm giấy (đo từ chữ đã vẽ); mỗi tên phòng hạ cỡ đều có ghi nhận (nhan_ha_co) đúng cỡ mới, không ghi nhận thừa",
          not low and not unreported and not stale and bool(got), f"{len(got)} tên phòng; cỡ nhỏ nhất {min(got.values()) if got else 'không có'} mm; dưới {ROOM_NAME_MIN:g}: {low}; hạ cỡ không ghi nhận: {unreported}; ghi nhận sai: {stale}")


def dxf_room_name_height(C, D, sp, dx, group, cid, where):
    """Height (paper mm = TEXT code 40 / scale) of the room name TEXT standing inside its room: at least one per room must be >= ROOM_NAME_MIN (a furniture label may share the string)."""
    if not room_name_lowered(D):
        return
    from readers import unesc
    s = D.scale
    best, bad = {}, []
    for e in dx["ents"]:
        if e["type"] != "TEXT":
            continue
        r = e["rec"]
        try:
            txt = unesc("".join(r.get(3, [])) + (r.get(1) or [""])[0])
            h, wf = f(r, 40), (f(r, 41) if 41 in r else 1.0)
            ax, ay = f(r, 10) + _real_width(txt, False, h / ARIAL_CAP, wf) / 2, f(r, 20)
        except (KeyError, ValueError, IndexError):
            continue
        for q in sp["views"][0]["elems"]:
            if q["t"] == "phong" and q["ten"] == txt and point_in(q["da_giac"], Fraction(ax).limit_denominator(10 ** 6), Fraction(ay).limit_denominator(10 ** 6)):
                best[q["id"]] = max(best.get(q["id"], 0.0), h / s)
    rooms = [q["id"] for q in sp["views"][0]["elems"] if q["t"] == "phong"]
    bad = [f"{i}:{best.get(i, 0.0):.3f}" for i in rooms if best.get(i, 0.0) < ROOM_NAME_MIN - 1e-3]
    C.add(group, cid, f"{where}: tên phòng (TEXT trong đa giác phòng) cao ≥ {ROOM_NAME_MIN:g} mm giấy (mã 40 chia tỷ lệ)", not bad and bool(rooms), f"phòng dưới {ROOM_NAME_MIN:g} mm hoặc không có chữ: {bad[:4]}")


# ------------------------------------------------------------------ 2/3. DXF and DWG read back
def in_title_block(D, kind, d):
    """True when a DXF shape lies inside the title block (its dividers are drawn on NET-MANH): converted to sheet mm with the origin and scale of the drawing."""
    sh, s, (ox, oy) = SHEETS[D.sheet], D.scale, D.origin
    pts = list(d) if kind == "seg" else ([(d[0], d[1]), (d[2], d[3])] if kind == "rect" else [d[0]])
    return all(sh.tb_x0 - 0.01 <= x / s + ox <= sh.tb_x1 + 0.01 and sh.tb_y0 - 0.01 <= y / s + oy <= sh.tb_y1 + 0.01 for x, y in pts)


def dxf_shapes(dx):
    out = []
    for e in dx["ents"]:
        r = e["rec"]
        try:
            if e["type"] == "LINE":
                out.append(("dxf", e["layer"], "seg", ((f(r, 10), f(r, 20)), (f(r, 11), f(r, 21)))))
            elif e["type"] == "CIRCLE":
                out.append(("dxf", e["layer"], "circ", ((f(r, 10), f(r, 20)), f(r, 40))))
            elif e["type"] == "LWPOLYLINE":
                xs, ys = [float(v) for v in r[10]], [float(v) for v in r[20]]
                out.append(("dxf", e["layer"], "rect", (min(xs), min(ys), max(xs), max(ys))))
        except (KeyError, ValueError, IndexError):
            pass
    return out


def dxf_checks(C, D, sp, dx, group, ids, where):
    X = expected(sp, D.scale)
    got = [(f"{l}/{k}", l, k, d) for _, l, k, d in dxf_shapes(dx) if l not in ("KHUNG-TEN",) and not in_title_block(D, k, d)]
    miss, extra = two_way([x for x in X["shapes"]], got, TOL_DXF)
    walls_m = [m for m in miss if m[1] == "NET-CHINH"]
    walls_x = [x for x in extra if x.startswith("NET-CHINH")]
    C.add(group, ids[0], f"{where}: đường bao tường (lớp NET-CHINH) khớp hai chiều với đường bao tính từ spec (mm thật, ±0,001)", not walls_m and not walls_x, f"thiếu {len(walls_m)}; thừa {len(walls_x)} {walls_x[:2]}")
    hat_m = [m for m in miss if m[1] == "MAT-CAT"]
    hat_x = [x for x in extra if x.startswith("MAT-CAT")]
    C.add(group, ids[4], f"{where}: hatch vật liệu (lớp MAT-CAT) khớp hai chiều với hatch tính từ spec (mẫu, khoảng cách, đoạn cắt theo hình chữ nhật)", not hat_m and not hat_x, f"thiếu {len(hat_m)}; thừa {len(hat_x)}")
    rest_m = [m for m in miss if m[1] not in ("NET-CHINH", "MAT-CAT")]
    rest_x = [x for x in extra if not x.startswith(("NET-CHINH", "MAT-CAT"))]
    C.add(group, ids[1], f"{where}: trục, ký hiệu cửa, nội thất, phần tử thô, mũi tên bắc và kích thước (đo từ tham chiếu) khớp hai chiều với spec, nét + tròn + hình chữ nhật", not rest_m and not rest_x,
          f"thiếu {len(rest_m)} {[m[0] + '/' + m[1] for m in rest_m[:3]]}; thừa {len(rest_x)} {rest_x[:3]}")
    texts = collections.Counter((lay, t) for lay, t in dx["texts"] if lay in ("CHU", "TRUC-KYHIEU", "KICH-THUOC"))
    want = collections.Counter(X["texts"])
    # title-block texts sit on layer CHU too: keep only those outside the title block
    from verify_d import _plan_texts
    plan = collections.Counter(("CHU", t) for t in _plan_texts(D, dx))
    got_t = collections.Counter({k: v for k, v in texts.items() if k[0] != "CHU"}) + plan
    C.add(group, ids[2], f"{where}: chữ (tên trục, phòng + diện tích, nội thất, ghi chú, nhãn kích thước, tên hình, tỷ lệ) khớp chính xác với spec", want == got_t, f"thiếu {list((want - got_t).elements())[:3]}; thừa {list((got_t - want).elements())[:3]}")
    # room labels inside their rooms (anchor = middle of the baseline, from the TEXT entities)
    from verify_d import _real_width
    view = sp["views"][0]
    anchors = collections.defaultdict(list)
    for e in dx["ents"]:
        if e["type"] != "TEXT":
            continue
        r = e["rec"]
        try:
            from readers import unesc
            txt = unesc("".join(r.get(3, [])) + (r.get(1) or [""])[0])
            h, wf = f(r, 40), (f(r, 41) if 41 in r else 1.0)
            anchors[txt].append((f(r, 10) + _real_width(txt, False, h / 0.716, wf) / 2, f(r, 20)))
        except (KeyError, ValueError, IndexError):
            pass
    bad_rooms = []
    for e in (q for q in view["elems"] if q["t"] == "phong"):
        for string in (e["ten"], area_text(e["da_giac"])):
            if not any(point_in(e["da_giac"], Fraction(x).limit_denominator(10 ** 6), Fraction(y).limit_denominator(10 ** 6)) for x, y in anchors.get(string, [])):
                bad_rooms.append(f"{e['id']}:{string}")
    C.add(group, ids[3], f"{where}: nhãn tên phòng và diện tích nằm trong đa giác của phòng (đọc từ thực thể TEXT)", not bad_rooms, f"nhãn ngoài phòng: {bad_rooms[:3]}")
    return X


def dxf_text_rules(C, D, dx, group, cid, where):
    boxes = [(t, "", b) for t, b in dxf_text_boxes_named(dx)]
    s = D.scale
    obst = []
    for _, layer, kind, d in dxf_shapes(dx):
        if layer in ("KHUNG-TEN",) or in_title_block(D, kind, d):
            continue
        if kind == "seg":
            obst.append((layer, "seg", d))
        elif kind == "rect":
            x0, y0, x1, y1 = d
            for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                obst.append((layer, "seg", (a, b)))
        else:
            obst.append((layer, "circ", d))
    sh = SHEETS[D.sheet]
    ox, oy = D.origin
    inside_tb = lambda b: sh.tb_x0 <= b[0] / s + ox <= sh.tb_x1 and sh.tb_y0 <= b[1] / s + oy <= sh.tb_y1
    boxes = [bx for bx in boxes if not inside_tb(bx[2])]
    bad, best = [], 1e9
    for txt, _, box in boxes:
        own_dim_text = False
        for layer, kind, data in obst:
            if kind == "seg":
                g = _seg_rect_gap(data[0], data[1], box)
            else:
                (cx, cy), r = data
                dx_, dy_ = max(box[0] - cx, 0.0, cx - box[2]), max(box[1] - cy, 0.0, cy - box[3])
                dmax = max(math.hypot(x - cx, y - cy) for x in (box[0], box[2]) for y in (box[1], box[3]))
                dmin = math.hypot(dx_, dy_)
                g = 0.0 if dmin <= r <= dmax else (dmin - r if dmin > r else r - dmax)
            if layer == "KICH-THUOC" and txt and (txt.isdigit() or txt[:1] in ("R", "Ø") or txt.endswith("°")):
                continue
            if layer == "NET-MANH" and re.fullmatch(r"[+\-±]\d+\.\d{3}", txt or ""):
                continue                    # a level text sits on the bar of its own symbol           # dimension labels may touch the lines of their own dimension; their crossing of the OTHER lines is covered by 1.56 (primitives carry the tags)
            best = min(best, g)
            if g < TEXT_MARGIN * s:
                bad.append((txt, layer))
    C.add(group, cid, f"{where}: không chuỗi chữ nào (trừ nhãn kích thước) có hộp bao cắt hoặc chạm (≤ {TEXT_MARGIN:g} mm giấy) một nét hay vòng tròn khác (độ rộng Arial thật)", not bad and bool(boxes),
          f"{len(boxes)} chuỗi, {len(obst)} nét/vòng; cắt/chạm: {bad[:3]}; khoảng cách nhỏ nhất {best / s if best < 1e8 else 'không có'} mm giấy")


def dxf_text_boxes_named(dx):
    return [(t, b) for t, b in dxf_text_boxes(dx)]


def check_dxf_e(C: Checks, D, sp, dx):
    dxf_checks(C, D, sp, dx, 2, ("2.30", "2.31", "2.32", "2.35", "2.36"), "DXF")
    dxf_text_rules(C, D, dx, 2, "2.33", "DXF")
    verify_e3.check_legend_linetypes(C, D, sp, dx, 2, "2.37", "DXF")
    dxf_room_name_height(C, D, sp, dx, 2, "2.38", "DXF")
    s = D.scale
    nz = [e for e in dx["ents"] if e["type"] == "LINE" and math.hypot(f(e["rec"], 11) - f(e["rec"], 10), f(e["rec"], 21) - f(e["rec"], 20)) < 1e-9]
    keys = collections.Counter((e["layer"], round(f(e["rec"], 10), 4), round(f(e["rec"], 20), 4), round(f(e["rec"], 11), 4), round(f(e["rec"], 21), 4)) for e in dx["ents"] if e["type"] == "LINE")
    C.add(2, "2.34", "DXF: không đoạn dài 0, không đoạn trùng lặp (cùng lớp, cùng hai đầu), mọi thực thể ở lớp có trong profile", not nz and all(v == 1 for v in keys.values()) and all(e["layer"] in ALLOWED_LAYERS + ("0",) for e in dx["ents"]),
          f"dài 0: {len(nz)}; trùng: {sum(1 for v in keys.values() if v > 1)}")


def check_dwg_e(C: Checks, D, sp, bx):
    dxf_checks(C, D, sp, bx, 3, ("3.20", "3.21", "3.22", "3.24", "3.25"), "DWG (đọc lại sau khứ hồi)")
    dxf_text_rules(C, D, bx, 3, "3.23", "DWG (đọc lại sau khứ hồi)")
    verify_e3.check_legend_linetypes(C, D, sp, bx, 3, "3.26", "DWG (đọc lại sau khứ hồi)")
    dxf_room_name_height(C, D, sp, bx, 3, "3.27", "DWG (đọc lại sau khứ hồi)")


# ------------------------------------------------------------------ 5. PDF
def check_pdf_e(C: Checks, D, sp, dx, paths, profile):
    """5.20: every LINE of the DXF (walls, symbols, axes, dimensions) has a straight PDF stroke of its layer's weight at the paper position derived from the DXF coordinates."""
    s, (ox, oy) = D.scale, D.origin
    top = lambda y: SHEETS[D.sheet].h - y
    strokes = [p for p in paths if p["kind"] == "stroke" and p["n"] == 2 and not p["curve"]]
    used, bad = set(), []
    n = 0
    for _, layer, kind, d in dxf_shapes(dx):
        if kind != "seg" or layer not in profile or layer == "KHUNG-TEN" or in_title_block(D, kind, d):
            continue
        n += 1
        (x1, y1), (x2, y2) = d
        a, c = (x1 / s + ox, y1 / s + oy), (x2 / s + ox, y2 / s + oy)
        bb = (min(a[0], c[0]), top(max(a[1], c[1])), max(a[0], c[0]), top(min(a[1], c[1])))
        lw = profile[layer]["lw"] / 100.0
        dashed = profile[layer]["ltype"] != "CONTINUOUS"
        for k, p in enumerate(strokes):
            if k not in used and all(close(x, y, TOL_PDF) for x, y in zip(p["bb"], bb)) and close(p["lw"], lw, 0.03) and bool(p["dash"]) == dashed:
                used.add(k)
                break
        else:
            bad.append((layer, tuple(round(x, 2) for x in bb)))
    C.add(5, "5.20", "PDF: mỗi đoạn thẳng của DXF (tường, ký hiệu cửa, trục, kích thước) có nét PDF thẳng đúng vị trí ±0,06 mm, đúng độ dày theo lớp, đúng nét liền/đứt", n > 0 and not bad, f"{n - len(bad)}/{n} đoạn có nét PDF; không thấy {bad[:3]}")
