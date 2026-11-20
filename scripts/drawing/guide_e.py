"""Text of huong_dan_ve("ve_tu_do"): the ONLY thing Claude Desktop knows about drawing type E. Keep it exact: every element name, parameter and rule here must match spec_e.py."""
from __future__ import annotations

import elems3
import spec_e


def _p(ten, mo_ta, bat_buoc=True, mac_dinh=None):
    d = dict(ten=ten, bat_buoc=bat_buoc, mo_ta=mo_ta)
    if mac_dinh is not None:
        d["mac_dinh"] = mac_dinh
    return d


PT = "điểm [x, y] (mm)"
PHAN_TU = [
    dict(loai="truc", nhom="nền", mo_ta="Lưới trục có vòng ký hiệu: trục dọc (x = hằng) ghi ở đầu trên, trục ngang (y = hằng) ghi ở đầu trái. Mỗi hình có tối đa MỘT phần tử truc. Trục chạy suốt phạm vi các trục kia và vượt 5 mm trên giấy.",
         tham_so=[_p("truc_dung", "danh sách {\"ten\": \"1\", \"x\": số mm}; ten 1-3 ký tự, không trùng"), _p("truc_ngang", "danh sách {\"ten\": \"A\", \"y\": số mm}; ten 1-3 ký tự, không trùng")],
         vi_du={"loai": "truc", "truc_dung": [{"ten": "1", "x": 0}, {"ten": "2", "x": 4000}], "truc_ngang": [{"ten": "A", "y": 0}, {"ten": "B", "y": 3600}]}),
    dict(loai="tuong", nhom="mặt bằng", mo_ta="Tường nằm ngang/đứng. Vẽ 2 nét = đường bao của HỢP các thân tường (tự xử lý giao nhau và góc), bị cắt bởi cửa; 1 nét = đường tim tường nét đậm.",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("diem", "danh sách ≥ 2 điểm [x, y]; hai điểm liên tiếp phải cùng x hoặc cùng y (không tường xiên)"), _p("day", "bề dày tường, mm > 0"),
                  _p("kin", "true: nối điểm cuối về điểm đầu (≥ 3 điểm)", False, False), _p("can", "\"giua\" | \"trai\" | \"phai\": đường đi qua tim tường / tường nằm bên TRÁI / bên PHẢI hướng đi. Tường nhiều đoạn hoặc kín chỉ nhận \"giua\"", False, "giua"),
                  _p("kieu", "\"2_net\" | \"1_net\"", False, "2_net")],
         vi_du={"loai": "tuong", "id": "W1", "diem": [[0, 0], [4000, 0], [4000, 3600], [0, 3600]], "kin": True, "day": 220}),
    dict(loai="cua_di", nhom="mặt bằng", mo_ta="Cửa đi: cắt tường, vẽ khung (2 nét mảnh theo hai mặt tường), cánh vuông góc và cung mở 90°. Nằm trọn trong MỘT đoạn tường.",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("tuong", "id của tường"), _p("doan", "chỉ số đoạn của tường (từ 0; điểm i tới i+1; đoạn khép kín là đoạn cuối)", False, 0),
                  _p("vi_tri", "khoảng cách từ ĐIỂM ĐẦU đoạn tới mép đầu cửa, mm ≥ 0"), _p("rong", "bề rộng, mm > 0 (cửa đi hẹp hơn 700 mm bị cảnh báo mềm: kinh nghiệm thực tế, không phải điều khoản TCVN)"),
                  _p("ban_le", "\"dau\" | \"cuoi\": bản lề ở mép đầu / mép cuối (theo hướng đi của đoạn)"), _p("mo_ve", "\"trai\" | \"phai\": cánh mở về phía TRÁI / PHẢI hướng đi của đoạn")],
         vi_du={"loai": "cua_di", "id": "D1", "tuong": "W1", "doan": 0, "vi_tri": 500, "rong": 900, "ban_le": "dau", "mo_ve": "trai"}),
    dict(loai="cua_so", nhom="mặt bằng", mo_ta="Cửa sổ: cắt tường, vẽ ký hiệu nét kép hoặc nét ba trong bề dày tường.",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("tuong", "id của tường"), _p("doan", "như cua_di", False, 0), _p("vi_tri", "như cua_di"), _p("rong", "mm > 0"), _p("ky_hieu", "\"kep\" (2 nét tại 1/3 và 2/3 bề dày) | \"ba\" (3 nét tại mặt trái, giữa, mặt phải)", False, "kep")],
         vi_du={"loai": "cua_so", "id": "S1", "tuong": "W1", "doan": 2, "vi_tri": 1100, "rong": 1500, "ky_hieu": "kep"}),
    dict(loai="o_trong", nhom="mặt bằng", mo_ta="Ô trống (cửa không cánh): chỉ cắt tường.", tham_so=[_p("id", "chuỗi duy nhất"), _p("tuong", "id của tường"), _p("doan", "như cua_di", False, 0), _p("vi_tri", "mm ≥ 0"), _p("rong", "mm > 0")],
         vi_du={"loai": "o_trong", "id": "O1", "tuong": "W1", "doan": 1, "vi_tri": 800, "rong": 1200}),
    dict(loai="phong", nhom="mặt bằng", mo_ta="Phòng: nhãn tên + diện tích (m², tính từ đa giác, 2 chữ số thập phân). Đa giác là mép TRONG của phòng (gồm cạnh ngang/đứng).",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("ten", "tên phòng, in hoa"), _p("da_giac", "danh sách ≥ 3 điểm [x, y] của mép trong phòng"), _p("vi_tri_nhan", PT + " trong phòng; bỏ trống = tâm hộp bao (nếu nằm ngoài phòng hình L thì bắt buộc nhập)", False)],
         vi_du={"loai": "phong", "id": "P1", "ten": "PHÒNG NGỦ", "da_giac": [[110, 110], [3890, 110], [3890, 3490], [110, 3490]]}),
    dict(loai="noi_that_co_ban", nhom="mặt bằng", mo_ta="Nội thất dạng khối chữ nhật có nhãn, kích thước thật. kieu và kích thước mặc định: " + "; ".join(f"{k} {w}x{d}" for k, (w, d, _) in spec_e.FURNITURE.items()) + " (mm, rộng x sâu).",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("kieu", "một trong: " + ", ".join(spec_e.FURNITURE)), _p("vi_tri", "góc DƯỚI-TRÁI của hộp bao (sau khi xoay), " + PT), _p("xoay", "0 | 90 | 180 | 270", False, 0), _p("kich_thuoc", "[rộng, sâu] mm để thay kích thước mặc định", False)],
         vi_du={"loai": "noi_that_co_ban", "id": "G1", "kieu": "giuong", "vi_tri": [2290, 1490]}),
    dict(loai="kich_thuoc", nhom="kích thước", mo_ta="Kích thước TỰ ĐO từ hình: KHÔNG có tham số nhập số. Chỉ nêu tham chiếu. Đường kích thước nằm ngoài hình, lớp 1 gần nhất (10 mm giấy), lớp 2, 3 cách nhau 7 mm. Chữ tự đẩy ra ngoài khi nhịp quá hẹp.",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("kieu", "\"ngang\" | \"doc\" | \"chuoi\" | \"song_song\" | \"ban_kinh\" | \"duong_kinh\" | \"goc\""),
                  _p("tham_chieu", "ngang/doc: đúng 2 tham chiếu; chuoi: ≥ 3 tham chiếu tăng dần; song_song: 2 điểm [x, y]"), _p("huong", "chỉ cho chuoi: \"ngang\" | \"doc\""),
                  _p("phia", "ngang/chuoi ngang: \"duoi\" | \"tren\"; doc/chuoi dọc: \"trai\" | \"phai\"; song_song: \"trai\" | \"phai\" so với hướng điểm 1 → điểm 2", False),
                  _p("lop", "1 | 2 | 3 (lớp kích thước từ hình ra ngoài)", False, 1), _p("khoang", "song_song: khoảng cách đường kích thước tới hai điểm, mm GIẤY", False, 10),
                  _p("phan_tu", "ban_kinh/duong_kinh: id của tron hoặc cung"), _p("goc", "ban_kinh/duong_kinh: hướng đường dẫn, độ", False, 45), _p("dinh", "goc: đỉnh góc " + PT), _p("tia1", "goc: điểm trên tia 1"), _p("tia2", "goc: điểm trên tia 2"),
                  _p("ban_kinh_cung", "goc: bán kính cung kích thước, mm GIẤY", False, 15)],
         tham_chieu_cu_phap=["số: toạ độ (x cho kích thước ngang, y cho kích thước dọc)", "\"truc:<ten>\": vị trí trục (trục dọc → x, trục ngang → y)",
                             "\"<id tường>:<mốc>\" hoặc \"<id tường>#<chỉ số đoạn>:<mốc>\": mốc trai | phai | giua (mặt/tim tường, toạ độ vuông góc với tường), dau | cuoi (đầu/cuối đoạn, toạ độ dọc theo tường)",
                             "\"<id cửa>:dau\" | \":cuoi\": mép đầu / cuối cửa, ô trống", "\"<id phòng | nội thất | tròn | cung>:tay|dong|nam|bac\": biên tây/đông (x), nam/bắc (y) của hộp bao"],
         vi_du=[{"loai": "kich_thuoc", "id": "K1", "kieu": "ngang", "tham_chieu": ["truc:1", "truc:2"], "phia": "duoi", "lop": 2},
                {"loai": "kich_thuoc", "id": "K2", "kieu": "chuoi", "huong": "ngang", "tham_chieu": ["W1:trai", "D1:dau", "D1:cuoi", "truc:2"], "phia": "duoi"},
                {"loai": "kich_thuoc", "id": "K3", "kieu": "doc", "tham_chieu": ["truc:A", "truc:B"], "phia": "phai"}]),
    dict(loai="ghi_chu", nhom="chữ", mo_ta="Ghi chú nhiều dòng tại một điểm. Mỗi dòng dưới 115 mm trên giấy (dài hơn thì báo lỗi: ngắt dòng).",
         tham_so=[_p("chu", "chuỗi hoặc danh sách chuỗi (mỗi phần tử một dòng)"), _p("vi_tri", "điểm neo (đầu dòng đầu, đường chân chữ), " + PT), _p("can", "\"trai\" | \"giua\" | \"phai\"", False, "trai"),
                  _p("cao", "chiều cao chữ trên giấy: 2.5 | 3.5 | 5 mm", False, 2.5), _p("dam", "chữ đậm", False, False)],
         vi_du={"loai": "ghi_chu", "chu": ["GHI CHÚ:", "TƯỜNG GẠCH DÀY 220 MM"], "vi_tri": [-600, -1300]}),
    dict(loai="tieu_de_hinh", nhom="chữ", mo_ta="(tuỳ chọn) đổi chữ tên hình in dưới hình; mặc định là hinh.ten. Tỷ lệ \"TỶ LỆ 1:N\" luôn tự in dưới tên.", tham_so=[_p("chu", "tên hình in đậm", False)],
         vi_du={"loai": "tieu_de_hinh", "chu": "MẶT BẰNG TẦNG 1"}),
    dict(loai="mui_ten_bac", nhom="chữ", mo_ta="Mũi tên hướng bắc: vòng tròn Ø14 mm giấy, tam giác, chữ B.", tham_so=[_p("vi_tri", "tâm, " + PT), _p("goc", "độ, ngược chiều kim đồng hồ từ trục y (0 = bắc hướng lên)", False, 0)],
         vi_du={"loai": "mui_ten_bac", "vi_tri": [4900, 3300], "goc": 0}),
    dict(loai="duong", nhom="phần tử thô", mo_ta="Đoạn thẳng.", tham_so=[_p("tu", PT), _p("den", PT), _p("lop", "NET-CHINH | NET-MANH | NET-KHUAT | NET-TAM", False, "NET-MANH")], vi_du={"loai": "duong", "tu": [0, 0], "den": [1000, 500], "lop": "NET-MANH"}),
    dict(loai="polyline", nhom="phần tử thô", mo_ta="Đường gấp khúc (các đoạn thẳng).", tham_so=[_p("diem", "≥ 2 điểm"), _p("kin", "nối về điểm đầu", False, False), _p("lop", "như duong", False, "NET-MANH")], vi_du={"loai": "polyline", "diem": [[0, 0], [500, 0], [500, 500]], "kin": False}),
    dict(loai="cung", nhom="phần tử thô", mo_ta="Cung tròn quét NGƯỢC chiều kim đồng hồ từ goc_dau tới goc_cuoi (độ). Vẽ bằng chuỗi đoạn thẳng (24 đoạn mỗi 90°).",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("tam", PT), _p("ban_kinh", "mm > 0"), _p("goc_dau", "độ"), _p("goc_cuoi", "độ (khác goc_dau)"), _p("lop", "như duong", False, "NET-MANH")],
         vi_du={"loai": "cung", "id": "C1", "tam": [0, 0], "ban_kinh": 500, "goc_dau": 0, "goc_cuoi": 90}),
    dict(loai="tron", nhom="phần tử thô", mo_ta="Vòng tròn.", tham_so=[_p("id", "chuỗi duy nhất"), _p("tam", PT), _p("ban_kinh", "mm > 0"), _p("lop", "như duong", False, "NET-MANH")],
         vi_du={"loai": "tron", "id": "C2", "tam": [2000, 2000], "ban_kinh": 300}),
    dict(loai="chu", nhom="phần tử thô", mo_ta="Một dòng chữ tại một điểm (lớp CHU).", tham_so=[_p("chu", "chuỗi một dòng"), _p("vi_tri", "điểm neo " + PT), _p("cao", "2.5 | 3.5 | 5 mm giấy", False, 2.5), _p("can", "trai | giua | phai", False, "trai"), _p("dam", "đậm", False, False)],
         vi_du={"loai": "chu", "chu": "BẾP", "vi_tri": [1000, 1000]}),
]

