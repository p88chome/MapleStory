"""校準 / 素材擷取工具 —— 建立你自己版本(楓星)素材的主要工具。

用法：
    python -m tools.calibrate --list-windows   # 列出所有視窗標題（找遊戲視窗關鍵字）
    python -m tools.calibrate                  # 開啟即時校準畫面

校準畫面操作：
    滑鼠拖曳   框選區域 → 終端機印出 {x, y, w, h}（直接貼到 config.yaml）
    滑鼠點一下 取色     → 終端機印出該像素的 BGR 值（玩家點/血條顏色用）
    空白鍵     凍結/解凍畫面（怪物出現的瞬間先凍結再框選）
    s          把「最後框選的區域」存成 PNG 到 assets/_captured/
               （怪物模板 → 移到 assets/monsters/<地圖名>/）
               （小地圖截圖 → 拿去畫路線後存到 assets/routes/）
    f          存整張畫面
    q          離開
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.capture import WindowCapture  # noqa: E402

OUT_DIR = ROOT / "assets" / "_captured"


class Calibrator:
    def __init__(self, cap: WindowCapture):
        self.cap = cap
        self.frame = None
        self.frozen = False
        self.drag_start = None
        self.drag_cur = None
        self.last_sel = None  # (x, y, w, h)

    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drag_start = (x, y)
            self.drag_cur = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drag_start:
            self.drag_cur = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.drag_start:
            x0, y0 = self.drag_start
            self.drag_start = None
            w, h = abs(x - x0), abs(y - y0)
            if w < 3 and h < 3:
                # 視為點擊 → 取色
                b, g, r = self.frame[y, x]
                print(f"取色 ({x},{y}) → BGR = [{b}, {g}, {r}]")
            else:
                sel = (min(x0, x), min(y0, y), w, h)
                self.last_sel = sel
                print(f"框選區域 → {{ x: {sel[0]}, y: {sel[1]}, w: {sel[2]}, h: {sel[3]} }}")

    def run(self):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        win = "Calibrate (q=quit, space=freeze, s=save-sel, f=save-frame)"
        cv2.namedWindow(win)
        cv2.setMouseCallback(win, self.on_mouse)
        print(__doc__)
        while True:
            if not self.frozen or self.frame is None:
                self.frame = self.cap.grab()
            disp = self.frame.copy()
            if self.drag_start and self.drag_cur:
                cv2.rectangle(disp, self.drag_start, self.drag_cur, (0, 255, 255), 1)
            if self.last_sel:
                x, y, w, h = self.last_sel
                cv2.rectangle(disp, (x, y), (x + w, y + h), (0, 255, 0), 1)
            if self.frozen:
                cv2.putText(disp, "FROZEN", (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (0, 0, 255), 2)
            cv2.imshow(win, disp)
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):
                self.frozen = not self.frozen
            elif key == ord("s") and self.last_sel:
                x, y, w, h = self.last_sel
                out = OUT_DIR / f"sel_{int(time.time())}.png"
                cv2.imwrite(str(out), self.frame[y:y + h, x:x + w])
                print(f"已儲存框選區域 → {out}")
            elif key == ord("f"):
                out = OUT_DIR / f"frame_{int(time.time())}.png"
                cv2.imwrite(str(out), self.frame)
                print(f"已儲存整張畫面 → {out}")
        cv2.destroyAllWindows()


def list_windows():
    import pygetwindow as gw
    print("目前所有視窗標題：")
    for w in gw.getAllWindows():
        if w.title.strip():
            print(f"  [{w.width}x{w.height}] {w.title}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-windows", action="store_true")
    ap.add_argument("--config", default=str(ROOT / "config" / "config.yaml"))
    args = ap.parse_args()

    if args.list_windows:
        list_windows()
        return

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cap = WindowCapture(cfg["window"]["title_keyword"], cfg["window"]["crop"])
    Calibrator(cap).run()


if __name__ == "__main__":
    main()
