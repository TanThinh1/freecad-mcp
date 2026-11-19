"""Command line used by the MCP tools (src/freecad_mcp/ban_ve.py): guide / check one drawing spec. Prints ONE JSON object on stdout (UTF-8).

    python ban_ve_cli.py guide <thang|luoi_cot|khung_ngang|xa_go|ve_tu_do>
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

LOAI = {"thang": "A", "luoi_cot": "B", "khung_ngang": "C", "xa_go": "D", "ve_tu_do": "E"}
EXAMPLE = {"thang": "a1_3600x20.json", "luoi_cot": "b2_12000x30000.json", "khung_ngang": "c1_12000x6000.json", "xa_go": "d1_12000x30000_2mai.json", "ve_tu_do": "e2_nha_cap4.json"}
MAX_SPEC_BYTES = 20000
MAX_SPEC_BYTES_E = 300000          # ve_tu_do: up to 2000 elements

KHOA_HOP_LE = {
    "thang": {"cao_tang", "so_bac", "be_rong_mat_bac", "be_rong_ve", "chieu_day_tam", "dam_con", "ty_le", "bo_cuc", "ty_le_rieng", "khung_ten", "tham_so"},
    "luoi_cot": {"nhip", "dai_nha", "buoc_cot", "tiet_dien_cot", "ty_le", "kho_giay", "gom_nhan_tiet_dien", "khung_ten", "tham_so"},
    "khung_ngang": {"nhip", "cao_cot", "do_doc_mai", "so_mai", "tiet_dien_cot", "tiet_dien_keo", "ve_truc_cau_kien", "ty_le", "kho_giay", "khung_ten", "tham_so"},
    "xa_go": {"nhip", "dai_nha", "buoc_cot", "do_doc_mai", "so_mai", "buoc_xa_go", "tiet_dien_cot", "tiet_dien_xa_go", "ty_le", "kho_giay", "khung_ten", "tham_so"},
    "ve_tu_do": {"hinh", "ty_le", "kho_giay", "khung_ten", "tham_so"},
}
# Mandatory numbers per type: when one is missing the answer is "ask the customer", never a guess.
BAT_BUOC = {"thang": ("cao_tang", "so_bac", "be_rong_ve"), "luoi_cot": ("nhip", "dai_nha", "buoc_cot"), "khung_ngang": ("nhip", "cao_cot", "do_doc_mai", "so_mai"),
           "xa_go": ("nhip", "dai_nha", "buoc_cot", "do_doc_mai", "so_mai", "buoc_xa_go"), "ve_tu_do": ("hinh",)}
# Secondary values used when the spec omits them (the answer lists every default that was applied so the assistant can tell the customer).
# These are tool defaults taken from the examples, NOT values verified from a standard.
MAC_DINH = {
    "thang": {"be_rong_mat_bac": (250, "bước bậc b"), "dam_con": ("H75x150x2", "dầm cốn hộp rộng x cao x dày thành, mm"), "chieu_day_tam": (3, "mm, thép tấm mặt bậc"), "ty_le": ("auto", "tỷ lệ tự chọn")},
    "luoi_cot": {"tiet_dien_cot": ("H250x125x6x9", "tiết diện cột"), "ty_le": ("auto", "tỷ lệ tự chọn")},
    "khung_ngang": {"tiet_dien_cot": ("H250x125x6x9", "tiết diện cột"), "tiet_dien_keo": ("H250x125x6x9", "tiết diện kèo"), "ty_le": ("auto", "tỷ lệ tự chọn")},
    "xa_go": {"ty_le": ("auto", "tỷ lệ tự chọn")},
    "ve_tu_do": {"ty_le": ("auto", "tỷ lệ tự chọn")},
}
# Type D applies these two itself (spec_d.validate) so that the drawing can print the word MẶC ĐỊNH next to the purlin section; they are only REPORTED here, never written into the spec.
MAC_DINH_D = {"tiet_dien_cot": ("H250x125x6x9", "tiết diện cột"), "tiet_dien_xa_go": ("C150x50x20x2.0", "tiết diện xà gồ (bản vẽ ghi rõ MẶC ĐỊNH)")}
# Title-block sample used when the customer gives no names (fictional placeholder text, as in the example specs).
KHUNG_TEN_MAU = {"don_vi_tk": "CÔNG TY TNHH THIẾT KẾ KẾT CẤU THÉP", "chu_dau_tu": "CÔNG TY TNHH THƯƠNG MẠI ABC", "loai_ho_so": "BVTC"}
CONG_TRINH_MAU = {"thang": "CẦU THANG THÉP", "luoi_cot": "NHÀ KHO TIỀN CHẾ", "khung_ngang": "NHÀ XƯỞNG KHUNG THÉP", "xa_go": "NHÀ XƯỞNG KHUNG THÉP", "ve_tu_do": "CÔNG TRÌNH DÂN DỤNG"}

KHUNG_TEN = ("khung_ten (tùy chọn): {don_vi_tk, cong_trinh, chu_dau_tu, ten_ban_ve, ky_hieu_ban_ve, loai_ho_so, ngay (dd/mm/yyyy), o15, "
             "ky: [{chuc_danh, ho_ten}], chu_tri / kiem_tra / thiet_ke (true = chỉ in nhãn chức danh ở ô 8-14; chuỗi = họ tên do người dùng cung cấp). MẶC ĐỊNH khi spec không nói gì: "
             "3 nhãn Chủ trì / Kiểm tra / Thiết kế với tên MẪU (NGUYỄN VĂN A, TRẦN VĂN B, LÊ VĂN C) và ngày của bản vẽ; ky_mau: false = để trống khối này; "
             "hệ thống KHÔNG tự bịa tên người); tối đa 7 dòng. ky_hieu_ban_ve mặc định theo loại (thang KC-03, luoi_cot KC-01, khung_ngang KC-02). "
             "Chữ trong ô khung tên tự co cho vừa ô (hệ số rộng tối thiểu 0,7, rồi cao tối thiểu 2 mm, rồi ngắt 2 dòng nếu ô đủ chỗ); vẫn không vừa thì báo lỗi, khi đó hãy rút gọn hoặc dùng dấu | để ngắt dòng.")
COMMON_RULES = [
    "SỐ BẮT BUỘC (thiếu thì HỎI LẠI khách, không tự bịa): thang = cao_tang, so_bac, be_rong_ve; luoi_cot = nhip, dai_nha, buoc_cot; khung_ngang = nhip, cao_cot, do_doc_mai, so_mai. "
    "Các số còn lại có giá trị mặc định (xem mac_dinh); kiem_tra_spec trả da_dung_mac_dinh để nói rõ với khách.",
    "Mọi kích thước tính bằng mm. nhip, cao_cot, cao_tang... phải là số nguyên mm dương (không làm tròn âm thầm).",
    "ty_le: \"auto\" (mặc định, chọn tỷ lệ lớn nhất còn vừa khổ A3) hoặc 1:20, 1:50, 1:100, 1:200, 1:500 (dãy TCVN 7286:2003).",
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
            dict(ten="dam_con", bat_buoc=False, mac_dinh="H75x150x2", mo_ta="dầm cốn hộp, dạng \"H75x150x2\" = rộng x cao x dày thành (mm); có 2 dầm cốn. Để dầm che TRỌN bậc, cao dầm phải >= h·cosθ (khoảng 145 mm cho thang 3000 cao, 17 bậc, bước bậc 250); thấp hơn thì hệ thống cảnh báo và hạ dải dầm cho che hết chân bậc"),
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
            dict(ten="kho_giay", bat_buoc=False, mac_dinh="auto", mo_ta="\"auto\": ưu tiên A3, chỉ dùng A2 rồi A1 khi A3 không vừa ở tỷ lệ ≤ 1:200; hoặc ép \"A3\" | \"A2\" | \"A1\" (khung A2 564x400, A1 811x574, khung tên vẫn 180x65 ở góc dưới phải)"),
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
            dict(ten="kho_giay", bat_buoc=False, mac_dinh="auto", mo_ta="\"auto\": ưu tiên A3, chỉ dùng A2 rồi A1 khi A3 không vừa ở tỷ lệ ≤ 1:100; hoặc ép \"A3\" | \"A2\" | \"A1\" (khung A2 564x400, A1 811x574, khung tên vẫn 180x65 ở góc dưới phải)"),
            dict(ten="ve_truc_cau_kien", bat_buoc=False, mac_dinh=False, mo_ta="true: vẽ thêm trục kèo (nét chấm gạch mảnh)"),
            dict(ten="ty_le", bat_buoc=False, mac_dinh="auto", mo_ta="xem quy tắc chung"),
            dict(ten="khung_ten", bat_buoc=False, mo_ta=KHUNG_TEN),
            dict(ten="tham_so", bat_buoc=False, mo_ta="ghi đè tham số bố cục (mm trên giấy)"),
        ],
        quy_tac=COMMON_RULES + [
            "nhip, cao_cot > 0; do_doc_mai trong (0, 100]; so_mai thuộc {1, 2}; tiết diện đọc được, ngược lại báo lỗi kèm giá trị sai.",
            "Cao đỉnh không nguyên mm (vd 13,3%): hình vẽ dùng giá trị chính xác, chữ hiển thị làm tròn nửa lên đến mm và có CẢNH BÁO nêu giá trị chính xác.",
        ]),
    "xa_go": dict(
        mo_ta="Mặt bằng xà gồ mái của nhà thép một nhịp (KC-04): lưới trục + cột như luoi_cot, các xà gồ chiếu lên mặt bằng (lớp XA-GO), chuỗi kích thước khoảng cách xà gồ theo phương chiếu, ghi chú tiết diện / số lượng / khoảng cách thực. Không có hình 3D.",
        tham_so=[
            dict(ten="nhip", don_vi="mm", bat_buoc=True, mo_ta="khoảng cách hai trục A và B, số nguyên > 0"),
            dict(ten="dai_nha", don_vi="mm", bat_buoc=True, mo_ta="chiều dài nhà; phải chia hết cho buoc_cot (không tự làm tròn)"),
            dict(ten="buoc_cot", don_vi="mm", bat_buoc=True, mo_ta="bước cột; số trục dọc N = dai_nha/buoc_cot + 1 (tối đa 100)"),
            dict(ten="do_doc_mai", don_vi="%", bat_buoc=True, mo_ta="độ dốc mái, 0 < i ≤ 100 (cho phép số lẻ như 13.3)"),
            dict(ten="so_mai", bat_buoc=True, mo_ta="1 hoặc 2. 2 mái: tim nóc ở giữa nhịp (xà gồ nóc của hai mái trùng nhau trên mặt bằng, vẽ một đường). 1 mái: dốc từ trục A (thấp) lên trục B (cao)"),
            dict(ten="buoc_xa_go", don_vi="mm", bat_buoc=True, mo_ta="khoảng cách TỐI ĐA giữa các xà gồ, đo dọc theo mặt dốc; số nguyên > 0, không lớn hơn chiều dài mặt dốc của một mái. Ngoài 800-2000 mm thì có cảnh báo mềm (kinh nghiệm thực tế, KHÔNG phải điều khoản TCVN)"),
            dict(ten="tiet_dien_cot", bat_buoc=False, mac_dinh="H250x125x6x9", mo_ta="\"H300x150x6x9\" (h x b x tw x tf) hoặc hộp \"100x50x2\", mm"),
            dict(ten="tiet_dien_xa_go", bat_buoc=False, mac_dinh="C150x50x20x2.0", mo_ta="\"C150x50x20x2.0\" = h x b x môi x dày (mm); khi khách không nêu, bản vẽ ghi rõ \"(MẶC ĐỊNH)\" cạnh tiết diện"),
            dict(ten="kho_giay", bat_buoc=False, mac_dinh="auto", mo_ta="\"auto\": ưu tiên A3, chỉ dùng A2 rồi A1 khi A3 không vừa ở tỷ lệ ≤ 1:200; hoặc ép \"A3\" | \"A2\" | \"A1\""),
            dict(ten="ty_le", bat_buoc=False, mac_dinh="auto", mo_ta="xem quy tắc chung"),
            dict(ten="khung_ten", bat_buoc=False, mo_ta=KHUNG_TEN + " Với xa_go: ky_hieu_ban_ve mặc định KC-04."),
            dict(ten="tham_so", bat_buoc=False, mo_ta="ghi đè tham số bố cục (mm trên giấy), như luoi_cot"),
        ],
        quy_tac=COMMON_RULES[1:] + [
            "SỐ BẮT BUỘC của xa_go (thiếu thì HỎI LẠI khách): nhip, dai_nha, buoc_cot, do_doc_mai, so_mai, buoc_xa_go.",
            "L = chiều dài mặt dốc một mái = (nhịp/2 hoặc nhịp) × √(1 + i²); n = số khoảng = làm tròn lên của L / buoc_xa_go; khoảng thực = L / n; mỗi mái có n + 1 xà gồ. Trên mặt bằng, xà gồ thứ k cách trục A k × (nhịp/2 hoặc nhịp) / n (= khoảng thực × cosθ).",
            "dai_nha không chia hết cho buoc_cot, buoc_xa_go lớn hơn chiều dài mặt dốc, so_mai ngoài {1, 2} → báo lỗi tiếng Việt kèm giá trị sai và gợi ý.",
            "Khoảng cách chiếu không nguyên mm (vd nhịp/2 chia n): nhãn kích thước làm tròn nửa lên đến mm và có CẢNH BÁO nêu giá trị chính xác; ghi chú trên bản vẽ nêu giá trị 1 chữ số thập phân.",
            "Nhãn khoảng cách xà gồ phải nằm gọn giữa hai mũi tên: tỷ lệ nào không đủ chỗ bị loại (ví dụ nhà lớn với xà gồ dày không vẽ được ở 1:200), khi đó lên khổ lớn hơn hoặc báo lỗi kèm lý do.",
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
    elif loai == "ve_tu_do":
        h = spec.get("hinh") if isinstance(spec.get("hinh"), list) else []
        name = f"ve_tu_do_{len(h)}hinh_{sum(len(x.get('phan_tu', [])) for x in h if isinstance(x, dict) and isinstance(x.get('phan_tu'), list))}pt"
    elif loai == "xa_go":
        name = f"xa_go_{_num_name(g('nhip'))}x{_num_name(g('dai_nha'))}_{_num_name(g('buoc_cot'))}_{_num_name(g('buoc_xa_go'))}"
    else:
        name = f"khung_ngang_{_num_name(g('nhip'))}x{_num_name(g('cao_cot'))}_{_num_name(g('do_doc_mai'))}pct_{_num_name(g('so_mai'))}mai"
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)[:64]


def guide(loai: str):
    if loai == "ve_tu_do":
        import guide_e
        import spec_e
        ex = json.load(open(os.path.join(HERE, "examples", EXAMPLE[loai]), encoding="utf-8-sig"))
        ex.pop("ten", None)
        ex.pop("loai", None)
        g = guide_e.guide()
        g["tham_so_bo_cuc_mac_dinh"] = dict(spec_e.DEFAULT_PARAMS_E)
        return dict(loai=loai, **g, vi_du_spec=ex)
    if loai not in GUIDE:
        return dict(hop_le=False, loi=[f"loai = {loai!r} không hợp lệ. Dùng một trong: thang, luoi_cot, khung_ngang, xa_go, ve_tu_do."])
    import spec_a
    import spec_b
    import spec_c
    import spec_d
    defaults = {"thang": spec_a.DEFAULT_PARAMS_A, "luoi_cot": spec_b.DEFAULT_PARAMS, "khung_ngang": spec_c.DEFAULT_PARAMS_C, "xa_go": spec_d.DEFAULT_PARAMS_D}[loai]
    ex = json.load(open(os.path.join(HERE, "examples", EXAMPLE[loai]), encoding="utf-8-sig"))
    ex.pop("ten", None)                  # generated
    ex.pop("loai", None)                 # set from the tool argument
    g = dict(GUIDE[loai])
    g["tham_so_bo_cuc_mac_dinh"] = {k: v for k, v in defaults.items()}
    return dict(loai=loai, **g, vi_du_spec=ex)


def _derived(loai, sp, D):
    import spec_c
    import spec_e
    import spec_d
    if loai == "thang":
        return dict(chieu_cao_bac_h_mm=sp["h"], chieu_cao_bac_dang_so=(f"{sp['cao_tang'] / sp['so_bac']:.4f}"), so_mat_bac=sp["n_treads"], chieu_dai_ve_mm=sp["L"],
                    goc_doc_do=round(sp["theta_deg"], 2), hai_h_cong_b_mm=round(sp["two_h_b"], 1))
    if loai == "luoi_cot":
        return dict(so_truc_doc_N=sp["so_truc_doc"], so_cot=2 * sp["so_truc_doc"], buoc_cot_mm=sp["buoc_cot"], dai_nha_mm=sp["dai_nha"], nhip_mm=sp["nhip"])
    if loai == "ve_tu_do":
        import collections
        v = sp["views"][0]
        c = collections.Counter(e["t"] for e in v["elems"])
        return dict(so_phan_tu=sp["n_elements"], theo_loai=dict(c), hinh=v["ten"],
                    phong=[dict(id=e["id"], ten=e["ten"], dien_tich_m2=spec_e.fmt2(e["dien_tich"])) for e in v["elems"] if e["t"] == "phong"],
                    so_cua_di=c.get("cua_di", 0), so_cua_so=c.get("cua_so", 0), so_kich_thuoc=c.get("kich_thuoc", 0))
    if loai == "xa_go":
        return dict(so_truc_doc_N=sp["so_truc_doc"], so_cot=2 * sp["so_truc_doc"], chieu_dai_mat_doc_mm=round(sp["L"], 1), so_khoang_n=sp["n"], so_xa_go_moi_mai=sp["n"] + 1, tong_so_xa_go=sp["n_purlins_total"],
                    khoang_cach_thuc_mm=sp["real_spacing_text"], khoang_cach_chieu_mm=spec_d.fmt_len(sp["proj_spacing"]), goc_doc_do=round(sp["theta_deg"], 2), so_mai=sp["so_mai"])
    return dict(cao_dinh_mm=sp["y_top"], cao_dinh_chinh_xac=spec_c.fmt_exact(sp["y_top_exact"]),
                khoang_nho_mm=sp["rise"], goc_doc_do=round(sp["theta_deg"], 2), chieu_dai_keo_truc_mm=round(sp["raf_len"], 1), so_mai=sp["so_mai"])


def check(loai: str, spec_path: str, write_spec: str | None, profile: str | None):
    if loai not in LOAI:
        return dict(hop_le=False, loi=[f"loai = {loai!r} không hợp lệ. Dùng một trong: thang, luoi_cot, khung_ngang, xa_go, ve_tu_do."])
    try:
        lim = MAX_SPEC_BYTES_E if loai == "ve_tu_do" else MAX_SPEC_BYTES
        if os.path.getsize(spec_path) > lim:
            return dict(hop_le=False, loai=loai, loi=[f"spec quá lớn (> {lim} byte)."])
        def _bad_const(c):
            raise ValueError("NaN/Infinity")
        raw = json.load(open(spec_path, encoding="utf-8-sig"), parse_constant=_bad_const)
    except ValueError:
        return dict(hop_le=False, loai=loai, loi=["spec JSON không hợp lệ (lỗi cú pháp, hoặc có NaN/Infinity)."])
    except OSError:
        return dict(hop_le=False, loai=loai, loi=["không đọc được tệp spec."])
    if not isinstance(raw, dict):
        return dict(hop_le=False, loai=loai, loi=["spec phải là một đối tượng JSON {...}."])
    k = LOAI[loai]
    spec = dict(raw)
    canh_bao_them = []
    for ig in ("ten", "loai"):
        if ig in spec:
            spec.pop(ig)
            canh_bao_them.append(f"Khóa {ig!r} trong spec bị bỏ qua: {'tên bản vẽ do hệ thống tự sinh' if ig == 'ten' else 'loại lấy từ tham số loai của công cụ'}.")
    la = sorted(x for x in spec if x not in KHOA_HOP_LE[loai])
    if la:
        return dict(hop_le=False, loai=loai, loi=[f"Tham số không được hỗ trợ: {', '.join(repr(x[:40]) for x in la)}. Tham số hợp lệ của loại {loai}: {', '.join(sorted(KHOA_HOP_LE[loai]))}. "
                                                   "Kiểm tra lỗi gõ tên tham số (không bỏ qua im lặng)."])
    lon = [x for x, v in spec.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) > 1e7]
    if lon:
        return dict(hop_le=False, loai=loai, loi=[f"{x} có giá trị quá lớn (> 10 triệu); đơn vị là mm (hoặc % / số đếm)." for x in lon])
    thieu = [x for x in BAT_BUOC[loai] if spec.get(x) is None]
    if thieu:
        return dict(hop_le=False, loai=loai, thieu_bat_buoc=thieu,
                    loi=[f"Thiếu số bắt buộc: {', '.join(thieu)}. HÃY HỎI LẠI khách các số này (đơn vị mm trừ do_doc_mai là %, so_bac/so_mai là số đếm); không tự đoán."])
    da_dung = []
    for key, (val, note) in MAC_DINH[loai].items():
        if spec.get(key) is None:
            spec[key] = val
            da_dung.append(dict(ten=key, gia_tri=val, y_nghia=note))
    if k == "D":
        da_dung.extend(dict(ten=key, gia_tri=val, y_nghia=note) for key, (val, note) in MAC_DINH_D.items() if spec.get(key) is None)
    kt_in = spec.get("khung_ten")
    if not kt_in:
        import datetime
        kt = dict(KHUNG_TEN_MAU, cong_trinh=CONG_TRINH_MAU[loai], ngay=datetime.date.today().strftime("%d/%m/%Y"))
        spec["khung_ten"] = kt
        da_dung.append(dict(ten="khung_ten", gia_tri=kt, y_nghia="khách chưa cung cấp: dùng tên mẫu (giả lập) và ngày hôm nay; ô họ tên người ký để trống"))
    spec["loai"] = k
    import hashlib
    ten = auto_name(loai, spec)[:55] + "_" + hashlib.sha1(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:6]
    spec["ten"] = ten
    import build_a
    import build_b
    import build_c
    import build_d
    import build_e
    import spec_a
    import spec_b
    import spec_c
    import spec_d
    import spec_e
    from spec_b import SpecError
    from tcvn import ProfileError, read_profile
    validate, build = {"A": (spec_a.validate, build_a.build), "B": (spec_b.validate, build_b.build), "C": (spec_c.validate, build_c.build), "D": (spec_d.validate, build_d.build), "E": (spec_e.validate, build_e.build)}[k]
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
    res = dict(hop_le=True, loai=loai, ten=ten, kho_giay=D.info.get("sheet", "A3"), ty_le=sc, bo_cuc=D.info.get("layout"), ly_do=D.info["reason"], so_do=_derived(loai, sp, D),
               canh_bao=canh_bao_them + list(D.info.get("warnings", [])) + list(D.info.get("notes", [])), da_dung_mac_dinh=da_dung, thu_muc_ket_qua=f"out\\{ten}\\")
    if k in ("C", "D"):
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
