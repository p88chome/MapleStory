"""視覺模組的煙霧測試（不需要遊戲，用合成圖驗證邏輯）。

執行： python -m tests.test_vision
"""
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.vision.bars import bar_ratio
from src.vision.minimap import find_player
from src.vision.monsters import MonsterDetector
from src.routing import Route


def test_minimap():
    mm = np.zeros((120, 180, 3), np.uint8)
    cv2.circle(mm, (50, 70), 2, (0, 221, 255), -1)  # 玩家黃點
    pos = find_player(mm, [0, 221, 255], 40)
    assert pos is not None and abs(pos[0] - 50) <= 2 and abs(pos[1] - 70) <= 2, pos
    assert find_player(np.zeros((120, 180, 3), np.uint8), [0, 221, 255], 40) is None
    print("  [OK] minimap 玩家定位")


def test_bar_ratio():
    bar = np.zeros((8, 100, 3), np.uint8)
    bar[:, :60] = (60, 60, 230)  # 60% 血
    r = bar_ratio(bar, [60, 60, 230], 60)
    assert abs(r - 0.6) < 0.03, r
    assert bar_ratio(np.zeros((8, 100, 3), np.uint8), [60, 60, 230], 60) == 0.0
    print("  [OK] 血條比例偵測")


def test_monster_downscale():
    # 造一個有紋理的假怪物，貼到場景 (200, 80) 的位置
    rng = np.random.default_rng(7)
    monster = rng.integers(0, 255, (48, 64, 3), dtype=np.uint8)
    scene = np.full((360, 700, 3), 30, np.uint8)
    scene[80:128, 200:264] = monster

    with tempfile.TemporaryDirectory() as d:
        cv2.imwrite(str(Path(d) / "mob.png"), monster)
        for scale in (1.0, 0.5):
            det = MonsterDetector(d, 0.7, match_flipped=True, downscale=scale)
            hits = det.detect(scene)
            assert hits, f"scale={scale} 沒抓到怪"
            best = hits[0]
            # 縮圖後座標要能映射回原始座標（容差 = 1/scale 像素）
            assert abs(best["x"] - 200) <= 2 / scale and abs(best["y"] - 80) <= 2 / scale, \
                (scale, best)
            assert best["w"] == 64 and best["h"] == 48  # 回報的是原始尺寸
    print("  [OK] 怪物偵測（含 0.5 縮圖座標映射）")


def test_monster_masked():
    """去背圖（alpha）模板：只比對怪物本體、忽略透明背景。"""
    rng = np.random.default_rng(3)
    # 怪物本體：中間 32x40 的紋理，四周透明
    body = rng.integers(0, 255, (40, 32, 3), dtype=np.uint8)
    sprite = np.zeros((60, 56, 4), dtype=np.uint8)
    sprite[10:50, 12:44, :3] = body
    sprite[10:50, 12:44, 3] = 255  # 只有本體不透明

    # 場景：雜訊背景 + 只把「本體」貼上去（模擬遊戲裡怪站在複雜背景前）
    scene = rng.integers(0, 255, (300, 500, 3), dtype=np.uint8)
    scene[150 + 10:150 + 50, 220 + 12:220 + 44] = body

    with tempfile.TemporaryDirectory() as d:
        cv2.imwrite(str(Path(d) / "mob.png"), sprite)  # 4 通道 PNG
        det = MonsterDetector(d, 0.7, match_flipped=False,
                              downscale=1.0, masked_threshold=0.9)
        assert det.templates[0][2] is not None, "alpha 模板應產生 mask"
        hits = det.detect(scene)
        assert hits, "mask 比對應該要在雜訊背景上抓到去背怪"
        best = hits[0]
        assert abs(best["x"] - 220) <= 2 and abs(best["y"] - 150) <= 2, best
    print("  [OK] 去背圖 mask 比對（雜訊背景）")


def test_route():
    img = np.zeros((120, 180, 3), np.uint8)
    img[100, 10:80] = (0, 0, 255)    # 紅 = 往左走
    img[100, 100:170] = (255, 0, 0)  # 藍 = 往右走
    img[60:100, 90] = (0, 255, 0)    # 綠 = 爬繩
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "route.png"
        cv2.imwrite(str(p), img)
        colors = {"walk_left": [0, 0, 255], "walk_right": [255, 0, 0],
                  "climb_up": [0, 255, 0]}
        route = Route(str(p), colors, 30, 12)
        assert route.action_at(40, 98) == "walk_left"
        assert route.action_at(130, 102) == "walk_right"
        assert route.action_at(91, 70) == "climb_up"
        assert route.action_at(0, 0) is None  # 半徑外
    print("  [OK] 路線圖動作判讀")


if __name__ == "__main__":
    test_minimap()
    test_bar_ratio()
    test_monster_downscale()
    test_monster_masked()
    test_route()
    print("全部測試通過 ✓")
