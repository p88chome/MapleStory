"""控制面板 GUI（Tkinter，Python 內建、零額外依賴）。

用法：
    python -m src.gui

- 開始/暫停/停止 按鈕（熱鍵 F8/F12 同時有效）
- 分頁調參：戰鬥 / 藥水 / 偵測 / 系統
- 「套用變更」：大部分參數立即生效，不用重啟
- 「重載素材」：換怪物模板資料夾 / 路線圖 / downscale 後按這個
- 「儲存設定」：寫回 config.yaml，下次啟動沿用
"""
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import yaml

from .controller import Bot
from .main import HotkeyState, ROOT

CONFIG_PATH = ROOT / "config" / "config.yaml"


# ---------- 設定欄位 → cfg dict 路徑 的綁定 ----------
class Field:
    """一個 UI 輸入欄位，綁定 cfg 裡的某個路徑（如 'attack.range.x'）。"""

    def __init__(self, cfg: dict, path: str, label: str):
        self.cfg = cfg
        self.keys = path.split(".")
        self.label = label
        cur = self._get()
        self.is_bool = isinstance(cur, bool)
        self.type = type(cur)
        self.var = tk.BooleanVar(value=cur) if self.is_bool else tk.StringVar(value=str(cur))

    def _get(self):
        cur = self.cfg
        for k in self.keys:
            cur = cur[k]
        return cur

    def apply(self):
        """把 UI 值寫回 cfg，型別跟原值一致。"""
        parent = self.cfg
        for k in self.keys[:-1]:
            parent = parent[k]
        if self.is_bool:
            parent[self.keys[-1]] = bool(self.var.get())
        else:
            raw = self.var.get().strip()
            parent[self.keys[-1]] = self.type(raw) if self.type in (int, float) else raw

    def refresh(self):
        if self.is_bool:
            self.var.set(self._get())
        else:
            self.var.set(str(self._get()))


