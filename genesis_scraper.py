# =========================================================
# Phase 1, Block 1.1: 創世爬蟲 (Genesis Scraper) v7.1 (自動排序最終版)
# Author: 電王
# Update: 在將數據寫入 Google Sheet 之前，在後端進行完美的雙重排序。
# =========================================================
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path
import time
import sys
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

# --- [步驟 A: 本地端 Google Sheets 授權] --- (不變)
print(">> 步驟 A: 正在進行本地端 Google Sheets 授權...")
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = None
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not os.path.exists('credentials.json'):
             print("\n❌ 錯誤: 找不到 'credentials.json' 檔案。")
             sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
gc = gspread.authorize(creds)
print("✅ Google Sheets 授權成功。")

# --- [設定區域] ---
sheet_name = "卡牌價格追蹤系統 - Command Deck"
worksheet_name = "Card_Master"
game_title = "One Piece Card Game"
base_url = "https://www.onepiece-cardgame.com"
SERIES_TARGET_LIST = [
    "550101", "550102", "550103", "550104", "550105", "550106", "550107", "550108", "550109", "550110", "550111", "550112", "550113",
    "550201", "550202", "550203", "550301", "550302",
    "552101", "552102", "552103", "552104", "552105", "552106", "552107", "552108", "552109", "552110", "552111", "552112", "552113", "552114", "552115", "552116", "552117", "552118", "552119",
    "554101", "554102", "554103", "554104", "554105", "554106", "554107", "554108", "554109", "554110", "554111", "554112", "554113",
]

# --- [主程式開始] ---
try:
    print("\n>> 創世爬蟲 v7.1 (自動排序最終版) 已啟動...")
    worksheet = gc.open(sheet_name).worksheet(worksheet_name)
    print("✅ 指揮室連接成功。")
    
    all_cards_data = []
    print(f"\n>> 準備對 {len(SERIES_TARGET_LIST)} 個已知目標發動最終打擊...")
    
    driver = uc.Chrome(headless=False, use_subprocess=True)

    for i, series_id in enumerate(SERIES_TARGET_LIST):
        series_url = f"{base_url}/cardlist/?series={series_id}"
        print(f"  -> 正在打擊目標 {i+1}/{len(SERIES_TARGET_LIST)} (Series ID: {series_id})...")
        
        try:
            driver.get(series_url)
            time.sleep(5) 
            series_html = driver.page_source
            series_soup = BeautifulSoup(series_html, 'html.parser')
            cards = series_soup.find_all('dl', class_='modalCol')

            if not cards:
                print("   -> 資訊為空。")
                continue

            print(f"   -> 勝利！捕獲 {len(cards)} 張卡牌情報！")
            
            for card in cards:
                try:
                    info_spans = card.select('div.infoCol span')
                    card_number = info_spans[0].text.strip()
                    rarity = info_spans[1].text.strip()
                    card_type = info_spans[2].text.strip()
                    
                    official_name = card.find('div', 'cardName').text.strip()
                    image_tag = card.select_one('div.frontCol img.lazy')
                    image_url = base_url + image_tag['data-src'] if image_tag else ""
                    
                    set_id = card_number.split('-')[0]
                    if not rarity: rarity = "N/A"
                    unique_id = f"{card_number}_{rarity}"
                    
                    all_cards_data.append([
                        unique_id, card_number, game_title, set_id, 
                        official_name, rarity, image_url, card_type
                    ])
                except Exception as e:
                     print(f"    - 警告: 解析卡片 {card.get('id', '')} 時發生錯誤: {e}")
            
        except Exception as e:
            print(f"   -> 訪問失敗。錯誤: {e}")
            continue

    print(f"\n✅ 所有目標打擊完畢，共捕獲 {len(all_cards_data)} 張卡牌的完整情報。")

    # *** 核心變更：在這裡加入魔法般的排序指令！ ***
    print("\n>> 正在對所有捕獲的情報進行後端排序...")
    # 規則：首先按 Set_ID (索引3) 排序，然後按 Card_Number (索引1) 排序
    all_cards_data.sort(key=lambda card: (card[3], card[1]))
    print("✅ 情報排序完畢。")

    if all_cards_data:
        print("\n>> 正在將所有情報寫入 `Card_Master` 指揮室...")
        worksheet.clear()
        headers = ["UniqueID", "Card_Number", "Game_Title", "Set_ID", 
                   "Official_Name", "Rarity", "Image_URL", "Card_Type"]
        worksheet.append_row(headers)
        worksheet.append_rows(all_cards_data, value_input_option='USER_ENTERED')
        print("✅ 情報寫入成功！")
    
    print("\n\n🎉🎉🎉 勝利！ `Card_Master` 已成功建立並完美排序！ 🎉🎉🎉")
    print("Phase 1, Block 1.1 - 目標已完全征服！")

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌")
    print(f"錯誤詳情: {e}")
finally:
    if 'driver' in locals():
        print("\n>> 任務結束，正在關閉匿蹤瀏覽器...")
        driver.quit()