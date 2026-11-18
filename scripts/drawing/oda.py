"""ODA File Converter wrapper (Windows). ODA prints nothing; success = a valid output file (and returncode 0 via Python)."""
from __future__ import annotations

import os
import shutil
import subprocess
import time

ODA = os.environ.get("ODA_EXE", r"C:\Program Files\ODA\ODAFileConverter 27.10.0\ODAFileConverter.exe")


class OdaError(Exception):
    pass


def _run(indir: str, outdir: str, ver: str, kind: str, name: str):
    if not os.path.isfile(ODA):
        raise OdaError(f"Không tìm thấy ODA File Converter: {ODA} (đặt biến môi trường ODA_EXE).")
    os.makedirs(outdir, exist_ok=True)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    t0 = time.perf_counter()
    try:
        p = subprocess.run([ODA, indir, outdir, ver, kind, "0", "1", name], capture_output=True, text=True, timeout=300, startupinfo=si, creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        raise OdaError("ODA File Converter chạy quá 300 giây (đã dừng).")
    return time.perf_counter() - t0, p.returncode, (p.stdout + p.stderr).strip()


def _convert(src: str, dst: str, ver: str, kind: str, src_ext: str, dst_ext: str) -> dict:
    base = os.path.splitext(os.path.basename(src))[0]
    work = os.path.join(os.path.dirname(os.path.abspath(dst)), "_oda_tmp")
    tmp_in, tmp_out = os.path.join(work, "in"), os.path.join(work, "out")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(tmp_in)
    try:
        shutil.copyfile(src, os.path.join(tmp_in, base + src_ext))
        t, rc, msg = _run(tmp_in, tmp_out, ver, kind, base + src_ext)
        produced = os.path.join(tmp_out, base + dst_ext)
        ok = os.path.isfile(produced) and os.path.getsize(produced) > 0
        header = open(produced, "rb").read(6).decode("latin1") if ok else ""
        errs = [f for f in os.listdir(tmp_out) if f.endswith(".err")] if os.path.isdir(tmp_out) else []
        if ok:
            if os.path.isfile(dst):
                os.remove(dst)
            shutil.move(produced, dst)
        return dict(ok=ok, seconds=t, returncode=rc, message=msg, header=header, size=os.path.getsize(dst) if ok else 0, err_files=errs)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def dxf_to_dwg(dxf: str, dwg_path: str, ver: str = "ACAD2018") -> dict:
    return _convert(dxf, dwg_path, ver, "DWG", ".dxf", ".dwg")


def dwg_to_dxf(dwg: str, dxf_path: str, ver: str = "ACAD2018") -> dict:
    return _convert(dwg, dxf_path, ver, "DXF", ".dwg", ".dxf")