class App:
    def __init__(self):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

        self.bot: Bot | None = None
        self.hk = HotkeyState(self.cfg["runtime"]["hotkey_pause"],
                              self.cfg["runtime"]["hotkey_quit"])
        self.worker: threading.Thread | None = None
        self.tick_ms = 0.0
        self.error_msg = ""  # 背景執行緒的錯誤，由 UI 輪詢顯示（執行緒安全）
        self.fields: list[Field] = []

        self.root = tk.Tk()
        self.root.title("MapleBot 控制面板")
        self.root.attributes("-topmost", True)  # 蓋在遊戲上方便操作
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_status()

    # ================= UI =================
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        self.btn_run = ttk.Button(top, text="▶ 開始 (F8)", command=self._toggle_run)
        self.btn_run.pack(side="left")
        ttk.Button(top, text="■ 停止", command=self._stop).pack(side="left", padx=6)
        ttk.Button(top, text="💾 儲存設定", command=self._save).pack(side="right")

        self.status_var = tk.StringVar(value="尚未啟動（按「開始」會連接遊戲視窗）")
        ttk.Label(self.root, textvariable=self.status_var, padding=(8, 0),
                  foreground="#0a6").pack(fill="x")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._tab(nb, "戰鬥", [
            ("attack.key", "攻擊技能按鍵"),
            ("attack.directional", "方向性技能（要面向怪）"),
            ("attack.turn_delay", "轉身按鍵時間（秒）"),
            ("attack.range.x", "攻擊距離 X（像素）"),
            ("attack.range.y", "攻擊距離 Y（像素）"),
            ("attack.cooldown", "施放間隔（秒）"),
        ])
        self._tab(nb, "藥水", [
            ("potion.hp.enabled", "自動喝 HP"),
            ("potion.hp.key", "HP 藥水按鍵"),
            ("potion.hp.threshold", "HP 門檻 (0~1)"),
            ("potion.mp.enabled", "自動喝 MP"),
            ("potion.mp.key", "MP 藥水按鍵"),
            ("potion.mp.threshold", "MP 門檻 (0~1)"),
        ])
        tab = self._tab(nb, "偵測", [
            ("monster.match_threshold", "怪物比對門檻 (0~1)"),
            ("monster.downscale", "縮圖倍率（重載生效）"),
            ("monster.detect_box.w", "偵測框寬"),
            ("monster.detect_box.h", "偵測框高"),
            ("route.search_radius", "路線搜尋半徑"),
        ])
        # 怪物資料夾 / 路線圖：用下拉選單列出 assets 裡現有的
        self._combo(tab, "monster.set", "怪物模板資料夾",
                    [p.name for p in (ROOT / "assets" / "monsters").iterdir() if p.is_dir()])
        self._combo(tab, "route.map", "路線圖",
                    [p.name for p in (ROOT / "assets" / "routes").glob("*.png")])
        ttk.Button(tab, text="↻ 重載素材（換地圖/downscale 後按）",
                   command=self._reload_assets).grid(
            column=0, columnspan=2, pady=(10, 0), sticky="w")

        self._tab(nb, "系統", [
            ("window.title_keyword", "遊戲視窗標題關鍵字"),
            ("runtime.fps", "主迴圈 FPS"),
            ("runtime.debug_window", "Debug 視窗（關=效能模式）"),
            ("runtime.potion_check_every", "血魔檢查頻率（每 N 圈）"),
            ("keys.jump", "跳躍鍵"),
        ])

        ttk.Button(self.root, text="✓ 套用變更（立即生效）", command=self._apply
                   ).pack(fill="x", padx=8, pady=(0, 8))

    def _tab(self, nb, title, items):
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text=title)
        for path, label in items:
            f = Field(self.cfg, path, label)
            self.fields.append(f)
            row = len(tab.grid_slaves()) // 2
            if f.is_bool:
                ttk.Checkbutton(tab, text=label, variable=f.var).grid(
                    row=row, column=0, columnspan=2, sticky="w", pady=2)
                ttk.Label(tab, text="").grid(row=row, column=1)  # 佔位讓 row 計算一致
            else:
                ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=2)
                ttk.Entry(tab, textvariable=f.var, width=14).grid(
                    row=row, column=1, sticky="w", padx=8)
        return tab

    def _combo(self, tab, path, label, values):
        f = Field(self.cfg, path, label)
        self.fields.append(f)
        row = len(tab.grid_slaves()) // 2
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(tab, textvariable=f.var, values=values, width=18).grid(
            row=row, column=1, sticky="w", padx=8)

    # ================= 動作 =================
    def _apply(self) -> bool:
        try:
            for f in self.fields:
                f.apply()
        except ValueError as e:
            messagebox.showerror("輸入錯誤", f"有欄位不是數字：{e}")
            return False
        if self.bot:
            self.bot.apply_tuning()
        self.status_var.set("已套用變更")
        return True

    def _reload_assets(self):
        if not self._apply():
            return
        if self.bot:
            try:
                self.bot.reload_assets(*self._asset_paths())
                self.status_var.set(f"已重載：{len(self.bot.detector.templates)} 個模板")
            except FileNotFoundError as e:
                messagebox.showerror("重載失敗", str(e))

    def _asset_paths(self):
        return (str(ROOT / "assets" / "monsters" / self.cfg["monster"]["set"]),
                str(ROOT / "assets" / "routes" / self.cfg["route"]["map"]))

    def _save(self):
        if not self._apply():
            return
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.cfg, f, allow_unicode=True, sort_keys=False)
        self.status_var.set(f"已儲存 → {CONFIG_PATH}")

    def _toggle_run(self):
        if not self._apply():
            return
        if self.worker is None or not self.worker.is_alive():
            # 第一次啟動：建立 bot + 背景執行緒
            try:
                self.bot = Bot(self.cfg, *self._asset_paths())
            except Exception as e:
                messagebox.showerror("啟動失敗", str(e))
                return
            self.hk.quit = False
            self.hk.paused = False
            self.worker = threading.Thread(target=self._loop, daemon=True)
            self.worker.start()
        else:
            self.hk.paused = not self.hk.paused

    def _stop(self):
        self.hk.quit = True
        if self.bot:
            self.bot.stop()

    def _on_close(self):
        self._stop()
        self.root.destroy()

    # ================= 背景主迴圈 =================
    def _loop(self):
        while not self.hk.quit:
            t0 = time.time()
            if self.hk.paused:
                self.bot.keys.release_all()
                time.sleep(0.1)
                continue
            try:
                dbg = self.bot.tick()
                if dbg is not None:
                    cv2.imshow("MapleBot Debug", dbg)
                    cv2.waitKey(1)
            except Exception as e:
                self.bot.keys.release_all()
                self.error_msg = str(e)
                time.sleep(1.0)
                continue
            self.error_msg = ""
            self.tick_ms = (time.time() - t0) * 1000
            interval = 1.0 / self.cfg["runtime"]["fps"]
            if (dt := time.time() - t0) < interval:
                time.sleep(interval - dt)
        self.bot.keys.release_all()
        cv2.destroyAllWindows()

    # ================= 狀態列輪詢 =================
    def _poll_status(self):
        if self.worker and self.worker.is_alive():
            if self.error_msg:
                self.btn_run.config(text="‖ 暫停 (F8)")
                self.status_var.set(f"⚠ 錯誤：{self.error_msg}")
            elif self.hk.paused:
                self.btn_run.config(text="▶ 繼續 (F8)")
                self.status_var.set("‖ 已暫停")
            else:
                self.btn_run.config(text="‖ 暫停 (F8)")
                self.status_var.set(
                    f"運作中 [{self.bot.status}]  每圈 {self.tick_ms:.0f}ms")
        else:
            self.btn_run.config(text="▶ 開始 (F8)")
        self.root.after(300, self._poll_status)

    def run(self):
        self.root.mainloop()


def main():
    App().run()


if __name__ == "__main__":
    main()
