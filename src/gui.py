"""控制面板 GUI（CustomTkinter 深色主題）。

用法：
    python -m src.gui

- 開始/暫停/停止（熱鍵 F8/F12 同時有效）、狀態指示燈
- 分頁調參：戰鬥 / 藥水 / 偵測 / 系統
- 門檻類參數用滑桿即時拖、開關類用 switch
- 「套用變更」立即生效；「重載素材」熱替換模板/路線；「儲存」寫回 config.yaml
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import cv2
import yaml

from tools import mob_downloader as mobdl
from .controller import Bot
from .main import HotkeyState
from .paths import ROOT

CONFIG_PATH = ROOT / "config" / "config.yaml"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# 配色
C_RUN = "#2fa572"      # 綠：運作中 / 開始
C_PAUSE = "#d99a1b"    # 琥珀：暫停
C_STOP = "#c0392b"     # 紅：停止 / 錯誤
C_IDLE = "#7a7a7a"     # 灰：待機
C_CARD = ("#dbdbdb", "#2b2b2b")


# ---------- 設定欄位 → cfg dict 路徑 的綁定 ----------
class Field:
    """一個 UI 輸入元件，綁定 cfg 裡的某個路徑（如 'attack.range.x'）。"""

    def __init__(self, cfg: dict, path: str, var: tk.Variable):
        self.cfg = cfg
        self.keys = path.split(".")
        self.var = var
        self.type = type(self._get())

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
        val = self.var.get()
        if isinstance(self.var, tk.BooleanVar):
            val = bool(val)
        elif isinstance(self.var, tk.DoubleVar):
            val = round(float(val), 3)
            if self.type is int:
                val = int(val)
        else:  # StringVar
            raw = str(val).strip()
            val = self.type(raw) if self.type in (int, float) else raw
        parent[self.keys[-1]] = val


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
        self.dl_queue: queue.Queue = queue.Queue()  # 下載執行緒 → UI 的訊息
        self.dl_mobs: list[dict] = []  # 目前列表顯示的搜尋結果

        self.root = ctk.CTk()
        self.root.title("MapleBot")
        self.root.geometry("440x640")
        self.root.minsize(400, 560)
        self.root.attributes("-topmost", True)
        self.font = ctk.CTkFont(family="Microsoft JhengHei UI", size=13)
        self.font_title = ctk.CTkFont(family="Microsoft JhengHei UI",
                                      size=20, weight="bold")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_status()

    # ================= UI =================
    def _build_ui(self):
        # ---- 標題列 ----
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(header, text="🍁 MapleBot", font=self.font_title
                     ).pack(side="left")
        self.pin_btn = ctk.CTkButton(
            header, text="📌", width=34, fg_color=C_RUN,
            command=self._toggle_pin)
        self.pin_btn.pack(side="right")

        # ---- 狀態列（指示燈 + 文字）----
        status = ctk.CTkFrame(self.root, corner_radius=10, fg_color=C_CARD)
        status.pack(fill="x", padx=14, pady=6)
        self.dot = ctk.CTkLabel(status, text="●", text_color=C_IDLE,
                                font=ctk.CTkFont(size=16), width=20)
        self.dot.pack(side="left", padx=(10, 0), pady=8)
        self.status_var = tk.StringVar(value="待機（按「開始」連接遊戲視窗）")
        ctk.CTkLabel(status, textvariable=self.status_var, font=self.font,
                     anchor="w").pack(side="left", fill="x", expand=True,
                                      padx=8, pady=8)

        # ---- 主控按鈕 ----
        ctrl = ctk.CTkFrame(self.root, fg_color="transparent")
        ctrl.pack(fill="x", padx=14, pady=4)
        self.btn_run = ctk.CTkButton(
            ctrl, text="▶  開始 (F8)", height=40, font=self.font,
            fg_color=C_RUN, hover_color="#26865c", command=self._toggle_run)
        self.btn_run.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(ctrl, text="■ 停止", width=90, height=40, font=self.font,
                      fg_color="transparent", border_width=2,
                      border_color=C_STOP, text_color=C_STOP,
                      hover_color=("#f2d7d5", "#3d2422"),
                      command=self._stop).pack(side="left", padx=(8, 0))

        # ---- 分頁 ----
        tabs = ctk.CTkTabview(self.root, corner_radius=10)
        tabs.pack(fill="both", expand=True, padx=14, pady=6)
        t_fight = tabs.add("戰鬥")
        t_potion = tabs.add("藥水")
        t_detect = tabs.add("偵測")
        t_dl = tabs.add("素材")
        t_sys = tabs.add("系統")
        for t in (t_fight, t_potion, t_detect, t_sys):
            t.grid_columnconfigure(1, weight=1)

        # 戰鬥
        self._entry(t_fight, "attack.key", "攻擊技能按鍵")
        self._switch(t_fight, "attack.directional", "方向性技能（要面向怪）")
        self._slider(t_fight, "attack.turn_delay", "轉身按鍵時間（秒）", 0.03, 0.2)
        self._entry(t_fight, "attack.range.x", "攻擊距離 X（像素）")
        self._entry(t_fight, "attack.range.y", "攻擊距離 Y（像素）")
        self._slider(t_fight, "attack.cooldown", "施放間隔（秒）", 0.1, 3.0)

        # 藥水
        self._switch(t_potion, "potion.hp.enabled", "自動喝 HP")
        self._entry(t_potion, "potion.hp.key", "HP 藥水按鍵")
        self._slider(t_potion, "potion.hp.threshold", "HP 門檻", 0.1, 0.9)
        self._switch(t_potion, "potion.mp.enabled", "自動喝 MP")
        self._entry(t_potion, "potion.mp.key", "MP 藥水按鍵")
        self._slider(t_potion, "potion.mp.threshold", "MP 門檻", 0.1, 0.9)

        # 偵測
        self._slider(t_detect, "monster.match_threshold", "怪物比對門檻（截圖）", 0.5, 0.95)
        self._slider(t_detect, "monster.masked_threshold", "怪物比對門檻（去背圖）", 0.7, 0.99)
        self._slider(t_detect, "monster.downscale", "縮圖倍率（重載生效）", 0.3, 1.0)
        self._entry(t_detect, "monster.detect_box.w", "偵測框寬")
        self._entry(t_detect, "monster.detect_box.h", "偵測框高")
        self.mobset_combo = self._combo(
            t_detect, "monster.set", "怪物模板資料夾",
            [p.name for p in (ROOT / "assets" / "monsters").iterdir()
             if p.is_dir()])
        self._combo(t_detect, "route.map", "路線圖",
                    [p.name for p in (ROOT / "assets" / "routes").glob("*.png")])
        ctk.CTkButton(t_detect, text="↻ 重載素材（換地圖 / 縮圖倍率後按）",
                      font=self.font, fg_color="transparent", border_width=1,
                      command=self._reload_assets).grid(
            column=0, columnspan=3, pady=(12, 0), sticky="we")

        # 素材下載
        self._build_download_tab(t_dl)

        # 系統
        self._entry(t_sys, "window.title_keyword", "遊戲視窗標題關鍵字")
        self._entry(t_sys, "runtime.fps", "主迴圈 FPS")
        self._switch(t_sys, "runtime.debug_window", "Debug 視窗（關 = 效能模式）")
        self._entry(t_sys, "runtime.potion_check_every", "血魔檢查頻率（每 N 圈）")
        self._entry(t_sys, "keys.jump", "跳躍鍵")

        # ---- 底部按鈕 ----
        bottom = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(2, 12))
        ctk.CTkButton(bottom, text="✓ 套用變更", height=36, font=self.font,
                      command=self._apply).pack(
            side="left", fill="x", expand=True)
        ctk.CTkButton(bottom, text="💾 儲存設定", height=36, font=self.font,
                      fg_color="transparent", border_width=1,
                      command=self._save).pack(side="left", padx=(8, 0))

    # ---------- 元件列產生器 ----------
    def _next_row(self, parent) -> int:
        return len(parent.grid_slaves()) and max(
            w.grid_info()["row"] for w in parent.grid_slaves()) + 1

    def _label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=self.font, anchor="w").grid(
            row=row, column=0, sticky="w", pady=5, padx=(2, 10))

    def _entry(self, parent, path, label):
        f = Field(self.cfg, path, tk.StringVar(value=str(self._cfg_get(path))))
        self.fields.append(f)
        row = self._next_row(parent)
        self._label(parent, label, row)
        ctk.CTkEntry(parent, textvariable=f.var, width=110, font=self.font,
                     justify="center").grid(row=row, column=1, columnspan=2,
                                            sticky="e", pady=5)

    def _switch(self, parent, path, label):
        f = Field(self.cfg, path, tk.BooleanVar(value=self._cfg_get(path)))
        self.fields.append(f)
        row = self._next_row(parent)
        self._label(parent, label, row)
        ctk.CTkSwitch(parent, text="", variable=f.var, width=48,
                      progress_color=C_RUN).grid(
            row=row, column=1, columnspan=2, sticky="e", pady=5)

    def _slider(self, parent, path, label, frm, to):
        f = Field(self.cfg, path, tk.DoubleVar(value=float(self._cfg_get(path))))
        self.fields.append(f)
        row = self._next_row(parent)
        self._label(parent, label, row)
        val_lbl = ctk.CTkLabel(parent, font=self.font, width=44,
                               text=f"{f.var.get():.2f}")
        val_lbl.grid(row=row, column=2, sticky="e", padx=(6, 0))
        ctk.CTkSlider(parent, variable=f.var, from_=frm, to=to,
                      progress_color=C_RUN,
                      command=lambda v, l=val_lbl: l.configure(text=f"{v:.2f}")
                      ).grid(row=row, column=1, sticky="we", pady=5)

    def _combo(self, parent, path, label, values):
        f = Field(self.cfg, path, tk.StringVar(value=str(self._cfg_get(path))))
        self.fields.append(f)
        row = self._next_row(parent)
        self._label(parent, label, row)
        cb = ctk.CTkComboBox(parent, variable=f.var, values=values or ["（無）"],
                             width=170, font=self.font)
        cb.grid(row=row, column=1, columnspan=2, sticky="e", pady=5)
        return cb

    # ---------- 素材下載分頁 ----------
    def _build_download_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # 地區/版本 + 搜尋列
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=3, sticky="we")
        self.dl_region = tk.StringVar(value="GMS")
        self.dl_version = tk.StringVar(value="65")
        ctk.CTkComboBox(top, variable=self.dl_region, width=80, font=self.font,
                        values=["GMS", "TMS", "KMS", "JMS", "CMS", "SEA"]
                        ).pack(side="left")
        ctk.CTkEntry(top, textvariable=self.dl_version, width=50,
                     font=self.font, justify="center").pack(side="left", padx=4)
        self.dl_search = tk.StringVar()
        ent = ctk.CTkEntry(top, textvariable=self.dl_search, font=self.font,
                           placeholder_text="怪物名稱…")
        ent.pack(side="left", fill="x", expand=True, padx=4)
        ent.bind("<Return>", lambda e: self._mob_search())
        self.dl_search_btn = ctk.CTkButton(top, text="🔍 搜尋", width=70,
                                           font=self.font,
                                           command=self._mob_search)
        self.dl_search_btn.pack(side="left")

        ctk.CTkLabel(tab, text="搜尋結果（可多選，Ctrl/Shift+點擊）",
                     font=self.font, anchor="w").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.dl_list = tk.Listbox(
            tab, selectmode="extended", height=7, activestyle="none",
            bg="#2b2b2b", fg="#e8e8e8", selectbackground=C_RUN,
            borderwidth=0, highlightthickness=0, font=("Microsoft JhengHei UI", 11))
        self.dl_list.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=4)

        # 目標資料夾 + 下載
        bottom = ctk.CTkFrame(tab, fg_color="transparent")
        bottom.grid(row=3, column=0, columnspan=3, sticky="we", pady=(4, 0))
        ctk.CTkLabel(bottom, text="存到資料夾", font=self.font).pack(side="left")
        self.dl_out = tk.StringVar(value=str(self.cfg["monster"]["set"]))
        ctk.CTkEntry(bottom, textvariable=self.dl_out, width=130,
                     font=self.font).pack(side="left", padx=6)
        self.dl_btn = ctk.CTkButton(bottom, text="⬇ 下載選取的怪", font=self.font,
                                    command=self._mob_download)
        self.dl_btn.pack(side="left", fill="x", expand=True)

        self.dl_log = ctk.CTkTextbox(tab, height=90, font=self.font,
                                     state="disabled", wrap="word")
        self.dl_log.grid(row=4, column=0, columnspan=3, sticky="we", pady=(6, 0))
        self._log_dl("怪物名稱可上 maplestory.wiki/GMS/65/mob 查（英文）；"
                     "懷舊怪用 GMS 65 圖庫即可。")

    def _log_dl(self, msg: str):
        """寫入下載日誌（只能在 UI 執行緒呼叫）。"""
        self.dl_log.configure(state="normal")
        self.dl_log.insert("end", msg + "\n")
        self.dl_log.see("end")
        self.dl_log.configure(state="disabled")

    def _set_dl_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.dl_search_btn.configure(state=state)
        self.dl_btn.configure(state=state)

    def _mob_search(self):
        kw = self.dl_search.get().strip()
        if not kw:
            return
        region, ver = self.dl_region.get().strip(), self.dl_version.get().strip()
        self._set_dl_busy(True)

        def work():
            try:
                mobs = mobdl.get_mob_list(region, ver, log=self.dl_queue.put)
                hits = mobdl.search(mobs, kw)
                self.dl_queue.put(("results", hits[:60]))
            except Exception as e:
                self.dl_queue.put(f"搜尋失敗：{e}")
                self.dl_queue.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def _mob_download(self):
        sel = self.dl_list.curselection()
        if not sel:
            self._log_dl("請先在列表選取要下載的怪物")
            return
        chosen = [self.dl_mobs[i] for i in sel]
        region, ver = self.dl_region.get().strip(), self.dl_version.get().strip()
        out = ROOT / "assets" / "monsters" / (self.dl_out.get().strip() or "downloaded")
        self._set_dl_busy(True)

        def work():
            try:
                for m in chosen:
                    self.dl_queue.put(f"下載 {m['name']} (id={m['id']}) ...")
                    mobdl.download_mob(region, ver, m["id"], str(m["name"]), out,
                                       mobdl.DEFAULT_ACTIONS, 4,
                                       log=self.dl_queue.put)
                self.dl_queue.put(
                    f"全部完成 → {out}\n"
                    "到「偵測」分頁選這個資料夾並按「重載素材」即可生效")
            except Exception as e:
                self.dl_queue.put(f"下載失敗：{e}")
            finally:
                self.dl_queue.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def _drain_dl_queue(self):
        """把下載執行緒的訊息搬進 UI（在 _poll_status 內呼叫）。"""
        try:
            while True:
                item = self.dl_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "results":
                    self.dl_mobs = item[1]
                    self.dl_list.delete(0, "end")
                    for m in self.dl_mobs:
                        self.dl_list.insert("end", f"  {m['name']}   (id={m['id']})")
                    self._log_dl(f"找到 {len(self.dl_mobs)} 筆")
                    self._set_dl_busy(False)
                elif isinstance(item, tuple) and item[0] == "done":
                    self._set_dl_busy(False)
                    # 重新整理「怪物模板資料夾」下拉選單
                    self.mobset_combo.configure(values=[
                        p.name for p in (ROOT / "assets" / "monsters").iterdir()
                        if p.is_dir()])
                else:
                    self._log_dl(str(item))
        except queue.Empty:
            pass

    def _cfg_get(self, path):
        cur = self.cfg
        for k in path.split("."):
            cur = cur[k]
        return cur

    # ================= 動作 =================
    def _toggle_pin(self):
        top = not self.root.attributes("-topmost")
        self.root.attributes("-topmost", top)
        self.pin_btn.configure(fg_color=C_RUN if top else C_IDLE)

    def _apply(self) -> bool:
        try:
            for f in self.fields:
                f.apply()
        except ValueError as e:
            messagebox.showerror("輸入錯誤", f"有欄位不是數字：{e}")
            return False
        if self.bot:
            self.bot.apply_tuning()
        return True

    def _reload_assets(self):
        if not self._apply():
            return
        if self.bot:
            try:
                self.bot.reload_assets(*self._asset_paths())
                self.status_var.set(
                    f"已重載：{len(self.bot.detector.templates)} 個模板")
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
        self.status_var.set("已儲存設定 ✓")

    def _toggle_run(self):
        if not self._apply():
            return
        if self.worker is None or not self.worker.is_alive():
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
        self._drain_dl_queue()
        running = self.worker and self.worker.is_alive()
        if running and self.error_msg:
            self.dot.configure(text_color=C_STOP)
            self.btn_run.configure(text="‖  暫停 (F8)", fg_color=C_PAUSE)
            self.status_var.set(f"錯誤：{self.error_msg}")
        elif running and self.hk.paused:
            self.dot.configure(text_color=C_PAUSE)
            self.btn_run.configure(text="▶  繼續 (F8)", fg_color=C_RUN)
            self.status_var.set("已暫停（所有按鍵已放開）")
        elif running:
            self.dot.configure(text_color=C_RUN)
            self.btn_run.configure(text="‖  暫停 (F8)", fg_color=C_PAUSE)
            self.status_var.set(
                f"運作中 [{self.bot.status}]　每圈 {self.tick_ms:.0f}ms")
        else:
            self.dot.configure(text_color=C_IDLE)
            self.btn_run.configure(text="▶  開始 (F8)", fg_color=C_RUN)
        self.root.after(300, self._poll_status)

    def run(self):
        self.root.mainloop()


def main():
    App().run()


if __name__ == "__main__":
    main()
