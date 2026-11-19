"""Verification specific to drawing type D (purlin plan of a roof). Every expected value is derived HERE from the spec numbers with its own formulas (never from build_d.py):
exact rational arithmetic for the purlin positions, n = smallest integer with n^2 * buoc_xa_go^2 >= L^2 (loop, no square root), printed numbers rounded half up with Decimal.
Layer: 1 primitives, 2 DXF read back, 3 DWG read back (same function as 2), 5 PDF strokes against the DXF. New check ids only (1.34-1.44, 2.22-2.25, 3.9, 5.8): no id is shared with
the checks of type A, B or C. Details say "suy luận" for anything inferred and not measured.
"""
from __future__ import annotations

import collections
import math
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from fractions import Fraction

from primitives import Line, Text, cap_to_em, prim_bbox
from readers import f, unesc
from tcvn import SHEETS, est_width
from verify import Checks, check_expressions, close

TOL = 1e-6              # real mm, floating point only
TOL_DXF = 1e-3          # real mm (DXF text has 6 decimals)
TOL_PDF = 0.06          # mm on paper
PURLIN_LAYER = "XA-GO"
TITLE = "MẶT BẰNG XÀ GỒ MÁI"
DEFAULT_NO = "KC-04"
RIDGE = "TIM NÓC (HAI XÀ GỒ NÓC TRÙNG NHAU)"
SOFT_MIN, SOFT_MAX = 800, 2000
SCALE_LIMIT = 200
MARGIN = 5.0             # paper mm between any drawn item and the frame / the title block


def _fr(x) -> Fraction:
    return x if isinstance(x, Fraction) else Fraction(repr(float(x)))


def _hu(x: Fraction) -> int:
    """Round half up to a whole number."""
    return math.floor(x + Fraction(1, 2))


def _dec1(x: Fraction) -> str:
    """One decimal with a comma, half up (Decimal); whole numbers without decimals."""
    if x.denominator == 1:
        return str(int(x))
    d = (Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{d:f}".replace(".", ",")


def expect_values(sp: dict) -> dict:
    """All expected numbers from the spec (own formulas)."""
    nhip, i = _fr(sp["nhip"]), _fr(sp["do_doc_mai"]) / 100
    m = int(sp["so_mai"])
    half = nhip / 2 if m == 2 else nhip
    L2 = half * half * (1 + i * i)
    b = _fr(sp["buoc_xa_go"])
    n = 1
    while Fraction(n * n) * b * b < L2 and n < 100000:
        n += 1
    p = half / n
    ys = {half * k / n for k in range(n + 1)}
    if m == 2:
        ys |= {nhip - y for y in ys}
    Y = (L2 * 100) / (n * n)                                           # (10 d)^2
    d1 = ((Decimal(Y.numerator) / Decimal(Y.denominator)).sqrt() + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR)
    real_txt = f"{int(d1) // 10},{int(d1) % 10}"
    dai, buoc = int(sp["dai_nha"]), int(sp["buoc_cot"])
    return dict(m=m, n=n, half=half, nhip=nhip, i=i, L2=L2, L=math.sqrt(float(L2)), p=p, ys=sorted(ys), label=str(_hu(p)), real_txt=real_txt, dai=dai, buoc=buoc, N=dai // buoc + 1,
                b=float(sp["section"]["b"]), h=float(sp["section"]["h"]), theta=math.degrees(math.atan(float(i))))


def expect_notes(sp: dict, X: dict) -> list:
    n, m, half, p = X["n"], X["m"], X["half"], X["p"]
    pur = "XÀ GỒ " + sp["xa_go"]["text"] + (" (MẶC ĐỊNH)" if sp["xa_go_mac_dinh"] else "")
    count = f"SỐ LƯỢNG: 2 x {n + 1} = {2 * (n + 1)} XÀ GỒ (2 MÁI)" if m == 2 else f"SỐ LƯỢNG: {n + 1} XÀ GỒ (1 MÁI, DỐC LÊN TRỤC B)"
    proj = f"{n} x {_dec1(p)} = {_dec1(half)}" if p.denominator == 1 else f"{_dec1(half)}/{n} ≈ {_dec1(p)}"
    pct = (f"{sp['do_doc_mai']:g}").replace(".", ",")
    deg = f"{X['theta']:.1f}".replace(".", ",")
    return [("col_note", f"TẤT CẢ CỘT: {sp['section']['text']}"), ("note_purlin", pur), ("note_count", count),
            ("note_real", f"KHOẢNG CÁCH THỰC DỌC MÁI: {X['real_txt']} MM (TỐI ĐA {sp['buoc_xa_go']:g} MM)"), ("note_proj", f"CHIẾU: {proj} MM; ĐỘ DỐC MÁI: {pct}% ({deg}°)")]


def _real(D, p):
    return ((p[0] - D.origin[0]) * D.scale, (p[1] - D.origin[1]) * D.scale)


def _horizontal(p):
    return abs(p.p1[1] - p.p2[1]) < 1e-9


def _vertical(p):
    return abs(p.p1[0] - p.p2[0]) < 1e-9


def _len(p):
    return math.hypot(p.p2[0] - p.p1[0], p.p2[1] - p.p1[1])


def _match_set(want, got, tol):
    """One-to-one: every wanted number has a distinct got number within tol and nothing is left over. Returns (ok, missing, extra)."""
    got = list(got)
    miss = []
    for w in want:
        for k, g in enumerate(got):
            if abs(g - w) <= tol:
                del got[k]
                break
        else:
            miss.append(w)
    return not miss and not got, miss, got


def purlin_findings(lines, X, dai, tol):
    """lines = [((x1, y1), (x2, y2))] in real mm. -> (ok, detail): one horizontal line per distinct plan position, each from x = 0 to x = dai."""
    ys, bad = [], []
    for a, b in lines:
        if abs(a[1] - b[1]) > tol or abs(min(a[0], b[0])) > tol or abs(max(a[0], b[0]) - dai) > tol:
            bad.append((round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)))
        ys.append((a[1] + b[1]) / 2)
    ok, miss, extra = _match_set([float(y) for y in X["ys"]], ys, tol)
    return ok and not bad, f"{len(lines)} đường; mong đợi {len(X['ys'])} (n = {X['n']}, {X['m']} mái); thiếu {[round(m, 3) for m in miss[:3]]}; thừa/trùng {[round(e, 3) for e in extra[:3]]}; sai đầu mút {bad[:2]}"


