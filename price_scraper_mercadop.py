# =========================================================
# Phase 1, Block 1.2: 價格爬蟲 (Price Scraper) - Mercadop 永久版 v3.4
# Author: 電王
# Update: 【v3.4 JPY-Only + API 優化 + 新動態 URL】
#         1. (來自 v3.3) 修正 Import 錯誤，徹底移除 HKD 相關代碼。
#         2. (來自 v3.3) 使用 col_values(2) 優化 API 讀取，解決 [500] 錯誤。
#         3. 【核心】: 放棄主頁掃描，改為從 /page/5 (パック別)
#            動態抓取所有 Booster 和 Deck 系列連結。
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
# import requests # <-- 【v3.4】 已移除

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
website_name = "MercadoP"
base_url = "https://www.mercardop.jp"
game_title = "One Piece Card Game"
# 【v3.4】 目標改為 Pack/Series 頁面
SERIES_PAGE_URL = "https://www.mercardop.jp/page/5" 

# --- 【v3.4】 匯率換算函數已移除 --- 

# --- 【v3.4】 更新：動態獲取系列 URL 的函數 ---
def get_series_urls(page, series_page_url):
    """
    從 /page/5 (パック別) 抓取所有 Booster 和 Deck 系列的 /product-group/ 連結。
    """
    print(f"  -> 正在掃描系列頁面以獲取連結: {series_page_url}...")
    # 目標選擇器: 選擇 BOOSTER 和 DECKS 下方的所有連結
    selector = "div.cate_navi_wrap ul.cate_navi li.cate_li a.cate_aa" 
    try:
        page.goto(series_page_url, wait_until='networkidle', timeout=60000)
        print(f"  -> 等待選擇器 '{selector}' 出現 (最長 30 秒)...")
        page.wait_for_selector(selector, timeout=30000) 
        print(f"  -> ✅ 選擇器已找到。")
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        links = []
        # 找到所有 cate_navi_wrap
        navi_wraps = soup.select("div.cate_navi_wrap")
        
        for wrap in navi_wraps:
            # 檢查標題是否包含 BOOSTER 或 DECKS
            title_tag = wrap.find('h2', class_='cate_navi_ttl')
            if title_tag and ('BOOSTER' in title_tag.text or 'DECKS' in title_tag.text):
                print(f"  -> 正在處理區塊: {title_tag.text.strip()}")
                series_link_tags = wrap.select("ul.cate_navi li.cate_li a.cate_aa")
                for link_tag in series_link_tags:
                    href = link_tag.get('href')
                    if href and ('/product-group/' in href):
                        if href.startswith(base_url): href = href.replace(base_url, "") 
                        href_without_params = href.split('?')[0]
                        if href_without_params not in links:
                            links.append(href_without_params) 
                            
        print(f"  -> ✅ 在系列頁面發現 {len(links)} 個 Booster/Deck 系列連結。")
        return links
        
    except PlaywrightTimeoutError: 
         print(f"  -> ❌ 在系列頁面等待選擇器 '{selector}' 超時 (30秒)。")
         return []
    except Exception as e:
        print(f"  -> ❌ 掃描系列頁面獲取連結時失敗: {e}")
        return []
# --- 【v3.4 函數結束】 ---

