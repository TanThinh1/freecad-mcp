"""Verification of the phase 2 elements of type E (own code, independent of elems2.py): expected geometry for hatch (Liang-Barsky style clipping), layered / structural
rectangles, door / window elevations, roofs, railings, stairs, level symbols, section markers, wind axes and leaders (compared two ways by verify_e as families 1.63-1.66), plus
measured rules: layer thicknesses add up (and equal tong_day), hatch never leaves its rectangle, level texts equal the geometric height difference to the reference level.
New ids only: 1.63-1.66 (+ 1.67, 1.68 measured rules), DXF 2.36, DWG 3.25.
"""
from __future__ import annotations

import collections
import math
from fractions import Fraction

from primitives import Circle, Line, Rect, Text

HATCH = {"be_tong": [(45, 4.0)], "gach": [(45, 2.0)], "vua": [(-45, 2.0)], "dat": [(45, 3.0), (-45, 3.0)], "thep": [(45, 1.2)]}
INSET = Fraction(60)
KIND_TAG = {"lop_vat_lieu": "lop", "san": "kc", "dam": "kc", "cot_mc": "kc", "mong_don": "mong"}


def F(x):
    return float(x)


def clip(p, d, rect):
    """Parameter interval [t0, t1] of the line p + t d inside rect (Liang-Barsky); None when empty."""
    t0, t1 = -1e18, 1e18
    for k in (0, 1):
        lo, hi = rect[k], rect[k + 2]
        if abs(d[k]) < 1e-15:
            if not lo - 1e-9 <= p[k] <= hi + 1e-9:
                return None
        else:
            a, b = (lo - p[k]) / d[k], (hi - p[k]) / d[k]
            t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
    return (t0, t1) if t1 > t0 else None


def hatch_expected(rect, material, s):
    out = []
    r = tuple(F(v) for v in rect)
    for ang, sp in HATCH[material]:
        D = sp * s * math.sqrt(2.0)
        d = (1.0, 1.0) if ang == 45 else (1.0, -1.0)
        lo = (r[1] - r[2]) if ang == 45 else (r[0] + r[1])
        hi = (r[3] - r[0]) if ang == 45 else (r[2] + r[3])
        for j in range(math.ceil(lo / D), math.floor(hi / D) + 1):
            c = j * D
            p = (0.0, c) if ang == 45 else (0.0, c)          # y = x + c   |   y = -x + c
            iv = clip(p, d, r)
            if iv and (iv[1] - iv[0]) > 0.3 * s / math.sqrt(2.0):
                out.append(((p[0] + iv[0] * d[0], p[1] + iv[0] * d[1]), (p[0] + iv[1] * d[0], p[1] + iv[1] * d[1])))
    return out


def level_text(val):
    m = math.floor(abs(val) * 1000 + Fraction(1, 2))
    return ("±" if m == 0 else "+" if val > 0 else "-") + f"{m // 1000}.{m % 1000:03d}"


