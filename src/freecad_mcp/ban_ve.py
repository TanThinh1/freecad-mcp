"""Technical-drawing tools (type A stair, B grid + columns, C portal-frame cross-section, D purlin plan) on top of scripts/drawing.

The drawing pipeline (make_drawing / verify) is NOT reimplemented here: every call runs the scripts as a separate Python process, so a crash or
a slow FreeCAD export never blocks the MCP server. Files are written only below <repo>/out/ (spec copies and logs in out/_jobs/<job_id>/, results in
out/<ten>/). One drawing job runs at a time. All messages are Vietnamese; no traceback or secret is ever returned.

TCVN profile: the layer table is read at runtime from the file named by the TCVN_PROFILE environment variable, or - if that is not set - from the
path written in out/tcvn_profile.txt (out/ is git-ignored). The profile content is never copied into this repository.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRAW = REPO / "scripts" / "drawing"
OUT = REPO / "out"
JOBS = OUT / "_jobs"
LOAI = ("thang", "luoi_cot", "khung_ngang", "xa_go", "ve_tu_do")
JOB_TIMEOUT = 900          # seconds; a drawing normally needs 30-60 s
CLI_TIMEOUT = 30
MAX_PNG_BYTES = 1_500_000

_lock = threading.Lock()
_current: dict | None = None            # the running job, if any
_jobs: dict[str, dict] = {}             # in-memory history (also persisted as job.json)


def _bad(msg: str) -> dict:
    return {"hop_le": False, "loi": [msg]}


def _paths_ok() -> str | None:
    if not (DRAW / "make_drawing.py").is_file() or not (DRAW / "ban_ve_cli.py").is_file():
        return "Không tìm thấy bộ dựng bản vẽ (scripts/drawing). Hãy chạy server từ thư mục fork freecad-mcp (uv --directory <fork> run freecad-mcp)."
    return None


def _profile_path() -> str | None:
    p = os.environ.get("TCVN_PROFILE", "").strip()
    if p and os.path.isfile(p):
        return p
    f = OUT / "tcvn_profile.txt"
    try:
        if f.is_file():
            q = f.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()
            if q and os.path.isfile(q):
                return q
    except (OSError, IndexError):
        pass
    return None


NOT_WRITABLE = "Không ghi được vào thư mục out của fork (kiểm tra quyền ghi hoặc ổ đĩa đầy)."
NO_PROFILE = ("Chưa cấu hình profile TCVN (bảng 18 layer). Đặt biến môi trường TCVN_PROFILE = đường dẫn profile.yaml trong mục freecad-dev của cấu hình "
              "Claude Desktop, hoặc ghi đường dẫn đó vào tệp out\\tcvn_profile.txt trong thư mục fork.")


def _env(freecadcmd: list[str] | None) -> dict:
    env = dict(os.environ)
    prof = _profile_path()
    if prof:
        env["TCVN_PROFILE"] = prof
    env["PYTHONIOENCODING"] = "utf-8"
    if freecadcmd and os.path.isfile(freecadcmd[0]):
        cmd = Path(freecadcmd[0])
        env.setdefault("FREECADCMD_EXE", str(cmd))
        gui = cmd.with_name("freecad.exe")
        if gui.is_file():
            env.setdefault("FREECAD_EXE", str(gui))
    return env


def _run_cli(args: list[str], freecadcmd: list[str] | None = None) -> dict:
    try:
        r = subprocess.run([sys.executable, str(DRAW / "ban_ve_cli.py"), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                           timeout=CLI_TIMEOUT, env=_env(freecadcmd), cwd=str(REPO), creationflags=0x08000000 if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        return _bad(f"Kiểm tra spec quá {CLI_TIMEOUT} giây (đã dừng).")
    except OSError as e:
        return _bad(f"Không chạy được bộ kiểm tra: {e}")
    try:
        return json.loads(r.stdout)
    except ValueError:
        return _bad("Bộ kiểm tra không trả kết quả hợp lệ (xem log máy chủ).")


def _check_loai(loai) -> str | None:
    if not isinstance(loai, str) or loai not in LOAI:
        shown = loai if isinstance(loai, str) and len(loai) <= 40 else type(loai).__name__
        return f"loai = {shown!r} không hợp lệ. Dùng một trong: thang, luoi_cot, khung_ngang, xa_go, ve_tu_do."
    return None


def _spec_text(spec, loai: str = "") -> tuple[str | None, str | None]:
    """spec (dict, or a JSON string) -> (JSON text, error)."""
    if isinstance(spec, str):
        try:
            spec = json.loads(spec.lstrip("﻿"))
        except ValueError:
            return None, "spec không phải JSON hợp lệ (chuỗi JSON bị lỗi cú pháp)."
    if not isinstance(spec, dict):
        return None, "spec phải là một đối tượng JSON {...}."
    try:
        text = json.dumps(spec, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        return None, "spec chứa giá trị không hợp lệ (NaN, Infinity hoặc kiểu không phải JSON)."
    lim = 300000 if loai == "ve_tu_do" else 20000
    if len(text.encode("utf-8")) > lim:
        return None, f"spec quá lớn (> {lim} byte)."
    return text, None


# ------------------------------------------------------------------ tool 1 / 2
def huong_dan(loai: str) -> dict:
    err = _check_loai(loai) or _paths_ok()
    if err:
        return _bad(err)
    return _run_cli(["guide", loai])


def kiem_tra(loai: str, spec, freecadcmd: list[str] | None = None) -> dict:
    err = _check_loai(loai) or _paths_ok()
    if err:
        return _bad(err)
    text, err = _spec_text(spec, loai)
    if err:
        return dict(hop_le=False, loai=loai, loi=[err])
    if not _profile_path():
        return dict(hop_le=False, loai=loai, loi=[NO_PROFILE], loi_he_thong=True)
    tmp = JOBS / f"_kiemtra_{uuid.uuid4().hex[:8]}.json"
    try:
        JOBS.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text, encoding="utf-8")
    except OSError:
        return dict(hop_le=False, loai=loai, loi=[NOT_WRITABLE], loi_he_thong=True)
    try:
        return _run_cli(["check", loai, str(tmp)], freecadcmd)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ tool 3 / 4: background job
def _save(job: dict) -> None:
    try:
        d = JOBS / job["job_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass


def _summarize(ten: str) -> dict:
    rp = OUT / ten / "report.json"
    if not rp.is_file():
        return {}
    try:
        rep = json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    checks = rep.get("checks", [])
    bad = [f"{c['id']}: {c['name']}" for c in checks if c.get("ok") is False]
    files = {k: str(Path(v).relative_to(REPO)) if str(v).startswith(str(REPO)) else v for k, v in rep.get("files", {}).items()}
    if rep.get("png3d"):
        files["png_3d"] = str(Path(rep["png3d"]).relative_to(REPO)) if str(rep["png3d"]).startswith(str(REPO)) else rep["png3d"]
    return dict(trang_thai_dung=rep.get("status"), ty_le=rep.get("scale"), ty_le_mat_bang=rep.get("scale_plan"), bo_cuc=rep.get("layout"), ly_do=rep.get("reason"),
                kiem_tra=dict(tong=len(checks), dat=sum(1 for c in checks if c.get("ok") is True), khong_dat=len(bad), chi_ghi_nhan=sum(1 for c in checks if c.get("ok") is None),
                              muc_khong_dat=bad),
                canh_bao=rep.get("warnings", []), bo_qua=rep.get("skipped", []), thoi_gian_giay={k: round(v, 1) for k, v in rep.get("timings", {}).items()},
                loi=rep.get("errors"), tep=files)


def _kill_tree(proc) -> None:
    """Stop the make_drawing process and everything it started (FreeCAD, ODA)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, stdin=subprocess.DEVNULL, timeout=20, creationflags=0x08000000)
        else:
            proc.kill()
    except (OSError, subprocess.SubprocessError):
        proc.kill()


