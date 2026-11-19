"""Mutation tests for drawing type C (cross-section of a steel portal frame): corrupt primitives / DXF / PDF expectations on purpose and
require verify.py + verify_c.py to FAIL the matching check; plus positive controls (the unmutated data passes every check that runs).

    python scripts\\drawing\\test_verify_mutations_c.py     (needs out\\c1_12000x6000, c2_16500x7000_kep, c3_24000x8000_1mai, c5_11000x6000_le from make_drawing)

Mutations (required): wrong top height (ridge +1 mm), wrong slope, wrong axis position, wrong level text, missing column, joint node displaced,
hidden inner edge drawn at a joint, missing joint_step (c2), wrong dimension value / label, wrong rounding label (c5), each also as a 0.5 mm near
miss where meaningful; the same kinds of mutations rendered to DXF (the mutated list is used both as the DXF source and as the expectation, so
only the independent spec-formula checks 2.7 / 2.8 can notice) and edits of the DXF bytes; PDF cross-checks with mutated expectations.
"""
from __future__ import annotations

import copy
import math
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import verify  # noqa: E402
import verify_c  # noqa: E402
from build_c import build  # noqa: E402
from dxf_render import render_dxf  # noqa: E402
from primitives import Line, Text  # noqa: E402
from spec_b import load_spec  # noqa: E402
from spec_c import validate  # noqa: E402
from tcvn import read_profile  # noqa: E402

OUT = os.environ.get("TEST_OUT", os.path.join(os.getcwd(), "out"))
EX = os.path.join(HERE, "examples")
NAMES = {"c1": "c1_12000x6000", "c2": "c2_16500x7000_kep", "c3": "c3_24000x8000_1mai", "c5": "c5_11000x6000_le"}


def load(name, profile, **over):
    raw = load_spec(os.path.join(EX, NAMES.get(name, name) + ".json"))
    raw.update(over)
    sp = validate(raw)
    return sp, build(sp, profile)


def failed(C):
    return {c["id"] for c in C.items if c["ok"] is False}


def prim_check(D, sp):
    C = verify.Checks()
    verify_c.check_primitives_c(C, D, sp)
    return failed(C)


def real(D, p):
    return ((p[0] - D.origin[0]) * D.scale, (p[1] - D.origin[1]) * D.scale)


def sheet(D, dx, dy):
    """real mm offset -> sheet mm offset"""
    return dx / D.scale, dy / D.scale


def outline(D):
    return [p for p in D.prims if p.tag in ("col_edge", "raf_edge", "joint_step")]


def move_vertex(D, pred, dx, dy):
    """Move every outline end point whose REAL position satisfies pred by (dx, dy) real mm."""
    ox, oy = sheet(D, dx, dy)
    n = 0
    for ln in outline(D):
        for k in ("p1", "p2"):
            q = getattr(ln, k)
            if pred(real(D, q)):
                setattr(ln, k, (q[0] + ox, q[1] + oy))
                n += 1
    assert n, "mutation did not touch any vertex"


def shift_prim(D, p, dx, dy):
    ox, oy = sheet(D, dx, dy)
    for k in ("p1", "p2", "p0", "c", "pos"):
        if hasattr(p, k):
            q = getattr(p, k)
            setattr(p, k, (q[0] + ox, q[1] + oy))


def by_tag(D, tag):
    return [p for p in D.prims if p.tag == tag]


