"""小地圖玩家定位：在小地圖區域裡找玩家點（顏色比對）。"""
import cv2
import numpy as np


def find_player(minimap_bgr: np.ndarray, color_bgr, tolerance: int):
    """回傳玩家點在小地圖內的 (x, y)，找不到回傳 None。"""
    color = np.array(color_bgr, dtype=np.int16)
    lower = np.clip(color - tolerance, 0, 255).astype(np.uint8)
    upper = np.clip(color + tolerance, 0, 255).astype(np.uint8)
    mask = cv2.inRange(minimap_bgr, lower, upper)
    if cv2.countNonZero(mask) == 0:
        return None
    # 取所有符合像素的質心，比單點更穩
    ys, xs = np.nonzero(mask)
    return int(xs.mean()), int(ys.mean())