PHAN_TU += [
    dict(loai="lop_vat_lieu", nhom="mặt cắt / chi tiết", mo_ta="Các lớp vật liệu song song, mỗi lớp một hình chữ nhật có hatch. huong \"ngang\": các lớp xếp chồng theo y (từ dưới lên), dài theo x; huong \"dung\": xếp theo x (từ trái sang phải), dài theo y. Vật liệu (danh sách đóng): be_tong, gach, vua, dat, thep (hatch 45° hoặc 135°, khoảng cách cố định theo vật liệu).",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("goc", "góc dưới-trái của lớp đầu, " + PT), _p("huong", "\"ngang\" | \"dung\""), _p("dai", "chiều dài mỗi lớp, mm > 0"), _p("lop", "danh sách {\"vat_lieu\": ..., \"day\": mm > 0}"), _p("tong_day", "(tuỳ chọn) tổng bề dày khai báo; không bằng tổng các lớp thì báo lỗi", False)],
         vi_du={"loai": "lop_vat_lieu", "id": "NEN", "goc": [-600, -300], "huong": "ngang", "dai": 4200, "lop": [{"vat_lieu": "dat", "day": 150}, {"vat_lieu": "be_tong", "day": 100}, {"vat_lieu": "vua", "day": 50}], "tong_day": 300}),
    dict(loai="san", nhom="mặt cắt / chi tiết", mo_ta="Sàn / dầm / cột (mặt cắt hoặc mặt đứng) dạng hình chữ nhật có hatch. Ba loại san, dam, cot_mc cùng tham số.", tham_so=[_p("id", "chuỗi duy nhất"), _p("hcn", "[x0, y0, x1, y1] mm, x1 > x0, y1 > y0"), _p("vat_lieu", "be_tong | gach | vua | dat | thep", False, "be_tong")],
         vi_du={"loai": "san", "id": "SAN", "hcn": [-100, 3000, 3000, 3120]}),
    dict(loai="mong_don", nhom="mặt cắt / chi tiết", mo_ta="Móng đơn dạng bậc: bê tông lót, đế móng, cổ móng (cùng trục giữa), mỗi khối có hatch bê tông.", tham_so=[_p("id", "chuỗi duy nhất"), _p("goc", "góc dưới-trái của lớp lót"), _p("dai_lot", "mm"), _p("day_lot", "mm"), _p("dai_mong", "mm, ≤ dai_lot"), _p("day_mong", "mm"), _p("dai_co", "mm, ≤ dai_mong"), _p("cao_co", "mm")],
         vi_du={"loai": "mong_don", "id": "M1", "goc": [0, -1100], "dai_lot": 1300, "day_lot": 100, "dai_mong": 1100, "day_mong": 300, "dai_co": 300, "cao_co": 700}),
    dict(loai="cot_chi_tiet", nhom="mặt cắt / chi tiết", mo_ta="Mặt cắt cột: hình chữ nhật bê tông, thép đai (lùi bao_ve), thép dọc (vòng tròn) dàn đều ở hàng trên và hàng dưới.", tham_so=[_p("id", "chuỗi duy nhất"), _p("hcn", "[x0, y0, x1, y1]"), _p("bao_ve", "lớp bê tông bảo vệ, mm"), _p("d", "đường kính thép dọc, mm"), _p("n_tren", "số thanh hàng trên, 2-20"), _p("n_duoi", "số thanh hàng dưới, 2-20")],
         vi_du={"loai": "cot_chi_tiet", "id": "CT", "hcn": [3200, -400, 3500, 0], "bao_ve": 25, "d": 16, "n_tren": 2, "n_duoi": 2}),
    dict(loai="cua_dung", nhom="mặt đứng", mo_ta="Cửa trên mặt đứng: khung ngoài, cánh lùi 60 mm; kieu \"so\": một thanh đứng giữa; kieu \"di\": hai nét đứt hình chữ V chỉ chiều mở (đỉnh V ở phía KHÔNG có bản lề).", tham_so=[_p("id", "chuỗi duy nhất"), _p("hcn", "[x0, y0, x1, y1], rộng và cao hơn 120 mm"), _p("kieu", "\"di\" | \"so\""), _p("ban_le", "\"trai\" | \"phai\" (chỉ cho kieu di)", False, "trai")],
         vi_du={"loai": "cua_dung", "id": "CD1", "hcn": [1000, 0, 2100, 2200], "kieu": "di", "ban_le": "trai"}),
    dict(loai="mai", nhom="mặt đứng / mặt cắt", mo_ta="Mái: hai đường (mặt trên và mặt dưới, cách nhau day theo phương đứng) và hai đầu hồi. kieu: \"bang\" (nằm ngang), \"1_mai\" (dốc lên về phía phải), \"2_mai\" (đỉnh giữa nhịp). tu là điểm mép trên trái ở trục trái; vuon là phần nhô ra hai bên theo phương ngang, giữ nguyên độ dốc.",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("kieu", "bang | 1_mai | 2_mai"), _p("tu", PT), _p("nhip", "mm"), _p("do_doc", "% trong (0, 100]; bỏ trống với bang", False), _p("day", "bề dày theo phương đứng, mm"), _p("vuon", "mm", False, 0)],
         vi_du={"loai": "mai", "id": "M1", "kieu": "2_mai", "tu": [0, 3300], "nhip": 9000, "do_doc": 30, "day": 120, "vuon": 600}),
    dict(loai="lan_can", nhom="mặt đứng / mặt cắt", mo_ta="Lan can: các trụ đứng cách đều (khoảng ≤ buoc), tay vịn trên cùng và thanh giữa. Cao dưới 900 mm bị cảnh báo mềm (kinh nghiệm thực tế, không phải điều khoản TCVN).", tham_so=[_p("id", "chuỗi duy nhất"), _p("tu", "góc dưới-trái, " + PT), _p("dai", "mm"), _p("cao", "mm"), _p("buoc", "khoảng cách tối đa giữa các trụ, mm")],
         vi_du={"loai": "lan_can", "id": "LC", "tu": [0, 3000], "dai": 3000, "cao": 1000, "buoc": 1000}),
    dict(loai="bac_thang_don_gian", nhom="mặt cắt", mo_ta="Mặt cắt bậc thang: đường gấp khúc so_bac bậc. 2h + b ngoài 600-630 mm bị cảnh báo mềm (kinh nghiệm thực tế, không phải điều khoản TCVN).", tham_so=[_p("id", "chuỗi duy nhất"), _p("tu", "chân bậc đầu, " + PT), _p("so_bac", "2-60"), _p("cao_bac", "mm"), _p("rong_bac", "mm")],
         vi_du={"loai": "bac_thang_don_gian", "id": "BT", "tu": [0, 0], "so_bac": 10, "cao_bac": 170, "rong_bac": 270}),
    dict(loai="cao_do", nhom="ký hiệu", mo_ta="Ký hiệu cao độ (tam giác + gạch ngang + chữ). Chữ TỰ TÍNH = cao_m của mức tham chiếu + (y - y tham chiếu)/1000, 3 chữ số thập phân; mức tham chiếu khai ở hinh.mo_cao = {\"y\": mm, \"cao_m\": m} (mặc định y 0 ứng với ±0.000). CẢNH BÁO MỀM: nếu độ cao (y) của vi_tri không trùng (±1 mm) mốc nào của cùng hình (mo_cao, mặt sàn, mép dầm, đỉnh/chân cột và móng, đỉnh và đáy mái, ranh giới các lớp, lan can, bậc thang, mép cửa) thì có cảnh báo nêu phần tử và mốc gần nhất (kinh nghiệm thực tế, KHÔNG phải điều khoản TCVN); bản vẽ vẫn dựng. Đỉnh mái 2 mái = tu.y + nhip/2 × do_doc%.",
         tham_so=[_p("vi_tri", "mũi tam giác " + PT), _p("huong", "\"phai\" | \"trai\" (gạch ngang kéo về phía nào)", False, "phai")], vi_du={"loai": "cao_do", "vi_tri": [9600, 3300], "huong": "phai"}),
    dict(loai="ghi_chu_dan", nhom="ký hiệu", mo_ta="Ghi chú có đường dẫn: mũi tên 45° tại diem, đường dẫn tới vi_tri, chữ nằm bên phải (hoặc bên trái nếu vi_tri ở bên trái diem). Chữ không được chạm nét khác. Đường dẫn KHÔNG được cắt qua nét khác (chỉ được kết thúc ngay trên nét cần chỉ tới): đặt diem trên nét, không đặt trong lòng một hình rồi kéo ra ngoài.", tham_so=[_p("chu", "chuỗi hoặc danh sách dòng"), _p("diem", "điểm chỉ tới " + PT), _p("vi_tri", "đầu kia của đường dẫn " + PT), _p("cao", "2.5 | 3.5 | 5", False, 2.5), _p("dam", "đậm", False, False)],
         vi_du={"loai": "ghi_chu_dan", "chu": ["BÊ TÔNG LÓT"], "diem": [1500, -200], "vi_tri": [2200, -900]}),
    dict(loai="dau_cat", nhom="ký hiệu", mo_ta="Dấu cắt mặt cắt: đường đậm từ tu tới den (ngang hoặc đứng) và hai cánh dài 8 mm giấy về phía nhìn, chữ ten ở đầu mỗi cánh.", tham_so=[_p("id", "chuỗi duy nhất"), _p("ten", "1-3 ký tự"), _p("tu", PT), _p("den", PT), _p("nhin", "tren | duoi (đường ngang); trai | phai (đường đứng)")],
         vi_du={"loai": "dau_cat", "id": "DC1", "ten": "1", "tu": [0, 1500], "den": [4000, 1500], "nhin": "tren"}),
    dict(loai="tuyen_gio", nhom="ký hiệu", mo_ta="Tuyến gió (trục) trên mặt đứng: đường chấm gạch thẳng đứng từ tu_y tới den_y và vòng ký hiệu ở đầu trên.", tham_so=[_p("id", "chuỗi duy nhất"), _p("ten", "1-3 ký tự"), _p("x", "mm"), _p("tu_y", "mm"), _p("den_y", "mm, lớn hơn tu_y")],
         vi_du={"loai": "tuyen_gio", "id": "G1", "ten": "1", "x": 0, "tu_y": -450, "den_y": 5000}),
]

