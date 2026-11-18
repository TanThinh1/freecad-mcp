"""Spec schema + input validation for drawing type B (grid + columns plan of a single-span steel building).

Parameter names: nhip, dai_nha, buoc_cot, tiet_dien_cot, ty_le (+ khung_ten metadata). Invalid input is never rounded or
cut silently: SpecError carries Vietnamese messages that name the wrong values.
"""
from __future__ import annotations

import datetime
import json
import math
import re
from fractions import Fraction

SCALES = (20, 50, 100, 200, 500)       # same series as scale.SCALES (TCVN 7286:2003)
MAX_AXES = 100            # N = dai_nha / buoc_cot + 1 vertical axes

# Layout parameters (paper mm). The defaults are project defaults, NOT dimensions verified from a TCVN standard.
# Override through spec["tham_so"].
DEFAULT_PARAMS = dict(
    duong_kinh_vong_truc=8.0,    # diameter of the axis bubble
    truc_vuon_qua=5.0,           # axis line runs this far past the outermost column edge
    khe_vong_truc=2.0,           # gap between axis end and bubble
    cao_chu_vong_truc=3.5,       # text height inside the bubble
    cao_chu_kich_thuoc=2.5,      # dimension digits
    cao_chu_nhan=2.5,            # section label next to each column
    cao_chu_tieu_de=5.0,         # view title
    cao_chu_ghi_chu=2.5,         # scale note under the title
    kt_dau_tien=10.0,            # first dimension line, measured from the axis end
    kt_giua_cac_duong=7.0,       # spacing between parallel dimension lines
    kt_exo=0.625,                # gap between measured point and extension line
    kt_exe=1.25,                 # extension line overshoot past the dimension line
    kt_mui_ten=2.5,              # tick size (bbox of the 45-degree slash)
    kt_khe_chu=0.625,            # gap between dimension line and text
    khoang_tieu_de=8.0,          # clear space between the annotated extents and the view title
    khoang_ghi_chu=3.0,          # between the title and the scale note
    khe_vung_ve=5.0,             # clearance to the frame / title block used when choosing the scale
)

SECTION_ERR = "tiet_dien_cot = %r không đọc được. Dạng hợp lệ: H300x150x6x9 (h x b x tw x tf, mm) hoặc hộp 100x50x2 (h x b x t, mm)."
_CTRL = re.compile("[\x00-\x1f\x7f\ud800-\udfff]")
_NAME = re.compile(r"[A-Za-z0-9_\-]{1,64}")
ROLE_KEYS = (("chu_tri", "Chủ trì"), ("kiem_tra", "Kiểm tra"), ("thiet_ke", "Thiết kế"))
# Names used ONLY when the spec says nothing about signatures (demo sample, obviously placeholder text); khung_ten.ky_mau = false switches the sample off.
SAMPLE_NAMES = {"chu_tri": "NGUYỄN VĂN A", "kiem_tra": "TRẦN VĂN B", "thiet_ke": "LÊ VĂN C"}
TEXT_FIELDS = ("don_vi_tk", "cong_trinh", "chu_dau_tu", "ten_ban_ve", "ky_hieu_ban_ve", "loai_ho_so", "ngay", "o15")


class SpecError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _mm(spec, key, errors):
    """Whole-millimetre positive number: labels are printed with DIMDEC = 0, so a fractional value would be rounded silently."""
    v = spec.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        errors.append(f"{key} = {v!r} phải là số hữu hạn (mm).")
        return None
    if v <= 0:
        errors.append(f"{key} = {v} phải lớn hơn 0.")
        return None
    if float(v) != int(v):
        errors.append(f"{key} = {v} mm không phải số nguyên mm: chữ kích thước in không có số thập phân (DIMDEC = 0) nên sẽ bị làm tròn "
                      f"(gần nhất {round(v)}). Hãy nhập số nguyên mm.")
        return None
    return float(int(v))


def _text(val, name, errors):
    if val is None or val == "":
        return ""
    if not isinstance(val, str):
        errors.append(f"{name} = {val!r} phải là chuỗi.")
        return ""
    if _CTRL.search(val):
        errors.append(f"{name} = {val!r}: chứa ký tự điều khiển hoặc xuống dòng. Dùng dấu | để ngắt dòng.")
        return ""
    return val.strip()


