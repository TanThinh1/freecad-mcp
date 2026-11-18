"""Verification specific to drawing type A (steel stair). Expected values are computed here FROM THE SPEC with independent formulas,
then compared with the primitives, the DXF entities and the 3D model; nothing is compared with a value derived from itself.
Tolerances: geometry in real mm 1e-6 (floating point only: h = cao_tang / so_bac is never rounded), DXF 1e-3 mm, 3D 1e-3 mm.
"""
from __future__ import annotations

import math

from primitives import Circle, Line, Rect, Text, fmt_dec
from readers import f
from verify import Checks, close, greedy_match

TOL = 1e-6
TOL_DXF = 1e-3


def _hl(h: float) -> str:
    """Label of the riser height: integer mm when exact, otherwise 1 decimal with a comma (explicit, geometry stays exact)."""
    return f"{round(h):d}" if abs(h - round(h)) < 1e-9 else f"{h:.1f}".replace(".", ",")


def expected_texts(sp: dict) -> dict:
    n, H, b, t = sp["so_bac"], sp["cao_tang"], sp["b"], sp["t"]
    h, L = H / n, (n - 1) * b
    th = math.degrees(math.atan(h / b))
    return dict(
        notes=[f"THÉP TẤM DÀY {f'{t:g}'.replace('.', ',')} MM", f"{n} x {_hl(h)} = {round(H):d}", f"{n - 1} x {round(b):d} = {round(L):d}"],
        angle=f"GÓC DỐC {f'{th:.1f}'.replace('.', ',')}°", levels=["+0.000", f"+{H / 1000:.3f}"], h_label=_hl(h), steps=[str(i) for i in range(1, n)])


def _seg_ends(p):
    return (p.p1, p.p2)


def _same_seg(a, b, tol):
    (a1, a2), (b1, b2) = a, b
    d = lambda p, q: close(p[0], q[0], tol) and close(p[1], q[1], tol)
    return (d(a1, b1) and d(a2, b2)) or (d(a1, b2) and d(a2, b1))


