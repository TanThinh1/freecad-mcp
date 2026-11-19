"""Mutation tests for drawing type D (purlin plan of a roof): corrupt primitives / DXF / DWG / PDF expectations on purpose and require verify.py + verify_d.py to FAIL
the matching check; plus positive controls (the unmutated data passes every check that runs).

    python scripts\\drawing\\test_verify_mutations_d.py     (needs out\\d1_12000x30000_2mai, d2_12000x30000_1mai, d3_24000x48000_2mai, d4_a1_24000x72000 from make_drawing; TCVN_PROFILE set)

Mutations: purlin moved / missing / duplicated / shortened / tilted / on another layer / extra / unevenly spaced (also 0.5 mm near misses), spec disagreeing with the drawing
(n, number of roofs, slope), dimension chain (segment, label, rounding, layer, ticks, extension lines, positions), notes (section, MẶC ĐỊNH marker, count, real / projected
spacing, slope, centring, overlap), TIM NÓC label, title / scale / title-block fields, grid + columns, layout and sheet policy, warnings, false arithmetic; the same kinds of
corruption rendered to DXF (only the independent spec-formula checks 2.22-2.25 can notice), byte / coordinate edits of the DXF, the DWG read-back check 3.9 (also through a real
ODA round trip), and PDF cross-checks 5.1 / 5.6 / 5.8 against mutated expectations and against the PDF of another drawing.
"""
from __future__ import annotations

import copy
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import oda  # noqa: E402
import verify  # noqa: E402
import verify_d  # noqa: E402
from build_d import build  # noqa: E402
from dxf_render import render_dxf  # noqa: E402
from primitives import Line, Text  # noqa: E402
from readers import read_dxf  # noqa: E402
from spec_b import SpecError, load_spec  # noqa: E402
from spec_d import validate  # noqa: E402
from tcvn import read_profile  # noqa: E402

OUT = os.environ.get("TEST_OUT", os.path.join(os.getcwd(), "out"))
EX = os.path.join(HERE, "examples")
NAMES = {"d1": "d1_12000x30000_2mai", "d2": "d2_12000x30000_1mai", "d3": "d3_24000x48000_2mai", "d4": "d4_a1_24000x72000"}


def load(key, profile, **over):
    raw = load_spec(os.path.join(EX, NAMES[key] + ".json"))
    raw.update(over)
    sp = validate(raw)
    return sp, build(sp, profile)


def failed(C):
    return {c["id"] for c in C.items if c["ok"] is False}


def prim_check(D, sp):
    C = verify.Checks()
    verify_d.check_primitives_d(C, D, sp)
    return failed(C)


def by_tag(D, tag):
    return [p for p in D.prims if p.tag == tag]


def purlins(D):
    return sorted(by_tag(D, "purlin"), key=lambda p: p.p1[1])


def shift(D, p, dx, dy):
    """move a primitive by (dx, dy) REAL mm"""
    ox, oy = dx / D.scale, dy / D.scale
    for k in ("p1", "p2", "p0", "c", "pos"):
        if hasattr(p, k):
            q = getattr(p, k)
            setattr(p, k, (q[0] + ox, q[1] + oy))


def real_y(D, p):
    return (p.p1[1] - D.origin[1]) * D.scale


def dim_lines(D, vertical, tag="dim_chain_line"):
    return [p for p in D.prims if p.tag == tag and isinstance(p, Line) and (abs(p.p1[0] - p.p2[0]) < 1e-9) == vertical]


def text_by(D, tag, s=None):
    return [p for p in D.prims if p.tag == tag and isinstance(p, Text) and (s is None or p.s == s)]


