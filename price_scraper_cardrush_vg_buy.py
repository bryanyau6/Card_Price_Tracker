# =========================================================
# Phase 1, Block 3.2: 價格爬蟲 (Price Scraper) - Card Rush VG 買取價 v1.2 (JPY-Only + API 優化)
# Author: 電王
# 戰術: 【JSON 提取】+【API 式分頁】+【v1.2 JPY-Only + API 優化】
# Update: v1.2 - 徹底移除所有匯率 (HKD) 相關代碼。
#         此腳本現在只負責抓取 JPY 原始價格並寫入 Sheet (9欄結構)。
#         【核心】: 將 get_all_records() 替換為 col_values(2)，
#                   解決因 Card_Master 過大導致的 APIError: [500] 錯誤。
# =========================================================
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path, time, re, random, json
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# import requests # <-- 【v1.2】 已移除

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
            else: print("\n❌ 錯誤: 找不到 'credentials.json'。"); exit()
    else:
        if not os.path.exists('credentials.json'): print("\n❌ 錯誤: 找不到 'credentials.json'。"); exit()
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES); creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token: token.write(creds.to_json())
gc = gspread.authorize(creds)
print("✅ Google Sheets 授權成功。")

# --- [VG 買取設定區域] ---
sheet_name = "卡牌價格追蹤系統 - Command Deck"
master_worksheet_name = "Card_Master"
history_worksheet_name = "Price_History"
website_name = "Cardrush-Media-Buy" 
base_url = "https://cardrush.media/vanguard/buying_prices"
game_title = "Vanguard"

# --- 【v1.2】 匯率換算函數已移除 --- 

