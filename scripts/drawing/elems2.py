"""Type E, phase 2: section / elevation / detail elements (validators + exact geometry used by build_e). Imported by spec_e (registration) and build_e.

Elements: lop_vat_lieu, san, dam, cot_mc, mong_don, cot_chi_tiet (rectangles with HATCH from the closed list MATERIALS), cua_dung, mai, lan_can, bac_thang_don_gian, cao_do,
ghi_chu_dan, dau_cat, tuyen_gio. Hatch = parallel 45-degree lines of fixed paper spacing anchored at the model origin (neighbouring rectangles line up), clipped to the rectangle; layer MAT-CAT.
"""
from __future__ import annotations

import math
from fractions import Fraction

import spec_e as S
from primitives import Circle, Line, Rect

MATERIALS = {"be_tong": [(45, 4.0)], "gach": [(45, 2.0)], "vua": [(-45, 2.0)], "dat": [(45, 3.0), (-45, 3.0)], "thep": [(45, 1.2)]}     # (angle deg, spacing paper mm)
MIN_HATCH_MM = 0.3          # paper mm: a clipped hatch piece shorter than this is not drawn
LAYER_INSET = Fraction(60)  # mm, door / window leaf inset inside the opening
STAIR_SOFT = (600, 630)     # mm, usual range of 2h + b (project experience, NOT a TCVN clause)
RAIL_MIN_SOFT = 900         # mm, usual minimum railing height (project experience, NOT a TCVN clause)


# ------------------------------------------------------------------ validators
def _box(e, key, path, ctx):
    h = e.get(key)
    if not isinstance(h, list) or len(h) != 4 or any(isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or abs(c) > S.MAX_COORD for c in h):
        ctx.err(path, f"{key} = {h!r} phải là [x0, y0, x1, y1] (4 số, mm).")
        return None
    x0, y0, x1, y1 = (S.fr(c) for c in h)
    if x1 <= x0 or y1 <= y0:
        ctx.err(path, f"{key} = {h!r}: cần x1 > x0 và y1 > y0.")
        return None
    return (x0, y0, x1, y1)


def _mat(e, path, ctx, default="be_tong"):
    return S.choice(e, "vat_lieu", tuple(MATERIALS), path, ctx, default)


def v_lop(e, path, ctx, view):
    g = S.pt(e.get("goc"), "goc", path, ctx)
    huong = S.choice(e, "huong", ("ngang", "dung"), path, ctx)
    dai = S.num(e, "dai", path, ctx, positive=True)
    lop = e.get("lop")
    layers = []
    if not isinstance(lop, list) or not lop:
        ctx.err(path, "lop phải là danh sách các lớp {\"vat_lieu\": ..., \"day\": mm} (từ dưới lên với huong ngang, từ trái sang phải với huong dung).")
    else:
        for k, l in enumerate(lop):
            lp = f"{path}.lop[{k}]"
            if not isinstance(l, dict) or set(l) - {"vat_lieu", "day"}:
                ctx.err(lp, "phải là {\"vat_lieu\": ..., \"day\": ...}.")
                continue
            m, d = _mat(l, lp, ctx, None), S.num(l, "day", lp, ctx, positive=True)
            if m and d:
                layers.append((m, d))
            else:
                layers = None
                break
    tong = S.num(e, "tong_day", path, ctx, positive=True) if "tong_day" in e else None
    if layers and g and huong and dai and lop is not None and len(layers) == len(lop):
        total = sum(d for _, d in layers)
        if tong is not None and total != tong:
            ctx.err(path, f"tổng chiều dày các lớp = {S.fnum(total)} mm khác tong_day = {S.fnum(tong)} mm.")
        rects, pos = [], (g[1] if huong == "ngang" else g[0])
        for m, d in layers:
            rects.append((g[0], pos, g[0] + dai, pos + d) if huong == "ngang" else (pos, g[1], pos + d, g[1] + dai))
            pos += d
        return dict(goc=g, huong=huong, dai=dai, layers=layers, rects=rects, tong_day=tong, box=(min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)))
    return None


def v_kc(e, path, ctx, view):
    b = _box(e, "hcn", path, ctx)
    m = _mat(e, path, ctx)
    return dict(box=b, vat_lieu=m) if b and m else None


