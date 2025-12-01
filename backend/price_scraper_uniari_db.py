# =========================================================
# TCGE-CIS 2.0: Uniari 爬蟲 (資料庫版)
# Author: 電王 & Copilot
# 
# 職責: 抓取 Union Arena 售價
# 升級重點:
# 1. 寫入 PostgreSQL 資料庫。
# 2. price_type = 'sell' (售價)。
# 3. 增量更新。
# =========================================================

import sys
import os
import time
import re
import random
import hashlib
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Game, CardSet, Card, MarketPrice

# --- [設定區域] ---
WEBSITE_NAME = "Merucard-Uniari"
BASE_URL = "https://www.merucarduniari.jp"
GAME_CODE = "UA"
GAME_NAME = "Union Arena"
SERIES_INDEX_URL = "https://www.merucarduniari.jp/page/pack"

# --- [資料庫工具函數] ---

def get_or_create_game(db: Session, code: str, name: str):
    game = db.query(Game).filter(Game.code == code).first()
    if not game:
        game = Game(code=code, name=name)
        db.add(game)
        db.commit()
        db.refresh(game)
    return game

def get_or_create_set(db: Session, game_id: int, set_code: str):
    card_set = db.query(CardSet).filter(CardSet.code == set_code, CardSet.game_id == game_id).first()
    if not card_set:
        card_set = CardSet(game_id=game_id, code=set_code, name=f"Series {set_code}")
        db.add(card_set)
        db.commit()
        db.refresh(card_set)
    return card_set

