"""巡邏路線系統。

路線圖 = 一張和小地圖截圖一樣大的圖片，
你用小畫家在「角色會走的路徑」上描上指定顏色的線，
每種顏色代表一個動作（往左走、往右走、跳、爬繩...）。

執行時：找出離玩家點最近的路線像素 → 顏色 → 動作。
"""
from pathlib import Path

import cv2
import numpy as np


class Route:
    def __init__(self, route_path: str, colors: dict, tolerance: int, search_radius: int):
        path = Path(route_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"找不到路線圖: {route_path}\n"
                "請先截一張小地圖、用小畫家描上路線顏色後存到 assets/routes/"
            )
        self.img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        self.search_radius = search_radius
        # 為每個動作建好顏色遮罩，查詢時直接用
        self.masks: dict[str, np.ndarray] = {}
        for action, bgr in colors.items():
            color = np.array(bgr, dtype=np.int16)
            lower = np.clip(color - tolerance, 0, 255).astype(np.uint8)
            upper = np.clip(color + tolerance, 0, 255).astype(np.uint8)
            self.masks[action] = cv2.inRange(self.img, lower, upper)

    def action_at(self, px: int, py: int) -> str | None:
        """回傳距離玩家 (px, py) 最近的路線動作，半徑內沒有則回傳 None。"""
        r = self.search_radius
        h, w = self.img.shape[:2]
        x0, y0 = max(0, px - r), max(0, py - r)
        x1, y1 = min(w, px + r + 1), min(h, py + r + 1)

        best_action, best_dist = None, None
        for action, mask in self.masks.items():
            ys, xs = np.nonzero(mask[y0:y1, x0:x1])
            if xs.size == 0:
                continue
            d2 = (xs + x0 - px) ** 2 + (ys + y0 - py) ** 2
            d = int(d2.min())
            if best_dist is None or d < best_dist:
                best_dist, best_action = d, action
        return best_action
