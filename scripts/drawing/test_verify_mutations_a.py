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
    sp3, D3 = load("a7_chung_3600x20", profile)
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
    sp6, D6 = load("a6_ngang_3600x20", profile)
    expect("control_primitives_a6_side_by_side", not prim_check(D6, sp6) and D6.meta["layout"] == "ngang", f"không đạt: {sorted(prim_check(D6, sp6))}; bố cục {D6.meta['layout']}")
    p6 = os.path.join(work, "a6.dxf")
    render_dxf(D6, profile, p6)
    C6 = verify.Checks()
    verify.check_dxf(C6, D6, sp6, profile, p6, do_fc=False)
    expect("control_dxf_a6_side_by_side", not failed(C6), f"không đạt: {sorted(failed(C6))}")
    sp8, D8 = load("a8_ngang_rieng_2400x14", profile)
    expect("control_primitives_a8_side_by_side_two_scales", not prim_check(D8, sp8) and D8.meta["layout"] == "ngang" and D8.scale != D8.view_scale("plan"),
           f"không đạt: {sorted(prim_check(D8, sp8))}; bố cục {D8.meta['layout']} 1:{D8.scale}/1:{D8.view_scale('plan')}")
    p8 = os.path.join(work, "a8.dxf")
    render_dxf(D8, profile, p8)
    C8 = verify.Checks()
    verify.check_dxf(C8, D8, sp8, profile, p8, do_fc=False)
    expect("control_dxf_a8_plan_reduced_in_dxf", not failed(C8), f"không đạt: {sorted(failed(C8))}")
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
        r.p1 = (r.p1[0], r.p1[1] + 1.0 / Dm.view_scale("plan"))
    need({"1.4"}, prim_check(mut(wrong_w), sp1), "prim_plan_width_plus_1mm")
    def wrong_angle(Dm):
        [p for p in Dm.prims if p.tag == "angle_text"][0].s = "GÓC DỐC 35,0°"
    need({"1.6"}, prim_check(mut(wrong_angle), sp1), "prim_angle_text_wrong")
    # (6) false arithmetic printed on the drawing (the old a2 note) and scale/layout mistakes
    def false_equation(Dm):
        n_ = [p for p in Dm.prims if p.tag == "note"][1]
        n_.s = "17 x 176,5 = 3000"
    need({"1.20", "1.9"}, prim_check(mut(false_equation, D2), sp2), "prim_false_equation_17x176.5=3000")
    def wrong_approx(Dm):
        n_ = [p for p in Dm.prims if p.tag == "note"][1]
        n_.s = n_.s.replace("176,5", "176,4")
    need({"1.20", "1.9"}, prim_check(mut(wrong_approx, D2), sp2), "prim_approx_note_176.4")
    def scale_note_wrong(Dm):
        [p for p in Dm.prims if p.tag == "scale_note"][0].s = "TỶ LỆ 1:100"
    need({"1.12"}, prim_check(mut(scale_note_wrong), sp1), "prim_scale_note_1:100")
    def plan_over_section(Dm):
        for p in Dm.prims:
            if p.tag in ("plan_outline", "plan_stringer", "plan_tread_line", "step_no", "plan_arrow", "up_text", "cut_stroke", "cut_arrow", "cut_label", "title_plan"):
                if hasattr(p, "p1"):
                    p.p1 = (p.p1[0], p.p1[1] + 40.0)
                if hasattr(p, "p0"):
                    p.p0 = (p.p0[0], p.p0[1] + 40.0)
                if hasattr(p, "p2"):
                    p.p2 = (p.p2[0], p.p2[1] + 40.0)
                if hasattr(p, "pos"):
                    p.pos = (p.pos[0], p.pos[1] + 40.0)
    need({"1.13", "1.4"}, prim_check(mut(plan_over_section), sp1), "prim_plan_moved_up_over_section")
    def view_scales_swapped(Dm):
        Dm.meta["view_scales"] = {"section": Dm.view_scale("plan"), "plan": Dm.view_scale("section")}
    need({"1.1", "1.3", "1.12"}, prim_check(mut(view_scales_swapped, D2), sp2), "meta_view_scales_swapped_a2_1:20_1:50")
    # (7) 2.2: dimension labels must not run over ticks / extension lines (the old placement of "176,5")
    def label_back_over_tick(Dm):
        d = [x for x in Dm.dims if x.text == "176,5"][0]
        t = [p for p in Dm.prims if p.tag == "dim_single_text" and p.s == "176,5"][0]
        t.rot, t.halign, t.pos = 90.0, "center", (d.line_pos - 0.625, (d.p1[1] + d.p2[1]) / 2)
    need({"1.14"}, prim_check(mut(label_back_over_tick, D2), sp2), "prim_riser_height_label_back_over_tick")
    def b_label_centered_over_ticks(Dm):
        d = [x for x in Dm.dims if x.kind == "h" and x.view == "section"][0]
        t = [p for p in Dm.prims if p.tag == "dim_single_text" and p.s == "250"][0]
        t.halign, t.pos = "center", ((d.p1[0] + d.p2[0]) / 2, d.line_pos + 0.625)
    need({"1.14"}, prim_check(mut(b_label_centered_over_ticks, D3), sp3), "prim_b_label_centered_over_ticks_1:50")
    # (8) mutants found by the independent review of type A that used to slip through
    def swap_level_texts_a(Dm):
        ta = [p for p in Dm.prims if p.tag == "level_text" and p.s == "+0.000"][0]
        tb = [p for p in Dm.prims if p.tag == "level_text" and p.s != "+0.000"][0]
        ta.s, tb.s = tb.s, ta.s
    need({"1.18"}, prim_check(mut(swap_level_texts_a), sp1), "prim_level_texts_swapped")

    def dim_label(old, new, tag="dim_single_text"):
        def fn(Dm):
            [p for p in Dm.prims if p.tag == tag and p.s == old][0].s = new
        return fn
    need({"1.19"}, prim_check(mut(dim_label("250", "260")), sp1), "prim_b_dimension_label_260_on_250")
    need({"1.19"}, prim_check(mut(dim_label("180", "25")), sp1), "prim_h_dimension_label_25_on_180")
    need({"1.19"}, prim_check(mut(dim_label("3600", "3660", "dim_overall_text")), sp1), "prim_total_height_label_3660")
    need({"1.19"}, prim_check(mut(dim_label("800", "900")), sp1), "prim_plan_width_label_900_on_800")

    def drop_tag(tag, idx=0):
        def fn(Dm):
            Dm.prims.remove([p for p in Dm.prims if p.tag == tag][idx])
        return fn
    need({"1.16"}, prim_check(mut(drop_tag("up_text")), sp1), "prim_up_text_missing")
    need({"1.16"}, prim_check(mut(drop_tag("plan_arrow")), sp1), "prim_up_arrow_shaft_missing")
    need({"1.18"}, prim_check(mut(drop_tag("floor_upper")), sp1), "prim_upper_floor_stub_missing")
    need({"1.18"}, prim_check(mut(drop_tag("level_tri")), sp1), "prim_level_triangle_missing")

    def tiny_notes(Dm):
        for p in Dm.prims:
            if p.tag == "note":
                p.h = 1.0
    need({"1.17"}, prim_check(mut(tiny_notes), sp1), "prim_notes_height_1mm")
    need({"1.15"}, prim_check(mut(drop_tag("dim_overall_ext")), sp1), "prim_extension_line_removed")

    def label_on_own_line(Dm):
        d = [x for x in Dm.dims if x.text == "180"][0]
        t = [p for p in Dm.prims if p.tag == "dim_single_text" and p.s == "180"][0]
        t.halign, t.rot, t.pos = "left", 0.0, (d.line_pos - 1.0, (d.p1[1] + d.p2[1]) / 2)           # label straddling its own dimension line
    need({"1.14", "1.17"}, prim_check(mut(label_on_own_line), sp1), "prim_h_label_placed_on_its_own_dimension_line")

    def steps_outside_plan(Dm):
        for p in Dm.prims:
            if p.tag == "step_no":
                p.pos = (p.pos[0], p.pos[1] + 30.0)
    need({"1.17"}, prim_check(mut(steps_outside_plan), sp1), "prim_step_numbers_above_the_plan")

    def level_text_on_symbol(Dm):
        t = [p for p in Dm.prims if p.tag == "level_text"][0]
        t.pos = (t.pos[0], t.pos[1] - 3.0)
    need({"1.17"}, prim_check(mut(level_text_on_symbol), sp1), "prim_level_text_on_the_level_symbol_lines")

    def floating_ext(Dm):
        e = [p for p in Dm.prims if p.tag == "dim_single_ext" and abs(p.p1[0] - p.p2[0]) < 1e-9][0]
        e.p1 = (e.p1[0], e.p1[1] + 6.0)
    need({"1.15"}, prim_check(mut(floating_ext), sp1), "prim_extension_line_starts_6mm_off_the_geometry")

    # (9) 2.x: stringers belong on NET-CHINH, not on KEO (rafters)
    def stringer_on_keo(Dm):
        for p in Dm.prims:
            if p.tag.startswith("stringer_"):
                p.layer = "KEO"
    need({"1.21"}, prim_check(mut(stringer_on_keo), sp1), "prim_stringer_on_layer_KEO")
    # (10) item 3: the stringer section label
    def del_dam_label(Dm):
        Dm.prims.remove([p for p in Dm.prims if p.tag == "dam_label"][0])
    need({"1.23"}, prim_check(mut(del_dam_label), sp1), "prim_stringer_label_deleted")
    def del_dam_leader(Dm):
        Dm.prims.remove([p for p in Dm.prims if p.tag == "dam_leader"][0])
    need({"1.23"}, prim_check(mut(del_dam_leader), sp1), "prim_stringer_leader_deleted")
    def edit_dam_label(Dm):
        [p for p in Dm.prims if p.tag == "dam_label"][0].s = "DẦM CỐN H80x120x2"
    need({"1.23"}, prim_check(mut(edit_dam_label), sp1), "prim_stringer_label_wrong_section")
    def dam_leader_off_stringer(Dm):
        ld = [p for p in Dm.prims if p.tag == "dam_leader"][0]
        ld.p1 = (ld.p1[0], ld.p1[1] + 2.0)
    need({"1.23"}, prim_check(mut(dam_leader_off_stringer), sp1), "prim_stringer_leader_tip_2mm_off_the_stringer")
    def dam_label_new_size(Dm):
        [p for p in Dm.prims if p.tag == "dam_label"][0].h = 3.5
    need({"1.23"}, prim_check(mut(dam_label_new_size), sp1), "prim_stringer_label_other_text_size")
    def dam_label_on_stair(Dm):
        t = [p for p in Dm.prims if p.tag == "dam_label"][0]
        t.pos = (t.pos[0], t.pos[1] + 12.0)
    need({"1.17", "1.23"}, prim_check(mut(dam_label_on_stair), sp1), "prim_stringer_label_moved_onto_the_stair_lines")
    # (13) P1: the stringer covers every inner corner (foot of a riser): 1.24 (primitives) / 2.15 (DXF, real mm)
    s_sec = D1.view_scale("section")
    shift1 = D1.meta["stringer_shift"]
    expect("control_stringer_a1_lowered_by_h_minus_o_and_covers_the_feet", shift1 > 20.0 and not prim_check(D1, sp1), f"hạ {shift1:.2f} mm; không đạt: {sorted(prim_check(D1, sp1))}")

    def move_stringer(dz_real, tags=("stringer_top", "stringer_low")):
        def fn(Dm):
            for p in Dm.prims:
                if p.tag in tags:
                    p.p1 = (p.p1[0], p.p1[1] + dz_real / s_sec)
                    p.p2 = (p.p2[0], p.p2[1] + dz_real / s_sec)
        return fn
    need({"1.24"}, prim_check(mut(move_stringer(1.0, ("stringer_low",))), sp1), "prim_stringer_low_raised_1mm_corners_stick_out")
    need({"1.24", "1.6"}, prim_check(mut(move_stringer(1.0)), sp1), "prim_stringer_whole_strip_raised_1mm")
    need({"1.24", "1.6"}, prim_check(mut(move_stringer(shift1)), sp1), "prim_stringer_back_at_the_old_position_top_on_the_nosing_line")
    need({"1.24", "1.6"}, prim_check(mut(move_stringer(shift1 + 146.0)), sp1), "prim_stringer_inverted_above_the_nosing_line")
    need({"1.6"}, prim_check(mut(move_stringer(-1.0, ("stringer_top",))), sp1), "prim_stringer_top_edge_1mm_off_its_position")

    def alt_spec(**changes):
        raw_ = load_spec(os.path.join(EX, "a1_3600x20.json"))
        raw_.update(changes)
        spx = validate(raw_)
        return spx, build(spx, profile)

    def full_prim_and_dxf(spx, Dx, name):
        px_ = os.path.join(work, name + ".dxf")
        render_dxf(Dx, profile, px_)
        Cx = verify.Checks()
        verify.check_dxf(Cx, Dx, spx, profile, px_, do_fc=False)
        return prim_check(Dx, spx) | failed(Cx)
    sp_eq, D_eq = alt_spec(be_rong_mat_bac=240, dam_con="H60x144x2")          # h = 180, b = 240: cos(theta) = 0.8, o = 144 / 0.8 = 180 = h exactly
    bad_eq = full_prim_and_dxf(sp_eq, D_eq, "o_eq_h")
    expect("stringer_o_equals_h_passes_everything", not bad_eq and D_eq.meta["stringer_shift"] < 1e-9, f"o = {D_eq.meta['stringer_offset']:.6f}, h = {sp_eq['h']:.6f}, hạ {D_eq.meta['stringer_shift']:.2e}; không đạt: {sorted(bad_eq)}")
    sp_gt, D_gt = alt_spec(dam_con="H60x200x2")                                # o = 200 / 0.8 = 253 mm > h = 180: top on the nosing line, lower edge cut at the floor
    bad_gt = full_prim_and_dxf(sp_gt, D_gt, "o_gt_h")
    low_gt = [p for p in D_gt.prims if p.tag == "stringer_low"][0]
    expect("stringer_o_greater_than_h_passes_everything_and_keeps_the_floor_cut", not bad_gt and D_gt.meta["stringer_shift"] == 0.0 and low_gt.p1[1] == D_gt.meta["section_origin"][1] and low_gt.p1[0] > D_gt.meta["section_origin"][0],
           f"o = {D_gt.meta['stringer_offset']:.2f} > h = {sp_gt['h']:.2f}; hạ {D_gt.meta['stringer_shift']}; mép dưới bắt đầu ở sàn: {low_gt.p1[1] == D_gt.meta['section_origin'][1]}; không đạt: {sorted(bad_gt)}")
    sp_sh, D_sh = alt_spec(dam_con="H40x60x2")                                 # a very shallow stringer: o = 73 mm, lowered by 107 mm
    bad_sh = full_prim_and_dxf(sp_sh, D_sh, "shallow")
    expect("stringer_much_shallower_than_h_passes_everything", not bad_sh and D_sh.meta["stringer_shift"] > 100.0, f"hạ {D_sh.meta['stringer_shift']:.2f} mm; không đạt: {sorted(bad_sh)}")
    def o_gt_h_raised(Dm):
        move_stringer(1.0, ("stringer_low",))(Dm)
    # for o > h the corner is inside the strip with room to spare: raising the lower edge by 1 mm must still pass, by 120 mm must fail
    expect("stringer_o_gt_h_lower_edge_raised_1mm_still_covers", not (prim_check(mut(o_gt_h_raised, D_gt), sp_gt) & {"1.24"}), "mép dưới nâng 1 mm vẫn che chân bậc (còn dư)")
    need({"1.24"}, prim_check(mut(move_stringer(120.0, ("stringer_low",)), D_gt), sp_gt), "prim_stringer_o_gt_h_lower_edge_raised_120mm")
    # (11) item 4: clear gap between step numbers and lines
    def steps_back_inside_cells(Dm):                  # the old layout: numbers between the tread lines (0.4-0.9 mm from them at 1:50)
        r_ = [p for p in Dm.prims if p.tag == "plan_outline"][0]
        for p in Dm.prims:
            if p.tag == "step_no":
                p.pos = (p.pos[0], r_.p0[1] + (r_.p1[1] - r_.p0[1]) * 0.58)
    need({"1.22"}, prim_check(mut(steps_back_inside_cells), sp1), "prim_step_numbers_back_inside_cells_at_1:50")
    def steps_0p5_above(Dm):
        r_ = [p for p in Dm.prims if p.tag == "plan_outline"][0]
        for p in Dm.prims:
            if p.tag == "step_no":
                p.pos = (p.pos[0], r_.p1[1] + 0.5)
    need({"1.22"}, prim_check(mut(steps_0p5_above), sp1), "prim_step_numbers_0.5mm_above_the_plan_edge")
    def one_number_shifted_into_tread_line(Dm):
        t = [p for p in Dm.prims if p.tag == "step_no" and p.s == "10"][0]
        t.pos = (t.pos[0] + 2.2, t.pos[1])
    need({"1.5", "1.22"}, prim_check(mut(one_number_shifted_into_tread_line), sp1), "prim_step_number_10_shifted_2.2mm_towards_a_tread_line")
    # (12) item 1: title block, left block rows (role labels + sample names + date by default)
    def title_check(Dm, spx):
        C_ = verify.Checks()
        verify.check_title_rows(C_, Dm, spx)
        return failed(C_)
    expect("control_title_rows_default_sample_names", not title_check(D1, sp1) and sp1["khung_ten"]["ky_nguon"] == "mac_dinh" and len([k for k in D1.fields if k.endswith("_role")]) == 3,
           f"không đạt: {sorted(title_check(D1, sp1))}; nguồn {sp1['khung_ten']['ky_nguon']}")
    def drop_role_text(Dm):
        Dm.prims.remove([p for p in Dm.prims if p.tag == "tb_text" and p.s == "Kiểm tra"][0])
    need({"1.30"}, title_check(mut(drop_role_text), sp1), "title_role_label_missing_in_primitives")
    def blank_field(Dm):
        Dm.fields.pop("row2_name")
    need({"1.30"}, title_check(mut(blank_field), sp1), "title_row_name_field_blank")
    def wrong_date(Dm):
        Dm.fields["row1_date"] = "01/01/2020"
    need({"1.30"}, title_check(mut(wrong_date), sp1), "title_row_date_not_the_drawing_date")
    def text_outside_left_block(Dm):
        t = [p for p in Dm.prims if p.tag == "tb_text" and p.s == "NGUYỄN VĂN A"][0]
        t.pos = (t.pos[0] + 100.0, t.pos[1])
    need({"1.30"}, title_check(mut(text_outside_left_block), sp1), "title_row_text_moved_out_of_the_left_block")
    raw_off = load_spec(os.path.join(EX, "a1_3600x20.json"))
    raw_off["khung_ten"]["ky_mau"] = False
    sp_off = validate(raw_off)
    D_off = build(sp_off, profile)
    expect("title_rows_blank_when_ky_mau_false", not title_check(D_off, sp_off) and not [k for k in D_off.fields if k.startswith("row")], f"nguồn {sp_off['khung_ten']['ky_nguon']}; ô {[k for k in D_off.fields if k.startswith('row')]}")
    raw_named = load_spec(os.path.join(EX, "a1_3600x20.json"))
    raw_named["khung_ten"].update(thiet_ke="PHẠM THỊ D")
    sp_n = validate(raw_named)
    D_n = build(sp_n, profile)
    expect("title_rows_follow_the_spec_when_given", not title_check(D_n, sp_n) and D_n.fields.get("row1_name") == "PHẠM THỊ D" and D_n.fields.get("row1_role") == "Thiết kế" and len([k for k in D_n.fields if k.endswith("_role")]) == 1,
           f"ô {[(k, v) for k, v in D_n.fields.items() if k.startswith('row')]}")
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
    need({"2.5", "2.7"}, dxf_of(mut(stringer_on_keo), "dxf_stringer_on_keo"), "dxf_stringer_on_layer_KEO")
    need({"2.15", "2.7"}, dxf_of(mut(move_stringer(1.0, ("stringer_low",))), "dxf_stringer_low_raised_1mm"), "dxf_stringer_low_raised_1mm_corners_stick_out")
    need({"2.15", "2.7"}, dxf_of(mut(move_stringer(shift1)), "dxf_stringer_old_position"), "dxf_stringer_back_at_the_old_position")
    need({"2.15", "2.7"}, dxf_of(mut(move_stringer(shift1 + 146.0)), "dxf_stringer_inverted"), "dxf_stringer_inverted_above_the_nosing_line")
    need({"2.7", "2.9"}, dxf_of(mut(wrong_b), "dxf_wrong_b"), "dxf_wrong_b_tread")
    need({"2.7", "2.9"}, dxf_of(mut(wrong_level), "dxf_wrong_level"), "dxf_level_line_off")
    need({"2.6", "2.8", "2.9"}, dxf_of(mut(wrong_note), "dxf_wrong_note"), "dxf_note_text_wrong")
    def drop_tread(Dm):
        Dm.prims.remove([p for p in Dm.prims if p.tag == "tread"][7])
    need({"2.5", "2.7", "2.9"}, dxf_of(mut(drop_tread), "dxf_missing_tread"), "dxf_missing_tread")
    src = open(base_dxf, "rb").read()
    for name, old, new, ids in (("dxf_text_edit_note", "THÉP TẤM DÀY 3 MM".encode(), "THÉP TẤM DÀY 5 MM".encode(), {"2.6", "2.8"}),
                                ("dxf_text_edit_level", b"+3.600", b"+3.800", {"2.6", "2.8"}),
                                ("dxf_false_equation", "19 x 250 = 4750".encode(), "19 x 250 = 4700".encode(), {"2.12", "2.6"}),
                                ("dxf_ltscale_changed", f"$LTSCALE\r\n 40\r\n{D1.scale}\r\n".encode(), b"$LTSCALE\r\n 40\r\n100\r\n", {"2.2"})):
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
