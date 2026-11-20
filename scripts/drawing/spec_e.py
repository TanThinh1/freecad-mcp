"""Spec schema + input validation for drawing type E ("ve_tu_do": free-form civil drawing built from a closed list of elements).

spec = {ty_le, kho_giay, khung_ten, tham_so, hinh: [ {id, ten, ty_le?, phan_tu: [ {loai: ..., ...}, ... ]} ]}. Model coordinates are real mm, y up. Numbers are kept exact
(Fraction); nothing is rounded silently. Every error is a Vietnamese message that names the element (index, loai, id) and the wrong parameter. Dimensions are never typed:
`kich_thuoc` only NAMES the references (axes, wall faces, openings, rooms, furniture, circles, points) and the builder measures them.

Phase 1 elements: truc, tuong, cua_di, cua_so, o_trong, phong, kich_thuoc, ghi_chu, tieu_de_hinh, mui_ten_bac, noi_that_co_ban and the raw elements duong, polyline, cung,
tron, chu (the escape hatch). Layers come from the standard 18-layer profile only (see LAYER_OF); no layer is created.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal
from fractions import Fraction

from spec_b import DEFAULT_PARAMS, SpecError, parse_khung_ten, parse_kho, parse_params, parse_ten
from tcvn import cons_width
from primitives import cap_to_em

MAX_ELEMENTS = 2000
MAX_COORD = 10_000_000
SCALES_E = (2, 5, 10, 20, 50, 100, 200, 500)      # reduction series of the profile (TCVN 7286:2003) up to 1:500
AUTO_SCALES = (20, 50, 100, 200, 500)             # "auto" tries these; 1:2, 1:5, 1:10 only when the user asks for them (detail drawings)
MAX_LINE_MM = 115.0                               # paper mm: every note line stays under 120 mm (a longer PDF text run is merged into one path that check 5.5 skips)
ID_RE = re.compile(r"[A-Za-z0-9_\-]{1,32}")
CTRL = re.compile("[\x00-\x1f\x7f\ud800-\udfff]")
TEXT_HEIGHTS = (2.5, 3.5, 5.0)                    # paper mm (TCVN 6-... text heights of the profile)
RAW_LAYERS = ("NET-CHINH", "NET-MANH", "NET-KHUAT", "NET-TAM")
# Layer map (profile.yaml has no wall / door / furniture layer, so the civil groups reuse the closest standard ones; nothing is created):
LAYER_OF = {"tuong": "NET-CHINH", "cua_di": "NET-MANH", "cua_so": "NET-MANH", "noi_that": "NET-MANH", "truc": "TRUC", "truc_ky_hieu": "TRUC-KYHIEU",
            "kich_thuoc": "KICH-THUOC", "chu": "CHU", "mui_ten_bac": "NET-MANH"}
# (width, depth, label) real mm of the basic furniture blocks
FURNITURE = {"giuong": (1600, 2000, "GIƯỜNG"), "ban": (1200, 600, "BÀN"), "ghe": (450, 450, "GHẾ"), "tu": (1200, 600, "TỦ"), "bep": (2000, 600, "BẾP"),
             "bon_rua": (800, 500, "BỒN RỬA"), "bon_cau": (400, 700, "BỒN CẦU"), "lavabo": (500, 400, "LAVABO")}
DOOR_MIN_SOFT = 700                                # mm, practical minimum clear width of a door (project experience, NOT a TCVN clause)
WALL_SOFT = (100, 500)                             # mm, usual wall thickness range (project experience, NOT a TCVN clause)
DEFAULT_PARAMS_E = dict(DEFAULT_PARAMS)
DEFAULT_PARAMS_E.update(cao_chu_ten_phong=3.5, cao_chu_noi_that=2.0, le_chu=1.5, ban_kinh_mui_ten_bac=7.0)
ARC_STEPS_90 = 24                                  # an arc is a polyline of straight segments (24 per 90 degrees: sagitta < 0.01 mm paper for a 900 mm door at 1:50)
EXTENT_NOTE = "kinh nghiệm thực tế, KHÔNG phải điều khoản TCVN"


def fr(v) -> Fraction:
    """Exact value of the decimal a JSON number prints as."""
    return v if isinstance(v, Fraction) else (Fraction(v) if isinstance(v, int) else Fraction(Decimal(repr(float(v)))))


def fnum(v: Fraction) -> str:
    return f"{float(v):g}"


class Ctx:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, path, msg):
        self.errors.append(f"{path}: {msg}")


def num(e, key, path, ctx, *, positive=False, nonneg=False, default=None):
    v = e.get(key, default)
    if v is None:
        ctx.err(path, f"thiếu {key} (số, mm).")
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        ctx.err(path, f"{key} = {v!r} phải là số hữu hạn.")
        return None
    if abs(v) > MAX_COORD:
        ctx.err(path, f"{key} = {v!r} quá lớn (> {MAX_COORD}); đơn vị là mm.")
        return None
    x = fr(v)
    if positive and x <= 0:
        ctx.err(path, f"{key} = {v:g} phải lớn hơn 0.")
        return None
    if nonneg and x < 0:
        ctx.err(path, f"{key} = {v:g} không được âm.")
        return None
    return x


def pt(v, name, path, ctx):
    if not isinstance(v, (list, tuple)) or len(v) != 2 or any(isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or abs(c) > MAX_COORD for c in v):
        ctx.err(path, f"{name} = {v!r} phải là điểm [x, y] gồm 2 số hữu hạn (mm).")
        return None
    return (fr(v[0]), fr(v[1]))


def pts(v, name, path, ctx, minimum=2):
    if not isinstance(v, list) or len(v) < minimum:
        ctx.err(path, f"{name} phải là danh sách ít nhất {minimum} điểm [x, y].")
        return None
    out = [pt(p, f"{name}[{k}]", path, ctx) for k, p in enumerate(v)]
    return None if any(p is None for p in out) else out


def text_of(e, key, path, ctx, required=True):
    v = e.get(key)
    if v is None:
        if required:
            ctx.err(path, f"thiếu {key} (chuỗi).")
        return None
    if not isinstance(v, str) or not v.strip() or CTRL.search(v):
        ctx.err(path, f"{key} = {v!r} phải là chuỗi không rỗng, không chứa ký tự điều khiển / xuống dòng (dùng danh sách các dòng cho nhiều dòng).")
        return None
    return v.strip()


def choice(e, key, allowed, path, ctx, default=None):
    v = e.get(key, default)
    if v not in allowed:
        ctx.err(path, f"{key} = {v!r} không hợp lệ; dùng một trong: {', '.join(repr(a) for a in allowed)}.")
        return None
    return v


def text_height(e, key, path, ctx, default=2.5):
    v = e.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or float(v) not in TEXT_HEIGHTS:
        ctx.err(path, f"{key} = {v!r} không hợp lệ; chiều cao chữ trên giấy là một trong {', '.join(f'{h:g}' for h in TEXT_HEIGHTS)} mm.")
        return None
    return float(v)


def line_ok(s, cao, bold, path, key, ctx):
    from tcvn import cons_width as cw
    w = cw(s, cap_to_em(cao), 1.0, bold)
    if w > MAX_LINE_MM:
        ctx.err(path, f"{key}: dòng {s[:30]!r}... rộng {w:.0f} mm trên giấy, vượt {MAX_LINE_MM:g} mm; ngắt thành nhiều dòng (danh sách) hoặc rút gọn.")
    return w


# ------------------------------------------------------------------ geometry helpers shared with the builder (verify_e has its own copies)
def sign(x: Fraction) -> int:
    return (x > 0) - (x < 0)


def wall_legs(w: dict) -> list[dict]:
    """Legs of a wall element: dict(a, b, d (unit axis step), n (left normal), length, lo, hi, ext0, ext1) - exact."""
    p = w["diem"]
    segs = [(p[i], p[i + 1]) for i in range(len(p) - 1)] + ([(p[-1], p[0])] if w["kin"] else [])
    day = w["day"]
    lo, hi = {"giua": (-day / 2, day / 2), "trai": (Fraction(0), day), "phai": (-day, Fraction(0))}[w["can"]]
    out = []
    for i, (a, b) in enumerate(segs):
        d = (sign(b[0] - a[0]), sign(b[1] - a[1]))
        joint0, joint1 = w["kin"] or i > 0, w["kin"] or i < len(segs) - 1
        ext = day / 2 if w["can"] == "giua" else Fraction(0)
        out.append(dict(a=a, b=b, d=d, n=(-d[1], d[0]), length=abs(b[0] - a[0]) + abs(b[1] - a[1]), lo=lo, hi=hi, ext0=ext if joint0 else Fraction(0), ext1=ext if joint1 else Fraction(0)))
    return out


def leg_rect(leg: dict, t0: Fraction, t1: Fraction):
    """Rectangle (x0, y0, x1, y1) of the wall body between the along-leg parameters t0 < t1 (t = 0 at the leg start point)."""
    (ax, ay), d, n = leg["a"], leg["d"], leg["n"]
    c = [(ax + d[0] * t + n[0] * o, ay + d[1] * t + n[1] * o) for t in (t0, t1) for o in (leg["lo"], leg["hi"])]
    xs, ys = [q[0] for q in c], [q[1] for q in c]
    return (min(xs), min(ys), max(xs), max(ys))


def leg_pieces(leg: dict, cuts: list[tuple]) -> list[tuple]:
    """Along-leg intervals of the wall body that remain after the openings `cuts` = [(v, v + w)] (sorted, inside [0, length])."""
    out, cur = [], -leg["ext0"]
    for v0, v1 in cuts:
        if v0 > cur:
            out.append((cur, v0))
        cur = v1
    if leg["length"] + leg["ext1"] > cur:
        out.append((cur, leg["length"] + leg["ext1"]))
    return out


def point_in_polygon(p, poly) -> bool:
    """Inside or on the boundary of a rectilinear / general polygon (exact)."""
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (x2 - x1) * (y - y1) == (y2 - y1) * (x - x1) and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
            return True
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def polygon_area(poly) -> Fraction:
    s = Fraction(0)
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def door_sweep_hits(view, d, box) -> bool:
    """True when the rectangle `box` meets the quarter disc swept by the leaf of the door element d (centre = hinge on the swing face, radius = rong). Exact."""
    w = view["by_id"].get(d["tuong"])
    if w is None:
        return False
    L = wall_legs(w)[d["doan"]]
    v, r = d["vi_tri"], d["rong"]
    th = v if d["ban_le"] == "dau" else v + r
    off = L["hi"] if d["mo_ve"] == "trai" else L["lo"]
    H = (L["a"][0] + L["d"][0] * th + L["n"][0] * off, L["a"][1] + L["d"][1] * th + L["n"][1] * off)
    dc = L["d"] if d["ban_le"] == "dau" else (-L["d"][0], -L["d"][1])
    sw = 1 if d["mo_ve"] == "trai" else -1
    ns = (sw * L["n"][0], sw * L["n"][1])
    cs = [((x - H[0]) * dc[0] + (y - H[1]) * dc[1], (x - H[0]) * ns[0] + (y - H[1]) * ns[1]) for x in (box[0], box[2]) for y in (box[1], box[3])]
    u0, u1, v0, v1 = min(c[0] for c in cs), max(c[0] for c in cs), min(c[1] for c in cs), max(c[1] for c in cs)
    return u1 > 0 and v1 > 0 and max(u0, 0) ** 2 + max(v0, 0) ** 2 < r * r


def fmt2(v: Fraction) -> str:
    """Two decimals with a comma, rounded half up (exact)."""
    m = math.floor(v * 100 + Fraction(1, 2))
    return f"{m // 100},{m % 100:02d}"


def fmt_len(v: Fraction) -> str:
    """Dimension label: whole mm, half up."""
    return str(math.floor(v + Fraction(1, 2)))


# ------------------------------------------------------------------ element validators (each returns the normalised element or None)
def v_truc(e, path, ctx, view):
    out = dict(dung=[], ngang=[])
    for key, field, axis in (("truc_dung", "x", "dung"), ("truc_ngang", "y", "ngang")):
        lst = e.get(key)
        if not isinstance(lst, list) or not lst:
            ctx.err(path, f"thiếu {key}: danh sách các trục dạng {{\"ten\": \"1\", \"{field}\": số mm}}.")
            continue
        for k, a in enumerate(lst):
            ap = f"{path}.{key}[{k}]"
            if not isinstance(a, dict):
                ctx.err(ap, "phải là {\"ten\": ..., \"" + field + "\": ...}.")
                continue
            ten = a.get("ten")
            v = num(a, field, ap, ctx)
            if not isinstance(ten, str) or not (1 <= len(ten) <= 3) or CTRL.search(ten):
                ctx.err(ap, f"ten = {ten!r} phải là chuỗi 1-3 ký tự (ghi trong vòng tròn ký hiệu trục).")
            elif v is not None:
                out[axis].append((ten, v))
        names = [t for t, _ in out[axis]]
        if len(set(names)) != len(names):
            ctx.err(path, f"{key}: tên trục trùng nhau ({', '.join(sorted(n for n in set(names) if names.count(n) > 1))}).")
        vals = [v for _, v in out[axis]]
        if len(set(vals)) != len(vals):
            ctx.err(path, f"{key}: hai trục cùng vị trí.")
    if set(t for t, _ in out["dung"]) & set(t for t, _ in out["ngang"]):
        ctx.err(path, "tên trục dọc và trục ngang trùng nhau (dùng số cho trục dọc, chữ cái cho trục ngang).")
    return out


def v_tuong(e, path, ctx, view):
    p = pts(e.get("diem"), "diem", path, ctx, 2)
    day = num(e, "day", path, ctx, positive=True)
    kin = e.get("kin", False)
    if not isinstance(kin, bool):
        ctx.err(path, f"kin = {kin!r} phải là true hoặc false.")
        kin = False
    can = choice(e, "can", ("giua", "trai", "phai"), path, ctx, "giua")
    kieu = choice(e, "kieu", ("2_net", "1_net"), path, ctx, "2_net")
    if p is None or day is None or can is None or kieu is None:
        return None
    if kin and len(p) < 3:
        ctx.err(path, "kin = true cần ít nhất 3 điểm.")
    if (kin or len(p) > 2) and can != "giua":
        ctx.err(path, f"can = {can!r} chỉ dùng cho tường một đoạn (2 điểm); tường nhiều đoạn / khép kín chỉ nhận can = \"giua\" (đường đi qua tim tường).")
    segs = [(p[i], p[i + 1]) for i in range(len(p) - 1)] + ([(p[-1], p[0])] if kin else [])
    for i, (a, b) in enumerate(segs):
        if a == b:
            ctx.err(path, f"đoạn {i} có hai đầu trùng nhau {fnum(a[0])},{fnum(a[1])}.")
        elif a[0] != b[0] and a[1] != b[1]:
            ctx.err(path, f"đoạn {i} từ [{fnum(a[0])}, {fnum(a[1])}] đến [{fnum(b[0])}, {fnum(b[1])}] là đường xiên; giai đoạn này chỉ nhận tường nằm ngang hoặc đứng (x hoặc y không đổi).")
    if not (WALL_SOFT[0] <= day <= WALL_SOFT[1]):
        ctx.warnings.append(f"{path}: day = {fnum(day)} mm ngoài khoảng {WALL_SOFT[0]}-{WALL_SOFT[1]} mm thường dùng ({EXTENT_NOTE}); cần người thiết kế xác nhận.")
    return dict(diem=p, day=day, kin=kin, can=can, kieu=kieu)


def v_opening(e, path, ctx, view):
    """cua_di / cua_so / o_trong share the wall reference; the wall is resolved in the second pass."""
    wid = e.get("tuong")
    doan = e.get("doan", 0)
    if isinstance(doan, bool) or not isinstance(doan, int) or doan < 0:
        ctx.err(path, f"doan = {doan!r} phải là số nguyên không âm (chỉ số đoạn của tường, tính từ 0).")
        doan = 0
    return dict(tuong=wid, doan=doan, vi_tri=num(e, "vi_tri", path, ctx, nonneg=True), rong=num(e, "rong", path, ctx, positive=True))


def v_cua_di(e, path, ctx, view):
    o = v_opening(e, path, ctx, view)
    o["ban_le"] = choice(e, "ban_le", ("dau", "cuoi"), path, ctx)
    o["mo_ve"] = choice(e, "mo_ve", ("trai", "phai"), path, ctx)
    if o["rong"] is not None and o["rong"] < DOOR_MIN_SOFT:
        ctx.warnings.append(f"{path}: cửa đi rộng {fnum(o['rong'])} mm, hẹp hơn {DOOR_MIN_SOFT} mm ({EXTENT_NOTE}); cần người thiết kế xác nhận.")
    return o


def v_cua_so(e, path, ctx, view):
    o = v_opening(e, path, ctx, view)
    o["ky_hieu"] = choice(e, "ky_hieu", ("kep", "ba"), path, ctx, "kep")
    return o


def v_o_trong(e, path, ctx, view):
    return v_opening(e, path, ctx, view)


def v_phong(e, path, ctx, view):
    ten = text_of(e, "ten", path, ctx)
    poly = pts(e.get("da_giac"), "da_giac", path, ctx, 3)
    out = dict(ten=ten, da_giac=poly, vi_tri_nhan=None)
    if "vi_tri_nhan" in e:
        out["vi_tri_nhan"] = pt(e["vi_tri_nhan"], "vi_tri_nhan", path, ctx)
    if ten is None or poly is None:
        return None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        if a == b or (a[0] != b[0] and a[1] != b[1]):
            ctx.err(path, f"da_giac: cạnh {i} không nằm ngang/đứng hoặc có hai đầu trùng nhau (đường bao phòng chỉ gồm cạnh ngang/đứng).")
    if polygon_area(poly) == 0:
        ctx.err(path, "da_giac có diện tích 0.")
    if out["vi_tri_nhan"] is not None and not point_in_polygon(out["vi_tri_nhan"], poly):
        ctx.err(path, "vi_tri_nhan nằm ngoài da_giac.")
    out["dien_tich"] = polygon_area(poly) / 1_000_000          # m2, exact
    return out


def v_noi_that(e, path, ctx, view):
    kind = choice(e, "kieu", tuple(FURNITURE), path, ctx)
    p = pt(e.get("vi_tri"), "vi_tri", path, ctx)
    xoay = choice(e, "xoay", (0, 90, 180, 270), path, ctx, 0)
    if kind is None:
        return None
    w, d, label = FURNITURE[kind]
    if "kich_thuoc" in e:
        ks = e["kich_thuoc"]
        if not isinstance(ks, list) or len(ks) != 2 or any(isinstance(c, bool) or not isinstance(c, (int, float)) or c <= 0 or c > MAX_COORD for c in ks):
            ctx.err(path, f"kich_thuoc = {ks!r} phải là [rộng, sâu] hai số dương (mm).")
        else:
            w, d = fr(ks[0]), fr(ks[1])
    if p is None or xoay is None:
        return None
    ww, dd = (fr(w), fr(d)) if xoay in (0, 180) else (fr(d), fr(w))
    return dict(kieu=kind, vi_tri=p, xoay=xoay, w=fr(w), d=fr(d), box=(p[0], p[1], p[0] + ww, p[1] + dd), nhan=label)


def v_ghi_chu(e, path, ctx, view):
    chu = e.get("chu")
    lines = chu if isinstance(chu, list) else [chu]
    cao = text_height(e, "cao", path, ctx)
    dam = e.get("dam", False)
    if not isinstance(dam, bool):
        ctx.err(path, f"dam = {dam!r} phải là true hoặc false.")
        dam = False
    ok = []
    for k, ln in enumerate(lines):
        t = text_of({"chu": ln}, "chu", f"{path}.chu[{k}]", ctx)
        if t is not None and cao is not None:
            line_ok(t, cao, dam, path, f"chu[{k}]", ctx)
            ok.append(t)
    p = pt(e.get("vi_tri"), "vi_tri", path, ctx)
    can = choice(e, "can", ("trai", "giua", "phai"), path, ctx, "trai")
    if p is None or not ok or cao is None or can is None:
        return None
    return dict(dong=ok, vi_tri=p, cao=cao, dam=dam, can=can)


def v_tieu_de(e, path, ctx, view):
    t = text_of(e, "chu", path, ctx, required=False)
    if t and cons_width(t, cap_to_em(5.0), 1.0, True) > MAX_LINE_MM:
        ctx.err(path, f"chu = {t[:30]!r}...: chữ đậm cao 5 mm rộng {cons_width(t, cap_to_em(5.0), 1.0, True):.0f} mm, vượt {MAX_LINE_MM:g} mm; rút gọn.")
    return dict(chu=t)


def v_bac(e, path, ctx, view):
    g = e.get("goc", 0)
    if isinstance(g, bool) or not isinstance(g, (int, float)) or not math.isfinite(g):
        ctx.err(path, f"goc = {g!r} phải là số (độ, ngược chiều kim đồng hồ từ trục y; 0 = bắc hướng lên).")
        g = 0
    return dict(vi_tri=pt(e.get("vi_tri"), "vi_tri", path, ctx), goc=fr(g))


def v_duong(e, path, ctx, view):
    return dict(tu=pt(e.get("tu"), "tu", path, ctx), den=pt(e.get("den"), "den", path, ctx), lop=choice(e, "lop", RAW_LAYERS, path, ctx, "NET-MANH"))


def v_polyline(e, path, ctx, view):
    kin = e.get("kin", False)
    if not isinstance(kin, bool):
        ctx.err(path, f"kin = {kin!r} phải là true hoặc false.")
        kin = False
    return dict(diem=pts(e.get("diem"), "diem", path, ctx, 2), kin=kin, lop=choice(e, "lop", RAW_LAYERS, path, ctx, "NET-MANH"))


def v_tron(e, path, ctx, view):
    return dict(tam=pt(e.get("tam"), "tam", path, ctx), ban_kinh=num(e, "ban_kinh", path, ctx, positive=True), lop=choice(e, "lop", RAW_LAYERS, path, ctx, "NET-MANH"))


def v_cung(e, path, ctx, view):
    o = v_tron(e, path, ctx, view)
    o["goc_dau"], o["goc_cuoi"] = num(e, "goc_dau", path, ctx), num(e, "goc_cuoi", path, ctx)
    if o["goc_dau"] is not None and o["goc_cuoi"] is not None:
        sweep = (o["goc_cuoi"] - o["goc_dau"]) % 360
        if sweep == 0:
            ctx.err(path, "goc_dau và goc_cuoi trùng nhau (cung quét ngược chiều kim đồng hồ từ goc_dau tới goc_cuoi; dùng tron cho vòng tròn).")
        o["quet"] = sweep
    return o


def v_chu(e, path, ctx, view):
    cao = text_height(e, "cao", path, ctx)
    dam = e.get("dam", False)
    s = text_of(e, "chu", path, ctx)
    if s is not None and cao is not None:
        line_ok(s, cao, bool(dam), path, "chu", ctx)
    return dict(chu=s, vi_tri=pt(e.get("vi_tri"), "vi_tri", path, ctx), cao=cao, dam=bool(dam), can=choice(e, "can", ("trai", "giua", "phai"), path, ctx, "trai"))


def v_kich_thuoc(e, path, ctx, view):
    kieu = choice(e, "kieu", ("ngang", "doc", "chuoi", "song_song", "ban_kinh", "duong_kinh", "goc"), path, ctx)
    out = dict(kieu=kieu)
    if kieu in ("ngang", "doc", "chuoi"):
        refs = e.get("tham_chieu")
        need = 3 if kieu == "chuoi" else 2
        if not isinstance(refs, list) or len(refs) < need or (kieu != "chuoi" and len(refs) != 2):
            ctx.err(path, f"tham_chieu phải là danh sách {'ít nhất 3' if kieu == 'chuoi' else 'đúng 2'} tham chiếu (số toạ độ, \"truc:<ten>\", \"<id>:<mốc>\").")
            refs = None
        out["tham_chieu"] = refs
        out["huong"] = {"ngang": "ngang", "doc": "doc"}.get(kieu) or choice(e, "huong", ("ngang", "doc"), path, ctx)
        sides = ("duoi", "tren") if out["huong"] == "ngang" else ("trai", "phai")
        out["phia"] = choice(e, "phia", sides, path, ctx, sides[0])
        lop = e.get("lop", 1)
        if isinstance(lop, bool) or lop not in (1, 2, 3):
            ctx.err(path, f"lop = {lop!r} phải là 1, 2 hoặc 3 (lớp kích thước tính từ hình ra ngoài).")
            lop = 1
        out["lop"] = lop
    elif kieu == "song_song":
        r = e.get("tham_chieu")
        out["p"] = [pt(r[0], "tham_chieu[0]", path, ctx), pt(r[1], "tham_chieu[1]", path, ctx)] if isinstance(r, list) and len(r) == 2 else None
        if out["p"] is None:
            ctx.err(path, "tham_chieu phải là 2 điểm [x, y].")
        out["phia"] = choice(e, "phia", ("trai", "phai"), path, ctx, "trai")
        out["khoang"] = num(e, "khoang", path, ctx, positive=True, default=10)
    elif kieu in ("ban_kinh", "duong_kinh"):
        out["phan_tu"] = e.get("phan_tu")
        g = e.get("goc", 45)
        if isinstance(g, bool) or not isinstance(g, (int, float)) or not math.isfinite(g):
            ctx.err(path, f"goc = {g!r} phải là số (độ).")
            g = 45
        out["goc"] = fr(g)
    elif kieu == "goc":
        out["dinh"], out["tia1"], out["tia2"] = (pt(e.get(k), k, path, ctx) for k in ("dinh", "tia1", "tia2"))
        out["ban_kinh_cung"] = num(e, "ban_kinh_cung", path, ctx, positive=True, default=15)
    return out if kieu else None


# loai -> (validator, needs id, required keys / allowed keys)
CATALOG = {
    "truc": (v_truc, False, {"truc_dung", "truc_ngang"}),
    "tuong": (v_tuong, True, {"diem", "kin", "day", "can", "kieu"}),
    "cua_di": (v_cua_di, True, {"tuong", "doan", "vi_tri", "rong", "ban_le", "mo_ve"}),
    "cua_so": (v_cua_so, True, {"tuong", "doan", "vi_tri", "rong", "ky_hieu"}),
    "o_trong": (v_o_trong, True, {"tuong", "doan", "vi_tri", "rong"}),
    "phong": (v_phong, True, {"ten", "da_giac", "vi_tri_nhan"}),
    "kich_thuoc": (v_kich_thuoc, True, {"kieu", "tham_chieu", "huong", "phia", "lop", "khoang", "phan_tu", "goc", "dinh", "tia1", "tia2", "ban_kinh_cung"}),
    "ghi_chu": (v_ghi_chu, False, {"chu", "vi_tri", "can", "cao", "dam"}),
    "tieu_de_hinh": (v_tieu_de, False, {"chu"}),
    "mui_ten_bac": (v_bac, False, {"vi_tri", "goc"}),
    "noi_that_co_ban": (v_noi_that, True, {"kieu", "vi_tri", "xoay", "kich_thuoc"}),
    "duong": (v_duong, False, {"tu", "den", "lop"}),
    "polyline": (v_polyline, False, {"diem", "kin", "lop"}),
    "cung": (v_cung, True, {"tam", "ban_kinh", "goc_dau", "goc_cuoi", "lop"}),
    "tron": (v_tron, True, {"tam", "ban_kinh", "lop"}),
    "chu": (v_chu, False, {"chu", "vi_tri", "cao", "dam", "can"}),
}
ONCE = ("truc", "tieu_de_hinh")        # at most one per view


# ------------------------------------------------------------------ references of the measured dimensions
def wall_of(view, eid):
    e = view["by_id"].get(eid)
    return e if e and e["t"] == "tuong" else None


def resolve(view, ref, want, path, ctx):
    """ref -> (exact scalar coordinate, 'x' | 'y') or None (error recorded). want = 'x' | 'y' | None."""
    if isinstance(ref, (int, float)) and not isinstance(ref, bool):
        if want is None or not math.isfinite(ref):
            ctx.err(path, f"tham chiếu {ref!r} không dùng được ở đây.")
            return None
        return fr(ref), want
    if not isinstance(ref, str) or ":" not in ref:
        ctx.err(path, f"tham chiếu {ref!r} không hiểu được; dùng số toạ độ, \"truc:<ten>\" hoặc \"<id>:<mốc>\" (mốc: dau, cuoi, trai, phai, giua cho tường; dau, cuoi cho cửa; tay, dong, nam, bac cho phòng/nội thất/tròn/cung).")
        return None
    head, anchor = ref.rsplit(":", 1)
    if head == "truc":
        g = next((e for e in view["elems"] if e["t"] == "truc"), None)
        for ten, v in (g["dung"] if g else []):
            if ten == anchor:
                return v, "x"
        for ten, v in (g["ngang"] if g else []):
            if ten == anchor:
                return v, "y"
        ctx.err(path, f"tham chiếu {ref!r}: không có trục tên {anchor!r}.")
        return None
    k = 0
    if "#" in head:
        head, ks = head.split("#", 1)
        k = int(ks) if ks.isdigit() else -1
    e = view["by_id"].get(head)
    if e is None:
        if head not in view["failed"]:
            ctx.err(path, f"tham chiếu {ref!r}: không có phần tử id {head!r}.")
        return None
    t = e["t"]
    if t == "tuong":
        legs = wall_legs(e)
        if not (0 <= k < len(legs)):
            ctx.err(path, f"tham chiếu {ref!r}: tường {head!r} có {len(legs)} đoạn (chỉ số 0..{len(legs) - 1}).")
            return None
        L = legs[k]
        horizontal = L["d"][1] == 0
        if anchor in ("trai", "phai", "giua"):
            off = {"trai": L["hi"], "phai": L["lo"], "giua": Fraction(0)}[anchor]
            return (L["a"][1] + L["n"][1] * off, "y") if horizontal else (L["a"][0] + L["n"][0] * off, "x")
        if anchor in ("dau", "cuoi"):
            p = L["a"] if anchor == "dau" else L["b"]
            return (p[0], "x") if horizontal else (p[1], "y")
    elif t in ("cua_di", "cua_so", "o_trong") and anchor in ("dau", "cuoi"):
        w = wall_of(view, e["tuong"])
        if w is None:
            return None
        legs = wall_legs(w)
        if e["doan"] >= len(legs):
            return None
        L = legs[e["doan"]]
        s = e["vi_tri"] if anchor == "dau" else e["vi_tri"] + e["rong"]
        x, y = L["a"][0] + L["d"][0] * s, L["a"][1] + L["d"][1] * s
        return (x, "x") if L["d"][1] == 0 else (y, "y")
    elif anchor in ("tay", "dong", "nam", "bac"):
        box = None
        if t == "phong":
            xs, ys = [p[0] for p in e["da_giac"]], [p[1] for p in e["da_giac"]]
            box = (min(xs), min(ys), max(xs), max(ys))
        elif e.get("box") is not None:
            box = e["box"]
        elif t in ("tron", "cung"):
            c, r = e["tam"], e["ban_kinh"]
            box = (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
        if box:
            return {"tay": (box[0], "x"), "dong": (box[2], "x"), "nam": (box[1], "y"), "bac": (box[3], "y")}[anchor]
    ctx.err(path, f"tham chiếu {ref!r}: phần tử {head!r} (loai {t}) không có mốc {anchor!r}.")
    return None


# ------------------------------------------------------------------ top level
def parse_scale_e(ty_le, errors, where="ty_le"):
    if ty_le == "auto":
        return ty_le, None
    m = re.fullmatch(r"1\s*:\s*(\d+)", ty_le) if isinstance(ty_le, str) else None
    if not m or int(m.group(1)) not in SCALES_E:
        errors.append(f"{where} = {ty_le!r} không hợp lệ. Dùng \"auto\" hoặc một trong " + ", ".join(f"1:{s}" for s in SCALES_E) + " (dãy tỷ lệ thu nhỏ của profile, TCVN 7286:2003; \"auto\" chỉ thử 1:20 đến 1:500).")
        return ty_le, None
    return ty_le, int(m.group(1))


def validate(spec) -> dict:
    if not isinstance(spec, dict):
        raise SpecError(["spec phải là một đối tượng JSON {...}."])
    ctx = Ctx()
    errors = ctx.errors
    if spec.get("loai") != "E":
        errors.append(f"loai = {spec.get('loai')!r}: spec_e chỉ xử lý loại E (ve_tu_do).")
    kho = parse_kho(spec.get("kho_giay", "auto"), errors)
    ty_le, scale = parse_scale_e(spec.get("ty_le", "auto"), errors)
    ten = parse_ten(spec.get("ten"), errors)
    kt = parse_khung_ten(spec.get("khung_ten") or {}, errors)
    params = parse_params(spec.get("tham_so") or {}, DEFAULT_PARAMS_E, errors)
    hinh = spec.get("hinh")
    views, total = [], 0
    if not isinstance(hinh, list) or not hinh:
        errors.append("hinh phải là danh sách ít nhất một hình: [{\"id\": \"H1\", \"ten\": \"MẶT BẰNG\", \"phan_tu\": [...]}].")
    elif len(hinh) > 1:
        errors.append(f"hinh có {len(hinh)} phần tử: giai đoạn này chỉ vẽ MỘT hình trên một tờ (nhiều hình trên một tờ chưa hỗ trợ).")
    for vi, h in enumerate(hinh if isinstance(hinh, list) else []):
        hp = f"hinh[{vi}]"
        if not isinstance(h, dict):
            errors.append(f"{hp} phải là đối tượng JSON.")
            continue
        hid = h.get("id", f"H{vi + 1}")
        if not isinstance(hid, str) or not ID_RE.fullmatch(hid):
            errors.append(f"{hp}.id = {hid!r} chỉ dùng chữ cái, số, '_' và '-' (tối đa 32 ký tự).")
        hten = h.get("ten")
        if not isinstance(hten, str) or not hten.strip() or CTRL.search(hten):
            errors.append(f"{hp}.ten = {hten!r} phải là chuỗi không rỗng (tên hình, in dưới hình).")
            hten = ""
        elif cons_width(hten.strip(), cap_to_em(5.0), 1.0, True) > MAX_LINE_MM:
            errors.append(f"{hp}.ten = {hten[:30]!r}...: tên hình in đậm cao 5 mm rộng {cons_width(hten.strip(), cap_to_em(5.0), 1.0, True):.0f} mm, vượt {MAX_LINE_MM:g} mm; rút gọn tên hình.")
        vscale = None
        if "ty_le" in h:
            _, vscale = parse_scale_e(h["ty_le"], errors, f"{hp}.ty_le")
            if vscale and scale and vscale != scale:
                errors.append(f"{hp}.ty_le = 1:{vscale} khác ty_le của bản vẽ 1:{scale}; giai đoạn này mọi hình cùng một tỷ lệ.")
            if h["ty_le"] == "auto":
                vscale = None
        elems = h.get("phan_tu")
        if not isinstance(elems, list) or not elems:
            errors.append(f"{hp}.phan_tu phải là danh sách ít nhất một phần tử.")
            continue
        total += len(elems)
        if total > MAX_ELEMENTS:
            errors.append(f"spec có {total} phần tử, vượt giới hạn {MAX_ELEMENTS}.")
            continue
        mo = None
        if "mo_cao" in h:
            m = h["mo_cao"]
            if not isinstance(m, dict) or set(m) - {"y", "cao_m"} or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in m.values()):
                errors.append(f"{hp}.mo_cao = {m!r} phải là {{\"y\": mm, \"cao_m\": mét}} (mức tham chiếu của ký hiệu cao độ).")
            else:
                mo = (fr(m.get("y", 0)), fr(m.get("cao_m", 0)))
        view = dict(id=hid, ten=hten.strip(), scale=vscale, elems=[], by_id={}, failed=set(), mo_cao=mo)
        views.append(view)
        for i, e in enumerate(elems):
            t = e.get("loai") if isinstance(e, dict) else None
            eid = e.get("id") if isinstance(e, dict) else None
            path = f"{hp}.phan_tu[{i}] (loai={t!r}" + (f", id={eid!r}" if eid is not None else "") + ")"
            if not isinstance(e, dict) or t not in CATALOG:
                errors.append(f"{path}: loai không hợp lệ; dùng một trong: {', '.join(CATALOG)}.")
                continue
            fn, needs_id, keys = CATALOG[t]
            extra = sorted(k for k in e if k not in keys and k not in ("loai", "id"))
            if extra:
                errors.append(f"{path}: tham số không được hỗ trợ: {', '.join(repr(k) for k in extra)}. Tham số của {t}: {', '.join(sorted(keys))} (+ id).")
                continue
            if t in ONCE and any(x["t"] == t for x in view["elems"]):
                errors.append(f"{path}: mỗi hình chỉ có một phần tử loai {t!r}.")
                continue
            if needs_id and eid is None:
                errors.append(f"{path}: thiếu id (chuỗi, duy nhất trong hình).")
            if eid is not None and (not isinstance(eid, str) or not ID_RE.fullmatch(eid)):
                errors.append(f"{path}: id = {eid!r} chỉ dùng chữ cái, số, '_' và '-' (tối đa 32 ký tự).")
                continue
            if eid is not None and eid in view["by_id"]:
                errors.append(f"{path}: id {eid!r} trùng với phần tử chỉ số {view['by_id'][eid]['idx']}.")
                continue
            n_before = len(ctx.errors)
            norm = fn(e, path, ctx, view)
            if norm is None or len(ctx.errors) > n_before:
                if eid is not None:
                    view["failed"].add(eid)           # references to it are not reported again (no cascade of "no such element")
                continue
            norm.update(t=t, id=eid, idx=i, path=path)
            view["elems"].append(norm)
            if eid is not None:
                view["by_id"][eid] = norm
    # ---- second pass: references between elements
    for view in views:
        for e in view["elems"]:
            t, path = e["t"], e["path"]
            if t in ("cua_di", "cua_so", "o_trong"):
                w = wall_of(view, e["tuong"])
                if w is None:
                    if e["tuong"] not in view["failed"]:
                        ctx.err(path, f"tuong = {e['tuong']!r}: không có tường với id này trong hình.")
                    continue
                legs = wall_legs(w)
                if e["doan"] >= len(legs):
                    ctx.err(path, f"doan = {e['doan']}: tường {e['tuong']!r} chỉ có {len(legs)} đoạn (chỉ số 0..{len(legs) - 1}).")
                    continue
                L = legs[e["doan"]]
                v, rong = e["vi_tri"], e["rong"]
                if v is None or rong is None:
                    continue
                if v + rong > L["length"]:
                    view["failed"].add(e["id"])
                    view["by_id"].pop(e["id"], None)         # dimensions that name it are not reported again
                    ctx.err(path, f"cửa nằm ngoài tường: vi_tri + rong = {fnum(v + rong)} mm vượt chiều dài đoạn {e['doan']} của tường {e['tuong']!r} ({fnum(L['length'])} mm). Giảm vi_tri hoặc rong.")
            elif t == "kich_thuoc":
                kieu = e["kieu"]
                if kieu in ("ngang", "doc", "chuoi"):
                    want = {"ngang": "x", "doc": "y"}.get(kieu) or ("x" if e["huong"] == "ngang" else "y")
                    vals = []
                    for k, r in enumerate(e["tham_chieu"] or []):
                        got = resolve(view, r, want, f"{path}.tham_chieu[{k}]", ctx)
                        if got:
                            if got[1] != want:
                                ctx.err(f"{path}.tham_chieu[{k}]", f"tham chiếu {r!r} là toạ độ {got[1]} nhưng kích thước {e['huong'] if kieu == 'chuoi' else kieu} đo theo {want}.")
                            vals.append(got[0])
                    if len(vals) == len(e["tham_chieu"] or []) and vals:
                        if kieu == "chuoi" and any(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)):
                            ctx.err(path, "tham_chieu của chuỗi phải tăng dần (mỗi tham chiếu lớn hơn tham chiếu trước).")
                        if kieu != "chuoi" and vals[0] == vals[1]:
                            ctx.err(path, "hai tham chiếu trùng toạ độ: kích thước bằng 0.")
                        e["vals"] = vals
                elif kieu in ("ban_kinh", "duong_kinh"):
                    c = view["by_id"].get(e["phan_tu"]) if isinstance(e["phan_tu"], str) else None
                    if c is None or c["t"] not in ("tron", "cung"):
                        ctx.err(path, f"phan_tu = {e['phan_tu']!r} phải là id của một phần tử loai tron hoặc cung trong hình.")
                elif kieu == "song_song" and e["p"] and e["p"][0] == e["p"][1]:
                    ctx.err(path, "hai điểm trùng nhau: kích thước bằng 0.")
            elif t == "phong" and e["vi_tri_nhan"] is None:
                xs, ys = [p[0] for p in e["da_giac"]], [p[1] for p in e["da_giac"]]
                c = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
                if not point_in_polygon(c, e["da_giac"]):
                    ctx.err(path, "tâm hộp bao của da_giac nằm ngoài phòng (phòng hình chữ L/U): nhập vi_tri_nhan [x, y] trong phòng.")
                e["nhan"] = c
            elif t == "phong":
                e["nhan"] = e["vi_tri_nhan"]
    for view in views:
        for fe in (q for q in view["elems"] if q["t"] == "noi_that_co_ban"):
            for de in (q for q in view["elems"] if q["t"] == "cua_di"):
                if door_sweep_hits(view, de, fe["box"]):
                    ctx.warnings.append(f"{fe['path']}: nội thất {fe['id']!r} nằm trong vùng quét của cánh cửa đi {de['id']!r} (cánh + cung mở 90°): cửa không mở hết được; dịch nội thất hoặc đổi chiều mở (cảnh báo mềm, bản vẽ vẫn dựng).")
    for view in views:
        elems3.check_pipes(view, ctx)
        elems2.check_levels(view, ctx)
    for view in views:
        legs_ops = {}
        for e in view["elems"]:
            if e["t"] in ("cua_di", "cua_so", "o_trong") and e["vi_tri"] is not None and e["rong"] is not None:
                legs_ops.setdefault((e["tuong"], e["doan"]), []).append(e)
        for (wid, k), ops in legs_ops.items():
            ops.sort(key=lambda o: o["vi_tri"])
            for a, b in zip(ops, ops[1:]):
                if a["vi_tri"] + a["rong"] > b["vi_tri"]:
                    ctx.err(b["path"], f"chồng lên {a['id']!r} (phần tử {a['idx']}) trên đoạn {k} của tường {wid!r}: {a['id']!r} kết thúc ở {fnum(a['vi_tri'] + a['rong'])} mm, {b['id']!r} bắt đầu ở {fnum(b['vi_tri'])} mm.")
    for view in views:
        if not any(e["t"] in ("tuong", "duong", "polyline", "cung", "tron", "noi_that_co_ban", "truc", "lop_vat_lieu", "san", "dam", "cot_mc", "mong_don", "cot_chi_tiet", "cua_dung", "mai", "lan_can", "bac_thang_don_gian", "ky_hieu", "ong") for e in view["elems"]) and view["elems"]:
            ctx.err(f"hinh {view['id']!r}", "hình chưa có phần tử hình học nào (tuong, truc, noi_that_co_ban, duong, polyline, cung, tron).")
    if errors:
        raise SpecError(errors)
    return dict(loai="E", ten=ten, kho_giay=kho, ty_le=ty_le, scale=scale, khung_ten=kt, params=params, views=views, warnings=ctx.warnings, n_elements=total)


import elems2  # noqa: E402,F401
import elems3  # noqa: E402,F401  (electrical / plumbing symbols)
#  (registers the phase 2 elements into CATALOG at its own end; works whichever module is imported first)
