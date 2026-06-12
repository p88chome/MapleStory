"""怪物圖下載器 —— 從 maplestory.io 開放資料庫自動抓怪物 PNG（去背圖）。

跟 KenYu910645/MapleStoryAutoLevelUp 的 mob_maker 相同的素材來源。
Artale / 楓星這類懷舊版的怪物 = 舊版楓之谷的怪，預設用 GMS v65 的圖庫。

用法：
    # 1. 搜怪物（英文名，可上 https://maplestory.wiki/GMS/65/mob 查）
    python -m tools.mob_downloader --search "snail"

    # 2. 用 id 下載到指定的模板資料夾
    python -m tools.mob_downloader --id 100100 --out assets/monsters/my_map

    # 3. 或直接用名字（取搜尋結果第一筆）
    python -m tools.mob_downloader --name "Blue Snail" --out assets/monsters/my_map

    # 其他版本/地區（例如繁中服 TMS 可用中文名搜尋）：
    python -m tools.mob_downloader --region TMS --version 209 --search "菇"

下載的 PNG 帶透明背景（alpha），偵測器會自動改用 mask 比對，
門檻用 config 的 monster.masked_threshold（預設 0.90）。
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

BASE = "https://maplestory.io/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (MapleBot asset downloader)"}
# 預設抓這幾種動作的前幾幀（不抓死亡動畫，跟 Ken 的做法一致）
DEFAULT_ACTIONS = ["stand", "move", "hit1"]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def get_mob_list(region: str, version: str) -> list[dict]:
    """抓怪物清單（會快取到 assets/_captured/，第二次起秒開）。"""
    cache = ROOT / "assets" / "_captured" / f"moblist_{region}_{version}.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    print(f"下載怪物清單 {region}/{version}（第一次會比較久）...")
    data = _get(f"{BASE}/{region}/{version}/mob")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return json.loads(data)


def search(mobs: list[dict], keyword: str) -> list[dict]:
    kw = keyword.casefold()
    return [m for m in mobs if kw in str(m.get("name", "")).casefold()]


def download_mob(region: str, version: str, mob_id: int, mob_name: str,
                 out_dir: Path, actions: list[str], max_frames: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w一-鿿-]", "_", mob_name) or str(mob_id)
    total = 0
    for action in actions:
        for frame in range(max_frames):
            url = f"{BASE}/{region}/{version}/mob/{mob_id}/render/{action}/{frame}"
            try:
                png = _get(url)
            except (urllib.error.HTTPError, urllib.error.URLError):
                break  # 這個動作沒有更多幀了
            if not png.startswith(b"\x89PNG"):
                break
            out = out_dir / f"{safe}_{action}{frame}.png"
            out.write_bytes(png)
            print(f"  ✓ {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
            total += 1
    if total == 0:
        print(f"  ✗ {mob_name} ({mob_id}) 一張都沒抓到，"
              f"請確認 id 正確、或試試其他 --actions（如 stand,move,hit1,attack1）")
    else:
        print(f"完成：{mob_name} 共 {total} 張（建議刪到剩 2~3 張代表性的省效能）")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="GMS",
                    help="圖庫地區：GMS(預設)/TMS/KMS/JMS...")
    ap.add_argument("--version", default="65",
                    help="圖庫版本，懷舊怪用 65（預設）")
    ap.add_argument("--search", help="搜尋怪物名稱（子字串）")
    ap.add_argument("--id", type=int, help="直接指定怪物 id 下載")
    ap.add_argument("--name", help="用名稱下載（取第一筆符合）")
    ap.add_argument("--out", default=str(ROOT / "assets" / "monsters" / "downloaded"),
                    help="輸出資料夾（建議 assets/monsters/<你的地圖名>）")
    ap.add_argument("--actions", default=",".join(DEFAULT_ACTIONS),
                    help=f"要抓的動作，逗號分隔（預設 {','.join(DEFAULT_ACTIONS)}）")
    ap.add_argument("--max-frames", type=int, default=4,
                    help="每個動作最多抓幾幀（預設 4）")
    args = ap.parse_args()

    if not (args.search or args.id or args.name):
        ap.print_help()
        return

    mobs = get_mob_list(args.region, args.version)

    if args.search:
        hits = search(mobs, args.search)
        print(f"找到 {len(hits)} 筆：")
        for m in hits[:40]:
            print(f"  id={m['id']:<9} {m['name']}")
        if len(hits) > 40:
            print("  ...（太多了，請輸入更精確的關鍵字）")
        return

    if args.id:
        mob_id = args.id
        mob_name = next((m["name"] for m in mobs if m["id"] == mob_id), str(mob_id))
    else:
        hits = search(mobs, args.name)
        if not hits:
            print(f"找不到名稱包含「{args.name}」的怪物，先用 --search 查查看")
            return
        mob_id, mob_name = hits[0]["id"], hits[0]["name"]
        print(f"選用第一筆：{mob_name} (id={mob_id})")

    download_mob(args.region, args.version, mob_id, mob_name,
                 Path(args.out), args.actions.split(","), args.max_frames)


if __name__ == "__main__":
    main()
