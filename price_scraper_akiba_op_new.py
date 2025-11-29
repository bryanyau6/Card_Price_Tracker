# =========================================================
# Phase 1, Block 1.4: 價格爬蟲 (Price Scraper) - Akiba OP 新彈買取價 v1.4
# Author: 電王
# 戰術: 【v1.3 JPY-Only 架構】
# Update: v1.4   - 新增批次寫入 Price_History，降低長程執行時的資料遺失風險。
#         v1.3.1 - 這是 v1.3 的最終確認版。
#         徹底移除所有匯率 (HKD) 相關代碼。
#         此腳本現在只負責抓取 JPY 原始價格並寫入 Sheet (9欄結構)。
# =========================================================
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request 
import os.path
import sys
import time
import re
import random
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# import requests # <-- 【v1.3】 已移除


def log(message: str) -> None:
    print(message, flush=True)

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

# --- [設定區域] --- 
sheet_name = "卡牌價格追蹤系統 - Command Deck"
master_worksheet_name = "Card_Master"
history_worksheet_name = "Price_History"
website_name = "Akiba-Cardshop" 
target_url = "https://akihabara-cardshop.com/op-kaitori-shindan/" 
LOAD_MORE_BUTTON_SELECTOR = "button#loadMoreButton"
FIRST_CARD_SELECTOR = "div.tr"
base_url_akiba = "https://akihabara-cardshop.com"

# --- [v1.4] 批次寫入設定 ---
HISTORY_BATCH_SIZE = 200

# --- 【v1.3】 匯率換算函數已移除 --- 

