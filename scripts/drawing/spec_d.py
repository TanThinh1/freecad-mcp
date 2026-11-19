"""Spec schema + input validation for drawing type D (purlin plan of a steel building roof; tool name "xa_go").

Parameters: nhip, dai_nha (a whole multiple of buoc_cot), buoc_cot, do_doc_mai (%), so_mai (1 or 2), buoc_xa_go (maximum purlin spacing measured ALONG the roof slope),
optional tiet_dien_cot (default H250x125x6x9), tiet_dien_xa_go (default C150x50x20x2.0, printed with the word "MẶC ĐỊNH" when it was not given), ty_le, kho_giay,
khung_ten, tham_so (same layout parameters as type B).

Geometry (exact arithmetic): half = nhip/2 (2 roofs, ridge in the middle) or nhip (1 roof, low eave at axis A, high eave at axis B); i = do_doc_mai/100.
L = half * sqrt(1 + i^2) is the slope length of one roof; n = ceil(L / buoc_xa_go) spaces, real spacing L/n, n + 1 purlins per roof. In plan the k-th purlin of a roof
stands at k * (L/n) * cos(theta) = k * half / n from its eave axis. The ridge purlins of the two roofs coincide in plan (one line).
"""
from __future__ import annotations

import math
import re
from decimal import Decimal
from fractions import Fraction

from spec_b import (DEFAULT_PARAMS, MAX_AXES, SECTION_ERR, SpecError, _mm, parse_khung_ten, parse_kho, parse_params, parse_scale, parse_section, parse_ten)

DEFAULT_PARAMS_D = dict(DEFAULT_PARAMS)
DEFAULT_COT = "H250x125x6x9"
DEFAULT_XA_GO = "C150x50x20x2.0"
MAX_PURLIN_SPANS = 100         # n = number of spacings of one roof
SOFT_MIN, SOFT_MAX = 800, 2000  # practical purlin spacing range, mm (project experience, NOT a TCVN clause)
XA_GO_ERR = "tiet_dien_xa_go = %r không đọc được. Dạng hợp lệ: C150x50x20x2.0 (h x b x môi x dày, mm; môi nhỏ hơn b, dày nhỏ hơn môi)."


def parse_purlin(text):
    """'C150x50x20x2.0' -> dict(kind='C', h, b, c, t, text) or None."""
    s = str(text).strip().replace(",", ".")
    n = r"(\d+(?:\.\d+)?)"
    sep = r"\s*[xX×]\s*"
    m = re.fullmatch(rf"[Cc]\s*{n}{sep}{n}{sep}{n}{sep}{n}", s)
    if not m:
        return None
    h, b, c, t = (float(m.group(i)) for i in range(1, 5))
    if not (min(h, b, c, t) > 0 and c < b and t < c and 2 * t < min(h, b)):
        return None
    return dict(kind="C", h=h, b=b, c=c, t=t, text=str(text).strip())


def fr(x) -> Fraction:
    """Exact value of the decimal a float / int prints as (spec numbers are decimals)."""
    return x if isinstance(x, Fraction) else Fraction(Decimal(repr(float(x))))