def parse_section(text):
    """'H300x150x6x9' -> dict(kind, h, b, ...). Returns None when unreadable."""
    s = str(text).strip().replace(",", ".")
    n = r"(\d+(?:\.\d+)?)"
    sep = r"\s*[xX×]\s*"
    m = re.fullmatch(rf"([HIhi])\s*{n}{sep}{n}{sep}{n}{sep}{n}", s)
    if m:
        h, b, tw, tf = (float(m.group(i)) for i in range(2, 6))
        if not (tw < b and 2 * tf < h and min(h, b, tw, tf) > 0):
            return None
        return dict(kind="I", h=h, b=b, tw=tw, tf=tf, text=str(text).strip())
    m = re.fullmatch(rf"(?:hộp|hop|RHS|SHS)?\s*{n}{sep}{n}{sep}{n}", s, re.I)
    if m:
        h, b, t = (float(m.group(i)) for i in range(1, 4))
        if not (2 * t < min(h, b) and t > 0):
            return None
        return dict(kind="RHS", h=h, b=b, t=t, text=str(text).strip())
    return None


def parse_scale(ty_le, errors):
    """-> (ty_le, scale or None). "auto" or "1:N" with N in SCALES."""
    if ty_le == "auto":
        return ty_le, None
    m = re.fullmatch(r"1\s*:\s*(\d+)", ty_le) if isinstance(ty_le, str) else None
    if not m or int(m.group(1)) not in SCALES:
        errors.append(f"ty_le = {ty_le!r} không hợp lệ. Dùng \"auto\" hoặc một trong " + ", ".join(f"1:{s}" for s in SCALES) + ".")
        return ty_le, None
    return ty_le, int(m.group(1))


def parse_kho(kho, errors):
    """kho_giay: "auto" (A3 first, A2/A1 only when needed) or one of A3, A2, A1."""
    if kho not in ("auto", "A3", "A2", "A1"):
        errors.append(f"kho_giay = {kho!r} không hợp lệ. Dùng \"auto\" (ưu tiên A3, lên A2 rồi A1 khi cần), \"A3\", \"A2\" hoặc \"A1\".")
        return "auto"
    return kho


def parse_ten(ten, errors):
    if not isinstance(ten, str) or not _NAME.fullmatch(ten):
        errors.append(f"ten = {ten!r}: chỉ dùng chữ cái, số, '_' và '-' (tối đa 64 ký tự); đây là tên thư mục và tệp đầu ra.")
    return ten


def parse_khung_ten(kt_in, errors) -> dict:
    """Title-block metadata (cells 1-7, 8-14, 15). Strings only, no control characters; date dd/mm/yyyy; at most 7 signature rows."""
    kt: dict = {}
    if not isinstance(kt_in, dict):
        errors.append(f"khung_ten = {kt_in!r} phải là đối tượng JSON.")
        return kt
    for k in TEXT_FIELDS:
        kt[k] = _text(kt_in.get(k), f"khung_ten.{k}", errors)
    ngay = kt.get("ngay", "")
    if ngay:
        try:
            datetime.datetime.strptime(ngay, "%d/%m/%Y")
        except ValueError:
            errors.append(f"khung_ten.ngay = {ngay!r} phải là ngày thật dạng dd/mm/yyyy.")
    ky_in = kt_in.get("ky") or []
    ky = []
    roles = []             # shortcut keys chu_tri / kiem_tra / thiet_ke: role label printed in cells 8-14, the name only when the spec gives one (never invented)
    for key, label in ROLE_KEYS:
        v = kt_in.get(key)
        if v is None or v is False:
            continue
        if v is True:
            roles.append(dict(chuc_danh=label, ho_ten=""))
        elif isinstance(v, str):
            roles.append(dict(chuc_danh=label, ho_ten=_text(v, f"khung_ten.{key}", errors)))
        else:
            errors.append(f"khung_ten.{key} = {v!r} phải là true (chỉ ghi nhãn chức danh) hoặc chuỗi họ tên.")
    if not isinstance(ky_in, list) or not all(isinstance(r, dict) for r in ky_in):
        errors.append(f"khung_ten.ky = {ky_in!r} phải là danh sách các đối tượng {{chuc_danh, ho_ten}}.")
    else:
        if len(ky_in) + len(roles) > 7:
            errors.append(f"khung_ten.ky ({len(ky_in)} dòng) cùng các nhãn chu_tri/kiem_tra/thiet_ke ({len(roles)} dòng) vượt 7 hàng của khung tên (ô 8-14).")
        for i, r in enumerate(ky_in):
            ky.append(dict(chuc_danh=_text(r.get("chuc_danh"), f"khung_ten.ky[{i}].chuc_danh", errors),
                           ho_ten=_text(r.get("ho_ten"), f"khung_ten.ky[{i}].ho_ten", errors)))
    ky_mau = kt_in.get("ky_mau", True)
    if not isinstance(ky_mau, bool):
        errors.append(f"khung_ten.ky_mau = {ky_mau!r} phải là true hoặc false (false: không điền tên mẫu vào khung tên).")
        ky_mau = True
    source = "spec" if (roles or ky) else "khong"
    if ky_mau and not roles and not ky and not any(k in kt_in for k, _ in ROLE_KEYS):
        roles = [dict(chuc_danh=label, ho_ten=SAMPLE_NAMES[k], mau=True) for k, label in ROLE_KEYS]          # default: role labels + sample names
        source = "mac_dinh"
    sign_date = kt.get("ngay") or datetime.date.today().strftime("%d/%m/%Y")
    for r in roles + ky:
        if r.get("ho_ten"):
            r["ngay"] = sign_date                                    # signed rows carry the drawing date (default: today)
    kt["ky_mau"] = ky_mau
    kt["ky_nguon"] = source
    kt["ky"] = roles + ky
    return kt


