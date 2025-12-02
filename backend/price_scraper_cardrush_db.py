# =========================================================
# TCGE-CIS 2.0: CardRush 爬蟲 (資料庫版) - DM & VG
# Author: 電王 & Copilot
# 
# 職責: 抓取 CardRush 的 DM 與 VG 售價
# 升級重點:
# 1. 寫入 PostgreSQL 資料庫。
# 2. 支援多遊戲 (DM / VG)。
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
WEBSITE_NAME = "Cardrush"

# 支援的遊戲設定
GAMES_CONFIG = [
    {
        "code": "DM",
        "name": "Duel Masters",
        "base_url": "https://www.cardrush-dm.jp",
        "index_url": "https://www.cardrush-dm.jp/",
        "selector": "div.pickupcategory_division1 ul.pickupcategory_list li a",
        "card_regex": r'\{([^}]+)\}'
    },
    {
        "code": "VG",
        "name": "Cardfight!! Vanguard",
        "base_url": "https://www.cardrush-vanguard.jp",
        "index_url": "https://www.cardrush-vanguard.jp/",
        "selector": "div.pickupcategory_division1 ul.pickupcategory_list li a",
        "card_regex": r'\{([^}]+)\}'
    }
]

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
        rarity_match = re.search(r'【([^】]+)】', name)
        if rarity_match: rarity = rarity_match.group(1)
        
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
        print(f"      [DB] ✨ 新增卡片: {card_number}")
    return card

def generate_price_hash(source, price_type, price, status):
    data_string = f"{source}|{price_type}|{price}|{status}"
    return hashlib.md5(data_string.encode()).hexdigest()

def save_price(db: Session, card_id: int, price_jpy: int, status: str, source: str, price_type: str = "sell"):
    current_hash = generate_price_hash(source, price_type, price_jpy, status)
    
    last_price = db.query(MarketPrice).filter(
        MarketPrice.card_id == card_id,
        MarketPrice.source == source,
        MarketPrice.price_type == price_type
    ).order_by(MarketPrice.timestamp.desc()).first()
    
    if last_price and last_price.data_hash == current_hash:
        return False
    
    new_price = MarketPrice(
        card_id=card_id,
        source=source,
        price_type=price_type,
        price_jpy=price_jpy,
        stock_status=status,
        data_hash=current_hash
    )
    db.add(new_price)
    db.commit()
    return True

# --- [爬蟲邏輯] ---

def get_series_links(page, url, selector, base_url):
    print(f" -> 正在掃描: {url}...")
    try:
        page.goto(url, wait_until='networkidle', timeout=60000)
        page.wait_for_selector(selector, timeout=15000)
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        series_links = soup.select(selector)
        for link in series_links:
            href = link.get('href')
            if href and ('/product-group/' in href):
                if href.startswith(base_url): href = href.replace(base_url, "")
                href_without_params = href.split('?')[0]
                if href_without_params not in links:
                    links.append(href_without_params)
        return links
    except Exception as e:
        print(f" -> ❌ 掃描失敗: {e}")
        return []

