"""Mutation tests: deliberately corrupt outputs / primitives and require verify.py to FAIL the matching check,
plus a positive control (the unmutated outputs must pass every check that runs).

    python scripts\\drawing\\test_verify_mutations.py     (needs out\\b2_12000x30000 and out\\b1_16500x36000 from make_drawing)
"""
from __future__ import annotations

import copy
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import verify  # noqa: E402
from build_b import build  # noqa: E402
from dxf_render import render_dxf  # noqa: E402
from primitives import Circle, Line, Rect, Text  # noqa: E402
from readers import read_dxf  # noqa: E402
from spec_b import load_spec, validate  # noqa: E402
from tcvn import read_profile  # noqa: E402

OUT = os.environ.get("TEST_OUT", os.path.join(os.getcwd(), "out"))
EX = os.path.join(HERE, "examples")


def load(name, profile):
    sp = validate(load_spec(os.path.join(EX, name + ".json")))
    return sp, build(sp, profile)


def failed(C):
    return {c["id"] for c in C.items if c["ok"] is False}


def main():
    profile = read_profile()
    sp2, D2 = load("b2_12000x30000", profile)
    work = os.path.join(OUT, "_mutations")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    base_dxf = os.path.join(work, "base.dxf")
    render_dxf(D2, profile, base_dxf)                 # regenerate from D2 (do not trust a stale file)
    src = open(base_dxf, "rb").read()
    pdf2 = os.path.join(OUT, "b2_12000x30000", "b2_12000x30000.pdf")
    pdf1 = os.path.join(OUT, "b1_16500x36000", "b1_16500x36000.pdf")
    results = []

    def expect(name, ok, detail):
        results.append((name, ok, detail))

    # ---- positive controls
    C = verify.Checks()
    verify.check_primitives(C, D2, sp2)
    dx = verify.check_dxf(C, D2, sp2, profile, base_dxf, do_fc=False)
    expect("control_primitives_and_dxf_pass", not failed(C), f"không đạt: {sorted(failed(C))}")
    C = verify.Checks()
    verify.check_pdf(C, D2, sp2, dx, pdf2, "png-not-checked", profile)
    expect("control_pdf_passes", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")

    # ---- DXF text/structure mutations
    def dxf_case(name, old, new, expect_id):
        data = src.replace(old, new, 1)
        assert data != src, f"mutation {name}: pattern not found"
        p = os.path.join(work, name + ".dxf")
        open(p, "wb").write(data)
        C = verify.Checks()
        verify.check_dxf(C, D2, sp2, profile, p, do_fc=False)
        expect(name, expect_id in failed(C), f"mong đợi {expect_id} KHÔNG ĐẠT; thực tế: {sorted(failed(C))}")

    dxf_case("dxf_text_6000_to_6001", b"\r\n  1\r\n6000\r\n", b"\r\n  1\r\n6001\r\n", "2.6")
    dxf_case("dxf_axis_moved_to_layer_CHU", b"\r\n  8\r\nTRUC\r\n", b"\r\n  8\r\nCHU\r\n", "2.5")
    dxf_case("dxf_ltscale_changed", b"$LTSCALE\r\n 40\r\n100\r\n", b"$LTSCALE\r\n 40\r\n50\r\n", "2.2")
    dxf_case("dxf_center_pattern_changed", b" 49\r\n12\r\n", b" 49\r\n11\r\n", "2.4")

    # ---- near-miss geometry: one column moved 0.5 mm in the DXF only
    def shifted(D, dx_paper=0.0, dy_paper=0.0, which=0):
        Dm = copy.deepcopy(D)
        col = [p for p in Dm.prims if p.tag == "column"][which]
        col.p0 = (col.p0[0] + dx_paper, col.p0[1] + dy_paper)
        col.p1 = (col.p1[0] + dx_paper, col.p1[1] + dy_paper)
        return Dm

    Dm = shifted(D2, 0.005)                           # 0.005 mm paper = 0.5 mm real at 1:100
    pm = os.path.join(work, "shifted_column.dxf")
    render_dxf(Dm, profile, pm)
    C = verify.Checks()
    verify.check_dxf(C, D2, sp2, profile, pm, do_fc=False)
    expect("dxf_column_shifted_0.5mm", {"2.9", "2.7"} & failed(C) != set() or "2.9" in failed(C), f"không đạt: {sorted(failed(C))}")

    # ---- primitives
    D = copy.deepcopy(D2)
    D.prims.remove([p for p in D.prims if p.tag == "column"][0])
    C = verify.Checks()
    verify.check_primitives(C, D, sp2)
    expect("prim_drop_one_column", "1.3" in failed(C), f"không đạt: {sorted(failed(C))}")
    D = shifted(D2, 0.3)
    C = verify.Checks()
    verify.check_primitives(C, D, sp2)
    expect("prim_column_off_axis", "1.7" in failed(C), f"không đạt: {sorted(failed(C))}")
    D = copy.deepcopy(D2)
    D.dims[0].value += 10
    C = verify.Checks()
    verify.check_primitives(C, D, sp2)
    expect("prim_dimension_value_off_by_10", "1.9" in failed(C), f"không đạt: {sorted(failed(C))}")
    D = copy.deepcopy(D2)
    bub = [p for p in D.prims if isinstance(p, Circle)][0]
    bub.r = 3.0
    C = verify.Checks()
    verify.check_primitives(C, D, sp2)
    expect("prim_bubble_wrong_diameter", "1.8" in failed(C), f"không đạt: {sorted(failed(C))}")
    # grouped section labels (gom_nhan_tiet_dien): one label + the note "TẤT CẢ CỘT: ..."
    D = copy.deepcopy(D2)
    D.prims.remove(D.by_tag("col_note")[0])
    C = verify.Checks()
    verify.check_primitives(C, D, sp2)
    expect("prim_group_note_deleted", "1.14" in failed(C), f"không đạt: {sorted(failed(C))}")
    D = copy.deepcopy(D2)
    D.by_tag("col_note")[0].s = "TẤT CẢ CỘT: H300x150x6x9"
    C = verify.Checks()
    verify.check_primitives(C, D, sp2)
    expect("prim_group_note_wrong_section", "1.14" in failed(C), f"không đạt: {sorted(failed(C))}")
    D = copy.deepcopy(D2)
    D.prims.append(copy.deepcopy(D.by_tag("col_label")[0]))
    C = verify.Checks()
    verify.check_primitives(C, D, sp2)
    expect("prim_group_extra_label", "1.14" in failed(C), f"không đạt: {sorted(failed(C))}")

    # ---- PDF near-miss: expected geometry shifted 0.3 mm paper (PDF itself is the correct one)
    for name, Dm, ids in (("pdf_column_shifted_0.3mm", shifted(D2, 0.3), {"5.1"}),
                          ("pdf_text_moved_2mm", None, {"5.5"})):
        if Dm is None:
            Dm = copy.deepcopy(D2)
            t = [p for p in Dm.prims if isinstance(p, Text) and p.tag == "dim_chain_text"][0]
            t.pos = (t.pos[0] + 2.0, t.pos[1])
        C = verify.Checks()
        verify.check_pdf(C, Dm, sp2, dx, pdf2, None, profile)
        expect(name, bool(ids & failed(C)), f"mong đợi {sorted(ids)}; không đạt: {sorted(failed(C))}")
    # PDF of another drawing against b2
    C = verify.Checks()
    verify.check_pdf(C, D2, sp2, dx, pdf1, None, profile)
    expect("pdf_of_other_drawing", bool({"5.1", "5.3", "5.4"} & failed(C)), f"không đạt: {sorted(failed(C))}")
    # PDF vs a wrong DXF dimension list (cross check 5.6 needs real values): drop dimension texts from the DXF view
    dx2 = copy.deepcopy(dx)
    dx2["texts"] = [(lay, t) for lay, t in dx["texts"] if not t.isdigit()]
    C = verify.Checks()
    verify.check_pdf(C, D2, sp2, dx2, pdf2, None, profile)
    expect("pdf_dxf_without_dimension_texts", "5.6" in failed(C), f"không đạt: {sorted(failed(C))}")

    # ---- A2 sheet (4.3): the same checks must follow the sheet size (frame 564x400, title block 180x65 at the bottom-right of the frame)
    pdf6 = os.path.join(OUT, "b6_a2_24000x72000", "b6_a2_24000x72000.pdf")
    if os.path.isfile(pdf6):
        sp6, D6 = load("b6_a2_24000x72000", profile)
        dxf6 = os.path.join(work, "b6.dxf")
        render_dxf(D6, profile, dxf6)
        C = verify.Checks()
        dx6 = verify.check_dxf(C, D6, sp6, profile, dxf6, do_fc=False)
        expect("control_a2_primitives_and_dxf", D6.sheet == "A2" and not failed(C), f"sheet {D6.sheet}; không đạt: {sorted(failed(C))}")
        C = verify.Checks()
        verify.check_pdf(C, D6, sp6, dx6, pdf6, "png-not-checked", profile)
        expect("control_a2_pdf_passes_frame_564x400", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")
        Dm = copy.deepcopy(D6)
        Dm.sheet = "A3"
        C = verify.Checks()
        verify.check_pdf(C, Dm, sp6, dx6, pdf6, None, profile)
        expect("pdf_a2_drawing_checked_as_A3", {"4.1", "4.2"} <= failed(C), f"không đạt: {sorted(failed(C))}")
        Dm = copy.deepcopy(D6)
        fr = [p for p in Dm.prims if p.tag == "frame"][0]
        fr.p1 = (fr.p1[0] - 5.0, fr.p1[1])
        C = verify.Checks()
        verify.check_pdf(C, Dm, sp6, dx6, pdf6, None, profile)
        expect("pdf_a2_frame_expected_5mm_narrower", "5.1" in failed(C), f"không đạt: {sorted(failed(C))}")
        Dm = copy.deepcopy(D6)
        tb = [p for p in Dm.prims if p.tag == "tb_outline"][0]
        tb.p0 = (tb.p0[0] - 10.0, tb.p0[1])
        C = verify.Checks()
        verify.check_pdf(C, Dm, sp6, dx6, pdf6, None, profile)
        expect("pdf_a2_title_block_expected_10mm_wider", "5.1" in failed(C), f"không đạt: {sorted(failed(C))}")
    else:
        expect("a2_cases_skipped", False, f"không có {pdf6} (chạy make_drawing cho b6 trước)")

    ok_all = True
    for name, ok, detail in results:
        ok_all &= bool(ok)
        print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail}")
    print("mutation tests:", "OK" if ok_all else "FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
