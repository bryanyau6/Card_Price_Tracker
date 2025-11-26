# =========================================================
# Phase 1, Block 2.2: 價格爬蟲 (Price Scraper) - Akiba UA 買取價 v1.3 (JPY-Only + API 優化)
# Author: 電王
# 戰術: 【v1.1 JPY-Only】+【v1.2 API 優化】
# Update: v1.3 - 新增批次寫入機制，降低長程執行時的資料遺失風險。
# Update: v1.2 - 徹底移除所有匯率 (HKD) 相關代碼。
#         此腳本現在只負責抓取 JPY 原始價格並寫入 Sheet (9欄結構)。
#         【核心】: 將 get_all_records() 替換為 col_values(2)，
#                   解決因 Card_Master 過大導致的 APIError: [500] 錯誤。
# =========================================================
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request 
import os.path, time, re, random, sys
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
            else: print("\n❌ 錯誤: 找不到 'credentials.json'。"); sys.exit(1)
    else:
        if not os.path.exists('credentials.json'): print("\n❌ 錯誤: 找不到 'credentials.json'。"); sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES); creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token: token.write(creds.to_json())
gc = gspread.authorize(creds)
print("✅ Google Sheets 授權成功。")

# --- [UA 買取設定區域] --- 
sheet_name = "卡牌價格追蹤系統 - Command Deck"
master_worksheet_name = "Card_Master"
history_worksheet_name = "Price_History"
website_name = "Akiba-Cardshop" 
target_url = "https://akihabara-cardshop.com/uniari-kaitori/"
LOAD_MORE_BUTTON_SELECTOR = "button#loadMoreButton"
FIRST_CARD_SELECTOR = "div.tr"
# base_url_akiba 仍然不需要

# --- [v1.3] 批次寫入設定 ---
MASTER_BATCH_SIZE = 100
HISTORY_BATCH_SIZE = 200

# --- 【v1.2】 匯率換算函數已移除 --- 