# ------------------------------------------------------------------ 1. primitives
def check_primitives_d(C: Checks, D, sp):
    X = expect_values(sp)
    s, P = D.scale, D.info["params"]
    n, N, dai, buoc, nhip = X["n"], X["N"], X["dai"], X["buoc"], float(X["nhip"])
    b, h = X["b"], X["h"]
    ov, gp, dia = P["truc_vuon_qua"], P["khe_vong_truc"], P["duong_kinh_vong_truc"]
    pur = [p for p in D.prims if p.layer == PURLIN_LAYER]
    tagged = D.by_tag("purlin")
    lines = [(_real(D, p.p1), _real(D, p.p2)) for p in pur if isinstance(p, Line)]
    ok, det = purlin_findings(lines, X, dai, TOL)
    ok = ok and len(pur) == len(lines) == len(tagged) and all(p.layer == PURLIN_LAYER and isinstance(p, Line) for p in tagged)
    C.add(1, "1.34", f"xà gồ: một đường lớp {PURLIN_LAYER} tại mỗi vị trí chiếu k × (nhịp/2 hoặc nhịp)/n (2 mái đối xứng, xà gồ nóc trùng nhau chỉ vẽ một đường), chạy suốt dai_nha (x = 0..dai_nha), không trùng lặp, không đường xà gồ ở lớp khác", ok, det)

    ys = sorted(round((a[1] + b_[1]) / 2, 9) for a, b_ in lines)
    gaps = [ys[k + 1] - ys[k] for k in range(len(ys) - 1)]
    per_roof = sum(1 for y in ys if y <= float(X["half"]) + TOL) if X["m"] == 2 else len(ys)
    ridge_once = X["m"] == 1 or sum(1 for y in ys if abs(y - float(X["half"])) < TOL) == 1
    cos_t = 1.0 / math.sqrt(1.0 + float(X["i"]) ** 2)
    real_d = X["L"] / n
    ok35 = (sp["n"] == n and all(close(g, float(X["p"]), TOL) for g in gaps) and per_roof == n + 1 and ridge_once and close(real_d * cos_t, float(X["p"]), 1e-6)
            and real_d <= float(_fr(sp["buoc_xa_go"])) + 1e-9 and (n == 1 or X["L"] / (n - 1) > float(_fr(sp["buoc_xa_go"]))) and close(ys[0], 0.0, TOL) and close(ys[-1], nhip, TOL))
    C.add(1, "1.35", "số khoảng n = ceil(L/buoc_xa_go) nhỏ nhất (L = nửa nhịp hoặc nhịp × √(1 + i²)), khoảng thực L/n ≤ buoc_xa_go, khoảng chiếu = L/n × cosθ = đều nhau giữa các xà gồ, mỗi mái n + 1 xà gồ",
          ok35, f"spec n = {sp['n']}, tính lại n = {n}; L = {X['L']:.3f} mm; khoảng thực {real_d:.4f} mm ≤ {sp['buoc_xa_go']:g}; chiếu {float(X['p']):.6f} mm; {len(gaps)} khoảng, lệch lớn nhất {max((abs(g - float(X['p'])) for g in gaps), default=0):.2e}; {per_roof} xà gồ/mái")

    # ---- grid + columns (own formulas, real mm)
    av, ah, cols = D.by_tag("axis_v"), D.by_tag("axis_h"), D.by_tag("column")
    ex_v, ex_h = nhip + h + 2 * ov * s, dai + b + 2 * ov * s
    xs = sorted(_real(D, a.p1)[0] for a in av)
    hs = sorted(_real(D, a.p1)[1] for a in ah)
    ok_av = all(_vertical(a) and close(_len(a) * s, ex_v, 1e-6 * ex_v) and a.layer == "TRUC" for a in av) and len(av) == N and _match_set([i * buoc for i in range(N)], xs, TOL)[0]
    ok_ah = all(_horizontal(a) and close(_len(a) * s, ex_h, 1e-6 * ex_h) and a.layer == "TRUC" for a in ah) and len(ah) == 2 and _match_set([0.0, nhip], hs, TOL)[0]
    ctr = [(((c.p0[0] + c.p1[0]) / 2 - D.origin[0]) * s, ((c.p0[1] + c.p1[1]) / 2 - D.origin[1]) * s) for c in cols]
    want_c = [(i * buoc, j * nhip) for i in range(N) for j in (0, 1)]
    ok_c = len(cols) == 2 * N and all(close((c.p1[0] - c.p0[0]) * s, b, 1e-6 * b) and close((c.p1[1] - c.p0[1]) * s, h, 1e-6 * h) and c.layer == "COT" for c in cols) and \
        all(any(close(w[0], g[0], 1e-3) and close(w[1], g[1], 1e-3) for g in ctr) for w in want_c)
    bub = D.by_tag("bubble")
    r_off = (ov + gp + dia / 2) * s
    want_b = [(i * buoc, nhip + h / 2 + r_off) for i in range(N)] + [(-b / 2 - r_off, 0.0), (-b / 2 - r_off, nhip)]
    got_b = [_real(D, c.c) for c in bub]
    ok_b = len(bub) == N + 2 and all(close(2 * c.r, dia, 1e-9) and c.layer == "TRUC-KYHIEU" for c in bub) and all(any(close(w[0], g[0], 1e-3) and close(w[1], g[1], 1e-3) for g in got_b) for w in want_b)
    labels = sorted(t.s for t in D.by_tag("bubble_text"))
    ok_l = labels == sorted([str(i + 1) for i in range(N)] + ["A", "B"])
    C.add(1, "1.36", "lưới trục + cột (dùng lại loại B): N = dai_nha/buoc_cot + 1 trục dọc, trục A/B, 2N cột b × h tại giao điểm, N + 2 vòng ký hiệu Ø đúng tâm, chữ 1..N, A, B", ok_av and ok_ah and ok_c and ok_b and ok_l,
          f"trục dọc {len(av)}/{N} ({ok_av}), trục ngang {len(ah)}/2 ({ok_ah}), cột {len(cols)}/{2 * N} ({ok_c}), vòng {len(bub)}/{N + 2} ({ok_b}), chữ {ok_l}")

    # ---- dimensions
    def dl(tag):
        return [p for p in D.prims if p.tag == tag and isinstance(p, Line)]

    def dt(tag):
        return [p for p in D.prims if p.tag == tag and isinstance(p, Text)]

    vch = [p for p in dl("dim_chain_line") if _vertical(p)]
    hch = [p for p in dl("dim_chain_line") if _horizontal(p)]
    vov = [p for p in dl("dim_overall_line") if _vertical(p)]
    hov = [p for p in dl("dim_overall_line") if _horizontal(p)]
    hsingle = dl("dim_single_line")
    half = float(X["half"])
    seg = sorted(((min(_real(D, p.p1)[1], _real(D, p.p2)[1]), max(_real(D, p.p1)[1], _real(D, p.p2)[1])) for p in vch))
    chain_ok = len(vch) == n and len({round(p.p1[0], 6) for p in vch}) == 1 and all(close(b_ - a_, float(X["p"]), TOL) for a_, b_ in seg) and close(seg[0][0], 0.0, TOL) and close(seg[-1][1], half, TOL) and \
        all(close(seg[k][1], seg[k + 1][0], TOL) for k in range(len(seg) - 1)) if vch else False
    span_ok = len(vov) == 1 and close(_len(vov[0]) * s, nhip, 1e-6) and close(min(_real(D, vov[0].p1)[1], _real(D, vov[0].p2)[1]), 0.0, TOL)
    labs_v = dt("dim_chain_text")
    txt_ok = sorted(t.s for t in labs_v if t.rot == 90.0) == [X["label"]] * n and [t.s for t in dt("dim_overall_text") if t.rot == 90.0] == [f"{round(nhip):d}"]
    if N == 2:
        bot_ok = len(hsingle) == 1 and close(_len(hsingle[0]) * s, dai, 1e-6) and sorted(t.s for t in dt("dim_single_text")) == [str(dai)] and not hch and not hov
    else:
        bot_ok = len(hch) == N - 1 and all(close(_len(p) * s, buoc, 1e-6) for p in hch) and len(hov) == 1 and close(_len(hov[0]) * s, dai, 1e-6) and \
            sorted(t.s for t in dt("dim_chain_text") if t.rot == 0.0) == [str(buoc)] * (N - 1) and [t.s for t in dt("dim_overall_text") if t.rot == 0.0] == [str(dai)]
    ticks = [p for p in D.prims if p.tag.startswith("dim_") and p.tag.endswith("_tick")]
    n_dims = n + 1 + (1 if N == 2 else N)
    ticks_ok = len(ticks) == 2 * n_dims and all(close(abs(p.p2[0] - p.p1[0]), P["kt_mui_ten"], 1e-9) and close(abs(p.p2[1] - p.p1[1]), P["kt_mui_ten"], 1e-9) for p in ticks)
    axes_end = max(a.p2[0] for a in ah)
    exo, exe = P["kt_exo"], P["kt_exe"]
    pos_ok = bool(vch) and bool(vov) and close(vch[0].p1[0], axes_end + P["kt_dau_tien"], 1e-6) and close(vov[0].p1[0], axes_end + P["kt_dau_tien"] + P["kt_giua_cac_duong"], 1e-6)
    ext_c = sorted(round((_real(D, p.p1)[1]), 6) for p in dl("dim_chain_ext") if _horizontal(p) and p.p1[0] > axes_end)
    ext_ok = bool(vch) and _match_set([float(half * k / n) for k in range(n + 1)], ext_c, 1e-5)[0] and all(
        close(p.p1[0], axes_end + exo, 1e-6) and close(p.p2[0], vch[0].p1[0] + exe, 1e-6) for p in dl("dim_chain_ext") if _horizontal(p) and p.p1[0] > axes_end)
    cust = dl("dim_ext_custom")
    top_from = (vch[0].p1[0] + exe) if X["m"] == 1 and vch else axes_end + exo
    cust_ok = bool(vov) and len(cust) == 2 and all(p.layer == "KICH-THUOC" and _horizontal(p) and close(p.p2[0], vov[0].p1[0] + exe, 1e-6) for p in cust) and \
        _match_set([0.0, nhip], [_real(D, p.p1)[1] for p in cust], TOL)[0] and any(close(p.p1[0], top_from, 1e-6) and close(_real(D, p.p1)[1], nhip, TOL) for p in cust) and \
        any(close(p.p1[0], vch[0].p1[0] + exe, 1e-6) and close(_real(D, p.p1)[1], 0.0, TOL) for p in cust)
    layers_ok = all(p.layer == "KICH-THUOC" for p in D.prims if p.tag.startswith("dim_"))
    want_v = sorted([float(X["p"])] * n + [nhip])
    want_h = [float(dai)] if N == 2 else sorted([float(buoc)] * (N - 1) + [float(dai)])
    dims_ok = sorted(d.value for d in D.dims if d.kind == "v") == want_v and sorted(d.value for d in D.dims if d.kind == "h") == want_h
    C.add(1, "1.37", f"kích thước: {n} đoạn chuỗi xà gồ (mỗi đoạn = nhịp/2 hoặc nhịp chia n, liên tục từ trục A tới tim nóc/trục B, tổng = nhịp/2 hoặc nhịp, nhãn làm tròn nửa lên), kích thước nhịp, chuỗi dọc nhà; vị trí, mũi tên, đường gióng, lớp KICH-THUOC",
          chain_ok and span_ok and txt_ok and bot_ok and ticks_ok and pos_ok and ext_ok and cust_ok and layers_ok and dims_ok,
          f"chuỗi {len(vch)}/{n} ({chain_ok}) tổng {sum(b_ - a_ for a_, b_ in seg):.6f} / {half:g}; nhịp {span_ok}; nhãn {txt_ok} ({X['label']!r}); dọc nhà {bot_ok}; mũi tên {len(ticks)}/{2 * n_dims}; vị trí {pos_ok}; đường gióng {ext_ok}; gióng tay {cust_ok}; lớp {layers_ok}; giá trị trong D.dims {dims_ok}")

    # ---- notes, ridge label
    exp_n = expect_notes(sp, X)
    got_n = {tag: [t for t in D.prims if isinstance(t, Text) and t.tag == tag] for tag, _ in exp_n}
    xc = (min(_real(D, c.p0)[0] for c in cols) + max(_real(D, c.p1)[0] for c in cols)) / 2
    notes_ok = True
    for tag, txt in exp_n:
        g = got_n[tag]
        notes_ok &= len(g) == 1 and g[0].s == txt and g[0].layer == "CHU" and close(g[0].h, P["cao_chu_ghi_chu"], 1e-9) and g[0].halign == "center" and close(_real(D, g[0].pos)[0], xc, 1e-3)
    order = [got_n[tag][0].pos[1] for tag, _ in exp_n if got_n[tag]]
    title_t, scale_t = D.by_tag("title"), D.by_tag("scale_note")
    stack = ([scale_t[0].pos[1]] if scale_t else []) + order
    notes_ok &= len(order) == len(exp_n) and all(stack[k] - stack[k + 1] >= P["cao_chu_ghi_chu"] + 1.0 for k in range(len(stack) - 1))
    ridge = D.by_tag("ridge_label")
    ry = _real(D, ridge[0].pos)[1] if ridge else None
    ridge_ok = (not ridge) if X["m"] == 1 else (len(ridge) == 1 and ridge[0].s == RIDGE and ridge[0].layer == "CHU" and close(ry, half + 1.2 * s, 1e-3))
    C.add(1, "1.38", "ghi chú: tiết diện xà gồ (+ 'MẶC ĐỊNH' khi không do người dùng nhập), số lượng, khoảng cách thực theo mặt dốc, khoảng cách chiếu, độ dốc; 'TIM NÓC' chỉ khi 2 mái; đúng chuỗi, đúng lớp CHU, căn giữa, không đè nhau",
          notes_ok and ridge_ok, f"ghi chú {[(t, len(got_n[t])) for t, _ in exp_n]} đúng chuỗi {notes_ok}; nhãn tim nóc {ridge_ok}; mong đợi {[x for _, x in exp_n]}")

    # ---- title, scale, title block
    kt = sp["khung_ten"]
    want4 = kt.get("ky_hieu_ban_ve") or DEFAULT_NO
    fields_ok = D.fields.get("cell4") == want4 and D.fields.get("cell7") == f"1:{s}" and "".join(D.fields.get(k, "") for k in ("cell3_l1", "cell3_l2")).replace(" ", "") == (kt.get("ten_ban_ve") or TITLE).replace(" ", "")
    ts_ok = len(title_t) == 1 and title_t[0].s == TITLE and len(scale_t) == 1 and scale_t[0].s == f"TỶ LỆ 1:{s}" and title_t[0].bold
    C.add(1, "1.39", "tên hình 'MẶT BẰNG XÀ GỒ MÁI', ghi chú tỷ lệ 1:N, khung tên: ô 4 = KC-04 (mặc định), ô 3 = tên bản vẽ, ô 7 = tỷ lệ", ts_ok and fields_ok,
          f"tiêu đề {[t.s for t in title_t]}; tỷ lệ {[t.s for t in scale_t]}; ô 4 {D.fields.get('cell4')!r} (cần {want4!r}); ô 7 {D.fields.get('cell7')!r}")

    # ---- layout
    sh = SHEETS[D.sheet]
    inside, tb_clear, rot_ok = True, True, True
    for p in D.prims:
        if p.sheet:
            continue
        bb = prim_bbox(p)
        inside &= bb[0] >= sh.x0 + MARGIN - 1e-6 and bb[2] <= sh.x1 - MARGIN + 1e-6 and bb[1] >= sh.y0 + MARGIN - 1e-6 and bb[3] <= sh.y1 - MARGIN + 1e-6
        tb_clear &= bb[2] <= sh.tb_x0 - MARGIN + 1e-6 or bb[1] >= sh.tb_y1 + MARGIN - 1e-6
        if isinstance(p, Text):
            rot_ok &= p.rot in (0.0, 90.0)
    fit_w = [(_len(p), est_width(X["label"], cap_to_em(P["cao_chu_kich_thuoc"])) + 3.0) for p in vch]
    labels_ok = bool(fit_w) and all(a >= w - 1e-6 for a, w in fit_w)
    C.add(1, "1.40", "bố cục: mọi nét/chữ trong khung (cách mép ≥ 5 mm) và cách khung tên 180×65 ≥ 5 mm, chữ chỉ nằm ngang/đứng, nhãn khoảng cách xà gồ nằm gọn giữa hai mũi tên (chữ + 2 × 1,25 + 0,5 mm)",
          inside and tb_clear and rot_ok and labels_ok,
          f"trong khung {inside}; cách khung tên {tb_clear}; xoay {rot_ok}; nhãn '{X['label']}' cần {fit_w[0][1] if fit_w else 0:.1f} mm, có {min((a for a, _ in fit_w), default=0):.1f} mm")
    check_policy(C, D, sp, X)

    # ---- soft warning + report
    warn = [w for w in D.info.get("warnings", []) if "800-2000" in w]
    soft = not (SOFT_MIN <= int(sp["buoc_xa_go"]) <= SOFT_MAX)
    w_ok = (len(warn) == 1 and "TCVN" in warn[0] and f"{int(sp['buoc_xa_go'])} mm" in warn[0]) if soft else not warn
    nonint = [w for w in D.info.get("warnings", []) if "không nguyên" in w]
    w2_ok = (len(nonint) == 1 and f"{_hu(X['p'])} mm" in nonint[0]) if X["p"].denominator != 1 else not nonint
    infos_ok = D.info.get("n_spans") == n and D.info.get("n_purlins") == X["m"] * (n + 1)
    C.add(1, "1.41", f"cảnh báo mềm: buoc_xa_go ngoài {SOFT_MIN}-{SOFT_MAX} mm (kinh nghiệm thực tế, không phải điều khoản TCVN) và khoảng chiếu không nguyên mm có trong báo cáo; trong khoảng / nguyên thì không có; báo cáo ghi đúng n và số xà gồ",
          w_ok and w2_ok and infos_ok, f"buoc_xa_go = {int(sp['buoc_xa_go'])}: cần cảnh báo {soft}, có {len(warn)}; chiếu không nguyên {X['p'].denominator != 1}: có {len(nonint)}; n = {D.info.get('n_spans')}, số xà gồ = {D.info.get('n_purlins')}")
    check_expressions(C, [p.s for p in D.prims if isinstance(p, Text)], 1, "1.42", "chữ trên bản vẽ")
    defaults_ok = ("tiet_dien_xa_go" in D.info.get("defaults", [])) == bool(sp["xa_go_mac_dinh"]) and ("tiet_dien_cot" in D.info.get("defaults", [])) == bool(sp["cot_mac_dinh"])
    C.add(1, "1.43", "giá trị mặc định (tiet_dien_cot H250x125x6x9, tiet_dien_xa_go C150x50x20x2.0) được ghi nhận trong báo cáo đúng với spec; tiết diện xà gồ mặc định có chữ MẶC ĐỊNH trên bản vẽ", defaults_ok and any(
        t.s.endswith("(MẶC ĐỊNH)") for t in D.by_tag("note_purlin")) == bool(sp["xa_go_mac_dinh"]), f"mặc định ghi nhận: {D.info.get('defaults')}")


