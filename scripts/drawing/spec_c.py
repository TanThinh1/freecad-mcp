"""Spec schema + input validation for drawing type C (cross-section of a steel portal frame, one A3 sheet, one view).

Parameters (same names as type B and the autocad-tcvn tool tcvn_draw_frame): nhip (mm, axis A to axis B), cao_cot (mm, ground +-0.000 to the
intersection of the column axis and the rafter axis), do_doc_mai (roof slope in %, 0 < i <= 100, fractions allowed), so_mai (1 or 2),
tiet_dien_cot, tiet_dien_keo (H h x b x tw x tf or box), ty_le ("auto" | "1:100"...), khung_ten metadata, optional ve_truc_cau_kien (true: draw the
rafter axes as thin CENTER lines, default false) and tham_so (layout parameters).

Geometry (real mm, axis A at x = 0, axis B at x = nhip, ground y = 0):
  so_mai = 2 : eave nodes (0, cao_cot) and (nhip, cao_cot), ridge node (nhip/2, cao_cot + nhip/2 * i)
  so_mai = 1 : low eave node at axis A (0, cao_cot), high node at axis B (nhip, cao_cot + nhip * i)   <- convention of this tool
The top height is computed with exact rational arithmetic; when it is not a whole number of mm the drawing shows it rounded (half up) and the
report carries a warning that states the exact value.
"""
from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

from spec_b import DEFAULT_PARAMS, SpecError, _mm, parse_khung_ten, parse_kho, parse_params, parse_scale, parse_section, parse_ten, SECTION_ERR

DEFAULT_PARAMS_C = dict(DEFAULT_PARAMS)
DEFAULT_PARAMS_C.update(
    nen_keo_dai=15.0,         # ground line extends this far (paper mm) past the outer column edges
    cao_chu_cao_do=3.5,       # level text height
    cao_chu_so_lieu=2.5,      # section labels / slope text
    khoang_cach_nhan=2.0,     # gap between a member edge and its label (paper mm)
)


def round_half_up(v) -> int:
    """Whole millimetres, half up, exact for Fraction / int / float values (floor(v + 1/2))."""
    return math.floor(Fraction(v) + Fraction(1, 2))


def fmt_exact(fr: Fraction) -> str:
    """Exact decimal text of a rational with a finite decimal expansion (inputs are decimals, so it is finite); comma not used (report text)."""
    d = Decimal(fr.numerator) / Decimal(fr.denominator)
    s = format(d.normalize(), "f")
    return s


def level_text(mm) -> str:
    """'+6.900' - metres with 3 decimals; the value is rounded half up to whole mm first (so +6.7315 m shows as +6.732)."""
    return f"+{round_half_up(mm) / 1000:.3f}"


def percent_text(do_doc: float) -> str:
    """Slope as printed: whole numbers without decimals ('15'), otherwise the shortest decimal with a comma ('13,3')."""
    return (f"{do_doc:g}").replace(".", ",")


def validate(spec) -> dict:
    if not isinstance(spec, dict):
        raise SpecError(["spec phải là một đối tượng JSON {...}."])
    errors: list[str] = []
    if spec.get("loai") != "C":
        errors.append(f"loai = {spec.get('loai')!r}: spec_c chỉ xử lý loại C.")
    nhip = _mm(spec, "nhip", errors)
    cao_cot = _mm(spec, "cao_cot", errors)
    i_in = spec.get("do_doc_mai")
    if isinstance(i_in, bool) or not isinstance(i_in, (int, float)) or not math.isfinite(i_in):
        errors.append(f"do_doc_mai = {i_in!r} phải là số hữu hạn (độ dốc mái, %).")
        i_in = None
    elif not (0 < i_in <= 100):
        errors.append(f"do_doc_mai = {i_in:g} % nằm ngoài khoảng cho phép (0, 100].")
        i_in = None
    n_mai = spec.get("so_mai")
    if isinstance(n_mai, bool) or n_mai not in (1, 2) or not isinstance(n_mai, (int, float)):
        errors.append(f"so_mai = {n_mai!r} phải là 1 hoặc 2.")
        n_mai = None
    else:
        n_mai = int(n_mai)
    col = parse_section(spec.get("tiet_dien_cot", "")) if "tiet_dien_cot" in spec else None
    if col is None:
        errors.append(SECTION_ERR % spec.get("tiet_dien_cot"))
    raf = parse_section(spec.get("tiet_dien_keo", "")) if "tiet_dien_keo" in spec else None
    if raf is None:
        errors.append((SECTION_ERR % spec.get("tiet_dien_keo")).replace("tiet_dien_cot", "tiet_dien_keo"))
    ve_truc = spec.get("ve_truc_cau_kien", False)
    if not isinstance(ve_truc, bool):
        errors.append(f"ve_truc_cau_kien = {ve_truc!r} phải là true hoặc false.")
        ve_truc = False
    kho = parse_kho(spec.get("kho_giay", "auto"), errors)
    ty_le, scale = parse_scale(spec.get("ty_le", "auto"), errors)
    ten = parse_ten(spec.get("ten"), errors)
    kt = parse_khung_ten(spec.get("khung_ten") or {}, errors)
    params = parse_params(spec.get("tham_so") or {}, DEFAULT_PARAMS_C, errors)
    if not errors:
        hc, hr = col["h"], raf["h"]
        th = math.atan(i_in / 100.0)
        if nhip <= 2 * (hc + hr):
            errors.append(f"nhip = {nhip:g} mm quá nhỏ so với tiết diện: cần nhip > 2 × (h cột + h kèo) = {2 * (hc + hr):g} mm.")
        if cao_cot <= hc + hr / math.cos(th):
            errors.append(f"cao_cot = {cao_cot:g} mm quá thấp so với tiết diện: cần cao_cot > h cột + h kèo / cos(góc dốc) = {hc + hr / math.cos(th):.0f} mm.")
    if errors:
        raise SpecError(errors)
    fi = Fraction(Decimal(repr(float(i_in))))
    rise = Fraction(int(nhip)) * fi / 100 / (2 if n_mai == 2 else 1)
    y_top = Fraction(int(cao_cot)) + rise
    warnings = []
    if y_top.denominator != 1 or rise.denominator != 1:
        warnings.append(f"cao đỉnh tính ra không nguyên mm: đã làm tròn khi hiển thị (cao độ +{round_half_up(y_top) / 1000:.3f} m, kích thước {round_half_up(y_top)} mm, "
                        f"khoảng nhô {round_half_up(rise)} mm); giá trị chính xác = {fmt_exact(y_top)} mm (khoảng nhô {fmt_exact(rise)} mm). Hình vẽ dùng giá trị chính xác.")
    theta_deg = math.degrees(math.atan(i_in / 100.0))
    half = nhip / 2 if n_mai == 2 else nhip
    return dict(loai="C", ten=ten, nhip=nhip, cao_cot=cao_cot, do_doc_mai=float(i_in), so_mai=n_mai, col=col, raf=raf, ve_truc=ve_truc, kho_giay=kho, ty_le=ty_le, scale=scale,
                khung_ten=kt, params=params, i=float(i_in) / 100.0, theta_deg=theta_deg, rise=float(rise), rise_exact=rise, y_top=float(y_top), y_top_exact=y_top,
                run=half, raf_len=math.hypot(half, float(rise)), warnings=warnings)
