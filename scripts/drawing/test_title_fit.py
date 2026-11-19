"""Title-block text fitting tests (no FreeCAD / no PDF needed): every text printed in a title-block cell must shrink to fit its cell by the worst-case estimate
(every character 1 em wide): width factor down to 0.7, then em size down to 2 mm, then two lines when the cell has room, else a Vietnamese error.

    python scripts/drawing/test_title_fit.py       (needs TCVN_PROFILE)
Covers: the 4-word names, 40-character strings, the default sample names (content unchanged), a property sweep over every field, DXF code 41, the PDF template
taking the same size / width factor as the primitives, and mutants that 1.31 / 2.13 / 5.7 must catch.
"""
from __future__ import annotations

import copy
import itertools
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import build_a  # noqa: E402
import build_b  # noqa: E402
import build_c  # noqa: E402
import spec_a  # noqa: E402
import spec_b  # noqa: E402
import spec_c  # noqa: E402
import titleblock as TBK  # noqa: E402
import verify  # noqa: E402
from dxf_render import render_dxf  # noqa: E402
from primitives import Text, cap_to_em  # noqa: E402
from readers import read_dxf  # noqa: E402
from tcvn import SHEETS, read_profile  # noqa: E402

EX = os.path.join(HERE, "examples")
profile = read_profile()
results = []
WORK = tempfile.mkdtemp(prefix="titlefit_")