def add_expected(view, s, P, sh, tx):
    """append (family, layer, kind, data) shapes and (layer, string) texts for the phase 2 elements. Families: hatch, kc, dung, dau."""
    by = {e["id"]: e for e in view["elems"] if e.get("id")}

    def seg(fam, layer, p, q):
        sh.append((fam, layer, "seg", ((F(p[0]), F(p[1])), (F(q[0]), F(q[1])))))

    def rect(fam, layer, r):
        sh.append((fam, layer, "rect", tuple(F(v) for v in r)))

    def hatch(r, material):
        for p, q in hatch_expected(r, material, s):
            sh.append(("hatch", "MAT-CAT", "seg", (p, q)))

    ref_y, ref_h = view.get("mo_cao") or (Fraction(0), Fraction(0))
    for e in view["elems"]:
        t = e["t"]
        if t == "lop_vat_lieu":
            g = e["goc"]
            pos = g[1] if e["huong"] == "ngang" else g[0]
            for mat, d in e["layers"]:
                r = (g[0], pos, g[0] + e["dai"], pos + d) if e["huong"] == "ngang" else (pos, g[1], pos + d, g[1] + e["dai"])
                rect("kc", "NET-CHINH", r)
                hatch(r, mat)
                pos += d
        elif t in ("san", "dam", "cot_mc", "mat_tuong_dung"):
            rect("kc", "NET-CHINH", e["box"])
            if e["vat_lieu"]:
                hatch(e["box"], e["vat_lieu"])
        elif t == "mong_don":
            g = e["goc"]
            xc = g[0] + e["dai_lot"] / 2
            y1 = g[1] + e["day_lot"]
            y2 = y1 + e["day_mong"]
            for r in ((g[0], g[1], g[0] + e["dai_lot"], y1), (xc - e["dai_mong"] / 2, y1, xc + e["dai_mong"] / 2, y2), (xc - e["dai_co"] / 2, y2, xc + e["dai_co"] / 2, y2 + e["cao_co"])):
                rect("kc", "NET-CHINH", r)
                hatch(r, "be_tong")
        elif t == "cot_chi_tiet":
            b, c, d = e["box"], e["bao_ve"], e["d"]
            rect("kc", "NET-CHINH", b)
            rect("kc", "NET-MANH", (b[0] + c, b[1] + c, b[2] - c, b[3] - c))
            for row, n in ((b[1] + c + d / 2, e["n_duoi"]), (b[3] - c - d / 2, e["n_tren"])):
                for k in range(n):
                    sh.append(("kc", "NET-MANH", "circ", ((F(b[0] + c + d / 2 + (b[2] - b[0] - 2 * c - d) * k / (n - 1)), F(row)), F(d / 2))))
        elif t == "cua_dung":
            b = e["box"]
            rect("dung", "NET-CHINH", b)
            i0, j0, i1, j1 = b[0] + INSET, b[1] + INSET, b[2] - INSET, b[3] - INSET
            rect("dung", "NET-MANH", (i0, j0, i1, j1))
            if e["kieu"] == "so":
                seg("dung", "NET-MANH", ((i0 + i1) / 2, j0), ((i0 + i1) / 2, j1))
            else:
                hx, ox = (i0, i1) if e["ban_le"] == "trai" else (i1, i0)
                for yy in (j0, j1):
                    seg("dung", "NET-KHUAT", (hx, yy), (ox, (j0 + j1) / 2))
        elif t == "mai":
            x0, y0 = e["tu"]
            i = Fraction(e["do_doc"] or 0)
            v, nh, dy = e["vuon"], e["nhip"], e["day"]
            if e["kieu"] == "bang":
                top = [(x0 - v, y0), (x0 + nh + v, y0)]
            elif e["kieu"] == "1_mai":
                top = [(x0 - v, y0 - v * i), (x0 + nh + v, y0 + (nh + v) * i)]
            else:
                top = [(x0 - v, y0 - v * i), (x0 + nh / 2, y0 + nh / 2 * i), (x0 + nh + v, y0 - v * i)]
            bot = [(x, y - dy) for x, y in top]
            for poly in (top, bot):
                for p, q in zip(poly, poly[1:]):
                    seg("dung", "NET-CHINH", p, q)
            seg("dung", "NET-CHINH", top[0], bot[0])
            seg("dung", "NET-CHINH", top[-1], bot[-1])
        elif t == "lan_can":
            x0, y0, cao = e["tu"][0], e["tu"][1], e["cao"]
            n = 1
            while n * e["buoc"] < e["dai"]:
                n += 1
            for k in range(n + 1):
                x = x0 + e["dai"] * k / n
                seg("dung", "NET-MANH", (x, y0), (x, y0 + cao))
            for h in (cao, cao / 2):
                seg("dung", "NET-MANH", (x0, y0 + h), (x0 + e["dai"], y0 + h))
        elif t == "bac_thang_don_gian":
            p = e["tu"]
            pts = [p]
            for k in range(e["n"]):
                pts += [(p[0] + e["b"] * k, p[1] + e["h"] * (k + 1)), (p[0] + e["b"] * (k + 1), p[1] + e["h"] * (k + 1))]
            for a, b in zip(pts, pts[1:]):
                seg("dung", "NET-CHINH", a, b)
        elif t == "cao_do":
            px, py = F(e["vi_tri"][0]), F(e["vi_tri"][1])
            sg = 1.0 if e["huong"] == "phai" else -1.0
            seg("dau", "NET-MANH", (px, py), (px - 1.5 * s, py + 3.0 * s))
            seg("dau", "NET-MANH", (px, py), (px + 1.5 * s, py + 3.0 * s))
            seg("dau", "NET-MANH", (px - 1.5 * sg * s, py + 3.0 * s), (px - 1.5 * sg * s + 19.0 * sg * s, py + 3.0 * s))
            tx.append(("CHU", level_text(ref_h + (Fraction(e["vi_tri"][1]) - ref_y) / 1000)))
        elif t == "ghi_chu_dan":
            d, v = e["diem"], e["vi_tri"]
            seg("dau", "NET-MANH", d, v)
            a = P["kt_mui_ten"] / 2 * s
            seg("dau", "NET-MANH", (F(d[0]) - a, F(d[1]) - a), (F(d[0]) + a, F(d[1]) + a))
            tx.extend(("CHU", ln) for ln in e["dong"])
        elif t == "dau_cat":
            a, b = e["tu"], e["den"]
            seg("dau", "NET-CHINH", a, b)
            dx, dy = {"tren": (0, 1), "duoi": (0, -1), "trai": (-1, 0), "phai": (1, 0)}[e["nhin"]]
            for q in (a, b):
                seg("dau", "NET-CHINH", q, (F(q[0]) + dx * 8.0 * s, F(q[1]) + dy * 8.0 * s))
                tx.append(("CHU", e["ten"]))
        elif t == "tuyen_gio":
            ov, gp, rb = P["truc_vuon_qua"] * s, P["khe_vong_truc"] * s, P["duong_kinh_vong_truc"] * s / 2
            seg("dau", "TRUC", (e["x"], F(e["y0"]) - ov), (e["x"], F(e["y1"]) + ov))
            sh.append(("dau", "TRUC-KYHIEU", "circ", ((F(e["x"]), F(e["y1"]) + ov + gp + rb), rb)))
            tx.append(("TRUC-KYHIEU", e["ten"]))


