@echo OFF
REM 戰術指令 v3.0 (新基地 + Python 3.14)

REM 更改目錄到 .bat 檔案所在的資料夾 (C:\projects\Card_Price_Tracker_NEW)
cd /d "%~dp0"

REM 執行總指揮腳本 (使用您已安裝工具的 Python 3.14)
echo [INFO] 正在啟動總指揮腳本 (v7.5 自動維護版)...
C:\Python314\python.exe run_all_scrapers.py

echo [INFO] 總指揮腳本執行完畢。
pause