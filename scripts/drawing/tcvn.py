"""TCVN constants for the A3 landscape sheet, plus a read-only reader for the layer table of a TCVN profile.yaml.

Sheet coordinates everywhere in scripts/drawing: millimetres on paper, origin at the sheet's lower-left corner, y up.
"""
from __future__ import annotations

import os
import re

SHEET_W, SHEET_H = 420.0, 297.0
# Drawing frame 390 x 277 (left margin 20, other margins 10) - TCVN 7285 / 5571
FRAME_X0, FRAME_Y0, FRAME_X1, FRAME_Y1 = 20.0, 10.0, 410.0, 287.0
# Title block 180 x 65 in the bottom-right corner (TCVN 5571:2012 figure 2)
TB_W, TB_H = 180.0, 65.0
TB_X0, TB_Y0 = FRAME_X1 - TB_W, FRAME_Y0
TB_X1, TB_Y1 = FRAME_X1, FRAME_Y0 + TB_H

W_FRAME, W_THIN, W_THICK = 0.7, 0.25, 0.5      # mm; A3 pair thick/thin = 0.5/0.25
ARIAL_CAP = 0.716                              # Arial digit/capital height as a fraction of the em size (measured in S2)

# Linetype patterns in paper mm (+dash, -gap). Same patterns in the DXF (scaled by $LTSCALE) and in the PDF symbol.
LTYPES = {
    "HIDDEN": ("Hidden __ __ __", [3.0, -1.0]),
    "CENTER": ("Center ____ _ ____ _", [12.0, -1.5, 2.0, -1.5]),
    "DASHED": ("Dashed __ __ __", [6.0, -1.5]),
}

# Standard layers used by drawing type B (names are checked against the profile).
LAYER_AXIS, LAYER_BUBBLE, LAYER_COLUMN = "TRUC", "TRUC-KYHIEU", "COT"
LAYER_DIM, LAYER_TEXT, LAYER_FRAME, LAYER_THIN = "KICH-THUOC", "CHU", "KHUNG-TEN", "NET-MANH"


class ProfileError(Exception):
    pass


def read_profile(path: str | None = None) -> dict:
    """Read the `layers:` table of the TCVN profile.yaml (read-only). Path: argument or TCVN_PROFILE.

    Returns {name: dict(color:int, ltype:str, lw:int in 1/100 mm, plot:bool)}.
    """
    path = path or os.environ.get("TCVN_PROFILE", "")
    if not path or not os.path.isfile(path):
        raise ProfileError("Không tìm thấy profile.yaml: đặt biến môi trường TCVN_PROFILE hoặc dùng --profile (đường dẫn hiện tại: %r)." % path)
    txt = open(path, encoding="utf-8-sig").read()
    m = re.search(r"^layers:[ \t]*\r?\n(.*?)(?=^\S|\Z)", txt, re.S | re.M)
    if not m:
        raise ProfileError("profile.yaml không có mục 'layers:'.")
    layers = {}
    for blk in re.split(r"^\s*- name:", m.group(1), flags=re.M)[1:]:
        name = blk.split("\n", 1)[0].strip()

        def get(k):
            mm = re.search(rf"^\s*{k}:[ \t]*(\S+)", blk, re.M)
            return mm.group(1) if mm else None

        try:
            lw = get("lineweight")
            lw_mm = {"thick": W_THICK, "thin": W_THIN}.get(lw)
            if lw_mm is None:
                lw_mm = float(lw)
            ltype = get("linetype").upper()
            layers[name] = dict(color=int(get("color")), ltype=ltype, lw=int(round(lw_mm * 100)), plot=(get("plot") != "false"))
        except (TypeError, ValueError, AttributeError):
            raise ProfileError(f"profile.yaml: layer {name!r} thiếu hoặc sai color/linetype/lineweight.")
        if ltype != "CONTINUOUS" and ltype not in LTYPES:
            raise ProfileError(f"profile.yaml: layer {name!r} dùng linetype {ltype!r} chưa có mẫu nét (hỗ trợ: CONTINUOUS, {', '.join(LTYPES)}).")
    if len(layers) != 18:
        raise ProfileError("profile.yaml: mong đợi 18 layer chuẩn, đọc được %d." % len(layers))
    return layers


def layer_style(profile: dict, layer: str):
    """(stroke width mm, dash pattern list in paper mm or [])"""
    a = profile[layer]
    pat = LTYPES.get(a["ltype"], ("", []))[1]
    return a["lw"] / 100.0, pat
