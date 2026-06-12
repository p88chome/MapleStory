@echo off
chcp 65001 >nul
REM ============================================
REM  在 Windows 上一鍵打包 MapleBot exe
REM  需求：已安裝 Python，且 pip install -r requirements.txt
REM ============================================

pip install pyinstaller || goto :error

echo.
echo [1/3] 打包控制面板 MapleBot.exe ...
pyinstaller --noconfirm --onefile --windowed --collect-all customtkinter --name MapleBot launcher.py || goto :error

echo.
echo [2/3] 打包校準工具 MapleBot-Calibrate.exe ...
pyinstaller --noconfirm --onefile --console --name MapleBot-Calibrate launcher_calibrate.py || goto :error

echo.
echo [3/3] 複製 config 與 assets 到 dist\ ...
xcopy /E /I /Y config dist\config >nul
xcopy /E /I /Y assets dist\assets >nul

echo.
echo ============================================
echo  完成！把整個 dist\ 資料夾複製給使用者即可：
echo    dist\MapleBot.exe            ← 控制面板（日常使用）
echo    dist\MapleBot-Calibrate.exe  ← 校準/截素材工具
echo    dist\config\config.yaml      ← 設定檔（exe 旁邊，可直接編輯）
echo    dist\assets\                 ← 怪物模板/路線圖（可直接替換）
echo ============================================
exit /b 0

:error
echo 打包失敗，請檢查上面的錯誤訊息
exit /b 1
