"""Independent readers used by verify.py (stdlib only): ASCII DXF reader and a PDF path/text measurer."""
from __future__ import annotations

import collections
import re
import zlib

PT = 25.4 / 72.0


# ------------------------------------------------------------------ DXF
def unesc(s: str) -> str:
    return re.sub(r"\\U\+([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), s)


def read_dxf(path: str) -> dict:
    raw = open(path, "rb").read()
    try:
        text, utf8_ok = raw.decode("utf-8"), True
    except UnicodeDecodeError:
        text, utf8_ok = raw.decode("cp1252", "replace"), False
    L = text.splitlines()
    pairs = []
    for i in range(0, len(L) - 1, 2):
        try:
            pairs.append((int(L[i].strip()), L[i + 1].strip()))
        except ValueError:
            pass
    hdr, ltypes, layers, ents = {}, {}, {}, []
    section, cur, rec, hvar = None, None, {}, None

    def flush():
        if cur is None:
            return
        if section == "TABLES":
            if cur == "LTYPE" and 2 in rec:
                ltypes[rec[2][0]] = [float(x) for x in rec.get(49, [])]
            elif cur == "LAYER" and 2 in rec:
                layers[unesc(rec[2][0])] = dict(color=int(rec.get(62, ["0"])[0]), ltype=rec.get(6, ["?"])[0], lw=int(rec.get(370, ["-1"])[0]),
                                                plot=rec.get(290, ["1"])[0] == "1")
        elif section == "ENTITIES" and cur not in ("VERTEX", "SEQEND"):
            ents.append(dict(type=cur, layer=unesc(rec.get(8, ["0"])[0]), rec=rec))

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
        elif section == "HEADER":
            if code == 9:
                hvar = val
            elif hvar:
                hdr.setdefault(hvar, {})[code] = val
        elif cur is not None:
            rec.setdefault(code, []).append(val)
    flush()
    texts = [(e["layer"], unesc("".join(e["rec"].get(3, [])) + (e["rec"].get(1) or [""])[0])) for e in ents if e["type"] in ("TEXT", "MTEXT")]
    return dict(version=hdr.get("$ACADVER", {}).get(1), ltscale=float(hdr.get("$LTSCALE", {}).get(40, "nan")), utf8_ok=utf8_ok,
                high_bytes=sum(1 for b in raw if b >= 0x80), escapes=len(re.findall(r"\\U\+[0-9A-Fa-f]{4}", text)), size=len(raw),
                ltypes=ltypes, layers=layers, ents=ents, texts=texts,
                by_type=collections.Counter(e["type"] for e in ents), by_layer_type=collections.Counter((e["layer"], e["type"]) for e in ents))


def f(rec, code, i=0):
    return float(rec[code][i])


# ------------------------------------------------------------------ PDF
TOKEN = re.compile(rb"\[|\]|<[0-9A-Fa-f\s]*>|\((?:\\.|[^\\)])*\)|/[^\s/\[\]<>()]+|[-+]?\d*\.?\d+|[A-Za-z'\"*]+")


def _objects(data):
    objs = {}
    for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", data, re.S):
        body = m.group(3)
        sm = re.search(rb"stream\r?\n", body)
        if sm:
            raw = body[sm.end():]
            raw = raw[: raw.rfind(b"endstream")]
            head = body[: sm.start()]
            if b"FlateDecode" in head:
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    raw = b""
            objs[int(m.group(1))] = (head, raw)
        else:
            objs[int(m.group(1))] = (body, None)
    return objs


def _mul(a, b):
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def analyze_pdf(path: str) -> dict:
    """Paths with bbox (mm from the page's top-left), stroke width (mm) and dash pattern (mm); fonts; page size."""
    data = open(path, "rb").read()
    objs = _objects(data)
    mb = [float(x) for x in re.search(rb"/MediaBox\s*\[([^\]]*)\]", data).group(1).split()]
    W, H = mb[2] - mb[0], mb[3] - mb[1]
    page = next(n for n, (h, _) in objs.items() if re.search(rb"/Type\s*/Page\b", h))
    cm = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+0\s+R)", objs[page][0])
    content = b"\n".join(objs[int(x)][1] or b"" for x in re.findall(rb"(\d+)\s+0\s+R", cm.group(1)))
    fonts = sorted({m.group(1).decode() for m in re.finditer(rb"/BaseFont\s*/(\S+)", data)})
    ctm, stack, lw, dash = (1, 0, 0, 1, 0, 0), [], 1.0, ""
    ops, cur, paths = [], [], []
    for m in TOKEN.finditer(content):
        t = m.group(0)
        if re.fullmatch(rb"[-+]?\d*\.?\d+", t) or t.startswith((b"/", b"<", b"(", b"[")) or t == b"]":
            ops.append(t)
            continue
        op = t.decode("latin1")
        a = ops
        try:
            if op == "q":
                stack.append((ctm, lw, dash))
            elif op == "Q":
                if stack:
                    ctm, lw, dash = stack.pop()
            elif op == "cm":
                ctm = _mul(tuple(float(x) for x in a[-6:]), ctm)
            elif op == "w":
                lw = float(a[-1])
            elif op == "d":
                joined = b" ".join(a).decode("latin1")
                dm = re.search(r"\[([^\]]*)\]\s*([-\d.]+)\s*$", joined)
                sc = abs(ctm[0] * ctm[3] - ctm[1] * ctm[2]) ** 0.5 * PT
                dash = [float(x) * sc for x in dm.group(1).split()] if dm and dm.group(1).strip() else []
            elif op in ("m", "l", "c"):
                x, y = float(a[-2]), float(a[-1])
                X, Y = x * ctm[0] + y * ctm[2] + ctm[4], x * ctm[1] + y * ctm[3] + ctm[5]
                if op == "m" and cur:
                    cur.append(None)
                cur.append((X, Y, op))
            elif op == "re":
                x, y, w, h = (float(v) for v in a[-4:])
                for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)):
                    cur.append((px * ctm[0] + py * ctm[2] + ctm[4], px * ctm[1] + py * ctm[3] + ctm[5], "re"))
                cur.append(None)
            elif op in ("S", "s", "B", "b", "f", "F", "f*", "B*", "b*"):
                pts = [p for p in cur if p]
                if pts:
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    sc = abs(ctm[0] * ctm[3] - ctm[1] * ctm[2]) ** 0.5
                    kind = "stroke" if op in ("S", "s") else "fill" if op.startswith(("f", "F")) else "fillstroke"
                    paths.append(dict(bb=(min(xs) * PT, (H - max(ys)) * PT, max(xs) * PT, (H - min(ys)) * PT), lw=lw * sc * PT, dash=dash, kind=kind,
                                      n=len(pts), curve=any(p[2] == "c" for p in pts)))
                cur = []
            elif op == "n":
                cur = []
        except Exception:  # noqa: BLE001
            pass
        ops = []
    return dict(page_mm=(W * PT, H * PT), fonts=fonts, paths=paths, size=len(data))