PHAN_TU += [
    dict(loai="ky_hieu", nhom="điện nước", mo_ta="Ký hiệu điện / nước lấy từ thư viện cố định (thu_vien_ky_hieu), kích thước CỐ ĐỊNH trên giấy, tâm = vi_tri (cũng là nút nối dây/ống), xoay bội số 90°.",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("kieu", "o_cam | cong_tac | den | quat | bang_dien | bon_cau | chau_rua | voi | van | dong_ho_nuoc"), _p("vi_tri", PT), _p("xoay", "0 | 90 | 180 | 270 (mặc định 0)", False)],
         vi_du={"loai": "ky_hieu", "id": "O1", "kieu": "o_cam", "vi_tri": [3700, 2200], "xoay": 90}),
    dict(loai="nut", nhom="điện nước", mo_ta="Nút nối (chấm tròn nhỏ) để dây/ống nối vào nơi không có thiết bị: chỗ rẽ nhánh, chỗ đi ra khỏi phòng.", tham_so=[_p("id", "chuỗi duy nhất"), _p("vi_tri", PT)],
         vi_du={"loai": "nut", "id": "N1", "vi_tri": [500, 3100]}),
    dict(loai="ong", nhom="điện nước", mo_ta="Đường dây điện / ống cấp / ống thoát: đường gấp khúc, điểm ĐẦU và điểm CUỐI phải trùng đúng vị trí một ky_hieu hoặc nut đã khai (không đầu mút lơ lửng; lệch là LỖI). Kiểu nét theo loại, chỉ dùng layer có sẵn.",
         tham_so=[_p("id", "chuỗi duy nhất"), _p("loai_ong", "day_dien (NET-TAM, chấm gạch) | ong_cap (NET-CHINH, nét đậm) | ong_thoat (NET-KHUAT, nét đứt)"), _p("diem", "danh sách >= 2 điểm [x, y] mm, hai điểm liên tiếp không trùng nhau")],
         vi_du={"loai": "ong", "id": "C1", "loai_ong": "ong_cap", "diem": [[1800, 300], [1800, 1200]]}),
    dict(loai="chu_giai", nhom="điện nước", mo_ta="Chú giải TỰ SINH: liệt kê đúng các ký hiệu và loại đường đã dùng (thứ tự cố định: ký hiệu điện, ký hiệu nước, rồi loại đường) dưới tiêu đề CHÚ GIẢI; nét mẫu của dây/ống dài 20 mm giấy và ĐÚNG kiểu nét với đường thật (dây điện chấm gạch, ống cấp nét liền đậm, ống thoát nét đứt); vi_tri = góc trên-trái, tối đa một lần mỗi hình.",
         tham_so=[_p("vi_tri", PT)], vi_du={"loai": "chu_giai", "vi_tri": [5200, 3400]}),
]

