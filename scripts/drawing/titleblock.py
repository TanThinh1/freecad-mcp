"""Title block TCVN 5571:2012 figure 2 (180 x 65 mm, bottom-right corner of the A3 frame) + frame 390 x 277.

Layout (relative to the block's top-left corner, y down):
  top row 16 high: cell 1 (design firm, x 0..90) | cell 2 (project + investor, x 90..180)
  left block, 7 rows x 7 high, columns 30/30/30: cells 8-14 (role | signature | name)
  right block (x 90..180): cell 3 title (90 x 28) ; row 12-13 (14 high): cell 7 scale (25) | cell 5 document type (40) ;
  row 14 (7 high): cell 15 (25) | cell 6 date (40) ; cell 4 drawing number (25 x 21) at x 155..180 spanning rows 12-14.
Text: Arial, regular and bold only (2 styles), sizes 2.5 / 3.5 / 5 mm (3 sizes).
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from primitives import Line, Rect, Text
from spec_b import SpecError
from tcvn import (ARIAL_CAP, FRAME_X0, FRAME_X1, FRAME_Y0, FRAME_Y1, LAYER_FRAME, LAYER_TEXT, LAYER_THIN, SHEET_H, SHEET_W, TB_H, TB_W, TB_X0, TB_Y0, W_FRAME,
                  W_THIN)

TB_TOP = TB_Y0 + TB_H

# cell id -> (x, y, w, h) relative to the block's top-left corner (y down)
CELLS = {"1": (0, 0, 90, 16), "2": (90, 0, 90, 16), "3": (90, 16, 90, 28), "7": (90, 44, 25, 14), "5": (115, 44, 40, 14),
         "4": (155, 44, 25, 21), "15": (90, 58, 25, 7), "6": (115, 58, 40, 7)}

# dividers (relative coordinates, thin)
DIVIDERS = [(0, 16, 180, 16)]
DIVIDERS += [(0, 16 + 7 * k, 90, 16 + 7 * k) for k in range(1, 7)]
DIVIDERS += [(30, 16, 30, 65), (60, 16, 60, 65), (90, 0, 90, 65), (90, 44, 180, 44), (90, 58, 155, 58), (115, 44, 115, 65), (155, 44, 155, 65)]

# editable fields: name -> (cell, dx, dy baseline from cell top, size, bold, max text width)
FIELDS = {
    "cell1_l1": ("1", 45, 6.5, 3.5, True, 86), "cell1_l2": ("1", 45, 12.0, 3.5, False, 86),
    "cell2_l1": ("2", 45, 6.5, 3.5, True, 86), "cell2_l2": ("2", 45, 12.0, 3.5, False, 86),
    "cell3_l1": ("3", 45, 12.0, 5.0, True, 86), "cell3_l2": ("3", 45, 20.0, 5.0, True, 86),
    "cell4": ("4", 12.5, 15.5, 5.0, True, 21), "cell5": ("5", 20, 10.5, 3.5, False, 36),
    "cell6": ("6", 20, 5.0, 3.5, False, 36), "cell7": ("7", 12.5, 10.5, 3.5, False, 21), "cell15": ("15", 12.5, 5.0, 3.5, False, 21),
}
ROWS = {}
for _k in range(7):
    top = 16 + 7 * _k
    FIELDS[f"row{_k + 1}_role"] = (None, 15, top + 4.8, 2.5, False, 27)
    FIELDS[f"row{_k + 1}_name"] = (None, 75, top + 4.8, 2.5, False, 27)
CAPTIONS = [("3", 1.5, 3.4, "Tên bản vẽ"), ("7", 1.5, 3.4, "Tỷ lệ"), ("5", 1.5, 3.4, "Loại hồ sơ"), ("4", 1.5, 3.4, "Số hiệu")]
CAP_SIZE = 2.5


def est_width(s: str, size: float, bold: bool = False) -> float:
    """Conservative Arial width estimate in mm (measured S1: 25 bold caps+spaces at 5 mm = 76 mm; estimate gives ~79)."""
    w = 0.0
    for ch in s:
        if ch == " ":
            w += 0.28
        elif ch.isdigit():
            w += 0.556
        elif ch.isupper():
            w += 0.72 if bold else 0.68
        elif ch.isalpha():
            w += 0.56 if bold else 0.52
        else:
            w += 0.35
    return w * size


def _split(text, size, bold, width, max_lines, what):
    parts = [p.strip() for p in text.split("|")] if "|" in text else [text.strip()]
    if len(parts) > max_lines:
        raise SpecError([f"{what} = {text!r}: tối đa {max_lines} dòng (dấu | là ngắt dòng)."])
    if len(parts) == 1 and est_width(parts[0], size, bold) > width and max_lines > 1:
        words = parts[0].split()
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            m = max(est_width(a, size, bold), est_width(b, size, bold))
            if best is None or m < best[0]:
                best = (m, [a, b])
        if best:
            parts = best[1]
    for p in parts:
        if est_width(p, size, bold) > width:
            raise SpecError([f"{what}: dòng {p!r} dài khoảng {est_width(p, size, bold):.0f} mm, vượt chiều rộng ô {width:g} mm "
                             f"(chữ {size:g} mm). Hãy rút gọn hoặc ngắt dòng bằng dấu |. Không tự thu nhỏ chữ."])
    return parts


def fields_from_meta(meta: dict, scale_text: str) -> dict:
    """khung_ten metadata -> {editable field: text}. Raises SpecError if a value does not fit its cell."""
    f: dict[str, str] = {}
    errs = []

    def put(name, text, what):
        _, _, _, size, bold, width = FIELDS[name]
        if text and est_width(text, size, bold) > width:
            errs.append(f"{what} = {text!r}: dài khoảng {est_width(text, size, bold):.0f} mm, vượt ô ({width:g} mm, chữ {size:g} mm).")
        else:
            f[name] = text

    try:
        l = _split(meta.get("don_vi_tk", ""), 3.5, True, 86, 2, "khung_ten.don_vi_tk (ô 1)") if meta.get("don_vi_tk") else []
        for i, t in enumerate(l[:2]):
            f[f"cell1_l{i + 1}"] = t
        l = _split(meta.get("ten_ban_ve", ""), 5.0, True, 86, 2, "khung_ten.ten_ban_ve (ô 3)") if meta.get("ten_ban_ve") else []
        for i, t in enumerate(l[:2]):
            f[f"cell3_l{i + 1}"] = t
    except SpecError as e:
        errs.extend(e.errors)
    if meta.get("cong_trinh"):
        put("cell2_l1", "CÔNG TRÌNH: " + meta["cong_trinh"], "khung_ten.cong_trinh (ô 2)")
    if meta.get("chu_dau_tu"):
        put("cell2_l2", "CHỦ ĐẦU TƯ: " + meta["chu_dau_tu"], "khung_ten.chu_dau_tu (ô 2)")
    put("cell4", meta.get("ky_hieu_ban_ve", ""), "khung_ten.ky_hieu_ban_ve (ô 4)")
    put("cell5", meta.get("loai_ho_so", ""), "khung_ten.loai_ho_so (ô 5)")
    put("cell6", meta.get("ngay", ""), "khung_ten.ngay (ô 6)")
    put("cell7", scale_text, "tỷ lệ (ô 7)")
    put("cell15", meta.get("o15", ""), "khung_ten.o15 (ô 15)")
    for k, row in enumerate(meta.get("ky") or [], start=1):
        put(f"row{k}_role", row.get("chuc_danh", ""), f"khung_ten.ky[{k - 1}].chuc_danh")
        put(f"row{k}_name", row.get("ho_ten", ""), f"khung_ten.ky[{k - 1}].ho_ten")
    if errs:
        raise SpecError(errs)
    return {k: v for k, v in f.items() if v}


# ---------------------------------------------------------------- geometry helpers (sheet coordinates, y up)
def rel_to_sheet(rx: float, ry: float):
    return TB_X0 + rx, TB_TOP - ry


def field_anchor(name: str):
    cell, dx, dy, size, bold, _ = FIELDS[name]
    rx0, ry0 = (CELLS[cell][0], CELLS[cell][1]) if cell else (0, 0)
    return rel_to_sheet(rx0 + dx, ry0 + dy)


def primitives(fields: dict) -> list:
    """Frame, title block outline, dividers, captions and values as primitives (all sheet=True)."""
    out = [Rect(layer=LAYER_FRAME, tag="frame", sheet=True, p0=(FRAME_X0, FRAME_Y0), p1=(FRAME_X1, FRAME_Y1)),
           Rect(layer=LAYER_FRAME, tag="tb_outline", sheet=True, p0=(TB_X0, TB_Y0), p1=(TB_X0 + TB_W, TB_TOP))]
    for x1, y1, x2, y2 in DIVIDERS:
        out.append(Line(layer=LAYER_THIN, tag="tb_divider", sheet=True, p1=rel_to_sheet(x1, y1), p2=rel_to_sheet(x2, y2)))
    for cell, dx, dy, txt in CAPTIONS:
        cx, cy, _, _ = CELLS[cell]
        out.append(Text(layer=LAYER_TEXT, tag="tb_caption", sheet=True, s=txt, pos=rel_to_sheet(cx + dx, cy + dy), h=CAP_SIZE * ARIAL_CAP))
    for name, text in fields.items():
        size, bold = FIELDS[name][3], FIELDS[name][4]       # `size` is the em size used in the SVG template
        out.append(Text(layer=LAYER_TEXT, tag="tb_text", sheet=True, s=text, pos=field_anchor(name), h=size * ARIAL_CAP, halign="center", bold=bold))
    return out


def template_svg() -> str:
    """A3 landscape SVG template for TechDraw (mm units, y down) with freecad:editable text cells."""
    H = SHEET_H
    fy = lambda y: H - y
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" xmlns:freecad="https://www.freecad.org/wiki/index.php?title=Svg_Namespace" '
             f'width="{SHEET_W:g}mm" height="{SHEET_H:g}mm" viewBox="0 0 {SHEET_W:g} {SHEET_H:g}" version="1.1">',
             '<g id="drawing_frame" style="fill:none;stroke:#000000;stroke-linecap:butt;stroke-linejoin:miter">',
             f'<rect x="{FRAME_X0:g}" y="{fy(FRAME_Y1):g}" width="{FRAME_X1 - FRAME_X0:g}" height="{FRAME_Y1 - FRAME_Y0:g}" style="stroke-width:{W_FRAME:g}"/>',
             "</g>", '<g id="title_block" style="fill:none;stroke:#000000;stroke-linecap:butt;stroke-linejoin:miter">',
             f'<rect x="{TB_X0:g}" y="{fy(TB_TOP):g}" width="{TB_W:g}" height="{TB_H:g}" style="stroke-width:{W_FRAME:g}"/>']
    for x1, y1, x2, y2 in DIVIDERS:
        a, b = rel_to_sheet(x1, y1), rel_to_sheet(x2, y2)
        parts.append(f'<line x1="{a[0]:g}" y1="{fy(a[1]):g}" x2="{b[0]:g}" y2="{fy(b[1]):g}" style="stroke-width:{W_THIN:g}"/>')
    parts += ["</g>", '<g id="title_block_text" style="fill:#000000;stroke:none;font-family:Arial">']
    for cell, dx, dy, txt in CAPTIONS:
        cx, cy, _, _ = CELLS[cell]
        x, y = rel_to_sheet(cx + dx, cy + dy)
        parts.append(f'<text x="{x:g}" y="{fy(y):g}" style="font-size:{CAP_SIZE:g}px">{escape(txt)}</text>')
    for name, (cell, dx, dy, size, bold, _) in FIELDS.items():
        x, y = field_anchor(name)
        w = "font-weight:bold;" if bold else ""
        parts.append(f'<text id="{name}_field" x="{x:g}" y="{fy(y):g}" freecad:editable="{name}" '
                     f'style="{w}font-size:{size:g}px;text-anchor:middle"><tspan></tspan></text>')
    parts += ["</g>", "</svg>"]
    return "\n".join(parts) + "\n"


def write_template(path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(template_svg())
    return path