# ------------------------------------------------------------------ 1. primitives
def check_primitives_a(C: Checks, D, sp):
    s = D.scale
    M = D.meta
    ox, oy = M["section_origin"]
    px, py = M["plan_origin"]
    n, H, b, w, t = sp["so_bac"], sp["cao_tang"], sp["b"], sp["w"], sp["t"]
    h, L = H / n, (n - 1) * b
    ds = sp["dam_con"]
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)          # section: real (x, z)
    PL = lambda p: ((p[0] - px) * s, (p[1] - py) * s)         # plan: real (x, y)
    by = lambda tag: [p for p in D.prims if p.tag == tag]
    ln = lambda p: math.hypot(p.p2[0] - p.p1[0], p.p2[1] - p.p1[1]) * s
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
    ok4 = len(outline) == 1 and close((outline[0].p1[0] - outline[0].p0[0]) * s, L, TOL) and close((outline[0].p1[1] - outline[0].p0[1]) * s, w, TOL) and close(outline[0].p0[0], ox, 1e-9)
    tl = by("plan_tread_line")
    n_t, _ = greedy_match([i * b for i in range(1, n - 1)], tl, lambda e, g: close(PL(g.p1)[0], e, TOL) and close(PL(g.p2)[0], e, TOL) and close(ln(g), w, TOL))
    C.add(1, "1.4", "mặt bằng: dài (so_bac − 1) × b, rộng w, thẳng hàng với mặt cắt; n − 2 đường mặt bậc đúng vị trí", ok4 and n_t == n - 2 == len(tl),
          f"dài {(outline[0].p1[0] - outline[0].p0[0]) * s:.3f} (cần {L:g}), rộng {(outline[0].p1[1] - outline[0].p0[1]) * s:.3f} (cần {w:g}); {n_t}/{n - 2} đường mặt bậc" if outline else "không có hình chữ nhật mặt bằng")
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
    geo_ok = all(close((abs(d.p2[0] - d.p1[0]) if d.kind == "h" else abs(d.p2[1] - d.p1[1])) * s, d.value, TOL) for d in D.dims)
    hdim = [d for d in D.dims if d.kind == "v" and abs(d.value - h) < 1e-9]
    C.add(1, "1.8", "kích thước: h (chính xác, không làm tròn), b, cao_tang, tổng chiều dài, w, chuỗi/gộp chuỗi; độ dài hình học = giá trị", n_d == len(exp_v) == len(got_v) and geo_ok and len(hdim) == 1 and hdim[0].text == X["h_label"],
          f"{n_d}/{len(exp_v)} kích thước đúng; nhãn h = {hdim[0].text if hdim else None!r} (h chính xác = {h:.6f}); chuỗi bị gộp: {M['chain_collapsed']}")
    notes = [p.s for p in by("note")]
    C.add(1, "1.9", "ghi chú: tấm thép dày đúng chieu_day_tam; 'so_bac x h = cao_tang'; '(so_bac−1) x b = dài'", notes == X["notes"], f"{notes}")
    cl = by("cut_label")
    yc = [PL(p.p1)[1] for p in by("cut_stroke")]
    ok10 = [p.s for p in cl] == ["1", "1"] and len(yc) == 2 and all(close(y, w / 2, TOL) for y in yc) and [p.s for p in by("title_section")] == ["MẶT CẮT 1-1"] and [p.s for p in by("title_plan")] == ["MẶT BẰNG THANG"]
    C.add(1, "1.10", "ký hiệu vết cắt 1-1 trên mặt bằng (2 đầu, nhãn 1, ở giữa bề rộng) và tên hai hình", ok10, f"nhãn {[p.s for p in cl]}, y vết cắt {[round(y, 3) for y in yc]} (w/2 = {w / 2:g})")
    if sp.get("warnings"):
        C.info(1, "1.11", "cảnh báo mềm (không phải lỗi)", " | ".join(sp["warnings"]))
    else:
        C.info(1, "1.11", "cảnh báo mềm 2h + b", f"2h + b = {sp['two_h_b']:.1f} mm, trong khoảng {sp['params']['nguong_2hb_min']:g}-{sp['params']['nguong_2hb_max']:g} mm (quy tắc kinh nghiệm, không phải điều khoản TCVN)")


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
    st = ents.get("KEO", [])
    top_ok = any(_same_seg(g, ((0.0, h), (L, H)), TOL_DXF) for g in st)
    cos_t = math.cos(math.atan(h / b))
    low_ok = any(abs(g[1][0] - L) < TOL_DXF and abs(g[1][0] - g[0][0]) > 1e-9 and close((H - g[1][1]) * cos_t, ds["bd"], TOL_DXF)
                 and close((g[1][1] - g[0][1]) / (g[1][0] - g[0][0]), h / b, 1e-9) for g in st)
    C.add(2, "2.7", "DXF (mm thật, gốc ở mép sàn dưới): răng cưa đúng công thức, đường cao độ z = 0 và z = cao_tang, dầm cốn đúng độ dốc và chiều cao",
          n_ok == len(exp) and lv_ok and top_ok and low_ok, f"{n_ok}/{len(exp)} đoạn răng cưa; cao độ {lv_ok}; mép trên dầm {top_ok}; mép dưới dầm {low_ok}; thiếu {miss[:2]}")
    polys = [e for e in dx["ents"] if e["type"] == "LWPOLYLINE" and e["layer"] == "NET-CHINH"]
    plan = []
    for e in polys:
        xs, ys = [float(v) for v in e["rec"][10]], [float(v) for v in e["rec"][20]]
        plan.append((min(xs), min(ys), max(xs), max(ys)))
    plan_ok = len(plan) == 1 and close(plan[0][0], 0.0, TOL_DXF) and close(plan[0][2] - plan[0][0], L, TOL_DXF) and close(plan[0][3] - plan[0][1], w, TOL_DXF) and plan[0][3] < 0
    hid = ents.get("NET-KHUAT", [])
    hid_ok = bool(plan) and len(hid) == 2 and all(close(abs(g[1][0] - g[0][0]), L, TOL_DXF) for g in hid) and \
        sorted(round(g[0][1] - plan[0][1], 3) for g in hid) == sorted([round(ds["bw"], 3), round(w - ds["bw"], 3)])
    txt = [t for lay, t in dx["texts"]]
    texts_ok = all(txt.count(x) >= 1 for x in X["notes"] + X["levels"] + [X["angle"], "MẶT CẮT 1-1", "MẶT BẰNG THANG"]) and all(str(i) in txt for i in range(1, n))
    C.add(2, "2.8", "DXF: hình chữ nhật mặt bằng (n−1)·b × w thẳng hàng và nằm dưới mặt cắt; 2 mép dầm cốn khuất cách mép bw; chữ ghi chú/cao độ/góc/số bậc",
          plan_ok and hid_ok and texts_ok, f"mặt bằng {plan}; dầm khuất {hid_ok}; chữ {texts_ok}")


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
