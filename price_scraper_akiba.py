# =========================================================
# Phase 1, Block 1.3: 價格爬蟲 (Price Scraper) - Akiba OP 買取價 v1.5.1
# Author: 電王
# 戰術: 【v1.5 JPY-Only + API 優化】+【v1.5.1 URL 空格終極修正】
# Update: v1.5.1 - 徹底移除所有匯率 (HKD) 相關代碼。
#         解決 [500] API 錯誤。
#         【核心】: 使用 re.sub(r'\s+', '', ...) 清潔 image_url 中的所有空格。
# =========================================================
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request 
import os.path, time, re, random
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# import requests # <-- 【v1.5】 已移除

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

# --- [設定區域] ---
sheet_name = "卡牌價格追蹤系統 - Command Deck"
master_worksheet_name = "Card_Master"
history_worksheet_name = "Price_History"
website_name = "Akiba-Cardshop"
target_url = "https://akihabara-cardshop.com/onepice-kaitori/"
LOAD_MORE_BUTTON_SELECTOR = "button#loadMoreButton"
FIRST_CARD_SELECTOR = "div.tr"
base_url_akiba = "https://akihabara-cardshop.com"

# --- 【v1.5】 匯率換算函數已移除 ---

# --- [主程式開始] ---
try:
    print(f"\n>> 價格爬蟲 v1.5.1 ({website_name} 買取價 - JPY-Only + API 優化 + URL 空格修正) 已啟動...")
    print(">> 步驟 1/4: 正在讀取 `Card_Master` (優化模式)...") # 步驟重編
    master_worksheet = gc.open(sheet_name).worksheet(master_worksheet_name)
    history_worksheet = gc.open(sheet_name).worksheet(history_worksheet_name)
    
    # --- 【v1.5 API 優化】 ---
    print("     -> 正在讀取 Card_Number (B 欄)...")
    all_card_numbers = master_worksheet.col_values(2) 
    existing_card_numbers = set(all_card_numbers[1:]) 
    print(f"✅ 讀取成功，資料庫中現有 {len(existing_card_numbers)} 條卡號紀錄以供參考。")
    # --- 【優化結束】 ---

    # --- 【v1.5】 步驟 2 (獲取匯率) 已移除 ---

    with sync_playwright() as p:
        print("\n>> 步驟 2/4: 正在啟動 Playwright 瀏覽器並執行「閃電進入」...") # 步驟重編
        browser = p.firefox.launch(headless=False)
        page = browser.new_page()

        print(f"     -> 正在訪問: {target_url} (等待 'domcontentloaded' 事件)...")
        page.goto(target_url, wait_until='domcontentloaded', timeout=60000)
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

        print("\n>> 步驟 3/4: 正在提取買取信息 (JPY) 並構建待寫入列表...") # 步驟重編
        price_history_to_add = []
        new_cards_to_add = [] # 【v1.5】 新增

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
                match_num = re.search(r'([A-Z]{1,3}\d{2,3}-?[A-Z]?\d{1,3})', model_text)
                if not match_num: continue
                item_card_number = match_num.group(1).strip()
                akiba_full_name = name_div.text.strip()
                history_unique_id = f"{item_card_number}_{akiba_full_name}"

                # --- 【v1.5.1 URL 空格終極修正】 ---
                image_url = ""
                if img_tag and img_tag.has_attr('src'):
                    image_url = img_tag['src'].strip() 
                    image_url = re.sub(r'\s+', '', image_url) # 移除所有空格
                    if image_url.startswith('/'): image_url = base_url_akiba + image_url
                # --- 【修正結束】 ---

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                history_id = f"{history_unique_id}_{website_name}_{timestamp}"
                set_id_history = item_card_number.split('-')[0] if '-' in item_card_number else item_card_number[:4]
                status = "買取中"
                
                # --- 【v1.5】 新卡檢查 ---
                if item_card_number not in existing_card_numbers:
                    print(f"       -> ✨ 發現新 OP 卡牌！ {item_card_number} {akiba_full_name}")
                    rarity = "Unknown"; card_type = "Unknown"
                    match_rarity = re.search(r'【([A-Z★]+)】', akiba_full_name)
                    if match_rarity: rarity = match_rarity.group(1)
                    
                    unique_id = f"{item_card_number}_{rarity}"
                    
                    new_cards_to_add.append([
                        unique_id, item_card_number, "One Piece Card Game", set_id_history,
                        akiba_full_name, rarity, image_url, card_type
                    ])
                    existing_card_numbers.add(item_card_number) 

                # --- 【v1.5 JPY-Only 結構 (9 欄)】 ---
                price_history_to_add.append([
                    history_id, history_unique_id, website_name,
                    "N/A",      # D: Sell_Price_JPY
                    price_jpy,  # E: Buy_Price_JPY
                    timestamp,  # F: Timestamp
                    status,     # G: Status
                    set_id_history, # H: Set_ID
                    image_url   # I: Image_URL
                ])
                parsed_count += 1
            except Exception as e:
                print(f"     -> 解析單個商品時出錯: {e} - {name_div.text if name_div else 'N/A'}")

        print(f"\n✅ 解析完成。準備新增 {len(new_cards_to_add)} 張新卡牌，記錄 {parsed_count} 條買取價格 (JPY)。")

        # --- 步驟 4/4: 排序和寫入 --- (步驟重編)
        if new_cards_to_add:
            print(f"     -> 正在將 {len(new_cards_to_add)} 張新 OP 卡牌寫入 `Card_Master`...")
            master_worksheet.append_rows(new_cards_to_add, value_input_option='USER_ENTERED')
            print("     -> ✅ 新 OP 卡牌寫入成功！")
        else:
            print("     -> 未發現需要添加到 `Card_Master` 的新 OP 卡牌。")

        if price_history_to_add:
             print(">> 步驟 4/4: 正在對捕獲的情報進行後端排序...")
             price_history_to_add.sort(key=lambda record: (record[1], record[5])) 
             print("✅ 情報排序完畢。")

             print(f"     -> 正在將 {len(price_history_to_add)} 條買取價格 (JPY-Only) **追加**到 `Price_History`...")
             history_worksheet.append_rows(price_history_to_add, value_input_option='USER_ENTERED')
             print("     -> ✅ 買取價格情報追加成功！")
        else:
             print(">> 步驟 4/4: 未解析到任何需要寫入的買取價格。")
        
        print("\n\n🎉🎉🎉 恭喜！Akihabara OP 買取價 (JPY-Only) 捕獲任務完成！ 🎉🎉🎉")

        browser.close()

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); print(f"錯誤詳情: {e}")
    if 'browser' in locals() and browser.is_connected(): browser.close()