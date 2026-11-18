"""Sheet policy tests (no FreeCAD): A3 first, A2 then A1 only when A3 does not hold the drawing at 1:200 (type B) / 1:100 (type C) or finer;
explicit kho_giay / ty_le restrict the search; nothing fits -> Vietnamese error. Also the measured sheet geometry (frame, title block).

    python scripts/drawing/test_sheets.py       (needs TCVN_PROFILE)
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import build_b  # noqa: E402
import build_c  # noqa: E402
import spec_b  # noqa: E402
import spec_c  # noqa: E402
from tcvn import SHEETS, read_profile  # noqa: E402

EX = os.path.join(HERE, "examples")
profile = read_profile()
results = []


def load(name):
    return spec_b.load_spec(os.path.join(EX, name + ".json"))


def case(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {e}"
    results.append((name, ok, detail))


def build(kind, **over):
    raw = load("b2_12000x30000" if kind == "B" else "c3_24000x8000_1mai")
    raw.update(over)
    if kind == "B":
        return build_b.build(spec_b.validate(raw), profile)
    return build_c.build(spec_c.validate(raw), profile)


def expect_sheet(kind, sheet, scale, **over):
    def f():
        D = build(kind, **over)
        return (D.sheet, D.scale) == (sheet, scale), f"{D.sheet} 1:{D.scale}"
    return f


def expect_error(kind, text, **over):
    def f():
        try:
            build(kind, **over)
        except spec_b.SpecError as e:
            m = " ".join(e.errors)
            return text in m, m[:160]
        return False, "không có lỗi"
    return f


case("geometry_A2_frame_564x400_tb_180x65", lambda: ((SHEETS["A2"].frame_w, SHEETS["A2"].frame_h, SHEETS["A2"].tb_w, SHEETS["A2"].tb_h) == (564, 400, 180, 65), repr(SHEETS["A2"])))
case("geometry_A1_frame_811x574_tb_180x65", lambda: ((SHEETS["A1"].frame_w, SHEETS["A1"].frame_h, SHEETS["A1"].tb_w, SHEETS["A1"].tb_h) == (811, 574, 180, 65), repr(SHEETS["A1"])))
case("geometry_title_block_at_frame_bottom_right", lambda: (all(s.tb_x1 == s.x1 and s.tb_y0 == s.y0 for s in SHEETS.values()), "ok"))
case("B_small_stays_A3_1:100", expect_sheet("B", "A3", 100))
case("B_36000_stays_A3_1:200", expect_sheet("B", "A3", 200, nhip=16500, dai_nha=36000))
case("B_24000x72000_goes_A2_1:200", expect_sheet("B", "A2", 200, nhip=24000, dai_nha=72000))
case("B_36000x120000_goes_A1_1:200", expect_sheet("B", "A1", 200, nhip=36000, dai_nha=120000))
case("B_36000x192000_no_sheet_at_1:200_uses_A2_1:500", expect_sheet("B", "A2", 500, nhip=36000, dai_nha=192000))
case("B_forced_A3_for_72000_is_an_error", expect_error("B", "Không vừa", nhip=24000, dai_nha=72000, kho_giay="A3", ty_le="1:200"))
case("B_forced_A1_uses_the_largest_scale_that_fits_1:50", expect_sheet("B", "A1", 50, kho_giay="A1"))
case("B_everything_too_big_error", expect_error("B", "Không vừa", nhip=100000, dai_nha=1200000, buoc_cot=60000))
def _bad_kho():
    try:
        spec_b.validate(dict(load("b2_12000x30000"), kho_giay="A0"))
    except spec_b.SpecError as e:
        return "kho_giay" in " ".join(e.errors), " ".join(e.errors)[:120]
    return False, "không có lỗi"


case("B_bad_kho_giay_message", _bad_kho)
case("C_small_stays_A3_1:100", expect_sheet("C", "A3", 100))
case("C_60000x12000_goes_A1_1:100", expect_sheet("C", "A1", 100, nhip=60000, cao_cot=12000))
case("C_36000_goes_A2_or_A1_not_A3", lambda: (build("C", nhip=36000, cao_cot=9000).sheet in ("A2", "A1"), build("C", nhip=36000, cao_cot=9000).sheet))
case("C_forced_A1_uses_the_largest_scale_that_fits_1:50", expect_sheet("C", "A1", 50, kho_giay="A1"))
case("C_600000_error_lists_every_sheet", expect_error("C", "A1 ở", nhip=600000, cao_cot=12000))

ok_all = True
for name, ok, detail in results:
    ok_all &= bool(ok)
    print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail}")
print(f"sheet tests: {sum(1 for _, o, _ in results if o)}/{len(results)} đúng;", "OK" if ok_all else "FAILED")
sys.exit(0 if ok_all else 1)
