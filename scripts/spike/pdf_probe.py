"""Measure a PDF without external libraries: path bounding boxes (mm), stroke widths, embedded fonts, text.

Usage: python -I scripts\\spike\\pdf_probe.py file.pdf [--min-area 400] [--text]
Coordinates are reported in mm from the page's TOP-LEFT corner (same orientation as the SVG template).
Works for PDFs written by Qt (plain objects, Flate streams, Type0/Identity-H fonts with ToUnicode).
"""
from __future__ import annotations

import collections
import re
import sys
import zlib

PT = 25.4 / 72.0


def load_objects(data: bytes):
    objs = {}
    for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", data, re.S):
        num = int(m.group(1))
        body = m.group(3)
        sm = re.search(rb"stream\r?\n", body)
        if sm:
            head = body[: sm.start()]
            raw = body[sm.end():]
            raw = raw[: raw.rfind(b"endstream")]
            if b"FlateDecode" in head:
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    raw = b""
            objs[num] = (head, raw)
        else:
            objs[num] = (body, None)
    return objs


def ref(s: bytes, key: bytes):
    m = re.search(key + rb"\s+(\d+)\s+0\s+R", s)
    return int(m.group(1)) if m else None


def parse_cmap(raw: bytes):
    mp = {}
    for blk in re.findall(rb"beginbfchar(.*?)endbfchar", raw, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            mp[int(a, 16)] = bytes.fromhex(b.decode()).decode("utf-16-be", "replace")
    for blk in re.findall(rb"beginbfrange(.*?)endbfrange", raw, re.S):
        for a, b, rest in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]+>)", blk):
            s, e = int(a, 16), int(b, 16)
            if rest.startswith(b"["):
                for k, u in zip(range(s, e + 1), re.findall(rb"<([0-9A-Fa-f]+)>", rest)):
                    mp[k] = bytes.fromhex(u.decode()).decode("utf-16-be", "replace")
            else:
                u0 = int(rest[1:-1], 16)
                for k in range(s, e + 1):
                    mp[k] = chr(u0 + k - s)
    return mp


TOKEN = re.compile(rb"\[|\]|<[0-9A-Fa-f\s]*>|\((?:\\.|[^\\)])*\)|/[^\s/\[\]<>()]+|[-+]?\d*\.?\d+|[A-Za-z'\"*]+")


