"""Drawing type E ("ve_tu_do"): free-form civil drawing from a closed list of elements -> primitives.

Model: real mm, y up, one view per sheet (phase 1). Paper position = model / scale + offset; everything that has a fixed paper size (bubbles, ticks, text, dimension offsets) is added
in paper mm. Walls are drawn as the OUTLINE OF THE UNION of the wall bodies (rectangles, cut by the openings), computed exactly with Fractions (coordinate compression). Arcs are
polylines of straight segments (the shared renderers have no ARC primitive). Dimensions are measured here from the references and drawn as LINE + TEXT (no DIMENSION entity).
Text is placed AFTER all geometry; every label is tried at a list of candidate positions and takes the first one whose box (real Arial width + 5 %) keeps `le_chu` from every
line / circle / other text; if none fits the builder raises a Vietnamese error that names the element. Primitive tags: truc_dung / truc_ngang (axis_v / axis_h), bubble, bubble_text,
wall_edge, wall_line, door_frame:<id>, door_leaf:<id>, door_arc:<id>, win_line:<id>, furn:<id>, furn_label:<id>, room_name:<id>, room_area:<id>, note:<id>, raw_*:<id>,
bac_*, dim:<id>:(line|ext|tick|text), title, scale_note.
"""
from __future__ import annotations

import bisect
import math
from decimal import Decimal
from fractions import Fraction

import titleblock as TBK
from build_a import _moved
from primitives import Circle, Drawing, Line, Rect, Text, cap_to_em, drawing_extent
from scale import fit_in_sheet, sheet_scale_candidates
from spec_b import SpecError
import elems2
import elems3
from spec_e import (ARC_STEPS_90, AUTO_SCALES, LAYER_OF, fmt2, fmt_len, leg_pieces, leg_rect, resolve, wall_legs)
from tcvn import ARIAL_CAP, SHEETS, cons_width, LAYER_AXIS, LAYER_BUBBLE, LAYER_DIM, LAYER_TEXT
from verify import _seg_rect_gap

SHEET_SCALE_LIMIT = 200
DEFAULT_SHEET_NO = "KT-01"
NEEDED_LAYERS = ("TRUC", "TRUC-KYHIEU", "NET-CHINH", "NET-MANH", "NET-KHUAT", "NET-TAM", "KICH-THUOC", "CHU", "KHUNG-TEN")


DIM_MARGIN = 0.4          # paper mm between a dimension label and a line (labels sit right beside their own lines and the extension lines of the neighbours)
ROOM_NAME_STEPS = (3.5, 2.5)          # paper mm: a room name that does not fit steps down this list; never below ROOM_NAME_MIN
ROOM_NAME_MIN = 2.5
MARGIN_STEPS = (1.0,)              # paper mm: one smaller text margin tried after `le_chu` (the independent check 1.56 only demands 0.3)
GRID_STEP, GRID_N = 1.5, 8           # furniture label: extra positions on a 1.5 mm grid, up to 12 mm paper around the furniture
TEXT_GAP = 0.2            # paper mm kept free between two text boxes (the boxes already include descenders and Vietnamese marks)
HALIGN = {"trai": "left", "giua": "center", "phai": "right"}


class Unplaceable(Exception):
    pass


def fl(v) -> float:
    return float(v)


# ------------------------------------------------------------------ exact wall outline (union of axis-aligned rectangles)
def union_outline(rects):
    """Boundary segments (Fractions) of the union of axis-aligned rectangles, collinear pieces merged: [((x0, y0), (x1, y1))]."""
    if not rects:
        return []
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})
    cov = [[False] * (len(ys) - 1) for _ in range(len(xs) - 1)]
    for x0, y0, x1, y1 in rects:
        for i in range(bisect.bisect_left(xs, x0), bisect.bisect_left(xs, x1)):
            row = cov[i]
            for j in range(bisect.bisect_left(ys, y0), bisect.bisect_left(ys, y1)):
                row[j] = True
    c = lambda i, j: 0 <= i < len(xs) - 1 and 0 <= j < len(ys) - 1 and cov[i][j]
    segs = {}
    for i in range(len(xs)):                               # vertical grid line x_i, between cells (i-1, j) and (i, j)
        for j in range(len(ys) - 1):
            if c(i - 1, j) != c(i, j):
                segs.setdefault(("v", xs[i]), []).append((ys[j], ys[j + 1]))
    for j in range(len(ys)):
        for i in range(len(xs) - 1):
            if c(i, j - 1) != c(i, j):
                segs.setdefault(("h", ys[j]), []).append((xs[i], xs[i + 1]))
    out = []
    for (kind, k), parts in segs.items():
        parts.sort()
        cur = list(parts[0])
        for a, b in parts[1:]:
            if a <= cur[1]:
                cur[1] = max(cur[1], b)
            else:
                out.append(((k, cur[0]), (k, cur[1])) if kind == "v" else ((cur[0], k), (cur[1], k)))
                cur = [a, b]
        out.append(((k, cur[0]), (k, cur[1])) if kind == "v" else ((cur[0], k), (cur[1], k)))
    return sorted(out)


def openings_by_leg(view):
    d = {}
    for e in view["elems"]:
        if e["t"] in ("cua_di", "cua_so", "o_trong"):
            d.setdefault((e["tuong"], e["doan"]), []).append(e)
    for v in d.values():
        v.sort(key=lambda o: o["vi_tri"])
    return d