# --- [主程式開始] ---
try:
    print(f"\n>> 價格爬蟲 v3.4 ({website_name} 永久版 - JPY-Only + API 優化 + 新動態 URL) 已啟動...")
    print(">> 步驟 1/5: 正在讀取 `Card_Master` (優化模式)...") 
    master_worksheet = gc.open(sheet_name).worksheet(master_worksheet_name)
    history_worksheet = gc.open(sheet_name).worksheet(history_worksheet_name)
    
    # --- 【v3.4 API 優化】 ---
    print("     -> 正在讀取 Card_Number (B 欄)...")
    all_card_numbers = master_worksheet.col_values(2) 
    existing_card_numbers = set(all_card_numbers[1:]) 
    print(f"✅ 讀取成功，資料庫中現有 {len(existing_card_numbers)} 條卡號紀錄以供參考。")
    # --- 【優化結束】 ---

    # --- 【v3.4】 步驟 2 (獲取匯率) 已移除 ---

    with sync_playwright() as p:
        print("\n>> 步驟 2/5: 正在啟動 Playwright 瀏覽器...") 
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        print("✅ Playwright 瀏覽器準備就緒。")

        # --- 【v3.4】 步驟 3: 動態獲取系列 URL ---
        print(f"\n>> 步驟 3/5: 開始動態掃描 OP 系列專櫃 (從 Pack/Series 頁面)...") 
        DYNAMIC_SERIES_URLS = get_series_urls(page, SERIES_PAGE_URL) # 不再需要 selector 參數
        
        if not DYNAMIC_SERIES_URLS:
            print("❌ 錯誤: 未能從系列頁面獲取任何 OP 系列 URL，任務中止。")
            browser.close(); exit()
        
        print(f"✅ 動態掃描完畢，將掃蕩 {len(DYNAMIC_SERIES_URLS)} 個系列專櫃。")
        all_mercadop_cards = {}
        # --- 【v3.4 步驟 3 結束】 ---

        # --- 【v3.4】 步驟 4: 掃蕩獲取的系列 URL ---
        print(f"\n>> 步驟 4/5: 開始掃蕩 {len(DYNAMIC_SERIES_URLS)} 個核心系列專櫃...") 

        for i, series_url_path in enumerate(DYNAMIC_SERIES_URLS):
            series_url = base_url + series_url_path 
            print(f"  -> 正在掃蕩專櫃 {i+1}/{len(DYNAMIC_SERIES_URLS)}: {series_url}")
            current_page = 1
            consecutive_failures = 0  # 連續失敗計數器
            max_pages = 100  # 最大頁數限制，防止無限循環
            
            while current_page <= max_pages:
                page_url = f"{series_url}?page={current_page}"
                if current_page == 1: page_url = series_url
                print(f"     -> 正在掃蕩頁面 {current_page}...")
                try:
                    page.goto(page_url, wait_until='networkidle', timeout=30000) 
                    page.wait_for_selector("li.list_item_cell", timeout=10000)
                    page_html = page.content()
                    soup = BeautifulSoup(page_html, 'html.parser')
                    card_items = soup.select("li.list_item_cell")
                    if not card_items: 
                        print("     -> 此頁面沒有商品，已到達末頁。")
                        break
                    print(f"     -> 在此頁面發現 {len(card_items)} 個商品。")
                    
                    consecutive_failures = 0  # 成功後重置失敗計數

                    for item in card_items:
                        item_data = item.find('div', class_='item_data')
                        if not item_data: continue
                        name_tag = item_data.find('span', class_='goods_name'); price_tag = item_data.find('span', class_='figure'); stock_tag = item_data.find('p', class_='stock'); model_tag = item_data.find('span', class_='model_number_value')
                        if not name_tag or not price_tag: continue
                        item_name = name_tag.text.strip(); price_text = price_tag.text.strip(); price_jpy = int(re.sub(r'[^\d]', '', price_text))

                        status = "In Stock"
                        if (stock_tag and "soldout_mer" in stock_tag.get('class', [])) or \
                           (stock_tag and "SOLD OUT" in stock_tag.text) or \
                           (stock_tag and "品切れ" in stock_tag.text) or \
                           'soldout' in item.get('class', []): status = "Out of Stock"
                        elif stock_tag and ("残り" in stock_tag.text or "在庫" in stock_tag.text): status = "In Stock"

                        item_card_number = ""
                        if model_tag:
                            match = re.search(r'([A-Z]{2,3}\d{2,3}-?[A-Z]?\d{3})', model_tag.text)
                            if match: item_card_number = match.group(1)
                        if not item_card_number:
                            match_name = re.search(r'([A-Z]{2,3}\d{2,3}-?[A-Z]?\d{3})', item_name)
                            if match_name: item_card_number = match_name.group(1)
                        if not item_card_number: continue

                        image_url = ""
                        image_container = item_data.select_one('div.global_photo')
                        if image_container and image_container.has_attr('data-src'):
                            image_url = image_container['data-src'].strip() 
                            if image_url.startswith('//'): image_url = 'https:' + image_url
                            elif image_url.startswith('/'): image_url = base_url + image_url

                        all_mercadop_cards[(item_card_number, item_name)] = {'price_jpy': price_jpy, 'status': status, 'image_url': image_url}

                    next_page_link = soup.select_one('a.to_next_page')
                    if not next_page_link: print("     -> 此系列已掃蕩完畢（沒有下一頁）。"); break
                    current_page += 1; time.sleep(random.uniform(1, 3))
                    
                except PlaywrightTimeoutError:
                    consecutive_failures += 1
                    if current_page == 1: 
                        print("     -> 警告：第 1 頁等待超時，跳過此專櫃...")
                        break
                    else: 
                        print(f"     -> 在第 {current_page} 頁等待超時...")
                        if consecutive_failures >= 3:
                            print(f"     -> 連續 {consecutive_failures} 次超時，跳過此專櫃...")
                            break
                        current_page += 1  # 嘗試下一頁
                        continue
                        
                except Exception as e: 
                    consecutive_failures += 1
                    print(f"     -> 掃蕩頁面 {current_page} 時失敗。錯誤: {e}")
                    if consecutive_failures >= 3:
                        print(f"     -> 連續 {consecutive_failures} 次失敗，跳過此專櫃...")
                        break
                    current_page += 1  # 嘗試下一頁
                    continue

        print(f"\n✅ 所有動態獲取的專櫃掃蕩完畢，共捕獲 {len(all_mercadop_cards)} 種卡牌的情報。")

        print("\n>> 步驟 4/5: 開始執行情報擴張與價格記錄...") 
        new_cards_to_add = []
        price_history_to_add = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for (item_card_number, item_name), card_info in all_mercadop_cards.items():
            price_jpy = card_info['price_jpy']; status = card_info['status']; image_url = card_info['image_url']
            # --- 【v3.4】 price_hkd 已移除 ---

            # --- 情報擴張 ---
            if item_card_number not in existing_card_numbers:
                print(f"     -> ✨ 發現新卡牌！ {item_card_number} {item_name}")
                rarity = "Unknown"; card_type = "Unknown"
                if "(パラレル)" in item_name or "パラレル" in item_name: rarity = "P"
                elif "SEC" in item_name: rarity = "SEC"
                elif "SR" in item_name: rarity = "SR"
                elif "R" in item_name: rarity = "R"
                elif "UC" in item_name: rarity = "UC"
                elif "C" in item_name: rarity = "C"
                elif "L" in item_name: rarity = "L"
                if "リーダー" in item_name: card_type = "LEADER"
                elif "キャラ" in item_name or "キャラクター" in item_name: card_type = "CHARACTER"
                elif "イベント" in item_name: card_type = "EVENT"
                elif "ステージ" in item_name: card_type = "STAGE"
                unique_id = f"{item_card_number}_{rarity}"; set_id = item_card_number.split('-')[0] if '-' in item_card_number else item_card_number[:4]

                new_cards_to_add.append([
                    unique_id, item_card_number, game_title, set_id,
                    item_name, rarity,
                    image_url, 
                    card_type  
                ])
                # existing_cards_map removed
                existing_card_numbers.add(item_card_number)
                print(f"       -> 已準備將其添加到 `Card_Master`。")

            # --- 價格歷史記錄 ---
            history_unique_id = f"{item_card_number}_{item_name}"
            history_id = f"{history_unique_id}_{website_name}_{timestamp}"
            set_id_history = item_card_number.split('-')[0] if '-' in item_card_number else item_card_number[:4]

            # --- 【v3.4 JPY-Only 結構 (9 欄)】 ---
            price_history_to_add.append([
                history_id, history_unique_id, website_name,
                price_jpy,  # D: Sell_Price_JPY
                "N/A",      # E: Buy_Price_JPY
                timestamp,  # F: Timestamp
                status,     # G: Status
                set_id_history, # H: Set_ID
                image_url   # I: Image_URL
            ])

        print(f"\n✅ 情報處理完畢。準備新增 {len(new_cards_to_add)} 張新卡牌，記錄 {len(price_history_to_add)} 條價格情報 (JPY)。")

        if price_history_to_add:
             print(">> 正在對捕獲的情報進行後端排序..."); price_history_to_add.sort(key=lambda record: (record[1], record[5])); print("✅ 情報排序完畢。")

        print("\n>> 步驟 5/5: 正在將數據寫入 Google Sheet...") 
        if new_cards_to_add:
            print(f"     -> 正在將 {len(new_cards_to_add)} 張新卡牌寫入 `Card_Master`...")
            master_worksheet.append_rows(new_cards_to_add, value_input_option='USER_ENTERED')
            print("     -> ✅ 新卡牌寫入成功！")
        else: print("     -> 未發現需要添加到 `Card_Master` 的新卡牌。")

        if price_history_to_add:
            print(f"     -> 正在將 {len(price_history_to_add)} 條價格情報 (JPY-Only) **追加**到 `Price_History`...")
            history_worksheet.append_rows(price_history_to_add, value_input_option='USER_ENTERED')
            print("     -> ✅ 價格情報追加成功！")
        else: print("     -> 未捕獲到需要添加到 `Price_History` 的價格情報。")

        print("\n\n🎉🎉🎉 恭喜！Mercadop (JPY-Only + 動態 URL) 征服任務完成！ 🎉🎉🎉")

        browser.close()

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); print(f"錯誤詳情: {e}")
    if 'browser' in locals() and browser.is_connected(): browser.close()