def ceil_sqrt_ratio(q: Fraction) -> int:
    """Smallest integer n >= 1 with n^2 >= q (q >= 0, exact)."""
    n = max(1, math.isqrt(q.numerator // q.denominator))
    while Fraction(n * n) < q:
        n += 1
    return n


def fmt_len(v: Fraction) -> str:
    """Length as printed: whole mm without decimals, otherwise one decimal with a comma, rounded half up (exact)."""
    if v.denominator == 1:
        return str(int(v))
    m = math.floor(v * 10 + Fraction(1, 2))
    return f"{m // 10}.{m % 10}".replace(".", ",")


def fmt_real_spacing(half: Fraction, i: Fraction, n: int) -> str:
    """Real spacing d = half*sqrt(1+i^2)/n with one decimal (comma), rounded half up, from exact integer arithmetic."""
    q = (half * half * (1 + i * i) * 100) / (n * n)          # (10 d)^2
    m = (lambda r: (r + 1 if (r + 1) % 2 == 1 else r + 2))(math.isqrt(math.floor(q * 4)))       # smallest odd k with k^2 > 4 q ...
    m = (m - 1) // 2                                          # ... so that m = floor(sqrt(q) + 1/2)
    return f"{m // 10}.{m % 10}".replace(".", ",")


def validate(spec) -> dict:
    if not isinstance(spec, dict):
        raise SpecError(["spec phải là một đối tượng JSON {...}."])
    errors: list[str] = []
    if spec.get("loai") != "D":
        errors.append(f"loai = {spec.get('loai')!r}: spec_d chỉ xử lý loại D.")
    nhip, dai, buoc = _mm(spec, "nhip", errors), _mm(spec, "dai_nha", errors), _mm(spec, "buoc_cot", errors)
    bxg = _mm(spec, "buoc_xa_go", errors)
    N = None
    if dai and buoc:
        q, r = divmod(Fraction(int(dai)), Fraction(int(buoc)))
        if r != 0:
            lo, hi = int(q) * buoc, (int(q) + 1) * buoc
            errors.append(f"dai_nha = {dai:g} mm không chia hết cho buoc_cot = {buoc:g} mm (dư {float(r):g} mm), nên số khung dai_nha/buoc_cot + 1 không nguyên. "
                          f"Giá trị chia hết gần nhất: {lo:g} mm hoặc {hi:g} mm. Không tự làm tròn.")
        else:
            N = int(q) + 1
            if N > MAX_AXES:
                errors.append(f"dai_nha/buoc_cot + 1 = {N} trục dọc vượt giới hạn {MAX_AXES}.")
    i_in = spec.get("do_doc_mai")
    if isinstance(i_in, bool) or not isinstance(i_in, (int, float)) or not math.isfinite(i_in):
        errors.append(f"do_doc_mai = {i_in!r} phải là số hữu hạn (độ dốc mái, %).")
        i_in = None
    elif not (0 < i_in <= 100):
        errors.append(f"do_doc_mai = {i_in:g} % nằm ngoài khoảng cho phép (0, 100].")
        i_in = None
    n_mai = spec.get("so_mai")
    if isinstance(n_mai, bool) or not isinstance(n_mai, (int, float)) or n_mai not in (1, 2):
        errors.append(f"so_mai = {n_mai!r} phải là 1 hoặc 2.")
        n_mai = None
    else:
        n_mai = int(n_mai)
    cot_text = spec.get("tiet_dien_cot")
    cot_default = cot_text is None
    col = parse_section(DEFAULT_COT if cot_default else cot_text)
    if col is None:
        errors.append(SECTION_ERR % cot_text)
    xg_text = spec.get("tiet_dien_xa_go")
    xg_default = xg_text is None
    pur = parse_purlin(DEFAULT_XA_GO if xg_default else xg_text)
    if pur is None:
        errors.append(XA_GO_ERR % xg_text)
    if col is not None:
        if buoc and buoc <= col["b"]:
            errors.append(f"buoc_cot = {buoc:g} mm không lớn hơn bề rộng cột b = {col['b']:g} mm: các cột chồng lên nhau.")
        if nhip and nhip <= col["h"]:
            errors.append(f"nhip = {nhip:g} mm không lớn hơn chiều cao tiết diện cột h = {col['h']:g} mm.")
    kho = parse_kho(spec.get("kho_giay", "auto"), errors)
    ty_le, scale = parse_scale(spec.get("ty_le", "auto"), errors)
    ten = parse_ten(spec.get("ten"), errors)
    kt = parse_khung_ten(spec.get("khung_ten") or {}, errors)
    params = parse_params(spec.get("tham_so") or {}, DEFAULT_PARAMS_D, errors)
    half = L2 = n = None
    if nhip and i_in is not None and n_mai is not None and bxg:
        i_ex = fr(i_in) / 100
        half = Fraction(int(nhip)) / (2 if n_mai == 2 else 1)
        L2 = half * half * (1 + i_ex * i_ex)
        L = math.sqrt(float(L2))
        if Fraction(int(bxg)) ** 2 > L2:
            errors.append(f"buoc_xa_go = {bxg:g} mm lớn hơn chiều dài mặt dốc của một mái L = {L:.1f} mm (nhip = {nhip:g} mm, so_mai = {n_mai}, do_doc_mai = {i_in:g} %). "
                          f"buoc_xa_go là khoảng cách TỐI ĐA giữa các xà gồ đo dọc mặt dốc nên không thể lớn hơn chiều dài mái; nhập buoc_xa_go ≤ {math.floor(L)} mm.")
        else:
            n = ceil_sqrt_ratio(L2 / (Fraction(int(bxg)) ** 2))
            if n > MAX_PURLIN_SPANS:
                errors.append(f"nhip = {nhip:g} mm, do_doc_mai = {i_in:g} %, buoc_xa_go = {bxg:g} mm cho n = {n} khoảng xà gồ trên một mái, vượt giới hạn {MAX_PURLIN_SPANS}. Tăng buoc_xa_go.")
    if errors:
        raise SpecError(errors)
    i_ex = fr(i_in) / 100
    warnings = []
    if not (SOFT_MIN <= bxg <= SOFT_MAX):
        warnings.append(f"buoc_xa_go = {bxg:g} mm nằm ngoài khoảng {SOFT_MIN}-{SOFT_MAX} mm thường dùng. Đây là kinh nghiệm thực tế, KHÔNG phải điều khoản TCVN; cần người thiết kế xác nhận.")
    proj = half / n
    if proj.denominator != 1:
        r = math.floor(proj + Fraction(1, 2))
        warnings.append(f"khoảng cách xà gồ chiếu lên mặt bằng = {fmt_len(half)}/{n} = {float(proj):.4f} mm không nguyên: nhãn kích thước làm tròn nửa lên {r} mm (tổng các nhãn {n} x {r} = {n * r} mm, "
                        f"không bằng {fmt_len(half)} mm); hình vẽ dùng giá trị chính xác và ghi chú nêu {fmt_len(proj)} mm.")
    d_text = fmt_real_spacing(half, i_ex, n)
    return dict(loai="D", ten=ten, nhip=nhip, dai_nha=dai, buoc_cot=buoc, so_truc_doc=N, buoc_xa_go=bxg, do_doc_mai=float(i_in), so_mai=n_mai, i_exact=i_ex, col=col, section=col,
                cot_mac_dinh=cot_default, xa_go=pur, xa_go_mac_dinh=xg_default, kho_giay=kho, ty_le=ty_le, scale=scale, khung_ten=kt, params=params, half=half,
                L=math.sqrt(float(L2)), n=n, real_spacing=math.sqrt(float(L2)) / n, real_spacing_text=d_text, proj_spacing=proj, theta_deg=math.degrees(math.atan(float(i_ex))),
                n_purlins_total=n_mai * (n + 1), n_lines=(2 * n + 1) if n_mai == 2 else n + 1, warnings=warnings)