def v_mong(e, path, ctx, view):
    g = S.pt(e.get("goc"), "goc", path, ctx)
    vals = {k: S.num(e, k, path, ctx, positive=True) for k in ("dai_lot", "day_lot", "dai_mong", "day_mong", "dai_co", "cao_co")}
    if g is None or any(v is None for v in vals.values()):
        return None
    if not (vals["dai_lot"] >= vals["dai_mong"] >= vals["dai_co"]):
        ctx.err(path, f"cần dai_lot ({S.fnum(vals['dai_lot'])}) ≥ dai_mong ({S.fnum(vals['dai_mong'])}) ≥ dai_co ({S.fnum(vals['dai_co'])}).")
        return None
    xc = g[0] + vals["dai_lot"] / 2
    y1 = g[1] + vals["day_lot"]
    y2 = y1 + vals["day_mong"]
    rects = [("lot", (g[0], g[1], g[0] + vals["dai_lot"], y1)), ("mong", (xc - vals["dai_mong"] / 2, y1, xc + vals["dai_mong"] / 2, y2)), ("co", (xc - vals["dai_co"] / 2, y2, xc + vals["dai_co"] / 2, y2 + vals["cao_co"]))]
    return dict(goc=g, rects=rects, box=(g[0], g[1], g[0] + vals["dai_lot"], y2 + vals["cao_co"]), **vals)