# ------------------------------------------------------------------ text boxes / collision tests (paper mm)
def text_box(s, h, pos, halign="left", rot=0.0, bold=False, wf=1.0):
    w = cons_width(s, cap_to_em(h), wf, bold)
    off = {"left": 0.0, "center": w / 2, "right": w}[halign]
    c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    x, y = pos[0] - off * c, pos[1] - off * sn
    pts = [(x + a * c - b * sn, y + a * sn + b * c) for a in (0.0, w) for b in (-0.25 * h, 1.35 * h)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def box_hits_circle(box, c, r, m):
    dx = max(box[0] - c[0], 0.0, c[0] - box[2])
    dy = max(box[1] - c[1], 0.0, c[1] - box[3])
    dmin = math.hypot(dx, dy)
    dmax = max(math.hypot(x - c[0], y - c[1]) for x in (box[0], box[2]) for y in (box[1], box[3]))
    return dmin <= r + m and dmax >= r - m


def boxes_overlap(a, b, m):
    return a[0] - m < b[2] and b[0] - m < a[2] and a[1] - m < b[3] and b[1] - m < a[3]


class Sheetwork:
    """Primitives of one view (paper mm, model origin at (0, 0)) + placed text boxes."""

    def __init__(self, P, s):
        self.P, self.s, self.prims, self.boxes, self.box_tags = P, s, [], [], []
        self.lowered = []      # labels placed only after a smaller text height / margin (reported to the user)

    def add(self, p):
        self.prims.append(p)
        return p

    def line(self, layer, tag, a, b):
        return self.add(Line(layer=layer, tag=tag, p1=(fl(a[0]), fl(a[1])), p2=(fl(b[0]), fl(b[1]))))

    def hits(self, box, exclude_tag="", m=None):
        """'' when the box is free, else a short description of the first thing it touches (tag of the line / circle, or 'chữ khác')."""
        m = self.P["le_chu"] if m is None else m
        for p in self.prims:
            if exclude_tag and p.tag.startswith(exclude_tag):
                continue
            if isinstance(p, Line):
                if max(p.p1[0], p.p2[0]) < box[0] - m or min(p.p1[0], p.p2[0]) > box[2] + m or max(p.p1[1], p.p2[1]) < box[1] - m or min(p.p1[1], p.p2[1]) > box[3] + m:
                    continue                  # farther than m on one axis, so the gap is >= m (same result, much faster)
                if _seg_rect_gap(p.p1, p.p2, box) < m:
                    return p.tag or "nét"
            elif isinstance(p, Rect):
                x0, y0, x1, y1 = p.p0[0], p.p0[1], p.p1[0], p.p1[1]
                if any(_seg_rect_gap(a, b, box) < m for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))):
                    return p.tag or "hình chữ nhật"
            elif isinstance(p, Circle):
                if box_hits_circle(box, p.c, p.r, m):
                    return p.tag or "vòng tròn"
        return "chữ khác" if any(boxes_overlap(box, b, TEXT_GAP) for b in self.boxes) else ""

    def text(self, tag, layer, s, h, pos, halign="left", rot=0.0, bold=False):
        t = self.add(Text(layer=layer, tag=tag, s=s, pos=(pos[0], pos[1]), h=h, rot=rot, halign=halign, bold=bold))
        self.boxes.append(text_box(s, h, pos, halign, rot, bold))
        self.box_tags.append(tag)
        return t

    def place(self, tag, layer, s, h, candidates, who, exclude_tag="", bold=False, margin=None):
        """candidates = [(pos, halign, rot)]. First free one wins; none -> Unplaceable."""
        blocker = ""
        for pos, halign, rot in candidates:
            blocker = self.hits(text_box(s, h, pos, halign, rot, bold), exclude_tag, margin)
            if not blocker:
                return self.text(tag, layer, s, h, pos, halign, rot, bold)
        raise Unplaceable(f"{who}: không đặt được chữ {s[:40]!r} (cao {h:g} mm) mà không chạm nét hoặc chữ khác (đã thử {len(candidates)} vị trí; vị trí cuối chạm {blocker!r}). Dịch vi_tri / diem hoặc đổi tỷ lệ")