def get_or_create_card(db: Session, set_id: int, card_number: str, name: str, image_url: str, version: str = "Normal"):
    card = db.query(Card).filter(Card.card_number == card_number, Card.version == version).first()
    if not card:
        rarity = "Unknown"
        if "SR★★" in name or "★★" in name: rarity = "SR★★"
        elif "SR★" in name or "★" in name: rarity = "SR★"
        elif "SR" in name: rarity = "SR"
        elif "R" in name: rarity = "R"
        elif "U" in name: rarity = "U"
        elif "C" in name: rarity = "C"
        
        card = Card(
            card_set_id=set_id,
            card_number=card_number,
            name=name,
            version=version,
            rarity=rarity,
            image_url=image_url
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        print(f"      [DB] ✨ 新增卡片資料: {card_number} ({version})")
    return card

def generate_price_hash(source, price_type, price, status):
    data_string = f"{source}|{price_type}|{price}|{status}"
    return hashlib.md5(data_string.encode()).hexdigest()

def save_price(db: Session, card_id: int, price_jpy: int, status: str, price_type: str = "sell"):
    current_hash = generate_price_hash(WEBSITE_NAME, price_type, price_jpy, status)
    
    last_price = db.query(MarketPrice).filter(
        MarketPrice.card_id == card_id,
        MarketPrice.source == WEBSITE_NAME,
        MarketPrice.price_type == price_type
    ).order_by(MarketPrice.timestamp.desc()).first()
    
    if last_price and last_price.data_hash == current_hash:
        return False
    
    new_price = MarketPrice(
        card_id=card_id,
        source=WEBSITE_NAME,
        price_type=price_type,
        price_jpy=price_jpy,
        stock_status=status,
        data_hash=current_hash
    )
    db.add(new_price)
    db.commit()
    return True

# --- [爬蟲邏輯] ---

def get_all_series_links(page):
    print(f" -> 正在掃描系列頁面: {SERIES_INDEX_URL}...")
    try:
        page.goto(SERIES_INDEX_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_selector("aside#left_side_col section.pickupcategory_nav_box", timeout=45000)
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        series_links = soup.select("aside#left_side_col section.pickupcategory_nav_box li.itemlist_nav_item a")
        for link in series_links:
            href = link.get('href')
            name = link.select_one("span.nav_label").get_text(strip=True) if link.select_one("span.nav_label") else ""
            if href and ('/product-group/' in href) and ('BT】' in name or 'ST】' in name):
                if href.startswith(BASE_URL): href = href.replace(BASE_URL, "")
                href_without_params = href.split('?')[0]
                if href_without_params not in links:
                    links.append(href_without_params)
        return links
    except Exception as e:
        print(f" -> ❌ 掃描失敗: {e}")
        return []

def main():
    print(f"\n>> TCGE-CIS 2.0: Uniari 爬蟲 (資料庫版) 啟動...")
    
    db = SessionLocal()
    game_obj = get_or_create_game(db, GAME_CODE, GAME_NAME)
    print(f"✅ 資料庫連線成功。目標遊戲: {game_obj.name}")

    with sync_playwright() as p:
        print("\n>> 啟動瀏覽器...")
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        series_urls = get_all_series_links(page)
        print(f"✅ 發現 {len(series_urls)} 個系列。")

        if not series_urls:
            print("❌ 未找到系列，任務中止。")
            browser.close()
            db.close()
            return

        total_processed = 0
        total_updated = 0

        for i, series_url_path in enumerate(series_urls):
            series_url = BASE_URL + series_url_path
            print(f"\n -> [{i+1}/{len(series_urls)}] 正在處理: {series_url}")
            
            current_page = 1
            max_retries = 2
            
            while True:
                page_url = f"{series_url}?page={current_page}" if current_page > 1 else series_url
                
                for retry in range(max_retries):
                    try:
                        # 使用 domcontentloaded 而非 networkidle，避免卡住
                        page.goto(page_url, wait_until='domcontentloaded', timeout=20000)
                        page.wait_for_selector("li.list_item_cell", timeout=8000)
                        break
                    except PlaywrightTimeoutError:
                        if retry < max_retries - 1:
                            print(f"    ⚠️ 重試 {retry+1}/{max_retries}...")
                            time.sleep(2)
                        else:
                            print(f"    ❌ 頁面超時，跳過")
                            break
                    except Exception as e:
                        print(f"    ❌ 錯誤: {str(e)[:50]}")
                        break
                else:
                    # 重試都失敗
                    break
                
                try:
                    html = page.content()
                    soup = BeautifulSoup(html, 'html.parser')
                    card_items = soup.select("li.list_item_cell")
                    
                    if not card_items: break
                    print(f"    -> Page {current_page}: 發現 {len(card_items)} 張卡片...")

                    for item in card_items:
                        try:
                            item_data = item.find('div', class_='item_data')
                            if not item_data: continue
                            
                            name_tag = item_data.find('span', class_='goods_name')
                            price_tag = item_data.find('span', class_='figure')
                            stock_tag = item_data.find('p', class_='stock')
                            model_tag = item_data.find('span', class_='model_number_value')
                            
                            if not name_tag or not price_tag: continue
                            
                            item_name = name_tag.text.strip()
                            price_jpy = int(re.sub(r'[^\d]', '', price_tag.text))
                            
                            status = "In Stock"
                            if (stock_tag and "soldout" in str(stock_tag.get('class', []))):
                                status = "Out of Stock"
                            
                            # UA 卡號格式
                            item_card_number = ""
                            ua_regex = r'([A-Z]{2,}\d{2,}[A-Z]{0,2}/[A-Z0-9-]+-[A-Z0-9]+)'
                            if model_tag:
                                match = re.search(ua_regex, model_tag.text)
                                if match: item_card_number = match.group(1).strip()
                            if not item_card_number:
                                match = re.search(ua_regex, item_name)
                                if match: item_card_number = match.group(1).strip()
                            
                            if not item_card_number: continue

                            # 圖片
                            image_url = ""
                            img_container = item_data.select_one('div.global_photo')
                            if img_container and img_container.has_attr('data-src'):
                                image_url = img_container['data-src'].strip()
                                if image_url.startswith('//'): image_url = 'https:' + image_url

                            version = "Normal"
                            
                            # --- [資料庫操作] ---
                            set_code = item_card_number.split('/')[0] if '/' in item_card_number else "UA_Unknown"
                            card_set = get_or_create_set(db, game_obj.id, set_code)
                            card = get_or_create_card(db, card_set.id, item_card_number, item_name, image_url, version)
                            
                            is_updated = save_price(db, card.id, price_jpy, status, "sell")
                            
                            if is_updated:
                                print(f"      [UP] 💰 售價變動: {item_card_number} -> {price_jpy} JPY")
                                total_updated += 1
                            
                            total_processed += 1

                        except Exception as e:
                            continue

                    next_page = soup.select_one('a.to_next_page')
                    if not next_page: break
                    current_page += 1
                    time.sleep(0.5)

                except Exception as e:
                    print(f"    ❌ 頁面處理錯誤: {str(e)[:50]}")
                    break

        print(f"\n{'='*50}")
        print(f"🎉 Uniari 任務完成！")
        print(f"📊 總掃描: {total_processed}")
        print(f"💾 更新紀錄: {total_updated}")
        print(f"{'='*50}")

        browser.close()
    db.close()

if __name__ == "__main__":
    main()
