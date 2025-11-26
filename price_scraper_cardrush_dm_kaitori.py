# =========================================================
# Phase 1, Block 3.3: 價格爬蟲 (Price Scraper) - Card Rush DM 買取 v1.2
# Author: 電王
# 戰術: 【v1.1 JPY-Only + API 優化】+【v1.1.2 導航邏輯修正】
# Update: v1.2   - 新增批次寫入機制，降低長程執行時的資料遺失風險。
# Update: v1.1.2 - 徹底移除所有匯率 (HKD) 相關代碼。
#         解決 [500] API 錯誤。
#         增加 __NEXT_DATA__ 等待超時至 60 秒。
#         【核心】: 修正分頁導航邏輯，
#                   不再手動構建 URL，而是直接使用 <a> 標籤中完整的 href 屬性。
# =========================================================
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path, time, re, random, json, sys
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# import requests # <-- 【v1.1】 已移除

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
            else: print("\n❌ 錯誤: 找不到 'credentials.json'。"); sys.exit(1)
    else:
        if not os.path.exists('credentials.json'): print("\n❌ 錯誤: 找不到 'credentials.json'。"); sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES); creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token: token.write(creds.to_json())
gc = gspread.authorize(creds)
print("✅ Google Sheets 授權成功。")

# --- [DM 買取 設定區域] ---
sheet_name = "卡牌價格追蹤系統 - Command Deck"
master_worksheet_name = "Card_Master"
history_worksheet_name = "Price_History"
website_name = "Cardrush-DM-Kaitori" 
base_url = "https://cardrush.media" # 根域名
game_title = "DuelMasters"
TARGET_URL = "https://cardrush.media/duel_masters/buying_prices" 

# --- [v1.2] 批次寫入設定 ---
MASTER_BATCH_SIZE = 100
HISTORY_BATCH_SIZE = 200

# --- 【v1.1】 匯率換算函數已移除 --- 