def check_policy(C: Checks, D, sp, X):
    """1.40b: sheet + scale. Measured: the drawing fits the chosen pair. Inferred (reuses build_d.layout for the extents): the pairs tried earlier do not fit
    (A3 first, A2 then A1 only when A3 does not hold the drawing at 1:200 or finer; labels must fit between the ticks)."""
    import build_d
    from scale import place_rects, sheet_scale_candidates
    P = D.info["params"]
    kho = sp["kho_giay"]
    cands = sheet_scale_candidates(sp["scale"], None if kho == "auto" else kho, limit=SCALE_LIMIT)
    need = est_width(X["label"], cap_to_em(P["cao_chu_kich_thuoc"])) + 3.0
    why, found = [], False
    for sh_, sc in cands:
        if (sh_, sc) == (D.sheet, D.scale):
            found = True
            break
        if float(X["p"]) / sc < need:
            continue
        prims, dims, _ = build_d.layout(sp, sc)
        bb = build_d._extent(prims, dims, P)
        if place_rects([bb], P["khe_vung_ve"], SHEETS[sh_]) is not None:
            why.append(f"{sh_} 1:{sc} vẫn vừa")
    C.add(1, "1.44", "khổ giấy + tỷ lệ theo quy tắc: ưu tiên A3, lên A2 rồi A1 chỉ khi khổ nhỏ hơn không vừa ở tỷ lệ ≤ 1:200; tỷ lệ lớn nhất còn vừa; khớp ty_le/kho_giay do người dùng chọn; đo: bản vẽ vừa cặp đã chọn, suy luận: các cặp đứng trước không vừa (dùng lại hàm bố cục)",
          found and not why and (not sp["scale"] or D.scale == sp["scale"]) and (kho == "auto" or D.sheet == kho), f"chọn {D.sheet} 1:{D.scale}; cặp đứng trước vẫn vừa: {why[:3]}; có trong danh sách {found}")


