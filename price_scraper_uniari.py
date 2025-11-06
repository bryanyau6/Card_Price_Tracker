# =========================================================
# Phase 1, Block 2.1: 價格爬蟲 (Price Scraper) - Union Arena 售價 v1.2 (JPY-Only + API 優化 + 分批寫入)
# Author: 電王
# 戰術: 【v1.0 URL 清潔】+【v1.1 JPY-Only + API 優化】+【v1.2 分批寫入】
# Update: v1.1 - 徹底移除所有匯率 (HKD) 相關代碼。
#              【核心】: 將 get_all_records() 替換為 col_values(2)，
#               解決 Card_Master 過大導致的 APIError: [500] 錯誤。
# Update: v1.2 - 導入 `batch_update_sheet` 函數，解決大量數據 (數萬行)
#               一次性 `append_rows` 導致的 API 超時或 429 速率限制錯誤。
#               修正 Playwright `browser.close()` 的呼叫邏輯。
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

# --- [步驟 A: 本地端 Google Sheets 授權] --- 
print(">> 步驟 A: 正在進行本地端 Google Sheets 授權...")
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = None

if os.path.exists('token.json'): 
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        try: 
            creds.refresh(Request())
        except Exception as e:
            print(f"❌ 刷新 Token 失敗: {e}");
            if os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            else: 
                print("\n❌ 錯誤: 找不到 'credentials.json'。"); 
                exit()
    else:
        if not os.path.exists('credentials.json'): 
            print("\n❌ 錯誤: 找不到 'credentials.json'。"); 
            exit()
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    
    with open('token.json', 'w') as token: 
        token.write(creds.to_json())

gc = gspread.authorize(creds)
print("✅ Google Sheets 授權成功。")

# --- [UA 設定區域] --- 
sheet_name = "卡牌價格追蹤系統 - Command Deck"
master_worksheet_name = "Card_Master"
history_worksheet_name = "Price_History"
website_name = "Merucard-Uniari"
base_url = "https://www.merucarduniari.jp"
game_title = "UnionArena" # 修正為 UnionArena
SERIES_INDEX_URL = "https://www.merucarduniari.jp/page/pack"

# --- [v1.0.3 函數] --- 
def get_all_series_links(page):
    print(f"    -> 正在訪問系列總覽: {SERIES_INDEX_URL}...")
    try:
        page.goto(SERIES_INDEX_URL, wait_until='domcontentloaded', timeout=60000)
        print("    -> HTML文檔已加載。正在【耐心觀察】系列選單出現...")
        page.wait_for_selector("aside#left_side_col section.pickupcategory_nav_box", timeout=45000) 
        print("    -> ✅ 偵測到系列選單。")
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        series_links = soup.select("aside#left_side_col section.pickupcategory_nav_box li.itemlist_nav_item a")
        for link in series_links:
            href = link.get('href')
            name = link.select_one("span.nav_label").get_text(strip=True) if link.select_one("span.nav_label") else ""
            if href and ('/product-group/' in href) and ('BT】' in name or 'ST】' in name):
                if href.startswith(base_url): 
                    href = href.replace(base_url, "") 
                href_without_params = href.split('?')[0] # 移除參數
                if href_without_params not in links:
                    links.append(href_without_params)
        print(f"    -> ✅ 動態掃描完畢，發現 {len(links)} 個 UA 系列專櫃。")
        return links
    except Exception as e:
        print(f"    -> ❌ 動態掃描系列頁面失敗: {e}")
        return []

