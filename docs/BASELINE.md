# BASELINE — kết quả kiểm tra nền (18/11/2026)

Mục đích: ghi lại cái gì **đã chạy được thật** trên máy dev trước mốc khách test Chủ nhật 22/11/2026.
Mọi thời gian là số đo thực tế trên máy này (Windows 10 Pro 19045). Chỗ nào chưa chạy được thì ghi
rõ "CHƯA CHẠY", không suy đoán.

## Tổng hợp nhanh

| Bước | Hạng mục | Trạng thái |
| --- | --- | --- |
| 0 | Kiểm tra môi trường | PASS (thiếu FreeCAD lúc đầu) |
| 1 | Fork + clone + branch `feat/techdraw-2d` | PASS |
| 2 | Cài FreeCAD 1.1.4 (uv đã có sẵn) | PASS ở lần thử thứ 2 |
| 3 | Chép addon vào FreeCAD | Chép PASS; **RPC 9875 chưa kiểm tra** (cần bạn bật FreeCAD GUI) |
| 4 | Nối Claude Desktop (`freecad-dev`) | Ghi config PASS; **chưa thử trong Claude Desktop** (cần thoát hẳn/mở lại) |
| 5 | Smoke test với GUI (`get_rpc_status`, hộp có lỗ + `get_view`, demo flange) | **CHƯA CHẠY** (làm cùng bạn) |
| 5 | `execute_code_headless` qua MCP | PASS (làm được không cần GUI) |
| 6 | TechDraw: 3 hình chiếu A4 → DXF / PDF / SVG | PASS (PDF/SVG cần GUI ẩn, không làm được chỉ bằng FreeCADCmd) |
| — | Baseline test của upstream | 441 pass, 5 skip, **2 fail** (xem dưới) |

## Bước 0 — Môi trường

| Công cụ | Kết quả |
| --- | --- |
| Windows | 10 Pro 19045 |
| git | 2.56.0 |
| gh | 2.102.0; đã đăng nhập tài khoản `TanThinh1`, scope `repo`, `workflow` |
| uv | 0.13.7 (cài qua winget; có sẵn nên bỏ qua cài uv) |
| python | 3.12.10 |
| FreeCAD | **chưa cài** lúc đầu (không có FreeCADCmd, registry, winget) |
| Claude Desktop | bản MSIX/Store (`Claude_pzs8sxrjxfjjc`), đang chạy |

## Bước 1 — Fork và clone

- `gh repo fork neka-nat/freecad-mcp --clone --default-branch-only` → fork `TanThinh1/freecad-mcp`.
- `origin` = fork của bạn, `upstream` = `neka-nat/freecad-mcp` (fetch). Base: `main` @ `246f608` (v0.1.32).
- Đã **khoá push tới upstream** bằng `git remote set-url --push upstream DISABLED_no_push_to_upstream`
  (cấu hình cục bộ trong `.git/config`, không ảnh hưởng repo gốc).
- Branch làm việc: `feat/techdraw-2d`.

## Bước 2 — Cài FreeCAD

| Lần thử | Lệnh | Kết quả |
| --- | --- | --- |
| 1 | `winget install --id FreeCAD.FreeCAD --version 1.1.4 --scope user --silent` | **FAIL** sau 69 s, mã `0x800704c7` (bị huỷ, thường do UAC/quyền) |
| 2 | `winget install --id FreeCAD.FreeCAD --version 1.1.4 --silent` | PASS sau 170 s |

- Cài vào `%LOCALAPPDATA%\Programs\FreeCAD 1.1` (không phải Program Files).
- `FreeCADCmd.exe --version` → `FreeCAD 1.1.4 Revision: 20260928`, Python 3.11.14, chạy 0,7 s.
- **FreeCADCmd không nằm trên PATH.** Hệ quả: `execute_code_headless` không tự tìm được → phải truyền
  `--freecadcmd` (xem Bước 4).

## Bước 3 — Addon

