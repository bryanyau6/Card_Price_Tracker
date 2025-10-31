@echo OFF
REM 更改目錄到 .bat 檔案所在的資料夾 (即 Card_Price_Tracker 資料夾)
cd /d "%~dp0"

REM 執行你的「總指揮」Python 腳本 (使用你日誌中顯示的 Python 絕對路徑)
echo [INFO] 正在啟動總指揮腳本...
C:\Users\bryan\AppData\Local\Programs\Python\Python313\python.exe run_all_scrapers.py

echo [INFO] 總指揮腳本執行完畢。