# --- 【v1.2 修正】: 新增分批寫入函數 (這是正確的位置) ---
def batch_update_sheet(worksheet, data, batch_size=5000):
    """
    將數據分批寫入 Google Sheet，並包含重試機制以應對 API 速率限制 (429)。
    """
    if not data:
        return 0 # 沒有數據需要寫入
    
    total_rows = len(data)
    print(f"    -> 準備將 {total_rows} 條記錄分批 (每批 {batch_size} 條) 寫入工作表 '{worksheet.title}'...")
    
    for i in range(0, total_rows, batch_size):
        batch = data[i:i + batch_size]
        current_batch_num = (i // batch_size) + 1
        total_batches = -(-total_rows // batch_size) # 向上取整
        
        print(f"    -> 正在寫入批次 {current_batch_num}/{total_batches} ({len(batch)} 條記錄)...")
        
        # --- [健壯性] 加入重試機制 ---
        retries = 3
        for attempt in range(retries):
            try:
                worksheet.append_rows(batch, value_input_option='USER_ENTERED')
                print(f"      -> ✅ 批次 {current_batch_num}/{total_batches} 寫入成功。")
                time.sleep(1.5) # [重要] 每次成功寫入後，"禮貌性"地暫停1.5秒，避免觸發 429 錯誤
                break # 成功，跳出重試循環
            
            except gspread.exceptions.APIError as e:
                wait_time = (attempt + 1) * 10 # 逐漸增加等待時間
                if e.response.status_code == 429: # 錯誤 429: Rate limit exceeded
                    print(f"      -> ❌ 觸發 API 速率限制 (429)。正在等待 {wait_time} 秒後重試 (第 {attempt + 1}/{retries} 次)...")
                    time.sleep(wait_time)
                else: # 其他 API 錯誤 (如 500, 503)
                    print(f"      -> ❌ 寫入批次時發生 API 錯誤 (代碼: {e.response.status_code})。{e}。正在等待 {wait_time} 秒後重試 (第 {attempt + 1}/{retries} 次)...")
                    time.sleep(wait_time)
            except Exception as e:
                # 其他非 gspread 的錯誤 (例如連接中斷)
                print(f"      -> ❌ 發生未知的寫入錯誤: {e}。正在等待 10 秒後重試 (第 {attempt + 1}/{retries} 次)...")
                time.sleep(10)
        else:
            # 如果重試 3 次都失敗，則拋出異常並中止腳本
            print(f"    -> ❌❌❌ 批次 {current_batch_num} 寫入失敗 (重試 {retries} 次後放棄)。")
            raise Exception(f"Batch write failed for worksheet '{worksheet.title}' after {retries} retries.")

    return total_rows

# --- [主程式開始] ---
try:
    print(f"\n>> 價格爬蟲 v1.2 ({website_name} 售價 - JPY-Only + API 優化 + 分批) 已啟動...")
    print(">> 步驟 1/5: 正在讀取 `Card_Master` (優化模式)...") # 步驟重編
    master_worksheet = gc.open(sheet_name).worksheet(master_worksheet_name)
    history_worksheet = gc.open(sheet_name).worksheet(history_worksheet_name)
    
    # --- 【v1.1 API 優化】 ---
    print("    -> 正在讀取 Card_Number (B 欄)...")
    all_card_numbers = master_worksheet.col_values(2) 
    existing_card_numbers = set(all_card_numbers[1:]) 
    print(f"✅ 讀取成功，資料庫中現有 {len(existing_card_numbers)} 條卡號紀錄以供參考。")

    with sync_playwright() as p:
        print("\n>> 步驟 2/5: 正在啟動 Playwright 瀏覽器...") # 步驟重編
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        print("✅ Playwright 瀏覽器準備就緒。")

        print("\n>> 步驟 3/5: 開始動態掃描 UA 系列專櫃...") # 步驟重編
        UA_SERIES_URLS = get_all_series_links(page) 
        
        if not UA_SERIES_URLS:
            print("❌ 錯誤: 未能獲取任何 UA 系列 URL，任務中止。")
            browser.close(); 
            exit()
            
        all_uniari_cards = {}

        for i, series_url_path in enumerate(UA_SERIES_URLS):
            series_url = base_url + series_url_path
            print(f"  -> 正在掃蕩專櫃 {i+1}/{len(UA_SERIES_URLS)}: {series_url}")
            current_page = 1
            while True:
                page_url = f"{series_url}?page={current_page}"
                if current_page == 1: 
                    page_url = series_url
                print(f"    -> 正在掃蕩頁面 {current_page}...")
                try:
                    page.goto(page_url, wait_until='networkidle', timeout=30000) 
                    page.wait_for_selector("li.list_item_cell", timeout=10000)
                    page_html = page.content()
                    soup = BeautifulSoup(page_html, 'html.parser')
                    card_items = soup.select("li.list_item_cell")
                    
                    if not card_items: 
                        break # 沒有商品，跳出 while True
                    
                    print(f"    -> 在此頁面發現 {len(card_items)} 個商品。")

                    for item in card_items:
                        item_data = item.find('div', class_='item_data');
                        if not item_data: 
                            continue
                        
                        name_tag = item_data.find('span', class_='goods_name')
                        price_tag = item_data.find('span', class_='figure')
                        stock_tag = item_data.find('p', class_='stock')
                        model_tag = item_data.find('span', class_='model_number_value')
                        
                        if not name_tag or not price_tag: 
                            continue
                        
                        item_name = name_tag.text.strip()
                        price_text = price_tag.text.strip()
                        price_jpy = int(re.sub(r'[^\d]', '', price_text))

                        status = "In Stock"
                        if (stock_tag and "soldout_mer" in stock_tag.get('class', [])) or \
                           (stock_tag and "SOLD OUT" in stock_tag.text) or (stock_tag and "品切れ" in stock_tag.text) or \
                           'soldout' in item.get('class', []): 
                            status = "Out of Stock"
                        elif stock_tag and ("残り" in stock_tag.text or "在庫" in stock_tag.text): 
                            status = "In Stock"

                        item_card_number = ""
                        ua_regex = r'([A-Z]{2,}\d{2,}[A-Z]{0,2}/[A-Z0-9-]+-[A-Z0-9]+)'
                        if model_tag:
                            match = re.search(ua_regex, model_tag.text)
                            if match: 
                                item_card_number = match.group(1).strip()
                        
                        if not item_card_number:
                            match_name = re.search(ua_regex, item_name)
                            if match_name: 
                                item_card_number = match_name.group(1).strip()
                        
                        if not item_card_number:
                            ua_regex_alt = r'([A-Z]{0,}[A-Z]{2,}\d{2,}[A-Z]{0,2}/[A-Z0-9-]+-[A-Z0-9]+)'
                            match_alt = re.search(ua_regex_alt, item_name)
                            if match_alt: 
                                item_card_number = match_alt.group(1).strip()
                        
                        if not item_card_number: 
                            continue

                        image_url = ""
                        image_container = item_data.select_one('div.global_photo')
                        if image_container and image_container.has_attr('data-src'):
                            image_url = image_container['data-src'].strip() 
                            image_url = image_url.replace(" ", "%20")  
                            if image_url.startswith('//'): 
                                image_url = 'https:' + image_url
                            elif image_url.startswith('/'): 
                                image_url = base_url + image_url

                        all_uniari_cards[(item_card_number, item_name)] = {'price_jpy': price_jpy, 'status': status, 'image_url': image_url}

                    next_page_link = soup.select_one('a.to_next_page')
                    if not next_page_link: 
                        print("    -> 此系列已掃蕩完畢（沒有下一頁）。"); 
                        break # 跳出 while True
                    
                    current_page += 1
                    time.sleep(random.uniform(1, 3))
                
                except PlaywrightTimeoutError:
                    if current_page == 1: 
                        print("    -> 警告：此系列可能為空或加載超時...")
                    else: 
                        print(f"    -> 在第 {current_page} 頁等待超時，跳轉到下個系列。")
                    break # 跳出 while True
                except Exception as e: 
                    print(f"    -> 掃蕩頁面 {current_page} 時失敗。錯誤: {e}"); 
                    break # 跳出 while True
        
        # --- 【v1.2 修正】: 將 browser.close() 移至 "with" 區塊內部 ---
        print("    -> ✅ 瀏覽器爬蟲任務完成，正在關閉瀏覽器...")
        browser.close() 
    
    # --- "with sync_playwright() as p:" 區塊在此結束 ---

    print(f"\n✅ 所有 UA 專櫃掃蕩完畢，共捕獲 {len(all_uniari_cards)} 種卡牌的情報。")

    print("\n>> 步驟 4/5: 開始執行情報擴張 (UA) 與價格記錄...") # 步驟重編
    new_cards_to_add = []
    price_history_to_add = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for (item_card_number, item_name), card_info in all_uniari_cards.items():
        price_jpy = card_info['price_jpy']; status = card_info['status']; image_url = card_info['image_url']

        # --- [情報擴張: Card_Master] ---
        if item_card_number not in existing_card_numbers:
            print(f"    -> ✨ 發現新 UA 卡牌！ {item_card_number} {item_name}")
            rarity = "Unknown"; card_type = "Unknown"
            if "SR★★" in item_name or "★★" in item_name: rarity = "SR★★"
            elif "SR★" in item_name or "★" in item_name: rarity = "SR★" 
            elif "R★" in item_name: rarity = "R★"
            elif "U★" in item_name: rarity = "U★"
            elif "C★" in item_name: rarity = "C★"
            elif "AP" in item_name: rarity = "AP"
            elif "SR" in item_name: rarity = "SR"
            elif "R" in item_name: rarity = "R"
            elif "U" in item_name: rarity = "U"
            elif "C" in item_name: rarity = "C"
            elif "L" in item_name: rarity = "L" 
            if "【キャラクター】" in item_name: card_type = "CHARACTER"
            elif "【イベント】" in item_name: card_type = "EVENT"
            elif "【フィールド】" in item_name: card_type = "FIELD"
            elif "【アクションポイント】" in item_name: card_type = "ACTION POINT"
            
            set_id = item_card_number.split('/')[0] if '/' in item_card_number else "UA_Unknown"
            unique_id = f"{item_card_number}_{rarity}"
            
            new_cards_to_add.append([
                unique_id, item_card_number, game_title, set_id,
                item_name, rarity, image_url, card_type
            ])
            existing_card_numbers.add(item_card_number)
            print(f"      -> 已準備將其添加到 `Card_Master`。")

        # --- [價格記錄: Price_History] ---
        history_unique_id = f"{item_card_number}_{item_name}"
        history_id = f"{history_unique_id}_{website_name}_{timestamp}"
        set_id_history = item_card_number.split('/')[0] if '/' in item_card_number else "UA_Unknown"

        # --- 【v1.1 JPY-Only 結構 (9 欄)】 ---
        price_history_to_add.append([
            history_id, history_unique_id, website_name,
            price_jpy,  # D: Sell_Price_JPY
            "N/A",      # E: Buy_Price_JPY
            timestamp,  # F: Timestamp
            status,     # G: Status
            set_id_history, # H: Set_ID
            image_url   # I: Image_URL
        ])

    print(f"\n✅ 情報處理完畢。準備新增 {len(new_cards_to_add)} 張新 UA 卡牌，記錄 {len(price_history_to_add)} 條 UA 價格情報 (JPY)。")

    if price_history_to_add:
        print(">> 正在對捕獲的情報進行後端排序..."); 
        price_history_to_add.sort(key=lambda record: (record[1], record[5])); 
        print("✅ 情報排序完畢。")

    # --- 【v1.2 修正】: 使用 `batch_update_sheet` 函數替換 步驟 5/5 ---
    print("\n>> 步驟 5/5: 正在將數據【分批】寫入 Google Sheet...")

    # 1. 寫入 Card_Master (批次較小)
    master_rows_added = batch_update_sheet(master_worksheet, new_cards_to_add, batch_size=1000)
    if master_rows_added > 0:
        print(f"    -> ✅ 成功將 {master_rows_added} 張新 UA 卡牌寫入 `Card_Master`！")
    else:
        print("    -> 未發現需要添加到 `Card_Master` 的新 UA 卡牌。")

    # 2. 寫入 Price_History (批次較大)
    history_rows_added = batch_update_sheet(history_worksheet, price_history_to_add, batch_size=5000)
    if history_rows_added > 0:
        print(f"    -> ✅ 成功將 {history_rows_added} 條 UA 價格情報追加到 `Price_History`！")
    else:
        print("    -> 未捕獲到需要添加到 `Price_History` 的 UA 價格情報。")
    
    print("\n\n🎉🎉🎉 恭喜！Union Arena 售價 (JPY-Only) 征服任務完成！ 🎉🎉🎉")

except Exception as e:
    print(f"\n❌❌❌ 發生嚴重錯誤 ❌❌❌"); 
    print(f"錯誤詳情: {e}")
    # 【v1.2 修正】: 移除此處的 browser.close()，因為它已在 "with" 區塊內關閉