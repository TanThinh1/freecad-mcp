"""Type E, group 2 (phase 3 minimum): electrical / plumbing symbols, wires and pipes, auto legend. Imported by spec_e (registration at the end of this module).

Symbols (ky_hieu) are drawn from the SYMBOLS table below with a FIXED size on paper (mm), centred on vi_tri (their connection node) and rotated by xoay (multiples of 90 degrees).
Wires / pipes (ong) are polylines whose first and last point must equal the position of a declared ky_hieu or nut (no dangling end). Line style comes from existing layers only:
day_dien NET-TAM (chain line), ong_cap NET-CHINH (thick), ong_thoat NET-KHUAT (dashed). The geometry and layout are checked; the DESIGN (loads, pipe sizes, codes) is NOT.
"""
from __future__ import annotations

import math
from fractions import Fraction

import spec_e as S
from primitives import Circle, Line, Rect

# kieu -> (name, group, [("c", cx, cy, r) | ("l", x1, y1, x2, y2) | ("r", x0, y0, x1, y1)])   paper mm, local axes, node at (0, 0)
SYMBOLS = {
    "o_cam": ("Ổ CẮM", "dien", [("c", 0, 0, 2.0), ("l", -2.0, 0, 2.0, 0)]),
    "cong_tac": ("CÔNG TẮC", "dien", [("c", 0, 0, 1.2), ("l", 0.85, 0.85, 3.5, 3.5)]),
    "den": ("ĐÈN", "dien", [("c", 0, 0, 2.5), ("l", -1.77, -1.77, 1.77, 1.77), ("l", -1.77, 1.77, 1.77, -1.77)]),
    "quat": ("QUẠT", "dien", [("c", 0, 0, 3.0), ("l", -3.0, 0, 3.0, 0), ("l", 0, -3.0, 0, 3.0)]),
    "bang_dien": ("BẢNG ĐIỆN", "dien", [("r", -3.0, -2.0, 3.0, 2.0), ("l", -3.0, -2.0, 3.0, 2.0)]),
    "bon_cau": ("BỒN CẦU", "nuoc", [("r", -2.2, -3.6, 2.2, -2.0), ("r", -1.8, -2.0, 1.8, 3.0)]),
    "chau_rua": ("CHẬU RỬA", "nuoc", [("r", -3.5, -2.5, 3.5, 2.5), ("c", 0, 0, 1.2)]),
    "voi": ("VÒI", "nuoc", [("c", 0, 0, 1.0), ("l", 0, 1.0, 0, 2.5), ("l", -1.2, 2.5, 1.2, 2.5)]),
    "van": ("VAN", "nuoc", [("l", -2.0, -1.5, 2.0, 1.5), ("l", -2.0, 1.5, 2.0, -1.5), ("l", -2.0, -1.5, -2.0, 1.5), ("l", 2.0, -1.5, 2.0, 1.5)]),
    "dong_ho_nuoc": ("ĐỒNG HỒ NƯỚC", "nuoc", [("c", 0, 0, 2.5), ("l", -2.5, 0, 2.5, 0)]),
}
PIPES = {"day_dien": ("DÂY ĐIỆN", "NET-TAM"), "ong_cap": ("ỐNG CẤP NƯỚC", "NET-CHINH"), "ong_thoat": ("ỐNG THOÁT NƯỚC", "NET-KHUAT")}
NUT_R = 0.6                 # paper mm, radius of a junction dot
LEG_PITCH, LEG_TITLE = 7.0, 10.0     # paper mm: row pitch of the legend, space under its title
LEG_SAMPLE = 20.0          # paper mm: length of the sample line of a legend row; must show a whole CENTER pattern (12 + 1.5 + 2 + 1.5 = 17 mm), else a chain line looks continuous
LEG_SYM_DX, LEG_TEXT_DX = 10.5, 24.0


def rot(x, y, k):
    for _ in range(k % 4):
        x, y = -y, x
    return x, y


