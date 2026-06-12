"""遊戲視窗畫面擷取。

用 pygetwindow 找到遊戲視窗的位置，再用 mss 高速截圖。
視窗模式下即使視窗被移動也能跟著抓（每次擷取前重新查詢視窗位置）。
"""
import time

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
    # 視窗位置快取秒數：列舉所有視窗其實很貴，不需要每幀做
    WINDOW_CACHE_SEC = 2.0

    def __init__(self, title_keyword: str, crop: dict):
        self.title_keyword = title_keyword
        self.crop = crop
        self._sct = mss()
        self._win = None
        self._win_time = 0.0

    def _get_window(self):
        now = time.time()
        if self._win is None or now - self._win_time > self.WINDOW_CACHE_SEC:
            self._win = self._find_window()
            self._win_time = now
        return self._win

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

    def client_size(self) -> tuple[int, int]:
        """遊戲畫面（裁掉邊框後）的 (寬, 高)。"""
        w = self._get_window()
        c = self.crop
        return (w.width - c["left"] - c["right"], w.height - c["top"] - c["bottom"])

    def grab(self, region: dict | None = None) -> np.ndarray:
        """擷取遊戲畫面，回傳 BGR 影像。

        region: 視窗內相對區域 {x,y,w,h}；None = 整個遊戲畫面。
        只抓需要的小區域比抓整張畫面快非常多（mss 成本和面積成正比）。
        """
        w = self._get_window()
        c = self.crop
        left, top = w.left + c["left"], w.top + c["top"]
        cw, ch = self.client_size()
        if region is not None:
            left += region["x"]
            top += region["y"]
            cw, ch = region["w"], region["h"]
        if cw <= 0 or ch <= 0:
            raise WindowNotFoundError("視窗太小或已最小化")
        img = np.asarray(self._sct.grab(
            {"left": left, "top": top, "width": cw, "height": ch}))  # BGRA
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def crop_region(frame: np.ndarray, region: dict) -> np.ndarray:
    """從畫面裁出 config 中定義的 {x,y,w,h} 區域。"""
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    return frame[y:y + h, x:x + w]