# ------------------------------------------------------------------ 2/3. DXF (and the DWG read back)
def _dxf_lines(dx, layer):
    out = []
    for e in dx["ents"]:
        if e["type"] == "LINE" and e["layer"] == layer:
            r = e["rec"]
            out.append(((f(r, 10), f(r, 20)), (f(r, 11), f(r, 21))))
    return out


def dxf_purlin_dims(dx, sp, X):
    """-> (ok_purlins, detail_purlins, ok_dims, detail_dims) measured on a DXF (or the DXF of a DWG round trip); real mm, nothing taken from the Drawing object."""
    pl = _dxf_lines(dx, PURLIN_LAYER)
    other = [e for e in dx["ents"] if e["layer"] == PURLIN_LAYER and e["type"] != "LINE"]
    ok_p, det_p = purlin_findings(pl, X, X["dai"], TOL_DXF)
    ok_p = ok_p and not other
    dim = _dxf_lines(dx, "KICH-THUOC")
    vert = [(a, b) for a, b in dim if abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) > 1e-6 and a[0] > X["dai"] + X["b"] / 2]       # right of the building: chain + span (the lines left of it are extension lines of the bottom dimensions)
    cols_x = sorted({round(a[0], 3) for a, b in vert})
    seg = lambda x: sorted((min(a[1], b[1]), max(a[1], b[1])) for a, b in vert if abs(a[0] - x) < 1e-3)
    n, half, nhip = X["n"], float(X["half"]), float(X["nhip"])
    ok_d = len(cols_x) == 2
    det_d = f"đường đứng ở x = {cols_x}"
    if ok_d:
        chain, span = seg(cols_x[0]), seg(cols_x[1])
        ok_d = len(chain) == n and all(abs(b - a - float(X["p"])) <= TOL_DXF for a, b in chain) and abs(chain[0][0]) <= TOL_DXF and abs(chain[-1][1] - half) <= TOL_DXF and \
            all(abs(chain[k][1] - chain[k + 1][0]) <= TOL_DXF for k in range(n - 1)) and len(span) == 1 and abs(span[0][0]) <= TOL_DXF and abs(span[0][1] - nhip) <= TOL_DXF
        det_d = f"chuỗi {len(chain)}/{n} đoạn, tổng {sum(b - a for a, b in chain):.4f} / {half:g}; nhịp {span}"
    hor = [(a, b) for a, b in dim if abs(a[1] - b[1]) < 1e-6 and abs(a[0] - b[0]) > 1e-6]
    right = [a[1] for a, b in hor if min(a[0], b[0]) > X["dai"] + X["b"] / 2]            # extension lines of the chain (n + 1) and of the span (2)
    ok_e = _match_set([half * k / n for k in range(n + 1)] + [0.0, nhip], right, TOL_DXF)[0]
    bottom = [abs(b[0] - a[0]) for a, b in hor if a[1] < -1.0]                           # dimension lines of the building length
    ok_bot = _match_set([float(X["dai"])] if X["N"] == 2 else [float(X["buoc"])] * (X["N"] - 1) + [float(X["dai"])], bottom, TOL_DXF)[0]
    ok_d = ok_d and ok_e and ok_bot
    det_d += f"; đường gióng bên phải {ok_e}; đường kích thước dọc nhà {ok_bot}"
    texts = collections.Counter(t for lay, t in dx["texts"] if lay == "KICH-THUOC")
    want = collections.Counter([X["label"]] * n + [str(int(nhip))] + ([str(X["dai"])] if X["N"] == 2 else [str(X["buoc"])] * (X["N"] - 1) + [str(X["dai"])]))
    return ok_p, det_p, ok_d and texts == want, det_d + f"; chữ kích thước {dict(texts) == dict(want)}"


