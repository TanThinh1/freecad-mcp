"""make_drawing: spec.json -> out/<ten>/<ten>.pdf, .dxf, .dwg + verification report.

    python scripts\\drawing\\make_drawing.py scripts\\drawing\\examples\\b1_16500x36000.json [more specs...]
        [--out out] [--profile path\\to\\profile.yaml] [--no-pdf] [--no-dwg] [--no-fc]

The 18-layer TCVN table is read (read-only) from the profile.yaml given by --profile or the TCVN_PROFILE variable.
One list of primitives feeds both renderers (DXF/DWG and PDF). Exit code 0 = every drawing built and every check passed
(skipped stages with --no-* give status "dat_khong_day_du" and exit code 1). Optional environment overrides: ODA_EXE,
FREECAD_EXE (freecad.exe), FREECADCMD_EXE (FreeCADCmd.exe).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import oda  # noqa: E402
import titleblock as TBK  # noqa: E402
import verify  # noqa: E402
import build_a  # noqa: E402
import build_b  # noqa: E402
import spec_a  # noqa: E402
import spec_b  # noqa: E402
from dxf_render import render_dxf  # noqa: E402
from pdf_render import symbol_svg  # noqa: E402
from spec_b import SpecError, load_spec  # noqa: E402
from tcvn import ProfileError, read_profile  # noqa: E402

FREECAD = os.environ.get("FREECAD_EXE") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "FreeCAD 1.1", "bin", "freecad.exe")
FREECADCMD = os.environ.get("FREECADCMD_EXE") or os.path.join(os.path.dirname(FREECAD), "FreeCADCmd.exe")
KINDS = {"A": (spec_a.validate, build_a.build), "B": (spec_b.validate, build_b.build)}


def render_3d(sp: dict, outdir: str, work: str, name: str, timeout: int = 240) -> dict:
    """Type A only: Part model from the same spec (FreeCADCmd), then a best-effort screenshot with the hidden GUI."""
    job = dict(n=sp["so_bac"], H=sp["cao_tang"], b=sp["b"], w=sp["w"], t=sp["t"], bw=sp["dam_con"]["bw"], bd=sp["dam_con"]["bd"],
               fcstd=os.path.join(outdir, f"{name}.FCStd"), png=os.path.join(outdir, f"{name}_3d.png"), result=os.path.join(work, f"{name}_3d.json"))
    _rm(job["fcstd"], job["result"], job["png"])
    jp = os.path.join(work, f"{name}_3d_job.json")
    json.dump(job, open(jp, "w", encoding="utf-8"))
    if not os.path.isfile(FREECADCMD):
        return dict(ok=False, error=f"không tìm thấy {FREECADCMD} (đặt FREECADCMD_EXE)")
    try:
        subprocess.run([FREECADCMD, os.path.join(HERE, "model3d_a.py")], env=dict(os.environ, MODEL_JOB=jp), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(ok=False, error=f"FreeCADCmd quá {timeout} giây")
    if not os.path.isfile(job["result"]):
        return dict(ok=False, error="model3d_a.py không ghi kết quả")
    res = json.load(open(job["result"], encoding="utf-8"))
    if not res.get("ok"):
        return dict(ok=False, error=res.get("error", "?"))
    # The preview PNG is software-rendered inside model3d_a.py (hidden-GUI screenshots come out blank: no OpenGL context).
    if res.get("png") and not os.path.isfile(res["png"]):
        res.pop("png")
        res["png_error"] = "không có tệp ảnh"
    if not res.get("png") and not res.get("png_error"):
        res["png_error"] = "không có kết quả"
    return res


def _rm(*paths):
    for p in paths:
        if os.path.isfile(p):
            os.remove(p)


def render_pdf(D, profile, outdir: str, work: str, name: str, timeout: int = 300) -> dict:
    job = dict(template=os.path.join(work, f"{name}_template.svg"), symbol=os.path.join(work, f"{name}_symbol.svg"), texts=D.fields,
               pdf=os.path.join(outdir, f"{name}.pdf"), svg=os.path.join(work, f"{name}_techdraw.svg"), log=os.path.join(work, f"{name}_freecad.log"))
    _rm(job["pdf"], job["svg"], job["log"])           # never accept a stale result from a previous run
    TBK.write_template(job["template"])
    open(job["symbol"], "w", encoding="utf-8").write(symbol_svg(D, profile))
    jp = os.path.join(work, f"{name}_job.json")
    json.dump(job, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not os.path.isfile(FREECAD):
        return dict(ok=False, error=f"không tìm thấy {FREECAD} (đặt biến môi trường FREECAD_EXE)")
    env = dict(os.environ, DRAWING_JOB=jp, PYTHONPATH=HERE)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    p = subprocess.Popen([FREECAD, "--hidden", os.path.join(HERE, "pdf_render.py")], env=env, startupinfo=si, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return dict(ok=False, error=f"FreeCAD chạy quá {timeout} giây (đã dừng)")
    log = open(job["log"], encoding="utf-8").read() if os.path.isfile(job["log"]) else ""
    ok = p.returncode == 0 and "EXIT 0" in log and os.path.isfile(job["pdf"]) and os.path.getsize(job["pdf"]) > 0
    return dict(ok=ok, pdf=job["pdf"], error=None if ok else f"returncode={p.returncode}; log: {log.strip()[-400:] or '(không có log: FreeCAD không chạy pdf_render.py)'}")


def render_png(pdf: str, png: str, width: int = 2400) -> bool:
    _rm(png)
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "pdf_to_png.ps1"), "-Pdf", pdf, "-Png", png, "-Width", str(width)],
                       capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False
    return os.path.isfile(png)


def make(spec_path: str, out_root: str, profile_path: str | None, do_pdf=True, do_dwg=True, do_fc=True, do_3d=True) -> dict:
    t00 = time.perf_counter()
    T: dict = {}
    res: dict = dict(spec=spec_path, name=os.path.splitext(os.path.basename(spec_path))[0], status="?", timings=T, stages={})
    try:
        raw = load_spec(spec_path)
        t = time.perf_counter()
        kind = raw.get("loai", "B") if isinstance(raw, dict) else "B"
        if kind not in KINDS:
            raise SpecError([f"loai = {kind!r} chưa được hỗ trợ (A: cầu thang thép, B: mặt bằng lưới trục và cột)."])
        validate_fn, build_fn = KINDS[kind]
        sp = validate_fn(raw)
        profile = read_profile(profile_path)
        D = build_fn(sp, profile)
        T["build"] = time.perf_counter() - t
    except SpecError as e:
        res.update(status="loi_dau_vao", errors=e.errors)
        T["total"] = time.perf_counter() - t00
        return res
    except ProfileError as e:
        res.update(status="loi_profile", errors=[str(e)])
        return res
    except (OSError, ValueError) as e:       # unreadable file / invalid JSON
        res.update(status="loi_dau_vao", errors=[f"không đọc được spec {spec_path}: {e}"])
        return res
    name = sp["ten"]
    outdir = os.path.join(out_root, name)
    work = os.path.join(outdir, "_work")
    os.makedirs(work, exist_ok=True)
    res.update(name=name, scale=D.scale, reason=D.info["reason"], band=D.info["band"], N=D.info["N"], columns=D.info["n_columns"])
    files = dict(dxf=os.path.join(outdir, f"{name}.dxf"), dwg=os.path.join(outdir, f"{name}.dwg"), pdf=os.path.join(outdir, f"{name}.pdf"), png=os.path.join(outdir, f"{name}.png"))
    _rm(files["dxf"], files["dwg"], files["png"])
    skipped = []
    try:
        t = time.perf_counter()
        render_dxf(D, profile, files["dxf"])
        T["dxf"] = time.perf_counter() - t
        res["stages"]["dxf"] = "ok"
        dwg_info = None
        if do_dwg:
            t = time.perf_counter()
            try:
                dwg_info = oda.dxf_to_dwg(files["dxf"], files["dwg"], "ACAD2018")
            except oda.OdaError as e:
                dwg_info = dict(ok=False, message=str(e))
            T["dwg"] = time.perf_counter() - t
            res["stages"]["dwg"] = "ok" if dwg_info.get("ok") else f"LOI: {dwg_info.get('message') or dwg_info}"
        else:
            skipped.append("dwg")
        pdf_ok = False
        if do_pdf:
            t = time.perf_counter()
            pr = render_pdf(D, profile, outdir, work, name)
            T["pdf"] = time.perf_counter() - t
            pdf_ok = pr["ok"]
            res["stages"]["pdf"] = "ok" if pdf_ok else f"LOI: {pr.get('error')}"
            if pdf_ok:
                t = time.perf_counter()
                png_ok = render_png(files["pdf"], files["png"])
                T["png"] = time.perf_counter() - t
                res["stages"]["png"] = "ok" if png_ok else "LOI: không tạo được PNG"
        else:
            skipped.append("pdf")
        if not do_fc:
            skipped.append("freecad_import")
        model3d = None
        if D.kind == "A":
            if do_3d:
                t = time.perf_counter()
                model3d = render_3d(sp, outdir, work, name)
                T["3d"] = time.perf_counter() - t
                res["stages"]["3d"] = "ok" if model3d.get("ok") else f"LOI: {model3d.get('error')}"
                res["png3d"] = model3d.get("png")
            else:
                skipped.append("3d")
        res["warnings"] = D.info.get("warnings", [])
        t = time.perf_counter()
        dwg_ok = bool(dwg_info and dwg_info.get("ok"))
        C = verify.run_all(D, sp, profile, dict(files, work=work), do_fc=do_fc, do_dwg=do_dwg and dwg_ok, do_pdf=do_pdf and pdf_ok, dwg_info=dwg_info, model3d=model3d)
        T["verify"] = time.perf_counter() - t
        res["checks"] = C.items
        res["groups"] = {g: C.passed(g) for g in (1, 2, 3, 4, 5, 6)}
        stages_ok = all(v == "ok" for v in res["stages"].values())
        if not (C.all_ok() and stages_ok):
            res["status"] = "khong_dat"
        else:
            res["status"] = "dat_khong_day_du" if skipped else "dat"
        res["skipped"] = skipped
    except Exception:  # noqa: BLE001  - one broken drawing must not stop the batch
        res["status"] = "loi_he_thong"
        res["errors"] = [traceback.format_exc(limit=6)]
    T["total"] = time.perf_counter() - t00
    res["files"] = {k: v for k, v in files.items() if os.path.isfile(v)}
    try:
        json.dump(res, open(os.path.join(outdir, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    except OSError:
        pass
    return res


def print_result(r: dict):
    print(f"\n=== {r.get('name')}  [{r['status']}]")
    if r["status"].startswith("loi"):
        for e in r.get("errors", []):
            print("  LỖI:", e)
        return
    print(f"  tỷ lệ 1:{r['scale']} - {r['reason']}")
    print("  thời gian: " + ", ".join(f"{k} {v:.1f}s" for k, v in r["timings"].items()))
    for k, v in r.get("stages", {}).items():
        if v != "ok":
            print(f"  bước {k}: {v}")
    for w_ in r.get("warnings", []):
        print("  CẢNH BÁO:", w_)
    if r.get("skipped"):
        print("  ĐÃ BỎ QUA (không được kiểm): " + ", ".join(r["skipped"]))
    for c in r.get("checks", []):
        tag = "INFO" if c["ok"] is None else ("ĐẠT" if c["ok"] else "KHÔNG")
        print(f"  [{tag}] {c['id']:<5} {c['name']}  -- {c['detail']}")


def main(argv):
    def opt(k):
        if k not in argv:
            return None
        i = argv.index(k)
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            raise SystemExit(f"{k} cần một giá trị.")
        return argv[i + 1]

    flags_with_value = {"--out", "--profile"}
    args, skip = [], False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a in flags_with_value:
            skip = True
        elif not a.startswith("--"):
            args.append(a)
    out = opt("--out") or os.path.join(os.getcwd(), "out")
    prof = opt("--profile")
    if not args:
        print(__doc__)
        return 2
    results = []
    for sp in args:
        r = make(sp, out, prof, do_pdf="--no-pdf" not in argv, do_dwg="--no-dwg" not in argv, do_fc="--no-fc" not in argv, do_3d="--no-3d" not in argv)
        print_result(r)
        results.append(r)
    return 0 if all(r["status"] == "dat" for r in results) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
