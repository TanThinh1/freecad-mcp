"""Mutation tests for drawing type A (steel stair): corrupt primitives / DXF / PDF expectations / 3D result on purpose and require
verify.py + verify_a.py to FAIL the matching check; plus a positive control (the unmutated data passes every check that runs).

    python scripts\\drawing\\test_verify_mutations_a.py     (needs out\\a1_3600x20 and out\\a2_3000x17 from make_drawing)
Mutations (the five required): wrong h, wrong b, wrong level position, wrong note text, missing step; extra: near-miss shift,
DXF text edit, 3D bbox / missing tread, PDF of another drawing.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import verify  # noqa: E402
import verify_a  # noqa: E402
from build_a import build  # noqa: E402
from dxf_render import render_dxf  # noqa: E402
from primitives import Line, Text  # noqa: E402
from spec_a import validate  # noqa: E402
from spec_b import load_spec  # noqa: E402
from tcvn import read_profile  # noqa: E402

OUT = os.environ.get("TEST_OUT", os.path.join(os.getcwd(), "out"))
EX = os.path.join(HERE, "examples")


def load(name, profile):
    sp = validate(load_spec(os.path.join(EX, name + ".json")))
    return sp, build(sp, profile)


def failed(C):
    return {c["id"] for c in C.items if c["ok"] is False}


def prim_check(D, sp):
    C = verify.Checks()
    verify_a.check_primitives_a(C, D, sp)
    return failed(C)


def main():
    profile = read_profile()
    sp1, D1 = load("a1_3600x20", profile)
    sp2, D2 = load("a2_3000x17", profile)
    work = os.path.join(OUT, "_mutations_a")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    results = []

    def expect(name, ok, detail):
        results.append((name, ok, detail))

    def need(ids, got, name):
        expect(name, bool(set(ids) & got), f"mong đợi một trong {sorted(ids)} KHÔNG ĐẠT; thực tế: {sorted(got)}")

    # ---- positive controls
    expect("control_primitives_a1", not prim_check(D1, sp1), f"không đạt: {sorted(prim_check(D1, sp1))}")
    expect("control_primitives_a2_non_integer_h", not prim_check(D2, sp2), f"không đạt: {sorted(prim_check(D2, sp2))}")
    base_dxf = os.path.join(work, "base.dxf")
    render_dxf(D1, profile, base_dxf)
    C = verify.Checks()
    dx = verify.check_dxf(C, D1, sp1, profile, base_dxf, do_fc=False)
    expect("control_dxf_a1", not failed(C), f"không đạt: {sorted(failed(C))}")
    res3d = json.load(open(os.path.join(OUT, "a1_3600x20", "_work", "a1_3600x20_3d.json"), encoding="utf-8"))
    C = verify.Checks()
    verify_a.check_3d_a(C, D1, sp1, res3d)
    expect("control_3d_a1", not failed(C), f"không đạt: {sorted(failed(C))}")

    # ---- primitives: the five required mutations
    def mut(fn, D=D1):
        Dm = copy.deepcopy(D)
        fn(Dm)
        return Dm

    # (1) wrong h: one riser top raised by 1 mm real (= 0.02 mm paper at 1:50) - a near miss
    def wrong_h(Dm):
        r = [p for p in Dm.prims if p.tag == "riser"][5]
        r.p2 = (r.p2[0], r.p2[1] + 1.0 / Dm.scale)
    need({"1.1", "1.3"}, prim_check(mut(wrong_h), sp1), "prim_wrong_h_one_riser_plus_1mm")
    # (1b) h label rounded silently on a non-integer h
    def h_label_rounded(Dm):
        d = [x for x in Dm.dims if x.kind == "v" and abs(x.value - sp2["cao_tang"] / sp2["so_bac"]) < 1e-9][0]
        d.text = "176"
    need({"1.8"}, prim_check(mut(h_label_rounded, D2), sp2), "prim_h_label_rounded_176")
    # (2) wrong b: one tread 0.5 mm longer
    def wrong_b(Dm):
        t = [p for p in Dm.prims if p.tag == "tread"][3]
        t.p2 = (t.p2[0] + 0.5 / Dm.scale, t.p2[1])
    need({"1.2", "1.3"}, prim_check(mut(wrong_b), sp1), "prim_wrong_b_tread_plus_0.5mm")
    # (3) level position: +3.600 line lowered by 2 mm real
    def wrong_level(Dm):
        lv = max([p for p in Dm.prims if p.tag == "level_line"], key=lambda p: p.p1[1])
        lv.p1 = (lv.p1[0], lv.p1[1] - 2.0 / Dm.scale)
        lv.p2 = (lv.p2[0], lv.p2[1] - 2.0 / Dm.scale)
    need({"1.7"}, prim_check(mut(wrong_level), sp1), "prim_level_line_off_2mm")
    def wrong_level_text(Dm):
        t = [p for p in Dm.prims if p.tag == "level_text" and p.s != "+0.000"][0]
        t.s = "+3.500"
    need({"1.7"}, prim_check(mut(wrong_level_text), sp1), "prim_level_text_3.500")
    # (4) note text: thickness 3 -> 4, and equation off by one
    def wrong_note(Dm):
        n = [p for p in Dm.prims if p.tag == "note"][0]
        n.s = n.s.replace("3 MM", "4 MM")
    need({"1.9"}, prim_check(mut(wrong_note), sp1), "prim_note_thickness_wrong")
    def wrong_note2(Dm):
        n = [p for p in Dm.prims if p.tag == "note"][2]
        n.s = "19 x 250 = 4700"
    need({"1.9"}, prim_check(mut(wrong_note2), sp1), "prim_note_length_wrong")
    # (5) missing step: drop a tread / a riser / a step number / a plan tread line
    for tag, ids in (("tread", {"1.2", "1.3"}), ("riser", {"1.1", "1.3"}), ("step_no", {"1.5"}), ("plan_tread_line", {"1.4"})):
        def drop(Dm, tag=tag):
            Dm.prims.remove([p for p in Dm.prims if p.tag == tag][7])
        need(ids, prim_check(mut(drop), sp1), f"prim_missing_{tag}")
    # wrong plan width / wrong angle text
    def wrong_w(Dm):
        r = [p for p in Dm.prims if p.tag == "plan_outline"][0]
        r.p1 = (r.p1[0], r.p1[1] + 1.0 / Dm.scale)
    need({"1.4"}, prim_check(mut(wrong_w), sp1), "prim_plan_width_plus_1mm")
    def wrong_angle(Dm):
        [p for p in Dm.prims if p.tag == "angle_text"][0].s = "GÓC DỐC 35,0°"
    need({"1.6"}, prim_check(mut(wrong_angle), sp1), "prim_angle_text_wrong")
    # a spec that disagrees with the (correct) drawing must fail too: b changed in the spec only
    sp_b = dict(sp1, b=260)
    need({"1.2", "1.3", "1.4"}, prim_check(D1, sp_b), "spec_b_260_vs_drawing_b_250")

    # ---- DXF: drawing built from a wrong primitive list, rendered to DXF; the DXF checks use spec formulas, not the primitives
    def dxf_of(Dm, name):
        p = os.path.join(work, name + ".dxf")
        render_dxf(Dm, profile, p)
        C = verify.Checks()
        verify.check_dxf(C, D1, sp1, profile, p, do_fc=False)     # expectation: the CORRECT D1 / spec
        return failed(C)

    need({"2.7", "2.9", "2.5"}, dxf_of(mut(wrong_h), "dxf_wrong_h"), "dxf_wrong_h_one_riser")
    need({"2.7", "2.9"}, dxf_of(mut(wrong_b), "dxf_wrong_b"), "dxf_wrong_b_tread")
    need({"2.7", "2.9"}, dxf_of(mut(wrong_level), "dxf_wrong_level"), "dxf_level_line_off")
    need({"2.6", "2.8", "2.9"}, dxf_of(mut(wrong_note), "dxf_wrong_note"), "dxf_note_text_wrong")
    def drop_tread(Dm):
        Dm.prims.remove([p for p in Dm.prims if p.tag == "tread"][7])
    need({"2.5", "2.7", "2.9"}, dxf_of(mut(drop_tread), "dxf_missing_tread"), "dxf_missing_tread")
    src = open(base_dxf, "rb").read()
    for name, old, new, ids in (("dxf_text_edit_note", "THÉP TẤM DÀY 3 MM".encode(), "THÉP TẤM DÀY 5 MM".encode(), {"2.6", "2.8"}),
                                ("dxf_text_edit_level", b"+3.600", b"+3.800", {"2.6", "2.8"}),
                                ("dxf_ltscale_changed", b"$LTSCALE\r\n 40\r\n50\r\n", b"$LTSCALE\r\n 40\r\n20\r\n", {"2.2"})):
        data = src.replace(old, new, 1)
        if data == src:
            data = src.replace(old.replace(b"\r\n", b"\n"), new.replace(b"\r\n", b"\n"), 1)
        assert data != src, f"mutation {name}: pattern not found"
        p = os.path.join(work, name + ".dxf")
        open(p, "wb").write(data)
        C = verify.Checks()
        verify.check_dxf(C, D1, sp1, profile, p, do_fc=False)
        need(ids, failed(C), name)

    # ---- PDF: the a1 PDF checked against another drawing's expectations, and a shifted expectation (PDF itself is the correct one)
    pdf1 = os.path.join(OUT, "a1_3600x20", "a1_3600x20.pdf")
    if os.path.isfile(pdf1):
        C = verify.Checks()
        verify.check_pdf(C, D1, sp1, dx, pdf1, "png-not-checked", profile)
        expect("control_pdf_a1", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")
        C = verify.Checks()
        verify.check_pdf(C, D2, sp2, dx, pdf1, None, profile)
        need({"5.1", "5.3"}, failed(C), "pdf_of_other_drawing_a2_vs_a1")

        def shifted(Dm):
            t = [p for p in Dm.prims if p.tag == "tread"][4]
            t.p1 = (t.p1[0] + 0.3, t.p1[1])
            t.p2 = (t.p2[0] + 0.3, t.p2[1])
        C = verify.Checks()
        verify.check_pdf(C, mut(shifted), sp1, dx, pdf1, None, profile)
        need({"5.1"}, failed(C), "pdf_tread_expected_0.3mm_paper_off")
    else:
        expect("pdf_cases_skipped", False, f"không có {pdf1} (chạy make_drawing không có --no-pdf trước)")

    # ---- 3D result
    def c3(fn):
        r = copy.deepcopy(res3d)
        fn(r)
        C = verify.Checks()
        verify_a.check_3d_a(C, D1, sp1, r)
        return failed(C)
    need({"6.2"}, c3(lambda r: r["bbox"].__setitem__("zmax", r["bbox"]["zmax"] + 0.01)), "3d_bbox_height_plus_0.01mm")
    need({"6.1", "6.3", "6.4"}, c3(lambda r: (r.__setitem__("n_treads", r["n_treads"] - 1), r["tread_tops"].pop(3), r.__setitem__("tread_volume", r["tread_volume"] * 18 / 19))), "3d_missing_tread")
    need({"6.3"}, c3(lambda r: r["tread_tops"].__setitem__(4, r["tread_tops"][4] + 0.5)), "3d_tread_top_off_0.5mm")
    need({"6.4"}, c3(lambda r: r.__setitem__("tread_volume", r["tread_volume"] * 4 / 3)), "3d_plate_thickness_4_vs_3")
    need({"6.1"}, c3(lambda r: r.__setitem__("n_stringers", 1)), "3d_one_stringer")

    ok_all = True
    for name, ok, detail in results:
        ok_all &= bool(ok)
        print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail if not ok else ''}".rstrip(": ").rstrip())
    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f"mutation tests A: {n_ok}/{len(results)} đúng;", "OK" if ok_all else "FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
