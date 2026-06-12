"""遊戲視窗畫面擷取。

用 pygetwindow 找到遊戲視窗的位置，再用 mss 高速截圖。
視窗模式下即使視窗被移動也能跟著抓（每次擷取前重新查詢視窗位置）。
"""
import numpy as np
import cv2
from mss import mss

try:
    import pygetwindow as gw
except Exception:  # 非 Windows 環境（開發用）
    gw = None


class WindowNotFoundError(Exception):
    pass


class WindowCapture:
    def __init__(self, title_keyword: str, crop: dict):
        self.title_keyword = title_keyword
        self.crop = crop
        self._sct = mss()

    def _find_window(self):
        if gw is None:
            raise WindowNotFoundError("pygetwindow 無法使用（請在 Windows 上執行）")
        for w in gw.getAllWindows():
            if self.title_keyword.lower() in w.title.lower() and w.width > 200:
                return w
        raise WindowNotFoundError(
            f"找不到標題包含 '{self.title_keyword}' 的視窗，"
            "請確認遊戲已開啟，或用 tools/calibrate.py --list-windows 查正確標題"
        )

    def grab(self) -> np.ndarray:
        """擷取遊戲畫面 (裁掉標題列/邊框)，回傳 BGR 影像。"""
        w = self._find_window()
        c = self.crop
        region = {
            "left": w.left + c["left"],
            "top": w.top + c["top"],
            "width": w.width - c["left"] - c["right"],
            "height": w.height - c["top"] - c["bottom"],
        }
        if region["width"] <= 0 or region["height"] <= 0:
            raise WindowNotFoundError("視窗太小或已最小化")
        img = np.asarray(self._sct.grab(region))  # BGRA
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def crop_region(frame: np.ndarray, region: dict) -> np.ndarray:
    """從畫面裁出 config 中定義的 {x,y,w,h} 區域。"""
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    return frame[y:y + h, x:x + w]