# --- [主程式開始] ---
try:
    print(f"\n>> 價格爬蟲 v1.2 ({website_name} 買取價 - JPY-Only + API 優化) 已啟動...")
    print(">> 步驟 1/5: 正在讀取 `Card_Master` (優化模式)...") # 步驟重編
    master_worksheet = gc.open(sheet_name).worksheet(master_worksheet_name)
    history_worksheet = gc.open(sheet_name).worksheet(history_worksheet_name)
    
    # --- 【v1.2 API 優化】 ---
    print("     -> 正在讀取 Card_Number (B 欄)...")
    all_card_numbers = master_worksheet.col_values(2) # 2 = B 欄
    existing_card_numbers = set(all_card_numbers[1:]) # 移除標頭並轉為 Set
    print(f"✅ 讀取成功，資料庫中現有 {len(existing_card_numbers)} 條卡號紀錄以供參考。")
    # --- 【優化結束】 ---

    # --- 【v1.2】 步驟 2 (獲取匯率) 已移除 ---

    with sync_playwright() as p:
        print("\n>> 步驟 2/5: 正在啟動 Playwright 瀏覽器...") # 步驟重編
        browser = p.firefox.launch(headless=False)
        page = browser.new_page()
        print("✅ Playwright 瀏覽器準備就緒。")

        print("\n>> 步驟 3/5: 開始 API 式分頁掃蕩 (JSON 模式)...") # 步驟重編
        
        all_cardrush_cards = {}
        current_page = 1
        last_page = 1 
        
        while current_page <= last_page:
            page_url = f"{base_url}?displayMode=リスト&limit=100&page={current_page}&sort%5Bkey%5D=amount&sort%5Border%5D=desc&associations%5B%5D=ocha_product&to_json_option%5Bexcept%5D%5B%5D=original_image_source&to_json_option%5Bexcept%5D%5B%5D=created_at&to_json_option%5Binclude%5D%5Bocha_product%5D%5Bonly%5D%5B%5D=id&to_json_option%5Binclude%5D%5Bocha_product%5D%5Bmethods%5D%5B%5D=image_source"

            print(f"     -> 正在掃蕩頁面 {current_page} / {last_page}...")
            try:
                page.goto(page_url, wait_until='domcontentloaded', timeout=60000)
                
                # 等待 JSON data (v1.1 修正)
                json_data_element = page.wait_for_selector("script#__NEXT_DATA__", state='attached', timeout=60000) # 增加超時
                
                json_data_string = json_data_element.inner_text()
                data = json.loads(json_data_string)
                
                cards_on_page = data['props']['pageProps']['buyingPrices']
                
                if current_page == 1:
                    last_page = data['props']['pageProps']['lastPage'] 
                    print(f"     -> 偵測到總頁數: {last_page}")

                if not cards_on_page:
                    print("     -> 此頁面無數據，結束掃蕩。")
                    break

                for card in cards_on_page:
                    try:
                        item_name = card.get('name', 'N/A')
                        item_card_number = card.get('model_number', 'N/A')
                        price_jpy = int(card.get('amount', 0))
                        rarity = card.get('rarity', 'Unknown')
                        card_type = card.get('nation', 'Unknown') 
                        
                        image_url = ""
                        if card.get('ocha_product') and card['ocha_product'].get('image_source'):
                            image_url = card['ocha_product']['image_source']
                            image_url = image_url.strip() 
                            image_url = re.sub(r'\s+', '%20', image_url) # URL 空格處理
                        
                        status = "買取中"

                        if item_card_number == 'N/A':
                            continue 

                        all_cardrush_cards[(item_card_number, item_name)] = {
                            'price_jpy': price_jpy, 
                            'status': status, 
                            'image_url': image_url,
                            'rarity': rarity,
                            'card_type': card_type
                        }
                    except Exception as e_inner:
                        print(f"       -> 解析單張卡牌時失敗: {e_inner} - {card.get('name')}")
                        
                print(f"     -> ✅ 頁面 {current_page} 解析完畢，捕獲 {len(cards_on_page)} 條情報。")
                
            except Exception as e:
                print(f"     -> ❌ 掃蕩頁面 {current_page} 時失敗: {e}")
            
            current_page += 1
            time.sleep(random.uniform(1, 3)) 

        print(f"\n✅ 所有 VG 買取頁面掃蕩完畢，共捕獲 {len(all_cardrush_cards)} 種卡牌的情報。")

        print("\n>> 步驟 4/5: 開始執行情報擴張 (VG) 與價格記錄...") # 步驟重編
        new_cards_to_add = []
        price_history_to_add = []

        for (item_card_number, item_name), card_info in all_cardrush_cards.items():
            price_jpy = card_info['price_jpy']; status = card_info['status']; image_url = card_info['image_url']
            rarity = card_info['rarity']; card_type = card_info['card_type']
            # --- 【v1.2】 price_hkd 已移除 ---

            # --- 【v1.2】 新卡檢查 ---
            if item_card_number not in existing_card_numbers:
                print(f"     -> ✨ 發現新 VG 卡牌！ {item_card_number} {item_name}")
                
                set_id = item_card_number.split('/')[0].split('-')[0] if '/' in item_card_number else "VG_Unknown"
                unique_id = f"{item_card_number}_{rarity}"
                
                new_cards_to_add.append([
                    unique_id, item_card_number, game_title, set_id,
                    item_name, rarity, image_url, card_type
                ])
                # existing_cards_map is removed
                existing_card_numbers.add(item_card_number) 
                print(f"       -> 已準備將其添加到 `Card_Master`。")

            history_unique_id = f"{item_card_number}_{item_name}"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            history_id = f"{history_unique_id}_{website_name}_{timestamp}"
            set_id_history = item_card_number.split('/')[0].split('-')[0] if '/' in item_card_number else "VG_Unknown"

            # --- 【v1.2 JPY-Only 結構 (9 欄)】 ---
            price_history_to_add.append([
                history_id, history_unique_id, website_name,
                "N/A",      # D: Sell_Price_JPY
                price_jpy,  # E: Buy_Price_JPY
                timestamp,  # F: Timestamp
                status,     # G: Status
                set_id_history, # H: Set_ID
                image_url   # I: Image_URL
            ])

        print(f"\n✅ 情報處理完畢。準備新增 {len(new_cards_to_add)} 張新 VG 卡牌，記錄 {len(price_history_to_add)} 條 VG 買取價格 (JPY)。")

        if price_history_to_add:
             print(">> 正在對捕獲的情報進行後端排序..."); price_history_to_add.sort(key=lambda record: (record[1], record[5])); print("✅ 情報排序完畢。")

        print("\n>> 步驟 5/5: 正在將數據寫入 Google Sheet...") # 步驟重編
        if new_cards_to_add:
            print(f"     -> 正在將 {len(new_cards_to_add)} 張新 VG 卡牌寫入 `Card_Master`...")
            master_worksheet.append_rows(new_cards_to_add, value_input_option='USER_ENTERED')
            print("     -> ✅ 新 VG 卡牌寫入成功！")
        else: print("     -> 未發現需要添加到 `Card_Master` 的新 VG 卡牌。")

        if price_history_to_add:
            print(f"     -> 正在將 {len(price_history_to_add)} 條 VG 買取價格情報 (JPY-Only) **追加**到 `Price_History`...")
            history_worksheet.append_rows(price_history_to_add, value_input_option='USER_ENTERED')
            print("     -> ✅ VG 買取價格情報追加成功！")
        else:
            print("     -> 未捕獲到需要添加到 `Price_History` 的 VG 買取價格情報。")

        print("\n\n🎉🎉🎉 恭喜！Card Rush (VG) 買取價 (JPY-Only) 征服任務完成！ 🎉🎉🎉")
        browser.close()

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); print(f"錯誤詳情: {e}")
    if 'browser' in locals() and browser.is_connected(): browser.close()