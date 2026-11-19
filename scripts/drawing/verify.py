"""Automatic verification of one drawing (type B). Returns checks: dict(group, id, name, ok, detail); ok=None = information only.

1 primitives vs formulas   2 DXF (+ FreeCAD import)   3 DWG round trip   4 PDF sheet geometry   5 PDF vs primitives/DXF
Everything is measured from the produced files except where a detail says "suy luận".
Geometry checks match EVERY primitive (position, size, line weight, dash) against the file; no check compares a value with itself.
"""
from __future__ import annotations

import collections
import decimal
import json
import math
import os
import re
import subprocess

import oda
import titleblock as TBK
from dxf_render import expected_counts
from primitives import Circle, Line, Rect, Text, cap_to_em, fmt_value
from readers import analyze_pdf, f, read_dxf, unesc
from tcvn import ARIAL_CAP, LAYER_AXIS, LAYER_COLUMN, LAYER_DIM, LTYPES, SHEETS, layer_style

HERE = os.path.dirname(os.path.abspath(__file__))
FREECADCMD = os.environ.get("FREECADCMD_EXE") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "FreeCAD 1.1", "bin", "FreeCADCmd.exe")
TB_TOP = TBK.TB_TOP
TOL_PDF = 0.06       # mm on paper (measured deviation of the PDF writer: <= 0.02 mm)
TOL_DXF = 1e-3       # mm real


class Checks:
    def __init__(self):
        self.items = []

    def add(self, group, cid, name, ok, detail=""):
        self.items.append(dict(group=group, id=cid, name=name, ok=bool(ok), detail=detail))

    def info(self, group, cid, name, detail=""):
        self.items.append(dict(group=group, id=cid, name=name, ok=None, detail=detail))

    def passed(self, group):
        g = [i for i in self.items if i["group"] == group and i["ok"] is not None]
        return all(i["ok"] for i in g) if g else None

    def all_ok(self):
        return all(i["ok"] is not False for i in self.items)


def _len(p):
    return math.hypot(p.p2[0] - p.p1[0], p.p2[1] - p.p1[1])


def close(a, b, tol):
    return abs(a - b) <= tol


_NUM = r"(?<![\d.,])(\d+(?:,\d+)?)(?![\d.])"
_EQ = re.compile(_NUM + r"\s*[x×]\s*" + _NUM + r"\s*=\s*" + _NUM)
_APPROX = re.compile(_NUM + r"\s*/\s*" + _NUM + r"\s*≈\s*" + _NUM)


def check_expressions(C: "Checks", texts, group: int, cid: str, where: str):
    """Every arithmetic expression printed on the drawing must be true for the DISPLAYED numbers: 'a x b = c' exactly (decimal arithmetic),
    'a/b ≈ c' after rounding a/b to the number of decimals shown in c (half up). A text with '=' or '≈' that is not one of these forms fails."""
    D = decimal.Decimal
    bad, n = [], 0
    for t in texts:
        found = False
        for a, b, c in _EQ.findall(t):
            found = True
            n += 1
            if D(a.replace(",", ".")) * D(b.replace(",", ".")) != D(c.replace(",", ".")):
                bad.append(f"{t!r}: {a} x {b} = {D(a.replace(',', '.')) * D(b.replace(',', '.')):f} ≠ {c}")
        for a, b, c in _APPROX.findall(t):
            found = True
            n += 1
            cd = D(c.replace(",", "."))
            q = (D(a.replace(",", ".")) / D(b.replace(",", "."))).quantize(D(1).scaleb(cd.as_tuple().exponent), rounding=decimal.ROUND_HALF_UP)
            if q != cd:
                bad.append(f"{t!r}: {a}/{b} = {q:f} khi làm tròn đúng số chữ số thập phân hiển thị, ≠ {c}")
        if ("=" in t or "≈" in t) and re.search(r"\d\.\d", t):
            bad.append(f"{t!r}: số thập phân dùng dấu chấm, chỉ hỗ trợ dấu phẩy")
            continue
        if not found and ("=" in t or "≈" in t) and not re.fullmatch(r"[A-Za-z]+ = \d+(?:,\d+)?%?(?: \(\d+(?:,\d+)?°\))?", t):   # plain assignments like 'i = 15% (8,5°)' are not arithmetic
            bad.append(f"{t!r}: biểu thức không đọc được")
    C.add(group, cid, f"{where}: mọi biểu thức số học in trên bản vẽ (a x b = c, a/b ≈ c) đúng với số hiển thị", not bad, f"{n} biểu thức đã kiểm" + (f"; SAI: {bad[:3]}" if bad else ""))


def _seg_rect_gap(a, b, rect):
    """Distance between segment a-b and an axis-aligned rectangle (x0, y0, x1, y1); 0 when they touch or cross."""
    x0, y0, x1, y1 = rect
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                t0, t1 = 1.0, 0.0
                break
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
    if t0 <= t1:
        return 0.0

    def pt_rect(px, py):
        return math.hypot(max(x0 - px, 0.0, px - x1), max(y0 - py, 0.0, py - y1))

    def pt_seg(px, py):
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))

    return min(pt_rect(*a), pt_rect(*b), pt_seg(x0, y0), pt_seg(x1, y0), pt_seg(x1, y1), pt_seg(x0, y1))


def text_min_gap(texts, segments):
    """Smallest clear distance (mm) between the (conservative, est_width based) box of each horizontal text and any segment [(p, q)]. Returns (gap, text)."""
    best = (1e9, None)
    for t in texts:
        w = TBK.est_width(t.s, cap_to_em(t.h), t.bold)
        x0, x1 = {"left": (0.0, w), "center": (-w / 2, w / 2), "right": (-w, 0.0)}[t.halign]
        rect = (t.pos[0] + x0, t.pos[1] - 0.05 * t.h, t.pos[0] + x1, t.pos[1] + t.h)
        for p, q in segments:
            g = _seg_rect_gap(p, q, rect)
            if g < best[0]:
                best = (g, t.s)
    return best


def greedy_match(expected, got, near):
    """expected/got: lists; near(e, g) -> bool. One-to-one greedy matching. Returns (n_matched, unmatched expected)."""
    used, bad = set(), []
    for e in expected:
        for i, g in enumerate(got):
            if i not in used and near(e, g):
                used.add(i)
                break
        else:
            bad.append(e)
    return len(expected) - len(bad), bad


