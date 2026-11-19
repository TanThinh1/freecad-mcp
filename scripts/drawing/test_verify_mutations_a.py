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
    # (13) the stringer strip and the steps. The lower edge ALWAYS runs through the feet of the risers from the origin (0, 0) to (L, (n-1)h); the top edge is the drawn depth od above it.
    #      Snug (0 <= o - h <= 10 mm, o = bd / cos(theta); the default H75x150x2 on every valid example but a3): od = h, the top edge is the nosing line, no cap, no end line;
    #      o - h > 10 mm: od = o, the top edge is cut flat at the upper floor level, cap along z = H to riser n, short end (0, h)-(0, o); o < h: the top edge lies h - o below the nosings (INFO)
    import ban_ve_cli

    def alt_spec(**changes):
        raw_ = load_spec(os.path.join(EX, "a1_3600x20.json"))
        raw_.update(changes)
        spx = validate(raw_)
        return spx, build(spx, profile)

    def move_stringer(dz_real, tags=("stringer_top", "stringer_low")):
        def fn(Dm):
            sc = Dm.view_scale("section")
            for p in Dm.prims:
                if p.tag in tags:
                    p.p1 = (p.p1[0], p.p1[1] + dz_real / sc)
                    p.p2 = (p.p2[0], p.p2[1] + dz_real / sc)
        return fn

    def tagged(Dx, tag):
        return [q for q in Dx.prims if q.tag == tag]

    def drop(tag):
        def fn(Dm):
            Dm.prims.remove(tagged(Dm, tag)[0])
        return fn

    def move_end(tag, which, dx_real, dz_real):
        def fn(Dm):
            sc = Dm.view_scale("section")
            q = tagged(Dm, tag)[0]
            c = getattr(q, which)
            setattr(q, which, (c[0] + dx_real / sc, c[1] + dz_real / sc))
        return fn

    def add_line(tag, a_real, b_real):
        def fn(Dm):
            sc = Dm.view_scale("section")
            ox_, oy_ = Dm.meta["section_origin"]
            Dm.prims.append(Line(layer="NET-CHINH", tag=tag, p1=(ox_ + a_real[0] / sc, oy_ + a_real[1] / sc), p2=(ox_ + b_real[0] / sc, oy_ + b_real[1] / sc)))
        return fn

    def dxf_expect(Dm, spx, Dx, name):
        px_ = os.path.join(work, name + ".dxf")
        render_dxf(Dm, profile, px_)
        Cx = verify.Checks()
        verify.check_dxf(Cx, Dx, spx, profile, px_, do_fc=False)          # expectation: the CORRECT drawing Dx / spec
        return failed(Cx)

    def item(Dx, spx, cid):
        Cx = verify.Checks()
        verify_a.check_primitives_a(Cx, Dx, spx)
        return [c for c in Cx.items if c["id"] == cid][0]

    def real_ends(Dx, tag):
        sc = Dx.view_scale("section")
        ox_, oy_ = Dx.meta["section_origin"]
        q = tagged(Dx, tag)[0]
        return [((c[0] - ox_) * sc, (c[1] - oy_) * sc) for c in (q.p1, q.p2)]

    def full_prim_and_dxf(spx, Dx, name):
        return prim_check(Dx, spx) | dxf_expect(Dx, spx, Dx, name)

    def ends_close(a_, b_):
        return all(abs(x - y) < 1e-6 for p_, q_ in zip(a_, b_) for x, y in zip(p_, q_))

    sp_s, D_s = alt_spec(dam_con="H60x120x2")                                  # shallow: o = 146.9 mm < h = 180 mm
    sp_big, D_big = alt_spec(dam_con="H75x160x2")                              # o - h = 17 mm > 10: not snug, top cut flat at the floor, cap + short end
    sp_eq, D_eq = alt_spec(be_rong_mat_bac=240, dam_con="H60x144x2")          # h = 180, b = 240: cos(theta) = 0.8, o = 144 / 0.8 = 180 = h exactly: snug without a note
    sp_gt, D_gt = alt_spec(dam_con="H60x200x2")                                # o - h = 73 mm: not snug
    sp_sh, D_sh = alt_spec(dam_con="H40x60x2")                                 # very shallow: o = 73 mm
    sp_b10, D_b10 = alt_spec(be_rong_mat_bac=240, dam_con="H60x152x2")        # o - h = 10 mm exactly: snug (limit included)
    sp_b11, D_b11 = alt_spec(be_rong_mat_bac=240, dam_con="H60x153x2")        # o - h = 11.25 mm: not snug
    shift_s = D_s.meta["stringer_shift"]
    h1, L1, H1 = sp1["h"], sp1["L"], sp1["cao_tang"]
    o_big = D_big.meta["stringer_offset"]
    slack_big = o_big - sp_big["h"]                                            # the top edge of the big stringer lies this far above the nosing line (real mm)
    x0_old = slack_big * sp_big["b"] / sp_big["h"]

    # ---- controls
    expect("control_default_stringer_is_snug_edges_through_the_nosings_and_the_feet_nothing_else_drawn",
           D1.meta["stringer_snug"] is True and not prim_check(D1, sp1) and item(D1, sp1, "1.32")["ok"] is True and item(D1, sp1, "1.25")["ok"] is True
           and ends_close(real_ends(D1, "stringer_low"), [(0.0, 0.0), (L1, H1 - h1)]) and ends_close(real_ends(D1, "stringer_top"), [(0.0, h1), (L1, H1)])
           and not tagged(D1, "stringer_cap") and not tagged(D1, "stringer_end") and not tagged(D1, "stringer_foot"),
           f"snug {D1.meta['stringer_snug']}; mép dưới {real_ends(D1, 'stringer_low')}; mép trên {real_ends(D1, 'stringer_top')}; không đạt: {sorted(prim_check(D1, sp1))}")
    expect("snug_note_in_report_info_1.33_and_in_the_spec_notes", item(D1, sp1, "1.33")["ok"] is None and "khít bậc" in item(D1, sp1, "1.33")["detail"] and len(sp1["ghi_chu"]) == 1, item(D1, sp1, "1.33")["detail"])
    sp_t, D_t = alt_spec(cao_tang=3000, so_bac=17, be_rong_mat_bac=250, be_rong_ve=900)
    want_note = "Dải dầm vẽ khít bậc, cao 144,2 mm vuông góc; tiết diện khai báo H75x150x2 cao hơn 5,8 mm"
    tmp_spec = os.path.join(work, "thang_note.json")
    json.dump(dict(cao_tang=3000, so_bac=17, be_rong_ve=900), open(tmp_spec, "w", encoding="utf-8"))
    res_cli = ban_ve_cli.check("thang", tmp_spec, None, None)
    expect("snug_note_text_is_computed_from_the_spec_and_shown_by_kiem_tra_spec", sp_t["ghi_chu"] == [want_note] and want_note in res_cli.get("canh_bao", []) and "H75x150x2" in " ".join(res_cli.get("canh_bao", [])),
           f"spec: {sp_t['ghi_chu']}; kiem_tra_spec canh_bao: {res_cli.get('canh_bao')}")
    expect("no_note_when_not_snug_or_when_exact", not sp_big["ghi_chu"] and not sp_eq["ghi_chu"] and not sp_s["ghi_chu"] and not sp_gt["ghi_chu"], f"{sp_big['ghi_chu']} {sp_eq['ghi_chu']}")
    expect("control_big_stringer_not_snug_top_cut_flat_with_cap_and_end_passes_everything",
           D_big.meta["stringer_snug"] is False and not prim_check(D_big, sp_big) and item(D_big, sp_big, "1.32")["ok"] is None and len(tagged(D_big, "stringer_cap")) == 1 and len(tagged(D_big, "stringer_end")) == 1
           and not tagged(D_big, "stringer_foot") and ends_close([real_ends(D_big, "stringer_low")[0]], [(0.0, 0.0)]) and abs(real_ends(D_big, "stringer_top")[1][1] - H1) < 1e-9,
           f"o - h = {slack_big:.2f} mm; không đạt: {sorted(prim_check(D_big, sp_big))}")
    expect("control_shallow_stringer_top_below_the_nosings_covers_the_feet_1.25_is_info_only", shift_s > 20.0 and not prim_check(D_s, sp_s) and item(D_s, sp_s, "1.25")["ok"] is None
           and "gợi ý" in item(D_s, sp_s, "1.25")["detail"] and item(D_s, sp_s, "1.24")["ok"] is True and ends_close([real_ends(D_s, "stringer_low")[0]], [(0.0, 0.0)])
           and not tagged(D_s, "stringer_cap") and not tagged(D_s, "stringer_end") and item(D_s, sp_s, "1.32")["ok"] is None, f"hạ {shift_s:.2f} mm; {item(D_s, sp_s, '1.25')['detail'][:150]}")
    warn_s = [w for w in sp_s["warnings"] if "không che trọn bậc" in w]
    expect("soft_warning_for_a_shallow_stringer_names_the_needed_depth_and_a_suggestion", len(warn_s) == 1 and "cần >= 146.1 mm vuông góc" in warn_s[0] and "gợi ý H60x150x2" in warn_s[0] and not [w for w in sp1["warnings"] if "không che trọn" in w],
           warn_s[0][:170] if warn_s else "không có cảnh báo")
    for nm, Dx, spx, snug_want in (("o_equals_h", D_eq, sp_eq, True), ("o_minus_h_exactly_10mm", D_b10, sp_b10, True), ("o_minus_h_11.25mm", D_b11, sp_b11, False), ("o_minus_h_73mm", D_gt, sp_gt, False), ("very_shallow", D_sh, sp_sh, False)):
        bad_ = full_prim_and_dxf(spx, Dx, "ctl_" + nm)
        cap_ = len(tagged(Dx, "stringer_cap"))
        expect(f"stringer_{nm}_passes_everything_snug_{snug_want}", not bad_ and Dx.meta["stringer_snug"] is snug_want and bool(cap_) == (not snug_want and Dx.meta["stringer_offset"] > spx["h"]) and ends_close([real_ends(Dx, "stringer_low")[0]], [(0.0, 0.0)]),
               f"o - h = {Dx.meta['stringer_offset'] - spx['h']:.3f} mm; snug {Dx.meta['stringer_snug']}; {cap_} nét nắp; không đạt: {sorted(bad_)}")

    # ---- shallow base: the lower edge through the feet (behaviour unchanged)
    need({"1.24"}, prim_check(mut(move_stringer(1.0, ("stringer_low",)), D_s), sp_s), "prim_stringer_low_raised_1mm_corners_stick_out")
    need({"1.24", "1.6"}, prim_check(mut(move_stringer(1.0), D_s), sp_s), "prim_stringer_whole_strip_raised_1mm")
    need({"1.24", "1.6"}, prim_check(mut(move_stringer(shift_s), D_s), sp_s), "prim_stringer_back_at_the_old_position_top_on_the_nosing_line")
    need({"1.24", "1.6"}, prim_check(mut(move_stringer(shift_s + 146.0), D_s), sp_s), "prim_stringer_inverted_above_the_nosing_line")
    need({"1.6"}, prim_check(mut(move_stringer(-1.0, ("stringer_top",)), D_s), sp_s), "prim_stringer_top_edge_1mm_off_its_position")

    # ---- snug base (D1): top edge through the nosings, lower edge through the feet, both within 0.01 mm; ends on the risers; nothing else (1.32 / 2.21, 1.29 / 2.20)
    snug_cat = [
        ("top_edge_1mm_above_the_nosings", move_stringer(1.0, ("stringer_top",)), {"1.32"}, {"2.21"}),
        ("top_edge_1mm_below_the_nosings", move_stringer(-1.0, ("stringer_top",)), {"1.32", "1.25"}, {"2.21", "2.16"}),
        ("lower_edge_1mm_above_the_feet", move_stringer(1.0, ("stringer_low",)), {"1.32", "1.24"}, {"2.21", "2.15"}),
        ("lower_edge_1mm_below_the_feet", move_stringer(-1.0, ("stringer_low",)), {"1.32"}, {"2.21"}),
        ("lower_edge_starts_1mm_right_of_the_origin", move_end("stringer_low", "p1", 1.0, 0.0), {"1.27", "1.32"}, {"2.18", "2.21"}),
        ("lower_edge_starts_1mm_above_the_origin", move_end("stringer_low", "p1", 0.0, 1.0), {"1.27", "1.32"}, {"2.18", "2.21"}),
        ("extra_cap_line_left_over", add_line("stringer_cap", (L1 - 10.0, H1), (L1, H1)), {"1.29", "1.32"}, {"2.20"}),
        ("extra_short_end_line_left_over", add_line("stringer_end", (0.0, h1), (0.0, h1 + 3.0)), {"1.29", "1.32"}, {"2.20"}),
        ("old_bottom_line_left_over", add_line("stringer_foot", (0.0, 0.0), (10.0, 0.0)), {"1.29", "1.32"}, {"2.20"}),
        ("top_edge_ends_1mm_short_of_the_corner_of_the_upper_floor", move_end("stringer_top", "p2", -1.0, 0.0), {"1.32", "1.26"}, {"2.21", "2.17"}),
        ("top_edge_pokes_1mm_above_the_upper_floor", move_end("stringer_top", "p2", 0.0, 1.0), {"1.28", "1.32"}, {"2.19", "2.21"}),
    ]
    for nm, fn_, pids, dids in snug_cat:
        need(pids, prim_check(mut(fn_), sp1), f"prim_snug_{nm}")
    expect("prim_1.32_edges_0.005mm_off_still_pass", "1.32" not in prim_check(mut(move_stringer(0.005, ("stringer_top",))), sp1) - {"1.6", "1.29"}, "lệch 0,005 mm nằm trong ngưỡng 0,01")
    need({"1.24", "1.25"}, prim_check(mut(move_stringer(h1)), sp1), "prim_snug_strip_inverted_above_the_nosing_line")
    need({"1.25"}, prim_check(mut(move_stringer(-h1 / 2)), sp1), "prim_snug_strip_lowered_by_half_its_depth")

    # ---- big (not snug) base: the top edge o - h above the nosings, cut flat at the floor, cap + short end; lower edge at the origin; nothing above the floor; closed at both ends
    def old_geometry_low(Dm):                                                  # lower edge starting on the floor at x0 as before, plus the old bottom line
        move_end("stringer_low", "p1", x0_old, 0.0)(Dm)
        add_line("stringer_foot", (0.0, 0.0), (x0_old, 0.0))(Dm)

    def top_untruncated(Dm):                                                   # the strip rises above the upper floor: top edge to (L, H + o - h), no cap
        sc = Dm.view_scale("section")
        q = tagged(Dm, "stringer_top")[0]
        q.p2 = (Dm.meta["section_origin"][0] + sp_big["L"] / sc, Dm.meta["section_origin"][1] + (sp_big["cao_tang"] + slack_big) / sc)
        Dm.prims.remove(tagged(Dm, "stringer_cap")[0])

    def cap_shorter(dx_real):
        def fn(Dm):
            sc = Dm.view_scale("section")
            q = tagged(Dm, "stringer_cap")[0]
            q.p1 = (q.p1[0] + dx_real / sc, q.p1[1])
        return fn
    big_cat = [
        ("lower_edge_starts_1mm_right_of_the_origin", move_end("stringer_low", "p1", 1.0, 0.0), {"1.27"}, {"2.18"}),
        ("lower_edge_starts_1mm_above_the_origin", move_end("stringer_low", "p1", 0.0, 1.0), {"1.27"}, {"2.18"}),
        ("old_bottom_line_still_there", add_line("stringer_foot", (0.0, 0.0), (x0_old, 0.0)), {"1.29"}, {"2.20"}),
        ("old_geometry_lower_edge_on_the_floor_at_x0_with_the_old_bottom_line", old_geometry_low, {"1.27", "1.29"}, {"2.18", "2.20"}),
        ("strip_pokes_above_the_upper_floor", top_untruncated, {"1.28", "1.26", "1.29"}, {"2.19", "2.17", "2.20"}),
        ("open_at_the_top_cap_missing", drop("stringer_cap"), {"1.26", "1.29"}, {"2.17", "2.20"}),
        ("open_at_the_top_cap_1mm_short", cap_shorter(1.0), {"1.26", "1.29"}, {"2.17", "2.20"}),
        ("open_at_the_top_edge_1mm_short_of_the_floor", move_end("stringer_top", "p2", -1.0, 0.0), {"1.26"}, {"2.17"}),
        ("open_at_the_foot_short_end_missing", drop("stringer_end"), {"1.26", "1.29"}, {"2.17", "2.20"}),
        ("top_edge_1mm_above_its_place", move_stringer(1.0, ("stringer_top",)), {"1.6", "1.29"}, {"2.7", "2.20"}),
    ]
    for nm, fn_, pids, dids in big_cat:
        need(pids, prim_check(mut(fn_, D_big), sp_big), f"prim_big_{nm}")
    need({"1.25"}, prim_check(mut(move_stringer(-(slack_big + 1.0), ("stringer_top",)), D_big), sp_big), "prim_big_1.25_top_edge_lowered_1mm_below_the_nosings")
    expect("prim_big_1.25_top_edge_lowered_by_less_than_its_slack_still_passes", "1.25" not in prim_check(mut(move_stringer(-(slack_big - 0.5), ("stringer_top",)), D_big), sp_big) - {"1.6", "1.29"},
           f"mép trên cao hơn mũi bậc {slack_big:.2f} mm; hạ {slack_big - 0.5:.2f} mm vẫn chứa mũi bậc")
    need({"1.24"}, prim_check(mut(move_stringer(120.0, ("stringer_low",)), D_gt), sp_gt), "prim_stringer_o_gt_h_lower_edge_raised_120mm")
    expect("prim_1.27_lower_edge_starts_0.05mm_off_the_origin_still_passes", "1.27" not in prim_check(mut(move_end("stringer_low", "p1", 0.05, 0.0), D_big), sp_big), "sai số 0,1 mm thật cho phép")
    expect("prim_1.28_nothing_above_the_floor_on_every_kind_of_stringer", all(item(Dx, spx, "1.28")["ok"] is True for Dx, spx in ((D1, sp1), (D_s, sp_s), (D_eq, sp_eq), (D_gt, sp_gt), (D_big, sp_big))), "1.28 đạt ở dầm khít / sâu / nông / vừa đúng")
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
    for nm, fn_, pids, dids in snug_cat:
        need(dids, dxf_of(mut(fn_), "dxf_snug_" + nm), f"dxf_snug_{nm}")
    expect("dxf_2.21_edges_0.005mm_off_still_pass", "2.21" not in dxf_of(mut(move_stringer(0.005, ("stringer_top",))), "dxf_snug_0.005"), "lệch 0,005 mm nằm trong ngưỡng 0,01")
    need({"2.15", "2.16"}, dxf_of(mut(move_stringer(h1)), "dxf_snug_inverted"), "dxf_snug_strip_inverted_above_the_nosing_line")
    need({"2.16"}, dxf_of(mut(move_stringer(-h1 / 2)), "dxf_snug_lowered_half"), "dxf_snug_strip_lowered_by_half_its_depth")
    need({"2.15", "2.7"}, dxf_expect(mut(move_stringer(1.0, ("stringer_low",)), D_s), sp_s, D_s, "dxf_shallow_low_raised_1mm"), "dxf_shallow_stringer_low_raised_1mm_corners_stick_out")
    need({"2.15", "2.7"}, dxf_expect(mut(move_stringer(shift_s), D_s), sp_s, D_s, "dxf_shallow_old_position"), "dxf_shallow_stringer_back_at_the_old_position")
    for nm, fn_, pids, dids in big_cat:
        need(dids, dxf_expect(mut(fn_, D_big), sp_big, D_big, "dxf_big_" + nm), f"dxf_big_{nm}")
    need({"2.16"}, dxf_expect(mut(move_stringer(-(slack_big + 1.0), ("stringer_top",)), D_big), sp_big, D_big, "dxf_big_low_top"), "dxf_big_2.16_top_edge_lowered_1mm_below_the_nosings")
    expect("dxf_2.18_lower_edge_starts_0.05mm_off_the_origin_still_passes", "2.18" not in dxf_expect(mut(move_end("stringer_low", "p1", 0.05, 0.0), D_big), sp_big, D_big, "dxf_big_low_0.05"), "sai số 0,1 mm thật cho phép")
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