def main():
    profile = read_profile()
    sp1, D1 = load("c1", profile)
    sp2, D2 = load("c2", profile)
    sp3, D3 = load("c3", profile)
    sp5, D5 = load("c5", profile)
    work = os.path.join(OUT, "_mutations_c")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    results = []

    def expect(name, ok, detail):
        results.append((name, ok, detail))

    def need(ids, got, name):
        expect(name, bool(set(ids) & got), f"mong đợi một trong {sorted(ids)} KHÔNG ĐẠT; thực tế: {sorted(got)}")

    def mut(fn, D):
        Dm = copy.deepcopy(D)
        fn(Dm)
        return Dm

    # ---- positive controls (primitives)
    for nm, sp_, D_ in (("c1", sp1, D1), ("c2_unequal_depths_with_steps", sp2, D2), ("c3_one_roof", sp3, D3), ("c5_non_integer_top", sp5, D5)):
        expect(f"control_primitives_{nm}", not prim_check(D_, sp_), f"không đạt: {sorted(prim_check(D_, sp_))}")
    spv, Dv = load("c1", profile, ve_truc_cau_kien=True)
    expect("control_primitives_c1_member_axes", not prim_check(Dv, spv) and len(by_tag(Dv, "member_axis")) == 2, f"không đạt: {sorted(prim_check(Dv, spv))}")
    sp4, D4 = load("c4_11000x6000", profile)
    expect("control_primitives_c4", not prim_check(D4, sp4), f"không đạt: {sorted(prim_check(D4, sp4))}")

    # ---- positive controls (DXF); the DXF of the correct drawing, checked against the correct drawing
    def dxf_of(Dm, name, Dexp, spx, do_fc=False):
        p = os.path.join(work, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".dxf")
        render_dxf(Dm, profile, p)
        C = verify.Checks()
        dx = verify.check_dxf(C, Dexp, spx, profile, p, do_fc=do_fc)
        return failed(C), dx, p

    for nm, sp_, D_ in (("c1", sp1, D1), ("c2", sp2, D2), ("c3", sp3, D3), ("c5", sp5, D5), ("c1_member_axes", spv, Dv)):
        f_, _, _ = dxf_of(D_, "ctl_" + nm, D_, sp_)
        expect(f"control_dxf_{nm}", not f_, f"không đạt: {sorted(f_)}")

    ridge_x = lambda D, sp_: sp_["nhip"] / 2

    # ---------------------------------------------------------------- mutation catalogue: (name, drawing key, mutator, prim ids, dxf ids)
    cat = []

    def add(name, key, fn, prim_ids, dxf_ids=None):
        cat.append((name, key, fn, prim_ids, dxf_ids))

    S = {"c1": (sp1, D1), "c2": (sp2, D2), "c3": (sp3, D3), "c5": (sp5, D5), "c1v": (spv, Dv)}

    # (1) wrong top height: the ridge (both outline vertices) moved up
    for dy, tag in ((1.0, "1mm"), (0.5, "0.5mm_near_miss")):
        add(f"wrong_top_height_ridge_up_{tag}", "c1", lambda D, dy=dy: move_vertex(D, lambda r: abs(r[0] - 6000.0) < 1e-6, 0.0, dy), {"1.2", "1.6"}, {"2.7"})
    add("wrong_top_height_ridge_up_1mm_c3_one_roof_high_node", "c3", lambda D: move_vertex(D, lambda r: abs(r[0] - 24000.0) < 300.0 and r[1] > 8000.0, 0.0, 1.0), {"1.2", "1.6", "1.7"}, {"2.7"})
    # the top level has no datum line any more: its symbol stands at the ridge on a short leader (1.20 / 2.18); a symbol part moved off its own tip is an error
    def top_level_text_up(D, dy):
        shift_prim(D, [p for p in by_tag(D, "level_text") if p.s == "+6.900"][0], 0.0, dy)
    add("wrong_top_level_text_up_1mm", "c1", lambda D: top_level_text_up(D, 1.0), {"1.20"}, {"2.18"})
    add("wrong_top_level_text_up_0.5mm_near_miss", "c1", lambda D: top_level_text_up(D, 0.5), {"1.20"}, {"2.18"})
    def eave_level_line_up(D, dy):
        shift_prim(D, [p for p in by_tag(D, "level_line") if abs(real(D, p.p1)[1] - 6000.0) < 1e-6][0], 0.0, dy)
    add("wrong_eave_level_line_up_1mm", "c1", lambda D: eave_level_line_up(D, 1.0), {"1.10"}, {"2.7"})
    add("wrong_eave_level_line_up_0.5mm_near_miss", "c1", lambda D: eave_level_line_up(D, 0.5), {"1.10"}, {"2.7"})

    # ---- top level symbol at the ridge (1.20 / 2.18) and short extension lines (1.21 / 2.19)
    def top_symbol_parts(D):
        txt = [p for p in by_tag(D, "level_text") if p.s == "+6.900"][0]
        tip_x, tip_y = txt.pos[0] + 1.0, txt.pos[1] - 3.8
        parts = [p for p in D.prims if p.tag in ("level_tri", "level_bar") and abs(p.p1[1] - tip_y) < 3.2 and abs(p.p1[0] - tip_x) < 20.0] + [txt] + by_tag(D, "level_note")
        return parts

    def symbol_at_axis_B(D):                      # the old layout: the symbol beside axis B, no leader at the ridge
        for p in top_symbol_parts(D):
            shift_prim(D, p, 6000.0, 0.0)
        D.prims.remove(by_tag(D, "level_leader")[0])
    add("top_level_symbol_placed_at_axis_B_instead_of_the_ridge", "c1", symbol_at_axis_B, {"1.20"}, {"2.18"})

    def symbol_moved_sideways(D):                 # symbol and leader end moved 30 mm (real 1500) along x: still at the roof's height but not at the ridge
        for p in top_symbol_parts(D):
            shift_prim(D, p, 1500.0, 0.0)
        ld = by_tag(D, "level_leader")[0]
        ld.p2 = (ld.p2[0] + 1500.0 / D.scale, ld.p2[1])
    add("top_level_symbol_30mm_away_from_the_ridge", "c1", symbol_moved_sideways, {"1.20"}, {"2.18"})

    def symbol_too_high(D):                       # 3 mm higher: 9 mm above the ridge (limit 8)
        for p in top_symbol_parts(D):
            shift_prim(D, p, 0.0, 3.0 * D.scale)
        ld = by_tag(D, "level_leader")[0]
        ld.p2 = (ld.p2[0], ld.p2[1] + 3.0)
    add("top_level_symbol_9mm_above_the_ridge", "c1", symbol_too_high, {"1.20"}, {"2.18"})

    def symbol_too_low(D):                        # 2.5 mm lower: 3.5 mm above the ridge (limit 5)
        for p in top_symbol_parts(D):
            shift_prim(D, p, 0.0, -2.5 * D.scale)
        ld = by_tag(D, "level_leader")[0]
        ld.p2 = (ld.p2[0], ld.p2[1] - 2.5)
    add("top_level_symbol_3.5mm_above_the_ridge", "c1", symbol_too_low, {"1.20"}, {"2.18"})

    def leader_deleted(D):
        D.prims.remove(by_tag(D, "level_leader")[0])
    add("top_level_leader_deleted", "c1", leader_deleted, {"1.20"}, {"2.18"})

    def leader_off_the_ridge(D):
        ld = by_tag(D, "level_leader")[0]
        ld.p1 = (ld.p1[0], ld.p1[1] + 1.0)
    add("top_level_leader_does_not_reach_the_ridge_1mm", "c1", leader_off_the_ridge, {"1.20"}, {"2.18"})

    def top_ext(D):
        e = [p for p in by_tag(D, "dim_ext_custom")]
        return max(e, key=lambda p: p.p1[1])

    def ext_to_the_ridge(D):                      # the old layout: the thin line runs from the dimension all the way to the ridge
        e = top_ext(D)
        e.p1 = (D.origin[0] + 6000.0 / D.scale - 1.0, e.p1[1])
    add("top_extension_line_runs_to_the_ridge", "c1", ext_to_the_ridge, {"1.21"}, {"2.19"})

    def ext_40mm(D):                              # still short of the ridge but 20 mm longer than allowed
        e = top_ext(D)
        e.p1 = (e.p1[0] + 20.0, e.p1[1])
    add("top_extension_line_20mm_too_long", "c1", ext_40mm, {"1.21"}, {"2.19"})

    def ext_long_at_eave(D):
        e = [p for p in by_tag(D, "dim_ext_custom") if abs(real(D, p.p1)[1] - 6000.0) < 1e-6][0]
        e.p1 = (e.p1[0] + 40.0, e.p1[1])
    add("eave_extension_line_40mm_too_long", "c1", ext_long_at_eave, {"1.21"}, {"2.19"})
    def top_dim_wrong(D):
        for p in D.prims:
            if p.tag.endswith("_line") and p.tag.startswith("dim_") and abs(real(D, p.p2)[1] - 6900.0) < 1e-6:
                p.p2 = (p.p2[0], p.p2[1] + 1.0 / D.scale)
    add("wrong_top_dimension_line_end_+1mm", "c1", top_dim_wrong, {"1.11"}, {"2.7"})
    # (2) wrong slope
    def slope_edge(D, dy):
        edges = [p for p in by_tag(D, "raf_edge") if abs(real(D, p.p1)[0] - real(D, p.p2)[0]) > 1000]
        e = max(edges, key=lambda p: max(real(D, p.p1)[1], real(D, p.p2)[1]))     # upper edge of a rafter
        k = "p1" if real(D, e.p1)[1] > real(D, e.p2)[1] else "p2"
        q = getattr(e, k)
        setattr(e, k, (q[0], q[1] + dy / D.scale))
    add("wrong_slope_rafter_edge_rotated_1mm", "c1", lambda D: slope_edge(D, 1.0), {"1.2", "1.6"}, {"2.7"})
    add("wrong_slope_rafter_edge_rotated_0.5mm_near_miss", "c1", lambda D: slope_edge(D, 0.5), {"1.2", "1.6"}, {"2.7"})
    def slope_text(D):
        for p in by_tag(D, "slope_text"):
            p.s = "i = 16% (9,1°)"
    add("wrong_slope_text_16%", "c1", slope_text, {"1.13"}, {"2.8"})
    def slope_angle(D):
        for p in by_tag(D, "slope_text"):
            p.s = p.s.replace("8,5", "8,6")
    add("wrong_slope_text_angle_8,6", "c1", slope_angle, {"1.13"}, {"2.8"})
    def slope_one_dp(D):
        for p in by_tag(D, "slope_text"):
            p.s = "i = 15%"
    add("slope_text_without_angle", "c1", slope_one_dp, {"1.13"}, {"2.8"})
    # ---- 4.1 note "CAO ĐỘ TÍNH THEO GIAO ĐIỂM TRỤC"
    NOTE = "CAO ĐỘ TÍNH THEO GIAO ĐIỂM TRỤC"
    def del_note(D):
        D.prims.remove(by_tag(D, "level_note")[0])
    add("level_note_deleted", "c1", del_note, {"1.19"}, {"2.8"})
    def edit_note(D):
        by_tag(D, "level_note")[0].s = "CAO ĐỘ TÍNH THEO MÉP TRÊN KÈO"
    add("level_note_text_edited", "c1", edit_note, {"1.19"}, {"2.8"})
    def note_dup(D):
        D.prims.append(copy.deepcopy(by_tag(D, "level_note")[0]))
    add("level_note_duplicated", "c1", note_dup, {"1.19"}, {"2.8"})
    def note_on_leader(D):
        n_ = by_tag(D, "level_note")[0]
        ld = by_tag(D, "level_leader")[0]
        n_.pos = (n_.pos[0], (ld.p1[1] + ld.p2[1]) / 2 - 0.6)              # baseline just under the middle of the ridge leader: the box crosses the leader
    add("level_note_over_the_ridge_leader", "c1", note_on_leader, {"1.19"}, None)
    def note_small(D):
        by_tag(D, "level_note")[0].h = 1.8
    add("level_note_wrong_height_1.8", "c1", note_small, {"1.19"}, None)
    def note_far(D):
        n_ = by_tag(D, "level_note")[0]
        n_.pos = (n_.pos[0] - 80.0, n_.pos[1])
    add("level_note_moved_80mm_away", "c1", note_far, {"1.19"}, None)

    # ---- findings of the independent review (all of these used to slip through)
    def swap_level_texts(D, a_, b_):
        ta = [p for p in by_tag(D, "level_text") if p.s == a_][0]
        tb = [p for p in by_tag(D, "level_text") if p.s == b_][0]
        ta.s, tb.s = tb.s, ta.s
    add("swap_level_texts_+6.000_+6.900", "c1", lambda D: swap_level_texts(D, "+6.000", "+6.900"), {"1.10"}, {"2.8"})
    add("swap_level_texts_+0.000_+6.000", "c1", lambda D: swap_level_texts(D, "+0.000", "+6.000"), {"1.10"}, {"2.8"})
    add("swap_level_texts_+0.000_+6.900", "c1", lambda D: swap_level_texts(D, "+0.000", "+6.900"), {"1.10"}, {"2.8"})
    def delete_one_slope_text(D):
        D.prims.remove(by_tag(D, "slope_text")[1])
    add("delete_one_slope_text_two_roofs", "c1", delete_one_slope_text, {"1.13"}, {"2.8"})
    def both_slope_texts_on_left_rafter(D):
        a_, b_ = by_tag(D, "slope_text")[:2]
        b_.pos, b_.rot = a_.pos, a_.rot
    add("both_slope_texts_on_left_rafter", "c1", both_slope_texts_on_left_rafter, {"1.13"}, None)
    def delete_one_rafter_label(D):
        D.prims.remove([p for p in by_tag(D, "section_label") if p.s == "H250x125x6x9" and abs(p.rot) > 1.0][1])
    add("delete_one_rafter_label", "c1", delete_one_rafter_label, {"1.14"}, {"2.8"})
    def column_label_moved_along_axis(D):
        t = [p for p in by_tag(D, "section_label") if abs(p.rot) < 1e-9][0]
        t.pos = (t.pos[0], t.pos[1] - 90.0)
    add("column_label_moved_90mm_below_ground", "c1", column_label_moved_along_axis, {"1.14"}, {"2.8"})

    # (3) wrong axis position
    def axis_move(D, dx, which=1):
        ax = sorted(by_tag(D, "axis_v"), key=lambda p: p.p1[0])[which]
        shift_prim(D, ax, dx, 0.0)
        ax.p2 = (ax.p2[0] + dx / D.scale, ax.p2[1])
    for dx, tag in ((1.0, "1mm"), (0.5, "0.5mm_near_miss")):
        add(f"wrong_axis_B_position_{tag}", "c1", lambda D, dx=dx: axis_move(D, dx), {"1.8"}, {"2.7"})
    add("wrong_axis_A_position_1mm", "c1", lambda D: axis_move(D, 1.0, 0), {"1.8"}, {"2.7"})
    def axis_not_center(D):
        for p in by_tag(D, "axis_v"):
            p.layer = "NET-MANH"
    add("axis_on_continuous_layer", "c1", axis_not_center, {"1.8"}, {"2.7"})
    def bubble_text(D):
        by_tag(D, "bubble_text")[0].s = "C"
    add("bubble_label_C_instead_of_A", "c1", bubble_text, {"1.8"}, {"2.8"})
    # (4) wrong level text
    def level_text(D, old, new):
        t = [p for p in by_tag(D, "level_text") if p.s == old][0]
        t.s = new
    add("wrong_level_text_+6.900_to_+6.800", "c1", lambda D: level_text(D, "+6.900", "+6.800"), {"1.10"}, {"2.8"})
    add("wrong_level_text_+6.000_to_+6.0", "c1", lambda D: level_text(D, "+6.000", "+6.0"), {"1.10"}, {"2.8"})
    add("level_text_2_decimals_comma", "c1", lambda D: level_text(D, "+0.000", "+0,00"), {"1.10"}, {"2.8"})
    def level_line_move(D):
        lv = [p for p in by_tag(D, "level_line") if abs(real(D, p.p1)[1] - 6000.0) < 1e-6][0]
        shift_prim(D, lv, 0.0, -1.0)
        lv.p2 = (lv.p2[0], lv.p2[1])
    add("wrong_level_line_cao_cot_down_1mm", "c1", level_line_move, {"1.10"}, {"2.7"})
    # (5) missing column
    def drop_col(D):
        D.prims.remove([p for p in by_tag(D, "col_edge") if abs(real(D, p.p1)[0] - 12125.0) < 1e-6][0])
    add("missing_column_edge_outer_B", "c1", drop_col, {"1.2", "1.5"}, {"2.7", "2.5"})
    def drop_col_axis(D):
        for p in [p for p in by_tag(D, "col_edge") if real(D, p.p1)[0] > 11000]:
            D.prims.remove(p)
    add("missing_whole_column_B", "c1", drop_col_axis, {"1.2", "1.5"}, {"2.7"})
    def short_col(D):
        e = [p for p in by_tag(D, "col_edge") if abs(real(D, p.p1)[0] + 125.0) < 1e-6][0]
        k = "p1" if real(D, e.p1)[1] < real(D, e.p2)[1] else "p2"
        q = getattr(e, k)
        setattr(e, k, (q[0], q[1] + 0.5 / D.scale))     # foot lifted 0.5 mm off the ground
    add("column_foot_lifted_0.5mm_near_miss", "c1", short_col, {"1.2", "1.5"}, {"2.7"})
    # (6) node displaced: the inner corner of the left knee
    def knee_vertex(D, dx, dy):
        move_vertex(D, lambda r: abs(r[0] - 125.0) < 1e-6 and r[1] > 5000, dx, dy)
    add("joint_node_displaced_1mm_x", "c1", lambda D: knee_vertex(D, 1.0, 0.0), {"1.2", "1.7", "1.4"}, {"2.7"})
    add("joint_node_displaced_1mm_y", "c1", lambda D: knee_vertex(D, 0.0, 1.0), {"1.2", "1.4"}, {"2.7"})
    add("joint_node_displaced_0.5mm_near_miss", "c1", lambda D: knee_vertex(D, 0.0, 0.5), {"1.2", "1.4"}, {"2.7"})
    def knee_outer(D):
        move_vertex(D, lambda r: abs(r[0] + 125.0) < 1e-6 and r[1] > 5000, 0.0, -1.0)
    add("joint_outer_corner_displaced_1mm", "c1", knee_outer, {"1.2", "1.4"}, {"2.7"})
    def ridge_x_shift(D):
        move_vertex(D, lambda r: abs(r[0] - 6000.0) < 1e-6, 1.0, 0.0)
    add("ridge_node_displaced_sideways_1mm", "c1", ridge_x_shift, {"1.2", "1.6"}, {"2.7"})
    # (7) hidden inner edge at a joint: an extra line on the cut line
    def hidden_edge(D, sp_, tag="joint_step"):
        X = verify_c.expect_values(sp_)
        pol = dict(verify_c.member_polys(X))["colA"]
        top = sorted(pol, key=lambda q: -q[1])[:2]               # the two highest vertices of the clipped column = the cut line
        a, b = (D.origin[0] + top[0][0] / D.scale, D.origin[1] + top[0][1] / D.scale), (D.origin[0] + top[1][0] / D.scale, D.origin[1] + top[1][1] / D.scale)
        D.prims.append(Line(layer="KEO" if tag != "col_edge" else "COT", tag=tag, p1=a, p2=b))
    add("hidden_inner_edge_on_cut_line_c1", "c1", lambda D: hidden_edge(D, sp1), {"1.2", "1.4"}, {"2.7"})
    add("hidden_inner_edge_on_cut_line_c2", "c2", lambda D: hidden_edge(D, sp2), {"1.2", "1.4"}, {"2.7"})
    def hidden_as_raf(D):
        hidden_edge(D, sp1, "raf_edge")
    add("hidden_inner_edge_tagged_raf_edge", "c1", hidden_as_raf, {"1.2", "1.4", "1.3"}, {"2.7"})
    # (8) missing joint step (c2) / wrong step
    def drop_step(D):
        D.prims.remove(by_tag(D, "joint_step")[0])
    add("missing_joint_step_c2", "c2", drop_step, {"1.2", "1.3"}, {"2.7"})
    def step_short(D):
        s_ = by_tag(D, "joint_step")[0]
        s_.p2 = (s_.p2[0] + 0.5 / D.scale, s_.p2[1])
    add("joint_step_end_moved_0.5mm_near_miss", "c2", step_short, {"1.2", "1.4"}, {"2.7"})
    def step_as_edge(D):
        by_tag(D, "joint_step")[0].tag = "raf_edge"
    add("joint_step_tagged_as_raf_edge", "c2", step_as_edge, {"1.3"}, None)
    # (9) dimensions
    def dim_text(D, old, new):
        t = [p for p in D.prims if p.tag.startswith("dim_") and p.tag.endswith("_text") and p.s == old][0]
        t.s = new
    add("wrong_dimension_label_span_12000_to_12100", "c1", lambda D: dim_text(D, "12000", "12100"), {"1.11"}, {"2.8"})
    add("wrong_dimension_label_900_to_90", "c1", lambda D: dim_text(D, "900", "90"), {"1.11"}, {"2.8"})
    def dim_value(D):
        d = [d for d in D.dims if d.kind == "h"][0]
        d.value += 1.0
    add("wrong_dim_value_in_D.dims_span_+1mm", "c1", dim_value, {"1.11"}, None)
    def dim_line_short(D):
        p = [p for p in D.prims if p.tag.startswith("dim_") and p.tag.endswith("_line") and abs(real(D, p.p1)[1] - real(D, p.p2)[1]) < 1e-6][0]
        p.p2 = (p.p2[0] - 0.5 / D.scale, p.p2[1])
    add("dimension_line_span_0.5mm_short_near_miss", "c1", dim_line_short, {"1.11"}, {"2.7"})
    def dim_layer(D):
        [p for p in D.prims if p.tag.startswith("dim_") and p.tag.endswith("_line")][0].layer = "NET-MANH"
    add("dimension_line_on_wrong_layer", "c1", dim_layer, {"1.11"}, {"2.7"})
    def dim_drop(D):
        for p in [p for p in D.prims if p.tag == "dim_overall_text"]:
            D.prims.remove(p)
    add("missing_dimension_text_total_height", "c1", dim_drop, {"1.11"}, {"2.8"})
    # (10) rounding rule (c5: top 6731.5, rise 731.5)
    add("rounding_label_6732_to_6731", "c5", lambda D: dim_text(D, "6732", "6731"), {"1.11"}, {"2.8"})
    add("rounding_label_rise_732_to_731", "c5", lambda D: dim_text(D, "732", "731"), {"1.11"}, {"2.8"})
    add("rounding_label_6732_to_6731.5", "c5", lambda D: dim_text(D, "6732", "6731.5"), {"1.11"}, {"2.8"})
    add("rounding_level_text_+6.732_to_+6.731", "c5", lambda D: level_text(D, "+6.732", "+6.731"), {"1.10"}, {"2.8"})
    def no_warning(D):
        D.info["warnings"] = []
    add("rounding_warning_missing_in_report", "c5", no_warning, {"1.12"}, None)
    def exact_top_rounded_in_geometry(D):      # geometry drawn with the rounded value 6732 instead of 6731.5 (ridge 0.5 mm too high)
        move_vertex(D, lambda r: abs(r[0] - 5500.0) < 1e-6, 0.0, 0.5)
    add("c5_geometry_uses_rounded_top_0.5mm", "c5", exact_top_rounded_in_geometry, {"1.2", "1.6"}, {"2.7"})
    # (11) texts / layout
    def sec_label(D):
        by_tag(D, "section_label")[0].s = "H300x150x6x9"
    add("wrong_section_label_column", "c1", sec_label, {"1.14"}, {"2.8"})
    def sec_label_drop(D):
        for p in by_tag(D, "section_label")[:2]:
            D.prims.remove(p)
    add("missing_section_labels_columns", "c1", sec_label_drop, {"1.14"}, {"2.8"})
    def scale_note(D):
        by_tag(D, "scale_note")[0].s = "TỶ LỆ 1:100"
    add("scale_note_1:100_on_1:50_drawing", "c1", scale_note, {"1.15"}, {"2.8"})
    def title(D):
        by_tag(D, "title")[0].s = "MẶT CẮT NGANG NHÀ"
    add("wrong_view_title", "c1", title, {"1.15"}, None)
    def ground_short(D):
        g = by_tag(D, "ground")[0]
        g.p1 = (g.p1[0] + 3.0, g.p1[1])
    add("ground_line_shortened_3mm_paper", "c1", ground_short, {"1.9"}, {"2.7"})
    def ground_up(D):
        shift_prim(D, by_tag(D, "ground")[0], 0.0, 0.5)
    add("ground_line_off_zero_0.5mm_near_miss", "c1", ground_up, {"1.9"}, {"2.7"})
    def move_all(D):
        for p in D.prims:
            if not p.sheet:
                shift_prim(D, p, 0.0, 0.0) if False else None
        for p in D.prims:
            if p.sheet:
                continue
            for k in ("p1", "p2", "p0", "c", "pos"):
                if hasattr(p, k):
                    q = getattr(p, k)
                    setattr(p, k, (q[0] + 300.0, q[1]))
        D.origin = (D.origin[0] + 300.0, D.origin[1])
    add("drawing_moved_onto_title_block_and_out_of_frame", "c1", move_all, {"1.17"}, None)
    def extra_member_axis(D):
        D.prims.append(Line(layer="NET-TAM", tag="member_axis", p1=(100.0, 100.0), p2=(150.0, 120.0)))
    add("member_axis_drawn_when_not_requested", "c1", extra_member_axis, {"1.18"}, {"2.7"})
    def member_axis_move(D):
        shift_prim(D, by_tag(D, "member_axis")[0], 0.0, 1.0)
    add("member_axis_moved_1mm", "c1v", member_axis_move, {"1.18"}, {"2.7"})
    def false_expr(D):
        by_tag(D, "slope_text")[0].s = "10 x 3 = 31"
    add("false_arithmetic_text", "c1", false_expr, {"1.20", "1.13"}, None)

    # ---------------------------------------------------------------- run: primitives
    for name, key, fn, prim_ids, dxf_ids in cat:
        sp_, D_ = S[key]
        Dm = mut(fn, D_)
        need(prim_ids, prim_check(Dm, sp_), f"prim_{name}")
    # spec disagreeing with the (correct) drawing
    need({"1.2", "1.6", "1.7", "1.10", "1.1"}, prim_check(D1, dict(sp1, y_top=6901.0, y_top_exact=sp1["y_top_exact"] + 1)), "spec_top_6901_vs_drawing_6900")
    need({"1.2", "1.16", "1.6"}, prim_check(D1, dict(sp1, scale=100)) | prim_check(D1, dict(sp1, scale=100, nhip=12100.0)), "spec_scale_1:100_vs_drawing_1:50")
    need({"1.2", "1.6", "1.7", "1.8", "1.10", "1.11"}, prim_check(D1, dict(sp1, nhip=12001.0)), "spec_nhip_12001_vs_drawing_12000")
    need({"1.2", "1.5"}, prim_check(D1, dict(sp1, col=dict(sp1["col"], h=260.0))), "spec_column_depth_260_vs_drawing_250")
    need({"1.2", "1.6"}, prim_check(D2, dict(sp2, raf=dict(sp2["raf"], h=340.0))), "spec_rafter_depth_340_vs_drawing_350")
    need({"1.2", "1.6", "1.7"}, prim_check(D1, dict(sp1, so_mai=1)), "spec_so_mai_1_vs_drawing_2_roofs")

    # ---------------------------------------------------------------- run: DXF (mutated list used as source AND expectation -> only 2.7 / 2.8 can notice)
    for name, key, fn, prim_ids, dxf_ids in cat:
        if not dxf_ids:
            continue
        sp_, D_ = S[key]
        Dm = mut(fn, D_)
        f_, _, _ = dxf_of(Dm, "m_" + name, Dm, sp_)
        need(dxf_ids, f_, f"dxf_{name}")

    # ---- DXF byte edits (the DXF itself is corrupted; expectation = correct drawing)
    base = os.path.join(work, "ctl_c1.dxf")
    src = open(base, "rb").read()

    def sub_all(data, old, new, name):
        d = data.replace(old, new)
        if d == data:
            d = data.replace(old.replace(b"\r\n", b"\n"), new.replace(b"\r\n", b"\n"))
        assert d != data, f"mutation {name}: pattern not found"
        return d

    byte_cases = [
        ("dxf_bytes_level_text_+6.900_to_+6.800", b"+6.900", b"+6.800", {"2.8", "2.6"}),
        ("dxf_bytes_slope_text_15%_to_16%", "i = 15%".encode(), "i = 16%".encode(), {"2.8", "2.6"}),
        ("dxf_bytes_section_label", b"H250x125x6x9", b"H250x125x6x8", {"2.8", "2.6"}),
        ("dxf_bytes_view_title", "MẶT CẮT NGANG KHUNG".encode(), "MẶT CẮT NGANG NHÀ".encode(), {"2.6", "2.8"}),
    ]
    for name, old, new, ids in byte_cases:
        data = sub_all(src, old, new, name)
        p = os.path.join(work, name + ".dxf")
        open(p, "wb").write(data)
        C = verify.Checks()
        verify.check_dxf(C, D1, sp1, profile, p, do_fc=False)
        need(ids, failed(C), name)
    # numeric coordinates edited in the DXF: the axis B x = 12000 -> 12001, ridge y, a column x
    lines = src.decode("utf-8").splitlines(keepends=True)

    def edit_value(code, old, new, name, ids, nth=0):
        """edit the nth group (code, value==old) in the DXF text"""
        out, seen, done = [], 0, False
        for k, ln in enumerate(lines):
            if not done and k % 2 == 1 and lines[k - 1].strip() == str(code) and ln.strip() == old:
                if seen == nth:
                    ln = ln.replace(old, new)
                    done = True
                seen += 1
            out.append(ln)
        assert done, f"mutation {name}: value not found"
        p = os.path.join(work, name + ".dxf")
        open(p, "w", encoding="utf-8", newline="").write("".join(out))
        C = verify.Checks()
        verify.check_dxf(C, D1, sp1, profile, p, do_fc=False)
        need(ids, failed(C), name)

    from readers import read_dxf
    dx0 = read_dxf(base)
    axisB = [e for e in dx0["ents"] if e["type"] == "LINE" and e["layer"] == "TRUC" and abs(float(e["rec"][10][0]) - 12000.0) < 1e-6][0]
    raw_x = axisB["rec"][10][0]
    edit_value(10, raw_x, "12000.5", "dxf_value_axis_B_start_x_+0.5mm", {"2.7", "2.9"})
    top_edges = [e for e in dx0["ents"] if e["type"] == "LINE" and e["layer"] == "KEO" and abs(float(e["rec"][11][0]) - 6000.0) < 1e-3 or e["type"] == "LINE" and e["layer"] == "KEO" and abs(float(e["rec"][10][0]) - 6000.0) < 1e-3]
    e0 = top_edges[0]
    code, idx = (11, 0) if abs(float(e0["rec"][11][0]) - 6000.0) < 1e-3 else (10, 0)
    ycode = code + 10
    raw_y = e0["rec"][ycode][0]
    edit_value(ycode, raw_y, f"{float(raw_y) + 0.5:.6f}", "dxf_value_ridge_vertex_y_+0.5mm", {"2.7", "2.9"})

    # ---- PDF cross-checks: the correct PDF of c1 against mutated expectations
    pdf1 = os.path.join(OUT, NAMES["c1"], NAMES["c1"] + ".pdf")
    if os.path.isfile(pdf1):
        C0 = verify.Checks()
        dx1 = verify.check_dxf(C0, D1, sp1, profile, base, do_fc=False)
        C = verify.Checks()
        verify.check_pdf(C, D1, sp1, dx1, pdf1, "png-not-checked", profile)
        expect("control_pdf_c1", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")
        pdf2 = os.path.join(OUT, NAMES["c2"], NAMES["c2"] + ".pdf")
        pdf5 = os.path.join(OUT, NAMES["c5"], NAMES["c5"] + ".pdf")
        for nm, sp_, D_, pdf_ in (("c2", sp2, D2, pdf2), ("c3", sp3, D3, os.path.join(OUT, NAMES["c3"], NAMES["c3"] + ".pdf")), ("c5", sp5, D5, pdf5)):
            if os.path.isfile(pdf_):
                Cx = verify.Checks()
                dxx = verify.check_dxf(Cx, D_, sp_, profile, os.path.join(work, f"ctl_{nm}.dxf"), do_fc=False)
                C = verify.Checks()
                verify.check_pdf(C, D_, sp_, dxx, pdf_, "png-not-checked", profile)
                expect(f"control_pdf_{nm}", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")
        C = verify.Checks()
        verify.check_pdf(C, D2, sp2, dx1, pdf1, None, profile)
        need({"5.1", "5.3"}, failed(C), "pdf_of_other_drawing_c2_expectation_vs_c1_pdf")

        def pdf_case(name, fn, ids):
            Dm = mut(fn, D1)
            C = verify.Checks()
            verify.check_pdf(C, Dm, sp1, dx1, pdf1, None, profile)
            need(ids, failed(C), name)

        def ridge_paper(D):      # 0.3 mm on paper (= 15 mm real at 1:50): larger than the PDF tolerance 0.06 mm
            move_vertex(D, lambda r: abs(r[0] - 6000.0) < 1e-6, 0.0, 0.3 * D.scale)
        pdf_case("pdf_ridge_expected_0.3mm_paper_higher", ridge_paper, {"5.1"})
        def level_paper(D):
            shift_prim(D, [p for p in by_tag(D, "level_line")][0], 0.0, 0.3 * D.scale)
        pdf_case("pdf_level_line_expected_0.3mm_paper_off", level_paper, {"5.1"})
        def axis_paper(D):
            ax = by_tag(D, "axis_v")[1]
            shift_prim(D, ax, 0.3 * D.scale, 0.0)
            ax.p2 = (ax.p2[0] + 0.3, ax.p2[1])
        pdf_case("pdf_axis_B_expected_0.3mm_paper_off", axis_paper, {"5.1"})
        def knee_paper(D):
            move_vertex(D, lambda r: abs(r[0] - 125.0) < 1e-6 and r[1] > 5000, 0.3 * D.scale, 0.0)
        pdf_case("pdf_knee_vertex_expected_0.3mm_paper_off", knee_paper, {"5.1"})
        pdf_case("pdf_expected_missing_column_edge", lambda D: D.prims.remove([p for p in by_tag(D, "col_edge")][0]), {"5.2", "5.1", "5.3"})
        pdf_case("pdf_expected_extra_hidden_edge", lambda D: hidden_edge(D, sp1), {"5.1", "5.3"})
        def axis_layer(D):
            by_tag(D, "axis_v")[0].layer = "NET-MANH"
        pdf_case("pdf_expected_axis_not_center", axis_layer, {"5.4", "5.1"})
        def dim_len(D):
            p = [p for p in D.prims if p.tag.startswith("dim_") and p.tag.endswith("_line")][0]
            p.p2 = (p.p2[0], p.p2[1] + 0.3) if abs(p.p2[0] - p.p1[0]) < 1e-9 else (p.p2[0] + 0.3, p.p2[1])
        pdf_case("pdf_dimension_line_expected_0.3mm_paper_longer", dim_len, {"5.1", "5.6"})
    else:
        expect("pdf_cases_skipped", False, f"không có {pdf1} (chạy make_drawing không có --no-pdf trước)")

    # ---- A1 sheet (4.3): frame 811x574, title block 180x65 at the bottom-right of the frame; policy picks A1 only when A3/A2 do not hold the drawing
    pdf8 = os.path.join(OUT, "c8_a1_60000x12000", "c8_a1_60000x12000.pdf")
    if os.path.isfile(pdf8):
        sp8, D8 = load("c8_a1_60000x12000", profile)
        expect("control_a1_primitives", D8.sheet == "A1" and D8.scale == 100 and not prim_check(D8, sp8), f"khổ {D8.sheet} 1:{D8.scale}; không đạt: {sorted(prim_check(D8, sp8))}")
        f8, dx8, _ = dxf_of(D8, "ctl_c8", D8, sp8)
        expect("control_a1_dxf", not f8, f"không đạt: {sorted(f8)}")
        C = verify.Checks()
        verify.check_pdf(C, D8, sp8, dx8, pdf8, "png-not-checked", profile)
        expect("control_a1_pdf_passes_frame_811x574", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")
        Dm = copy.deepcopy(D8)
        Dm.sheet = "A2"
        C = verify.Checks()
        verify.check_pdf(C, Dm, sp8, dx8, pdf8, None, profile)
        expect("pdf_a1_drawing_checked_as_A2", {"4.1", "4.2"} <= failed(C), f"không đạt: {sorted(failed(C))}")
        # the sheet policy: the same drawing labelled A3 (as if the builder had not moved up to A1) must fail 1.16 / 1.17
        Dm = copy.deepcopy(D8)
        Dm.sheet = "A3"
        C = verify.Checks()
        verify_c.check_primitives_c(C, Dm, sp8)
        expect("policy_a1_drawing_labelled_A3", {"1.16", "1.17"} <= failed(C), f"không đạt: {sorted(failed(C))}")
        # a drawing that fits A3 but is labelled A2 violates "A3 first"
        Dm = copy.deepcopy(D1)
        Dm.sheet = "A2"
        C = verify.Checks()
        verify_c.check_primitives_c(C, Dm, sp1)
        expect("policy_a3_drawing_labelled_A2", "1.16" in failed(C), f"không đạt: {sorted(failed(C))}")
    else:
        expect("a1_cases_skipped", False, f"không có {pdf8} (chạy make_drawing cho c8 trước)")

    ok_all = True
    for name, ok, detail in results:
        ok_all &= bool(ok)
        print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail if not ok else ''}".rstrip(": ").rstrip())
    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f"mutation tests C: {n_ok}/{len(results)} đúng;", "OK" if ok_all else "FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