def soft_warning_ids(view):
    out = []
    for e in view["elems"]:
        if e["t"] == "bac_thang_don_gian" and not (600 <= 2 * e["h"] + e["b"] <= 630):
            out.append(e["id"])
        if e["t"] == "lan_can" and e["cao"] < 900:
            out.append(e["id"])
    return out


def check_phase2(C, D, sp, tol=1e-6):
    """Measured rules on the drawn primitives (real mm)."""
    view = sp["views"][0]
    s, (ox, oy) = D.scale, D.origin
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    rects = {p.tag: (min(R(p.p0)[0], R(p.p1)[0]), min(R(p.p0)[1], R(p.p1)[1]), max(R(p.p0)[0], R(p.p1)[0]), max(R(p.p0)[1], R(p.p1)[1])) for p in D.prims if isinstance(p, Rect)}
    # ---- layers: thickness of every drawn layer, contiguity, total
    bad, n = [], 0
    for e in (q for q in view["elems"] if q["t"] == "lop_vat_lieu"):
        drawn = [rects.get(f"lop:{e['id']}:{k}") for k in range(len(e["layers"]))]
        if any(r is None for r in drawn):
            bad.append(f"{e['id']}: thiếu lớp")
            continue
        along = (lambda r: r[3] - r[1]) if e["huong"] == "ngang" else (lambda r: r[2] - r[0])
        lo = (lambda r: r[1]) if e["huong"] == "ngang" else (lambda r: r[0])
        hi = (lambda r: r[3]) if e["huong"] == "ngang" else (lambda r: r[2])
        for (mat, d), r in zip(e["layers"], drawn):
            n += 1
            if abs(along(r) - F(d)) > tol:
                bad.append(f"{e['id']}: lớp {mat} dày {along(r):.4f} ≠ {F(d):g}")
        for a, b in zip(drawn, drawn[1:]):
            if abs(hi(a) - lo(b)) > tol:
                bad.append(f"{e['id']}: hai lớp liền nhau không khít")
        total = hi(drawn[-1]) - lo(drawn[0])
        if e.get("tong_day") is not None and abs(total - F(e["tong_day"])) > tol:
            bad.append(f"{e['id']}: tổng {total:.4f} ≠ tong_day {F(e['tong_day']):g}")
    C.add(1, "1.67", "lớp vật liệu: mỗi lớp đúng bề dày khai báo, các lớp liền khít nhau, tổng bề dày bằng tong_day (đo từ hình chữ nhật đã vẽ)", not bad and n >= 0, f"{n} lớp đã đo; sai: {bad[:3]}")
    # ---- hatch stays inside its rectangle
    out, total = [], 0
    owner = {}
    for e in view["elems"]:
        if e["t"] == "lop_vat_lieu":
            for k in range(len(e["layers"])):
                owner[f"hatch:{e['id']}:{k}"] = f"lop:{e['id']}:{k}"
        elif e["t"] in ("san", "dam", "cot_mc", "mat_tuong_dung"):
            owner[f"hatch:{e['id']}:0"] = f"kc:{e['id']}"
        elif e["t"] == "mong_don":
            for k, nm in enumerate(("lot", "mong", "co")):
                owner[f"hatch:{e['id']}:{k}"] = f"mong:{e['id']}:{nm}"
    for p in (q for q in D.prims if isinstance(q, Line) and q.tag.startswith("hatch:")):
        total += 1
        r = rects.get(owner.get(":".join(p.tag.split(":")[:3])))
        pts = (R(p.p1), R(p.p2))
        if r is None or any(not (r[0] - tol <= x <= r[2] + tol and r[1] - tol <= y <= r[3] + tol) for x, y in pts):
            out.append(p.tag)
        elif p.layer != "MAT-CAT" or abs(abs(pts[1][1] - pts[0][1]) - abs(pts[1][0] - pts[0][0])) > 1e-6 * max(1.0, abs(pts[1][0] - pts[0][0])):
            out.append(p.tag + " (lớp/góc)")
    C.add(1, "1.68", "hatch: mọi nét hatch nằm trong hình chữ nhật của lớp (kiểm bằng toạ độ), lớp MAT-CAT, nghiêng đúng 45°", not out, f"{total} nét hatch; ra ngoài/sai: {out[:3]}")
    # ---- level texts from the drawn symbol
    ref_y, ref_h = view.get("mo_cao") or (Fraction(0), Fraction(0))
    lvl_bad, nl = [], 0
    for e in (q for q in view["elems"] if q["t"] == "cao_do"):
        lines = [p for p in D.prims if isinstance(p, Line) and p.tag == f"lv:{e['idx']}"]
        txt = [p for p in D.prims if isinstance(p, Text) and p.tag == f"lv_text:{e['idx']}"]
        nl += 1
        if len(lines) != 3 or len(txt) != 1:
            lvl_bad.append(f"phần tử {e['idx']}: {len(lines)} nét, {len(txt)} chữ")
            continue
        tip = R(lines[0].p1)
        val = ref_h + (Fraction(tip[1]).limit_denominator(10 ** 6) - ref_y) / 1000
        if txt[0].s != level_text(val):
            lvl_bad.append(f"phần tử {e['idx']}: chữ {txt[0].s!r}, đo từ hình {level_text(val)!r}")
    C.add(1, "1.69", "cao độ: chữ trên ký hiệu = cao độ mức tham chiếu + (độ cao mũi ký hiệu đo từ hình - độ cao tham chiếu)/1000, làm tròn nửa lên 3 chữ số", not lvl_bad, f"{nl} ký hiệu; sai: {lvl_bad[:3]}")