def case(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {e}"
    results.append((name, bool(ok), detail))


def build(kind, khung=None, **over):
    name = {"A": "a2_3000x17", "B": "b2_12000x30000", "C": "c1_12000x6000"}[kind]
    raw = spec_b.load_spec(os.path.join(EX, name + ".json"))
    raw.update(over)
    raw.setdefault("khung_ten", {})
    raw["khung_ten"].update(khung or {})
    mod, bld = {"A": (spec_a, build_a), "B": (spec_b, build_b), "C": (spec_c, build_c)}[kind]
    sp = mod.validate(raw)
    return sp, bld.build(sp, profile)


def ids(C):
    return {c["id"] for c in C.items if c["ok"] is False}


def prim_fit(D):
    C = verify.Checks()
    verify.check_title_fit(C, D)
    return ids(C)


def dxf_fit(D, name="t", mutate=None):
    p = os.path.join(WORK, name + ".dxf")
    render_dxf(D, profile, p)
    if mutate:
        raw = open(p, "rb").read()
        raw = mutate(raw)
        open(p, "wb").write(raw)
    C = verify.Checks()
    verify.check_title_fit_dxf(C, D, read_dxf(p), 2, "2.13", "DXF")
    return ids(C)


def rows(D):
    return {k: v for k, v in D.fields.items() if k.startswith("row")}


# ---------------------------------------------------------------- (a) 4-word names shrink and pass verify, for the three drawing types
LONG = {"chu_tri": "NGUYỄN THỊ MINH ANH", "kiem_tra": "TRẦN NGUYỄN HOÀNG LONG", "thiet_ke": "LÊ VĂN C"}


def long_names(kind):
    def f():
        sp, D = build(kind, LONG)
        got = {k: v for k, v in rows(D).items() if k.endswith("_name") or k.endswith("_name_2")}
        joined = [got.get("row1_name"), " ".join(x for x in (got.get("row2_name"), got.get("row2_name_2")) if x), got.get("row3_name")]
        names = [p for p in D.prims if p.tag == "tb_text" and getattr(p, 'field', '').startswith("row") and "name" in getattr(p, 'field', '')]
        ok = not prim_fit(D) and not dxf_fit(D, f"long_{kind}") and joined == [LONG["chu_tri"], LONG["kiem_tra"], LONG["thiet_ke"]]
        return ok, "; ".join(f"{getattr(p, 'field', '')}={p.s!r} em {cap_to_em(p.h):.2f} wf {p.wf:g}" for p in names)
    return f


for k in ("A", "B", "C"):
    case(f"{k}_four_word_names_shrink_to_fit_and_pass_1.31_2.13", long_names(k))


# ---------------------------------------------------------------- (c) default sample names keep their text
def default_names():
    sp, D = build("A", {"ky_mau": True})
    sp2, D2 = build("A")
    want = {"row1_name": "NGUYỄN VĂN A", "row2_name": "TRẦN VĂN B", "row3_name": "LÊ VĂN C"}
    got = {k: v for k, v in D2.fields.items() if k.endswith("_name") and v}
    sizes = {getattr(p, 'field', ''): (round(cap_to_em(p.h), 2), p.wf) for p in D2.prims if getattr(p, 'field', '') in want}
    return got == want and not prim_fit(D2) and not dxf_fit(D2, "default"), f"{got}; cỡ/hệ số rộng {sizes}"


case("default_sample_names_keep_their_text", default_names)


def sample_is_shrunk_not_cut():
    _, D = build("A")
    p = [p for p in D.prims if getattr(p, 'field', '') == "row1_name"][0]
    return p.s == "NGUYỄN VĂN A" and p.wf < 1.0 and abs(cap_to_em(p.h) - 2.5) < 1e-9, f"wf {p.wf:g}, em {cap_to_em(p.h):.2f}"


case("NGUYEN_VAN_A_only_the_width_factor_is_lowered", sample_is_shrunk_not_cut)


# ---------------------------------------------------------------- (b) 40-character strings: shrink to the limit, then break or error, never overflow
def forty(field_kw, text):
    def f():
        try:
            sp, D = build("A", {field_kw: text})
        except spec_b.SpecError as e:
            return True, "lỗi: " + " ".join(e.errors)[:150]
        return not prim_fit(D) and not dxf_fit(D, "forty"), "; ".join(f"{getattr(p, 'field', '')}={p.s!r} em {cap_to_em(p.h):.1f} wf {p.wf:g}" for p in D.prims if getattr(p, 'field', '') in
                                                                      ("cell2_l1", "cell2_l2", "cell5", "cell6", "cell4", "cell1_l1", "cell1_l2", "cell3_l1", "cell3_l2"))
    return f


S40 = "NGUYỄN THỊ MINH ANH TRẦN HOÀNG LONG PHẠM VĂN"[:40]
case("forty_chars_cong_trinh_fits_or_errors", forty("cong_trinh", S40))
case("forty_chars_chu_dau_tu_fits_or_errors", forty("chu_dau_tu", S40))
case("forty_chars_loai_ho_so_two_lines_or_error", forty("loai_ho_so", S40))
case("forty_chars_ky_hieu_ban_ve_error_or_fit", forty("ky_hieu_ban_ve", "KC-" + "0" * 37))
case("forty_chars_ten_ban_ve_fits_or_errors", forty("ten_ban_ve", S40))
case("forty_chars_don_vi_tk_fits_or_errors", forty("don_vi_tk", S40))
case("forty_chars_ho_ten_two_lines_or_error", forty("chu_tri", S40))


def hopeless(field_kw, text, word):
    def f():
        try:
            build("A", {field_kw: text})
        except spec_b.SpecError as e:
            m = " ".join(e.errors)
            return word in m and "rút gọn" in m.lower(), m[:170]
        return False, "không có lỗi"
    return f


case("name_of_40_letters_no_space_is_a_clear_error", hopeless("chu_tri", "N" * 40, "ký tự"))
case("name_of_90_chars_is_a_clear_error", hopeless("chu_tri", " ".join(["NGUYỄN"] * 13), "ký tự"))
case("cell_15_text_too_long_is_a_clear_error", hopeless("o15", "X" * 30, "ký tự"))


# ---------------------------------------------------------------- property sweep: every field, random strings, either an error or no overflow
def sweep():
    rnd = random.Random(7)
    alpha = "ABCDEFGHIKLMNOPQRSTUVXYĂÂÊÔƠƯĐỄẰỔ0123456789 -/."
    keys = ["don_vi_tk", "cong_trinh", "chu_dau_tu", "ten_ban_ve", "ky_hieu_ban_ve", "loai_ho_so", "ngay", "o15"]
    n_ok = n_err = 0
    bad = []
    for _ in range(300):
        kw = {}
        for k in rnd.sample(keys, 2):
            kw[k] = "".join(rnd.choice(alpha) for _ in range(rnd.randint(1, 48))).strip() or "A"
        kw["chu_tri"] = "".join(rnd.choice(alpha[:28]) for _ in range(rnd.randint(1, 30))).strip() or "A"
        try:
            sp, D = build("B", kw)
        except spec_b.SpecError:
            n_err += 1
            continue
        n_ok += 1
        if prim_fit(D) or dxf_fit(D, "sweep"):
            bad.append(kw)
    return not bad and n_ok > 50 and n_err > 10, f"{n_ok} hợp lệ, {n_err} báo lỗi, vi phạm {len(bad)}: {bad[:1]}"


case("property_sweep_300_random_titleblocks_never_overflow", sweep)


# ---------------------------------------------------------------- DXF carries code 41 / PDF template follows the primitives
def dxf_has_41():
    _, D = build("A", LONG)
    p = os.path.join(WORK, "c41.dxf")
    render_dxf(D, profile, p)
    dx = read_dxf(p)
    got = {}
    for e in dx["ents"]:
        if e["type"] == "TEXT" and e["rec"].get(1, [""])[0] in LONG.values():
            got[e["rec"][1][0]] = float(e["rec"][41][0]) if 41 in e["rec"] else 1.0
    want = {p_.s: p_.wf for p_ in D.prims if getattr(p_, 'field', '') in ("row1_name", "row3_name") and p_.s in LONG.values()}
    return got == want and any(v < 1.0 for v in got.values()), f"DXF {got}; primitives {want}"


case("dxf_text_has_width_factor_code_41_equal_to_primitive", dxf_has_41)


def template_follows():
    import re
    _, D = build("A", LONG)
    sh = SHEETS[D.sheet]
    fit = {getattr(p, 'field', ''): (cap_to_em(p.h), p.wf, p.pos) for p in D.prims if p.tag == "tb_text"}
    svg = TBK.template_svg(sh, fit)
    bad = []
    for name, (em, wf, pos) in fit.items():
        m = re.search(r'<text id="%s_field"([^>]*)>' % name, svg)
        a = m.group(1) if m else ""
        fs = re.search(r"font-size:([\d.]+)px", a)
        sc = re.search(r"scale\(([\d.]+),1\)", a)
        if not (fs and abs(float(fs.group(1)) - em) < 1e-6 and ((sc and abs(float(sc.group(1)) - wf) < 1e-6) or (not sc and abs(wf - 1) < 1e-9))):
            bad.append(name)
    return not bad and len(fit) > 10, f"{len(fit)} ô; lệch: {bad}"


case("pdf_template_uses_the_same_size_and_width_factor_as_primitives", template_follows)


# ---------------------------------------------------------------- mutants: 1.31 / 2.13 / 5.7 must catch them
def mutate_prims(fn):
    def f():
        _, D = build("A", LONG)
        assert not prim_fit(D)
        fn(D)
        return "1.31" in prim_fit(D), f"bị bắt: {sorted(prim_fit(D))}"
    return f


def unshrink(D):
    for p in D.prims:
        if getattr(p, 'field', '') == "row2_name":
            p.wf = 1.0


def bigger(D):
    for p in D.prims:
        if getattr(p, 'field', '') == "row1_name":
            p.h *= 2.0


def too_small(D):
    for p in D.prims:
        if getattr(p, 'field', '') == "row1_name":
            p.h = 1.0
            p.wf = 1.0


def move_to_edge(D):
    p = [p for p in D.prims if getattr(p, 'field', '') == "row3_name"][0]
    p.pos = (p.pos[0] + 12.0, p.pos[1])


def wf_below_limit(D):
    for p in D.prims:
        if getattr(p, 'field', '') == "row1_name":
            p.wf = 0.5


def date_cell_text_longer(D):
    p = [p for p in D.prims if getattr(p, 'field', '') == "cell6"][0]
    p.s = p.s * 3


case("mutant_prim_width_factor_reset_to_1_is_caught", mutate_prims(unshrink))
case("mutant_prim_height_doubled_is_caught", mutate_prims(bigger))
case("mutant_prim_text_moved_to_the_cell_edge_is_caught", mutate_prims(move_to_edge))
case("mutant_prim_width_factor_0.5_below_limit_is_caught", mutate_prims(wf_below_limit))
case("mutant_prim_text_longer_than_its_cell_is_caught", mutate_prims(date_cell_text_longer))


def dxf_mut(mutate, name):
    def f():
        _, D = build("A", LONG)
        bad = dxf_fit(D, name, mutate)
        return "2.13" in bad, f"bị bắt: {sorted(bad)}"
    return f


def strip_41(raw):
    out = raw.replace(b"\r\n 41\r\n0.", b"\r\n 41\r\n1.0\r\n 0.")          # not used: replaced below
    lines = raw.split(b"\r\n")
    res = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == b"41" and i + 1 < len(lines) and 0.5 < float(lines[i + 1] or b"1") < 0.999999:
            i += 2                                           # drop the width factor of the shrunk TEXT
            continue
        res.append(lines[i])
        i += 1
    return b"\r\n".join(res)


case("mutant_dxf_width_factor_code_41_removed_is_caught", dxf_mut(strip_41, "m41"))


def dxf_text_moved(raw):
    L = raw.split(b"\r\n")
    i = next(k for k in range(0, len(L) - 1, 2) if L[k].strip() == b"1" and L[k + 1] == "LÊ VĂN C".encode())
    j = i
    while not (L[j].strip() == b"0" and L[j + 1].strip() == b"TEXT"):          # start of this TEXT entity
        j -= 2
    end = i
    while L[end].strip() != b"0" or end == j:
        end += 2                                                                  # up to the next entity (the alignment point 11 follows the text)
    for q in range(j, end, 2):
        if L[q].strip() in (b"10", b"11"):
            L[q + 1] = str(float(L[q + 1]) + 200.0).encode()                     # x of the anchor: moved 10 mm on paper (1:20) towards the cell line
    return b"\r\n".join(L)


case("mutant_dxf_text_moved_out_of_its_cell_is_caught", dxf_mut(dxf_text_moved, "mmove"))


# 5.7 on synthetic PDF glyph outlines (a positive control and two mutants)
def pdf_fit(glyph_fn):
    _, D = build("A", LONG)
    sh = SHEETS[D.sheet]
    cells = TBK.all_cells(sh)
    c = cells[len(cells) // 2]
    H = sh.h
    cx0, cy0, cx1, cy1 = [x for x in cells if x[2] - x[0] == 30][4]
    bb = glyph_fn((cx0, H - cy1, cx1, H - cy0))
    C = verify.Checks()
    verify.check_title_fit_pdf(C, D, [dict(kind="fill", n=80, bb=bb)])
    return ids(C)


case("pdf_5.7_positive_control_ink_inside_the_cell_passes", lambda: (not pdf_fit(lambda b: (b[0] + 2.0, b[1] + 2.0, b[2] - 2.0, b[3] - 2.0)), "ok"))
case("pdf_5.7_ink_crossing_the_right_cell_line_is_caught", lambda: ("5.7" in pdf_fit(lambda b: (b[0] + 10.0, b[1] + 2.0, b[2] + 0.5, b[3] - 2.0)), "bị bắt"))
case("pdf_5.7_ink_within_1mm_of_the_cell_line_is_caught", lambda: ("5.7" in pdf_fit(lambda b: (b[0] + 8.0, b[1] + 2.0, b[2] - 0.5, b[3] - 2.0)), "bị bắt"))

ok_all = True
for name, ok, detail in results:
    ok_all &= ok
    print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail}")
print(f"title-fit tests: {sum(1 for _, o, _ in results if o)}/{len(results)} đúng;", "OK" if ok_all else "FAILED")
sys.exit(0 if ok_all else 1)