def scrape_game(db: Session, page, game_config: dict):
    game_code = game_config["code"]
    game_name = game_config["name"]
    base_url = game_config["base_url"]
    index_url = game_config["index_url"]
    selector = game_config["selector"]
    card_regex = game_config["card_regex"]
    source_name = f"{WEBSITE_NAME}-{game_code}"

    print(f"\n{'='*50}")
    print(f"🎮 開始處理: {game_name}")
    print(f"{'='*50}")

    game_obj = get_or_create_game(db, game_code, game_name)
    
    series_urls = get_series_links(page, index_url, selector, base_url)
    print(f"✅ 發現 {len(series_urls)} 個系列。")

    if not series_urls:
        return 0, 0

    total_processed = 0
    total_updated = 0

    for i, series_url_path in enumerate(series_urls):  # 處理所有系列
        series_url = base_url + series_url_path
        print(f"\n -> [{i+1}/{len(series_urls)}] 處理: {series_url}")
        
        current_page = 1
        max_retries = 2
        
        while True:
            page_url = f"{series_url}?page={current_page}" if current_page > 1 else series_url
            
            retry_count = 0
            page_success = False
            
            while retry_count < max_retries and not page_success:
                try:
                    # 使用 domcontentloaded 而非 networkidle，更快更穩定
                    page.goto(page_url, wait_until='domcontentloaded', timeout=15000)
                    page.wait_for_selector("li.list_item_cell", timeout=8000)
                    page_success = True
                except PlaywrightTimeoutError:
                    retry_count += 1
                    print(f"    ⚠️ 超時，重試 {retry_count}/{max_retries}...")
                    time.sleep(2)
                except Exception as e:
                    retry_count += 1
                    print(f"    ⚠️ 錯誤: {str(e)[:50]}，重試 {retry_count}/{max_retries}...")
                    time.sleep(2)
            
            if not page_success:
                print(f"    ❌ 跳過此頁面")
                break
            
            try:
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                card_items = soup.select("li.list_item_cell")
                
                if not card_items: break
                print(f"    -> Page {current_page}: {len(card_items)} 張卡片")

                for item in card_items:
                    try:
                        item_data = item.find('div', class_='item_data')
                        if not item_data: continue
                        
                        name_tag = item.find('span', class_='goods_name')
                        price_tag = item.find('span', class_='figure')
                        stock_tag = item.find('p', class_='stock')
                        
                        if not name_tag or not price_tag: continue
                        
                        item_name = name_tag.text.strip()
                        price_jpy = int(re.sub(r'[^\d]', '', price_tag.text))
                        
                        status = "In Stock"
                        if stock_tag and ("soldout" in stock_tag.get('class', []) or "SOLD OUT" in stock_tag.text):
                            status = "Out of Stock"
                        
                        # 卡號解析
                        item_card_number = ""
                        match = re.search(card_regex, item_name)
                        if match:
                            item_card_number = match.group(1).strip()
                        
                        if not item_card_number: continue

                        # 圖片
                        image_url = ""
                        img_tag = item.select_one("div.global_photo img")
                        if img_tag and img_tag.has_attr('src'):
                            image_url = img_tag['src'].strip()
                            if image_url.startswith('//'): image_url = 'https:' + image_url
                            elif not image_url.startswith('http'): image_url = base_url + image_url

                        version = "Normal"
                        
                        # --- [資料庫操作] ---
                        set_code = item_card_number.split('/')[0].split('-')[0] if '/' in item_card_number else item_card_number[:4]
                        card_set = get_or_create_set(db, game_obj.id, set_code)
                        card = get_or_create_card(db, card_set.id, item_card_number, item_name, image_url, version)
                        
                        is_updated = save_price(db, card.id, price_jpy, status, source_name, "sell")
                        
                        if is_updated:
                            print(f"      [UP] 💰 {item_card_number} -> {price_jpy} JPY")
                            total_updated += 1
                        
                        total_processed += 1

                    except Exception:
                        continue

                next_page = soup.select_one('a.to_next_page')
                if not next_page: break
                current_page += 1
                time.sleep(0.5)

            except Exception as e:
                print(f"    ❌ 頁面處理錯誤: {str(e)[:50]}")
                break

    return total_processed, total_updated

def main():
    print(f"\n>> TCGE-CIS 2.0: CardRush 爬蟲 (資料庫版) 啟動...")
    
    db = SessionLocal()
    print("✅ 資料庫連線成功。")

    grand_total_processed = 0
    grand_total_updated = 0

    with sync_playwright() as p:
        print("\n>> 啟動瀏覽器...")
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        for game_config in GAMES_CONFIG:
            processed, updated = scrape_game(db, page, game_config)
            grand_total_processed += processed
            grand_total_updated += updated

        browser.close()

    print(f"\n{'='*50}")
    print(f"🎉 CardRush 全部任務完成！")
    print(f"📊 總掃描: {grand_total_processed}")
    print(f"💾 更新紀錄: {grand_total_updated}")
    print(f"{'='*50}")

    db.close()

if __name__ == "__main__":
    main()