def _plan_texts(D, dx):
    """Texts of layer CHU that stand outside the title block (the title-block texts are on layer CHU as well); the position comes from the DXF entity (code 10/11, 20/21)."""
    sh, s, (ox, oy) = SHEETS[D.sheet], D.scale, D.origin
    out = []
    for e in dx["ents"]:
        if e["type"] != "TEXT" or e["layer"] != "CHU":
            continue
        r = e["rec"]
        px, py = ((f(r, 11), f(r, 21)) if 11 in r else (f(r, 10), f(r, 20)))
        if sh.tb_x0 <= px / s + ox <= sh.tb_x1 and sh.tb_y0 <= py / s + oy <= sh.tb_y1:
            continue
        out.append(unesc("".join(r.get(3, [])) + (r.get(1) or [""])[0]))
    return out


def check_dxf_d(C: Checks, D, sp, dx):
    X = expect_values(sp)
    ok_p, det_p, ok_d, det_d = dxf_purlin_dims(dx, sp, X)
    C.add(2, "2.22", f"DXF (mm thật, gốc ở giao trục 1/A): xà gồ lớp {PURLIN_LAYER} đúng số lượng, vị trí k × (nhịp/2 hoặc nhịp)/n, đầu mút x = 0..dai_nha, không trùng lặp, không thực thể khác trên lớp", ok_p, det_p)
    C.add(2, "2.23", "DXF: chuỗi kích thước xà gồ (n đoạn liên tục từ 0 tới nhịp/2 hoặc nhịp, mỗi đoạn = nhịp/2 hoặc nhịp chia n) và kích thước nhịp, đọc từ đường LINE; chữ kích thước đúng", ok_d, det_d)
    exp_n = expect_notes(sp, X)
    want = collections.Counter([t for _, t in exp_n] + [sp["section"]["text"], TITLE, f"TỶ LỆ 1:{D.scale}"] + ([RIDGE] if X["m"] == 2 else []))
    got = collections.Counter(_plan_texts(D, dx))
    C.add(2, "2.24", "DXF: chữ lớp CHU (nhãn tiết diện cột, tên hình, tỷ lệ, 5 ghi chú tiết diện/số lượng/khoảng cách, TIM NÓC khi 2 mái) khớp chính xác với spec; chữ MẶC ĐỊNH đúng", want == got,
          f"{sum(got.values())} chuỗi; thiếu {list((want - got).elements())[:2]}; thừa {list((got - want).elements())[:2]}")
    N, buoc, nhip, b, h = X["N"], X["buoc"], float(X["nhip"]), X["b"], X["h"]
    axis = _dxf_lines(dx, "TRUC")
    vx = [a[0] for a, c in axis if abs(a[0] - c[0]) < 1e-6]
    hy = [a[1] for a, c in axis if abs(a[1] - c[1]) < 1e-6]
    P = D.info["params"]
    ov = P["truc_vuon_qua"] * D.scale
    len_ok = all(abs(abs(c[1] - a[1]) - (nhip + h + 2 * ov)) <= TOL_DXF for a, c in axis if abs(a[0] - c[0]) < 1e-6) and all(abs(abs(c[0] - a[0]) - (X["dai"] + b + 2 * ov)) <= TOL_DXF for a, c in axis if abs(a[1] - c[1]) < 1e-6)
    cols = [e for e in dx["ents"] if e["type"] == "LWPOLYLINE" and e["layer"] == "COT"]
    sizes = collections.Counter((round(max(float(v) for v in e["rec"][10]) - min(float(v) for v in e["rec"][10]), 3), round(max(float(v) for v in e["rec"][20]) - min(float(v) for v in e["rec"][20]), 3)) for e in cols)
    ctr = [((min(float(v) for v in e["rec"][10]) + max(float(v) for v in e["rec"][10])) / 2, (min(float(v) for v in e["rec"][20]) + max(float(v) for v in e["rec"][20])) / 2) for e in cols]
    ctr_ok = len(ctr) == 2 * N and all(any(abs(i * buoc - g[0]) <= TOL_DXF and abs(j * nhip - g[1]) <= TOL_DXF for g in ctr) for i in range(N) for j in (0, 1))
    bub = collections.Counter(t for lay, t in dx["texts"] if lay == "TRUC-KYHIEU")
    bub_ok = bub == collections.Counter([str(i + 1) for i in range(N)] + ["A", "B"])
    C.add(2, "2.25", "DXF: trục dọc tại x = i × buoc_cot, 2 trục ngang tại y = 0 và nhịp, độ dài trục, 2N cột b × h tại giao điểm (mm thật), chữ ký hiệu trục 1..N, A, B",
          _match_set([float(i * buoc) for i in range(N)], vx, TOL_DXF)[0] and _match_set([0.0, nhip], hy, TOL_DXF)[0] and len_ok and dict(sizes) == {(round(b, 3), round(h, 3)): 2 * N} and ctr_ok and bub_ok,
          f"x trục dọc {sorted(round(v, 3) for v in vx)[:3]}…; y trục ngang {sorted(round(v, 3) for v in hy)}; độ dài {len_ok}; cột {dict(sizes)} đúng tâm {ctr_ok}; chữ trục {bub_ok}")