# ------------------------------------------------------------------ geometry of the elements
def arc_points(c, r, a0, a1, n):
    return [(c[0] + r * math.cos(a0 + (a1 - a0) * k / n), c[1] + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def build_geometry(sp, view, W, X):
    P, s = sp["params"], W.s
    ov, gp, rb, hb = P["truc_vuon_qua"], P["khe_vong_truc"], P["duong_kinh_vong_truc"] / 2, P["cao_chu_vong_truc"]
    by = view["by_id"]
    # ---- axes + bubbles
    g = next((e for e in view["elems"] if e["t"] == "truc"), None)
    if g:
        ys = [v for _, v in g["ngang"]]
        xs = [v for _, v in g["dung"]]
        y_lo, y_hi, x_lo, x_hi = X(min(ys)) - ov, X(max(ys)) + ov, X(min(xs)) - ov, X(max(xs)) + ov
        for ten, x in g["dung"]:
            W.line("TRUC", "axis_v", (X(x), y_lo), (X(x), y_hi))
            cy = y_hi + gp + rb
            W.add(Circle(layer="TRUC-KYHIEU", tag="bubble", c=(X(x), cy), r=rb))
            W.text("bubble_text", "TRUC-KYHIEU", ten, hb, (X(x), cy - hb / 2), "center")
        for ten, y in g["ngang"]:
            W.line("TRUC", "axis_h", (x_lo, X(y)), (x_hi, X(y)))
            cx = x_lo - gp - rb
            W.add(Circle(layer="TRUC-KYHIEU", tag="bubble", c=(cx, X(y)), r=rb))
            W.text("bubble_text", "TRUC-KYHIEU", ten, hb, (cx, X(y) - hb / 2), "center")
    # ---- walls
    cuts = openings_by_leg(view)
    rects = []
    for w in (e for e in view["elems"] if e["t"] == "tuong"):
        for k, L in enumerate(wall_legs(w)):
            ops = [(o["vi_tri"], o["vi_tri"] + o["rong"]) for o in cuts.get((w["id"], k), [])]
            for t0, t1 in leg_pieces(L, ops):
                if w["kieu"] == "2_net":
                    rects.append(leg_rect(L, t0, t1))
                else:
                    a, d = L["a"], L["d"]
                    W.line("NET-CHINH", "wall_line", (X(a[0] + d[0] * t0), X(a[1] + d[1] * t0)), (X(a[0] + d[0] * t1), X(a[1] + d[1] * t1)))
    for a, b in union_outline(rects):
        W.line("NET-CHINH", "wall_edge", (X(a[0]), X(a[1])), (X(b[0]), X(b[1])))
    # ---- doors, windows
    for o in view["elems"]:
        if o["t"] not in ("cua_di", "cua_so"):
            continue
        w = by[o["tuong"]]
        L = wall_legs(w)[o["doan"]]
        a, d, n, lo, hi = L["a"], L["d"], L["n"], L["lo"], L["hi"]
        v, wd = o["vi_tri"], o["rong"]
        pt = lambda t, off: (X(a[0] + d[0] * t + n[0] * off), X(a[1] + d[1] * t + n[1] * off))
        if o["t"] == "cua_so":
            for fr_ in ((Fraction(1, 3), Fraction(2, 3)) if o["ky_hieu"] == "kep" else (Fraction(0), Fraction(1, 2), Fraction(1))):
                off = lo + fr_ * (hi - lo)
                W.line("NET-MANH", f"win_line:{o['id']}", pt(v, off), pt(v + wd, off))
            continue
        for off in (lo, hi):
            W.line("NET-MANH", f"door_frame:{o['id']}", pt(v, off), pt(v + wd, off))
        th = v if o["ban_le"] == "dau" else v + wd
        sw = 1 if o["mo_ve"] == "trai" else -1
        off_s = hi if o["mo_ve"] == "trai" else lo
        H = pt(th, off_s)
        ns = (sw * n[0], sw * n[1])
        dc = d if o["ban_le"] == "dau" else (-d[0], -d[1])
        r = X(wd)
        W.line("NET-MANH", f"door_leaf:{o['id']}", H, (H[0] + ns[0] * r, H[1] + ns[1] * r))
        a0, a1 = math.atan2(dc[1], dc[0]), math.atan2(ns[1], ns[0])
        delta = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        pts_ = arc_points(H, r, a0, a0 + delta, ARC_STEPS_90)
        for p, q in zip(pts_, pts_[1:]):
            W.line("NET-MANH", f"door_arc:{o['id']}", p, q)
    # ---- furniture blocks, raw elements, north arrow
    for e in view["elems"]:
        t = e["t"]
        if t == "noi_that_co_ban":
            b = e["box"]
            W.add(Rect(layer="NET-MANH", tag=f"furn:{e['id']}", p0=(X(b[0]), X(b[1])), p1=(X(b[2]), X(b[3]))))
        elif t == "duong":
            W.line(e["lop"], f"raw_duong:{e['idx']}", (X(e["tu"][0]), X(e["tu"][1])), (X(e["den"][0]), X(e["den"][1])))
        elif t == "polyline":
            p = e["diem"] + ([e["diem"][0]] if e["kin"] else [])
            for q, r in zip(p, p[1:]):
                W.line(e["lop"], f"raw_polyline:{e['idx']}", (X(q[0]), X(q[1])), (X(r[0]), X(r[1])))
        elif t == "tron":
            W.add(Circle(layer=e["lop"], tag=f"raw_tron:{e['id']}", c=(X(e["tam"][0]), X(e["tam"][1])), r=X(e["ban_kinh"])))
        elif t == "cung":
            n = max(2, math.ceil(ARC_STEPS_90 * fl(e["quet"]) / 90))
            a0 = math.radians(fl(e["goc_dau"]))
            pts_ = arc_points((X(e["tam"][0]), X(e["tam"][1])), X(e["ban_kinh"]), a0, a0 + math.radians(fl(e["quet"])), n)
            for p, q in zip(pts_, pts_[1:]):
                W.line(e["lop"], f"raw_cung:{e['id']}", p, q)
        elif t == "mui_ten_bac":
            R = P["ban_kinh_mui_ten_bac"]
            c = (X(e["vi_tri"][0]), X(e["vi_tri"][1]))
            ph = math.radians(fl(e["goc"]))
            u, pp = (-math.sin(ph), math.cos(ph)), (math.cos(ph), math.sin(ph))
            tip = (c[0] + u[0] * R * 0.9, c[1] + u[1] * R * 0.9)
            b1 = (c[0] - u[0] * R * 0.5 + pp[0] * R * 0.35, c[1] - u[1] * R * 0.5 + pp[1] * R * 0.35)
            b2 = (c[0] - u[0] * R * 0.5 - pp[0] * R * 0.35, c[1] - u[1] * R * 0.5 - pp[1] * R * 0.35)
            W.add(Circle(layer="NET-MANH", tag="bac_vong", c=c, r=R))
            for p, q in ((tip, b1), (tip, b2), (b1, b2)):
                W.line("NET-MANH", "bac_tam_giac", p, q)
    elems2.geom(sp, view, W, X)
    elems3.geom(sp, view, W, X)


def geometry_extent(W, skip=()):
    bbs = []
    for p in W.prims:
        if skip and p.tag.startswith(skip):
            continue
        if isinstance(p, Line):
            bbs.append((min(p.p1[0], p.p2[0]), min(p.p1[1], p.p2[1]), max(p.p1[0], p.p2[0]), max(p.p1[1], p.p2[1])))
        elif isinstance(p, Rect):
            bbs.append((min(p.p0[0], p.p1[0]), min(p.p0[1], p.p1[1]), max(p.p0[0], p.p1[0]), max(p.p0[1], p.p1[1])))
        elif isinstance(p, Circle):
            bbs.append((p.c[0] - p.r, p.c[1] - p.r, p.c[0] + p.r, p.c[1] + p.r))
    return (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs)) if bbs else (0.0, 0.0, 0.0, 0.0)


# ------------------------------------------------------------------ dimensions (measured here from the references)
def sqrt_half_up(v: Fraction) -> int:
    """round-half-up(sqrt(v)) for an exact rational (Decimal, 60 digits)."""
    d = (Decimal(v.numerator) / Decimal(v.denominator)).sqrt()
    return int((d + Decimal("0.5")).to_integral_value(rounding="ROUND_FLOOR"))


def build_dims(sp, view, W, X, ext):
    P, s = sp["params"], W.s
    exo, exe, asz, gap, h = P["kt_exo"], P["kt_exe"], P["kt_mui_ten"], P["kt_khe_chu"], P["cao_chu_kich_thuoc"]
    dims = [e for e in view["elems"] if e["t"] == "kich_thuoc"]
    drawn_ext, drawn_tick, texts = {}, set(), []

    def tick(tag, c, key):
        if key in drawn_tick:
            return
        drawn_tick.add(key)
        W.line("KICH-THUOC", tag, (c[0] - asz / 2, c[1] - asz / 2), (c[0] + asz / 2, c[1] + asz / 2))

    lin = [e for e in dims if e["kieu"] in ("ngang", "doc", "chuoi")]
    for e in sorted(lin, key=lambda q: (q["lop"], q["idx"])):
        horiz = e["huong"] == "ngang"
        vals = e["vals"]
        if e["kieu"] != "chuoi":
            vals = sorted(vals)
        off = P["kt_dau_tien"] + (e["lop"] - 1) * P["kt_giua_cac_duong"]
        if horiz:
            edge = ext[1] if e["phia"] == "duoi" else ext[3]
            ly = edge - off if e["phia"] == "duoi" else edge + off
            sg = -1.0 if e["phia"] == "duoi" else 1.0
        else:
            edge = ext[0] if e["phia"] == "trai" else ext[2]
            ly = edge - off if e["phia"] == "trai" else edge + off
            sg = -1.0 if e["phia"] == "trai" else 1.0
        pairs = list(zip(vals, vals[1:])) if e["kieu"] == "chuoi" else [tuple(vals)]
        for a, b in pairs:
            a, b = (a, b) if a <= b else (b, a)
            pa, pb = X(a), X(b)
            for c, vv in ((pa, a), (pb, b)):
                key = (horiz, e["phia"], vv)
                start = drawn_ext.get(key)
                s0 = (start if start is not None else edge + sg * exo)
                end = ly + sg * exe
                if start is None or (abs(end - start) > 1e-9 and (end - start) * sg > 0):
                    if horiz:
                        W.line("KICH-THUOC", f"dim:{e['id']}:ext", (c, s0), (c, end))
                    else:
                        W.line("KICH-THUOC", f"dim:{e['id']}:ext", (s0, c), (end, c))
                    drawn_ext[key] = end
                tick(f"dim:{e['id']}:tick", (c, ly) if horiz else (ly, c), (horiz, ly, vv))
            if horiz:
                W.line("KICH-THUOC", f"dim:{e['id']}:line", (pa, ly), (pb, ly))
            else:
                W.line("KICH-THUOC", f"dim:{e['id']}:line", (ly, pa), (ly, pb))
            texts.append((e, a, b, pa, pb, ly, horiz))
    # texts of the linear dimensions (after ALL their lines exist)
    for e, a, b, pa, pb, ly, horiz in texts:
        label = fmt_len(b - a)
        w = cons_width(label, cap_to_em(h))
        ex = f"dim:{e['id']}:"
        who = f"phan_tu[{e['idx']}] (loai='kich_thuoc', id={e['id']!r})"
        if horiz:
            mid = (pa + pb) / 2
            cands = []
            if (pb - pa) >= w + 3.0 * (asz / 2.5):
                cands.append(((mid, ly + gap), "center", 0.0))
            cands += [((pb + asz / 2 + gap, ly + gap), "left", 0.0), ((pa - asz / 2 - gap, ly + gap), "right", 0.0), ((mid, ly + gap + h + 1.0), "center", 0.0),
                      ((pb + asz / 2 + gap, ly + gap + h + 1.0), "left", 0.0)]
        else:
            mid = (pa + pb) / 2
            cands = []
            if (pb - pa) >= w + 3.0 * (asz / 2.5):
                cands.append(((ly - gap, mid), "center", 90.0))
            cands += [((ly - gap, pb + asz / 2 + gap + w / 2), "center", 90.0), ((ly - gap, pa - asz / 2 - gap - w / 2), "center", 90.0), ((ly - gap - h - 1.0, mid), "center", 90.0)]
        try:
            W.place(f"dim:{e['id']}:text", "KICH-THUOC", label, h, cands, who, exclude_tag=ex, margin=DIM_MARGIN)
        except Unplaceable as u:
            raise Unplaceable(str(u))
    # ---- aligned, radius / diameter, angle
    for e in dims:
        k, ex = e["kieu"], f"dim:{e['id']}:"
        who = f"phan_tu[{e['idx']}] (loai='kich_thuoc', id={e['id']!r})"
        if k == "song_song":
            (x1, y1), (x2, y2) = e["p"]
            p1, p2 = (X(x1), X(y1)), (X(x2), X(y2))
            L = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            u = ((p2[0] - p1[0]) / L, (p2[1] - p1[1]) / L)
            nl = (-u[1], u[0]) if e["phia"] == "trai" else (u[1], -u[0])
            off = fl(e["khoang"])
            q1, q2 = (p1[0] + nl[0] * off, p1[1] + nl[1] * off), (p2[0] + nl[0] * off, p2[1] + nl[1] * off)
            for p, q in ((p1, q1), (p2, q2)):
                W.line("KICH-THUOC", ex + "ext", (p[0] + nl[0] * exo, p[1] + nl[1] * exo), (q[0] + nl[0] * exe, q[1] + nl[1] * exe))
            W.line("KICH-THUOC", ex + "line", q1, q2)
            tk = asz / 2
            for q in (q1, q2):
                W.line("KICH-THUOC", ex + "tick", (q[0] - tk * (u[0] - u[1]), q[1] - tk * (u[1] + u[0])), (q[0] + tk * (u[0] - u[1]), q[1] + tk * (u[1] + u[0])))
            lab = str(sqrt_half_up((x2 - x1) ** 2 + (y2 - y1) ** 2))
            ang = math.degrees(math.atan2(u[1], u[0]))
            if ang > 90 or ang <= -90:                       # keep the text readable (never upside down)
                ang += 180 if ang <= -90 else -180
            ph = math.radians(ang)
            up = (-math.sin(ph), math.cos(ph))              # the text's own "up": the label sits above the line in its reading frame
            mid = ((q1[0] + q2[0]) / 2, (q1[1] + q2[1]) / 2)
            cands = [((mid[0] + up[0] * (gap + dd), mid[1] + up[1] * (gap + dd)), "center", ang) for dd in (0.0, h + 1.0, 2 * (h + 1.0))]
            W.place(ex + "text", "KICH-THUOC", lab, h, cands, who, exclude_tag=ex, margin=DIM_MARGIN)
        elif k in ("ban_kinh", "duong_kinh"):
            c = view["by_id"][e["phan_tu"]]
            cx, cy, r = X(c["tam"][0]), X(c["tam"][1]), X(c["ban_kinh"])
            th = math.radians(fl(e["goc"]))
            dirx, diry = math.cos(th), math.sin(th)
            Q = (cx + r * dirx, cy + r * diry)
            Eo = (cx + (r + 12.0) * dirx, cy + (r + 12.0) * diry)
            start = Q if k == "ban_kinh" else (cx - r * dirx, cy - r * diry)
            W.line("KICH-THUOC", ex + "line", start, Eo)
            tick(ex + "tick", Q, ("c", e["id"], 0))
            if k == "duong_kinh":
                tick(ex + "tick", start, ("c", e["id"], 1))
            lab = ("R" if k == "ban_kinh" else "Ø") + (fmt_len(c["ban_kinh"]) if k == "ban_kinh" else fmt_len(2 * c["ban_kinh"]))
            al = "left" if dirx >= -1e-9 else "right"
            cands = [((Eo[0] + (1.0 if al == "left" else -1.0) * (gap + dd), Eo[1] - h / 2 + dd2), al, 0.0) for dd in (0.0, 2.0, 4.0) for dd2 in (0.0, h + 1.0)]
            W.place(ex + "text", "KICH-THUOC", lab, h, cands, who, exclude_tag=ex, margin=DIM_MARGIN)
        elif k == "goc":
            (vx, vy), (ax, ay), (bx, by_) = e["dinh"], e["tia1"], e["tia2"]
            V = (X(vx), X(vy))
            a1 = math.atan2(fl(ay - vy), fl(ax - vx))
            a2 = math.atan2(fl(by_ - vy), fl(bx - vx))
            delta = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
            R = fl(e["ban_kinh_cung"])
            nseg = max(2, math.ceil(ARC_STEPS_90 * abs(math.degrees(delta)) / 90))
            pts_ = arc_points(V, R, a1, a1 + delta, nseg)
            for p, q in zip(pts_, pts_[1:]):
                W.line("KICH-THUOC", ex + "line", p, q)
            for p in (pts_[0], pts_[-1]):
                tick(ex + "tick", p, ("g", e["id"], round(p[0], 6), round(p[1], 6)))
            deg = Decimal(repr(abs(math.degrees(delta)))).quantize(Decimal("0.1"), rounding="ROUND_HALF_UP")
            lab = f"{deg:f}".replace(".", ",") + "°"
            mid = a1 + delta / 2
            cands = [((V[0] + (R + 3.0 + dd) * math.cos(mid), V[1] + (R + 3.0 + dd) * math.sin(mid) - h / 2), "center", 0.0) for dd in (0.0, 3.0, 6.0, 9.0)]
            W.place(ex + "text", "KICH-THUOC", lab, h, cands, who, exclude_tag=ex, margin=DIM_MARGIN)


# ------------------------------------------------------------------ labels
def build_labels(sp, view, W, X):
    from spec_e import point_in_polygon
    P = sp["params"]
    hn, ha, hf = P["cao_chu_ten_phong"], P["cao_chu_ghi_chu"], P["cao_chu_noi_that"]
    elems2.labels2(sp, view, W, X)
    elems3.labels3(sp, view, W, X)
    order = {"noi_that_co_ban": 0, "phong": 1}
    for e in sorted(view["elems"], key=lambda q: (order.get(q["t"], 2), q["idx"])):
        t = e["t"]
        who = f"{e['path']}"
        if t == "phong":
            cx, cy = X(e["nhan"][0]), X(e["nhan"][1])
            area = f"DT: {fmt2(e['dien_tich'])} m²"
            def in_room(lst):                      # spots whose centre lies in the room (only (0, 0) when vi_tri_nhan fixes the place)
                if e["vi_tri_nhan"] is not None:
                    return [(0.0, 0.0)]
                return [(dx, dy) for dx, dy in lst if point_in_polygon((Fraction((cx + dx) * W.s).limit_denominator(10 ** 6), Fraction((cy + dy) * W.s).limit_denominator(10 ** 6)), e["da_giac"])]
            spots = in_room(sorted(((dx * 3.0, dy * 3.0) for dx in range(-30, 31) for dy in range(-20, 21)), key=lambda q: (q[0] ** 2 + q[1] ** 2, q)))
            fine = []                              # 1 mm grid, built only when the first try fails
            sizes = [hn] + [h for h in ROOM_NAME_STEPS if ROOM_NAME_MIN <= h < hn]
            margins = [P["le_chu"]] + [m for m in MARGIN_STEPS if m < P["le_chu"]]
            ok = False
            for h in sizes:                        # (a) sweep the grid of spots, (b) then smaller text height, then smaller margin
                for m in margins:
                    first = (h, m) == (hn, P["le_chu"])
                    if not first and not fine:
                        fine = in_room(sorted(((dx * 1.0, dy * 1.0) for dx in range(-60, 61) for dy in range(-40, 41)), key=lambda q: (q[0] ** 2 + q[1] ** 2, q)))
                    for dx, dy in (spots if first else fine):      # first try = old coarse grid; later tries = 1 mm grid
                        pos_n, pos_a = (cx + dx, cy + dy + 1.5), (cx + dx, cy + dy - 3.5)
                        bn, ba = text_box(e["ten"], h, pos_n, "center", 0.0, True), text_box(area, ha, pos_a, "center")
                        if not W.hits(bn, m=m) and not W.hits(ba, m=m) and not boxes_overlap(bn, ba, 0.3):
                            W.text(f"room_name:{e['id']}", "CHU", e["ten"], h, pos_n, "center", 0.0, True)
                            W.text(f"room_area:{e['id']}", "CHU", area, ha, pos_a, "center")
                            if h != hn or m != P["le_chu"]:
                                W.lowered.append(dict(id=e["id"], ten=e["ten"], loai="ten_phong", cao_cu=hn, cao_moi=h, le_cu=P["le_chu"], le_moi=m))
                            ok = True
                            break
                    if ok:
                        break
                if ok:
                    break
            if not ok:
                raise Unplaceable(f"{who}: không đặt được nhãn phòng {e['ten']!r} và diện tích mà không chạm nét/chữ khác (đã thử cỡ chữ {hn:g} xuống {sizes[-1]:g} mm, lề chữ {P['le_chu']:g} xuống {margins[-1]:g} mm, quét lưới vị trí); nhập vi_tri_nhan hoặc dùng tỷ lệ lớn hơn")
        elif t == "noi_that_co_ban":
            b = e["box"]
            x0, y0, x1, y1 = X(b[0]), X(b[1]), X(b[2]), X(b[3])
            lab = e["nhan"]
            w = cons_width(lab, cap_to_em(hf))
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            cands = [((mx, my - hf / 2), "center", 0.0), ((mx + hf / 2, my), "center", 90.0), ((x1 + 1.5, my - hf / 2), "left", 0.0), ((x0 - 1.5, my - hf / 2), "right", 0.0),
                     ((mx, y1 + 1.5), "center", 0.0), ((mx, y0 - 1.5 - hf), "center", 0.0)]
            cx_, cy_ = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            room = next((q for q in view["elems"] if q["t"] == "phong" and point_in_polygon((Fraction(cx_).limit_denominator(10 ** 6), Fraction(cy_).limit_denominator(10 ** 6)), q["da_giac"])), None)
            grid = sorted(((i * GRID_STEP, j * GRID_STEP) for i in range(-GRID_N, GRID_N + 1) for j in range(-GRID_N, GRID_N + 1) if i or j), key=lambda q: (q[0] ** 2 + q[1] ** 2, q))
            for dx, dy in grid:                    # extra spots, kept in the room the furniture stands in
                px, py = mx + dx, my + dy - hf / 2
                if room is None or point_in_polygon((Fraction((px) * W.s).limit_denominator(10 ** 6), Fraction((py + hf / 2) * W.s).limit_denominator(10 ** 6)), room["da_giac"]):
                    cands.append(((px, py), "center", 0.0))
            for m in [P["le_chu"]] + [q for q in MARGIN_STEPS if q < P["le_chu"]]:
                try:
                    W.place(f"furn_label:{e['id']}", "CHU", lab, hf, cands, who, margin=m)
                except Unplaceable as u:
                    err = u
                    continue
                if m != P["le_chu"]:
                    W.lowered.append(dict(id=e["id"], ten=lab, loai="nhan_noi_that", cao_cu=hf, cao_moi=hf, le_cu=P["le_chu"], le_moi=m))
                break
            else:
                raise Unplaceable(f"{err} (đã thử lề chữ {P['le_chu']:g} xuống {min(P['le_chu'], MARGIN_STEPS[-1]):g} mm, cỡ chữ {hf:g} mm giữ nguyên vì dưới đó không có nấc chuẩn, quét thêm lưới vị trí quanh nội thất)")
        elif t in ("ghi_chu", "chu"):
            lines = e["dong"] if t == "ghi_chu" else [e["chu"]]
            x, y = X(e["vi_tri"][0]), X(e["vi_tri"][1])
            for k, ln in enumerate(lines):
                tg = f"note:{e['idx']}:{k}" if t == "ghi_chu" else f"raw_chu:{e['idx']}"
                W.place(tg, "CHU", ln, e["cao"], [((x, y - k * (e["cao"] + 2.0)), HALIGN[e["can"]], 0.0)], who, bold=e["dam"])
        elif t == "mui_ten_bac":
            R = P["ban_kinh_mui_ten_bac"]
            c = (X(e["vi_tri"][0]), X(e["vi_tri"][1]))
            ph = math.radians(fl(e["goc"]))
            u = (-math.sin(ph), math.cos(ph))
            pos = (c[0] + u[0] * (R + 2.7), c[1] + u[1] * (R + 2.7))
            W.place("bac_chu", "CHU", "B", 3.5, [(pos, "center", 0.0)], who)


# ------------------------------------------------------------------ one layout at scale 1:s
def layout(sp, s):
    view = sp["views"][0]
    P = sp["params"]
    X = lambda v: float(v) / s
    W = Sheetwork(P, s)
    build_geometry(sp, view, W, X)
    ext = geometry_extent(W, skip=("bac_",))      # dimensions are offset from the building, not from a north arrow standing far away
    build_dims(sp, view, W, X, ext)
    build_labels(sp, view, W, X)
    check_bubbles(W)
    ge = geometry_extent(W)
    xc = (ext[0] + ext[2]) / 2
    # ---- title + scale note below everything
    tt = next((e for e in view["elems"] if e["t"] == "tieu_de_hinh"), None)
    title = (tt["chu"] if tt and tt["chu"] else view["ten"])
    allb = [b[1] for b in W.boxes] + [ge[1]]
    bottom = min(allb)
    cap_t, cap_n = P["cao_chu_tieu_de"], P["cao_chu_ghi_chu"]
    t_base = bottom - P["khoang_tieu_de"] - cap_t
    W.text("title", "CHU", title, cap_t, (xc, t_base), "center", 0.0, True)
    W.text("scale_note", "CHU", f"TỶ LỆ 1:{s}", cap_n, (xc, t_base - P["khoang_ghi_chu"] - cap_n * ARIAL_CAP), "center")
    return W.prims, dict(title=title, extent=ge, ext_geom=ext, nhan_ha_co=W.lowered)


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def check_bubbles(W):
    """A bubble (grid axis, wind axis) must not touch another line, rectangle, circle or text (0.3 mm): else Unplaceable."""
    m = 0.3
    for c in (p for p in W.prims if isinstance(p, Circle) and (p.tag == "bubble" or p.tag.startswith("gio_bubble"))):
        for p in W.prims:
            if p is c:
                continue
            hit = None
            if isinstance(p, Line) and _seg_dist(c.c, p.p1, p.p2) < c.r + m:
                hit = p.tag
            elif isinstance(p, Rect):
                x0, y0, x1, y1 = p.p0[0], p.p0[1], p.p1[0], p.p1[1]
                if any(_seg_dist(c.c, a, b) < c.r + m for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))):
                    hit = p.tag
            elif isinstance(p, Circle) and math.hypot(p.c[0] - c.c[0], p.c[1] - c.c[1]) < p.r + c.r + m:
                hit = p.tag
            if hit:
                raise Unplaceable(f"vòng ký hiệu trục/tuyến gió tại ({(c.c[0]) * W.s:.0f}, {(c.c[1]) * W.s:.0f}) mm chạm {hit!r}: dời trục / nét đó ra xa hoặc đổi tỷ lệ")
        for b, tg in zip(W.boxes, W.box_tags):
            if tg in ("bubble_text",) or tg.startswith("gio_text"):
                if b[0] <= c.c[0] <= b[2] and b[1] <= c.c[1] <= b[3]:
                    continue
            if box_hits_circle(b, c.c, c.r, m):
                raise Unplaceable(f"vòng ký hiệu trục/tuyến gió tại ({(c.c[0]) * W.s:.0f}, {(c.c[1]) * W.s:.0f}) mm chạm chữ {tg!r}: dời chữ hoặc trục")