# --- [主程式開始] ---
try:
    # 【v1.3.1 視覺確認點】
    print(f"\n>> 價格爬蟲 v1.3.1 ({website_name} OP 新彈買取價 - JPY-Only 最終確認版) 已啟動...")
    print(">> 步驟 1/4: 正在讀取 `Card_Master` (用於內部參考)...")
    master_worksheet = gc.open(sheet_name).worksheet(master_worksheet_name)
    history_worksheet = gc.open(sheet_name).worksheet(history_worksheet_name)
    existing_cards_data = master_worksheet.get_all_records()
    print(f"✅ 讀取成功，資料庫中現有 {len(existing_cards_data)} 條卡牌紀錄以供參考。")

    # --- 【v1.3】 步驟 2 (獲取匯率) 已移除 ---

    with sync_playwright() as p:
        print("\n>> 步驟 2/4: 正在啟動 Playwright 瀏覽器並執行「閃電進入」...")
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        print(f"     -> 正在訪問 (新彈頁面): {target_url} (等待 'domcontentloaded', 最長 120 秒)...")
        page.goto(target_url, wait_until='domcontentloaded', timeout=120000)
        print("     -> HTML文檔已加載。正在【嘗試偵測】第一個卡牌商品 (短時等待)...")

        page_is_empty = False
        try:
            page.wait_for_selector(FIRST_CARD_SELECTOR, timeout=15000) 
            print("     -> ✅ 偵測到卡牌內容。進入戰術循環。")
        except PlaywrightTimeoutError:
            print("     -> ⚠️ 警告: 未能在 15 秒內偵測到卡牌內容。頁面可能為空或未加載。")
            page_is_empty = True 

        price_history_to_add = []
        total_price_records = 0

        def flush_price_history(force=False):
            if price_history_to_add and (force or len(price_history_to_add) >= HISTORY_BATCH_SIZE):
                print(f"     -> 正在批次寫入 {len(price_history_to_add)} 條 OP 新彈買取價格至 `Price_History`...")
                price_history_to_add.sort(key=lambda record: (record[1], record[5]))
                history_worksheet.append_rows(price_history_to_add, value_input_option='USER_ENTERED')
                print("     -> ✅ OP 新彈買取價格批次寫入完成！")
                price_history_to_add.clear()

        parsed_count = 0

        if not page_is_empty:
            print("     -> 正在執行「循環點擊」以加載所有卡牌 (如果存在)...")
            click_count = 0
            while True: 
                try:
                    button = page.locator(LOAD_MORE_BUTTON_SELECTOR + ":not([style*='display: none'])")
                    button.wait_for(state="visible", timeout=5000) 
                    button.click()
                    click_count += 1
                    print(f"     -> 點擊「もっと見る」 ({click_count}回目)... 數據待機中...")
                    page.wait_for_load_state('networkidle', timeout=15000)
                    time.sleep(random.uniform(0.5, 1.5))
                except PlaywrightTimeoutError:
                    if click_count == 0:
                        print("     -> 未找到或無需點擊「もっと見る」按鈕。")
                    else:
                        print("     -> ✅ 按鈕消失或超時。判斷所有卡牌已加載。")
                    break
                except Exception as e:
                    print(f"     -> 點擊時發生錯誤: {e}, 停止加載。")
                    break

            print("     -> 正在解析最終頁面...")
            page_html = page.content()
            soup = BeautifulSoup(page_html, 'html.parser')

            print("\n>> 步驟 3/4: 正在提取 OP 新彈買取信息 (JPY) 並構建待寫入列表...")
            card_units = soup.select("div.tbody > div.tr")
            print(f"     -> 在頁面上偵測到 {len(card_units)} 條買取情報。")

            for unit in card_units:
                name_div = unit.select_one("div.td.td2")
                model_div = unit.select_one("div.td.td3")
                price_span = unit.select_one("div.td.td5 span.price")
                img_tag = unit.select_one("div.td.td1 img")
                if not name_div or not model_div or not price_span: continue
                try:
                    price_jpy = int(re.sub(r'[^\d]', '', price_span.text))
                    model_text = model_div.text.strip()
                    match_num = re.search(r'([A-Z]{1,3}\d{2,3}-?[A-Z]?\d{1,3})', model_text) 
                    if not match_num: continue
                    item_card_number = match_num.group(1).strip()
                    akiba_full_name = name_div.text.strip()
                    history_unique_id = f"{item_card_number}_{akiba_full_name}"
                    image_url = ""
                    if img_tag and img_tag.has_attr('src'):
                        image_url = img_tag['src'].strip() 
                        image_url = re.sub(r'\s+', '', image_url) # v1.2 URL 空格修正
                        if image_url.startswith('/'): image_url = base_url_akiba + image_url
                            
                    # --- 【v1.3】 移除 price_hkd 計算 ---
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    history_id = f"{history_unique_id}_{website_name}_{timestamp}"
                    set_id_history = item_card_number.split('-')[0] if '-' in item_card_number else item_card_number[:4]
                    
                    # --- 【v1.3 錯誤修正】 ---
                    status = "買取中"
                    # --- 【修正結束】 ---
                    
                    # --- 【v1.3 JPY-Only 結構 (9 欄)】 ---
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
                    print(f"     -> 解析單個 OP 新彈商品時出錯: {e} - {name_div.text if name_div else 'N/A'}")

            print(f"\n✅ 解析完成。成功解析 {parsed_count} 條 OP 新彈買取價格 (JPY)。")

        else: 
            print("\n>> 步驟 3/4: 因頁面為空或未加載，跳過解析。")


        # --- 步驟 4/4: 排序和寫入 ---
        flush_price_history(force=True)
        if total_price_records == 0:
             print(">> 步驟 4/4: 未解析到任何需要寫入的 OP 新彈買取價格。")
        else:
             print(f"     -> ✅ 累計寫入 `Price_History` {total_price_records} 條 OP 新彈買取價格。")
        
        print("\n\n🎉🎉🎉 恭喜！Akiba OP 新彈買取價 (JPY-Only) 捕獲任務完成！ 🎉🎉🎉")

        try:
            browser.close()
        except Exception:
            pass

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); print(f"錯誤詳情: {e}")
    try:
        if 'browser' in locals() and browser.is_connected(): browser.close()
    except Exception:
        pass