# ------------------------------------------------------------------ 1. primitives vs formulas
def check_primitives_b(C: Checks, D, sp):
    s = D.scale
    P = D.info["params"]
    b, h = sp["section"]["b"], sp["section"]["h"]
    sec_text = sp["section"]["text"]
    N, nhip, dai, buoc = sp["so_truc_doc"], sp["nhip"], sp["dai_nha"], sp["buoc_cot"]
    ov = P["truc_vuon_qua"]
    av, ah, cols = D.by_tag("axis_v"), D.by_tag("axis_h"), D.by_tag("column")
    C.add(1, "1.1", "số trục dọc = dai_nha/buoc_cot + 1", len(av) == round(dai / buoc) + 1 == N, f"{len(av)} trục dọc; dai_nha/buoc_cot + 1 = {dai / buoc + 1:g}")
    C.add(1, "1.2", "số trục ngang = 2 (A, B)", len(ah) == 2, f"{len(ah)}")
    C.add(1, "1.3", "số cột = số trục dọc × số trục ngang", len(cols) == len(av) * len(ah), f"{len(cols)} cột = {len(av)} × {len(ah)}")
    exp_v, exp_h = nhip + h + 2 * ov * s, dai + b + 2 * ov * s
    tot_v, tot_h = sum(_len(x) for x in av) * s, sum(_len(x) for x in ah) * s
    each_v = all(close(_len(x) * s, exp_v, 1e-6 * exp_v) for x in av)
    each_h = all(close(_len(x) * s, exp_h, 1e-6 * exp_h) for x in ah)
    C.add(1, "1.4", "chiều dài từng trục dọc và tổng", each_v and close(tot_v, N * exp_v, 1e-6 * N * exp_v), f"đo tổng {tot_v:.3f} mm; công thức N×(nhip + h + 2×vươn×tỷ lệ) = {N * exp_v:.3f} mm")
    C.add(1, "1.5", "chiều dài từng trục ngang và tổng", each_h and close(tot_h, 2 * exp_h, 1e-6 * 2 * exp_h), f"đo tổng {tot_h:.3f} mm; công thức 2×(dai_nha + b + 2×vươn×tỷ lệ) = {2 * exp_h:.3f} mm")
    bad = [c for c in cols if not (close((c.p1[0] - c.p0[0]) * s, b, 1e-6 * b) and close((c.p1[1] - c.p0[1]) * s, h, 1e-6 * h))]
    C.add(1, "1.6", "mọi cột đúng kích thước tiết diện (b × h) theo tỷ lệ", not bad, f"b×h = {b:g}×{h:g} mm, lệch: {len(bad)} cột")
    ox, oy = D.origin
    exp_c = [((i * buoc, j * nhip)) for i in range(N) for j in (0, 1)]
    got_c = [(((c.p0[0] + c.p1[0]) / 2 - ox) * s, ((c.p0[1] + c.p1[1]) / 2 - oy) * s) for c in cols]
    n_ok, miss = greedy_match(exp_c, got_c, lambda e, g: close(e[0], g[0], 1e-3) and close(e[1], g[1], 1e-3))
    C.add(1, "1.7", "tâm mọi cột nằm đúng giao điểm lưới trục (mm thật)", n_ok == len(exp_c) == len(got_c), f"{n_ok}/{len(exp_c)} cột đúng vị trí; thiếu {miss[:3]}")
    bub = D.by_tag("bubble")
    exp_b = [(i * buoc, None) for i in range(N)]
    top_ok = sum(1 for i in range(N) if any(close((c.c[0] - ox) * s, i * buoc, 1e-3) for c in bub))
    C.add(1, "1.8", "vòng ký hiệu trục: số lượng, đường kính, vị trí tâm", len(bub) == N + 2 and all(close(2 * c.r, P["duong_kinh_vong_truc"], 1e-9) for c in bub) and top_ok == N,
          f"{len(bub)} vòng Ø{P['duong_kinh_vong_truc']:g} mm; {top_ok}/{N} vòng số nằm đúng trục dọc")
    hd = [d for d in D.dims if d.kind == "h"]
    vd = [d for d in D.dims if d.kind == "v"]
    # rendered dimension primitives (lines + texts), not only the Dim objects
    dim_lines = sorted(round(_len(p) * s, 3) for p in D.prims if p.tag in ("dim_chain_line", "dim_overall_line", "dim_single_line"))
    dim_texts = sorted(p.s for p in D.prims if p.tag.startswith("dim_") and p.tag.endswith("_text"))
    want = sorted(round(d.value, 3) for d in D.dims)
    C.add(1, "1.9", "đường kích thước đã dựng: độ dài × tỷ lệ = giá trị; chữ = giá trị (DIMDEC 0)", dim_lines == want and dim_texts == sorted(fmt_value(d.value) for d in D.dims),
          f"{len(dim_lines)} đường kích thước, {len(dim_texts)} chữ; giá trị {collections.Counter(int(v) for v in want)}")
    chain = [d for d in hd if d.role in ("chain", "single")]
    over = [d for d in hd if d.role in ("overall", "single")]
    C.add(1, "1.10", "tổng chuỗi kích thước ngang = dai_nha; kích thước tổng = dai_nha", close(sum(d.value for d in chain), dai, 1e-3) and len(over) == 1 and close(over[0].value, dai, 1e-3),
          f"tổng chuỗi {sum(d.value for d in chain):g} mm ({len(chain)} đoạn); tổng {over[0].value:g} mm" if over else "thiếu kích thước tổng")
    C.add(1, "1.11", "kích thước dọc = nhip", len(vd) == 1 and close(vd[0].value, nhip, 1e-3), f"{vd[0].value:g} mm" if vd else "không có")
    C.add(1, "1.12", "mỗi đoạn chuỗi = buoc_cot; số đoạn = N − 1 (N > 2)", N == 2 or (len(chain) == N - 1 and all(close(d.value, buoc, 1e-3) for d in chain)), f"{len(chain)} đoạn")
    labels = sorted(p.s for p in D.by_tag("bubble_text"))
    wantl = sorted([str(i + 1) for i in range(N)] + ["A", "B"])
    C.add(1, "1.13", "ký hiệu trục: 1..N và A, B", labels == wantl, f"{len(labels)} vòng: {', '.join(wantl)}")
    labs, notes = D.by_tag("col_label"), D.by_tag("col_note")
    want_note = f"TẤT CẢ CỘT: {sec_text}"
    if sp.get("gom_nhan_tiet_dien", True):
        ok14 = len(labs) == 1 and labs[0].s == sec_text and len(notes) == 1 and notes[0].s == want_note and any(
            close(((c.p0[0] + c.p1[0]) / 2 - ox) * s, 0.0, 1e-3) and close(((c.p0[1] + c.p1[1]) / 2 - oy) * s, 0.0, 1e-3) for c in cols if abs(labs[0].pos[0] - c.p1[0] - 2.0) < 1e-6)
        d14 = f"gom nhãn: {len(labs)} nhãn {[t.s for t in labs]} (cần 1, ở cột 1/A), chú thích {[t.s for t in notes]} (cần {want_note!r})"
    else:
        ok14 = len(labs) == 2 * N and all(t.s == sec_text for t in labs) and not notes
        d14 = f"không gom: {len(labs)} nhãn (cần {2 * N}), chú thích {len(notes)} (cần 0)"
    C.add(1, "1.14", "nhãn tiết diện: gom (1 nhãn ở cột 1/A + chú thích 'TẤT CẢ CỘT: …') hoặc không gom (nhãn ở mọi cột)", ok14, d14)
    check_expressions(C, [p.s for p in D.prims if isinstance(p, Text)], 1, "1.20", "chữ trên bản vẽ")


