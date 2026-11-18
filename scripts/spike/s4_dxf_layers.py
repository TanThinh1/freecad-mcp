"""S4: write a DXF whose layers follow the 18-layer TCVN table of profile.yaml (read-only), with linetypes, colours,
lineweights and Vietnamese text.  Plain Python (no FreeCAD needed):

    python -I scripts\\spike\\s4_dxf_layers.py [out.dxf]

The profile path must be given in the TCVN_PROFILE environment variable. Nothing from it is copied into the repo: only
the generated test DXF goes to out\\spike\\ (git-ignored).
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dxfw import Dxf  # noqa: E402

PROFILE = os.environ.get("TCVN_PROFILE", "")   # path to the TCVN profile.yaml (read-only); no default on purpose
OUT = os.path.join(os.environ.get("SPIKE_OUT", os.path.join(os.getcwd(), "out", "spike")))
SCALE = 100.0                       # drawing scale denominator -> $LTSCALE and text height (2.5 mm * 100)
PAIR_A3 = {"thick": 0.5, "thin": 0.25}   # profile.yaml line_widths.pairs.A3

LTYPES = {   # paper-mm patterns (positive dash, negative gap); scaled by $LTSCALE
    "HIDDEN": ("Hidden __ __ __", [3.0, -1.0]),
    "CENTER": ("Center ____ _ ____ _", [12.0, -1.5, 2.0, -1.5]),
    "DASHED": ("Dashed __ __ __", [6.0, -1.5]),
}


def read_layers(path: str):
    """Tiny parser for the `layers:` list of profile.yaml (no PyYAML needed)."""
    if not path or not os.path.isfile(path):
        raise SystemExit("Set TCVN_PROFILE to the path of the TCVN profile.yaml (file not found: %r)" % path)
    txt = open(path, encoding="utf-8").read()
    sect = re.search(r"^layers:\s*\n(.*?)^\S", txt, re.S | re.M).group(1)
    layers = []
    for blk in re.split(r"^\s*- name:", sect, flags=re.M)[1:]:
        name = blk.split("\n", 1)[0].strip()
        get = lambda k: (re.search(rf"^\s*{k}:\s*(\S+)", blk, re.M) or [None, None])[1]
        layers.append(dict(name=name, color=int(get("color")), ltype=get("linetype"), lw=get("lineweight"), plot=(get("plot") != "false")))
    return layers


def lw_hundredths(lw: str) -> int:
    if lw in PAIR_A3:
        return int(round(PAIR_A3[lw] * 100))
    return int(round(float(lw) * 100))


def build(path: str, utf8: bool = False):
    layers = read_layers(PROFILE)
    d = Dxf(ltscale=SCALE, utf8=utf8)
    for n, (desc, pat) in LTYPES.items():
        d.add_ltype(n, desc, pat)
    d.add_style("TCVN-ARIAL", "arial.ttf")
    for L in layers:
        d.add_layer(L["name"], color=L["color"], ltype=L["ltype"], lw=lw_hundredths(L["lw"]), plot=L["plot"])
    h = 2.5 * SCALE
    for i, L in enumerate(layers):
        y = i * 1000.0
        d.line(L["name"], (0, y), (6000, y))
        d.text(L["name"], f"{L['name']} – Ắ Ằ Ơ Ư Đ ướ ượ", (6200, y), h, style="TCVN-ARIAL")
    d.circle("TRUC-KYHIEU", (-600, 11000), 400)
    d.text("TRUC-KYHIEU", "A", (-600, 10900), h, style="TCVN-ARIAL", halign="center")
    d.arc("BAN-MA", (-600, 15000), 400, 0, 180)
    d.rect("KHUNG-TEN", -2000, -1000, 18000, 19000)
    d.text("KICH-THUOC", "3000 Ø16 ±5° R500", (1500, 9200), h, style="TCVN-ARIAL", halign="center")
    path = d.save(path)
    expected = {"LINE": len(layers), "TEXT": len(layers) + 2, "CIRCLE": 1, "ARC": 1, "LWPOLYLINE": 1}
    return path, layers, expected


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    utf8 = "--utf8" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = args[0] if args else os.path.join(OUT, "s4_layers_utf8.dxf" if utf8 else "s4_layers.dxf")
    p, layers, expected = build(target, utf8)
    print(f"wrote {p} ({os.path.getsize(p):,} bytes), {len(layers)} layers from profile")
    print("expected entity counts:", json.dumps(expected))