def parse_params(ts, defaults: dict, errors) -> dict:
    """Layout parameters: only known keys, positive finite numbers."""
    params = dict(defaults)
    if not isinstance(ts, dict):
        errors.append(f"tham_so = {ts!r} phải là đối tượng JSON.")
        return params
    for k, v in ts.items():
        if k not in defaults:
            errors.append(f"tham_so.{k} không phải tham số được hỗ trợ ({', '.join(defaults)}).")
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            errors.append(f"tham_so.{k} = {v!r} phải là số dương hữu hạn.")
        else:
            params[k] = float(v)
    return params


def validate(spec) -> dict:
    """Return a normalised copy of the spec or raise SpecError with every problem found."""
    if not isinstance(spec, dict):
        raise SpecError(["spec phải là một đối tượng JSON {...}."])
    errors: list[str] = []
    if spec.get("loai", "B") != "B":
        errors.append(f"loai = {spec.get('loai')!r}: make_drawing hiện chỉ hỗ trợ loại B.")
    nhip, dai, buoc = _mm(spec, "nhip", errors), _mm(spec, "dai_nha", errors), _mm(spec, "buoc_cot", errors)
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
    sec = parse_section(spec.get("tiet_dien_cot", "")) if "tiet_dien_cot" in spec else None
    if sec is None:
        errors.append(SECTION_ERR % spec.get("tiet_dien_cot"))
    else:
        if buoc and buoc <= sec["b"]:
            errors.append(f"buoc_cot = {buoc:g} mm không lớn hơn bề rộng cột b = {sec['b']:g} mm: các cột chồng lên nhau.")
        if nhip and nhip <= sec["h"]:
            errors.append(f"nhip = {nhip:g} mm không lớn hơn chiều cao tiết diện cột h = {sec['h']:g} mm.")
    gom = spec.get("gom_nhan_tiet_dien", True)
    if not isinstance(gom, bool):
        errors.append(f"gom_nhan_tiet_dien = {gom!r} phải là true hoặc false (true: một nhãn tiết diện + chú thích \"TẤT CẢ CỘT\"; false: nhãn ở mọi cột).")
        gom = True
    kho = parse_kho(spec.get("kho_giay", "auto"), errors)
    ty_le, scale = parse_scale(spec.get("ty_le", "auto"), errors)
    ten = parse_ten(spec.get("ten"), errors)
    kt = parse_khung_ten(spec.get("khung_ten") or {}, errors)
    params = parse_params(spec.get("tham_so") or {}, DEFAULT_PARAMS, errors)
    if errors:
        raise SpecError(errors)
    return dict(loai="B", ten=ten, gom_nhan_tiet_dien=gom, kho_giay=kho, nhip=nhip, dai_nha=dai, buoc_cot=buoc, so_truc_doc=N, section=sec, ty_le=ty_le, scale=scale, khung_ten=kt, params=params)


def load_spec(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as fh:      # tolerate a BOM written by Notepad / PowerShell
        return json.load(fh)
