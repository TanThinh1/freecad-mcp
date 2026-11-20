"""Verification of the electrical / plumbing group of type E (own code and own copy of the symbol table, independent of elems3.py): expected symbols, wires, pipes, junction dots and
legend rows (families kyhieu, ong, legend -> checks 1.73, 1.74, 1.76 through verify_e's two-way comparison) plus measured rules: every end of a wire / pipe equals a declared node (1.75)
and the legend lists exactly the used symbols / pipe types in the fixed order (1.77). New ids: 1.73-1.77.
This checks GEOMETRY and LAYOUT only: it does NOT check that an electrical / plumbing design follows any code.
"""
from __future__ import annotations

import math

from primitives import Line, Text

TABLE = {   # kind -> (name, [(shape, numbers...)]) in paper mm around the node (0, 0)
    "o_cam": ("Ổ CẮM", [("c", 0, 0, 2.0), ("l", -2.0, 0, 2.0, 0)]),
    "cong_tac": ("CÔNG TẮC", [("c", 0, 0, 1.2), ("l", 0.85, 0.85, 3.5, 3.5)]),
    "den": ("ĐÈN", [("c", 0, 0, 2.5), ("l", -1.77, -1.77, 1.77, 1.77), ("l", -1.77, 1.77, 1.77, -1.77)]),
    "quat": ("QUẠT", [("c", 0, 0, 3.0), ("l", -3.0, 0, 3.0, 0), ("l", 0, -3.0, 0, 3.0)]),
    "bang_dien": ("BẢNG ĐIỆN", [("r", -3.0, -2.0, 3.0, 2.0), ("l", -3.0, -2.0, 3.0, 2.0)]),
    "bon_cau": ("BỒN CẦU", [("r", -2.2, -3.6, 2.2, -2.0), ("r", -1.8, -2.0, 1.8, 3.0)]),
    "chau_rua": ("CHẬU RỬA", [("r", -3.5, -2.5, 3.5, 2.5), ("c", 0, 0, 1.2)]),
    "voi": ("VÒI", [("c", 0, 0, 1.0), ("l", 0, 1.0, 0, 2.5), ("l", -1.2, 2.5, 1.2, 2.5)]),
    "van": ("VAN", [("l", -2.0, -1.5, 2.0, 1.5), ("l", -2.0, 1.5, 2.0, -1.5), ("l", -2.0, -1.5, -2.0, 1.5), ("l", 2.0, -1.5, 2.0, 1.5)]),
    "dong_ho_nuoc": ("ĐỒNG HỒ NƯỚC", [("c", 0, 0, 2.5), ("l", -2.5, 0, 2.5, 0)]),
}
PIPE = {"day_dien": ("DÂY ĐIỆN", "NET-TAM"), "ong_cap": ("ỐNG CẤP NƯỚC", "NET-CHINH"), "ong_thoat": ("ỐNG THOÁT NƯỚC", "NET-KHUAT")}


def F(x):
    return float(x)


def turn(x, y, quarter):
    for _ in range(quarter % 4):
        x, y = -y, x
    return x, y


def symbol_shapes(kind, xoay, cx, cy, s, fam):
    """shapes (family, layer, kind, data) in real mm for one symbol of the table at (cx, cy) real mm; the paper numbers are multiplied by the scale."""
    q = xoay // 90
    out = []
    for p in TABLE[kind][1]:
        if p[0] == "c":
            x, y = turn(p[1], p[2], q)
            out.append((fam, "NET-MANH", "circ", ((cx + x * s, cy + y * s), p[3] * s)))
        elif p[0] == "l":
            a, b = turn(p[1], p[2], q), turn(p[3], p[4], q)
            out.append((fam, "NET-MANH", "seg", ((cx + a[0] * s, cy + a[1] * s), (cx + b[0] * s, cy + b[1] * s))))
        else:
            a, b = turn(p[1], p[2], q), turn(p[3], p[4], q)
            out.append((fam, "NET-MANH", "rect", (cx + min(a[0], b[0]) * s, cy + min(a[1], b[1]) * s, cx + max(a[0], b[0]) * s, cy + max(a[1], b[1]) * s)))
    return out


