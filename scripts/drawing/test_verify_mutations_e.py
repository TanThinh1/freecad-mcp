"""Mutation tests for drawing type E (ve_tu_do): corrupt primitives / DXF / DWG read-back / PDF expectations on purpose and require verify.py + verify_e.py to FAIL the matching check;
plus positive controls (the unmutated data passes every check that runs). Every rule of verify_e (1.50-1.62, 2.30-2.34, 3.20-3.23, 5.20) has at least 2 mutants.

    python scripts\\drawing\\test_verify_mutations_e.py     (needs out\\e1_phong_don_gian and out\\e2_nha_cap4 from make_drawing for the PDF cases; TCVN_PROFILE set)
"""
from __future__ import annotations

import copy
import os
import re
import shutil
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import oda  # noqa: E402
import verify  # noqa: E402
import verify_e  # noqa: E402
from build_e import build  # noqa: E402
from dxf_render import render_dxf  # noqa: E402
from primitives import Circle, Line, Rect, Text  # noqa: E402
from readers import read_dxf  # noqa: E402
from spec_b import load_spec  # noqa: E402
from spec_e import validate  # noqa: E402
from tcvn import read_profile  # noqa: E402

OUT = os.environ.get("TEST_OUT", os.path.join(os.getcwd(), "out"))
EX = os.path.join(HERE, "examples")


def load(name, profile, edit=None):
    raw = load_spec(os.path.join(EX, name + ".json"))
    if edit:
        edit(raw)
    sp = validate(raw)
    return sp, build(sp, profile)


def failed(C):
    return {c["id"] for c in C.items if c["ok"] is False}


def prim_check(D, sp):
    C = verify.Checks()
    verify_e.check_primitives_e(C, D, sp)
    return failed(C)


def tagged(D, prefix, cls=None):
    return [p for p in D.prims if p.tag.startswith(prefix) and (cls is None or isinstance(p, cls))]


def shift(D, p, dx, dy):
    """move by (dx, dy) REAL mm"""
    for k in ("p1", "p2", "p0", "c", "pos"):
        if hasattr(p, k):
            q = getattr(p, k)
            setattr(p, k, (q[0] + dx / D.scale, q[1] + dy / D.scale))


def elems(sp, t):
    return [e for e in sp["views"][0]["elems"] if e["t"] == t]


def raw_variant(raw):
    el = [e for e in raw["hinh"][0]["phan_tu"] if e["loai"] not in ("noi_that_co_ban", "phong", "ghi_chu", "mui_ten_bac")]
    el += [dict(loai="duong", tu=[600, 2200], den=[1600, 2200], lop="NET-KHUAT"), dict(loai="polyline", diem=[[600, 2600], [1600, 2600], [1600, 3000]], kin=False, lop="NET-MANH"),
           dict(loai="cung", id="C1", tam=[2500, 2300], ban_kinh=300, goc_dau=0, goc_cuoi=120, lop="NET-MANH"), dict(loai="tron", id="C2", tam=[3200, 2300], ban_kinh=200, lop="NET-MANH"),
           dict(loai="chu", chu="GHI", vi_tri=[2000, 1500], cao=2.5),
           dict(loai="kich_thuoc", id="K7", kieu="ban_kinh", phan_tu="C2", goc=45), dict(loai="kich_thuoc", id="K8", kieu="duong_kinh", phan_tu="C2", goc=200),
           dict(loai="kich_thuoc", id="K9", kieu="song_song", tham_chieu=[[600, 2200], [1600, 3000]], phia="trai", khoang=8), dict(loai="kich_thuoc", id="K10", kieu="goc", dinh=[600, 1000], tia1=[1600, 1000], tia2=[600, 1800])]
    raw["hinh"][0]["phan_tu"] = el
    raw["ty_le"] = "1:20"
    raw["kho_giay"] = "A2"


def warn_variant(raw):
    for e in raw["hinh"][0]["phan_tu"]:
        if e["loai"] == "cua_di":
            e["rong"] = 600
        if e["loai"] == "tuong":
            e["day"] = 600
    raw["hinh"][0]["phan_tu"] = [e for e in raw["hinh"][0]["phan_tu"] if e["loai"] != "phong"]


def x_variant(raw):
    el = raw["hinh"][0]["phan_tu"]
    el += [dict(loai="lan_can", id="LC", tu=[7200, 0], dai=1500, cao=1000, buoc=500), dict(loai="bac_thang_don_gian", id="BT", tu=[9600, 0], so_bac=4, cao_bac=170, rong_bac=270),
           dict(loai="dau_cat", id="DC", ten="1", tu=[-600, -1300], den=[1000, -1300], nhin="tren"), dict(loai="tuyen_gio", id="G1", ten="1", x=3400, tu_y=-300, den_y=3400),
           dict(loai="cot_mc", id="CM", hcn=[10800, 0, 11020, 3000]), dict(loai="mong_don", id="MG", goc=[11300, -1200], dai_lot=1000, day_lot=100, dai_mong=800, day_mong=200, dai_co=300, cao_co=900)]


def warn2_variant(raw):
    raw["hinh"][0]["phan_tu"] += [dict(loai="lan_can", id="LC", tu=[7200, 0], dai=1500, cao=800, buoc=500), dict(loai="bac_thang_don_gian", id="BT", tu=[9600, 0], so_bac=4, cao_bac=200, rong_bac=250)]