def _worker(job: dict, spec_path: Path, env: dict) -> None:
    global _current
    log = JOBS / job["job_id"] / "log.txt"
    t0 = time.perf_counter()
    wall0 = time.time()
    try:
        try:
            (OUT / job["ten"] / "report.json").unlink()          # never accept a report left over from an earlier run
        except OSError:
            pass
        with open(log, "w", encoding="utf-8", errors="replace") as lf:
            proc = subprocess.Popen([sys.executable, str(DRAW / "make_drawing.py"), str(spec_path), "--out", str(OUT)], stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT, env=env,
                                    cwd=str(REPO), creationflags=0x08000000 if os.name == "nt" else 0)
            try:
                proc.wait(timeout=JOB_TIMEOUT)
            except subprocess.TimeoutExpired:
                _kill_tree(proc)
                job.update(trang_thai="loi", loi=f"Dựng bản vẽ quá {JOB_TIMEOUT} giây, đã dừng.")
        if job["trang_thai"] == "dang_chay":
            summary = _summarize(job["ten"])
            rp = OUT / job["ten"] / "report.json"
            if summary and (not rp.is_file() or rp.stat().st_mtime < wall0 - 1.0):
                summary = {}
            if not summary:
                job.update(trang_thai="loi", loi="Dựng xong nhưng không có báo cáo (report.json); xem log trong " + str(Path("out") / "_jobs" / job["job_id"] / "log.txt"))
            else:
                st = summary.get("trang_thai_dung")
                job["ket_qua"] = summary
                if st in ("loi_dau_vao", "loi_profile", "loi_he_thong"):
                    job.update(trang_thai="loi", loi="; ".join(summary.get("loi") or [st]))
                else:
                    job["trang_thai"] = "xong"
                    job["kiem_tra_dat"] = st in ("dat", "dat_khong_day_du") and summary["kiem_tra"]["khong_dat"] == 0
    except Exception as e:  # noqa: BLE001
        job.update(trang_thai="loi", loi=f"Lỗi nội bộ khi dựng bản vẽ: {type(e).__name__}")
    finally:
        job["thoi_gian_tong_giay"] = round(time.perf_counter() - t0, 1)
        job["ket_thuc"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save(job)
        with _lock:
            _current = None


def ve(loai: str, spec, freecadcmd: list[str] | None = None) -> dict:
    """Validate, then start the drawing in the background. Returns {job_id,...} or {loi:[...]}."""
    global _current
    err = _check_loai(loai) or _paths_ok()
    if err:
        return _bad(err)
    text, err = _spec_text(spec, loai)
    if err:
        return dict(hop_le=False, loai=loai, loi=[err])
    if not _profile_path():
        return dict(hop_le=False, loai=loai, loi=[NO_PROFILE], loi_he_thong=True)
    with _lock:
        if _current is not None:
            c = _current
            return dict(hop_le=False, ban=True, loi=[f"Đang dựng bản vẽ {c['ten']} (job_id {c['job_id']}, đã chạy {int(time.time() - c['_t0'])} giây). Chỉ chạy một bản vẽ một lúc: "
                                                     f"đợi xong (trang_thai_ban_ve) rồi gọi lại."], job_dang_chay=c["job_id"])
        job_id = uuid.uuid4().hex[:8]
        tmp_raw, tmp_norm = JOBS / f"_ve_{job_id}_goc.json", JOBS / f"_ve_{job_id}_chuan.json"
        try:
            JOBS.mkdir(parents=True, exist_ok=True)
            tmp_raw.write_text(text, encoding="utf-8")
        except OSError:
            return dict(hop_le=False, loai=loai, loi=[NOT_WRITABLE], loi_he_thong=True)
        chk = _run_cli(["check", loai, str(tmp_raw), "--write-spec", str(tmp_norm)], freecadcmd)
        if not chk.get("hop_le"):
            for t in (tmp_raw, tmp_norm):
                try:
                    t.unlink()
                except OSError:
                    pass
            return dict(hop_le=False, loai=loai, loi=chk.get("loi", ["spec không hợp lệ."]), **{k: chk[k] for k in ("thieu_bat_buoc", "loi_he_thong") if k in chk})
        d = JOBS / job_id
        norm = d / "spec.json"
        try:
            d.mkdir(parents=True, exist_ok=True)
            tmp_raw.replace(d / "spec_goc.json")
            tmp_norm.replace(norm)
        except OSError:
            return dict(hop_le=False, loai=loai, loi=[NOT_WRITABLE], loi_he_thong=True)
        job = dict(job_id=job_id, loai=loai, ten=chk["ten"], trang_thai="dang_chay", bat_dau=time.strftime("%Y-%m-%d %H:%M:%S"), thu_muc=f"out\\{chk['ten']}\\",
                   ty_le_du_kien=chk.get("ty_le"), canh_bao=chk.get("canh_bao", []), da_dung_mac_dinh=chk.get("da_dung_mac_dinh", []), _t0=time.time())
        _current = job
        _jobs[job_id] = job
        _save(job)
    threading.Thread(target=_worker, args=(job, norm, _env(freecadcmd)), name=f"banve-{job_id}", daemon=True).start()
    return dict(hop_le=True, job_id=job_id, ten=chk["ten"], trang_thai="dang_chay", ty_le_du_kien=chk.get("ty_le"), canh_bao=chk.get("canh_bao", []), da_dung_mac_dinh=chk.get("da_dung_mac_dinh", []), thu_muc=job["thu_muc"],
                nhac="Mỗi bản vẽ mất khoảng 30-60 giây; gọi trang_thai_ban_ve(job_id) để xem tiến độ/kết quả.")


def _load_job(job_id: str) -> dict | None:
    if job_id in _jobs:
        return _jobs[job_id]
    if not re.fullmatch(r"[0-9a-f]{8}", job_id or ""):
        return None
    f = JOBS / job_id / "job.json"
    try:
        job = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if job.get("trang_thai") == "dang_chay":             # persisted as running but no live worker: the server restarted meanwhile
        job.update(trang_thai="loi", loi="Máy chủ đã khởi động lại trong lúc dựng; hãy gọi lại ve_ban_ve.")
    return job


def trang_thai(job_id: str = "") -> tuple[dict, str | None]:
    """-> (status dict, path of the PNG to attach or None)."""
    job_id = job_id.strip() if isinstance(job_id, str) else ""
    if not job_id:
        with _lock:
            job_id = _current["job_id"] if _current else (max(_jobs.values(), key=lambda j: j["_t0"])["job_id"] if _jobs else "")
        if not job_id:
            return dict(hop_le=False, loi=["Chưa có bản vẽ nào được dựng trong phiên này. Gọi ve_ban_ve trước."]), None
    job = _load_job(job_id)
    if job is None:
        return dict(hop_le=False, loi=[f"Không tìm thấy job_id {job_id[:20]!r}."]), None
    pub = {k: v for k, v in job.items() if not k.startswith("_")}
    if job.get("trang_thai") == "dang_chay":
        pub["da_chay_giay"] = int(time.time() - job["_t0"]) if "_t0" in job else None
    png = None
    kt = (job.get("ket_qua") or {}).get("tep", {})
    if job.get("trang_thai") == "xong" and kt.get("png"):
        p = REPO / kt["png"]
        if p.is_file() and p.stat().st_size <= MAX_PNG_BYTES:
            png = str(p)
        elif p.is_file():
            pub["ghi_chu"] = f"Ảnh PNG lớn hơn {MAX_PNG_BYTES // 1000} KB nên không đính kèm; mở tệp {kt['png']}."
    return pub, png