# --- [主程式開始] ---
try:
    print(f"\n>> 價格爬蟲 v1.1.2 ({website_name} 買取 - JPY-Only + API 優化 + 導航修正) 已啟動...")
    print(">> 步驟 1/5: 正在讀取 `Card_Master` (優化模式)...") 
    master_worksheet = gc.open(sheet_name).worksheet(master_worksheet_name)
    history_worksheet = gc.open(sheet_name).worksheet(history_worksheet_name)
    
    # --- 【v1.1 API 優化】 ---
    print("     -> 正在讀取 Card_Number (B 欄)...")
    all_card_numbers = master_worksheet.col_values(2) 
    existing_card_numbers = set(all_card_numbers[1:]) 
    print(f"✅ 讀取成功，資料庫中現有 {len(existing_card_numbers)} 條卡號紀錄以供參考。")
    # --- 【優化結束】 ---

    # --- 【v1.1】 步驟 2 (獲取匯率) 已移除 ---

    with sync_playwright() as p:
        print("\n>> 步驟 2/5: 正在啟動 Playwright 瀏覽器...") 
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        print("✅ Playwright 瀏覽器準備就緒。")

        print(f"\n>> 步驟 3/5: 開始掃蕩 DM 買取清單 (入口: {TARGET_URL})...") 
        all_cardrush_cards = {}
        current_page_num = 1
        
        # 初始加載
        try:
            print(f"   -> 正在導航至入口頁面 (等待 networkidle)...")
            # 確保使用包含所有參數的初始 URL
            initial_url = f"{TARGET_URL}?displayMode=リスト&limit=100&page=1&sort%5Bkey%5D=amount&sort%5Border%5D=desc&associations%5B%5D=ocha_product&to_json_option%5Bexcept%5D%5B%5D=original_image_source&to_json_option%5Bexcept%5D%5B%5D=created_at&to_json_option%5Binclude%5D%5Bocha_product%5D%5Bonly%5D%5B%5D=id&to_json_option%5Binclude%5D%5Bocha_product%5D%5Bmethods%5D%5B%5D=image_source"
            page.goto(initial_url, wait_until='networkidle', timeout=60000)
            print(f"   -> 入口頁面加載完成。標題: {page.title()}")
        except Exception as e:
            print(f"❌ 嚴重錯誤：無法加載買取頁面入口。 {e}");
            browser.close()
            exit()

        while True:
            print(f"   -> 正在掃蕩頁面 {current_page_num}...")
            try:
                # (v1.1.1 修正) 
                print(f"     -> 等待 __NEXT_DATA__ script 附加 (最長 60 秒)...")
                page.wait_for_selector('script#__NEXT_DATA__', state='attached', timeout=60000) 
                print(f"     -> ✅ __NEXT_DATA__ script 已找到。")
                
                time.sleep(1) 
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                data_script = soup.find('script', {'id': '__NEXT_DATA__'})
                if not data_script:
                    print(f"   -> ❌ 在第 {current_page_num} 頁未找到 __NEXT_DATA__ script (已等待60秒)，中止掃蕩。")
                    break
                    
                parsed_json = json.loads(data_script.string)
                card_list = parsed_json.get('props', {}).get('pageProps', {}).get('buyingPrices', [])
                
                if not card_list:
                    table_check = soup.select_one('table.PriceTable tbody')
                    if table_check and not table_check.find_all('tr'):
                         print(f"   -> ✅ 在第 {current_page_num} 頁 JSON 中未發現卡牌數據，且表格為空，判斷為結束頁。")
                    else:
                         print(f"   -> ⚠️ 在第 {current_page_num} 頁 JSON 中未發現卡牌數據，但表格似乎存在內容？可能解析錯誤。")
                    break

                print(f"   -> ✅ 在此頁面 JSON 中解析到 {len(card_list)} 張卡牌情報。")

                for card in card_list:
                    item_name = card.get('name', '').strip()
                    item_card_number = card.get('model_number', '').strip()
                    price_jpy = card.get('amount')
                    ocha_product = card.get('ocha_product', {})
                    image_url = ocha_product.get('image_source', '').strip() 
                    card_type = card.get('element', 'Unknown') 

                    if not item_name or (not item_card_number and "デッキ" not in item_name and "サプライ" not in item_name) or price_jpy is None:
                        continue
                    
                    # 如果卡號為空，但不是 Deck/Supply，嘗試從 name 提取
                    if not item_card_number:
                        dm_regex = r'\{([^}]+)\}'
                        match_num = re.search(dm_regex, item_name)
                        if match_num:
                            item_card_number = match_num.group(1).strip()
                        else:
                            continue # 真的沒有卡號，跳過
                    
                    all_cardrush_cards[(item_card_number, item_name)] = {
                        'price_jpy': int(price_jpy), 
                        'status': 'Wanting to Buy', 
                        'image_url': image_url, 
                        'card_type': card_type
                    }

                # --- 【v1.1.2 導航邏輯修正】 ---
                pagination_div = soup.select_one('div.Pagination__StyledPagination-sc-1b7j6i9-1')
                if not pagination_div:
                    print("   -> 未找到分頁器 (Pagination)，掃蕩完畢。")
                    break
                
                # 尋找準確的下一頁 (page=2, page=3, ...) 連結
                next_page_link_tag = pagination_div.select_one(f'a[href*="page={current_page_num + 1}"]')
                
                if not next_page_link_tag or 'null' in next_page_link_tag.get('class', []): 
                    print(f"   -> 未找到有效的 'page={current_page_num + 1}' 連結，掃蕩完畢。 (最後一頁是 {current_page_num})")
                    break
                    
                # 【核心】直接使用 href 提供的完整 URL
                next_url_path = next_page_link_tag['href']
                
                if next_url_path.startswith('/'):
                    next_page_full_url = base_url + next_url_path
                else:
                    next_page_full_url = next_url_path # href 可能是相對路徑
                
                # 確保 URL 包含域名
                if not next_page_full_url.startswith('http'):
                     next_page_full_url = base_url + next_page_full_url
                     
                print(f"   -> 準備前往下一頁: {next_page_full_url}")
                page.goto(next_page_full_url, wait_until='networkidle', timeout=60000)
                current_page_num += 1
                time.sleep(random.uniform(1.5, 3.5))
                # --- 【導航修正結束】 ---

            except PlaywrightTimeoutError:
                print(f"   -> ⚠️ 在第 {current_page_num} 頁等待元素超時 (已等待60秒)，可能已達最後一頁或頁面加載問題。")
                break
            except Exception as e: 
                print(f"   -> ❌ 掃蕩頁面 {current_page_num} 時失敗。錯誤: {e}"); 
                break

        print(f"\n✅ 所有 DM 買取頁面掃蕩完畢，共捕獲 {len(all_cardrush_cards)} 種卡牌的情報。")

        print("\n>> 步驟 4/5: 開始執行情報擴張 (DM) 與價格記錄...") 
        new_cards_to_add = []
        price_history_to_add = []
        total_new_cards = 0
        total_price_records = 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def flush_new_cards(force=False):
            if new_cards_to_add and (force or len(new_cards_to_add) >= MASTER_BATCH_SIZE):
                print(f"      -> 正在批次寫入 {len(new_cards_to_add)} 張新 DM 卡牌至 `Card_Master`...")
                master_worksheet.append_rows(new_cards_to_add, value_input_option='USER_ENTERED')
                print("      -> ✅ 新 DM 卡牌批次寫入完成！")
                new_cards_to_add.clear()

        def flush_price_history(force=False):
            if price_history_to_add and (force or len(price_history_to_add) >= HISTORY_BATCH_SIZE):
                print(f"      -> 正在批次寫入 {len(price_history_to_add)} 條 DM 買取價格至 `Price_History`...")
                price_history_to_add.sort(key=lambda record: (record[1], record[5]))
                history_worksheet.append_rows(price_history_to_add, value_input_option='USER_ENTERED')
                print("      -> ✅ DM 買取價格批次寫入完成！")
                price_history_to_add.clear()

        for (item_card_number, item_name), card_info in all_cardrush_cards.items():
            price_jpy = card_info['price_jpy']
            status = card_info['status']
            image_url = card_info['image_url']
            card_type = card_info['card_type']
            # --- 【v1.1】 price_hkd 已移除 ---

            # --- [情報擴張: Card_Master] ---
            if item_card_number not in existing_card_numbers:
                print(f"      -> ✨ 發現新 DM 卡牌！ {item_card_number} {item_name}")
                rarity = "Unknown"
                rarity_match = re.search(r'【([^】]+)】', item_name) 
                if rarity_match: rarity = rarity_match.group(1)
                set_id = item_card_number.split('/')[0].split('-')[0] if '/' in item_card_number else "DM_Unknown"
                unique_id = f"{item_card_number}_{rarity}"
                
                new_cards_to_add.append([
                    unique_id, item_card_number, game_title, set_id,
                    item_name, rarity, image_url, card_type
                ])
                existing_card_numbers.add(item_card_number)
                total_new_cards += 1
                print(f"         -> 已準備將其添加到 `Card_Master`。")
                flush_new_cards()

            # --- [價格記錄: Price_History] ---
            history_unique_id = f"{item_card_number}_{item_name}"
            history_id = f"{history_unique_id}_{website_name}_{timestamp}"
            set_id_history = item_card_number.split('/')[0].split('-')[0] if '/' in item_card_number else "DM_Unknown"

            # --- 【v1.1 JPY-Only 結構 (9 欄)】 ---
            price_history_to_add.append([
                history_id, history_unique_id, website_name,
                "N/A",      # D: Sell_Price_JPY
                price_jpy,  # E: Buy_Price_JPY
                timestamp,  # F: Timestamp
                status,     # G: Status
                set_id_history, # H: Set_ID
                image_url   # I: Image_URL
            ])
            total_price_records += 1
            flush_price_history()

        print(f"\n✅ 情報處理完畢。共偵測 {total_new_cards} 張新 DM 卡牌，記錄 {total_price_records} 條 DM 買取價格 (JPY)。")

        print("\n>> 步驟 5/5: 正在觸發最終批次寫入 (DM 買取)...") 

        flush_new_cards(force=True)
        if total_new_cards == 0:
            print("      -> 未發現需要添加到 `Card_Master` 的新 DM 卡牌。")
        else:
            print(f"      -> ✅ 累計寫入 `Card_Master` {total_new_cards} 張新 DM 卡牌。")

        flush_price_history(force=True)
        if total_price_records == 0:
            print("      -> 未捕獲到需要添加到 `Price_History` 的 DM 買取價格情報。")
        else:
            print(f"      -> ✅ 累計寫入 `Price_History` {total_price_records} 條 DM 買取價格情報。")

        print("\n\n🎉🎉🎉 恭喜！Card Rush (DM) 買取 (JPY-Only) 任務完成！ 🎉🎉🎉")
        browser.close()

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); 
    print(f"錯誤詳情: {e}")
    if 'browser' in locals() and browser.is_connected(): 
        browser.close()