- Thư mục Mod đúng cho FreeCAD 1.1.4 trên Windows: **`%APPDATA%\FreeCAD\v1-1\Mod\`** (FreeCAD tự báo
  `getUserAppDataDir()`, khớp `docs/installation.md`). Đề bài ghi `%APPDATA%\FreeCAD\Mod\` — đó là đường
  của bản cũ không đánh version nên **không dùng**.
- Đã chép `addon/FreeCADMCP` → `%APPDATA%\FreeCAD\v1-1\Mod\FreeCADMCP` (23 file, hash SHA-256 trùng nguồn,
  `InitGui.py` nằm ngay dưới `FreeCADMCP`, không lồng thư mục). Addon version 0.1.32.
- Cổng RPC `127.0.0.1:9875`: lúc kiểm tra **chưa lắng nghe** vì FreeCAD GUI chưa được bật. Việc cần làm tay:
  mở FreeCAD → chọn workbench **MCP Addon** → menu **FreeCAD MCP** → bật **Auto-Start Server** (hoặc bấm
  **Start RPC Server**).
- Kiểm tra cổng:
  `Test-NetConnection 127.0.0.1 -Port 9875` rồi
  `py -3.12 -c "import socket, xmlrpc.client; socket.setdefaulttimeout(5); s = xmlrpc.client.ServerProxy('http://127.0.0.1:9875'); print(s.ping()); print(s.get_rpc_status())"`.

## Bước 4 — Claude Desktop

- Claude Desktop ở máy này là **bản MSIX**: config nằm ở
  `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`,
  **không** phải `%APPDATA%\Claude\`.
- Lúc kiểm tra, file `claude_desktop_config.json` **không tồn tại**; chỉ còn
  `claude_desktop_config.json.bak-20261115-174922` chứa 1 MCP server của một dự án khác.
- Theo lựa chọn của bạn: tạo file mới **chỉ có `freecad-dev`**, **không** đụng `.bak`, **không** khôi phục
  server đó. Nếu cần server đó, hãy tự thêm lại từ `.bak`.
- Mục đã ghi (UTF-8 không BOM):

```json
{
  "mcpServers": {
    "freecad-dev": {
      "command": "uv",
      "args": [
        "--directory", "<đường dẫn tuyệt đối tới fork>",
        "run", "freecad-mcp",
        "--freecadcmd", "<FreeCAD>\\bin\\FreeCADCmd.exe"
      ]
    }
  }
}
```

- Đã thêm `--freecadcmd` (ngoài yêu cầu gốc) vì FreeCADCmd không có trên PATH. **Chưa** thêm
  `--only-text-feedback`: bật nó nếu muốn tiết kiệm token; `get_view` vẫn trả ảnh khi có cờ này.
- Kiểm chứng **ngoài Claude Desktop** bằng một MCP client stdio chạy đúng command/args trong config:
  khởi tạo 6,8 s, liệt kê **18 tool**; `get_rpc_status` báo lỗi kết nối rõ ràng khi FreeCAD GUI chưa bật
  (đúng kỳ vọng). **Việc cần làm tay:** thoát hẳn Claude Desktop (kể cả khay hệ thống) rồi mở lại.

## Bước 5 — Smoke test

### Đã chạy được (không cần GUI)

| Mục | Kết quả |
| --- | --- |
| `execute_code_headless` qua MCP (`FreeCAD.Version()`) | PASS, 0,5 s; trả FreeCAD 1.1.4, Python 3.11.14 |

### CHƯA CHẠY — làm cùng bạn (cần FreeCAD GUI + RPC bật + Claude Desktop khởi động lại)

| # | Việc | Kết quả | Thời gian | Lỗi |
| --- | --- | --- | --- | --- |
| 1 | `get_rpc_status` (mong `version_check` = compatible) | _chưa_ | | |
| 2 | Tạo hộp 50×30×10 mm có lỗ Ø8 ở giữa, rồi `get_view` | _chưa_ | | |
| 3 | `execute_code_headless` từ Claude Desktop in phiên bản FreeCAD | _chưa_ | | |
| 4 | Demo flange của README | _chưa_ | | |

Lưu ý demo flange: README chỉ có ảnh GIF (`assets/freecad_mcp4.gif`), **không công bố prompt dạng chữ**;
cần tự viết prompt tương đương (ví dụ mặt bích tròn, nhiều lỗ bu-lông trên vòng tròn chia).

## Bước 6 — Lớp 2D (TechDraw)

Script: `scripts/techdraw_smoke_test.py` (FreeCADCmd) và `scripts/techdraw_export_gui.py` (GUI ẩn).
Vật thể: hộp 50×30×10 có lỗ xuyên Ø8 ở giữa (thể tích 14497,3 mm³ đúng lý thuyết). Template:
`ISO/A4_Landscape_ISO5457_minimal.svg` (template A4 có sẵn của FreeCAD; thư mục
`Mod/TechDraw/Templates/` gốc không có file nào tên `A4*`, chúng nằm trong thư mục con `ISO/`).

| Việc | Kết quả |
| --- | --- |
| `import TechDraw` trong FreeCADCmd | PASS |
| `import TechDrawGui` trong FreeCADCmd | **FAIL (bình thường)**: "Cannot load Gui module in console application" |
| 3 hình chiếu bằng `DrawProjGroup` (first angle: Front, Top, Right) | PASS (visible edges 4 / 5 / 4) |
| Xuất **DXF** bằng `TechDraw.writeDXFPage` trong FreeCADCmd | PASS, ~7,7 KB, định dạng AC1014; 12 LINE + 1 CIRCLE (đúng 3 hình chiếu + lỗ Ø8) |
| Xuất **SVG/PDF cả trang** trong FreeCADCmd | **KHÔNG làm được**: `page.PageResult` rỗng; cả trang chỉ có ở lớp GUI |
| Xuất **PDF + SVG** bằng `freecad.exe --hidden script.py` (`TechDrawGui.exportPageAsPdf/Svg`) | PASS sau 1 lần sửa; PDF ~314 KB, A4 ngang (842×595 pt), 1 trang; SVG ~16 KB |

Thời gian đo được: script FreeCADCmd 4,9 s ở lần chạy đầu (nguội), 1,6–1,7 s ở các lần sau; GUI ẩn
(`freecad.exe --hidden`) 18–30 s tổng, lần đầu chậm hơn.

### Lỗi gặp và cách xử lý (quan trọng cho lớp TechDraw)

1. **PDF/SVG lần đầu chỉ có template, mất hết hình chiếu** (PDF chỉ 3 KB, SVG 23 path = đúng số path
   của template). Nguyên nhân: scene của page chưa dựng. Cách sửa: gọi `page.ViewObject.doubleClicked()`
   (mở MDI view của page), xử lý sự kiện Qt (`FreeCADGui.updateGui()` ~2 s), `page.touch()` + `recompute()`,
   rồi mới xuất. Script có kiểm tra tự động "số `<path>` của SVG phải nhiều hơn template" để không PASS giả.
2. **Bố cục ban đầu sai** (mặt bằng đè khung tên, mặt cạnh tràn khung): tâm nhóm đặt ở (130,100) mm.
   `DrawProjGroup.X/Y` là tâm view **Front** (anchor), tính từ góc dưới-trái trang; first angle đặt Top bên
   dưới, Right bên trái Front. Đã đổi sang (165,150) với scale 2.
3. Tiến trình GUI ẩn kết thúc bằng `os._exit` (không ghi user.cfg, không bị dialog chặn). Cổng 9875 không bị
   chiếm vì Auto-Start chưa bật.

### Thư viện thiếu (trong Python của FreeCAD 1.1.4)

| Thư viện | Trạng thái |
| --- | --- |
| `reportlab`, `svglib`, `cairosvg` | **THIẾU** |
| `ezdxf`, `fitz` (PyMuPDF) | **THIẾU** |
| `PySide6.QtSvg`, `QtGui`, `QtPrintSupport` | có |
| `PySide6.QtPdf` | **THIẾU** (không render được PDF → ảnh bằng Qt) |

Chưa kiểm tra project venv của MCP server (nó chỉ cài dependency của `pyproject.toml`, không có các thư
viện trên). Hiện **chưa cần cài thư viện nào** để xuất DXF/PDF/SVG; nếu sau này cần chỉnh DXF theo TCVN
(layer, linetype) thì cân nhắc `ezdxf`.

### Chưa kiểm tra

- Kích thước (dimension), chú thích, đường tâm, mặt cắt, hidden lines, nét theo TCVN.
- Điền khối tiêu đề (EditableTexts); font tiếng Việt trong PDF.
- Hình chiếu của DXF trong AutoCAD/ZWCAD (chỉ đếm thực thể, chưa mở bằng CAD).
- Chạy luồng 2D qua MCP (`execute_code` trên GUI).

## Baseline test của upstream

| Lệnh | Kết quả | Thời gian |
| --- | --- | --- |
| `uv sync --locked` | PASS | 8 s |
| `uv run freecad-mcp --help` | PASS | 9,2 s (lần đầu) |
| `uv run python -m compileall -q src addon` | PASS | 0,6 s |
| `uv run --locked pytest -q` | **441 passed, 5 skipped, 2 failed** | 91 s |

Hai test fail đều là test của upstream, chưa tìm nguyên nhân, không liên quan phần việc của mình:

- `tests/test_bump_version.py::test_registry_write_failure_restores_xml` (so sánh nội dung text, có thể do
  newline/encoding trên Windows — **chưa xác minh**).
- `tests/test_dispatch_guards.py::test_queue_timeout_ignores_a_guard_that_only_held_an_earlier_call`
  (thông điệp lỗi chứa "popup or context menu" trong khi test khẳng định không chứa — **chưa xác minh** vì sao).

## Việc còn lại / cần làm tay

1. Bật FreeCAD GUI → workbench **MCP Addon** → bật **Auto-Start Server** → xác nhận cổng 9875.
2. Thoát hẳn và mở lại Claude Desktop → kiểm tra server `freecad-dev` xuất hiện.
3. Chạy 4 việc của Bước 5 (bảng "CHƯA CHẠY") rồi điền kết quả vào file này.
4. Quyết định có khôi phục server cũ từ file `.bak` hay không.
