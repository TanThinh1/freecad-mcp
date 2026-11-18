"""Spec schema + input validation for drawing type A (single-flight straight steel stair, 2D plan + longitudinal section).

Parameters: cao_tang (mm, floor-to-floor), so_bac (number of risers), be_rong_mat_bac b, be_rong_ve w, chieu_day_tam (plate
thickness, default 3), dam_con (box stringer, e.g. "H60x120x2" = width 60 x depth 120 x wall 2, mm), ty_le, khung_ten.
Layout options: bo_cuc ("auto" | "chong" | "ngang") and ty_le_rieng (true: with ty_le "auto" the plan may use a smaller scale than the
section; an explicit ty_le is one common scale for both views).
The riser height h = cao_tang / so_bac may be non-integer; it is never rounded in geometry (verification tolerance 1e-6 mm).
"""
from __future__ import annotations

import math
import re

from spec_b import (DEFAULT_PARAMS, SpecError, _mm, _text, parse_khung_ten, parse_params, parse_scale, parse_ten)

MAX_RISERS = 200

# Layout parameters (paper mm unless noted): the spec_b defaults (project defaults, NOT verified from TCVN) plus stair-specific ones.
DEFAULT_PARAMS_A = dict(DEFAULT_PARAMS)
DEFAULT_PARAMS_A.update(
    doan_san=12.0,            # length of the floor stub drawn on each side of the section (paper mm)
    cao_chu_so_bac=2.5,       # step numbers in the plan
    khe_so_bac=1.5,           # minimum clear gap between a step number and any line (paper mm); numbers move above the plan when the step pitch is too small
    nguong_2hb_min=600.0,     # soft rule of thumb (NOT a verified TCVN clause): 2h + b normally 600..630 mm (real mm)
    nguong_2hb_max=630.0,
    khoang_giua_hinh=8.0,     # clear gap between the section block and the plan block (paper mm)
)
# parameters that are not paper lengths but real mm thresholds
REAL_MM_PARAMS = ("nguong_2hb_min", "nguong_2hb_max")
BO_CUC = ("auto", "chong", "ngang")      # sheet arrangement: automatic, plan below the section, plan beside the section


def parse_stringer(text):
    """'H60x120x2' / 'hộp 60x120x2' -> dict(bw, bd, t, text) (width, depth, wall in mm) or None."""
    n = r"(\d+(?:\.\d+)?)"
    sep = r"\s*[xX×]\s*"
    m = re.fullmatch(rf"(?:H|hộp|hop|RHS|SHS)?\s*{n}{sep}{n}{sep}{n}", str(text).strip().replace(",", "."), re.I)
    if not m:
        return None
    bw, bd, t = (float(m.group(i)) for i in range(1, 4))
    if not (min(bw, bd, t) > 0 and 2 * t < min(bw, bd)):
        return None
    return dict(bw=bw, bd=bd, t=t, text=str(text).strip())


def validate(spec) -> dict:
    if not isinstance(spec, dict):
        raise SpecError(["spec phải là một đối tượng JSON {...}."])
    errors: list[str] = []
    if spec.get("loai") != "A":
        errors.append(f"loai = {spec.get('loai')!r}: spec_a chỉ xử lý loại A.")
    H = _mm(spec, "cao_tang", errors)
    b = _mm(spec, "be_rong_mat_bac", errors)
    w = _mm(spec, "be_rong_ve", errors)
    n = spec.get("so_bac")
    if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or float(n) != int(n):
        errors.append(f"so_bac = {n!r} phải là số nguyên (số lần nâng).")
        n = None
    else:
        n = int(n)
        if n < 2:
            errors.append(f"so_bac = {n} phải ≥ 2 (vế thang cần ít nhất một mặt bậc).")
            n = None
        elif n > MAX_RISERS:
            errors.append(f"so_bac = {n} vượt giới hạn {MAX_RISERS}.")
            n = None
    t = spec.get("chieu_day_tam", 3)
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t <= 0:
        errors.append(f"chieu_day_tam = {t!r} phải là số dương (mm).")
        t = None
    ds = parse_stringer(spec.get("dam_con", "")) if "dam_con" in spec else None
    if ds is None:
        errors.append(f"dam_con = {spec.get('dam_con')!r} không đọc được. Dạng hợp lệ: H60x120x2 (rộng x cao x dày thành, mm).")
    elif w and 2 * ds["bw"] >= w:
        errors.append(f"dam_con rộng {ds['bw']:g} mm: hai dầm cốn ({2 * ds['bw']:g} mm) không nhỏ hơn bề rộng vế be_rong_ve = {w:g} mm.")
    ty_le, scale = parse_scale(spec.get("ty_le", "auto"), errors)
    bo_cuc = spec.get("bo_cuc", "auto")
    if bo_cuc not in BO_CUC:
        errors.append(f"bo_cuc = {bo_cuc!r} không hợp lệ. Dùng một trong: " + ", ".join(f'"{x}"' for x in BO_CUC) + " (auto: tự chọn; chong: mặt bằng dưới mặt cắt; ngang: mặt bằng bên phải mặt cắt).")
    rieng = spec.get("ty_le_rieng", True)
    if not isinstance(rieng, bool):
        errors.append(f"ty_le_rieng = {rieng!r} phải là true hoặc false (true: cho phép mặt bằng dùng tỷ lệ nhỏ hơn mặt cắt khi dùng ty_le \"auto\").")
        rieng = True
    ten = parse_ten(spec.get("ten"), errors)
    kt = parse_khung_ten(spec.get("khung_ten") or {}, errors)
    params = parse_params(spec.get("tham_so") or {}, DEFAULT_PARAMS_A, errors)
    if params["nguong_2hb_min"] > params["nguong_2hb_max"]:
        errors.append("tham_so.nguong_2hb_min lớn hơn nguong_2hb_max.")
    if errors:
        raise SpecError(errors)
    h = H / n
    warnings = []
    two_h_b = 2 * h + b
    if not (params["nguong_2hb_min"] <= two_h_b <= params["nguong_2hb_max"]):
        warnings.append(f"2h + b = {two_h_b:.1f} mm nằm ngoài khoảng {params['nguong_2hb_min']:g}-{params['nguong_2hb_max']:g} mm: ngoài khoảng thường dùng, "
                        f"cần người thiết kế xác nhận. (Quy tắc kinh nghiệm thông dụng, KHÔNG phải điều khoản TCVN đã xác minh; ngưỡng đổi được qua tham_so.)")
    return dict(loai="A", ten=ten, cao_tang=H, so_bac=n, b=b, w=w, t=float(t), dam_con=ds, ty_le=ty_le, scale=scale, bo_cuc=bo_cuc, ty_le_rieng=rieng, khung_ten=kt, params=params,
                h=h, L=(n - 1) * b, n_treads=n - 1, theta_deg=math.degrees(math.atan2(h, b)), two_h_b=two_h_b, warnings=warnings)