def main():
    profile = read_profile()
    S = {"e1": load("e1_phong_don_gian", profile), "e2": load("e2_nha_cap4", profile), "e1r": load("e1_phong_don_gian", profile, raw_variant), "e1w": load("e1_phong_don_gian", profile, warn_variant),
         "e4": load("e4_mat_dung_nha_cap4", profile), "e5": load("e5_mat_cat_1_1", profile), "e5x": load("e5_mat_cat_1_1", profile, x_variant), "e7": load("e7_chi_tiet_mong", profile),
         "e5w": load("e5_mat_cat_1_1", profile, warn2_variant)}
    work = os.path.join(OUT, "_mutations_e")
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

    for k, (sp_, D_) in S.items():
        expect(f"control_primitives_{k}", not prim_check(D_, sp_), f"không đạt: {sorted(prim_check(D_, sp_))}")
        f_, _, _ = dxf_of(D_, "ctl_" + k, D_, sp_)
        expect(f"control_dxf_{k}", not f_, f"không đạt: {sorted(f_)}")
    sp1, D1 = S["e1"]
    sp2, D2 = S["e2"]
    spr, Dr = S["e1r"]
    spw, Dw = S["e1w"]

    cat = []

    def add(name, key, fn, prim_ids, dxf_ids=None):
        cat.append((name, key, fn, prim_ids, dxf_ids))

    L = lambda D, pre: tagged(D, pre, Line)
    T = lambda D, pre: tagged(D, pre, Text)
    H = lambda D, k=0: L(D, "hatch:")[k]
    # ---- phase 2: 1.63 hatch
    add("hatch_line_deleted", "e5", lambda D: D.prims.remove(H(D, 3)), {"1.63"}, {"2.36"})
    add("hatch_line_moved_0.5mm_near_miss", "e5", lambda D: shift(D, H(D, 5), 0.5, 0.0), {"1.63"}, {"2.36"})
    add("hatch_extra_line_inside_the_rectangle", "e7", lambda D: D.prims.append(Line(layer="MAT-CAT", tag="hatch:NEN1:0:0", p1=(H(D, 0).p1[0], H(D, 0).p1[1]), p2=(H(D, 0).p1[0] + 0.2, H(D, 0).p1[1] + 0.1))), {"1.63", "1.68"}, {"2.36"})
    add("hatch_on_wrong_layer", "e4", lambda D: setattr(H(D, 2), "layer", "NET-MANH"), {"1.63"}, {"2.36"})
    add("hatch_family_shifted_half_a_spacing", "e5", lambda D: [shift(D, h, 0.0, 1.0 * D.scale) for h in L(D, "hatch:TUONG:1")], {"1.63"}, {"2.36"})
    add("hatch_for_the_wrong_material_double_density", "e7", lambda D: [D.prims.remove(h) for h in L(D, "hatch:M1:1")[::2]], {"1.63"}, {"2.36"})
    # ---- 1.64 layers / structural rectangles
    add("layer_rectangle_moved_1mm", "e5", lambda D: shift(D, tagged(D, "lop:NEN:1", Rect)[0], 0.0, 1.0), {"1.64", "1.67"}, {"2.30"})
    add("layer_rectangle_thinner_1mm", "e5", lambda D: setattr(tagged(D, "lop:TUONG:1", Rect)[0], "p1", (tagged(D, "lop:TUONG:1", Rect)[0].p1[0] - 1.0 / D.scale, tagged(D, "lop:TUONG:1", Rect)[0].p1[1])), {"1.64", "1.67"}, {"2.30"})
    add("slab_rectangle_deleted", "e5", lambda D: D.prims.remove(tagged(D, "kc:SAN", Rect)[0]), {"1.64"}, {"2.30"})
    add("foundation_block_moved_1mm", "e7", lambda D: shift(D, tagged(D, "mong:M1:mong", Rect)[0], 1.0, 0.0), {"1.64"}, {"2.30"})
    add("rebar_circle_moved_1mm", "e7", lambda D: shift(D, tagged(D, "cot:CT:thep", Circle)[1], 1.0, 0.0), {"1.64"}, {"2.31"})
    add("stirrup_rectangle_resized", "e7", lambda D: setattr(tagged(D, "cot:CT:dai", Rect)[0], "p1", (tagged(D, "cot:CT:dai", Rect)[0].p1[0] + 1.0 / D.scale, tagged(D, "cot:CT:dai", Rect)[0].p1[1])), {"1.64"}, {"2.31"})
    add("rebar_circle_deleted", "e7", lambda D: D.prims.remove(tagged(D, "cot:CT:thep", Circle)[0]), {"1.64"}, {"2.31"})
    # ---- 1.65 elevation / section items
    add("roof_line_moved_1mm", "e4", lambda D: shift(D, L(D, "mai:M1:top")[0], 0.0, 1.0), {"1.65"}, {"2.30"})
    add("roof_end_line_deleted", "e5", lambda D: D.prims.remove(L(D, "mai:MAI:dau")[0]), {"1.65"}, {"2.30"})
    add("door_leaf_rectangle_deleted", "e4", lambda D: D.prims.remove(tagged(D, "cd:CD1:canh", Rect)[0]), {"1.65"}, {"2.31"})
    add("door_swing_line_deleted", "e4", lambda D: D.prims.remove(L(D, "cd:CD1:gach")[0]), {"1.65"}, {"2.31"})
    add("window_mullion_moved_1mm", "e4", lambda D: shift(D, L(D, "cd:CD2:gach")[0], 1.0, 0.0), {"1.65"}, {"2.31"})
    add("railing_post_deleted", "e5x", lambda D: D.prims.remove(L(D, "lc:LC:cot")[1]), {"1.65"}, {"2.31"})
    add("railing_rail_moved_1mm", "e5x", lambda D: shift(D, L(D, "lc:LC:thanh")[0], 0.0, 1.0), {"1.65"}, {"2.31"})
    add("stair_segment_deleted", "e5x", lambda D: D.prims.remove(L(D, "bt:BT")[2]), {"1.65"}, {"2.30"})
    add("stair_segment_moved_1mm", "e5x", lambda D: shift(D, L(D, "bt:BT")[4], 1.0, 0.0), {"1.65"}, {"2.30"})
    # ---- 1.66 markers
    add("level_symbol_line_moved_1mm", "e4", lambda D: shift(D, L(D, "lv:")[1], 0.0, 1.0), {"1.66", "1.69"}, {"2.31"})
    add("level_bar_deleted", "e5", lambda D: D.prims.remove(L(D, "lv:")[2]), {"1.66", "1.69"}, {"2.31"})
    add("leader_line_moved_1mm", "e5", lambda D: shift(D, L(D, "leader:")[0], 0.0, 1.0), {"1.66"}, {"2.31"})
    add("leader_tick_deleted", "e7", lambda D: D.prims.remove([p for p in L(D, "leader:") if p.tag.endswith(":tick")][0]), {"1.66"}, {"2.31"})
    add("section_marker_arm_deleted", "e5x", lambda D: D.prims.remove(L(D, "cut_arm:DC")[0]), {"1.66"}, {"2.30"})
    add("section_marker_line_shortened", "e5x", lambda D: setattr(L(D, "cut:DC")[0], "p2", (L(D, "cut:DC")[0].p2[0] - 1.0 / D.scale, L(D, "cut:DC")[0].p2[1])), {"1.66"}, {"2.30"})
    add("wind_axis_moved_1mm", "e4", lambda D: shift(D, L(D, "gio_line:G1")[0], 1.0, 0.0), {"1.66"}, {"2.31"})
    add("wind_bubble_deleted", "e4", lambda D: D.prims.remove(tagged(D, "gio_bubble:G2", Circle)[0]), {"1.66"}, {"2.31"})
    # ---- 1.67 layer thickness (measured), 1.68 hatch containment, 1.69 level text
    add("layers_not_contiguous_gap_1mm", "e5", lambda D: shift(D, tagged(D, "lop:NEN:2", Rect)[0], 0.0, 1.0), {"1.67"}, {"2.30"})
    add("layer_thickness_off_0.5mm", "e5", lambda D: setattr(tagged(D, "lop:NEN:0", Rect)[0], "p1", (tagged(D, "lop:NEN:0", Rect)[0].p1[0], tagged(D, "lop:NEN:0", Rect)[0].p1[1] + 0.5 / D.scale)), {"1.67"}, {"2.30"})
    add("hatch_line_sticks_out_of_its_rectangle", "e5", lambda D: setattr(H(D, 4), "p2", (H(D, 4).p2[0] + 2.0, H(D, 4).p2[1] + 2.0)), {"1.68", "1.63"}, {"2.36"})
    add("hatch_line_tilted", "e7", lambda D: setattr(H(D, 6), "p2", (H(D, 6).p2[0], H(D, 6).p2[1] + 0.8)), {"1.68", "1.63"}, {"2.36"})
    add("level_text_wrong_value", "e4", lambda D: setattr(T(D, "lv_text:")[1], "s", "+3.400"), {"1.69", "1.55"}, {"2.32"})
    add("level_text_sign_dropped", "e5", lambda D: setattr(T(D, "lv_text:")[0], "s", "0.300"), {"1.69", "1.55"}, {"2.32"})
    add("level_symbol_moved_100mm_text_unchanged", "e4", lambda D: [shift(D, p, 0.0, 100.0) for p in L(D, "lv:") if p.tag == "lv:11"], {"1.69", "1.66"}, {"2.31"})
    add("wrong_warning_missing_for_low_railing_and_odd_stair", "e5w", lambda D: D.info.__setitem__("warnings", []), {"1.61"})
    # ---- 1.50 axes + bubbles
    add("axis_vertical_moved_1mm", "e1", lambda D: shift(D, L(D, "axis_v")[0], 1.0, 0.0), {"1.50"}, {"2.31"})
    add("axis_vertical_moved_0.5mm_near_miss", "e1", lambda D: shift(D, L(D, "axis_v")[1], 0.5, 0.0), {"1.50"}, {"2.31"})
    add("axis_horizontal_deleted", "e1", lambda D: D.prims.remove(L(D, "axis_h")[0]), {"1.50"}, {"2.31"})
    add("axis_on_wrong_layer", "e2", lambda D: setattr(L(D, "axis_v")[0], "layer", "NET-MANH"), {"1.50"}, {"2.31"})
    add("bubble_moved_1mm", "e2", lambda D: shift(D, tagged(D, "bubble", Circle)[0], 1.0, 0.0), {"1.50"}, {"2.31"})
    add("bubble_deleted", "e1", lambda D: D.prims.remove(tagged(D, "bubble", Circle)[0]), {"1.50"}, {"2.31"})
    # ---- 1.51 walls
    add("wall_edge_moved_1mm", "e1", lambda D: shift(D, L(D, "wall_edge")[3], 0.0, 1.0), {"1.51"}, {"2.30"})
    add("wall_edge_moved_0.5mm_near_miss", "e2", lambda D: shift(D, L(D, "wall_edge")[5], 0.5, 0.0), {"1.51"}, {"2.30"})
    add("wall_edge_deleted", "e2", lambda D: D.prims.remove(L(D, "wall_edge")[7]), {"1.51"}, {"2.30"})
    add("wall_edge_extra_line", "e1", lambda D: D.prims.append(Line(layer="NET-CHINH", tag="wall_edge", p1=(100.0, 100.0), p2=(120.0, 100.0))), {"1.51"}, {"2.30"})
    add("wall_edge_shortened_1mm", "e1", lambda D: setattr(L(D, "wall_edge")[2], "p2", (L(D, "wall_edge")[2].p2[0] - 1.0 / D.scale, L(D, "wall_edge")[2].p2[1]) if abs(L(D, "wall_edge")[2].p1[1] - L(D, "wall_edge")[2].p2[1]) < 1e-9 else (L(D, "wall_edge")[2].p2[0], L(D, "wall_edge")[2].p2[1] - 1.0 / D.scale)), {"1.51"}, {"2.30"})
    add("wall_edge_on_thin_layer", "e1", lambda D: setattr(L(D, "wall_edge")[1], "layer", "NET-MANH"), {"1.51"}, {"2.30", "2.31"})
    add("wall_not_cut_at_the_door_bridged", "e1", lambda D: D.prims.append(Line(layer="NET-CHINH", tag="wall_edge", p1=L(D, "door_frame")[0].p1, p2=L(D, "door_frame")[0].p2)), {"1.51"}, {"2.30"})
    # ---- 1.52 openings
    add("door_leaf_moved_1mm", "e1", lambda D: shift(D, L(D, "door_leaf")[0], 1.0, 0.0), {"1.52"}, {"2.31"})
    add("door_leaf_deleted", "e2", lambda D: D.prims.remove(L(D, "door_leaf")[0]), {"1.52"}, {"2.31"})
    add("door_arc_segment_deleted", "e1", lambda D: D.prims.remove(L(D, "door_arc")[5]), {"1.52"}, {"2.31"})
    add("door_arc_point_moved_0.5mm", "e1", lambda D: shift(D, L(D, "door_arc")[10], 0.0, 0.5), {"1.52"}, {"2.31"})
    add("door_frame_line_deleted", "e2", lambda D: D.prims.remove(L(D, "door_frame")[0]), {"1.52"}, {"2.31"})
    add("window_line_moved_1mm", "e1", lambda D: shift(D, L(D, "win_line")[0], 0.0, 1.0), {"1.52"}, {"2.31"})
    add("window_line_deleted_3line_window", "e2", lambda D: D.prims.remove(L(D, "win_line")[3]), {"1.52"}, {"2.31"})
    add("door_swing_flipped_leaf_mirrored", "e1", lambda D: setattr(L(D, "door_leaf")[0], "p2", (2 * L(D, "door_leaf")[0].p1[0] - L(D, "door_leaf")[0].p2[0], 2 * L(D, "door_leaf")[0].p1[1] - L(D, "door_leaf")[0].p2[1])), {"1.52"}, {"2.31"})
    # ---- 1.53 furniture, raw, north arrow
    add("furniture_rect_moved_1mm", "e1", lambda D: shift(D, tagged(D, "furn:", Rect)[0], 1.0, 0.0), {"1.53"}, {"2.31"})
    add("furniture_rect_deleted", "e2", lambda D: D.prims.remove(tagged(D, "furn:", Rect)[0]), {"1.53"}, {"2.31"})
    add("furniture_rect_resized_1mm", "e1", lambda D: setattr(tagged(D, "furn:", Rect)[1], "p1", (tagged(D, "furn:", Rect)[1].p1[0] + 1.0 / D.scale, tagged(D, "furn:", Rect)[1].p1[1])), {"1.53"}, {"2.31"})
    add("north_circle_moved_1mm", "e1", lambda D: shift(D, tagged(D, "bac_vong", Circle)[0], 1.0, 0.0), {"1.53"}, {"2.31"})
    add("north_triangle_line_deleted", "e2", lambda D: D.prims.remove(L(D, "bac_tam_giac")[0]), {"1.53"}, {"2.31"})
    add("raw_line_moved_1mm", "e1r", lambda D: shift(D, L(D, "raw_duong")[0], 0.0, 1.0), {"1.53"}, {"2.31"})
    add("raw_polyline_segment_deleted", "e1r", lambda D: D.prims.remove(L(D, "raw_polyline")[0]), {"1.53"}, {"2.31"})
    add("raw_arc_segment_moved_0.5mm", "e1r", lambda D: shift(D, L(D, "raw_cung")[3], 0.5, 0.0), {"1.53"}, {"2.31"})
    add("raw_circle_resized", "e1r", lambda D: setattr(tagged(D, "raw_tron", Circle)[0], "r", tagged(D, "raw_tron", Circle)[0].r * 1.01), {"1.53"}, {"2.31"})
    add("raw_line_on_wrong_layer", "e1r", lambda D: setattr(L(D, "raw_duong")[0], "layer", "NET-MANH"), {"1.53"}, {"2.31"})
    # ---- 1.54 dimensions
    add("dim_line_0.5mm_short_near_miss", "e1", lambda D: setattr(L(D, "dim:K1:line")[0], "p2", (L(D, "dim:K1:line")[0].p2[0] - 0.5 / D.scale, L(D, "dim:K1:line")[0].p2[1])), {"1.54"}, {"2.31"})
    add("dim_line_moved_1mm", "e2", lambda D: shift(D, L(D, "dim:K2:line")[0], 0.0, -1.0), {"1.54"}, {"2.31"})
    add("dim_tick_deleted", "e2", lambda D: D.prims.remove(L(D, "dim:K2:tick")[0]), {"1.54"}, {"2.31"})
    add("dim_extension_line_moved_1mm", "e2", lambda D: shift(D, L(D, "dim:K3:ext")[0], 1.0, 0.0), {"1.54"}, {"2.31"})
    add("dim_extension_line_deleted", "e1", lambda D: D.prims.remove(L(D, "dim:K2:ext")[0]), {"1.54"}, {"2.31"})
    add("dim_extension_duplicated", "e2", lambda D: D.prims.append(copy.deepcopy(L(D, "dim:K1:ext")[0])), {"1.54", "1.58"}, {"2.31", "2.34"})
    add("dim_segment_deleted_chain", "e2", lambda D: D.prims.remove(L(D, "dim:K1:line")[2]), {"1.54"}, {"2.31"})
    add("dim_on_wrong_layer", "e2", lambda D: setattr(L(D, "dim:K1:line")[0], "layer", "NET-MANH"), {"1.54"}, {"2.31"})
    add("dim_tier_two_moved_to_tier_one_position", "e2", lambda D: shift(D, L(D, "dim:K2:line")[0], 0.0, 7.0 * D.scale), {"1.54"}, {"2.31"})
    add("radius_dimension_line_rotated", "e1r", lambda D: setattr(L(D, "dim:K7:line")[0], "p2", (L(D, "dim:K7:line")[0].p2[0] + 1.0, L(D, "dim:K7:line")[0].p2[1])), {"1.54"}, {"2.31"})
    add("aligned_dimension_offset_changed", "e1r", lambda D: shift(D, L(D, "dim:K9:line")[0], 1.0, 0.0), {"1.54"}, {"2.31"})
    add("angle_dimension_arc_point_moved", "e1r", lambda D: shift(D, L(D, "dim:K10:line")[2], 0.5, 0.0), {"1.54"}, {"2.31"})
    # ---- 1.55 texts (strings)
    add("room_name_changed", "e2", lambda D: setattr(T(D, "room_name:P1")[0], "s", "PHÒNG ĂN"), {"1.55"}, {"2.32"})
    add("room_area_11,04_to_11,05", "e2", lambda D: setattr(T(D, "room_area:P3")[0], "s", "DT: 11,05 m²"), {"1.55"}, {"2.32"})
    add("room_area_rounded_wrong_24,41_to_24,4", "e2", lambda D: setattr(T(D, "room_area:P1")[0], "s", "DT: 24,4 m²"), {"1.55"}, {"2.32"})
    add("furniture_label_changed", "e2", lambda D: setattr(T(D, "furn_label:G1")[0], "s", "SOFA"), {"1.55"}, {"2.32"})
    add("note_line_changed", "e2", lambda D: setattr(T(D, "note:")[1], "s", "- TƯỜNG GẠCH DÀY 200 MM, TRÁT VỮA HAI MẶT."), {"1.55"}, {"2.32"})
    add("title_changed", "e1", lambda D: setattr(T(D, "title")[0], "s", "MẶT BẰNG"), {"1.55"}, {"2.32"})
    add("scale_note_wrong", "e1", lambda D: setattr(T(D, "scale_note")[0], "s", "TỶ LỆ 1:100"), {"1.55"}, {"2.32"})
    add("bubble_text_changed", "e2", lambda D: setattr(T(D, "bubble_text")[0], "s", "9"), {"1.55"}, {"2.32"})
    add("dimension_label_wrong_value", "e2", lambda D: setattr(T(D, "dim:K3:text")[0], "s", "9100"), {"1.55"}, {"2.32"})
    add("dimension_label_rounding_wrong", "e1r", lambda D: setattr(T(D, "dim:K9:text")[0], "s", "1118"), {"1.55"}, {"2.32"})
    add("text_deleted", "e2", lambda D: D.prims.remove(T(D, "furn_label:B1")[0]), {"1.55"}, {"2.32"})
    add("text_extra", "e1", lambda D: D.prims.append(Text(layer="CHU", tag="note:9:0", s="THỪA", pos=(D.origin[0] - 25.0, D.origin[1] + 80.0), h=2.5)), {"1.55"}, {"2.32"})
    add("text_on_wrong_layer", "e1", lambda D: setattr(T(D, "room_name:P1")[0], "layer", "NET-CHINH"), {"1.55", "1.58"}, {"2.32"})
    # ---- 1.56 / 1.57 text vs lines and texts
    wall_pt = lambda D: L(D, "wall_edge")[0].p1
    add("room_name_dragged_onto_a_wall_line", "e1", lambda D: setattr(T(D, "room_name:P1")[0], "pos", ((L(D, "wall_edge")[2].p1[0] + L(D, "wall_edge")[2].p2[0]) / 2, (L(D, "wall_edge")[2].p1[1] + L(D, "wall_edge")[2].p2[1]) / 2 - 1.0)), {"1.56"}, {"2.33"})
    add("note_dragged_onto_the_axis", "e1", lambda D: setattr(T(D, "note:")[0], "pos", (L(D, "axis_v")[0].p1[0] - 5.0, D.origin[1] + 30.0)), {"1.56"}, {"2.33"})
    add("furniture_label_across_furniture_edge", "e1", lambda D: setattr(T(D, "furn_label:G1")[0], "pos", (tagged(D, "furn:G1", Rect)[0].p0[0] - 3.0, (tagged(D, "furn:G1", Rect)[0].p0[1] + tagged(D, "furn:G1", Rect)[0].p1[1]) / 2)), {"1.56"}, {"2.33"})
    add("dimension_label_on_another_dimension_line", "e2", lambda D: setattr(T(D, "dim:K1:text")[0], "pos", (T(D, "dim:K1:text")[0].pos[0], L(D, "dim:K2:line")[0].p1[1] - 0.3)), {"1.56"}, None)
    add("room_label_moved_out_of_its_room", "e2", lambda D: [shift(D, T(D, "room_name:P3")[0], 0.0, -4500.0), shift(D, T(D, "room_area:P3")[0], 0.0, -4500.0)], {"1.56"}, {"2.35"})
    add("room_label_swapped_into_the_neighbour_room", "e2", lambda D: [shift(D, T(D, "room_name:P1")[0], 0.0, 4000.0), shift(D, T(D, "room_area:P1")[0], 0.0, 4000.0)], {"1.56"}, {"2.35"})
    add("text_over_circle_outline", "e1r", lambda D: setattr(T(D, "raw_chu")[0], "pos", (tagged(D, "raw_tron", Circle)[0].c[0] + tagged(D, "raw_tron", Circle)[0].r, tagged(D, "raw_tron", Circle)[0].c[1])), {"1.56"}, {"2.33"})
    add("two_texts_overlapping", "e2", lambda D: setattr(T(D, "note:")[1], "pos", (T(D, "note:")[0].pos[0] + 1.0, T(D, "note:")[0].pos[1] - 0.5)), {"1.57", "1.56"}, None)
    add("room_name_over_room_area", "e2", lambda D: setattr(T(D, "room_area:P1")[0], "pos", (T(D, "room_name:P1")[0].pos[0], T(D, "room_name:P1")[0].pos[1] + 0.5)), {"1.57"}, None)
    # ---- 1.58 layers, duplicates, counts
    add("line_on_a_layer_outside_the_profile", "e1", lambda D: setattr(L(D, "axis_h")[0], "layer", "XYZ"), {"1.58"}, None)
    add("line_duplicated", "e2", lambda D: D.prims.append(copy.deepcopy(L(D, "wall_edge")[3])), {"1.58", "1.51"}, {"2.34", "2.30"})
    add("zero_length_line", "e1", lambda D: D.prims.append(Line(layer="NET-MANH", tag="raw_duong:9", p1=(100.0, 100.0), p2=(100.0, 100.0))), {"1.58"}, {"2.34"})
    add("report_element_count_wrong", "e1", lambda D: D.info.__setitem__("n_elements", 99), {"1.58"})
    add("report_element_count_zero", "e2", lambda D: D.info.__setitem__("n_elements", 0), {"1.58"})
    # ---- 1.59 / 1.60 layout and policy
    def move_all(D):
        for p in D.prims:
            if p.sheet:
                continue
            for k in ("p1", "p2", "p0", "c", "pos"):
                if hasattr(p, k):
                    q = getattr(p, k)
                    setattr(p, k, (q[0] + 300.0, q[1]))
        D.origin = (D.origin[0] + 300.0, D.origin[1])
    add("drawing_moved_onto_the_title_block_and_out_of_the_frame", "e1", move_all, {"1.59"})
    add("one_line_outside_the_frame", "e2", lambda D: D.prims.append(Line(layer="NET-MANH", tag="raw_duong:9", p1=(5.0, 5.0), p2=(8.0, 5.0))), {"1.59", "1.51"}, None)
    add("e2_labelled_A3_although_it_needs_A2", "e2", lambda D: setattr(D, "sheet", "A3"), {"1.60", "1.59"})
    add("e1_labelled_A2_although_A3_fits", "e1", lambda D: setattr(D, "sheet", "A2"), {"1.60"})
    # ---- 1.61 warnings, 1.62 arithmetic
    add("warnings_missing_for_narrow_door_and_thick_wall", "e1w", lambda D: D.info.__setitem__("warnings", []), {"1.61"})
    add("spurious_warning_when_door_is_wide_enough", "e1", lambda D: D.info.__setitem__("warnings", ["phan_tu[2]: cửa đi rộng 900 mm, hẹp hơn 700 mm (kinh nghiệm thực tế, KHÔNG phải điều khoản TCVN)"]), {"1.61"})
    add("false_arithmetic_note", "e2", lambda D: setattr(T(D, "note:")[1], "s", "- 2 x 6 = 13 CỬA"), {"1.62", "1.55"}, {"2.12"})

    for name, key, fn, prim_ids, dxf_ids in cat:
        sp_, D_ = S[key]
        need(prim_ids, prim_check(mut(fn, D_), sp_), f"prim_{name}")
    # spec disagreeing with the correct drawing
    def sp_edit(sp, fn):
        s2 = copy.deepcopy(sp)
        fn(s2)
        return s2
    need({"1.51", "1.52", "1.54"}, prim_check(D1, sp_edit(sp1, lambda s: elems(s, "tuong")[0].update(day=s["views"][0]["elems"][1]["day"] + 10))), "spec_wall_thickness_230_vs_drawing_220")
    need({"1.52", "1.51"}, prim_check(D1, sp_edit(sp1, lambda s: elems(s, "cua_di")[0].update(vi_tri=elems(s, "cua_di")[0]["vi_tri"] + 100))), "spec_door_position_moved_100")
    need({"1.52"}, prim_check(D1, sp_edit(sp1, lambda s: elems(s, "cua_di")[0].update(mo_ve="phai"))), "spec_door_swing_side_flipped")
    need({"1.55"}, prim_check(D1, sp_edit(sp1, lambda s: elems(s, "phong")[0].update(ten="PHÒNG KHÁCH"))), "spec_room_name_vs_drawing")
    need({"1.53", "1.55"}, prim_check(D1, sp_edit(sp1, lambda s: elems(s, "noi_that_co_ban")[0].update(kieu="ban"))), "spec_furniture_kind_vs_drawing")
    need({"1.54", "1.55"}, prim_check(D2, sp_edit(sp2, lambda s: elems(s, "kich_thuoc")[0].update(tham_chieu=["truc:1", "S1:dau", "S1:cuoi", "D1:dau", "D1:cuoi", "truc:2"]))), "spec_dimension_reference_changed")
    need({"1.60"}, prim_check(D1, sp_edit(sp1, lambda s: s.update(scale=100))), "spec_scale_1:100_vs_drawing_1:50")
    sp5, D5 = S["e5"]
    need({"1.67", "1.64", "1.63"}, prim_check(D5, sp_edit(sp5, lambda s: s["views"][0]["elems"][0]["layers"].__setitem__(0, ("dat", Fraction(160))))), "spec_layer_150_vs_160_in_the_drawing")
    need({"1.67"}, prim_check(D5, sp_edit(sp5, lambda s: elems(s, "lop_vat_lieu")[1].update(tong_day=Fraction(240)))), "spec_total_thickness_240_vs_layers_230")
    need({"1.69"}, prim_check(D5, sp_edit(sp5, lambda s: s["views"][0].update(mo_cao=(Fraction(0), Fraction(1))))), "spec_reference_level_1.000_vs_drawn_texts")
    need({"1.64", "1.63", "1.65"}, prim_check(D5, sp_edit(sp5, lambda s: elems(s, "san")[0].update(box=(Fraction(-100), Fraction(3000), Fraction(3000), Fraction(3130))))), "spec_slab_top_3130_vs_drawing_3120")

    # ---- DXF (mutated list as source AND expectation -> only the independent checks 2.30-2.34 can notice)
    for name, key, fn, prim_ids, dxf_ids in cat:
        if not dxf_ids:
            continue
        sp_, D_ = S[key]
        f_, _, _ = dxf_of(mut(fn, D_), "m_" + name, mut(fn, D_), sp_)
        need(dxf_ids, f_, f"dxf_{name}")

    # ---- DXF byte / coordinate edits (the DXF is corrupted; expectation = the correct drawing)
    base = os.path.join(work, "ctl_e2.dxf")
    src = open(base, "rb").read()

    def run_bytes(name, data, ids):
        p = os.path.join(work, name + ".dxf")
        open(p, "wb").write(data)
        C = verify.Checks()
        verify.check_dxf(C, D2, sp2, profile, p, do_fc=False)
        need(ids, failed(C), name)

    def sub_all(old, new, name, ids):
        d = src.replace(old, new)
        assert d != src, f"mutation {name}: pattern not found"
        run_bytes(name, d, ids)

    sub_all("PHÒNG KHÁCH".encode(), "PHÒNG BẾP".encode(), "dxf_bytes_room_name", {"2.32", "2.6"})
    sub_all(b"24,41", b"24,42", "dxf_bytes_room_area", {"2.32", "2.6"})
    sub_all("GHẾ".encode(), "BÀN".encode(), "dxf_bytes_furniture_label", {"2.32", "2.6"})
    sub_all(b"\r\n  8\r\nNET-CHINH\r\n", b"\r\n  8\r\nNET-MANH\r\n", "dxf_bytes_all_walls_to_thin_layer", {"2.30", "2.5"})
    sub_all(b"\r\n  8\r\nTRUC\r\n", b"\r\n  8\r\nCHU\r\n", "dxf_bytes_axes_to_text_layer", {"2.31", "2.5"})
    text = src.decode("utf-8")
    lines = text.splitlines(keepends=True)

    def edit_entity(name, layer, etype, code, pred, newval, ids):
        out, cur, done = [], {}, False
        for k, ln in enumerate(lines):
            if k % 2 == 0:
                cc = ln.strip()
            else:
                v = ln.strip()
                if cc == "0":
                    cur = {"type": v, "layer": None}
                elif cc == "8" and cur:
                    cur["layer"] = v
                elif not done and cc == str(code) and cur.get("type") == etype and cur.get("layer") == layer and pred(v):
                    ln = ln.replace(v, newval)
                    done = True
            out.append(ln)
        assert done, f"mutation {name}: value not found"
        run_bytes(name, "".join(out).encode("utf-8"), ids)

    dx0 = read_dxf(base)
    walls = [e for e in dx0["ents"] if e["type"] == "LINE" and e["layer"] == "NET-CHINH"]
    raw_x = walls[0]["rec"][10][0]
    edit_entity("dxf_value_wall_start_x_+0.5mm", "NET-CHINH", "LINE", 10, lambda v: v == raw_x, f"{float(raw_x) + 0.5:.6f}", {"2.30", "2.9"})
    raw_y = walls[3]["rec"][21][0]
    edit_entity("dxf_value_wall_end_y_+1mm", "NET-CHINH", "LINE", 21, lambda v: v == raw_y, f"{float(raw_y) + 1.0:.6f}", {"2.30", "2.9"})
    dims = [e for e in dx0["ents"] if e["type"] == "LINE" and e["layer"] == "KICH-THUOC" and abs(float(e["rec"][20][0]) - float(e["rec"][21][0])) < 1e-9 and abs(float(e["rec"][10][0]) - float(e["rec"][11][0])) > 100]
    ry = dims[0]["rec"][11][0]
    edit_entity("dxf_value_dimension_line_end_x_+0.5mm", "KICH-THUOC", "LINE", 11, lambda v: v == ry, f"{float(ry) + 0.5:.6f}", {"2.31", "2.9"})
    door = [e for e in dx0["ents"] if e["type"] == "LINE" and e["layer"] == "NET-MANH"][0]["rec"][10][0]
    edit_entity("dxf_value_door_frame_start_x_+0.5mm", "NET-MANH", "LINE", 10, lambda v: v == door, f"{float(door) + 0.5:.6f}", {"2.31", "2.9"})

    # ---- DWG read back (ODA round trip as control; mutated DXF read back as mutants)
    try:
        dwg = os.path.join(work, "ctl_e2.dwg")
        info = oda.dxf_to_dwg(base, dwg, "ACAD2018")
        back = os.path.join(work, "ctl_e2_back.dxf")
        r = oda.dwg_to_dxf(dwg, back, "ACAD2018") if info.get("ok") else {"ok": False}
        if r.get("ok"):
            C = verify.Checks()
            verify_e.check_dwg_e(C, D2, sp2, read_dxf(back))
            expect("control_dwg_round_trip_through_ODA", not failed(C), f"không đạt: {sorted(failed(C))}")
            for nm, fn, ids in (("wall_deleted", lambda D: D.prims.remove(L(D, "wall_edge")[4]), {"3.20"}), ("wall_moved_0.5mm", lambda D: shift(D, L(D, "wall_edge")[2], 0.5, 0.0), {"3.20"}),
                                ("door_arc_segment_deleted", lambda D: D.prims.remove(L(D, "door_arc")[3]), {"3.21"}), ("dimension_line_moved_1mm", lambda D: shift(D, L(D, "dim:K1:line")[1], 0.0, 1.0), {"3.21"}),
                                ("room_name_changed", lambda D: setattr(T(D, "room_name:P2")[0], "s", "SẢNH"), {"3.22"}), ("area_changed", lambda D: setattr(T(D, "room_area:P2")[0], "s", "DT: 8,61 m²"), {"3.22"}),
                                ("note_dragged_onto_axis", lambda D: setattr(T(D, "note:")[0], "pos", (L(D, "axis_v")[0].p1[0] - 5.0, D.origin[1] + 30.0)), {"3.23"}),
                                ("room_label_out_of_room", lambda D: [shift(D, T(D, "room_name:P3")[0], 0.0, -4500.0), shift(D, T(D, "room_area:P3")[0], 0.0, -4500.0)], {"3.24"}),
                                ("room_name_onto_wall", lambda D: setattr(T(D, "room_name:P1")[0], "pos", ((L(D, "wall_edge")[2].p1[0] + L(D, "wall_edge")[2].p2[0]) / 2, (L(D, "wall_edge")[2].p1[1] + L(D, "wall_edge")[2].p2[1]) / 2 - 1.0)), {"3.23"})):
                Dm = mut(fn, D2)
                _, _, pbad = dxf_of(Dm, "dwg_" + nm, Dm, sp2)
                C = verify.Checks()
                verify_e.check_dwg_e(C, D2, sp2, read_dxf(pbad))
                need(ids, failed(C), f"dwg_read_back_{nm}")
        else:
            expect("dwg_round_trip_skipped", False, f"ODA không chạy được: {info}")
    except oda.OdaError as e:
        expect("dwg_round_trip_skipped", False, f"ODA: {e}")

    # ---- DWG read back of the phase 2 hatch (mutated DXF read back; the ODA round trip itself is the control above)
    for nm, fn in (("hatch_line_deleted", lambda D: D.prims.remove(H(D, 3))), ("hatch_line_moved_0.5mm", lambda D: shift(D, H(D, 5), 0.5, 0.0)), ("hatch_line_extra", lambda D: D.prims.append(copy.deepcopy(H(D, 2))))):
        Dm = mut(fn, D5)
        _, _, pbad = dxf_of(Dm, "dwg5_" + nm, Dm, sp5)
        C = verify.Checks()
        verify_e.check_dwg_e(C, D5, sp5, read_dxf(pbad))
        need({"3.25"}, failed(C), f"dwg_read_back_{nm}")

    # ---- PDF cross-checks
    pdf1, pdf2 = (os.path.join(OUT, n, n + ".pdf") for n in ("e1_phong_don_gian", "e2_nha_cap4"))
    if os.path.isfile(pdf1) and os.path.isfile(pdf2):
        dxs = {}
        for k, (sp_, D_, pdf_) in {"e1": (sp1, D1, pdf1), "e2": (sp2, D2, pdf2)}.items():
            C0 = verify.Checks()
            dxs[k] = verify.check_dxf(C0, D_, sp_, profile, os.path.join(work, f"ctl_{k}.dxf"), do_fc=False)
            C = verify.Checks()
            verify.check_pdf(C, D_, sp_, dxs[k], pdf_, "png-not-checked", profile)
            expect(f"control_pdf_{k}", not (failed(C) - {"4.6"}), f"không đạt: {sorted(failed(C))}")
        C = verify.Checks()
        verify.check_pdf(C, D2, sp2, dxs["e1"], pdf1, None, profile)
        need({"5.20", "5.1"}, failed(C), "pdf_of_e1_checked_against_the_expectation_of_e2")
        C = verify.Checks()
        verify.check_pdf(C, D1, sp1, dxs["e2"], pdf1, None, profile)
        need({"5.20"}, failed(C), "pdf_of_e1_checked_against_the_dxf_of_e2")

        def pdf_case(name, fn, ids, key="e2"):
            sp_, D_ = S[key]
            C = verify.Checks()
            verify.check_pdf(C, mut(fn, D_), sp_, dxs[key], {"e1": pdf1, "e2": pdf2}[key], None, profile)
            need(ids, failed(C), name)

        pdf_case("pdf_wall_edge_expected_0.3mm_paper_off", lambda D: shift(D, L(D, "wall_edge")[3], 0.0, 0.3 * D.scale), {"5.1"})
        pdf_case("pdf_door_leaf_expected_0.3mm_paper_off", lambda D: shift(D, L(D, "door_leaf")[0], 0.3 * D.scale, 0.0), {"5.1"})
        pdf_case("pdf_dimension_line_expected_0.3mm_paper_longer", lambda D: setattr(L(D, "dim:K3:line")[0], "p2", (L(D, "dim:K3:line")[0].p2[0], L(D, "dim:K3:line")[0].p2[1] + 0.3)), {"5.1"})
        pdf_case("pdf_expected_wall_edge_missing", lambda D: D.prims.remove(L(D, "wall_edge")[0]), {"5.1", "5.2", "5.3"})
        pdf_case("pdf_wall_expected_on_a_dashed_layer", lambda D: setattr(L(D, "wall_edge")[2], "layer", "NET-KHUAT"), {"5.1"})
        pdf_case("pdf_e1_axis_expected_off", lambda D: shift(D, L(D, "axis_v")[0], 0.3 * D.scale, 0.0), {"5.1"}, "e1")
    else:
        expect("pdf_cases_skipped", False, "thiếu PDF của e1 / e2 (chạy make_drawing cho các ví dụ e trước)")

    ok_all = True
    for name, ok, detail in results:
        ok_all &= bool(ok)
        print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail if not ok else ''}".rstrip(": ").rstrip())
    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f"mutation tests E: {n_ok}/{len(results)} đúng;", "OK" if ok_all else "FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