def v_cot_ct(e, path, ctx, view):
    b = _box(e, "hcn", path, ctx)
    cover = S.num(e, "bao_ve", path, ctx, positive=True)
    d = S.num(e, "d", path, ctx, positive=True)
    nt, nd = e.get("n_tren"), e.get("n_duoi")
    for k, v in (("n_tren", nt), ("n_duoi", nd)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 2 or v > 20:
            ctx.err(path, f"{k} = {v!r} phải là số nguyên từ 2 đến 20.")
            return None
    if not (b and cover and d):
        return None
    if (b[2] - b[0]) < 2 * cover + 2 * d or (b[3] - b[1]) < 2 * cover + 2 * d:
        ctx.err(path, f"hcn quá nhỏ so với bao_ve = {S.fnum(cover)} mm và đường kính thép d = {S.fnum(d)} mm.")
        return None
    return dict(box=b, bao_ve=cover, d=d, n_tren=nt, n_duoi=nd)


def v_cua_dung(e, path, ctx, view):
    b = _box(e, "hcn", path, ctx)
    kieu = S.choice(e, "kieu", ("di", "so"), path, ctx)
    ban_le = S.choice(e, "ban_le", ("trai", "phai"), path, ctx, "trai")
    if b and (b[2] - b[0] <= 2 * LAYER_INSET or b[3] - b[1] <= 2 * LAYER_INSET):
        ctx.err(path, f"hcn phải rộng và cao hơn {S.fnum(2 * LAYER_INSET)} mm (cánh cửa lùi vào {S.fnum(LAYER_INSET)} mm).")
        return None
    return dict(box=b, kieu=kieu, ban_le=ban_le) if b and kieu and ban_le else None


def v_mai(e, path, ctx, view):
    kieu = S.choice(e, "kieu", ("bang", "1_mai", "2_mai"), path, ctx)
    p = S.pt(e.get("tu"), "tu", path, ctx)
    nhip = S.num(e, "nhip", path, ctx, positive=True)
    day = S.num(e, "day", path, ctx, positive=True)
    vuon = S.num(e, "vuon", path, ctx, nonneg=True, default=0)
    do_doc = None
    if kieu in ("1_mai", "2_mai"):
        v = e.get("do_doc")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not (0 < v <= 100):
            ctx.err(path, f"do_doc = {v!r} phải là số trong (0, 100] (%).")
        else:
            do_doc = S.fr(v) / 100
    elif "do_doc" in e:
        ctx.err(path, "mai bằng không có do_doc.")
    if not (kieu and p and nhip and day) or vuon is None or (kieu != "bang" and do_doc is None):
        return None
    x0, y0, i = p[0], p[1], do_doc if do_doc is not None else Fraction(0)
    if kieu == "bang":
        top = [(x0 - vuon, y0), (x0 + nhip + vuon, y0)]
    elif kieu == "1_mai":
        top = [(x0 - vuon, y0 - vuon * i), (x0 + nhip + vuon, y0 + (nhip + vuon) * i)]
    else:
        top = [(x0 - vuon, y0 - vuon * i), (x0 + nhip / 2, y0 + nhip / 2 * i), (x0 + nhip + vuon, y0 - vuon * i)]
    bottom = [(x, y - day) for x, y in top]
    xs, ys = [q[0] for q in top + bottom], [q[1] for q in top + bottom]
    return dict(kieu=kieu, top=top, bottom=bottom, tu=p, nhip=nhip, day=day, vuon=vuon, do_doc=do_doc, box=(min(xs), min(ys), max(xs), max(ys)))


def v_lan_can(e, path, ctx, view):
    p = S.pt(e.get("tu"), "tu", path, ctx)
    dai, cao, buoc = (S.num(e, k, path, ctx, positive=True) for k in ("dai", "cao", "buoc"))
    if not (p and dai and cao and buoc):
        return None
    n = 1
    while n * buoc < dai:
        n += 1
    if n > 200:
        ctx.err(path, f"buoc = {S.fnum(buoc)} mm cho {n} khoảng, vượt 200.")
        return None
    if cao < RAIL_MIN_SOFT:
        ctx.warnings.append(f"{path}: lan can cao {S.fnum(cao)} mm, thấp hơn {RAIL_MIN_SOFT} mm ({S.EXTENT_NOTE}); cần người thiết kế xác nhận.")
    return dict(tu=p, dai=dai, cao=cao, buoc=buoc, n=n, box=(p[0], p[1], p[0] + dai, p[1] + cao))


def v_bac_thang(e, path, ctx, view):
    p = S.pt(e.get("tu"), "tu", path, ctx)
    n = e.get("so_bac")
    h, b = S.num(e, "cao_bac", path, ctx, positive=True), S.num(e, "rong_bac", path, ctx, positive=True)
    if isinstance(n, bool) or not isinstance(n, int) or not (2 <= n <= 60):
        ctx.err(path, f"so_bac = {n!r} phải là số nguyên từ 2 đến 60.")
        return None
    if not (p and h and b):
        return None
    if not (STAIR_SOFT[0] <= 2 * h + b <= STAIR_SOFT[1]):
        ctx.warnings.append(f"{path}: 2h + b = {S.fnum(2 * h + b)} mm ngoài {STAIR_SOFT[0]}-{STAIR_SOFT[1]} mm ({S.EXTENT_NOTE}); cần người thiết kế xác nhận.")
    pts = [p]
    for k in range(n):
        pts += [(p[0] + b * k, p[1] + h * (k + 1)), (p[0] + b * (k + 1), p[1] + h * (k + 1))]
    return dict(tu=p, n=n, h=h, b=b, pts=pts, box=(p[0], p[1], p[0] + b * n, p[1] + h * n))


def v_cao_do(e, path, ctx, view):
    return dict(vi_tri=S.pt(e.get("vi_tri"), "vi_tri", path, ctx), huong=S.choice(e, "huong", ("phai", "trai"), path, ctx, "phai"))


def v_dan(e, path, ctx, view):
    o = S.v_ghi_chu(dict(e, vi_tri=e.get("vi_tri")), path, ctx, view)
    d = S.pt(e.get("diem"), "diem", path, ctx)
    if o is None or d is None:
        return None
    o["diem"] = d
    return o


def v_dau_cat(e, path, ctx, view):
    ten = e.get("ten")
    a, b = S.pt(e.get("tu"), "tu", path, ctx), S.pt(e.get("den"), "den", path, ctx)
    nhin = S.choice(e, "nhin", ("tren", "duoi", "trai", "phai"), path, ctx)
    if not isinstance(ten, str) or not (1 <= len(ten) <= 3) or S.CTRL.search(ten):
        ctx.err(path, f"ten = {ten!r} phải là chuỗi 1-3 ký tự.")
        return None
    if a and b and a != b and a[0] != b[0] and a[1] != b[1]:
        ctx.err(path, "tu và den phải cùng x hoặc cùng y (đường cắt ngang hoặc đứng).")
        return None
    if a and b and a == b:
        ctx.err(path, "tu và den trùng nhau.")
        return None
    if a and b and nhin and ((a[1] == b[1] and nhin in ("trai", "phai")) or (a[0] == b[0] and nhin in ("tren", "duoi"))):
        ctx.err(path, f"nhin = {nhin!r} không vuông góc với đường cắt (đường ngang: nhin tren|duoi; đường đứng: nhin trai|phai).")
        return None
    return dict(ten=ten, tu=a, den=b, nhin=nhin) if a and b and nhin else None


def v_gio(e, path, ctx, view):
    ten = e.get("ten")
    if not isinstance(ten, str) or not (1 <= len(ten) <= 3) or S.CTRL.search(ten):
        ctx.err(path, f"ten = {ten!r} phải là chuỗi 1-3 ký tự.")
        return None
    x, y0, y1 = S.num(e, "x", path, ctx), S.num(e, "tu_y", path, ctx), S.num(e, "den_y", path, ctx)
    if None in (x, y0, y1):
        return None
    if y1 <= y0:
        ctx.err(path, "den_y phải lớn hơn tu_y.")
        return None
    return dict(ten=ten, x=x, y0=y0, y1=y1)


NEW = {
    "lop_vat_lieu": (v_lop, True, {"goc", "huong", "dai", "lop", "tong_day"}),
    "san": (v_kc, True, {"hcn", "vat_lieu"}), "dam": (v_kc, True, {"hcn", "vat_lieu"}), "cot_mc": (v_kc, True, {"hcn", "vat_lieu"}),
    "mong_don": (v_mong, True, {"goc", "dai_lot", "day_lot", "dai_mong", "day_mong", "dai_co", "cao_co"}),
    "cot_chi_tiet": (v_cot_ct, True, {"hcn", "bao_ve", "d", "n_tren", "n_duoi"}),
    "cua_dung": (v_cua_dung, True, {"hcn", "kieu", "ban_le"}),
    "mai": (v_mai, True, {"kieu", "tu", "nhip", "do_doc", "day", "vuon"}),
    "lan_can": (v_lan_can, True, {"tu", "dai", "cao", "buoc"}),
    "bac_thang_don_gian": (v_bac_thang, True, {"tu", "so_bac", "cao_bac", "rong_bac"}),
    "cao_do": (v_cao_do, False, {"vi_tri", "huong"}),
    "ghi_chu_dan": (v_dan, False, {"chu", "diem", "vi_tri", "can", "cao", "dam"}),
    "dau_cat": (v_dau_cat, True, {"ten", "tu", "den", "nhin"}),
    "tuyen_gio": (v_gio, True, {"ten", "x", "tu_y", "den_y"}),
}
RECT_MATERIAL = ("san", "dam", "cot_mc")


# ------------------------------------------------------------------ geometry
def hatch_segments(box, angle, spacing_paper, s):
    """Segments ((x1, y1), (x2, y2)) in model mm (float) of one hatch family clipped to box = (x0, y0, x1, y1) (Fractions). Lines y - x = j D (45 deg) or x + y = j D (-45 deg), D = spacing * s * sqrt(2)."""
    x0, y0, x1, y1 = (float(v) for v in box)
    D = spacing_paper * s * math.sqrt(2.0)
    out = []
    lo, hi = ((y0 - x1), (y1 - x0)) if angle == 45 else ((x0 + y0), (x1 + y1))
    for j in range(math.ceil(lo / D), math.floor(hi / D) + 1):
        c = j * D
        if angle == 45:
            xa, xb = max(x0, y0 - c), min(x1, y1 - c)
            seg = ((xa, xa + c), (xb, xb + c))
        else:
            xa, xb = max(x0, c - y1), min(x1, c - y0)
            seg = ((xa, c - xa), (xb, c - xb))
        if xb - xa > MIN_HATCH_MM * s / math.sqrt(2.0):
            out.append(seg)
    return out


def level_text(val: Fraction) -> str:
    m = math.floor(abs(val) * 1000 + Fraction(1, 2))
    return ("±" if m == 0 else "+" if val > 0 else "-") + f"{m // 1000}.{m % 1000:03d}"


def rect_with_hatch(W, X, s, tag, hatch_tag, box, material, layer="NET-CHINH"):
    x0, y0, x1, y1 = box
    W.add(Rect(layer=layer, tag=tag, p0=(float(x0) / s, float(y0) / s), p1=(float(x1) / s, float(y1) / s)))
    for m, (ang, sp) in enumerate(MATERIALS[material]):
        for k, (p, q) in enumerate(hatch_segments(box, ang, sp, s)):
            W.line("MAT-CAT", f"{hatch_tag}:{m}", (p[0] / s, p[1] / s), (q[0] / s, q[1] / s))


def geom(sp, view, W, X):
    s, P = W.s, sp["params"]
    for e in view["elems"]:
        t, eid = e["t"], e.get("id")
        if t == "lop_vat_lieu":
            for k, ((m, d), r) in enumerate(zip(e["layers"], e["rects"])):
                rect_with_hatch(W, X, s, f"lop:{eid}:{k}", f"hatch:{eid}:{k}", r, m)
        elif t in RECT_MATERIAL:
            rect_with_hatch(W, X, s, f"kc:{eid}", f"hatch:{eid}:0", e["box"], e["vat_lieu"])
        elif t == "mong_don":
            for k, (nm, r) in enumerate(e["rects"]):
                rect_with_hatch(W, X, s, f"mong:{eid}:{nm}", f"hatch:{eid}:{k}", r, "be_tong")
        elif t == "cot_chi_tiet":
            b, c, d = e["box"], e["bao_ve"], e["d"]
            W.add(Rect(layer="NET-CHINH", tag=f"cot:{eid}:be_tong", p0=(X(b[0]), X(b[1])), p1=(X(b[2]), X(b[3]))))
            W.add(Rect(layer="NET-MANH", tag=f"cot:{eid}:dai", p0=(X(b[0] + c), X(b[1] + c)), p1=(X(b[2] - c), X(b[3] - c))))
            for row, n in ((b[1] + c + d / 2, e["n_duoi"]), (b[3] - c - d / 2, e["n_tren"])):
                for k in range(n):
                    x = b[0] + c + d / 2 + (b[2] - b[0] - 2 * c - d) * k / (n - 1)
                    W.add(Circle(layer="NET-MANH", tag=f"cot:{eid}:thep", c=(X(x), X(row)), r=X(d / 2)))
        elif t == "cua_dung":
            b = e["box"]
            W.add(Rect(layer="NET-CHINH", tag=f"cd:{eid}:khung", p0=(X(b[0]), X(b[1])), p1=(X(b[2]), X(b[3]))))
            i0, j0, i1, j1 = b[0] + LAYER_INSET, b[1] + LAYER_INSET, b[2] - LAYER_INSET, b[3] - LAYER_INSET
            W.add(Rect(layer="NET-MANH", tag=f"cd:{eid}:canh", p0=(X(i0), X(j0)), p1=(X(i1), X(j1))))
            if e["kieu"] == "so":
                W.line("NET-MANH", f"cd:{eid}:gach", (X((i0 + i1) / 2), X(j0)), (X((i0 + i1) / 2), X(j1)))
            else:
                hx, ox = (i0, i1) if e["ban_le"] == "trai" else (i1, i0)
                ym = (j0 + j1) / 2
                for yy in (j0, j1):
                    W.line("NET-KHUAT", f"cd:{eid}:gach", (X(hx), X(yy)), (X(ox), X(ym)))
        elif t == "mai":
            for nm, poly in (("top", e["top"]), ("bottom", e["bottom"])):
                for p, q in zip(poly, poly[1:]):
                    W.line("NET-CHINH", f"mai:{eid}:{nm}", (X(p[0]), X(p[1])), (X(q[0]), X(q[1])))
            for a, b_ in zip(e["top"][::len(e["top"]) - 1], e["bottom"][::len(e["bottom"]) - 1]):
                W.line("NET-CHINH", f"mai:{eid}:dau", (X(a[0]), X(a[1])), (X(b_[0]), X(b_[1])))
        elif t == "lan_can":
            x0, y0, cao = e["tu"][0], e["tu"][1], e["cao"]
            for k in range(e["n"] + 1):
                x = x0 + e["dai"] * k / e["n"]
                W.line("NET-MANH", f"lc:{eid}:cot", (X(x), X(y0)), (X(x), X(y0 + cao)))
            for h in (cao, cao / 2):
                W.line("NET-MANH", f"lc:{eid}:thanh", (X(x0), X(y0 + h)), (X(x0 + e["dai"]), X(y0 + h)))
        elif t == "bac_thang_don_gian":
            for p, q in zip(e["pts"], e["pts"][1:]):
                W.line("NET-CHINH", f"bt:{eid}", (X(p[0]), X(p[1])), (X(q[0]), X(q[1])))
        elif t == "cao_do":
            px, py = X(e["vi_tri"][0]), X(e["vi_tri"][1])
            sgn = 1.0 if e["huong"] == "phai" else -1.0
            W.line("NET-MANH", f"lv:{e['idx']}", (px, py), (px - 1.5, py + 3.0))
            W.line("NET-MANH", f"lv:{e['idx']}", (px, py), (px + 1.5, py + 3.0))
            W.line("NET-MANH", f"lv:{e['idx']}", (px - 1.5 * sgn, py + 3.0), (px - 1.5 * sgn + 19.0 * sgn, py + 3.0))
        elif t == "tuyen_gio":
            ov, gp, rb, hb = P["truc_vuon_qua"], P["khe_vong_truc"], P["duong_kinh_vong_truc"] / 2, P["cao_chu_vong_truc"]
            W.line("TRUC", f"gio_line:{eid}", (X(e["x"]), X(e["y0"]) - ov), (X(e["x"]), X(e["y1"]) + ov))
            cy = X(e["y1"]) + ov + gp + rb
            W.add(Circle(layer="TRUC-KYHIEU", tag=f"gio_bubble:{eid}", c=(X(e["x"]), cy), r=rb))
        elif t == "dau_cat":
            a, b = e["tu"], e["den"]
            W.line("NET-CHINH", f"cut:{eid}", (X(a[0]), X(a[1])), (X(b[0]), X(b[1])))
            dx, dy = {"tren": (0, 1), "duoi": (0, -1), "trai": (-1, 0), "phai": (1, 0)}[e["nhin"]]
            for q in (a, b):
                W.line("NET-CHINH", f"cut_arm:{eid}", (X(q[0]), X(q[1])), (X(q[0]) + dx * 8.0, X(q[1]) + dy * 8.0))
        elif t == "ghi_chu_dan":
            d, v = e["diem"], e["vi_tri"]
            W.line("NET-MANH", f"leader:{eid if eid else e['idx']}", (X(d[0]), X(d[1])), (X(v[0]), X(v[1])))
            c = (X(d[0]), X(d[1]))
            asz = P["kt_mui_ten"] / 2
            W.line("NET-MANH", f"leader:{eid if eid else e['idx']}:tick", (c[0] - asz, c[1] - asz), (c[0] + asz, c[1] + asz))


def labels2(sp, view, W, X):
    P = sp["params"]
    mo = view.get("mo_cao") or (Fraction(0), Fraction(0))
    for e in view["elems"]:
        t = e["t"]
        who = e["path"]
        if t == "tuyen_gio":
            hb, rb = P["cao_chu_vong_truc"], P["duong_kinh_vong_truc"] / 2
            cy = X(e["y1"]) + P["truc_vuon_qua"] + P["khe_vong_truc"] + rb
            W.place(f"gio_text:{e['id']}", "TRUC-KYHIEU", e["ten"], hb, [((X(e["x"]), cy - hb / 2), "center", 0.0)], who, exclude_tag=f"gio_bubble:{e['id']}")
        if t == "cao_do":
            px, py = X(e["vi_tri"][0]), X(e["vi_tri"][1])
            sgn = 1.0 if e["huong"] == "phai" else -1.0
            val = mo[1] + (e["vi_tri"][1] - mo[0]) / 1000
            W.place(f"lv_text:{e['idx']}", "CHU", level_text(val), P["cao_chu_vong_truc"], [((px - 1.0 * sgn, py + 3.8), "left" if sgn > 0 else "right", 0.0)], who, exclude_tag=f"lv:{e['idx']}")
        elif t == "ghi_chu_dan":
            d, v = e["diem"], e["vi_tri"]
            right = X(v[0]) >= X(d[0])
            for k, ln in enumerate(e["dong"]):
                pos = (X(v[0]) + (1.2 if right else -1.2), X(v[1]) - e["cao"] / 2 - k * (e["cao"] + 2.0))
                W.place(f"leader_text:{e['id'] if e['id'] else e['idx']}:{k}", "CHU", ln, e["cao"], [(pos, "left" if right else "right", 0.0)], who, exclude_tag=f"leader:{e['id'] if e['id'] else e['idx']}", bold=e["dam"])
        elif t == "dau_cat":
            dx, dy = {"tren": (0, 1), "duoi": (0, -1), "trai": (-1, 0), "phai": (1, 0)}[e["nhin"]]
            for q in (e["tu"], e["den"]):
                tip = (X(q[0]) + dx * 8.0, X(q[1]) + dy * 8.0)
                h = 3.5
                pos = (tip[0] + dx * 2.0, tip[1] + (2.0 if dy > 0 else (-2.0 - 1.35 * h if dy < 0 else -h / 2)))
                al = "center" if dx == 0 else ("left" if dx > 0 else "right")
                W.place(f"cut_text:{e['id']}", "CHU", e["ten"], h, [(pos, al, 0.0)], who, exclude_tag=f"cut_arm:{e['id']}")


S.CATALOG.update(NEW)
