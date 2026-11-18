"""Command line used by the MCP tools (src/freecad_mcp/ban_ve.py): guide / check one drawing spec. Prints ONE JSON object on stdout (UTF-8).

    python ban_ve_cli.py guide <thang|luoi_cot|khung_ngang>
    python ban_ve_cli.py check <loai> <spec.json> [--write-spec normalized.json]

`check` validates the spec with the same code as make_drawing, builds the primitives (no FreeCAD, no files except --write-spec) and reports the chosen
scale/layout with the reason, derived values and warnings. Every failure is a Vietnamese message; no traceback ever reaches the caller.
The layer table of the TCVN profile is read from the TCVN_PROFILE variable (or --profile).
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

LOAI = {"thang": "A", "luoi_cot": "B", "khung_ngang": "C"}
EXAMPLE = {"thang": "a1_3600x20.json", "luoi_cot": "b2_12000x30000.json", "khung_ngang": "c1_12000x6000.json"}
MAX_SPEC_BYTES = 20000

# Mandatory numbers per type: when one is missing the answer is "ask the customer", never a guess.
BAT_BUOC = {"thang": ("cao_tang", "so_bac", "be_rong_ve"), "luoi_cot": ("nhip", "dai_nha", "buoc_cot"), "khung_ngang": ("nhip", "cao_cot", "do_doc_mai", "so_mai")}
# Secondary values used when the spec omits them (the answer lists every default that was applied so the assistant can tell the customer).
# These are tool defaults taken from the examples, NOT values verified from a standard.
MAC_DINH = {
    "thang": {"be_rong_mat_bac": (250, "bước bậc b"), "dam_con": ("H60x120x2", "dầm cốn hộp rộng x cao x dày thành, mm"), "chieu_day_tam": (3, "mm, thép tấm mặt bậc"), "ty_le": ("auto", "tỷ lệ tự chọn")},
    "luoi_cot": {"tiet_dien_cot": ("H250x125x6x9", "tiết diện cột"), "ty_le": ("auto", "tỷ lệ tự chọn")},
    "khung_ngang": {"tiet_dien_cot": ("H250x125x6x9", "tiết diện cột"), "tiet_dien_keo": ("H250x125x6x9", "tiết diện kèo"), "ty_le": ("auto", "tỷ lệ tự chọn")},
}
# Title-block sample used when the customer gives no names (fictional placeholder text, as in the example specs).
KHUNG_TEN_MAU = {"don_vi_tk": "CÔNG TY TNHH THIẾT KẾ KẾT CẤU THÉP", "chu_dau_tu": "CÔNG TY TNHH THƯƠNG MẠI ABC", "loai_ho_so": "BVTC"}
CONG_TRINH_MAU = {"thang": "CẦU THANG THÉP", "luoi_cot": "NHÀ KHO TIỀN CHẾ", "khung_ngang": "NHÀ XƯỞNG KHUNG THÉP"}

KHUNG_TEN = ("khung_ten (tùy chọn): {don_vi_tk, cong_trinh, chu_dau_tu, ten_ban_ve, ky_hieu_ban_ve, loai_ho_so, ngay (dd/mm/yyyy), o15, "
             "ky: [{chuc_danh, ho_ten}], chu_tri / kiem_tra / thiet_ke (true = chỉ in nhãn chức danh ở ô 8-14; chuỗi = họ tên do người dùng cung cấp; không có = để trống, "
             "hệ thống KHÔNG tự bịa tên người); tối đa 7 dòng. ky_hieu_ban_ve mặc định theo loại (thang KC-03, luoi_cot KC-01, khung_ngang KC-02). "
             "Chuỗi dài hơn ô khung tên sẽ báo lỗi (không tự thu nhỏ chữ); dùng dấu | để ngắt dòng.")
COMMON_RULES = [
    "SỐ BẮT BUỘC (thiếu thì HỎI LẠI khách, không tự bịa): thang = cao_tang, so_bac, be_rong_ve; luoi_cot = nhip, dai_nha, buoc_cot; khung_ngang = nhip, cao_cot, do_doc_mai, so_mai. "
    "Các số còn lại có giá trị mặc định (xem mac_dinh); kiem_tra_spec trả da_dung_mac_dinh để nói rõ với khách.",
    "Mọi kích thước tính bằng mm. nhip, cao_cot, cao_tang... phải là số nguyên mm dương (không làm tròn âm thầm).",
    "ty_le: \"auto\" (mặc định, chọn tỷ lệ lớn nhất còn vừa khổ A3) hoặc 1:20, 1:25, 1:50, 1:100, 1:200, 1:500.",
    "Không tự xoay hình; nếu không vừa khung A3 (khung 390x277 trừ góc khung tên 180x65) sẽ báo lỗi kèm kích thước cần thiết.",
    "Tên bản vẽ/tệp (ten) do hệ thống tự sinh từ loại và số liệu; kết quả nằm trong thư mục out\\<ten>\\.",
]

GUIDE = {
    "thang": dict(
        mo_ta="Cầu thang thép một vế thẳng: một tờ A3 gồm MẶT BẰNG THANG và MẶT CẮT DỌC 1-1 (cùng danh sách nét), có mô hình 3D Part để đối chiếu.",
        tham_so=[
            dict(ten="cao_tang", don_vi="mm", bat_buoc=True, mo_ta="chiều cao từ sàn dưới đến sàn trên, số nguyên > 0"),
            dict(ten="so_bac", don_vi="bậc", bat_buoc=True, mo_ta="số lần nâng (số bậc cao), nguyên 2..200; số mặt bậc = so_bac − 1; chiều cao bậc h = cao_tang/so_bac (không làm tròn trong hình học)"),
            dict(ten="be_rong_mat_bac", don_vi="mm", bat_buoc=False, mac_dinh=250, mo_ta="bước bậc b (bề rộng mặt bậc theo phương chạy), số nguyên > 0"),
            dict(ten="be_rong_ve", don_vi="mm", bat_buoc=True, mo_ta="bề rộng vế thang, phải lớn hơn 2 lần bề rộng dầm cốn"),
            dict(ten="dam_con", bat_buoc=False, mac_dinh="H60x120x2", mo_ta="dầm cốn hộp, dạng \"H60x120x2\" = rộng x cao x dày thành (mm); có 2 dầm cốn"),
            dict(ten="chieu_day_tam", don_vi="mm", bat_buoc=False, mac_dinh=3, mo_ta="chiều dày thép tấm mặt bậc (ghi chú \"THÉP TẤM DÀY n MM\")"),
            dict(ten="ty_le", bat_buoc=False, mac_dinh="auto", mo_ta="xem quy tắc chung"),
            dict(ten="bo_cuc", bat_buoc=False, mac_dinh="auto", mo_ta="\"auto\" | \"chong\" (mặt bằng dưới mặt cắt) | \"ngang\" (mặt bằng bên phải mặt cắt)"),
            dict(ten="ty_le_rieng", bat_buoc=False, mac_dinh=True, mo_ta="true: với ty_le \"auto\", mặt bằng được dùng tỷ lệ nhỏ hơn mặt cắt để mặt cắt lớn hơn; ty_le cụ thể = một tỷ lệ chung"),
            dict(ten="khung_ten", bat_buoc=False, mo_ta=KHUNG_TEN),
            dict(ten="tham_so", bat_buoc=False, mo_ta="ghi đè tham số bố cục (mm trên giấy, số dương); mặc định là giá trị dự án, CHƯA kiểm chứng từ TCVN"),
        ],
        quy_tac=COMMON_RULES + [
            "Chiều cao bậc h không nguyên (vd 3000/17): hình dùng giá trị chính xác, chữ ghi \"h = 3000/17 ≈ 176,5 MM\"; không in phép nhân sai.",
            "Cảnh báo mềm (không phải lỗi): 2h + b ngoài 600-630 mm → \"cần người thiết kế xác nhận\" (quy tắc kinh nghiệm thông dụng, KHÔNG phải điều khoản TCVN đã xác minh; đổi ngưỡng qua tham_so nguong_2hb_min/max).",
            "so_bac < 2 hoặc cao_tang <= 0 → báo lỗi kèm giá trị sai.",
        ]),
    "luoi_cot": dict(
        mo_ta="Mặt bằng lưới trục và cột của nhà thép một nhịp: các trục 1..N, trục A, B, cột tại mọi giao điểm, chuỗi kích thước.",
        tham_so=[
            dict(ten="nhip", don_vi="mm", bat_buoc=True, mo_ta="khoảng cách hai trục A và B, số nguyên > 0"),
            dict(ten="dai_nha", don_vi="mm", bat_buoc=True, mo_ta="chiều dài nhà; phải chia hết cho buoc_cot (không tự làm tròn)"),
            dict(ten="buoc_cot", don_vi="mm", bat_buoc=True, mo_ta="bước cột; số trục dọc N = dai_nha/buoc_cot + 1 (tối đa 100)"),
            dict(ten="tiet_dien_cot", bat_buoc=False, mac_dinh="H250x125x6x9", mo_ta="\"H300x150x6x9\" (h x b x tw x tf) hoặc hộp \"100x50x2\" (h x b x t), mm"),
            dict(ten="gom_nhan_tiet_dien", bat_buoc=False, mac_dinh=True, mo_ta="true: ghi 1 nhãn tiết diện + chú thích \"TẤT CẢ CỘT: ...\"; false: nhãn ở mọi cột"),
            dict(ten="ty_le", bat_buoc=False, mac_dinh="auto", mo_ta="xem quy tắc chung"),
            dict(ten="khung_ten", bat_buoc=False, mo_ta=KHUNG_TEN),
            dict(ten="tham_so", bat_buoc=False, mo_ta="ghi đè tham số bố cục (mm trên giấy)"),
        ],
        quy_tac=COMMON_RULES + [
            "dai_nha không chia hết cho buoc_cot → báo lỗi kèm hai giá trị chia hết gần nhất.",
            "buoc_cot phải lớn hơn bề rộng cột b; nhip phải lớn hơn chiều cao tiết diện cột h.",
        ]),
    "khung_ngang": dict(
        mo_ta="Mặt cắt ngang khung thép (một hình): 2 cột + 1 hoặc 2 mái, đường bao là hợp các cấu kiện (nút cắt theo phân giác), kích thước, cao độ, ký hiệu trục A, B.",
        tham_so=[
            dict(ten="nhip", don_vi="mm", bat_buoc=True, mo_ta="khoảng cách hai trục A và B"),
            dict(ten="cao_cot", don_vi="mm", bat_buoc=True, mo_ta="từ cốt ±0.000 đến giao điểm trục cột và trục kèo"),
            dict(ten="do_doc_mai", don_vi="%", bat_buoc=True, mo_ta="độ dốc mái, 0 < i ≤ 100 (cho phép số lẻ như 13.3)"),
            dict(ten="so_mai", bat_buoc=True, mo_ta="1 hoặc 2. 2 mái: đỉnh giữa nhịp, cao đỉnh = cao_cot + nhip/2 × i. 1 mái: kèo dốc từ trục A (thấp) lên trục B, cao đỉnh = cao_cot + nhip × i"),
            dict(ten="tiet_dien_cot", bat_buoc=False, mac_dinh="H250x125x6x9", mo_ta="\"H300x150x6x9\" hoặc hộp; chiều cao h là bề dày nét cột trên hình"),
            dict(ten="tiet_dien_keo", bat_buoc=False, mac_dinh="H250x125x6x9", mo_ta="như trên, cho kèo"),
            dict(ten="ve_truc_cau_kien", bat_buoc=False, mac_dinh=False, mo_ta="true: vẽ thêm trục kèo (nét chấm gạch mảnh)"),
            dict(ten="ty_le", bat_buoc=False, mac_dinh="auto", mo_ta="xem quy tắc chung"),
            dict(ten="khung_ten", bat_buoc=False, mo_ta=KHUNG_TEN),
            dict(ten="tham_so", bat_buoc=False, mo_ta="ghi đè tham số bố cục (mm trên giấy)"),
        ],
        quy_tac=COMMON_RULES + [
            "nhip, cao_cot > 0; do_doc_mai trong (0, 100]; so_mai thuộc {1, 2}; tiết diện đọc được, ngược lại báo lỗi kèm giá trị sai.",
            "Cao đỉnh không nguyên mm (vd 13,3%): hình vẽ dùng giá trị chính xác, chữ hiển thị làm tròn nửa lên đến mm và có CẢNH BÁO nêu giá trị chính xác.",
        ]),
}


def _out(obj, code=0):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    sys.stdout.write("\n")
    return code


def _num_name(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return "x"
    if float(v) == int(v):
        return str(int(v))
    return re.sub(r"[^0-9]", "p", f"{v:g}")


def auto_name(loai: str, spec: dict) -> str:
    g = spec.get
    if loai == "thang":
        name = f"thang_{_num_name(g('cao_tang'))}x{_num_name(g('so_bac'))}"
    elif loai == "luoi_cot":
        name = f"luoi_cot_{_num_name(g('nhip'))}x{_num_name(g('dai_nha'))}_{_num_name(g('buoc_cot'))}"
    else:
        name = f"khung_ngang_{_num_name(g('nhip'))}x{_num_name(g('cao_cot'))}_{_num_name(g('do_doc_mai'))}pct_{_num_name(g('so_mai'))}mai"
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)[:64]


def guide(loai: str):
    if loai not in GUIDE:
        return dict(hop_le=False, loi=[f"loai = {loai!r} không hợp lệ. Dùng một trong: thang, luoi_cot, khung_ngang."])
    import spec_a
    import spec_b
    import spec_c
    defaults = {"thang": spec_a.DEFAULT_PARAMS_A, "luoi_cot": spec_b.DEFAULT_PARAMS, "khung_ngang": spec_c.DEFAULT_PARAMS_C}[loai]
    ex = json.load(open(os.path.join(HERE, "examples", EXAMPLE[loai]), encoding="utf-8-sig"))
    ex.pop("ten", None)                  # generated
    ex.pop("loai", None)                 # set from the tool argument
    g = dict(GUIDE[loai])
    g["tham_so_bo_cuc_mac_dinh"] = {k: v for k, v in defaults.items()}
    return dict(loai=loai, **g, vi_du_spec=ex)


def _derived(loai, sp, D):
    import spec_c
    if loai == "thang":
        return dict(chieu_cao_bac_h_mm=sp["h"], chieu_cao_bac_dang_so=(f"{sp['cao_tang'] / sp['so_bac']:.4f}"), so_mat_bac=sp["n_treads"], chieu_dai_ve_mm=sp["L"],
                    goc_doc_do=round(sp["theta_deg"], 2), hai_h_cong_b_mm=round(sp["two_h_b"], 1))
    if loai == "luoi_cot":
        return dict(so_truc_doc_N=sp["so_truc_doc"], so_cot=2 * sp["so_truc_doc"], buoc_cot_mm=sp["buoc_cot"], dai_nha_mm=sp["dai_nha"], nhip_mm=sp["nhip"])
    return dict(cao_dinh_mm=sp["y_top"], cao_dinh_chinh_xac=spec_c.fmt_exact(sp["y_top_exact"]),
                khoang_nho_mm=sp["rise"], goc_doc_do=round(sp["theta_deg"], 2), chieu_dai_keo_truc_mm=round(sp["raf_len"], 1), so_mai=sp["so_mai"])


def check(loai: str, spec_path: str, write_spec: str | None, profile: str | None):
    if loai not in LOAI:
        return dict(hop_le=False, loi=[f"loai = {loai!r} không hợp lệ. Dùng một trong: thang, luoi_cot, khung_ngang."])
    try:
        if os.path.getsize(spec_path) > MAX_SPEC_BYTES:
            return dict(hop_le=False, loai=loai, loi=[f"spec quá lớn (> {MAX_SPEC_BYTES} byte)."])
        raw = json.load(open(spec_path, encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return dict(hop_le=False, loai=loai, loi=[f"không đọc được spec JSON: {e}"])
    if not isinstance(raw, dict):
        return dict(hop_le=False, loai=loai, loi=["spec phải là một đối tượng JSON {...}."])
    k = LOAI[loai]
    spec = dict(raw)
    thieu = [x for x in BAT_BUOC[loai] if spec.get(x) is None]
    if thieu:
        return dict(hop_le=False, loai=loai, thieu_bat_buoc=thieu,
                    loi=[f"Thiếu số bắt buộc: {', '.join(thieu)}. HÃY HỎI LẠI khách các số này (đơn vị mm trừ do_doc_mai là %, so_bac/so_mai là số đếm); không tự đoán."])
    da_dung = []
    for key, (val, note) in MAC_DINH[loai].items():
        if spec.get(key) is None:
            spec[key] = val
            da_dung.append(dict(ten=key, gia_tri=val, y_nghia=note))
    kt_in = spec.get("khung_ten")
    if not kt_in:
        import datetime
        kt = dict(KHUNG_TEN_MAU, cong_trinh=CONG_TRINH_MAU[loai], ngay=datetime.date.today().strftime("%d/%m/%Y"))
        spec["khung_ten"] = kt
        da_dung.append(dict(ten="khung_ten", gia_tri=kt, y_nghia="khách chưa cung cấp: dùng tên mẫu (giả lập) và ngày hôm nay; ô họ tên người ký để trống"))
    spec["loai"] = k
    ten = auto_name(loai, spec)
    spec["ten"] = ten
    import build_a
    import build_b
    import build_c
    import spec_a
    import spec_b
    import spec_c
    from spec_b import SpecError
    from tcvn import ProfileError, read_profile
    validate, build = {"A": (spec_a.validate, build_a.build), "B": (spec_b.validate, build_b.build), "C": (spec_c.validate, build_c.build)}[k]
    try:
        sp = validate(spec)
        D = build(sp, read_profile(profile))
    except SpecError as e:
        return dict(hop_le=False, loai=loai, ten=ten, loi=e.errors)
    except ProfileError as e:
        return dict(hop_le=False, loai=loai, ten=ten, loi=[str(e)], loi_he_thong=True)
    sc = f"1:{D.scale}"
    if D.info.get("scale_plan") and D.info["scale_plan"] != D.scale:
        sc = f"mặt cắt 1:{D.scale}, mặt bằng 1:{D.info['scale_plan']}"
    res = dict(hop_le=True, loai=loai, ten=ten, ty_le=sc, bo_cuc=D.info.get("layout"), ly_do=D.info["reason"], so_do=_derived(loai, sp, D),
               canh_bao=list(D.info.get("warnings", [])), da_dung_mac_dinh=da_dung, thu_muc_ket_qua=f"out\\{ten}\\")
    if k == "C":
        res["quy_uoc"] = D.info.get("convention")
    if write_spec:
        with open(write_spec, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False, indent=1)
        res["spec_chuan_hoa"] = write_spec
    return res


def main(argv):
    try:
        if len(argv) >= 2 and argv[0] == "guide":
            return _out(guide(argv[1]))
        if len(argv) >= 3 and argv[0] == "check":
            def opt(name):
                return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None
            return _out(check(argv[1], argv[2], opt("--write-spec"), opt("--profile")))
        return _out(dict(hop_le=False, loi=["cách dùng: ban_ve_cli.py guide <loai> | check <loai> <spec.json> [--write-spec tệp]"]), 2)
    except Exception as e:  # noqa: BLE001 - the MCP tool must never see a raw traceback
        sys.stderr.write(f"ban_ve_cli: {type(e).__name__}: {e}\n")
        return _out(dict(hop_le=False, loi=["Lỗi nội bộ khi kiểm tra spec; kiểm tra lại cấu trúc spec (đúng kiểu số/chuỗi) rồi thử lại."], loi_he_thong=True), 1)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