PHAN_TU.insert([p["loai"] for p in PHAN_TU].index("san"), dict(
    loai="mat_tuong_dung", nhom="mặt đứng", mo_ta="Mặt tường / dầm / cột nhìn từ ngoài (mặt đứng): hình chữ nhật KHÔNG hatch (mặt đứng không hatch vật liệu); tuỳ chọn vat_lieu_hatch nếu cần hatch.",
    tham_so=[_p("id", "chuỗi duy nhất"), _p("hcn", "[x0, y0, x1, y1] mm, x1 > x0, y1 > y0"), _p("vat_lieu_hatch", "be_tong | gach | vua | dat | thep; bỏ trống = không hatch", False)],
    vi_du={"loai": "mat_tuong_dung", "id": "MT1", "hcn": [0, 0, 9000, 2950]}))

LAYERS = {"tuong": "NET-CHINH (nét đậm)", "cửa đi / cửa sổ / nội thất / mũi tên bắc / phần tử thô mặc định": "NET-MANH (nét mảnh)", "trục": "TRUC (nét chấm gạch) + TRUC-KYHIEU (vòng, chữ)", "kích thước": "KICH-THUOC",
          "chữ (nhãn phòng, ghi chú, tên hình, nhãn nội thất)": "CHU", "hatch vật liệu": "MAT-CAT", "cửa đứng nét khuất (chiều mở)": "NET-KHUAT", "phần tử thô": "NET-CHINH | NET-MANH | NET-KHUAT (nét đứt) | NET-TAM (nét chấm gạch) theo tham số lop"}