# --- [主程式開始] ---
try:
    print(f"\n>> 價格爬蟲 v1.2 ({website_name} UA 買取價 - JPY-Only + API 優化) 已啟動...")
    print(">> 步驟 1/4: 正在讀取 `Card_Master` (優化模式)...") # 步驟重編
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
        print("\n>> 步驟 2/4: 正在啟動 Playwright 瀏覽器並執行「閃電進入 + 超長待機」...") # 步驟重編
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        print(f"     -> 正在訪問: {target_url} (等待 'domcontentloaded' 事件, 最長 120 秒)...")
        page.goto(target_url, wait_until='domcontentloaded', timeout=120000) 
        print("     -> HTML文檔已加載。正在【耐心觀察】第一個卡牌商品出現...")
        page.wait_for_selector(FIRST_CARD_SELECTOR, timeout=45000)
        print("     -> ✅ 偵測到卡牌內容。進入戰術循環。")

        print("     -> 正在執行「循環點擊」以加載所有卡牌...")
        click_count = 0
        while True:
            try:
                button = page.locator(LOAD_MORE_BUTTON_SELECTOR + ":not([style*='display: none'])")
                button.wait_for(state="visible", timeout=10000)
                button.click()
                click_count += 1
                print(f"     -> 點擊「もっと見る」 ({click_count}回目)... 數據待機中...")
                page.wait_for_load_state('networkidle', timeout=15000)
                time.sleep(random.uniform(0.5, 1.5))
            except PlaywrightTimeoutError:
                print("     -> ✅ 按鈕消失或超時。判斷所有卡牌已加載。")
                break
            except Exception as e:
                print(f"     -> 點擊時發生錯誤: {e}, 停止加載。")
                break
                
        print("     -> 正在解析最終頁面...")
        page_html = page.content()
        soup = BeautifulSoup(page_html, 'html.parser')

        print("\n>> 步驟 3/4: 正在提取 UA 買取信息 (JPY) 並構建待寫入列表...") # 步驟重編
        price_history_to_add = []
        new_cards_to_add = [] # 【v1.2】 新增
        total_new_cards = 0
        total_price_records = 0

        def flush_new_cards(force=False):
            if new_cards_to_add and (force or len(new_cards_to_add) >= MASTER_BATCH_SIZE):
                print(f"     -> 正在批次寫入 {len(new_cards_to_add)} 張新 UA 卡牌至 `Card_Master`...")
                master_worksheet.append_rows(new_cards_to_add, value_input_option='USER_ENTERED')
                print("     -> ✅ 新 UA 卡牌批次寫入完成！")
                new_cards_to_add.clear()

        def flush_price_history(force=False):
            if price_history_to_add and (force or len(price_history_to_add) >= HISTORY_BATCH_SIZE):
                print(f"     -> 正在批次寫入 {len(price_history_to_add)} 條 UA 買取價格至 `Price_History`...")
                price_history_to_add.sort(key=lambda record: (record[1], record[5]))
                history_worksheet.append_rows(price_history_to_add, value_input_option='USER_ENTERED')
                print("     -> ✅ UA 買取價格批次寫入完成！")
                price_history_to_add.clear()

        card_units = soup.select("div.tbody > div.tr")
        print(f"     -> 在頁面上偵測到 {len(card_units)} 條買取情報。")

        parsed_count = 0
        for unit in card_units:
            name_div = unit.select_one("div.td.td2")
            model_div = unit.select_one("div.td.td3")
            price_span = unit.select_one("div.td.td5 span.price")
            img_tag = unit.select_one("div.td.td1 img")

            if not name_div or not model_div or not price_span:
                continue

            try:
                price_jpy = int(re.sub(r'[^\d]', '', price_span.text))
                model_text = model_div.text.strip()
                
                match_num = re.search(r'([A-Z]{2,}\d{2,}[A-Z]{0,2}/[A-Z0-9-]+-[A-Z0-9]+)', model_text)
                
                if not match_num: continue
                item_card_number = match_num.group(1).strip()
                akiba_full_name = name_div.text.strip()
                history_unique_id = f"{item_card_number}_{akiba_full_name}"

                image_url = ""
                if img_tag and img_tag.has_attr('src'):
                    image_url = img_tag['src'].strip() 
                    image_url = re.sub(r'/\s+', '/', image_url) # v1.1 URL 清潔
                    
                # --- 【v1.2】 移除 price_hkd 計算 ---
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                history_id = f"{history_unique_id}_{website_name}_{timestamp}"
                set_id_history = item_card_number.split('/')[0] if '/' in item_card_number else "UA_Unknown"
                status = "買取中"
                
                # --- 【v1.2】 新卡檢查 ---
                if item_card_number not in existing_card_numbers:
                    print(f"       -> ✨ 發現新 UA 卡牌！ {item_card_number} {akiba_full_name}")
                    rarity = "Unknown"; card_type = "Unknown"
                    match_rarity = re.search(r'【([A-Z★]+)】', akiba_full_name)
                    if match_rarity: rarity = match_rarity.group(1)
                    
                    unique_id = f"{item_card_number}_{rarity}"
                    
                    new_cards_to_add.append([
                        unique_id, item_card_number, "UnionArena", set_id_history,
                        akiba_full_name, rarity, image_url, card_type
                    ])
                    total_new_cards += 1
                    existing_card_numbers.add(item_card_number)
                    flush_new_cards()

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
                total_price_records += 1
                flush_price_history()
                parsed_count += 1
            except Exception as e:
                print(f"     -> 解析單個 UA 商品時出錯: {e} - {name_div.text if name_div else 'N/A'}")

        print(f"\n✅ 解析完成。準備新增 {total_new_cards} 張新卡牌，記錄 {parsed_count} 條買取價格 (JPY)。")

        # --- 步驟 4/4: 排序和寫入 --- (步驟重編)
        flush_new_cards(force=True)
        if total_new_cards == 0:
            print("     -> 未發現需要添加到 `Card_Master` 的新 UA 卡牌。")
        else:
            print(f"     -> ✅ 累計寫入 `Card_Master` {total_new_cards} 張新 UA 卡牌。")

        flush_price_history(force=True)
        if total_price_records == 0:
             print(">> 步驟 4/4: 未解析到任何需要寫入的 UA 買取價格。")
        else:
             print(f"     -> ✅ 累計寫入 `Price_History` {total_price_records} 條 UA 買取價格紀錄。")
        
        print("\n\n🎉🎉🎉 恭喜！Akihabara UA 買取價 (JPY-Only) 捕獲任務完成！ 🎉🎉🎉")

        browser.close()

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); print(f"錯誤詳情: {e}")
    if 'browser' in locals() and browser.is_connected(): browser.close()