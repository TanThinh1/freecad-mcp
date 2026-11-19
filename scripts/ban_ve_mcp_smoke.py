"""Smoke test of the drawing MCP tools through a REAL stdio MCP session (starts `uv run freecad-mcp` from this repository).

    uv run python scripts/ban_ve_mcp_smoke.py

Needs the TCVN profile path in TCVN_PROFILE or in out/tcvn_profile.txt. Prints each tool call with its wall time; a full drawing takes 30-60 s.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "scripts" / "drawing" / "examples"
sys.stdout.reconfigure(encoding="utf-8")


def spec(name):
    d = json.loads((EX / f"{name}.json").read_text(encoding="utf-8-sig"))
    d.pop("ten", None)
    d.pop("loai", None)
    return d


def payload(res):
    texts = [c.text for c in res.content if c.type == "text"]
    imgs = [c for c in res.content if c.type == "image"]
    try:
        data = json.loads(texts[0]) if texts else {}
    except ValueError:
        data = {"raw": texts[0][:300] if texts else ""}
    return data, len(imgs), res.isError


async def main():
    params = StdioServerParameters(command="uv", args=["--directory", str(REPO), "run", "freecad-mcp"], env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools if t.name in ("huong_dan_ve", "kiem_tra_spec", "ve_ban_ve", "trang_thai_ban_ve"))
            print("tools:", names)

            async def call(name, args):
                t = time.perf_counter()
                res = await s.call_tool(name, args)
                dt = time.perf_counter() - t
                d, n_img, err = payload(res)
                return d, n_img, err, dt

            cases = [("thang", "a2_3000x17"), ("luoi_cot", "b2_12000x30000"), ("khung_ngang", "c5_11000x6000_le")]
            for loai, ex in cases:
                d, _, err, dt = await call("huong_dan_ve", {"loai": loai})
                print(f"huong_dan_ve({loai}): {dt:.2f}s keys={sorted(d)[:6]} loi={err}")
            for loai, ex in cases:
                d, _, err, dt = await call("kiem_tra_spec", {"loai": loai, "spec": spec(ex)})
                print(f"kiem_tra_spec({loai}): {dt:.2f}s hop_le={d.get('hop_le')} ten={d.get('ten')} ty_le={d.get('ty_le')} canh_bao={len(d.get('canh_bao', []))} so_do={d.get('so_do')}")
            bad = {"thang": {"cao_tang": -5, "so_bac": 1, "be_rong_mat_bac": 250, "be_rong_ve": 800, "dam_con": "H75x150x2"},
                   "luoi_cot": {"nhip": 16500, "dai_nha": 31750, "buoc_cot": 6000, "tiet_dien_cot": "H300x150x6x9"},
                   "khung_ngang": {"nhip": 0, "cao_cot": 6000, "do_doc_mai": 120, "so_mai": 3, "tiet_dien_cot": "abc", "tiet_dien_keo": "H250x125x6x9"}}
            for loai, sp_ in bad.items():
                d, _, err, dt = await call("kiem_tra_spec", {"loai": loai, "spec": sp_})
                print(f"kiem_tra_spec(LOI {loai}): {dt:.2f}s hop_le={d.get('hop_le')} loi={d.get('loi')}")
                d, _, err, dt = await call("ve_ban_ve", {"loai": loai, "spec": sp_})
                print(f"ve_ban_ve(LOI {loai}): {dt:.2f}s hop_le={d.get('hop_le')} job_id={d.get('job_id')} loi={len(d.get('loi', []))} thông báo")
            # 4.4: deliberate error case - dai_nha 31750 is not a multiple of buoc_cot 6000: must report the 1750 mm remainder, suggest 30000 / 36000 and NOT start a job
            sp44 = {"nhip": 16500, "dai_nha": 31750, "buoc_cot": 6000}
            d, _, err, dt = await call("kiem_tra_spec", {"loai": "luoi_cot", "spec": sp44})
            msg = " ".join(d.get("loi", []))
            print(f"4.4 kiem_tra_spec: {dt:.2f}s hop_le={d.get('hop_le')} du1750={'1750' in msg} goi_y30000={'30000' in msg} goi_y36000={'36000' in msg}")
            d, _, err, dt = await call("ve_ban_ve", {"loai": "luoi_cot", "spec": sp44})
            print(f"4.4 ve_ban_ve: {dt:.2f}s hop_le={d.get('hop_le')} job_id={d.get('job_id')} (khong dung)")
            d, _, err, dt = await call("kiem_tra_spec", {"loai": "thang", "spec": {"cao_tang": 3000, "so_bac": 17}})
            print(f"thieu so bat buoc: hop_le={d.get('hop_le')} thieu={d.get('thieu_bat_buoc')}")
            d, _, err, dt = await call("kiem_tra_spec", {"loai": ["x"], "spec": 5})
            print(f"sai kieu: isError={err} {d.get('loi') or d.get('raw', '')[:80]}")
            d, _, err, dt = await call("kiem_tra_spec", {"loai": "mai_nha", "spec": {}})
            print(f"kiem_tra_spec(loai sai): {dt:.2f}s {d.get('loi')}")
            for loai, ex in cases:
                d, _, err, dt = await call("ve_ban_ve", {"loai": loai, "spec": spec(ex)})
                print(f"ve_ban_ve({loai}): trả sau {dt:.2f}s job_id={d.get('job_id')} ten={d.get('ten')} {d.get('trang_thai')}")
                jid = d.get("job_id")
                if loai == "thang":
                    d2, _, err2, dt2 = await call("ve_ban_ve", {"loai": "luoi_cot", "spec": spec("b2_12000x30000")})
                    print(f"  ve_ban_ve khi đang bận: {dt2:.2f}s ban={d2.get('ban')} isError={err2} {d2.get('loi')}")
                t0 = time.perf_counter()
                while True:
                    st, n_img, err, dt = await call("trang_thai_ban_ve", {"job_id": jid})
                    if st.get("trang_thai") != "dang_chay":
                        break
                    await asyncio.sleep(3)
                kq = st.get("ket_qua", {})
                print(f"  -> {st.get('trang_thai')} sau {time.perf_counter() - t0:.0f}s (tổng {st.get('thoi_gian_tong_giay')}s) kiểm tra={kq.get('kiem_tra', {}).get('dat')}/{kq.get('kiem_tra', {}).get('tong')} "
                      f"không đạt={kq.get('kiem_tra', {}).get('khong_dat')} ảnh={n_img} tệp={list(kq.get('tep', {}))} tỷ lệ={kq.get('ty_le')}")


asyncio.run(main())
