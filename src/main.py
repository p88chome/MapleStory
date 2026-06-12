"""主程式入口。

用法：
    python -m src.main                       # 用 config/config.yaml
    python -m src.main --config my.yaml      # 指定設定檔

熱鍵（預設）：F8 = 暫停/繼續、F12 = 結束程式
"""
import argparse
import threading
import time
from pathlib import Path

import cv2
import yaml

from .controller import Bot

ROOT = Path(__file__).resolve().parent.parent


class HotkeyState:
    def __init__(self, pause_key: str, quit_key: str):
        self.paused = True   # 啟動時先暫停，按 F8 才開始（避免一啟動就亂按）
        self.quit = False
        self._pause_key = pause_key.lower()
        self._quit_key = quit_key.lower()
        try:
            from pynput import keyboard
            listener = keyboard.Listener(on_press=self._on_press)
            listener.daemon = True
            listener.start()
        except Exception as e:
            print(f"[警告] 熱鍵監聽啟動失敗: {e}（只能用 Ctrl+C 停止）")
            self.paused = False

    def _on_press(self, key):
        name = getattr(key, "name", None) or getattr(key, "char", None) or ""
        if name.lower() == self._pause_key:
            self.paused = not self.paused
            print(f"[熱鍵] {'暫停' if self.paused else '繼續'}")
        elif name.lower() == self._quit_key:
            self.quit = True
            print("[熱鍵] 結束程式")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "config.yaml"))
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    monster_dir = ROOT / "assets" / "monsters" / cfg["monster"]["set"]
    route_path = ROOT / "assets" / "routes" / cfg["route"]["map"]
    bot = Bot(cfg, str(monster_dir), str(route_path))

    rt = cfg["runtime"]
    hk = HotkeyState(rt["hotkey_pause"], rt["hotkey_quit"])
    interval = 1.0 / rt["fps"]

    print("=" * 50)
    print(f" 已載入 {len(bot.detector.templates)} 個怪物模板")
    print(f" 按 {rt['hotkey_pause'].upper()} 開始/暫停，{rt['hotkey_quit'].upper()} 結束")
    print("=" * 50)

    try:
        while not hk.quit:
            t0 = time.time()
            if hk.paused:
                bot.keys.release_all()
                time.sleep(0.1)
                continue
            try:
                dbg = bot.tick()
            except Exception as e:
                print(f"[錯誤] {e}")
                bot.keys.release_all()
                time.sleep(1.0)
                continue
            if dbg is not None:
                cv2.imshow("MapleBot Debug (q=quit)", dbg)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            dt = time.time() - t0
            if dt < interval:
                time.sleep(interval - dt)
    finally:
        bot.stop()
        cv2.destroyAllWindows()
        print("已停止，所有按鍵已放開。")


if __name__ == "__main__":
    main()
