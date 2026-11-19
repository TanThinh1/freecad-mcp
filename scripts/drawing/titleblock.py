"""Title block TCVN 5571:2012 figure 2 (180 x 65 mm, bottom-right corner of the A3 frame) + frame 390 x 277.

Layout (relative to the block's top-left corner, y down):
  top row 16 high: cell 1 (design firm, x 0..90) | cell 2 (project + investor, x 90..180)
  left block, 7 rows x 7 high, columns 30/30/30: cells 8-14 (role | signature | name)
  right block (x 90..180): cell 3 title (90 x 28) ; row 12-13 (14 high): cell 7 scale (25) | cell 5 document type (40) ;
  row 14 (7 high): cell 15 (25) | cell 6 date (40) ; cell 4 drawing number (25 x 21) at x 155..180 spanning rows 12-14.
Text: Arial, regular and bold only (2 styles), sizes 2.5 / 3.5 / 5 mm (3 sizes).
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from primitives import Line, Rect, Text
from spec_b import SpecError
from tcvn import est_width  # noqa: F401  (re-exported: verify.py uses TBK.est_width)
from tcvn import A3, MIN_EM, MIN_WF, SHEETS, TB_MARGIN, cons_width  # noqa: F401
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
# (the last number is the usable width = cell width - 2 x TB_MARGIN)
FIELDS = {
    "cell1_l1": ("1", 45, 6.5, 3.5, True, 87), "cell1_l2": ("1", 45, 12.0, 3.5, False, 87),
    "cell2_l1": ("2", 45, 6.5, 3.5, True, 87), "cell2_l2": ("2", 45, 12.0, 3.5, False, 87),
    "cell3_l1": ("3", 45, 12.0, 5.0, True, 87), "cell3_l2": ("3", 45, 20.0, 5.0, True, 87),
    "cell4": ("4", 12.5, 15.5, 5.0, True, 22), "cell5": ("5", 20, 10.5, 3.5, False, 37),
    "cell6": ("6", 20, 5.0, 3.5, False, 37), "cell7": ("7", 12.5, 10.5, 3.5, False, 22), "cell15": ("15", 12.5, 5.0, 3.5, False, 22),
}
ROWS = {}
FIELD_CELL = {}            # field -> (x, y, w, h) of its cell relative to the block's top-left corner (y down)
for _n, _f in FIELDS.items():
    FIELD_CELL[_n] = CELLS[_f[0]]
for _k in range(7):
    top = 16 + 7 * _k
    for _suffix, _col, _dx in (("role", 0, 15), ("date", 1, 45), ("name", 2, 75)):         # middle column (signature column) carries the signing date
        FIELDS[f"row{_k + 1}_{_suffix}"] = (None, _dx, top + 4.8, 2.5, False, 27)
        FIELD_CELL[f"row{_k + 1}_{_suffix}"] = (30 * _col, top, 30, 7)
# fields that may be broken into two lines when shrinking is not enough: name -> (baseline dy of line 1, baseline dy of line 2) from the cell top; line 2 is the field name + "_2"
LINES2 = {}
for _k in range(7):
    top = 16 + 7 * _k
    for _s in ("role", "name"):
        LINES2[f"row{_k + 1}_{_s}"] = (top + 3.1, top + 6.1)
LINES2["cell4"] = (11.0, 18.5)
LINES2["cell5"] = (7.2, 11.8)
for _n, (_d1, _d2) in list(LINES2.items()):
    _c, _dx, _dy, _sz, _b, _w = FIELDS[_n]
    FIELDS[_n + "_2"] = (_c, _dx, _d2, _sz, _b, _w)
    FIELD_CELL[_n + "_2"] = FIELD_CELL[_n]
CAPTIONS = [("3", 1.5, 3.4, "Tên bản vẽ"), ("7", 1.5, 3.4, "Tỷ lệ"), ("5", 1.5, 3.4, "Loại hồ sơ"), ("4", 1.5, 3.4, "Số hiệu")]
CAP_SIZE = 2.5


def fit_line(text: str, em0: float, avail: float):
    """Worst-case fit of one line into `avail` mm: (em, width factor) or None. Order: lower the width factor down to MIN_WF, then the height (em) down to MIN_EM.
    The widths are floored (0.01 / 0.1 steps) so the result is never wider than `avail`."""
    n = len(text)
    if n == 0 or cons_width(text, em0) <= avail:
        return em0, 1.0
    wf = math.floor(avail / cons_width(text, em0) * 100 + 1e-9) / 100
    if wf >= MIN_WF:
        return em0, wf
    em = math.floor(avail / cons_width(text, 1.0, MIN_WF) * 10 + 1e-9) / 10
    if em >= MIN_EM:
        return min(em, em0), MIN_WF
    return None


def best_split(text: str):
    """Break a string at a space into two lines, the longer line as short as possible; None when it has no space."""
    words = text.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if best is None or max(len(a), len(b)) < best[0]:
            best = (max(len(a), len(b)), [a, b])
    return best[1] if best else None


def _too_long(what, text, avail):
    return (f"{what}: dòng {text!r} có {len(text)} ký tự, cần khoảng {cons_width(text, MIN_EM, MIN_WF):.0f} mm ngay cả khi co chữ tới giới hạn "
            f"(hệ số rộng {MIN_WF:g}, cao {MIN_EM:g} mm, ước lượng thận trọng) nhưng ô chỉ rộng {avail:g} mm. Hãy rút gọn hoặc ngắt dòng bằng dấu |.")


def _split(text, size, bold, width, max_lines, what):
    parts = [p.strip() for p in text.split("|")] if "|" in text else [text.strip()]
    if len(parts) > max_lines:
        raise SpecError([f"{what} = {text!r}: tối đa {max_lines} dòng (dấu | là ngắt dòng)."])
    if len(parts) == 1 and fit_line(parts[0], size, width) is None and max_lines > 1:         # shrink first (width factor, height), then break into two lines
        parts = best_split(parts[0]) or parts
    for p in parts:
        if fit_line(p, size, width) is None:
            raise SpecError([_too_long(what, p, width)])
    return parts


def fields_from_meta(meta: dict, scale_text: str) -> dict:
    """khung_ten metadata -> {editable field: text}. Raises SpecError if a value does not fit its cell."""
    f: dict[str, str] = {}
    errs = []

    def put(name, text, what):
        _, _, _, size, bold, width = FIELDS[name]
        if not text or fit_line(text, size, width):
            f[name] = text
            return
        parts = best_split(text) if name in LINES2 else None                    # shrinking did not suffice: break into two lines when the cell has room
        if parts and fit_line(max(parts, key=len), size, width):
            f[name], f[name + "_2"] = parts
        else:
            errs.append(f"{what} = " + _too_long("", text, width).lstrip(": "))

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
        if row.get("ngay"):
            put(f"row{k}_date", row["ngay"], f"khung_ten.ky[{k - 1}].ngay")
    if errs:
        raise SpecError(errs)
    return {k: v for k, v in f.items() if v}


# ---------------------------------------------------------------- geometry helpers (sheet coordinates, y up)
def rel_to_sheet(rx: float, ry: float, sheet=A3):
    return sheet.tb_x0 + rx, sheet.tb_y1 - ry


def field_anchor(name: str, sheet=A3, dy=None):
    """Sheet position (centre of the baseline) of a field; `dy` overrides the baseline offset (two-line layouts, see layout())."""
    cell, dx, dy0, size, bold, _ = FIELDS[name]
    rx0, ry0 = (CELLS[cell][0], CELLS[cell][1]) if cell else (0, 0)
    return rel_to_sheet(rx0 + dx, ry0 + (dy0 if dy is None else dy), sheet)


def cell_rect(name: str, sheet=A3):
    """(x0, y0, x1, y1) of the cell holding field `name`, sheet mm (y up)."""
    rx, ry, w, h = FIELD_CELL[name]
    x0, y1 = rel_to_sheet(rx, ry, sheet)
    return x0, y1 - h, x0 + w, y1


def all_cells(sheet=A3) -> list:
    """Every text cell of the title block as (x0, y0, x1, y1) sheet mm (y up): cells 1-7, 15 and the 7 x 3 cells of the left block."""
    rects = {tuple(v) for v in CELLS.values()} | {(30 * c, 16 + 7 * k, 30, 7) for k in range(7) for c in range(3)}
    out = []
    for rx, ry, w, h in sorted(rects):
        x0, y1 = rel_to_sheet(rx, ry, sheet)
        out.append((x0, y1 - h, x0 + w, y1))
    return out


def layout(fields: dict) -> dict:
    """{field: dict(em, wf, dy)} for every printed field: the size, width factor and baseline offset after fitting the text into its cell.
    A field with a partner `name_2` is a two-line text: both lines share the size / width factor needed by the longer one and use the two-line baselines (LINES2)."""
    out = {}
    for name, text in fields.items():
        base = name[:-2] if name.endswith("_2") and name[:-2] in LINES2 else name
        size, width = FIELDS[name][3], FIELDS[name][5]
        if base in LINES2 and base in fields and base + "_2" in fields:
            fit = fit_line(max(fields[base], fields[base + "_2"], key=len), size, width)
            dy = LINES2[base][1 if name.endswith("_2") else 0]
        else:
            fit, dy = fit_line(text, size, width), FIELDS[name][2]
        if fit is None:
            raise SpecError([_too_long(f"khung tên, ô {name}", text, width)])
        out[name] = dict(em=fit[0], wf=fit[1], dy=dy)
    return out


def primitives(fields: dict, sheet=A3) -> list:
    """Frame, title block outline, dividers, captions and values as primitives (all sheet=True) for the given sheet (default A3)."""
    out = [Rect(layer=LAYER_FRAME, tag="frame", sheet=True, p0=(sheet.x0, sheet.y0), p1=(sheet.x1, sheet.y1)),
           Rect(layer=LAYER_FRAME, tag="tb_outline", sheet=True, p0=(sheet.tb_x0, sheet.tb_y0), p1=(sheet.tb_x0 + sheet.tb_w, sheet.tb_y1))]
    for x1, y1, x2, y2 in DIVIDERS:
        out.append(Line(layer=LAYER_THIN, tag="tb_divider", sheet=True, p1=rel_to_sheet(x1, y1, sheet), p2=rel_to_sheet(x2, y2, sheet)))
    for cell, dx, dy, txt in CAPTIONS:
        cx, cy, _, _ = CELLS[cell]
        out.append(Text(layer=LAYER_TEXT, tag="tb_caption", sheet=True, s=txt, pos=rel_to_sheet(cx + dx, cy + dy, sheet), h=CAP_SIZE * ARIAL_CAP))
    lay = layout(fields)
    for name, text in fields.items():
        bold = FIELDS[name][4]
        L = lay[name]                                        # em size / width factor after fitting; the PDF template uses exactly these values
        out.append(Text(layer=LAYER_TEXT, tag="tb_text", sheet=True, s=text, pos=field_anchor(name, sheet, L["dy"]), h=L["em"] * ARIAL_CAP, halign="center", bold=bold,
                        wf=L["wf"], field=name))
    return out


def template_svg(sheet=A3, fit=None) -> str:
    """Landscape SVG template of the sheet for TechDraw (mm units, y down) with freecad:editable text cells.
    fit = {field: (em, wf, (x, y) sheet position)} from the title-block Text primitives: the PDF then prints each field with the same size / width factor / baseline as the DXF."""
    fit = fit or {}
    H = sheet.h
    SHEET_W, SHEET_H = sheet.w, sheet.h
    FRAME_X0, FRAME_Y0, FRAME_X1, FRAME_Y1 = sheet.x0, sheet.y0, sheet.x1, sheet.y1
    TB_X0, TB_TOP, TB_W, TB_H = sheet.tb_x0, sheet.tb_y1, sheet.tb_w, sheet.tb_h
    fy = lambda y: H - y
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" xmlns:freecad="https://www.freecad.org/wiki/index.php?title=Svg_Namespace" '
             f'width="{SHEET_W:g}mm" height="{SHEET_H:g}mm" viewBox="0 0 {SHEET_W:g} {SHEET_H:g}" version="1.1">',
             '<g id="drawing_frame" style="fill:none;stroke:#000000;stroke-linecap:butt;stroke-linejoin:miter">',
             f'<rect x="{FRAME_X0:g}" y="{fy(FRAME_Y1):g}" width="{FRAME_X1 - FRAME_X0:g}" height="{FRAME_Y1 - FRAME_Y0:g}" style="stroke-width:{W_FRAME:g}"/>',
             "</g>", '<g id="title_block" style="fill:none;stroke:#000000;stroke-linecap:butt;stroke-linejoin:miter">',
             f'<rect x="{TB_X0:g}" y="{fy(TB_TOP):g}" width="{TB_W:g}" height="{TB_H:g}" style="stroke-width:{W_FRAME:g}"/>']
    for x1, y1, x2, y2 in DIVIDERS:
        a, b = rel_to_sheet(x1, y1, sheet), rel_to_sheet(x2, y2, sheet)
        parts.append(f'<line x1="{a[0]:g}" y1="{fy(a[1]):g}" x2="{b[0]:g}" y2="{fy(b[1]):g}" style="stroke-width:{W_THIN:g}"/>')
    parts += ["</g>", '<g id="title_block_text" style="fill:#000000;stroke:none;font-family:Arial">']
    for cell, dx, dy, txt in CAPTIONS:
        cx, cy, _, _ = CELLS[cell]
        x, y = rel_to_sheet(cx + dx, cy + dy, sheet)
        parts.append(f'<text x="{x:g}" y="{fy(y):g}" style="font-size:{CAP_SIZE:g}px">{escape(txt)}</text>')
    for name, (cell, dx, dy, size, bold, _) in FIELDS.items():
        x, y = field_anchor(name, sheet)
        w = "font-weight:bold;" if bold else ""
        if name in fit:
            em, wf, (x, y) = fit[name]
            tr = f' transform="translate({x:.4f},{fy(y):.4f}) scale({wf:g},1)"' if abs(wf - 1.0) > 1e-9 else ""
            parts.append(f'<text id="{name}_field"{tr} x="{0 if tr else x:.4f}" y="{0 if tr else fy(y):.4f}" freecad:editable="{name}" '
                         f'style="{w}font-size:{em:g}px;text-anchor:middle"><tspan></tspan></text>')
            continue
        parts.append(f'<text id="{name}_field" x="{x:g}" y="{fy(y):g}" freecad:editable="{name}" '
                     f'style="{w}font-size:{size:g}px;text-anchor:middle"><tspan></tspan></text>')
    parts += ["</g>", "</svg>"]
    return "\n".join(parts) + "\n"


def write_template(path: str, sheet=A3, fit=None) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(template_svg(sheet, fit))
    return path