def legend_rows(view):
    ks = {e["kieu"] for e in view["elems"] if e["t"] == "ky_hieu"}
    ps = {e["loai_ong"] for e in view["elems"] if e["t"] == "ong"}
    return [("sym", k, TABLE[k][0]) for k in TABLE if k in ks] + [("pipe", k, PIPE[k][0]) for k in PIPE if k in ps]


def add_expected(view, s, P, sh, tx):
    for e in view["elems"]:
        t = e["t"]
        cx, cy = (F(e["vi_tri"][0]), F(e["vi_tri"][1])) if t in ("ky_hieu", "nut", "chu_giai") else (0.0, 0.0)
        if t == "ky_hieu":
            sh.extend(symbol_shapes(e["kieu"], e["xoay"], cx, cy, s, "kyhieu"))
        elif t == "nut":
            sh.append(("ong", "NET-MANH", "circ", ((cx, cy), 0.6 * s)))
        elif t == "ong":
            for a, b in zip(e["diem"], e["diem"][1:]):
                sh.append(("ong", PIPE[e["loai_ong"]][1], "seg", ((F(a[0]), F(a[1])), (F(b[0]), F(b[1])))))
        elif t == "chu_giai":
            tx.append(("CHU", "CHÚ GIẢI"))
            for k, (typ, kind, name) in enumerate(legend_rows(view)):
                y = cy - (10.0 + 7.0 * k) * s
                if typ == "sym":
                    sh.extend(symbol_shapes(kind, 0, cx + 10.5 * s, y, s, "legend"))
                else:
                    sh.append(("legend", PIPE[kind][1], "seg", ((cx + 0.5 * s, y), (cx + 20.5 * s, y))))
                tx.append(("CHU", name))


def check_phase3(C, D, sp, tol=1e-6):
    view = sp["views"][0]
    s, (ox, oy) = D.scale, D.origin
    R = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    nodes = [(F(e["vi_tri"][0]), F(e["vi_tri"][1])) for e in view["elems"] if e["t"] in ("ky_hieu", "nut")]
    bad, n = [], 0
    for e in (q for q in view["elems"] if q["t"] == "ong"):
        lines = [p for p in D.prims if isinstance(p, Line) and p.tag == f"ong:{e['id']}"]
        if not lines:
            bad.append(f"{e['id']}: không có nét")
            continue
        for end in (R(lines[0].p1), R(lines[-1].p2)):
            n += 1
            if not any(abs(end[0] - x) <= tol and abs(end[1] - y) <= tol for x, y in nodes):
                bad.append(f"{e['id']}: đầu mút ({end[0]:.3f}, {end[1]:.3f}) lơ lửng")
        for a, b in zip(lines, lines[1:]):
            if abs(a.p2[0] - b.p1[0]) > tol / s or abs(a.p2[1] - b.p1[1]) > tol / s:
                bad.append(f"{e['id']}: đứt đoạn")
    C.add(1, "1.75", "đường dây / ống: mọi đầu mút (đo từ nét đã vẽ) trùng đúng vị trí của một thiết bị hoặc nút đã khai (±1e-6 mm thật), các đoạn nối liền nhau; không đầu mút lơ lửng", not bad, f"{n} đầu mút đã đo; sai: {bad[:3]}")
    # legend: rows = exactly the used symbols / pipe types, in the fixed order (top to bottom)
    want = [name for _, _, name in legend_rows(view)] if any(e["t"] == "chu_giai" for e in view["elems"]) else []
    drawn = sorted((p for p in D.prims if isinstance(p, Text) and p.tag.startswith("legend_text:")), key=lambda p: -p.pos[1])
    has_title = [p for p in D.prims if isinstance(p, Text) and p.tag.startswith("legend_title:")]
    C.add(1, "1.77", "chú giải tự sinh: đúng các ký hiệu và loại đường đã dùng, theo thứ tự cố định (ký hiệu điện, nước rồi loại đường), mỗi dòng một chữ, có tiêu đề CHÚ GIẢI khi có phần tử chu_giai",
          [p.s for p in drawn] == want and (len(has_title) == 1) == bool(any(e["t"] == "chu_giai" for e in view["elems"])), f"mong đợi {want}; có {[p.s for p in drawn]}; tiêu đề {len(has_title)}")


