# =========================================================
# TCGE-CIS 2.0: Akiba 爬蟲 (資料庫版)
# Author: 電王 & Copilot
# 
# 職責: 抓取 Akiba Cardshop 的 OP 買取價格
# 升級重點:
# 1. 寫入 PostgreSQL 資料庫。
# 2. price_type = 'buy' (買取價)。
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

# 引入資料庫模組
from database import SessionLocal
from models import Game, CardSet, Card, MarketPrice

# --- [設定區域] ---
WEBSITE_NAME = "Akiba-Cardshop"
TARGET_URL = "https://akihabara-cardshop.com/op-kaitori-shindan/" # 新彈買取
# 注意: 這裡只示範新彈頁面，若要包含主列表需擴充 URL 列表
BASE_URL_AKIBA = "https://akihabara-cardshop.com"
GAME_CODE = "OP"
GAME_NAME = "One Piece Card Game"
LOAD_MORE_BUTTON_SELECTOR = "button#loadMoreButton"
FIRST_CARD_SELECTOR = "div.tr"

# --- [資料庫工具函數 (重用)] ---
# 為了保持代碼獨立性，這裡再次定義，實際專案中應提取到 crud.py

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
        rarity = "Unknown" # Akiba 頁面較難直接解析稀有度，暫設 Unknown
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

def save_price(db: Session, card_id: int, price_jpy: int, status: str):
    current_hash = generate_price_hash(WEBSITE_NAME, "buy", price_jpy, status)
    
    last_price = db.query(MarketPrice).filter(
        MarketPrice.card_id == card_id,
        MarketPrice.source == WEBSITE_NAME,
        MarketPrice.price_type == "buy" # 注意: 這裡是 buy
    ).order_by(MarketPrice.timestamp.desc()).first()
    
    if last_price and last_price.data_hash == current_hash:
        return False
    
    new_price = MarketPrice(
        card_id=card_id,
        source=WEBSITE_NAME,
        price_type="buy", # 注意: 這裡是 buy
        price_jpy=price_jpy,
        stock_status=status,
        data_hash=current_hash
    )
    db.add(new_price)
    db.commit()
    return True

# --- [爬蟲主程式] ---

def main():
    print(f"\n>> TCGE-CIS 2.0: Akiba 爬蟲 (資料庫版) 啟動...")
    
    db = SessionLocal()
    game_obj = get_or_create_game(db, GAME_CODE, GAME_NAME)
    print(f"✅ 資料庫連線成功。目標遊戲: {game_obj.name}")

    with sync_playwright() as p:
        print("\n>> 啟動瀏覽器...")
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        print(f" -> 正在訪問: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, wait_until='domcontentloaded', timeout=120000)
            
            # 檢查頁面是否為空
            try:
                page.wait_for_selector(FIRST_CARD_SELECTOR, timeout=15000)
            except PlaywrightTimeoutError:
                print(" ⚠️ 警告: 頁面可能為空或未加載。")
                browser.close()
                return

            # 循環點擊 "Load More"
            print(" -> 正在加載所有卡片...")
            click_count = 0
            while True:
                try:
                    button = page.locator(LOAD_MORE_BUTTON_SELECTOR + ":not([style*='display: none'])")
                    if button.is_visible():
                        button.click()
                        click_count += 1
                        print(f"    -> 點擊「更多」 ({click_count})...")
                        page.wait_for_load_state('networkidle', timeout=5000)
                        time.sleep(1)
                    else:
                        break
                except Exception:
                    break
            
            print(" -> 開始解析頁面...")
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            card_units = soup.select("div.tbody > div.tr")
            print(f"✅ 發現 {len(card_units)} 條買取情報。")

            total_processed = 0
            total_updated = 0

            for unit in card_units:
                try:
                    name_div = unit.select_one("div.td.td2")
                    model_div = unit.select_one("div.td.td3")
                    price_span = unit.select_one("div.td.td5 span.price")
                    img_tag = unit.select_one("div.td.td1 img")
                    
                    if not name_div or not model_div or not price_span: continue
                    
                    price_jpy = int(re.sub(r'[^\d]', '', price_span.text))
                    model_text = model_div.text.strip()
                    
                    # 卡號解析
                    match_num = re.search(r'([A-Z]{1,3}\d{2,3}-?[A-Z]?\d{1,3})', model_text) 
                    if not match_num: continue
                    item_card_number = match_num.group(1).strip()
                    
                    item_name = name_div.text.strip()
                    
                    # 圖片 URL
                    image_url = ""
                    if img_tag and img_tag.has_attr('src'):
                        image_url = img_tag['src'].strip()
                        image_url = re.sub(r'\s+', '', image_url)
                        if image_url.startswith('/'): image_url = BASE_URL_AKIBA + image_url

                    # 版本判斷
                    version = "Normal" # Akiba 較難判斷版本，暫設 Normal，可根據名稱優化

                    # --- [資料庫操作] ---
                    set_code = item_card_number.split('-')[0] if '-' in item_card_number else "Unknown"
                    card_set = get_or_create_set(db, game_obj.id, set_code)
                    card = get_or_create_card(db, card_set.id, item_card_number, item_name, image_url, version)
                    
                    # 狀態: Akiba 爬蟲抓的是「買取表」，所以狀態通常是「買取中」
                    status = "買取中"
                    
                    is_updated = save_price(db, card.id, price_jpy, status)
                    
                    if is_updated:
                        print(f"      [UP] 💰 買取變動: {item_card_number} -> {price_jpy} JPY")
                        total_updated += 1
                    
                    total_processed += 1

                except Exception as e:
                    print(f"      ❌ 解析錯誤: {e}")
                    continue

            print(f"\n{'='*50}")
            print(f"🎉 Akiba 任務完成！")
            print(f"📊 總掃描: {total_processed}")
            print(f"💾 更新紀錄: {total_updated}")
            print(f"{'='*50}")

        except Exception as e:
            print(f"❌ 發生錯誤: {e}")
        
        browser.close()
    db.close()

if __name__ == "__main__":
    main()