def main():
    profile = read_profile()
    S = {}
    for k in ("d1", "d2", "d3", "d4"):
        S[k] = load(k, profile)
    S["d1x"] = load("d1", profile, tiet_dien_xa_go="C200x70x20x2.5")                 # explicit purlin section: no MẶC ĐỊNH
    S["d1f"] = load("d1", profile, dai_nha=7200, buoc_cot=1800)                      # bays of 18 mm: TIM NÓC and the column label do not fit -> fallback (outside, left of axis 1)
    S["d1w"] = load("d1", profile, buoc_xa_go=2200)                                  # outside 800-2000: soft warning
    work = os.path.join(OUT, "_mutations_d")
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

    def dxf_of(Dm, name, Dexp, spx):
        p = os.path.join(work, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".dxf")
        render_dxf(Dm, profile, p)
        C = verify.Checks()
        dx = verify.check_dxf(C, Dexp, spx, profile, p, do_fc=False)
        return failed(C), dx, p

    # ---- positive controls
    for k, (sp_, D_) in S.items():
        expect(f"control_primitives_{k}", not prim_check(D_, sp_), f"không đạt: {sorted(prim_check(D_, sp_))}")
        f_, _, _ = dxf_of(D_, "ctl_" + k, D_, sp_)
        expect(f"control_dxf_{k}", not f_, f"không đạt: {sorted(f_)}")
    sp1, D1 = S["d1"]
    sp2, D2 = S["d2"]
    sp3, D3 = S["d3"]
    sp4, D4 = S["d4"]
    expect("control_sheets_d1_A3_d3_A2_d4_A1", (D1.sheet, D3.sheet, D4.sheet) == ("A3", "A2", "A1") and D1.scale == D3.scale == D4.scale == 100, f"{D1.sheet} {D3.sheet} {D4.sheet}")
    expect("control_default_marker_only_when_defaulted", D1.by_tag("note_purlin")[0].s.endswith("(MẶC ĐỊNH)") and "MẶC ĐỊNH" not in S["d1x"][1].by_tag("note_purlin")[0].s, "dấu MẶC ĐỊNH")

    cat = []

    def add(name, key, fn, prim_ids, dxf_ids=None):
        cat.append((name, key, fn, prim_ids, dxf_ids))

    # ---------------------------------------------------------------- purlins
    for dy, tag in ((1.0, "1mm"), (0.5, "0.5mm_near_miss")):
        add(f"purlin_interior_up_{tag}", "d1", lambda D, dy=dy: shift(D, purlins(D)[2], 0.0, dy), {"1.34"}, {"2.22"})
        add(f"purlin_ridge_up_{tag}", "d1", lambda D, dy=dy: shift(D, purlins(D)[5], 0.0, dy), {"1.34"}, {"2.22"})
        add(f"purlin_one_roof_interior_up_{tag}", "d2", lambda D, dy=dy: shift(D, purlins(D)[4], 0.0, dy), {"1.34"}, {"2.22"})
        add(f"purlin_rounded_spacing_up_{tag}", "d3", lambda D, dy=dy: shift(D, purlins(D)[7], 0.0, dy), {"1.34"}, {"2.22"})
    add("purlin_eave_A_deleted", "d1", lambda D: D.prims.remove(purlins(D)[0]), {"1.34"}, {"2.22"})
    add("purlin_eave_B_deleted", "d1", lambda D: D.prims.remove(purlins(D)[-1]), {"1.34"}, {"2.22"})
    add("purlin_interior_deleted", "d1", lambda D: D.prims.remove(purlins(D)[3]), {"1.34", "1.35"}, {"2.22"})
    add("purlin_ridge_deleted", "d1", lambda D: D.prims.remove(purlins(D)[5]), {"1.34", "1.35"}, {"2.22"})
    add("purlin_one_roof_top_deleted", "d2", lambda D: D.prims.remove(purlins(D)[-1]), {"1.34"}, {"2.22"})
    add("purlin_duplicated", "d1", lambda D: D.prims.append(copy.deepcopy(purlins(D)[2])), {"1.34"}, {"2.22"})
    add("purlin_ridge_drawn_twice_one_per_roof", "d1", lambda D: D.prims.append(copy.deepcopy(purlins(D)[5])), {"1.34"}, {"2.22"})
    add("purlin_extra_line_at_wrong_y_600mm", "d1", lambda D: (D.prims.append(copy.deepcopy(purlins(D)[2])), shift(D, D.prims[-1], 0.0, 600.0)), {"1.34"}, {"2.22"})

    def short_end(D, dx):
        p = purlins(D)[2]
        p.p2 = (p.p2[0] - dx / D.scale, p.p2[1])
    add("purlin_right_end_0.5mm_short_near_miss", "d1", lambda D: short_end(D, 0.5), {"1.34"}, {"2.22"})
    add("purlin_right_end_1000mm_short", "d1", lambda D: short_end(D, 1000.0), {"1.34"}, {"2.22"})

    def long_left(D):
        p = purlins(D)[2]
        p.p1 = (p.p1[0] - 0.5 / D.scale, p.p1[1])
    add("purlin_left_end_0.5mm_long_near_miss", "d1", long_left, {"1.34"}, {"2.22"})

    def tilt(D):
        p = purlins(D)[2]
        p.p2 = (p.p2[0], p.p2[1] + 0.5 / D.scale)
    add("purlin_tilted_0.5mm_over_the_length", "d1", tilt, {"1.34"}, {"2.22"})

    def half_length(D):
        p = purlins(D)[3]
        p.p2 = ((p.p1[0] + p.p2[0]) / 2, p.p2[1])
    add("purlin_half_length", "d1", half_length, {"1.34"}, {"2.22"})
    add("purlin_on_layer_NET-MANH", "d1", lambda D: setattr(purlins(D)[2], "layer", "NET-MANH"), {"1.34"}, {"2.22"})
    add("purlin_on_layer_TRUC", "d1", lambda D: setattr(purlins(D)[1], "layer", "TRUC"), {"1.34"}, {"2.22"})
    add("purlin_tag_changed_on_layer_XA-GO", "d1", lambda D: setattr(purlins(D)[2], "tag", "other"), {"1.34"})
    add("other_line_on_layer_XA-GO", "d1", lambda D: setattr(by_tag(D, "axis_h")[0], "layer", "XA-GO"), {"1.34", "1.36"}, {"2.22"})
    add("purlin_spacing_uneven_50mm", "d1", lambda D: shift(D, purlins(D)[3], 0.0, 50.0), {"1.34", "1.35"}, {"2.22"})
    add("purlin_spacing_uneven_roof_two_d3", "d3", lambda D: shift(D, purlins(D)[-3], 0.0, -40.0), {"1.34", "1.35"}, {"2.22"})

    # ---------------------------------------------------------------- dimensions
    def chain_short(D, d):
        p = dim_lines(D, True)[1]
        p.p2 = (p.p2[0], p.p2[1] - d / D.scale)
    add("chain_segment_1mm_short", "d1", lambda D: chain_short(D, 1.0), {"1.37"}, {"2.23"})
    add("chain_segment_0.5mm_short_near_miss", "d1", lambda D: chain_short(D, 0.5), {"1.37"}, {"2.23"})
    add("chain_segment_deleted", "d1", lambda D: D.prims.remove(dim_lines(D, True)[2]), {"1.37"}, {"2.23"})

    def chain_label(D, old, new, tag="dim_chain_text", rot=90.0):
        [t for t in text_by(D, tag) if t.s == old and t.rot == rot][0].s = new
    add("chain_label_1200_to_1210", "d1", lambda D: chain_label(D, "1200", "1210"), {"1.37"}, {"2.23"})
    add("chain_label_rounding_1091_to_1090", "d3", lambda D: chain_label(D, "1091", "1090"), {"1.37"}, {"2.23"})
    add("chain_label_rounding_1091_to_1090.9", "d3", lambda D: chain_label(D, "1091", "1090.9"), {"1.37"}, {"2.23"})
    add("chain_label_deleted", "d1", lambda D: D.prims.remove([t for t in text_by(D, "dim_chain_text") if t.rot == 90.0][0]), {"1.37"}, {"2.23"})
    add("span_label_12000_to_12100", "d1", lambda D: chain_label(D, "12000", "12100", "dim_overall_text"), {"1.37"}, {"2.23"})

    def span_short(D):
        p = dim_lines(D, True, "dim_overall_line")[0]
        p.p2 = (p.p2[0], p.p2[1] - 1.0 / D.scale)
    add("span_line_1mm_short", "d1", span_short, {"1.37"}, {"2.23"})
    add("chain_dimension_on_layer_NET-MANH", "d1", lambda D: setattr(dim_lines(D, True)[0], "layer", "NET-MANH"), {"1.37"}, {"2.23"})
    add("chain_tick_deleted", "d1", lambda D: D.prims.remove([p for p in D.prims if p.tag == "dim_chain_tick"][0]), {"1.37"})
    add("chain_extension_line_deleted", "d1", lambda D: D.prims.remove(by_tag(D, "dim_chain_ext")[2]), {"1.37"})
    add("chain_extension_line_duplicated", "d1", lambda D: D.prims.append(copy.deepcopy(by_tag(D, "dim_chain_ext")[2])), {"1.37"})
    add("chain_extension_line_moved_1mm", "d1", lambda D: shift(D, by_tag(D, "dim_chain_ext")[2], 0.0, 1.0), {"1.37"})
    add("span_extension_line_at_B_moved_1mm", "d1", lambda D: shift(D, [p for p in by_tag(D, "dim_ext_custom") if real_y(D, p) > 1000][0], 0.0, 1.0), {"1.37"}, {"2.23"})
    add("span_extension_line_at_B_deleted", "d1", lambda D: D.prims.remove([p for p in by_tag(D, "dim_ext_custom") if real_y(D, p) > 1000][0]), {"1.37"})
    add("span_extension_line_one_roof_starts_late", "d2", lambda D: setattr([p for p in by_tag(D, "dim_ext_custom") if real_y(D, p) > 1000][0], "p1", (D.origin[0] + 100.0, [p for p in by_tag(D, "dim_ext_custom") if real_y(D, p) > 1000][0].p1[1])), {"1.37"})

    def chain_x(D):
        for p in D.prims:
            if p.tag.startswith("dim_chain_") and isinstance(p, Line) and abs(p.p1[0] - p.p2[0]) < 1e-9 and p.p1[0] > D.origin[0] + 100:
                shift(D, p, 2.0 * D.scale, 0.0)
    add("chain_line_moved_2mm_sideways", "d1", chain_x, {"1.37"})
    add("bottom_chain_label_6000_to_6100", "d1", lambda D: chain_label(D, "6000", "6100", rot=0.0), {"1.37"}, {"2.23"})

    def del_overall(D):
        D.prims.remove(dim_lines(D, False, "dim_overall_line")[0])
    add("bottom_overall_dimension_line_deleted", "d1", del_overall, {"1.37"}, {"2.23"})
    add("dimension_text_wrong_value_in_D.dims", "d1", lambda D: setattr(D.dims[-1], "value", D.dims[-1].value + 1.0), {"1.37"})

    # ---------------------------------------------------------------- notes, ridge label, title
    def note(D, tag):
        return text_by(D, tag)[0]
    add("note_purlin_section_changed", "d1", lambda D: setattr(note(D, "note_purlin"), "s", "XÀ GỒ C150x50x20x2.5 (MẶC ĐỊNH)"), {"1.38"}, {"2.24"})
    add("note_purlin_default_marker_removed", "d1", lambda D: setattr(note(D, "note_purlin"), "s", "XÀ GỒ C150x50x20x2.0"), {"1.38"}, {"2.24"})
    add("note_purlin_default_marker_added_when_given_by_user", "d1x", lambda D: setattr(note(D, "note_purlin"), "s", note(D, "note_purlin").s + " (MẶC ĐỊNH)"), {"1.38"}, {"2.24"})
    add("note_purlin_default_marker_misspelt", "d1", lambda D: setattr(note(D, "note_purlin"), "s", "XÀ GỒ C150x50x20x2.0 (MAC DINH)"), {"1.38"}, {"2.24"})
    add("note_count_12_to_13", "d1", lambda D: setattr(note(D, "note_count"), "s", "SỐ LƯỢNG: 2 x 6 = 13 XÀ GỒ (2 MÁI)"), {"1.38", "1.42"}, {"2.24"})
    add("note_count_one_roof_instead_of_two", "d1", lambda D: setattr(note(D, "note_count"), "s", "SỐ LƯỢNG: 6 XÀ GỒ (1 MÁI, DỐC LÊN TRỤC B)"), {"1.38"}, {"2.24"})
    add("note_real_spacing_1213,4_to_1213,5", "d1", lambda D: setattr(note(D, "note_real"), "s", note(D, "note_real").s.replace("1213,4", "1213,5")), {"1.38"}, {"2.24"})
    add("note_real_spacing_wrong_max", "d1", lambda D: setattr(note(D, "note_real"), "s", note(D, "note_real").s.replace("1500", "1600")), {"1.38"}, {"2.24"})
    add("note_projected_spacing_changed_d3", "d3", lambda D: setattr(note(D, "note_proj"), "s", note(D, "note_proj").s.replace("1090,9", "1091,0")), {"1.38", "1.42"}, {"2.24"})
    add("note_projected_slope_changed", "d1", lambda D: setattr(note(D, "note_proj"), "s", note(D, "note_proj").s.replace("15%", "16%")), {"1.38"}, {"2.24"})
    add("note_column_section_changed", "d1", lambda D: setattr(note(D, "col_note"), "s", "TẤT CẢ CỘT: H300x150x6x9"), {"1.38"}, {"2.24"})
    add("note_deleted", "d1", lambda D: D.prims.remove(note(D, "note_real")), {"1.38"}, {"2.24"})
    add("note_duplicated", "d1", lambda D: D.prims.append(copy.deepcopy(note(D, "note_count"))), {"1.38"}, {"2.24"})
    add("note_off_centre_5mm_paper", "d1", lambda D: setattr(note(D, "note_count"), "pos", (note(D, "note_count").pos[0] + 5.0, note(D, "note_count").pos[1])), {"1.38"})
    add("note_wrong_height_2.0", "d1", lambda D: setattr(note(D, "note_count"), "h", 2.0), {"1.38"})
    add("note_on_layer_NET-MANH", "d1", lambda D: setattr(note(D, "note_count"), "layer", "NET-MANH"), {"1.38"}, {"2.24"})
    add("notes_overlapping", "d1", lambda D: setattr(note(D, "note_real"), "pos", (note(D, "note_real").pos[0], note(D, "note_count").pos[1] - 1.0)), {"1.38"})
    add("ridge_label_deleted", "d1", lambda D: D.prims.remove(note(D, "ridge_label")), {"1.38"}, {"2.24"})
    add("ridge_label_text_changed_to_the_old_long_text", "d1", lambda D: setattr(note(D, "ridge_label"), "s", "TIM NÓC (HAI XÀ GỒ NÓC TRÙNG NHAU)"), {"1.38"}, {"2.24"})
    add("ridge_label_moved_3mm_paper", "d1", lambda D: setattr(note(D, "ridge_label"), "pos", (note(D, "ridge_label").pos[0], note(D, "ridge_label").pos[1] + 3.0)), {"1.38"})
    add("ridge_label_present_with_one_roof", "d2", lambda D: D.prims.append(Text(layer="CHU", tag="ridge_label", s="TIM NÓC", pos=(100.0, 100.0), h=2.5, halign="right")), {"1.38"}, {"2.24"})
    add("title_text_changed", "d1", lambda D: setattr(note(D, "title"), "s", "MẶT BẰNG XÀ GỒ"), {"1.39"})
    add("title_not_bold", "d1", lambda D: setattr(note(D, "title"), "bold", False), {"1.39"})
    add("scale_note_1:50_on_1:100", "d1", lambda D: setattr(note(D, "scale_note"), "s", "TỶ LỆ 1:50"), {"1.39"}, {"2.24"})
    add("title_block_number_KC-03", "d1", lambda D: D.fields.__setitem__("cell4", "KC-03"), {"1.39"})
    add("title_block_scale_cell_1:50", "d1", lambda D: D.fields.__setitem__("cell7", "1:50"), {"1.39"})

    # ---------------------------------------------------------------- text boxes against the vertical axes (1.45 / 2.26 / 3.10) and the placement rule of the labels among the axes
    def axis_x(D, k):
        return sorted(by_tag(D, "axis_v"), key=lambda p: p.p1[0])[k].p1[0]

    def ridge_old_place(D):                       # the old layout: the long text, right-aligned 3 mm before the last axis -> axis 5 crosses it
        r = note(D, "ridge_label")
        r.s, r.halign, r.pos = "TIM NÓC (HAI XÀ GỒ NÓC TRÙNG NHAU)", "right", (axis_x(D, -1) - 3.0, r.pos[1])
    add("ridge_label_old_long_text_at_the_old_place_crosses_axis_5", "d1", ridge_old_place, {"1.45", "1.38"}, {"2.26"})
    add("ridge_label_short_text_centred_on_axis_4", "d1", lambda D: setattr(note(D, "ridge_label"), "pos", (axis_x(D, 3), note(D, "ridge_label").pos[1])), {"1.45", "1.38"}, {"2.26"})
    add("ridge_label_short_text_right_aligned_on_axis_6", "d1", lambda D: (setattr(note(D, "ridge_label"), "halign", "right"), setattr(note(D, "ridge_label"), "pos", (axis_x(D, -1) + 1.0, note(D, "ridge_label").pos[1]))), {"1.45", "1.38"}, {"2.26"})
    add("ridge_label_in_first_bay_instead_of_the_right_most", "d1", lambda D: setattr(note(D, "ridge_label"), "pos", ((axis_x(D, 0) + axis_x(D, 1)) / 2, note(D, "ridge_label").pos[1])), {"1.38"})
    add("ridge_label_left_aligned_in_the_bay_not_centred", "d1", lambda D: (setattr(note(D, "ridge_label"), "halign", "left"), setattr(note(D, "ridge_label"), "pos", (axis_x(D, -2) + 2.0, note(D, "ridge_label").pos[1]))), {"1.38"})
    add("column_label_straddling_axis_2", "d1", lambda D: setattr(note(D, "col_label"), "pos", (axis_x(D, 1) - 5.0, note(D, "col_label").pos[1])), {"1.45", "1.38"}, {"2.26"})
    add("note_pulled_up_across_the_plan_crosses_every_axis", "d1", lambda D: setattr(note(D, "note_count"), "pos", (note(D, "note_count").pos[0], note(D, "ridge_label").pos[1] + 12.0)), {"1.45", "1.38"}, {"2.26"})
    add("bottom_dimension_label_moved_up_onto_axis_3", "d1", lambda D: [setattr(t, "pos", (axis_x(D, 2), D.origin[1] - 2.0)) for t in text_by(D, "dim_chain_text", "6000")[:1]], {"1.45", "1.37"}, {"2.26"})
    add("bubble_label_dragged_down_onto_the_axis_line", "d1", lambda D: shift(D, [t for t in text_by(D, "bubble_text", "3")][0], 0.0, -8.0 * D.scale), {"1.45", "1.36"}, {"2.26"})
    add("narrow_bays_ridge_label_forced_into_the_right_most_bay", "d1f", lambda D: setattr(note(D, "ridge_label"), "pos", ((axis_x(D, -2) + axis_x(D, -1)) / 2, note(D, "ridge_label").pos[1])) or setattr(note(D, "ridge_label"), "halign", "center"), {"1.38"})
    add("narrow_bays_ridge_label_centred_on_an_axis", "d1f", lambda D: setattr(note(D, "ridge_label"), "pos", (axis_x(D, 2), note(D, "ridge_label").pos[1])) or setattr(note(D, "ridge_label"), "halign", "center"), {"1.45", "1.38"}, {"2.26"})
    add("narrow_bays_ridge_label_not_moved_outside", "d1f", lambda D: setattr(note(D, "ridge_label"), "halign", "center"), {"1.38"})
    add("narrow_bays_column_label_kept_in_the_first_bay_crosses_axis_2", "d1f", lambda D: (setattr(note(D, "col_label"), "halign", "left"), setattr(note(D, "col_label"), "pos", (axis_x(D, 0) + 2.625, D.origin[1] + 1.2))), {"1.45", "1.38"}, {"2.26"})
    add("narrow_bays_ridge_label_moved_3mm_further_left", "d1f", lambda D: setattr(note(D, "ridge_label"), "pos", (note(D, "ridge_label").pos[0] - 3.0, note(D, "ridge_label").pos[1])), {"1.38"})

    # ---------------------------------------------------------------- grid + columns
    add("column_deleted", "d1", lambda D: D.prims.remove(by_tag(D, "column")[3]), {"1.36"}, {"2.25"})
    add("column_wider_1mm", "d1", lambda D: setattr(by_tag(D, "column")[3], "p1", (by_tag(D, "column")[3].p1[0] + 1.0 / D.scale, by_tag(D, "column")[3].p1[1])), {"1.36"}, {"2.25"})
    add("column_moved_1mm", "d1", lambda D: shift(D, by_tag(D, "column")[4], 1.0, 0.0), {"1.36"}, {"2.25"})
    add("column_moved_0.5mm_near_miss", "d1", lambda D: shift(D, by_tag(D, "column")[4], 0.0, 0.5), {"1.36"}, {"2.25"})
    add("axis_vertical_moved_1mm", "d1", lambda D: shift(D, by_tag(D, "axis_v")[2], 1.0, 0.0), {"1.36"}, {"2.25"})
    add("axis_vertical_deleted", "d1", lambda D: D.prims.remove(by_tag(D, "axis_v")[2]), {"1.36"}, {"2.25"})
    add("axis_horizontal_B_moved_1mm", "d1", lambda D: shift(D, by_tag(D, "axis_h")[1], 0.0, 1.0), {"1.36"}, {"2.25"})
    add("axis_on_layer_NET-MANH", "d1", lambda D: setattr(by_tag(D, "axis_v")[0], "layer", "NET-MANH"), {"1.36"}, {"2.25"})
    add("bubble_label_wrong", "d1", lambda D: setattr(by_tag(D, "bubble_text")[0], "s", "9"), {"1.36"}, {"2.25"})
    add("bubble_moved_1mm", "d1", lambda D: shift(D, by_tag(D, "bubble")[0], 1.0, 0.0), {"1.36"})

    # ---------------------------------------------------------------- layout, policy, warnings, arithmetic, defaults
    def move_all(D):
        for p in D.prims:
            if p.sheet:
                continue
            for k in ("p1", "p2", "p0", "c", "pos"):
                if hasattr(p, k):
                    q = getattr(p, k)
                    setattr(p, k, (q[0] + 300.0, q[1]))
        D.origin = (D.origin[0] + 300.0, D.origin[1])
    add("drawing_moved_onto_title_block_and_out_of_frame", "d1", move_all, {"1.40"})
    add("d1_labelled_A2_although_A3_fits", "d1", lambda D: setattr(D, "sheet", "A2"), {"1.44", "1.40"})
    add("d3_labelled_A3_although_it_needs_A2", "d3", lambda D: setattr(D, "sheet", "A3"), {"1.44", "1.40"})
    add("d4_labelled_A2_although_it_needs_A1", "d4", lambda D: setattr(D, "sheet", "A2"), {"1.44", "1.40"})
    add("text_rotated_30_degrees", "d1", lambda D: setattr(note(D, "note_count"), "rot", 30.0), {"1.40"})
    add("warning_missing_for_non_integer_projected_spacing", "d3", lambda D: D.info.__setitem__("warnings", []), {"1.41"})
    add("warning_missing_outside_800_2000", "d1w", lambda D: D.info.__setitem__("warnings", []), {"1.41"})
    add("warning_spurious_inside_800_2000", "d1", lambda D: D.info.__setitem__("warnings", ["buoc_xa_go = 1500 mm nằm ngoài khoảng 800-2000 mm (TCVN)"]), {"1.41"})
    add("report_wrong_number_of_spans", "d1", lambda D: D.info.__setitem__("n_spans", 6), {"1.41"})
    add("report_wrong_number_of_purlins", "d1", lambda D: D.info.__setitem__("n_purlins", 11), {"1.41"})
    add("false_arithmetic_text", "d1", lambda D: setattr(note(D, "note_proj"), "s", "CHIẾU: 5 x 1200 = 6001 MM; ĐỘ DỐC MÁI: 15% (8,5°)"), {"1.42", "1.38"}, {"2.12", "2.24"})
    add("defaults_not_reported", "d1", lambda D: D.info.__setitem__("defaults", []), {"1.43"})
    add("defaults_reported_although_given", "d1x", lambda D: D.info.__setitem__("defaults", ["tiet_dien_xa_go"]), {"1.43"})

    # ---------------------------------------------------------------- run: primitives
    for name, key, fn, prim_ids, dxf_ids in cat:
        sp_, D_ = S[key]
        need(prim_ids, prim_check(mut(fn, D_), sp_), f"prim_{name}")
    # spec disagreeing with the (correct) drawing
    need({"1.34", "1.35"}, prim_check(D1, dict(sp1, buoc_xa_go=1000)), "spec_buoc_xa_go_1000_vs_drawing_for_1500")
    need({"1.34", "1.38"}, prim_check(D1, dict(sp1, so_mai=1)), "spec_one_roof_vs_two_roof_drawing")
    need({"1.34", "1.38"}, prim_check(D2, dict(sp2, so_mai=2)), "spec_two_roofs_vs_one_roof_drawing")
    need({"1.38"}, prim_check(D1, dict(sp1, do_doc_mai=25.0)), "spec_slope_25_vs_drawing_15_slope_note")
    need({"1.34", "1.36", "1.37"}, prim_check(D1, dict(sp1, nhip=12002.0)), "spec_nhip_12002_vs_drawing_12000")
    need({"1.35"}, prim_check(D1, dict(sp1, n=6)), "spec_n_6_vs_5")
    need({"1.36", "1.34"}, prim_check(D1, dict(sp1, dai_nha=36000.0)), "spec_dai_nha_36000_vs_drawing_30000")
    need({"1.36"}, prim_check(D1, dict(sp1, section=dict(sp1["section"], h=260.0))), "spec_column_depth_260_vs_250")
    need({"1.38"}, prim_check(D1, dict(sp1, xa_go_mac_dinh=False)), "spec_says_purlin_section_given_but_drawing_prints_MẶC_ĐỊNH")
    need({"1.44"}, prim_check(D1, dict(sp1, scale=50)), "spec_scale_1:50_vs_drawing_1:100")
    need({"1.44"}, prim_check(D1, dict(sp1, kho_giay="A2")), "spec_sheet_A2_vs_drawing_A3")
    need({"1.41"}, prim_check(D1, dict(sp1, buoc_xa_go=2200)), "spec_buoc_xa_go_2200_needs_soft_warning")
    # an explicit scale that leaves no room for the spacing labels is refused by the builder, with the reason
    try:
        load("d1", profile, ty_le="1:200")
        expect("builder_refuses_1:200_when_spacing_labels_do_not_fit", False, "không báo lỗi")
    except SpecError as e:
        expect("builder_refuses_1:200_when_spacing_labels_do_not_fit", "nhãn khoảng cách xà gồ" in " ".join(e.errors) and "Không vừa" in " ".join(e.errors), " ".join(e.errors)[:120])

    # ---------------------------------------------------------------- run: DXF (the mutated list is the source AND the expectation -> only 2.22-2.25 can notice)
    for name, key, fn, prim_ids, dxf_ids in cat:
        if not dxf_ids:
            continue
        sp_, D_ = S[key]
        f_, _, _ = dxf_of(mut(fn, D_), "m_" + name, mut(fn, D_), sp_)
        need(dxf_ids, f_, f"dxf_{name}")

    # ---- DXF byte edits (the DXF is corrupted; expectation = the correct drawing)
    base = os.path.join(work, "ctl_d1.dxf")
    src = open(base, "rb").read()

    def run_dxf_bytes(name, data, ids):
        p = os.path.join(work, name + ".dxf")
        open(p, "wb").write(data)
        C = verify.Checks()
        verify.check_dxf(C, D1, sp1, profile, p, do_fc=False)
        need(ids, failed(C), name)

    def sub_all(old, new, name, ids):
        d = src.replace(old, new)
        if d == src:
            d = src.replace(old.replace(b"\r\n", b"\n"), new.replace(b"\r\n", b"\n"))
        assert d != src, f"mutation {name}: pattern not found"
        run_dxf_bytes(name, d, ids)

    sub_all(b"1213,4", b"1213,5", "dxf_bytes_real_spacing_1213,4_to_1213,5", {"2.24", "2.6"})
    sub_all("(MẶC ĐỊNH)".encode(), "(MAC DINH)".encode(), "dxf_bytes_default_marker", {"2.24", "2.6"})
    sub_all("TIM NÓC".encode(), "TIM NOC".encode(), "dxf_bytes_ridge_label", {"2.24", "2.6"})
    sub_all(b"C150x50x20x2.0", b"C150x50x20x2.5", "dxf_bytes_purlin_section", {"2.24", "2.6"})
    sub_all(b"2 x 6 = 12", b"2 x 6 = 13", "dxf_bytes_count_12_to_13", {"2.24", "2.12"})
    sub_all("MẶT BẰNG XÀ GỒ MÁI".encode(), "MẶT BẰNG XÀ GỒ".encode(), "dxf_bytes_view_title", {"2.24", "2.6"})
    sub_all(b"\r\n  8\r\nXA-GO\r\n", b"\r\n  8\r\nCHU\r\n", "dxf_bytes_all_purlins_to_layer_CHU", {"2.22", "2.5"})

    text = src.decode("utf-8")
    lines = text.splitlines(keepends=True)

    def edit_entity(name, layer, etype, code, pred, newval, ids):
        """edit the first group (code) of the first entity (type, layer) whose value satisfies pred"""
        out, cur, done = [], {}, False
        for k, ln in enumerate(lines):
            if k % 2 == 0:
                cur_code = ln.strip()
            else:
                v = ln.strip()
                if cur_code == "0":
                    cur = {"type": v, "layer": None}
                elif cur_code == "8" and cur:
                    cur["layer"] = v
                    if not done and code == 8 and cur.get("type") == etype and v == layer and pred(v):
                        ln = ln.replace(v, newval)
                        done = True
                elif not done and cur_code == str(code) and cur.get("type") == etype and cur.get("layer") == layer and pred(v):
                    ln = ln.replace(v, newval)
                    done = True
            out.append(ln)
        assert done, f"mutation {name}: value not found"
        run_dxf_bytes(name, "".join(out).encode("utf-8"), ids)

    dx0 = read_dxf(base)
    pl = sorted((e for e in dx0["ents"] if e["type"] == "LINE" and e["layer"] == "XA-GO"), key=lambda e: float(e["rec"][20][0]))
    y2 = pl[2]["rec"][20][0]
    edit_entity("dxf_value_purlin_start_y_+0.5mm", "XA-GO", "LINE", 20, lambda v: v == y2, f"{float(y2) + 0.5:.6f}", {"2.22", "2.9"})
    x_end = pl[3]["rec"][11][0]
    edit_entity("dxf_value_purlin_end_x_-0.5mm", "XA-GO", "LINE", 11, lambda v: v == x_end, f"{float(x_end) - 0.5:.6f}", {"2.22", "2.9"})
    edit_entity("dxf_value_ridge_purlin_end_y_+1mm", "XA-GO", "LINE", 21, lambda v: abs(float(v) - 6000.0) < 1e-6, "6001.000000", {"2.22", "2.9"})
    vdim = [e for e in dx0["ents"] if e["type"] == "LINE" and e["layer"] == "KICH-THUOC" and abs(float(e["rec"][10][0]) - float(e["rec"][11][0])) < 1e-6 and float(e["rec"][10][0]) > 30200]
    yv = sorted(vdim, key=lambda e: (float(e["rec"][10][0]), float(e["rec"][20][0])))[1]["rec"][21][0]
    edit_entity("dxf_value_chain_dimension_end_+0.5mm", "KICH-THUOC", "LINE", 21, lambda v: v == yv, f"{float(yv) + 0.5:.6f}", {"2.23", "2.9"})
    ridge = [e for e in dx0["ents"] if e["type"] == "TEXT" and e["layer"] == "CHU" and (e["rec"].get(1) or [""])[0].startswith("TIM N")][0]["rec"]
    edit_entity("dxf_value_ridge_label_start_x_moved_onto_axis_4", "CHU", "TEXT", 10, lambda v: v == ridge[10][0], "18000.000000", {"2.26", "2.9"})
    edit_entity("dxf_value_ridge_label_start_x_moved_across_axis_6_by_5mm", "CHU", "TEXT", 10, lambda v: v == ridge[10][0], f"{30000.0 - 5.0 * 100:.6f}", {"2.26", "2.9"})
    edit_entity("dxf_value_purlin_layer_changed_to_NET-MANH", "XA-GO", "LINE", 8, lambda v: v == "XA-GO", "NET-MANH", {"2.22", "2.5"})

    # ---- DWG read-back check 3.9: through a real ODA round trip (control) and on a corrupted DXF read back
    try:
        dwg = os.path.join(work, "ctl_d1.dwg")
        info = oda.dxf_to_dwg(base, dwg, "ACAD2018")
        back = os.path.join(work, "ctl_d1_back.dxf")
        r = oda.dwg_to_dxf(dwg, back, "ACAD2018") if info.get("ok") else {"ok": False}
        if r.get("ok"):
            C = verify.Checks()
            verify_d.check_dwg_d(C, D1, sp1, read_dxf(back))
            expect("control_dwg_round_trip_through_ODA", not failed(C), f"không đạt: {sorted(failed(C))}")
            Dm = mut(lambda D: D.prims.remove(purlins(D)[2]), D1)
            _, _, pbad = dxf_of(Dm, "dwg_purlin_deleted", Dm, sp1)
            C = verify.Checks()
            verify_d.check_dwg_d(C, D1, sp1, read_dxf(pbad))
            need({"3.9"}, failed(C), "dwg_read_back_purlin_deleted")
            Dm = mut(lambda D: shift(D, purlins(D)[2], 0.0, 0.5), D1)
            _, _, pbad = dxf_of(Dm, "dwg_purlin_moved", Dm, sp1)
            C = verify.Checks()
            verify_d.check_dwg_d(C, D1, sp1, read_dxf(pbad))
            need({"3.9"}, failed(C), "dwg_read_back_purlin_moved_0.5mm")
            Dm = mut(lambda D: setattr(note(D, "ridge_label"), "pos", (axis_x(D, 3), note(D, "ridge_label").pos[1])), D1)
            _, _, pbad = dxf_of(Dm, "dwg_ridge_label_on_axis_4", Dm, sp1)
            C = verify.Checks()
            verify_d.check_dwg_d(C, D1, sp1, read_dxf(pbad))
            need({"3.10"}, failed(C), "dwg_read_back_ridge_label_straddles_axis_4")
            Dm = mut(lambda D: D.prims.remove(dim_lines(D, True)[1]), D1)
            _, _, pbad = dxf_of(Dm, "dwg_chain_segment_deleted", Dm, sp1)
            C = verify.Checks()
            verify_d.check_dwg_d(C, D1, sp1, read_dxf(pbad))
            need({"3.9"}, failed(C), "dwg_read_back_chain_segment_deleted")
        else:
            expect("dwg_round_trip_skipped", False, f"ODA không chạy được: {info}")
    except oda.OdaError as e:
        expect("dwg_round_trip_skipped", False, f"ODA: {e}")

    # ---- PDF cross-checks: the correct PDFs against mutated expectations
    pdfs = {k: os.path.join(OUT, NAMES[k], NAMES[k] + ".pdf") for k in NAMES}
    if all(os.path.isfile(p) for p in pdfs.values()):
        dxs = {}
        for k in NAMES:
            sp_, D_ = S[k]
            C0 = verify.Checks()
            dxs[k] = verify.check_dxf(C0, D_, sp_, profile, os.path.join(work, f"ctl_{k}.dxf"), do_fc=False)
            C = verify.Checks()
            verify.check_pdf(C, D_, sp_, dxs[k], pdfs[k], "png-not-checked", profile)
            expect(f"control_pdf_{k}", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")
        C = verify.Checks()
        verify.check_pdf(C, D3, sp3, dxs["d1"], pdfs["d1"], None, profile)
        need({"5.8", "5.1"}, failed(C), "pdf_of_other_drawing_d3_expectation_vs_d1_pdf")
        C = verify.Checks()
        verify.check_pdf(C, D1, sp1, dxs["d3"], pdfs["d1"], None, profile)
        need({"5.8"}, failed(C), "pdf_d1_checked_against_the_dxf_of_d3")

        def pdf_case(name, fn, ids, key="d1"):
            sp_, D_ = S[key]
            C = verify.Checks()
            verify.check_pdf(C, mut(fn, D_), sp_, dxs[key], pdfs[key], None, profile)
            need(ids, failed(C), name)

        pdf_case("pdf_purlin_expected_0.3mm_paper_off", lambda D: shift(D, purlins(D)[2], 0.0, 0.3 * D.scale), {"5.1"})
        pdf_case("pdf_purlin_expected_deleted_in_drawing", lambda D: D.prims.remove(purlins(D)[3]), {"5.8", "5.2", "5.1"})
        pdf_case("pdf_purlin_expected_dashed_layer", lambda D: setattr(purlins(D)[2], "layer", "NET-KHUAT"), {"5.1"})
        pdf_case("pdf_extra_purlin_expected", lambda D: D.prims.append(copy.deepcopy(purlins(D)[2])), {"5.8", "5.1", "5.3"})

        def chain_len(D):
            p = dim_lines(D, True)[0]
            p.p2 = (p.p2[0], p.p2[1] + 0.3)
        pdf_case("pdf_chain_dimension_expected_0.3mm_paper_longer", chain_len, {"5.1", "5.6"})
        pdf_case("pdf_d3_purlin_expected_0.3mm_paper_off", lambda D: shift(D, purlins(D)[4], 0.0, 0.3 * D.scale), {"5.1"}, "d3")
        pdf_case("pdf_d2_one_roof_top_purlin_expected_missing", lambda D: D.prims.remove(purlins(D)[-1]), {"5.8", "5.1"}, "d2")
        Dm = copy.deepcopy(D4)
        Dm.sheet = "A2"
        C = verify.Checks()
        verify.check_pdf(C, Dm, sp4, dxs["d4"], pdfs["d4"], None, profile)
        expect("pdf_a1_drawing_checked_as_A2", {"4.1", "4.2"} <= failed(C), f"không đạt: {sorted(failed(C))}")
    else:
        expect("pdf_cases_skipped", False, "thiếu PDF của d1/d2/d3/d4 (chạy make_drawing cho các ví dụ d trước)")

    ok_all = True
    for name, ok, detail in results:
        ok_all &= bool(ok)
        print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail if not ok else ''}".rstrip(": ").rstrip())
    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f"mutation tests D: {n_ok}/{len(results)} đúng;", "OK" if ok_all else "FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
