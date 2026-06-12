# MapleStory 楓星 視覺掛機 (Auto Level Up)

純「電腦視覺」方案的自動練功程式：不讀遊戲記憶體、不改封包，
只靠**看畫面 + 模擬鍵盤**運作。架構參考
[KenYu910645/MapleStoryAutoLevelUp](https://github.com/KenYu910645/MapleStoryAutoLevelUp)（Artale 版），
但素材與 UI 座標全部做成可設定，方便適配「楓星」版本。

> ⚠️ 使用外掛違反遊戲服務條款，有封號風險，請自行評估。

## 運作原理

```
┌─ 每秒 10 次 ──────────────────────────────────────┐
│ 1. 擷取遊戲視窗畫面 (mss)                          │
│ 2. 看 HP/MP 條 → 低於門檻按藥水鍵                  │
│ 3. 在小地圖找玩家黃點 → 知道自己在地圖哪裡          │
│ 4. 在角色附近做怪物模板比對 (OpenCV)               │
│ 5. 範圍內有怪 → 轉身面向最近的怪出招；              │
│    沒怪 → 照路線圖巡邏                             │
│    (路線圖 = 你在小地圖截圖上用顏色描的線)          │
└──────────────────────────────────────────────────┘
```

## 安裝（Windows）

```bash
pip install -r requirements.txt
```

遊戲請用**視窗模式**執行。

## 設定流程（第一次使用，約 30 分鐘）

### 第 0 步：找到遊戲視窗

```bash
python -m tools.calibrate --list-windows
```

找到楓星的視窗標題，把關鍵字填到 `config/config.yaml` 的
`window.title_keyword`。如果擷取畫面上下有黑邊或包含標題列，
調整 `window.crop` 的四邊裁切值。

### 第 1 步：校準 UI 座標

```bash
python -m tools.calibrate
```

會開一個即時畫面，操作方式：

| 操作 | 功能 |
|---|---|
| 滑鼠**拖曳** | 框選區域，終端機印出 `{x, y, w, h}` → 貼到 config |
| 滑鼠**點一下** | 取得該像素 BGR 顏色 → 貼到 config |
| `空白鍵` | 凍結畫面（等怪物出現瞬間凍結再框選） |
| `s` | 把框選區存成 PNG（到 `assets/_captured/`） |
| `f` | 存整張畫面 |
| `q` | 離開 |

要校準的東西：

1. **小地圖區域** → 框選整個小地圖 → 填到 `minimap.region`
2. **玩家點顏色** → 點一下小地圖上代表你的點 → 填到 `minimap.player_color_bgr`
3. **HP 條** → 框選血條（只框「會變長變短」的部分）→ `potion.hp.bar_region`，
   再點一下血條中間取色 → `potion.hp.fill_color_bgr`；MP 同理

### 第 2 步：建立怪物模板

1. 在練功地圖開校準工具，怪物出現時按`空白鍵`凍結
2. 框選**一隻怪**（框緊一點、避開血條和名字）→ 按 `s` 儲存
3. 同一種怪建議截 2~4 張不同動作（站立、移動、被打）
4. 把 PNG 移到 `assets/monsters/<你的地圖名>/`，
   並把 `monster.set` 改成 `<你的地圖名>`

### 第 3 步：畫巡邏路線圖

1. 校準工具中框選小地圖 → 按 `s` 存出小地圖截圖
2. 用**小畫家**打開，沿著角色會走的路徑描線（粗 2~3px），顏色對照：

| 顏色 | RGB（小畫家用） | 動作 |
|---|---|---|
| 🔴 紅 | 255, 0, 0 | 往左走 |
| 🔵 藍 | 0, 0, 255 | 往右走 |
| 🟠 橘 | 255, 165, 0 | 往左跳 |
| 🩵 青 | 0, 255, 255 | 往右跳 |
| 🟡 黃 | 255, 255, 0 | 原地跳（跳上台階） |
| 🟢 綠 | 0, 255, 0 | 爬繩/梯子（按住上） |
| 🟣 紫 | 128, 0, 128 | 往下爬 / 下跳 |

   範例：平台兩端來回 → 平台左半描紅線、右半描藍線、
   兩端交界各留一小段相反色，角色就會左右來回巡邏。
   繩子位置畫一條垂直綠線、繩子頂端接平台的地方畫黃/橘/青色即可爬上去。

3. 存成 PNG 放到 `assets/routes/`，檔名填到 `route.map`
   （**圖片尺寸必須跟 `minimap.region` 的 w/h 一致**，直接拿步驟 1 存的圖來畫就不會錯）

### 第 4 步：設定按鍵

`config/config.yaml` 的 `attack.key`（攻擊技能）、`potion.*.key`（藥水）、
`keys.jump` 改成你遊戲內的按鍵設定。

技能類型用 `attack.directional` 控制：
* `true`（預設）= 方向性技能，出招前會自動轉身面向最近的怪
* `false` = 以自己為中心的 AOE，原地放招

## 執行

### 控制面板（建議）

```bash
python -m src.gui
```

開一個置頂的小視窗，可以：

* **開始 / 暫停 / 停止**（熱鍵 F8 / F12 同時有效）
* 分頁調參（戰鬥 / 藥水 / 偵測 / 系統），按「**套用變更**」立即生效不用重啟
* 換怪物資料夾 / 路線圖 / 縮圖倍率後按「**重載素材**」熱重載
* 「**儲存設定**」寫回 `config.yaml`，下次啟動沿用
* 狀態列即時顯示目前動作（attack/patrol/...）和每圈耗時

> 調參流程：開著 Debug 視窗 → 邊看偵測框邊在面板改門檻 → 套用 →
> 滿意後儲存 → 關掉 Debug 視窗進效能模式長時間掛機。

### 純命令列（最省資源）

```bash
python -m src.main
```

* 啟動後是**暫停狀態**，切回遊戲視窗後按 **F8** 開始
* **F8** 暫停/繼續（會放開所有按鍵）、**F12** 結束
* Debug 視窗會畫出：怪物偵測框（綠）、攻擊範圍（黃框）、
  小地圖玩家點（紫）、目前狀態文字 —— 先看這個視窗確認偵測都正常再放著掛

## 調參指南

| 症狀 | 調整 |
|---|---|
| 怪一直抓不到 | `monster.match_threshold` 調低（如 0.65），或多截幾張模板 |
| 一直誤判背景是怪 | threshold 調高（如 0.8），模板框緊一點 |
| 找不到玩家點 | 重新取色 `player_color_bgr`，或加大 tolerance |
| 走到路線外卡住 | 路線線條畫粗一點，或加大 `route.search_radius` |
| 血條偵測亂喝水 | 重新框 `bar_region`（只框會縮短的填充部分）|
| 轉身轉不過去 / 出招前會走動 | `attack.turn_delay` 調大 / 調小（0.06~0.12）|
| 技能放了但打不到怪 | `attack.range.x` 改成符合技能實際射程 |

## 效能（弱電腦掛一整天）

> 常見問題：「用 YOLO 會不會比較快？」—— **不會，反而更慢。**
> YOLO 這類神經網路要有 NVIDIA GPU 才快，純 CPU 上比 template matching
> 慢一個數量級。YOLO 的優勢是準確度（怪物變形/重疊也認得），
> 如果之後誤判嚴重再考慮，效能問題交給下面這些優化。

內建的效能優化：

1. **縮圖比對** `monster.downscale: 0.5` — 比對計算量降到約 1/4（預設已開）
2. **效能模式** `runtime.debug_window: false` — 不抓整張畫面，
   只抓「偵測框 + 小地圖 + 血條」三個小區域（長時間掛機必開）
3. **視窗位置快取** — 自動，每 2 秒才重新找一次遊戲視窗
4. **血魔條降頻檢查** `runtime.potion_check_every: 5` — 每 5 個迴圈看一次

弱電腦建議設定：

```yaml
monster:
  downscale: 0.5
  detect_box: { w: 500, h: 300 }   # 偵測框縮小，比對面積更小
runtime:
  fps: 7                            # 打怪節奏沒那麼快，7fps 很夠用
  debug_window: false               # 調試完就關
```

再加上：怪物模板每種怪留 2~3 張就好（每多一張模板就多一次全區比對，
`match_flipped: true` 還會再翻倍）、遊戲本身解析度調低一級也有幫助。

## 專案結構

```
src/
  main.py            入口、主迴圈、熱鍵
  controller.py      決策狀態機（喝水→打怪→巡邏）
  capture.py         遊戲視窗擷取
  input.py           DirectInput 鍵盤模擬
  routing.py         路線圖解讀
  vision/
    minimap.py       小地圖玩家定位
    monsters.py      怪物模板比對 + NMS
    bars.py          HP/MP 條比例偵測
tools/
  calibrate.py       校準 + 素材擷取工具
config/config.yaml   所有設定（座標、顏色、按鍵、門檻）
assets/
  monsters/<map>/    怪物模板 PNG
  routes/            路線圖 PNG
```

## 打包成 exe（給不裝 Python 的使用者）

兩種方式擇一：

**方式 A：GitHub 雲端打包（推薦，本機什麼都不用裝）**

1. GitHub repo 頁面 → **Actions** → **Build Windows EXE** → **Run workflow**
2. 等 5~10 分鐘跑完，進該次 run 頁面下載 `MapleBot-windows` 壓縮檔

**方式 B：本機打包**（要先 `pip install -r requirements.txt`）

```bash
build.bat
```

兩種方式產出的內容一樣，整包發給使用者即可：

```
dist/
  MapleBot.exe            ← 控制面板，雙擊就能用（日常使用）
  MapleBot-Calibrate.exe  ← 校準/截素材工具
  config/config.yaml      ← 在 exe「旁邊」，使用者可直接編輯
  assets/                 ← 怪物模板/路線圖，可直接替換不用重新打包
```

設計重點：config 和 assets **刻意不打包進 exe 內**，
換素材、改設定都不需要重新打包——GUI 的「儲存設定」也是寫到 exe 旁的
`config/config.yaml`。

> 注意：PyInstaller 打包的 onefile exe 偶爾會被防毒軟體誤判，
> 是已知的誤報問題；自己打包的話加入白名單即可。

## Roadmap（之後可加）

- [ ] 被傳送 / 視窗異常 / 玩家靠近 → 警報音 + 自動停止
- [ ] 自動換頻道
- [ ] 撿物
- [ ] 輪迴(rune)自動解
