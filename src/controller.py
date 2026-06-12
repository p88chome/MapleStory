"""主控制邏輯（狀態機）：定位 → 喝水 → 打怪 → 巡邏。"""
import random
import time

import cv2
import numpy as np

from .capture import WindowCapture, crop_region
from .input import KeyController, Cooldown
from .routing import Route
from .vision.bars import bar_ratio
from .vision.minimap import find_player
from .vision.monsters import MonsterDetector


class Bot:
    def __init__(self, cfg: dict, monster_dir: str, route_path: str):
        self.cfg = cfg
        self.capture = WindowCapture(cfg["window"]["title_keyword"], cfg["window"]["crop"])
        self.keys = KeyController()
        self.detector = MonsterDetector(
            monster_dir,
            cfg["monster"]["match_threshold"],
            cfg["monster"]["match_flipped"],
            cfg["monster"].get("downscale", 1.0),
        )
        self.route = Route(
            route_path,
            cfg["route"]["colors"],
            cfg["route"]["color_tolerance"],
            cfg["route"]["search_radius"],
        )
        self.attack_cd = Cooldown(cfg["attack"]["cooldown"])
        self.potion_cd = Cooldown(cfg["potion"]["cooldown"])
        self.buff_cds = []
        for buff in cfg["attack"].get("buffs") or []:
            cd = Cooldown(buff["interval"])
            cd._last = time.time()  # 開場先不放，等第一個間隔
            self.buff_cds.append((buff["key"], cd))

        self._last_pos = None
        self._last_move_time = time.time()
        self._tick_count = 0
        self.status = "init"

    # ---------- 每一幀的主流程 ----------
    def tick(self) -> np.ndarray | None:
        """執行一輪決策。debug 模式回傳視覺化影像，否則回傳 None。

        效能模式（debug_window: false）：不抓整張畫面，
        只分別抓「偵測框 / 小地圖 / 血條」幾個小區域，CPU 負擔低很多。
        """
        cfg = self.cfg
        self._tick_count += 1
        debug = cfg["runtime"]["debug_window"]
        frame = self.capture.grab() if debug else None

        # 1. 喝水（不需要每幀檢查，血量不會一瞬間掉光）
        if self._tick_count % cfg["runtime"].get("potion_check_every", 5) == 0:
            self._check_potions(frame)

        # 2. Buff
        for key, cd in self.buff_cds:
            if cd.ready():
                self.keys.tap(key)
                cd.trigger()

        # 3. 玩家定位（小地圖）
        mm = (crop_region(frame, cfg["minimap"]["region"]) if frame is not None
              else self.capture.grab(cfg["minimap"]["region"]))
        pos = find_player(mm, cfg["minimap"]["player_color_bgr"],
                          cfg["minimap"]["player_color_tolerance"])

        # 4. 怪物偵測（以畫面中心 = 角色 為中心的偵測框）
        roi, roi_offset = self._detect_roi(frame)
        monsters = self.detector.detect(roi)
        target = self._monster_in_attack_range(monsters, roi_offset)

        # 5. 決策：有怪 → 攻擊；沒怪 → 走路線
        if target is not None:
            self.status = "attack"
            self.keys.release_all()
            if self.attack_cd.ready():
                if cfg["attack"].get("directional", True):
                    # 方向性技能：先朝怪物方向轉身再出招
                    self._face_target(target, roi_offset)
                self.keys.tap(cfg["attack"]["key"])
                self.attack_cd.trigger()
        elif pos is not None:
            action = self.route.action_at(*pos)
            self.status = f"patrol:{action}"
            self._do_action(action)
            self._check_stuck(pos)
        else:
            # 找不到玩家點（轉場/被傳送/小地圖被擋住）→ 全部停下最安全
            self.status = "player_not_found"
            self.keys.release_all()

        if frame is None:
            return None
        return self._draw_debug(frame, mm, pos, monsters, roi_offset, target)

    # ---------- 喝水 ----------
    def _check_potions(self, frame):
        for kind in ("hp", "mp"):
            p = self.cfg["potion"][kind]
            if not p["enabled"] or not self.potion_cd.ready():
                continue
            roi = (crop_region(frame, p["bar_region"]) if frame is not None
                   else self.capture.grab(p["bar_region"]))
            ratio = bar_ratio(roi, p["fill_color_bgr"], p["fill_color_tolerance"])
            if 0.0 < ratio < p["threshold"]:  # ratio==0 多半是偵測失敗，不亂按
                self.keys.tap(p["key"])
                self.potion_cd.trigger()

    # ---------- 怪物 ----------
    def _detect_roi(self, frame):
        cw, ch = self.capture.client_size()
        bw = min(self.cfg["monster"]["detect_box"]["w"], cw)
        bh = min(self.cfg["monster"]["detect_box"]["h"], ch)
        x0 = max(0, cw // 2 - bw // 2)
        y0 = max(0, ch // 2 - bh // 2)
        if frame is not None:
            return frame[y0:y0 + bh, x0:x0 + bw], (x0, y0)
        return self.capture.grab({"x": x0, "y": y0, "w": bw, "h": bh}), (x0, y0)

    def _monster_in_attack_range(self, monsters, roi_offset):
        """回傳攻擊範圍內「水平距離最近」的怪（方向性技能優先打最近的）。"""
        cw, ch = self.capture.client_size()
        cx, cy = cw // 2, ch // 2
        rx = self.cfg["attack"]["range"]["x"]
        ry = self.cfg["attack"]["range"]["y"]
        best, best_dx = None, None
        for m in monsters:
            mx = roi_offset[0] + m["x"] + m["w"] // 2
            my = roi_offset[1] + m["y"] + m["h"] // 2
            dx = abs(mx - cx)
            if dx <= rx and abs(my - cy) <= ry:
                if best is None or dx < best_dx:
                    best, best_dx = m, dx
        return best

    def _face_target(self, target, roi_offset):
        """輕點方向鍵讓角色面向怪物（按太久會走動，所以只點一下）。"""
        cw, _ = self.capture.client_size()
        mx = roi_offset[0] + target["x"] + target["w"] // 2
        k = self.cfg["keys"]
        key = k["left"] if mx < cw // 2 else k["right"]
        self.keys.hold(key)
        time.sleep(self.cfg["attack"].get("turn_delay", 0.08))
        self.keys.release(key)
        self.status = f"attack:{'left' if mx < cw // 2 else 'right'}"

    # ---------- 移動 ----------
    def _do_action(self, action: str | None):
        k = self.cfg["keys"]
        if action == "walk_left":
            self.keys.hold_only([k["left"]])
        elif action == "walk_right":
            self.keys.hold_only([k["right"]])
        elif action == "jump_left":
            self.keys.hold_only([k["left"]])
            self.keys.tap(k["jump"])
        elif action == "jump_right":
            self.keys.hold_only([k["right"]])
            self.keys.tap(k["jump"])
        elif action == "jump":
            self.keys.hold_only([])
            self.keys.tap(k["jump"])
        elif action == "climb_up":
            self.keys.hold_only([k["up"]])
        elif action == "climb_down":
            self.keys.hold_only([k["down"]])
        else:
            # 半徑內找不到路線 → 保持上一個動作繼續走，通常很快會走回線上
            pass

    def _check_stuck(self, pos):
        now = time.time()
        if self._last_pos is None or pos != self._last_pos:
            self._last_pos = pos
            self._last_move_time = now
            return
        if now - self._last_move_time > self.cfg["runtime"]["stuck_seconds"]:
            # 卡住了：隨機跳 + 隨機方向走一下試圖脫困
            self.status = "stuck->escape"
            k = self.cfg["keys"]
            direction = random.choice([k["left"], k["right"]])
            self.keys.hold_only([direction])
            self.keys.tap(k["jump"])
            self._last_move_time = now

    # ---------- 視覺化 ----------
    def _draw_debug(self, frame, mm, pos, monsters, roi_offset, target):
        dbg = frame.copy()
        h, w = dbg.shape[:2]
        cx, cy = w // 2, h // 2
        # 攻擊範圍
        rx, ry = self.cfg["attack"]["range"]["x"], self.cfg["attack"]["range"]["y"]
        cv2.rectangle(dbg, (cx - rx, cy - ry), (cx + rx, cy + ry), (0, 255, 255), 1)
        # 怪物框
        for m in monsters:
            x = roi_offset[0] + m["x"]
            y = roi_offset[1] + m["y"]
            color = (0, 0, 255) if m is target else (0, 255, 0)
            cv2.rectangle(dbg, (x, y), (x + m["w"], y + m["h"]), color, 2)
            cv2.putText(dbg, f'{m["name"]} {m["score"]:.2f}', (x, y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        # 小地圖 + 玩家點 + 路線疊圖
        mr = self.cfg["minimap"]["region"]
        cv2.rectangle(dbg, (mr["x"], mr["y"]),
                      (mr["x"] + mr["w"], mr["y"] + mr["h"]), (255, 0, 255), 1)
        if pos is not None:
            cv2.circle(dbg, (mr["x"] + pos[0], mr["y"] + pos[1]), 4, (255, 0, 255), -1)
        # 狀態文字
        cv2.putText(dbg, f"[{self.status}]", (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        return dbg

    def stop(self):
        self.keys.release_all()