def mat_mul(a, b):  # a then b  (row vectors): result = a x b
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1]
    min_area = float(sys.argv[sys.argv.index("--min-area") + 1]) if "--min-area" in sys.argv else 400.0
    data = open(path, "rb").read()
    objs = load_objects(data)
    page = next((n for n, (h, _) in objs.items() if re.search(rb"/Type\s*/Page\b", h) and b"/Pages" not in h.split(b"/Type")[0]), None)
    head = objs[page][0]
    mb = [float(x) for x in re.search(rb"/MediaBox\s*\[([^\]]*)\]", data).group(1).split()]
    W, H = mb[2] - mb[0], mb[3] - mb[1]
    print(f"file: {path}  ({len(data):,} bytes)   PDF header: {data[:8].decode('latin1').strip()}")
    print(f"MediaBox: {W:.2f} x {H:.2f} pt = {W*PT:.2f} x {H*PT:.2f} mm")

    # fonts
    fonts = {}
    for n, (h, _) in objs.items():
        if re.search(rb"/Type\s*/Font\b", h) and b"/BaseFont" in h:
            bf = re.search(rb"/BaseFont\s*/(\S+)", h).group(1).decode()
            sub = re.search(rb"/Subtype\s*/(\S+)", h)
            d = ref(h, rb"/DescendantFonts\s*\[") or None
            fonts[n] = dict(name=bf, sub=sub.group(1).decode() if sub else "?", head=h)
    emb = []
    for n, f in fonts.items():
        fd = None
        h = f["head"]
        m = re.search(rb"/DescendantFonts\s*\[\s*(\d+)\s+0\s+R", h)
        target = objs.get(int(m.group(1)))[0] if m else h
        fdn = ref(target, rb"/FontDescriptor")
        fdh = objs.get(fdn, (b"", None))[0] if fdn else b""
        embedded = any(k in fdh for k in (b"/FontFile2", b"/FontFile3", b"/FontFile"))
        emb.append((f["name"], f["sub"], embedded))
    print("fonts (BaseFont, Subtype, embedded):")
    for e in sorted(set(emb)):
        print(f"   {e[0]:<40}{e[1]:<10} embedded={e[2]}")

    # page resources -> font name map and ToUnicode maps
    res_font = {}
    rm = re.search(rb"/Font\s*<<(.*?)>>", head, re.S)
    if not rm:
        rn = ref(head, rb"/Resources")
        rm = re.search(rb"/Font\s*<<(.*?)>>", objs[rn][0], re.S) if rn else None
        if not rm and rn:
            fr = ref(objs[rn][0], rb"/Font")
            rm = re.search(rb"<<(.*?)>>", objs[fr][0], re.S) if fr else None
    if rm:
        for nm, on in re.findall(rb"/(\S+)\s+(\d+)\s+0\s+R", rm.group(1)):
            res_font[nm.decode()] = int(on)
    cmaps = {}
    for nm, on in res_font.items():
        tu = ref(objs[on][0], rb"/ToUnicode")
        cmaps[nm] = parse_cmap(objs[tu][1]) if tu and objs[tu][1] else {}

    # content streams
    cm = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+0\s+R)", head)
    nums = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", cm.group(1))]
    content = b"\n".join(objs[n][1] or b"" for n in nums)

    ctm = (1, 0, 0, 1, 0, 0)
    stack = []
    lw = 1.0
    ops = []
    cur = []        # current subpath points in user space (already transformed)
    paths = []      # (bbox mm, linewidth mm, kind)
    widths = collections.Counter()
    dashes = collections.Counter()
    cur_dash = ""
    texts = []   # (string, em size mm on paper, font resource name)
    tfont = None
    tsize_mm = 0.0
    cur_text = ""
    for m in TOKEN.finditer(content):
        t = m.group(0)
        if re.fullmatch(rb"[-+]?\d*\.?\d+", t) or t.startswith((b"/", b"<", b"(", b"[")) or t == b"]":
            ops.append(t)
            continue
        op = t.decode("latin1")
        a = ops
        try:
            if op == "q":
                stack.append((ctm, lw, cur_dash))
            elif op == "Q":
                ctm, lw, cur_dash = stack.pop() if stack else (ctm, lw, cur_dash)
            elif op == "cm":
                v = tuple(float(x) for x in a[-6:])
                ctm = mat_mul(v, ctm)
            elif op == "w":
                lw = float(a[-1])
            elif op == "d":
                joined = b" ".join(a).decode("latin1")
                dm = re.search(r"\[([^\]]*)\]\s*([-\d.]+)\s*$", joined)
                if dm and dm.group(1).strip():
                    sc = (abs(ctm[0] * ctm[3] - ctm[1] * ctm[2])) ** 0.5 * PT
                    cur_dash = "[" + " ".join(f"{float(x) * sc:.2f}" for x in dm.group(1).split()) + "] mm"
                else:
                    cur_dash = ""
            elif op in ("m", "l"):
                x, y = float(a[-2]), float(a[-1])
                X = x * ctm[0] + y * ctm[2] + ctm[4]
                Y = x * ctm[1] + y * ctm[3] + ctm[5]
                if op == "m" and cur:
                    cur.append(None)
                cur.append((X, Y))
            elif op == "re":
                x, y, w, h = (float(v) for v in a[-4:])
                for (px, py) in ((x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)):
                    cur.append((px * ctm[0] + py * ctm[2] + ctm[4], px * ctm[1] + py * ctm[3] + ctm[5]))
                cur.append(None)
            elif op == "c":
                x, y = float(a[-2]), float(a[-1])
                cur.append((x * ctm[0] + y * ctm[2] + ctm[4], x * ctm[1] + y * ctm[3] + ctm[5]))
            elif op in ("S", "s", "B", "b", "f", "F", "f*", "B*", "b*"):
                pts = [p for p in cur if p]
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    scale = (abs(ctm[0] * ctm[3] - ctm[1] * ctm[2])) ** 0.5
                    wmm = lw * scale * PT
                    bb = (min(xs) * PT, (H - max(ys)) * PT, max(xs) * PT, (H - min(ys)) * PT)
                    kind = "stroke" if op in ("S", "s") else "fill" if op.startswith(("f", "F")) else "fill+stroke"
                    paths.append((bb, wmm, kind, len([p for p in cur if p]), cur_dash))
                    if kind != "fill":
                        widths[round(wmm, 2)] += 1
                        dashes[cur_dash or "solid"] += 1
                cur = []
            elif op == "n":
                cur = []
            elif op == "BT":
                cur_text, text_start = "", True
            elif op == "ET":
                if cur_text:
                    texts.append((cur_text, tsize_mm, tfont))
                cur_text = ""
            elif op == "Tf":
                tfont = a[-2].decode().lstrip("/")
                tsize_mm = float(a[-1]) * (abs(ctm[0] * ctm[3] - ctm[1] * ctm[2])) ** 0.5 * PT
            elif op in ("Tj", "TJ"):
                mp = cmaps.get(tfont, {})
                for tok in a:
                    if tok.startswith(b"<"):
                        hx = re.sub(rb"\s", b"", tok[1:-1])
                        for i in range(0, len(hx) - 3, 4):
                            cur_text += mp.get(int(hx[i:i + 4], 16), "?")
        except Exception as exc:  # noqa: BLE001
            print("warn:", op, exc)
        ops = []

    print(f"\npaths: {len(paths)} (stroked/filled)")
    print("stroke widths (mm -> count):", dict(sorted(widths.items())))
    print("dash patterns:", dict(dashes))
    print(f"\nlarge paths (bbox area >= {min_area:g} mm2): x0,y0 = top-left in mm; w x h in mm; stroke width")
    for bb, wmm, kind, n, dash in sorted(paths, key=lambda p: -((p[0][2] - p[0][0]) * (p[0][3] - p[0][1]))):
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        if w * h >= min_area:
            print(f"   {kind:<11} ({bb[0]:7.2f},{bb[1]:7.2f}) {w:8.2f} x {h:7.2f}  lw={wmm:.2f} pts={n} dash={dash or 'solid'}")
    if "--text" in sys.argv:
        print("\ntext strings decoded via ToUnicode:")
        for s, em, f in texts:
            print(f"    {s!r:<30} em={em:.2f} mm  (digit/cap height ~ {em * 0.716:.2f} mm)  font={f}")
    else:
        print(f"\ntext runs: {len(texts)} (use --text to list)")


main()
