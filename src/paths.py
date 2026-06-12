"""路徑解析：開發模式用專案根目錄，打包成 exe 後用 exe 所在資料夾。

config/ 和 assets/ 刻意「不」打包進 exe 內部，而是放在 exe 旁邊，
這樣使用者不用重新打包就能改設定、換怪物模板和路線圖。
"""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):  # PyInstaller 打包後
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent
