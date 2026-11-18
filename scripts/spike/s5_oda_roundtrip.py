"""S5: DXF -> DWG (ACAD2018) -> DXF with ODA File Converter, compare entity counts / layers with the original.

    python -I scripts\\spike\\s5_oda_roundtrip.py [src.dxf ...]      (default: the two S4 DXFs)

Work happens in out\\spike\\s5\\ (git-ignored). ODA does not report errors on stdout: success = a valid output file.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.environ.get("SPIKE_OUT", os.path.join(os.getcwd(), "out", "spike")), "s5")
ODA = os.environ.get("ODA_EXE", r"C:\Program Files\ODA\ODAFileConverter 27.10.0\ODAFileConverter.exe")


def run_oda(indir: str, outdir: str, ver: str, kind: str, name: str):
    os.makedirs(outdir, exist_ok=True)
    t0 = time.perf_counter()
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    p = subprocess.run([ODA, indir, outdir, ver, kind, "0", "1", name], capture_output=True, text=True, timeout=300, startupinfo=si, creationflags=0x08000000)
    return time.perf_counter() - t0, p.returncode, (p.stdout + p.stderr).strip()


def census(path: str):
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "dxf_check.py"), path], capture_output=True, text=True, encoding="utf-8")
    out = r.stdout
    ents = ast.literal_eval(re.search(r"entities by type: (\{.*?\})", out).group(1))
    layers = re.findall(r"^   (\S.*?)\s+colour=\s*(\d+) linetype=(\S+)\s+lineweight=\s*(\S+)", out, re.M)
    ver = re.search(r"version=(\S+)", out).group(1)
    return dict(ents=ents, layers=layers, ver=ver, raw=out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    srcs = sys.argv[1:] or [os.path.join(os.path.dirname(OUT), "s4_layers.dxf"), os.path.join(os.path.dirname(OUT), "s4_layers_utf8.dxf")]
    print("ODA:", ODA, "exists:", os.path.isfile(ODA))
    for src in srcs:
        name = os.path.splitext(os.path.basename(src))[0]
        work = os.path.join(OUT, name)
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(os.path.join(work, "in"))
        shutil.copyfile(src, os.path.join(work, "in", name + ".dxf"))
        print(f"\n=== {name}  ({os.path.getsize(src):,} bytes)")
        orig = census(src)
        print(f"original: version={orig['ver']} entities={orig['ents']} layers={len(orig['layers'])}")
        t, rc, msg = run_oda(os.path.join(work, "in"), os.path.join(work, "dwg"), "ACAD2018", "DWG", name + ".dxf")
        dwg = os.path.join(work, "dwg", name + ".dwg")
        hdr = open(dwg, "rb").read(6).decode("latin1") if os.path.isfile(dwg) else "MISSING"
        print(f"DXF->DWG ACAD2018: {t:.1f}s returncode={rc} msg={msg!r} -> {os.path.basename(dwg)} {os.path.getsize(dwg) if os.path.isfile(dwg) else 0:,} bytes header={hdr}")
        errs = [f for f in os.listdir(os.path.join(work, "dwg")) if f.endswith(".err")] if os.path.isdir(os.path.join(work, "dwg")) else []
        if errs:
            print("  ODA .err files:", errs, open(os.path.join(work, "dwg", errs[0]), errors="replace").read()[:400])
        for ver in ("ACAD2000", "ACAD2018"):
            back = os.path.join(work, "back_" + ver)
            t, rc, msg = run_oda(os.path.join(work, "dwg"), back, ver, "DXF", name + ".dwg")
            bp = os.path.join(back, name + ".dxf")
            if not os.path.isfile(bp):
                print(f"DWG->DXF {ver}: FAILED (no output) {t:.1f}s rc={rc} {msg!r}")
                continue
            c = census(bp)
            same = c["ents"] == orig["ents"]
            lay_o = {(a, b, c2, d) for a, b, c2, d in orig["layers"]}
            lay_b = {(a, b, c2, d) for a, b, c2, d in c["layers"]}
            print(f"DWG->DXF {ver}: {t:.1f}s rc={rc} -> {os.path.getsize(bp):,} bytes, version={c['ver']}, entities={c['ents']}  same counts as original: {same}")
            print(f"   layers back={len(lay_b)} original={len(lay_o)}; layer attrs identical: {lay_o == lay_b}; differing: {sorted(lay_o ^ lay_b)[:6]}")
            print("   encoding line:", re.search(r"encoding: .*", c["raw"]).group(0))


main()