# ------------------------------------------------------------------ linetype of the legend samples (read from the DXF / DWG read-back, not from the spec)
LINETYPE_OF_PIPE = {"day_dien": "CENTER", "ong_cap": "CONTINUOUS", "ong_thoat": "HIDDEN"}


def _line_at(dx, a, b, tol=1e-3):
    for e in dx["ents"]:
        if e["type"] != "LINE":
            continue
        r = e["rec"]
        try:
            p, q = (float(r[10][0]), float(r[20][0])), (float(r[11][0]), float(r[21][0]))
        except (KeyError, ValueError, IndexError):
            continue
        for u, v in ((p, q), (q, p)):
            if abs(u[0] - a[0]) <= tol and abs(u[1] - a[1]) <= tol and abs(v[0] - b[0]) <= tol and abs(v[1] - b[1]) <= tol:
                return e
    return None


def _linetype(dx, e):
    own = (e["rec"].get(6) or [None])[0]
    name = own if own and own.upper() != "BYLAYER" else dx["layers"].get(e["layer"], {}).get("ltype", "?")
    return str(name).upper()


def check_legend_linetypes(C, D, sp, dx, group, cid, where):
    """Each pipe / wire row of the legend: its sample line has the SAME linetype as the real line of that type, both equal the expected linetype, and the sample is long enough to show one whole pattern."""
    view = sp["views"][0]
    s = D.scale
    leg = [e for e in view["elems"] if e["t"] == "chu_giai"]
    bad, n = [], 0
    for e in leg:
        cx, cy = F(e["vi_tri"][0]), F(e["vi_tri"][1])
        for k, (typ, kind, name) in enumerate(legend_rows(view)):
            if typ != "pipe":
                continue
            n += 1
            y = cy - (10.0 + 7.0 * k) * s
            sample = _line_at(dx, (cx + 0.5 * s, y), (cx + 20.5 * s, y))
            real = next((q for q in view["elems"] if q["t"] == "ong" and q["loai_ong"] == kind), None)
            real_line = _line_at(dx, (F(real["diem"][0][0]), F(real["diem"][0][1])), (F(real["diem"][1][0]), F(real["diem"][1][1]))) if real else None
            if sample is None or real_line is None:
                bad.append(f"{kind}: không thấy nét {'mẫu' if sample is None else 'thật'}")
                continue
            lt_s, lt_r = _linetype(dx, sample), _linetype(dx, real_line)
            if lt_s != lt_r or lt_s != LINETYPE_OF_PIPE[kind]:
                bad.append(f"{kind}: mẫu {lt_s}, đường thật {lt_r}, cần {LINETYPE_OF_PIPE[kind]}")
                continue
            pat = next((v for k2, v in dx["ltypes"].items() if k2.upper() == lt_s), [])
            period = sum(abs(x) for x in pat) * dx["ltscale"]
            if pat and 20.0 * s + 1e-6 < period:
                bad.append(f"{kind}: mẫu dài {20.0 * s:.0f} mm < một chu kỳ nét {period:.0f} mm (trông như nét liền)")
    C.add(group, cid, f"{where}: kiểu nét mẫu trong chú giải (dây điện, ống cấp, ống thoát) đúng bằng kiểu nét đường thật cùng loại (đọc từ thực thể và bảng lớp, không từ spec) và mẫu đủ dài để hiện trọn một chu kỳ nét", not bad, f"{n} dòng loại đường; sai: {bad[:3]}")
