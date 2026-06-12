"""怪物偵測：用怪物圖片模板在角色附近區域做 template matching。"""
import os
from pathlib import Path

import cv2
import numpy as np


class MonsterDetector:
    def __init__(self, template_dir: str, threshold: float, match_flipped: bool):
        self.threshold = threshold
        self.templates: list[tuple[str, np.ndarray]] = []
        path = Path(template_dir)
        if not path.is_dir():
            raise FileNotFoundError(f"找不到怪物模板資料夾: {template_dir}")
        for f in sorted(path.glob("*.png")):
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            self.templates.append((f.stem, img))
            if match_flipped:
                self.templates.append((f.stem + "_flip", cv2.flip(img, 1)))
        if not self.templates:
            raise FileNotFoundError(f"{template_dir} 內沒有任何 png 模板")

    def detect(self, roi_bgr: np.ndarray) -> list[dict]:
        """在 ROI 內找怪。回傳 [{x, y, w, h, score, name}, ...]（ROI 座標）。"""
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        hits = []
        for name, tmpl in self.templates:
            th, tw = tmpl.shape
            if gray.shape[0] < th or gray.shape[1] < tw:
                continue
            res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.nonzero(res >= self.threshold)
            for x, y in zip(xs, ys):
                hits.append({
                    "x": int(x), "y": int(y), "w": tw, "h": th,
                    "score": float(res[y, x]), "name": name,
                })
        return _nms(hits)


def _nms(hits: list[dict], iou_thresh: float = 0.4) -> list[dict]:
    """簡單的 non-maximum suppression，去掉重疊的偵測框。"""
    hits = sorted(hits, key=lambda h: h["score"], reverse=True)
    kept: list[dict] = []
    for h in hits:
        if all(_iou(h, k) < iou_thresh for k in kept):
            kept.append(h)
    return kept


def _iou(a: dict, b: dict) -> float:
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union