def symbol_prims(kieu, xoay, cx, cy):
    """-> [("c", x, y, r) | ("l", x1, y1, x2, y2) | ("r", x0, y0, x1, y1)] in paper mm around the centre (cx, cy)."""
    k = (xoay // 90) % 4
    out = []
    for p in SYMBOLS[kieu][2]:
        if p[0] == "c":
            x, y = rot(p[1], p[2], k)
            out.append(("c", cx + x, cy + y, p[3]))
        elif p[0] == "l":
            a, b = rot(p[1], p[2], k), rot(p[3], p[4], k)
            out.append(("l", cx + a[0], cy + a[1], cx + b[0], cy + b[1]))
        else:
            a, b = rot(p[1], p[2], k), rot(p[3], p[4], k)
            out.append(("r", cx + min(a[0], b[0]), cy + min(a[1], b[1]), cx + max(a[0], b[0]), cy + max(a[1], b[1])))
    return out


# ------------------------------------------------------------------ validators
def v_ky_hieu(e, path, ctx, view):
    kieu = S.choice(e, "kieu", tuple(SYMBOLS), path, ctx)
    p = S.pt(e.get("vi_tri"), "vi_tri", path, ctx)
    xoay = S.choice(e, "xoay", (0, 90, 180, 270), path, ctx, 0)
    return dict(kieu=kieu, vi_tri=p, xoay=xoay) if kieu and p and xoay is not None else None


def v_nut(e, path, ctx, view):
    p = S.pt(e.get("vi_tri"), "vi_tri", path, ctx)
    return dict(vi_tri=p) if p else None


def v_ong(e, path, ctx, view):
    loai = S.choice(e, "loai_ong", tuple(PIPES), path, ctx)
    d = S.pts(e.get("diem"), "diem", path, ctx, 2)
    if not loai or not d:
        return None
    for i in range(len(d) - 1):
        if d[i] == d[i + 1]:
            ctx.err(path, f"diem[{i}] và diem[{i + 1}] trùng nhau.")
            return None
    return dict(loai_ong=loai, diem=d)


def v_chu_giai(e, path, ctx, view):
    p = S.pt(e.get("vi_tri"), "vi_tri", path, ctx)
    return dict(vi_tri=p) if p else None


NEW = {"ky_hieu": (v_ky_hieu, True, {"kieu", "vi_tri", "xoay"}), "nut": (v_nut, True, {"vi_tri"}), "ong": (v_ong, True, {"loai_ong", "diem"}), "chu_giai": (v_chu_giai, False, {"vi_tri"})}


def check_pipes(view, ctx):
    """Second pass: both ends of every wire / pipe equal the position of a declared ky_hieu or nut (exact)."""
    if view["failed"]:
        return                       # a symbol that failed validation has no position: report that first, not a cascade of "dangling" ends
    nodes = {e["vi_tri"] for e in view["elems"] if e["t"] in ("ky_hieu", "nut")}
    for e in (q for q in view["elems"] if q["t"] == "ong"):
        for name, p in (("điểm đầu", e["diem"][0]), ("điểm cuối", e["diem"][-1])):
            if p not in nodes:
                ctx.err(e["path"], f"{name} [{S.fnum(p[0])}, {S.fnum(p[1])}] của đường {e['loai_ong']} không trùng thiết bị (ky_hieu.vi_tri) hay nút nào đã khai: đầu mút lơ lửng. Sửa toạ độ hoặc khai thêm một phần tử nut tại đó.")


def used(view):
    """legend entries in the fixed order: [(kind, name, 'sym' | 'pipe')] for the symbols and pipe types that appear in the view."""
    ks = {e["kieu"] for e in view["elems"] if e["t"] == "ky_hieu"}
    ps = {e["loai_ong"] for e in view["elems"] if e["t"] == "ong"}
    return [(k, SYMBOLS[k][0], "sym") for k in SYMBOLS if k in ks] + [(k, PIPES[k][0], "pipe") for k in PIPES if k in ps]


# ------------------------------------------------------------------ geometry
def add_symbol(W, tag, kieu, xoay, cx, cy):
    for p in symbol_prims(kieu, xoay, cx, cy):
        if p[0] == "c":
            W.add(Circle(layer="NET-MANH", tag=tag, c=(p[1], p[2]), r=p[3]))
        elif p[0] == "l":
            W.add(Line(layer="NET-MANH", tag=tag, p1=(p[1], p[2]), p2=(p[3], p[4])))
        else:
            W.add(Rect(layer="NET-MANH", tag=tag, p0=(p[1], p[2]), p1=(p[3], p[4])))


def geom(sp, view, W, X):
    for e in view["elems"]:
        t, eid = e["t"], e.get("id")
        if t == "ky_hieu":
            add_symbol(W, f"sym:{eid}", e["kieu"], e["xoay"], X(e["vi_tri"][0]), X(e["vi_tri"][1]))
        elif t == "nut":
            W.add(Circle(layer="NET-MANH", tag=f"nut:{eid}", c=(X(e["vi_tri"][0]), X(e["vi_tri"][1])), r=NUT_R))
        elif t == "ong":
            for a, b in zip(e["diem"], e["diem"][1:]):
                W.line(PIPES[e["loai_ong"]][1], f"ong:{eid}", (X(a[0]), X(a[1])), (X(b[0]), X(b[1])))
        elif t == "chu_giai":
            ax, ay = X(e["vi_tri"][0]), X(e["vi_tri"][1])
            for k, (kind, name, typ) in enumerate(used(view)):
                y = ay - LEG_TITLE - k * LEG_PITCH
                if typ == "sym":
                    add_symbol(W, f"legend_sym:{kind}", kind, 0, ax + LEG_SYM_DX, y)
                else:
                    W.line(PIPES[kind][1], f"legend_line:{kind}", (ax + 0.5, y), (ax + 0.5 + LEG_SAMPLE, y))


def labels3(sp, view, W, X):
    P = sp["params"]
    for e in view["elems"]:
        if e["t"] == "chu_giai":
            ax, ay = X(e["vi_tri"][0]), X(e["vi_tri"][1])
            W.place(f"legend_title:{e['idx']}", "CHU", "CHÚ GIẢI", 3.5, [((ax, ay - 3.5), "left", 0.0)], e["path"], bold=True)
            for k, (kind, name, typ) in enumerate(used(view)):
                y = ay - LEG_TITLE - k * LEG_PITCH
                W.place(f"legend_text:{kind}", "CHU", name, P["cao_chu_ghi_chu"], [((ax + LEG_TEXT_DX, y - P["cao_chu_ghi_chu"] / 2), "left", 0.0)], e["path"])


S.CATALOG.update(NEW)
S.ONCE = tuple(S.ONCE) + ("chu_giai",)