def _extent(prims):
    return drawing_extent(prims)


def build(sp: dict, profile: dict) -> Drawing:
    missing = [n for n in NEEDED_LAYERS if n not in profile]
    if missing:
        raise SpecError([f"profile.yaml thiếu layer chuẩn cần dùng: {', '.join(missing)}."])
    P = sp["params"]
    gap = P["khe_vung_ve"]
    view = sp["views"][0]
    want = sp["scale"] or view["scale"]
    only_sheet = None if sp["kho_giay"] == "auto" else sp["kho_giay"]
    tried, chosen, cache = [], None, {}
    for sh, sc in sheet_scale_candidates(want, only_sheet, limit=SHEET_SCALE_LIMIT, scales=AUTO_SCALES):
        if sc not in cache:
            try:
                cache[sc] = layout(sp, sc) + (None,)
            except Unplaceable as u:
                cache[sc] = (None, None, str(u))
        prims, meta, bad = cache[sc]
        if prims is None:
            if sh == "A3" or only_sheet:
                tried.append(f"1:{sc}: {bad}")
            continue
        bb = _extent(prims)
        w, hh = bb[2] - bb[0] + 2 * gap, bb[3] - bb[1] + 2 * gap
        fit = fit_in_sheet(w, hh, SHEETS[sh])
        t = None if fit is None else ((fit[1][0] + fit[1][2]) / 2 - (bb[0] + bb[2]) / 2, (fit[1][1] + fit[1][3]) / 2 - (bb[1] + bb[3]) / 2)     # centred in the drawing band
        if t is None:
            if sc == (want or SHEET_SCALE_LIMIT) or (not want and sc == 500):
                tried.append(f"{sh} ở 1:{sc} cần {w:.0f}×{hh:.0f} mm (khung {SHEETS[sh].frame_w:g}×{SHEETS[sh].frame_h:g} trừ góc khung tên 180×65)")
            continue
        chosen = (sh, sc, prims, meta, bb, t, w, hh)
        break
    if chosen is None:
        raise SpecError(["Không dựng được bản vẽ ở khổ/tỷ lệ nào đã thử: " + "; ".join(tried[:6]) + ". Không tự xoay hình."])
    sheet_name, s, prims, meta, bb, (tx, ty), w, hh = chosen
    sheet = SHEETS[sheet_name]
    reason = (f"khổ {sheet_name}, tỷ lệ 1:{s} " + ("do người dùng chọn" if want else "là tỷ lệ lớn nhất còn vừa trong dãy 1:20 - 1:500") +
              f"; hình cần {w:.0f}×{hh:.0f} mm gồm kích thước, ký hiệu trục, tên hình, nằm trong vùng vẽ (khung {sheet.frame_w:g}×{sheet.frame_h:g} trừ góc khung tên 180×65)." +
              ("" if want else f" Quy tắc: ưu tiên A3, chỉ dùng A2 rồi A1 khi khổ nhỏ hơn không vừa ở tỷ lệ ≤ 1:{SHEET_SCALE_LIMIT}") + (f"; không vừa: {'; '.join(tried[:4])}" if tried else ""))
    D = Drawing(name=sp["ten"], scale=s, origin=(tx, ty), kind="E", sheet=sheet_name)
    D.prims.extend(_moved(p, tx, ty) for p in prims)
    kt = dict(sp["khung_ten"])
    if not kt.get("ky_hieu_ban_ve"):
        kt["ky_hieu_ban_ve"] = DEFAULT_SHEET_NO
    if not kt.get("ten_ban_ve"):
        kt["ten_ban_ve"] = meta["title"]
    D.fields = TBK.fields_from_meta(kt, f"1:{s}")
    D.prims.extend(TBK.primitives(D.fields, sheet))
    g = next((e for e in view["elems"] if e["t"] == "truc"), None)
    D.info = dict(scale=s, sheet=sheet_name, reason=reason, band="L", N=len(g["dung"]) if g else 0, n_columns=0, warnings=sp["warnings"], params=P, extents_paper=(w, hh),
                  n_elements=sp["n_elements"], view_title=meta["title"], nhan_ha_co=meta.get("nhan_ha_co", []))
    return D