check_primitives = check_primitives_b      # backwards-compatible name (tests)


# ------------------------------------------------------------------ 2. DXF
def freecad_import(dxf: str):
    if not os.path.isfile(FREECADCMD):
        return None, f"không tìm thấy FreeCADCmd ({FREECADCMD}); đặt FREECADCMD_EXE"
    env = dict(os.environ, DXF_IN=dxf)
    try:
        r = subprocess.run([FREECADCMD, os.path.join(HERE, "fc_import_check.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=240)
    except subprocess.TimeoutExpired:
        return None, "FreeCADCmd nhập DXF quá 240 giây"
    out = r.stdout + r.stderr
    m = re.search(r"FCRESULT (\{.*\})", out)
    return dict(res=json.loads(m.group(1)) if m else {}, text=out), ""


def dxf_geometry_diff(dx: dict, D) -> dict:
    """Match every primitive with a DXF entity of the same layer/type at the expected real-mm position. Returns {type: (matched, total)}."""
    s = D.scale
    ox, oy = D.origin
    T = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    ents = collections.defaultdict(list)
    for e in dx["ents"]:
        r = e["rec"]
        try:
            if e["type"] == "LINE":
                ents[("LINE", e["layer"])].append(((f(r, 10), f(r, 20)), (f(r, 11), f(r, 21))))
            elif e["type"] == "CIRCLE":
                ents[("CIRCLE", e["layer"])].append(((f(r, 10), f(r, 20)), f(r, 40)))
            elif e["type"] == "LWPOLYLINE":
                xs, ys = [float(v) for v in r[10]], [float(v) for v in r[20]]
                ents[("LWPOLYLINE", e["layer"])].append((min(xs), min(ys), max(xs), max(ys)))
            elif e["type"] == "TEXT":
                px, py = ((f(r, 11), f(r, 21)) if 11 in r else (f(r, 10), f(r, 20)))
                ents[("TEXT", e["layer"])].append((px, py, f(r, 40), f(r, 50) if 50 in r else 0.0, f(r, 41) if 41 in r else 1.0))
        except (KeyError, ValueError, IndexError):
            pass
    res = {}
    tallies = collections.defaultdict(lambda: [0, 0])
    for p in D.prims:
        if isinstance(p, Line):
            a, b = T(p.p1), T(p.p2)
            near = lambda e, g, a=a, b=b: (close(g[0][0], a[0], TOL_DXF) and close(g[0][1], a[1], TOL_DXF) and close(g[1][0], b[0], TOL_DXF) and close(g[1][1], b[1], TOL_DXF)) or \
                                          (close(g[0][0], b[0], TOL_DXF) and close(g[0][1], b[1], TOL_DXF) and close(g[1][0], a[0], TOL_DXF) and close(g[1][1], a[1], TOL_DXF))
            key = ("LINE", p.layer)
        elif isinstance(p, Rect):
            a, b = T(p.p0), T(p.p1)
            near = lambda e, g, a=a, b=b: all(close(x, y, TOL_DXF) for x, y in zip(g, (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))))
            key = ("LWPOLYLINE", p.layer)
        elif isinstance(p, Circle):
            c = T(p.c)
            near = lambda e, g, c=c, p=p: close(g[0][0], c[0], TOL_DXF) and close(g[0][1], c[1], TOL_DXF) and close(g[1], p.r * s, TOL_DXF)
            key = ("CIRCLE", p.layer)
        else:
            c = T(p.pos)
            near = lambda e, g, c=c, p=p: close(g[0], c[0], TOL_DXF) and close(g[1], c[1], TOL_DXF) and close(g[2], p.h * s, TOL_DXF) and close(g[3], p.rot, 1e-6) and close(g[4], p.wf, 1e-6)
            key = ("TEXT", p.layer)
        pool = ents[key]
        ok = False
        for i, g in enumerate(pool):
            if near(None, g):
                pool.pop(i)
                ok = True
                break
        tallies[key[0]][1] += 1
        tallies[key[0]][0] += int(ok)
    return {k: tuple(v) for k, v in tallies.items()}


def check_dxf(C: Checks, D, sp, profile, dxf: str, do_fc: bool):
    dx = read_dxf(dxf)
    s = D.scale
    if D.kind == "B":
        N, nhip, dai, buoc = sp["so_truc_doc"], sp["nhip"], sp["dai_nha"], sp["buoc_cot"]
        b, h = sp["section"]["b"], sp["section"]["h"]
    C.add(2, "2.1", "định dạng AC1021, UTF-8 hợp lệ, không dùng escape \\U+", dx["version"] == "AC1021" and dx["utf8_ok"] and dx["escapes"] == 0,
          f"version={dx['version']} utf8={dx['utf8_ok']} byte≥0x80={dx['high_bytes']} escape={dx['escapes']} size={dx['size']:,}")
    C.add(2, "2.2", "$LTSCALE = tỷ lệ bản vẽ", close(dx["ltscale"], s, 1e-9), f"{dx['ltscale']:g} (tỷ lệ 1:{s})")
    names = set(profile) | {"0"}
    miss = names - set(dx["layers"])
    wrong = [n for n in profile if n in dx["layers"] and (dx["layers"][n]["color"], dx["layers"][n]["ltype"], dx["layers"][n]["lw"], dx["layers"][n]["plot"]) !=
             (profile[n]["color"], profile[n]["ltype"], profile[n]["lw"], profile[n]["plot"])]
    C.add(2, "2.3", "18 layer TCVN (+ layer 0): tên, màu, linetype, lineweight đúng profile", not miss and not wrong and len(dx["layers"]) == 19,
          f"{len(dx['layers'])} layer; thiếu {sorted(miss)}; sai {wrong}")
    pats_ok = all(dx["ltypes"].get(k) == [float(x) for x in v[1]] for k, v in LTYPES.items())
    C.add(2, "2.4", "mẫu nét HIDDEN/CENTER/DASHED đúng giá trị (mm giấy)", pats_ok, f"{ {k: v for k, v in dx['ltypes'].items() if v} }")
    exp = expected_counts(D)
    got = dict(dx["by_layer_type"])
    C.add(2, "2.5", "số entity theo (layer, loại) khớp danh sách primitives", exp == got,
          f"tổng {sum(got.values())} entity {dict(dx['by_type'])}; lệch: { {k: (exp.get(k), got.get(k)) for k in set(exp) | set(got) if exp.get(k) != got.get(k)} }")
    want_t = collections.Counter(p.s for p in D.prims if isinstance(p, Text))
    got_t = collections.Counter(t for _, t in dx["texts"])
    C.add(2, "2.6", "chữ trong DXF (kể cả tiếng Việt) khớp chính xác", want_t == got_t,
          f"{sum(got_t.values())} chuỗi TEXT; ví dụ: {[t for t in got_t if any(ord(c) > 127 for c in t)][:3]}")
    if D.kind == "B":
        axis = [e for e in dx["ents"] if e["type"] == "LINE" and e["layer"] == LAYER_AXIS]
        vx = sorted({round(f(e["rec"], 10), 3) for e in axis if close(f(e["rec"], 10), f(e["rec"], 11), 1e-6)})
        hy = sorted({round(f(e["rec"], 20), 3) for e in axis if close(f(e["rec"], 20), f(e["rec"], 21), 1e-6)})
        C.add(2, "2.7", "toạ độ trục theo mm thật (gốc tại giao 1/A)", vx == [round(i * buoc, 3) for i in range(N)] and hy == [0.0, round(nhip, 3)], f"x trục dọc {vx[:3]}…{vx[-1]}; y trục ngang {hy}")
        cols = [e for e in dx["ents"] if e["type"] == "LWPOLYLINE" and e["layer"] == LAYER_COLUMN]
        sizes = collections.Counter()
        for e in cols:
            xs, ys = [float(v) for v in e["rec"][10]], [float(v) for v in e["rec"][20]]
            sizes[(round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3))] += 1
        C.add(2, "2.8", "cột trong DXF đúng b × h (mm thật)", dict(sizes) == {(round(b, 3), round(h, 3)): 2 * N}, f"{dict(sizes)}")
    elif D.kind == "C":
        import verify_c
        verify_c.check_dxf_c(C, D, sp, dx)
    elif D.kind == "D":
        import verify_d
        verify_d.check_dxf_d(C, D, sp, dx)
    else:
        import verify_a
        verify_a.check_dxf_a(C, D, sp, dx)
    check_expressions(C, [t for _, t in dx["texts"]], 2, "2.12", "chữ trong DXF")
    gd = dxf_geometry_diff(dx, D)
    C.add(2, "2.9", "mọi primitive có entity DXF đúng vị trí/kích thước (±0,001 mm thật)", all(a == t for a, t in gd.values()) and sum(t for _, t in gd.values()) == len(D.prims),
          "; ".join(f"{k} {a}/{t}" for k, (a, t) in sorted(gd.items())))
    if do_fc:
        info, err = freecad_import(dxf)
        if info is None:
            C.add(2, "2.10", "FreeCAD nhập DXF không lỗi", False, err)
        else:
            res, txt = info["res"], info["text"]
            bad = re.search(r"UnicodeError|Traceback|Aborting|UTF8 conversion", txt)
            m = re.search(r"Total entities read:\s*(\d+)", txt)
            enc = re.search(r"File encoding:\s*(\S+)", txt)
            ok = res.get("ok") and not bad and m and int(m.group(1)) == len(dx["ents"]) and len(res.get("layers", [])) == 19
            C.add(2, "2.10", "FreeCAD nhập DXF: không UnicodeError, đủ entity, đủ 19 layer", ok,
                  f"encoding={enc.group(1) if enc else '?'}; entity đọc {m.group(1) if m else '?'}/{len(dx['ents'])}; {len(res.get('layers', []))} layer; {res.get('objects')} object; lỗi: {bad.group(0) if bad else 'không'}")
            vi = [t for t in res.get("texts", []) if any(ord(c) > 127 for c in t)]
            C.add(2, "2.11", "FreeCAD đọc đúng chữ Việt (không còn \\U+)", bool(vi) and not any("\\U+" in t for t in res.get("texts", [])), f"ví dụ: {vi[:1]}")
    return dx


# ------------------------------------------------------------------ 3. DWG
def check_dwg(C: Checks, D, dx_src: dict, dwg: str, workdir: str, dwg_info: dict, sp=None):
    C.add(3, "3.1", "ODA tạo DWG hợp lệ (header AC1032, returncode 0, không file .err)", dwg_info.get("ok") and dwg_info.get("header") == "AC1032" and dwg_info.get("returncode") == 0 and not dwg_info.get("err_files"),
          f"{dwg_info.get('size', 0):,} byte, {dwg_info.get('seconds', 0):.1f}s, returncode={dwg_info.get('returncode')}, file .err: {dwg_info.get('err_files')}")
    back = os.path.join(workdir, "roundtrip_back.dxf")
    try:
        r = oda.dwg_to_dxf(dwg, back, "ACAD2018")
    except oda.OdaError as e:
        C.add(3, "3.2", "chuyển ngược DWG → DXF", False, str(e))
        return
    if not r["ok"]:
        C.add(3, "3.2", "chuyển ngược DWG → DXF", False, f"thất bại: {r}")
        return
    bx = read_dxf(back)
    C.add(3, "3.2", "số entity sau khứ hồi = bản gốc (theo layer, loại)", dict(bx["by_layer_type"]) == dict(dx_src["by_layer_type"]),
          f"gốc {sum(dx_src['by_type'].values())} → sau {sum(bx['by_type'].values())} entity {dict(bx['by_type'])}; {r['seconds']:.1f}s")
    C.add(3, "3.3", "thuộc tính 19 layer không đổi sau khứ hồi", dict(bx["layers"]) == dict(dx_src["layers"]), f"{len(bx['layers'])} layer")
    C.add(3, "3.4", "chữ Việt không đổi sau khứ hồi", collections.Counter(t for _, t in bx["texts"]) == collections.Counter(t for _, t in dx_src["texts"]), "so sánh toàn bộ chuỗi TEXT")
    gd = dxf_geometry_diff(bx, D)
    C.add(3, "3.5", "toạ độ/kích thước/chiều cao chữ sau khứ hồi vẫn khớp primitives (±0,001 mm thật)", all(a == t for a, t in gd.values()) and sum(t for _, t in gd.values()) == len(D.prims),
          "; ".join(f"{k} {a}/{t}" for k, (a, t) in sorted(gd.items())))
    C.add(3, "3.6", "$LTSCALE và mẫu nét giữ nguyên sau khứ hồi", close(bx["ltscale"], D.scale, 1e-9) and all(bx["ltypes"].get(k) == [float(x) for x in v[1]] for k, v in LTYPES.items()),
          f"LTSCALE {bx['ltscale']:g}; {bx['ltypes'].get('CENTER')}")
    check_title_fit_dxf(C, D, bx, 3, "3.7", "DWG (đọc lại sau khứ hồi)")
    check_text_anchor(C, D, bx, 3, "3.8", "DWG (đọc lại sau khứ hồi)")
    if D.kind == "D" and sp is not None:
        import verify_d
        verify_d.check_dwg_d(C, D, sp, bx)


# ------------------------------------------------------------------ 4/5. PDF
def _straight(p):
    return p["kind"] == "stroke" and p["n"] == 2 and not p["curve"]


def expected_pdf_shapes(D, profile):
    top = lambda y: SHEETS[D.sheet].h - y
    out = []
    for p in D.prims:
        if isinstance(p, Text):
            continue
        lw, pat = layer_style(profile, p.layer)
        if isinstance(p, Line):
            xs, ys = (p.p1[0], p.p2[0]), (p.p1[1], p.p2[1])
            cls = "line"
        elif isinstance(p, Rect):
            xs, ys = (p.p0[0], p.p1[0]), (p.p0[1], p.p1[1])
            cls = "rect"
        else:
            xs, ys = (p.c[0] - p.r, p.c[0] + p.r), (p.c[1] - p.r, p.c[1] + p.r)
            cls = "circle"
        out.append(dict(cls=cls, bb=(min(xs), top(max(ys)), max(xs), top(min(ys))), lw=lw, dashed=bool(pat), tag=p.tag, layer=p.layer))
    return out


def _pdf_class(p):
    if p["kind"] != "stroke":
        return None
    if p["curve"]:
        return "circle"
    return "line" if p["n"] == 2 else "rect"


def pdf_text_match(D, paths):
    """Each text must have glyph outline(s) at the expected place: the union of the glyphs inside the expected (rotated) text box must be centred on the
    expected centre (tolerance 0.8 mm, or 5 % of the string width for centred text / 15 % for left- or right-aligned text, whose width is only estimated);
    digit-only strings of >= 3 digits (horizontal or vertical) must also have the expected ink width. Slanted text: position only (suy luận: rotation is not decoded)."""
    top = lambda y: SHEETS[D.sheet].h - y
    glyphs = [p for p in paths if p["kind"] == "fill" and p["n"] > 30 and (p["bb"][2] - p["bb"][0]) < 120 and (p["bb"][3] - p["bb"][1]) < 25]
    ok, bad, wr = 0, [], []
    n_digit = 0
    for t in (p for p in D.prims if isinstance(p, Text)):
        em = cap_to_em(t.h)
        w = TBK.est_width(t.s, em, t.bold) * t.wf
        ax, ay = t.pos
        off = {"left": w / 2, "center": 0.0, "right": -w / 2}[t.halign]
        phi = math.radians(t.rot)
        cx, cy = ax + off * math.cos(phi) - (t.h / 2) * math.sin(phi), top(ay + off * math.sin(phi) + (t.h / 2) * math.cos(phi))
        hx = abs(math.cos(phi)) * w / 2 + abs(math.sin(phi)) * t.h / 2
        hy = abs(math.sin(phi)) * w / 2 + abs(math.cos(phi)) * t.h / 2
        marg = 0.5
        hit = [g for g in glyphs if abs((g["bb"][0] + g["bb"][2]) / 2 - cx) <= hx + marg and abs((g["bb"][1] + g["bb"][3]) / 2 - cy) <= hy + marg]
        good = False
        if hit:
            ux, uy = (min(g["bb"][0] for g in hit) + max(g["bb"][2] for g in hit)) / 2, (min(g["bb"][1] for g in hit) + max(g["bb"][3] for g in hit)) / 2
            tol = max(0.8, (0.05 if t.halign == "center" else 0.15) * w)
            tol_y = max(0.8, 0.6 * t.h) if t.rot % 90 == 0 and t.rot % 180 == 0 else tol
            tol_x = tol if t.rot % 180 == 0 else max(0.8, 0.6 * t.h) if t.rot % 90 == 0 else tol
            good = abs(ux - cx) <= tol_x and abs(uy - cy) <= tol_y
        if good:
            ok += 1
            if re.fullmatch(r"\d{3,}", t.s) and t.rot % 90 == 0:
                n_digit += 1
                ink = max(((g["bb"][2] - g["bb"][0]) if t.rot % 180 == 0 else (g["bb"][3] - g["bb"][1])) for g in hit)
                if not (0.78 * w <= ink <= 1.02 * w):
                    wr.append((t.s, round(ink, 2), round(w, 2)))
        else:
            bad.append(t.s)
    return ok, bad, wr, n_digit


def check_pdf(C: Checks, D, sp, dx: dict, pdf: str, png: str | None, profile: dict):
    a = analyze_pdf(pdf)
    paths = a["paths"]
    s = D.scale
    W, H = a["page_mm"]
    sh = SHEETS[D.sheet]
    FRAME_X0, FRAME_X1, FRAME_Y0, FRAME_Y1 = sh.x0, sh.x1, sh.y0, sh.y1
    TB_X0, TB_W, TB_Y0, TB_TOP = sh.tb_x0, sh.tb_w, sh.tb_y0, sh.tb_y1
    top = lambda y: sh.h - y
    C.add(4, "4.1", f"khổ trang {sh.name}: {sh.w:g} × {sh.h:g} mm", close(W, sh.w, 0.3) and close(H, sh.h, 0.3), f"{W:.2f} × {H:.2f} mm (khổ {sh.name})")
    fr = [p for p in paths if p["kind"] == "stroke" and close(p["bb"][0], FRAME_X0, 0.08) and close(p["bb"][1], top(FRAME_Y1), 0.08)
          and close(p["bb"][2], FRAME_X1, 0.08) and close(p["bb"][3], top(FRAME_Y0), 0.08)]
    C.add(4, "4.2", f"khung bản vẽ {sh.frame_w:g} × {sh.frame_h:g} tại lề trái 20 / các lề khác 10, nét 0,7 mm", len(fr) == 1 and close(fr[0]["lw"], 0.7, 0.03),
          f"bbox {tuple(round(x, 2) for x in fr[0]['bb'])} lw={fr[0]['lw']:.2f}" if fr else "không tìm thấy")
    tb = [p for p in paths if p["kind"] == "stroke" and close(p["bb"][0], TB_X0, 0.08) and close(p["bb"][1], top(TB_TOP), 0.08)
          and close(p["bb"][2], TB_X0 + TB_W, 0.08) and close(p["bb"][3], top(TB_Y0), 0.08)]
    C.add(4, "4.3", "khung tên 180 × 65 ở góc dưới phải, nét bao 0,7 mm (= nét khung)", len(tb) == 1 and close(tb[0]["lw"], 0.7, 0.03),
          f"{tb[0]['bb'][2] - tb[0]['bb'][0]:.2f} × {tb[0]['bb'][3] - tb[0]['bb'][1]:.2f} mm" if tb else "không tìm thấy")
    inside = [p for p in paths if _straight(p) and p["bb"][0] >= TB_X0 - 0.1 and p["bb"][2] <= TB_X0 + TB_W + 0.1 and p["bb"][1] >= top(TB_TOP) - 0.1 and p["bb"][3] <= top(TB_Y0) + 0.1
              and close(p["lw"], 0.25, 0.03) and (close(p["bb"][0], p["bb"][2], 0.01) or close(p["bb"][1], p["bb"][3], 0.01))]
    C.add(4, "4.4", f"{len(TBK.DIVIDERS)} đường chia khung tên (nét 0,25 mm) trong khung tên", len(inside) == len(TBK.DIVIDERS), f"đo {len(inside)}")
    C.info(4, "4.5", "font trong PDF", f"font nhúng: {a['fonts'] or 'không có; chữ là nét vẽ (đã chấp nhận); vị trí chữ được kiểm ở 5.5'}")
    C.add(4, "4.6", "xuất được PNG để xem", bool(png and os.path.isfile(png) and os.path.getsize(png) > 1000), f"{png}" if png else "không")

    # ---- 5: every primitive (incl. frame / title block) must exist in the PDF at the same place
    exp = expected_pdf_shapes(D, profile)
    pool = [(i, p, _pdf_class(p)) for i, p in enumerate(paths) if _pdf_class(p)]
    used: set = set()
    tally = collections.defaultdict(lambda: [0, 0])
    unmatched = []
    for e in exp:
        tally[e["cls"]][1] += 1
        for i, p, cls in pool:
            if i in used or cls != e["cls"]:
                continue
            if all(close(x, y, TOL_PDF) for x, y in zip(p["bb"], e["bb"])) and close(p["lw"], e["lw"], 0.03) and bool(p["dash"]) == e["dashed"]:
                used.add(i)
                tally[e["cls"]][0] += 1
                break
        else:
            unmatched.append((e["tag"], e["layer"], tuple(round(x, 2) for x in e["bb"])))
    allm = sum(v[0] for v in tally.values()) == len(exp) == sum(1 for p in D.prims if not isinstance(p, Text))
    C.add(5, "5.1", "mọi nét (đoạn thẳng, hình chữ nhật, vòng tròn) của primitives có trong PDF đúng vị trí ±0,06 mm, độ dày, nét đứt/liền", allm,
          "; ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(tally.items())) + (f"; không khớp: {unmatched[:3]}" if unmatched else ""))
    extra = [p for i, p, cls in pool if i not in used]
    C.add(5, "5.2", "PDF không có nét thừa ngoài primitives", not extra, f"{len(extra)} nét thừa" + (f", ví dụ bbox {[tuple(round(x, 2) for x in p['bb']) for p in extra[:2]]}" if extra else ""))
    dxn = dx["by_type"]
    extra_b = ""
    ok_b = True
    if D.kind == "B":
        ok_b = dxn["CIRCLE"] == sp["so_truc_doc"] + 2
        extra_b = f" (N+2 = {sp['so_truc_doc'] + 2})"
    C.add(5, "5.3", "số nét PDF = số LINE / LWPOLYLINE / CIRCLE của DXF", tally["line"][1] == dxn["LINE"] and tally["rect"][1] == dxn["LWPOLYLINE"] and tally["circle"][1] == dxn["CIRCLE"] and ok_b,
          f"LINE {tally['line'][1]}/{dxn['LINE']}, rect {tally['rect'][1]}/{dxn['LWPOLYLINE']}, circle {tally['circle'][1]}/{dxn['CIRCLE']}{extra_b}")
    cen = [p for p in paths if _straight(p) and len(p["dash"]) == 4]
    want = [abs(x) for x in LTYPES["CENTER"][1]]
    n_center = sum(1 for p in D.prims if isinstance(p, Line) and profile[p.layer]["ltype"] == "CENTER")
    pat_ok = bool(cen) and all(all(close(x, y, 0.15) for x, y in zip(p["dash"], want)) for p in cen)
    C.add(5, "5.4", "nét CENTER: số lượng = số đường layer CENTER của primitives, mẫu nét 12 / 1,5 / 2 / 1,5 mm", len(cen) == n_center and n_center > 0 and pat_ok,
          f"PDF {len(cen)} / primitives {n_center}; mẫu {[round(x, 2) for x in cen[0]['dash']] if cen else None}")
    check_title_fit_pdf(C, D, paths)
    if D.kind == "D":
        import verify_d
        verify_d.check_pdf_d(C, D, sp, dx, paths, profile)
    ok, bad, wr, n_digit = pdf_text_match(D, paths)
    ntext = sum(1 for p in D.prims if isinstance(p, Text))
    C.add(5, "5.5", "mỗi chuỗi chữ (kể cả khung tên) có nét chữ đúng vị trí; số có ≥ 3 chữ số đúng độ rộng nét chữ", ok == ntext and not wr,
          f"{ok}/{ntext} chuỗi có nét chữ tại vị trí; độ rộng sai: {wr[:3]}; không thấy: {bad[:3]}. Giá trị từng chữ số trong PDF không giải mã được (suy luận: cùng nguồn primitives; 5.1 xác nhận chiều dài đường kích thước)")
    # every dimension must exist in the PDF as a dimension line of the exact real length, and its label text must be in the DXF
    vals = [d.value / D.view_scale(d.view) for d in D.dims]         # paper length of each dimension line (view scale)
    dim_lines = [p for p in paths if _straight(p) and close(p["lw"], 0.25, 0.03) and not p["dash"] and (close(p["bb"][0], p["bb"][2], 0.01) or close(p["bb"][1], p["bb"][3], 0.01))]
    n_m, bad_v = greedy_match(vals, dim_lines, lambda v, p: close(max(p["bb"][2] - p["bb"][0], p["bb"][3] - p["bb"][1]), v, TOL_PDF))
    dxt = collections.Counter(t for lay, t in dx["texts"] if lay == LAYER_DIM)
    want_t = collections.Counter(p.s for p in D.prims if isinstance(p, Text) and p.tag.startswith("dim_") and p.tag.endswith("_text"))
    C.add(5, "5.6", "mỗi kích thước có đường kích thước PDF dài đúng (± 0,06 mm × tỷ lệ) và chữ tương ứng trong DXF", bool(vals) and n_m == len(vals) and dxt == want_t,
          f"{n_m}/{len(vals)} đường khớp (giá trị thật {sorted(set(round(d.value, 2) for d in D.dims))}); chữ DXF {dict(dxt)}")
    return a


def check_title_rows(C: Checks, D, sp):
    """1.30: left block of the title block (cells 8-14). Default (the spec says nothing about signatures): the three role labels with the sample names and the
    drawing date; otherwise exactly the rows of the spec; every printed text lies inside the left block (x 0..90, rows area 49 mm high)."""
    kt = sp["khung_ten"]
    rows = kt.get("ky", [])
    sh = SHEETS[D.sheet]
    exp = {}
    if kt.get("ky_nguon") == "mac_dinh":
        sample = [("Chủ trì", "NGUYỄN VĂN A"), ("Kiểm tra", "TRẦN VĂN B"), ("Thiết kế", "LÊ VĂN C")]
        ok_rows = [(r["chuc_danh"], r["ho_ten"]) for r in rows] == sample
    else:
        ok_rows = True
    date = kt.get("ngay") or None
    for k, r in enumerate(rows, start=1):
        exp[f"row{k}_role"] = r["chuc_danh"]
        if r.get("ho_ten"):
            exp[f"row{k}_name"] = r["ho_ten"]
            exp[f"row{k}_date"] = r.get("ngay", "")
    got_raw = {k: v for k, v in D.fields.items() if k.startswith("row")}
    got = {k: (v + " " + got_raw[k + "_2"] if k + "_2" in got_raw else v) for k, v in got_raw.items() if not k.endswith("_2")}      # a long name may be printed on two lines
    lay = TBK.layout(D.fields)
    fields_ok = got == {k: v for k, v in exp.items() if v}
    date_ok = all(re.fullmatch(r"\d\d/\d\d/\d{4}", v) and (date is None or v == date) for k, v in got.items() if k.endswith("_date"))
    left = [p for p in D.prims if isinstance(p, Text) and p.tag == "tb_text" and sh.tb_x0 <= p.pos[0] <= sh.tb_x0 + 90 and sh.tb_y1 - 16 - 49 <= p.pos[1] <= sh.tb_y1 - 16]
    inside = True
    printed_ok = len(left) == len(got_raw)                  # exactly the expected texts are printed in the left block, nothing else
    for name, val in got_raw.items():
        ax, ay = TBK.field_anchor(name, sh, lay[name]["dy"])
        printed_ok &= any(p.s == val and close(p.pos[0], ax, 1e-6) and close(p.pos[1], ay, 1e-6) for p in left)
    nonempty_roles = sum(1 for k, v in got.items() if k.endswith("_role") and v)
    default_filled = kt.get("ky_nguon") != "mac_dinh" or nonempty_roles == 3
    C.add(1, "1.30", "khung tên, khối trái (ô 8-14): mặc định có 3 nhãn chức danh + tên mẫu + ngày của bản vẽ; khi spec nêu thì đúng theo spec; mọi chữ nằm trong khối trái",
          ok_rows and fields_ok and date_ok and inside and printed_ok and default_filled,
          f"nguồn {kt.get('ky_nguon')}; {nonempty_roles} hàng có nhãn; ô {got}; đủ chữ trong khung tên {printed_ok}; nằm trong khối trái {inside}")


def _fit_problems(cells, s, ax, ay, h, wf, halign, bold=False):
    """Why a title-block text (string s, anchor, cap height h, width factor wf) does not stay inside its cell, per the Arial-width estimate (+5 %); [] when it fits."""
    em = cap_to_em(h)
    w = TBK.cons_width(s, em, wf, bold)
    cell = [c for c in cells if c[0] <= ax <= c[2] and c[1] < ay <= c[3]]
    if not cell:
        return ["không nằm trong ô nào"]
    c = cell[0]
    x0, x1 = {"left": (ax, ax + w), "center": (ax - w / 2, ax + w / 2), "right": (ax - w, ax)}[halign]
    bad = []
    if x0 < c[0] + TBK.TB_MARGIN - 1e-6 or x1 > c[2] - TBK.TB_MARGIN + 1e-6:
        bad.append(f"rộng {w:.1f} mm (đo Arial + 5 %) tràn ô {c[2] - c[0]:g} mm (lề {TBK.TB_MARGIN:g} mm)")
    if em < TBK.MIN_EM - 1e-6 or not (TBK.MIN_WF - 1e-6 <= wf <= 1.0 + 1e-6):
        bad.append(f"cỡ chữ {em:.2f} mm, hệ số rộng {wf:g} ngoài giới hạn ({TBK.MIN_EM:g} mm, {TBK.MIN_WF:g})")
    if ay < c[1] + 0.3 or ay + h > c[3] - 0.5:
        bad.append("chữ chạm mép trên/dưới của ô")
    return bad


def check_title_fit(C: Checks, D):
    """1.31: every text printed in a title-block cell (names, date, project, investor, firm, title, symbol, scale, captions) stays inside its cell minus a 1.5 mm margin
    on each side by the Arial-width estimate (real advance widths + 5 %), with em size >= 2 mm and width factor in [0.7, 1]."""
    sh = SHEETS[D.sheet]
    cells = TBK.all_cells(sh)
    tx = [p for p in D.prims if isinstance(p, Text) and p.tag in ("tb_text", "tb_caption")]
    bad = [(t.s, b) for t in tx for b in [_fit_problems(cells, t.s, t.pos[0], t.pos[1], t.h, t.wf, t.halign, t.bold)] if b]
    n_fit = sum(1 for t in tx if t.wf < 1.0 - 1e-9 or abs(cap_to_em(t.h) - TBK.FIELDS.get(t.field, (0, 0, 0, cap_to_em(t.h)))[3]) > 1e-6)
    C.add(1, "1.31", "chữ trong mọi ô khung tên không vượt bề rộng ô (đo theo font Arial + 5 % dự phòng, lề 1,5 mm); co chữ: hệ số rộng ≥ 0,7, cao ≥ 2 mm", bool(tx) and not bad,
          f"{len(tx)} chữ trong khung tên, {n_fit} chữ đã co; vi phạm: {bad[:3]}")


def check_title_fit_dxf(C: Checks, D, dx: dict, group: int, cid: str, label: str):
    """Same rule on the TEXT entities of a DXF (code 41 = width factor), converted back to sheet mm: every title-block TEXT inside its cell."""
    sh = SHEETS[D.sheet]
    cells = TBK.all_cells(sh)
    s = D.scale
    ox, oy = D.origin
    n, bad = 0, []
    for e in dx["ents"]:
        if e["type"] != "TEXT":
            continue
        r = e["rec"]
        try:
            ax, ay = ((f(r, 11), f(r, 21)) if 11 in r else (f(r, 10), f(r, 20)))
            ax, ay = ax / s + ox, ay / s + oy
            if not (sh.tb_x0 <= ax <= sh.tb_x0 + sh.tb_w and sh.tb_y0 <= ay <= sh.tb_y1):
                continue
            h = f(r, 40) / s
            wf = f(r, 41) if 41 in r else 1.0
            ha = {0: "left", 1: "center", 2: "right"}.get(int(float(r[72][0])) if 72 in r else 0, "left")
            txt = unesc("".join(r.get(3, [])) + (r.get(1) or [""])[0])
        except (KeyError, ValueError, IndexError):
            continue
        n += 1
        b = _fit_problems(cells, txt, ax, ay, h, wf, ha)
        if b:
            bad.append((txt, b))
    want = sum(1 for p in D.prims if isinstance(p, Text) and p.tag in ("tb_text", "tb_caption"))
    C.add(group, cid, f"chữ khung tên trong {label}: mọi TEXT nằm trong ô, không vượt bề rộng ô (đo Arial + 5 %, có xét hệ số rộng mã 41)", n == want and not bad,
          f"{n}/{want} TEXT khung tên; vi phạm: {bad[:3]}")


def check_text_anchor(C: Checks, D, dx: dict, group: int, cid: str, label: str):
    """Every centred / right-aligned TEXT (code 72 = 1 or 2) must carry the REAL left end of its baseline in code 10: 10 + width/2 (centre) or 10 + width (right) = code 11,
    within 1 mm on paper. Some readers (a DWG converted by ODA, as drawn by ZWCAD) place the text from code 10 and ignore the justification, so 10 = 11 shifts every
    centred text to the right by half its width. The width is measured on the real Arial file when it is installed (else the embedded table), at the TEXT's own height and
    width factor (code 41)."""
    import fontmetrics
    ttf = fontmetrics.have_ttf(False)
    s = D.scale
    n, worst, bad = 0, 0.0, []
    for e in dx["ents"]:
        if e["type"] != "TEXT":
            continue
        r = e["rec"]
        try:
            hj = int(float(r[72][0])) if 72 in r else 0
            if hj not in (1, 2):
                continue
            x10, y10, x11, y11 = f(r, 10), f(r, 20), f(r, 11), f(r, 21)
            h = f(r, 40) / s
            wf = f(r, 41) if 41 in r else 1.0
            phi = math.radians(f(r, 50) if 50 in r else 0.0)
            txt = unesc("".join(r.get(3, [])) + (r.get(1) or [""])[0])
        except (KeyError, ValueError, IndexError):
            continue
        n += 1
        w = fontmetrics.text_em(txt, False, "ttf") * (h / ARIAL_CAP) * wf * (0.5 if hj == 1 else 1.0)          # paper mm, from the anchor back to the left end
        ex, ey = x11 / s - w * math.cos(phi), y11 / s - w * math.sin(phi)
        err = math.hypot(x10 / s - ex, y10 / s - ey)
        worst = max(worst, err)
        if err > 1.0:
            bad.append((txt, round(err, 2)))
    want = sum(1 for p in D.prims if isinstance(p, Text) and p.halign in ("center", "right"))
    C.add(group, cid, f"{label}: mọi TEXT căn giữa/phải ghi mã 10 = điểm đầu chân chữ thật (10 + bề rộng/2 hoặc 10 + bề rộng = mã 11, sai số ≤ 1 mm giấy)", n == want and n > 0 and not bad,
          f"{n}/{want} TEXT căn giữa/phải; sai lệch lớn nhất {worst:.2f} mm giấy (đo bằng {'arial.ttf' if ttf else 'bảng Arial nhúng'}); vi phạm: {bad[:3]}")


def check_title_fit_pdf(C: Checks, D, paths):
    """5.7: measured in the PDF: no glyph outline of the title block crosses its cell border or comes within 1.5 mm of the left/right border (ink actually printed)."""
    sh = SHEETS[D.sheet]
    cells = TBK.all_cells(sh)
    H = sh.h
    glyphs = [p for p in paths if p["kind"] == "fill" and (p["bb"][2] - p["bb"][0]) < 60 and (p["bb"][3] - p["bb"][1]) < 25
              and sh.tb_x0 <= (p["bb"][0] + p["bb"][2]) / 2 <= sh.tb_x0 + sh.tb_w and H - sh.tb_y1 <= (p["bb"][1] + p["bb"][3]) / 2 <= H - sh.tb_y0]
    bad = []
    for g in glyphs:
        bb = g["bb"]
        cx, cy = (bb[0] + bb[2]) / 2, H - (bb[1] + bb[3]) / 2
        cell = [c for c in cells if c[0] <= cx <= c[2] and c[1] <= cy <= c[3]]
        if not cell:
            bad.append(("ngoài ô", tuple(round(x, 1) for x in bb)))
            continue
        c = cell[0]
        m = TBK.TB_MARGIN - 0.35
        if bb[0] < c[0] + m or bb[2] > c[2] - m or bb[1] < H - c[3] + 0.1 or bb[3] > H - c[1] - 0.1:
            bad.append(("tràn ô", tuple(round(x, 1) for x in bb)))
    C.add(5, "5.7", "đo trong PDF: nét chữ khung tên không chạm/vượt đường kẻ ô (cách lề trái/phải ≥ 1,5 mm)", bool(glyphs) and not bad, f"{len(glyphs)} nét chữ trong khung tên; vi phạm: {bad[:3]}")


def run_all(D, sp, profile, files: dict, do_fc=True, do_dwg=True, do_pdf=True, dwg_info=None, model3d=None):
    C = Checks()
    if D.kind == "A":
        import verify_a
        verify_a.check_primitives_a(C, D, sp)
    elif D.kind == "C":
        import verify_c
        verify_c.check_primitives_c(C, D, sp)
    elif D.kind == "D":
        import verify_d
        verify_d.check_primitives_d(C, D, sp)
    else:
        check_primitives_b(C, D, sp)
    check_title_rows(C, D, sp)
    check_title_fit(C, D)
    dx = check_dxf(C, D, sp, profile, files["dxf"], do_fc)
    check_title_fit_dxf(C, D, dx, 2, "2.13", "DXF")
    check_text_anchor(C, D, dx, 2, "2.14", "DXF")
    if do_dwg:
        check_dwg(C, D, dx, files["dwg"], files.get("work") or os.path.dirname(files["dxf"]), dwg_info or {}, sp)
    if do_pdf:
        check_pdf(C, D, sp, dx, files["pdf"], files.get("png"), profile)
    if D.kind == "A" and model3d is not None:
        import verify_a
        verify_a.check_3d_a(C, D, sp, model3d)
    return C