def guide() -> dict:
    return dict(
        mo_ta="Bản vẽ tự do (loại E) cho công trình dân dụng ngoài 4 loại chuẩn: dựng từ một danh sách PHẦN TỬ có sẵn (tường, cửa, phòng, nội thất, kích thước tự đo, chữ...) rồi vẽ ra DXF + DWG + PDF + PNG với khung tên TCVN 5571:2012, khổ A3/A2/A1 và tỷ lệ tự chọn, kèm kiểm tra tự động. Giai đoạn hiện tại: MỘT hình trên một tờ (mặt bằng, mặt đứng, mặt cắt, chi tiết cấu tạo); sơ đồ điện / cấp thoát nước một phòng (ký hiệu, dây/ống, chú giải) có ở mức tối thiểu; NHIỀU HÌNH trên một tờ CHƯA có.",
        quy_trinh=["1. Hỏi khách các số còn thiếu (kích thước phòng, bề dày tường, vị trí/bề rộng cửa...). KHÔNG tự đoán số; không có số thì HỎI.",
                   "2. Soạn spec JSON theo danh mục dưới đây; KHÔNG viết mã FreeCAD hay Python. Chỉ dùng các phần tử trong danh mục.",
                   "3. LUÔN gọi kiem_tra_spec trước. Lỗi báo đúng phần tử (chỉ số phan_tu) và tham số: sửa theo thông báo rồi gọi lại. Trình bày cho khách bảng số liệu (kích thước phòng, diện tích, số cửa, khổ giấy, tỷ lệ, cảnh báo) và CHỜ khách nói OK.",
                   "4. Chỉ khi khách OK mới gọi ve_ban_ve (chạy nền 30-60 giây), rồi gọi trang_thai_ban_ve(job_id) cho tới khi xong. Báo đường dẫn tệp và kết quả kiểm tra tự động."],
        he_toa_do="Đơn vị mm. Trục x sang phải, trục y lên trên (toạ độ thật, không co tỷ lệ). Gốc tuỳ ý (khuyến nghị gốc tại giao trục 1/A). \"TRÁI/PHẢI hướng đi\" nghĩa là bên trái/phải khi đi dọc đoạn tường từ điểm đầu tới điểm cuối.",
        cau_truc_spec=dict(ty_le="\"auto\" (mặc định; thử 1:20, 1:50, 1:100, 1:200, 1:500) hoặc một trong 1:2, 1:5, 1:10, 1:20, 1:50, 1:100, 1:200, 1:500 (1:2, 1:5, 1:10 chỉ khi chỉ định, dùng cho chi tiết)",
                           kho_giay="\"auto\" (ưu tiên A3, lên A2 rồi A1 khi cần ở tỷ lệ ≤ 1:200) | \"A3\" | \"A2\" | \"A1\"", khung_ten="như các loại khác (don_vi_tk, cong_trinh, chu_dau_tu, ten_ban_ve, ky_hieu_ban_ve mặc định KT-01, loai_ho_so, ngay dd/mm/yyyy, ...)",
                           hinh="danh sách đúng MỘT hình: {\"id\": \"MB1\", \"ten\": \"MẶT BẰNG TẦNG 1\", \"phan_tu\": [ ...phần tử... ]}", tham_so="ghi đè tham số bố cục (mm giấy), như luoi_cot (tuỳ chọn)"),
        phan_tu=PHAN_TU,
        layer=LAYERS,
        thu_vien_ky_hieu=dict(
            ky_hieu={k: dict(ten=v[0], nhom=("điện" if v[1] == "dien" else "nước")) for k, v in elems3.SYMBOLS.items()},
            loai_duong={k: dict(ten=v[0], layer=v[1]) for k, v in elems3.PIPES.items()},
            ghi_chu="Kích thước ký hiệu cố định trên giấy (mm giấy, nhân tỷ lệ khi quy ra mm thật); tên tiếng Việt do chú giải tự in. Hệ thống CHỈ kiểm tra HÌNH HỌC và BỐ CỤC (ký hiệu đúng hình/vị trí/chiều xoay, đường nối đúng vào thiết bị hoặc nút, chú giải đủ và đúng thứ tự). KHÔNG kiểm tra thiết kế điện / cấp thoát nước có đúng quy chuẩn hay không (tải, tiết diện dây, đường kính ống, độ dốc, khoảng cách an toàn...): người thiết kế chịu trách nhiệm."),
        gioi_han=["Tối đa 2000 phần tử mỗi spec; tối đa 1 hình mỗi tờ (giai đoạn này); spec tối đa 300000 byte.", "Mỗi dòng chữ ghi chú dưới 115 mm trên giấy.", "Tường chỉ nằm ngang hoặc đứng; đa giác phòng chỉ có cạnh ngang/đứng.",
                  "Mỗi hình phải nằm gọn vùng vẽ (khung trừ góc khung tên 180×65); nếu không vừa A1 ở tỷ lệ nào thì báo lỗi kèm kích thước cần.", "Chữ không được chạm nét tường/trục/cửa hay chữ khác: builder tự tìm vị trí nhãn, không tìm được thì báo lỗi nêu phần tử; ghi_chu/chu đặt đúng vị trí khách chọn nên có thể phải dịch vi_tri.",
                  "Nhiều hình trên một tờ: CHƯA có (mỗi tờ đúng một hình). Sơ đồ điện nước chỉ kiểm tra hình học và bố cục, KHÔNG kiểm tra thiết kế theo quy chuẩn điện / cấp thoát nước.", "Cung tròn vẽ bằng chuỗi đoạn thẳng (24 đoạn / 90°); kích thước là LINE + TEXT (không phải DIMENSION)."],
        canh_bao_mem=["ký hiệu cao độ không trùng mốc nào của hình (±1 mm); cửa đi hẹp hơn 700 mm; tường dày ngoài 100-500 mm. Đều là kinh nghiệm thực tế, KHÔNG phải điều khoản TCVN: nêu cho khách rồi để người thiết kế xác nhận."],
        loi_thuong_gap=["cửa nằm ngoài tường: vi_tri + rong > chiều dài đoạn tường → giảm vi_tri hoặc rong, hoặc chọn đúng chỉ số doan.", "tường độ dày 0 hoặc âm; id trùng; kích thước tham chiếu tới id/mốc không tồn tại; kích thước dọc dùng mốc x (tay/dong/\"truc:1\")."],
    )
