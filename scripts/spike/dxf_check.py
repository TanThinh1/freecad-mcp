"""ASCII DXF checker (read-only, stdlib only).

Usage: python -I scripts\\spike\\dxf_check.py file.dxf [--text]
Reports: version, encoding sanity, LTYPE table, LAYER table (colour, linetype, lineweight), entity counts by type,
entities by (layer, linetype), and with --text the TEXT/MTEXT strings decoded (\\U+XXXX and %% escapes).
"""
from __future__ import annotations

import collections
import re
import sys


def unesc(s: str) -> str:
    s = re.sub(r"\\U\+([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace("%%c", "Ø").replace("%%d", "°").replace("%%p", "±")


def read(path: str):
    raw = open(path, "rb").read()
    try:
        text, enc = raw.decode("utf-8"), "utf-8 (valid)"
    except UnicodeDecodeError:
        text, enc = raw.decode("cp1252", "replace"), "NOT valid UTF-8 (read as cp1252)"
    hi = sum(1 for b in raw if b >= 0x80)
    return raw, text, enc, hi


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1]
    raw, text, enc, hi = read(path)
    L = text.splitlines()
    pairs = []
    for i in range(0, len(L) - 1, 2):
        try:
            pairs.append((int(L[i].strip()), L[i + 1].strip()))
        except ValueError:
            pass
    hdr, section, cur, rec, table = {}, None, None, {}, None
    ltypes, layers, ents = {}, {}, []
    hvar = None

    def flush():
        if cur is None:
            return
        if section == "TABLES":
            if cur == "LTYPE" and 2 in rec:
                ltypes[rec[2][0]] = [float(x) for x in rec.get(49, [])]
            elif cur == "LAYER" and 2 in rec:
                layers[unesc(rec[2][0])] = dict(color=rec.get(62, ["?"])[0], ltype=rec.get(6, ["?"])[0], lw=rec.get(370, [""])[0], flags=rec.get(70, ["0"])[0])
        elif section == "ENTITIES" and cur not in ("VERTEX", "SEQEND"):
            ents.append((cur, rec))

    for code, val in pairs:
        if code == 0:
            flush()
            rec = {}
            if val == "SECTION":
                cur = None
            elif val == "ENDSEC":
                section, cur = None, None
            elif val != "EOF":
                cur = val
        elif code == 2 and cur is None and section is None:
            section = val
        else:
            if section == "HEADER":
                if code == 9:
                    hvar = val
                elif hvar:
                    hdr.setdefault(hvar, {})[code] = val
            elif cur is not None:
                rec.setdefault(code, []).append(val)
    flush()

    print(f"file: {path} ({len(raw):,} bytes)  version={hdr.get('$ACADVER', {}).get(1)}  codepage={hdr.get('$DWGCODEPAGE', {}).get(3)}  INSUNITS={hdr.get('$INSUNITS', {}).get(70)}")
    n_esc = len(re.findall(r"\\U\+[0-9A-Fa-f]{4}", text))
    print(f"encoding: {enc}; bytes>=0x80: {hi}; backslash-U+XXXX escapes: {n_esc}")
    print("LTYPE table:", {k: v for k, v in ltypes.items()})
    print(f"LAYER table ({len(layers)}):")
    for n, v in layers.items():
        print(f"   {n:<14} colour={v['color']:>4} linetype={v['ltype']:<12} lineweight={v['lw'] or '-':>5} flags={v['flags']}")
    cnt = collections.Counter(t for t, _ in ents)
    print("entities by type:", dict(cnt.most_common()), " total:", sum(cnt.values()))
    by = collections.Counter()
    for t, r in ents:
        lay = unesc(r.get(8, ["0"])[0])
        lt = r.get(6, ["BYLAYER"])[0]
        by[(lay, lt, r.get(62, ["BYLAYER"])[0], r.get(370, ["BYLAYER"])[0])] += 1
    print("entities by (layer, linetype, colour, lineweight):")
    for (lay, lt, col, lw), n in sorted(by.items()):
        print(f"   {lay:<14} {lt:<10} colour={col:<8} lw={lw:<8} x{n}")
    if "--text" in sys.argv:
        print("text entities:")
        for t, r in ents:
            if t in ("TEXT", "MTEXT"):
                s = "".join(r.get(3, [])) + (r.get(1) or [""])[0]
                print(f"   {t:<5} layer={unesc(r.get(8, ['0'])[0]):<10} h={r.get(40, ['?'])[0]:<6} {unesc(s)!r}")


main()
