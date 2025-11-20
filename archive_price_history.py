# =========================================================
# Phase 4, Block 1.0: 維護工具 (Maintenance Tool) - 存檔 Price_History v1.3.1
# Author: 電王
# 戰術: 【v1.3 Purge Old Data - 精準清除版】
# 職責: 智能分析時間戳，只保留最新的 3 個「時段」的數據，其餘全部刪除。
#
# Update v1.3.1:
# 1. (來自 v1.3) 保留 3 個最新時段，永久刪除舊數據。
# 2. 【核心】: 增加了 'import sys'。
# 3. 【核心】: 在 'except' 模塊中增加了 'sys.exit(1)'，
#    確保此腳本在失敗時會返回錯誤代碼 1，
#    以便 run_all_scrapers.py (v7.5) 能夠中止後續任務。
# =========================================================
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path
from datetime import datetime, timedelta
import sys # <-- 【v1.3.1】 新增

# --- [步驟 A: 本地端 Google Sheets 授權] --- 
print(">> 步驟 A: 正在進行本地端 Google Sheets 授權...")
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = None
# ... (授權代碼不變) ...
if os.path.exists('token.json'): creds = Credentials.from_authorized_user_file('token.json', SCOPES)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        try: creds.refresh(Request())
        except Exception as e:
            print(f"❌ 刷新 Token 失敗: {e}");
            if os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES); creds = flow.run_local_server(port=0)
            else: print("\n❌ 錯誤: 找不到 'credentials.json'。"); sys.exit(1) # <-- 【v1.3.1】 增加
    else:
        if not os.path.exists('credentials.json'): print("\n❌ 錯誤: 找不到 'credentials.json'。"); sys.exit(1) # <-- 【v1.3.1】 增加
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES); creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token: token.write(creds.to_json())
gc = gspread.authorize(creds)
print("✅ Google Sheets 授權成功。")

# --- [設定區域] ---
sheet_name = "卡牌價格追蹤系統 - Command Deck"
history_worksheet_name = "Price_History"
SESSION_GAP_HOURS = 4  
SESSIONS_TO_KEEP = 2   

# --- [主程式開始] ---
try:
    print(f"\n>> 精準清除維護工具 v1.3.1 ({history_worksheet_name}) 已啟動...")
    print(f">> 正在連接到 Google Sheet: '{sheet_name}'...")
    sh = gc.open(sheet_name)
    print("✅ 連接成功。")

    print(f">> 正在打開工作表: '{history_worksheet_name}'...")
    try:
        history_worksheet = sh.worksheet(history_worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"❌ 錯誤: 找不到名為 '{history_worksheet_name}' 的工作表。")
        sys.exit(1) # <-- 【v1.3.1】 增加
        
    print(f"✅ 成功打開。正在讀取所有數據 (這可能需要幾分鐘)...")
    all_data = history_worksheet.get_all_values()
    
    if len(all_data) <= 1:
        print("✅ Price_History 為空或只有標頭，無需操作。任務完成。")
        sys.exit(0)

    headers = all_data[0]
    rows = all_data[1:]
    
    print(f"✅ 成功讀取 {len(rows)} 行數據 (含 {headers} 標頭)。")
    
    # --- 【v1.3 核心 - 時間邏輯】 ---
    print(f">> 正在分析時間戳 (F 欄) 以識別 {SESSIONS_TO_KEEP} 個最新時段...")
    
    unique_timestamps = set()
    for row in rows:
        try:
            ts_str = row[5] # F 欄 = 索引 5
            unique_timestamps.add(datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
        except (ValueError, IndexError):
            continue 

    if not unique_timestamps:
        print("❌ 錯誤: 找不到任何有效的時間戳數據，無法分析。")
        sys.exit(1) # <-- 【v1.3.1】 增加

    sorted_timestamps = sorted(list(unique_timestamps), reverse=True)

    sessions = []
    if sorted_timestamps:
        current_session = [sorted_timestamps[0]]
        for i in range(1, len(sorted_timestamps)):
            current_ts = sorted_timestamps[i]
            prev_ts = sorted_timestamps[i-1]
            if (prev_ts - current_ts) < timedelta(hours=SESSION_GAP_HOURS):
                current_session.append(current_ts)
            else:
                sessions.append(current_session)
                current_session = [current_ts]
        sessions.append(current_session) 

    print(f"   -> 分析完畢。共發現 {len(sessions)} 個獨立時段。")

    sessions_to_keep = sessions[0:SESSIONS_TO_KEEP]
    print(f"   -> 遵命。將保留最新的 {len(sessions_to_keep)} 個時段。")

    timestamps_to_keep_set = set()
    for session in sessions_to_keep:
        for dt in session:
            timestamps_to_keep_set.add(dt.strftime("%Y-%m-%d %H:%M:%S"))

    rows_to_keep = []
    rows_to_discard_count = 0
    
    for row in rows:
        if row[5] in timestamps_to_keep_set:
            rows_to_keep.append(row)
        else:
            rows_to_discard_count += 1
            
    print(f">> 總結: 保留 {len(rows_to_keep)} 行 (最新 {len(sessions_to_keep)} 個時段)，將永久刪除 {rows_to_discard_count} 行 (舊數據)。")

    # --- 【v1.3 核心 - 存檔邏輯 (刪除)】 ---
    
    if rows_to_discard_count == 0:
        print("✅ 沒有需要刪除的舊數據。任務完成。")
        sys.exit(0) # 正常退出
        
    print(f">> 步驟 1/2: 正在清空 '{history_worksheet_name}' 的所有數據...")
    history_worksheet.clear()
    print("   -> ✅ 清空完畢。")
    
    print(f">> 步驟 2/2: 正在將標頭和 {len(rows_to_keep)} 行新數據寫回 '{history_worksheet_name}'...")
    history_worksheet.append_row(headers, value_input_option='USER_ENTERED')
    if rows_to_keep:
        # (如果數據量很大，分批次寫入)
        if len(rows_to_keep) > 20000:
             print(f"   -> 數據量 ({len(rows_to_keep)} 行) 較大，將分批寫入...")
             # 每 20000 行寫入一次
             for i in range(0, len(rows_to_keep), 20000):
                 batch = rows_to_keep[i:i+20000]
                 history_worksheet.append_rows(batch, value_input_option='USER_ENTERED')
                 print(f"     -> 已寫入 {i + len(batch)} / {len(rows_to_keep)} 行...")
        else:
             history_worksheet.append_rows(rows_to_keep, value_input_option='USER_ENTERED')
            
    print("   -> ✅ 新數據寫回成功。")

    print(f"\n\n🎉🎉🎉 精準清除任務完成！🎉🎉🎉")
    print(f"'{history_worksheet_name}' 現已準備就緒，可以接收新的爬蟲數據。")

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); 
    print(f"錯誤詳情: {e}")
    sys.exit(1) # <-- 【v1.3.1 核心修正】