def check_dwg_d(C: Checks, D, sp, bx):
    ok_p, det_p, ok_d, det_d = dxf_purlin_dims(bx, sp, expect_values(sp))
    C.add(3, "3.9", "DWG đọc lại sau khứ hồi: xà gồ (lớp XA-GO) và chuỗi kích thước xà gồ vẫn đúng vị trí/số lượng (mm thật, ±0,001)", ok_p and ok_d, f"xà gồ: {det_p}; kích thước: {det_d}")


# ------------------------------------------------------------------ 5. PDF
def check_pdf_d(C: Checks, D, sp, dx, paths, profile):
    """5.8: every XA-GO LINE of the DXF has a thin continuous horizontal stroke in the PDF at the paper position derived from the DXF coordinates (±0.06 mm)."""
    s, (ox, oy) = D.scale, D.origin
    top = lambda y: SHEETS[D.sheet].h - y
    want = [((a[0] / s + ox, a[1] / s + oy), (c[0] / s + ox, c[1] / s + oy)) for a, c in _dxf_lines(dx, PURLIN_LAYER)]
    lw = profile[PURLIN_LAYER]["lw"] / 100.0
    strokes = [p for p in paths if p["kind"] == "stroke" and p["n"] == 2 and not p["curve"] and not p["dash"] and close(p["lw"], lw, 0.03)]
    used, bad = set(), []
    for a, c in want:
        bb = (min(a[0], c[0]), top(max(a[1], c[1])), max(a[0], c[0]), top(min(a[1], c[1])))
        for k, p in enumerate(strokes):
            if k not in used and all(close(x, y, TOL_PDF) for x, y in zip(p["bb"], bb)):
                used.add(k)
                break
        else:
            bad.append(tuple(round(x, 2) for x in bb))
    C.add(5, "5.8", f"PDF: mỗi đường xà gồ của DXF có nét mảnh {lw:g} mm liền (không đứt) ở đúng vị trí ±0,06 mm, đúng chiều dài dai_nha/tỷ lệ", bool(want) and not bad and len(want) == len(D.by_tag("purlin")),
          f"{len(want) - len(bad)}/{len(want)} đường xà gồ DXF có nét PDF; không thấy {bad[:3]}")
