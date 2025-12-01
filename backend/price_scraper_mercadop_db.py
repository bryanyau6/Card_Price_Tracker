# =========================================================
# TCGE-CIS 2.0: Mercadop 爬蟲 (資料庫版)
# Author: 電王 & Copilot
# 
# 升級重點:
# 1. 移除 Google Sheets 依賴，改為直接寫入 PostgreSQL。
# 2. 實作「靜態/動態分離」：卡片資料存 cards 表，價格存 market_prices 表。
# 3. 實作「增量更新」：透過 Hash 比對，只有價格變動時才寫入。
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
from sqlalchemy import select

# 引入資料庫模組
from database import SessionLocal, engine
from models import Game, CardSet, Card, MarketPrice

# --- [設定區域] ---
WEBSITE_NAME = "MercadoP"
BASE_URL = "https://www.mercardop.jp"
GAME_CODE = "OP" # One Piece
GAME_NAME = "One Piece Card Game"
SERIES_PAGE_URL = "https://www.mercardop.jp/page/5" 

# --- [資料庫工具函數] ---

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_or_create_game(db: Session, code: str, name: str):
    game = db.query(Game).filter(Game.code == code).first()
    if not game:
        game = Game(code=code, name=name)
        db.add(game)
        db.commit()
        db.refresh(game)
    return game

def get_or_create_set(db: Session, game_id: int, set_code: str):
    # 簡單處理：如果 set_code 不存在就建立
    card_set = db.query(CardSet).filter(CardSet.code == set_code, CardSet.game_id == game_id).first()
    if not card_set:
        card_set = CardSet(game_id=game_id, code=set_code, name=f"Series {set_code}")
        db.add(card_set)
        db.commit()
        db.refresh(card_set)
    return card_set

def get_or_create_card(db: Session, set_id: int, card_number: str, name: str, image_url: str, version: str = "Normal"):
    # 複合查詢：卡號 + 版本
    card = db.query(Card).filter(
        Card.card_number == card_number,
        Card.version == version
    ).first()
    
    if not card:
        # 判斷稀有度 (簡單邏輯)
        rarity = "Unknown"
        if "SEC" in name: rarity = "SEC"
        elif "SR" in name: rarity = "SR"
        elif "L" in name: rarity = "L"
        elif "R" in name: rarity = "R"
        
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
    """生成數據指紋，用於比對是否變動"""
    data_string = f"{source}|{price_type}|{price}|{status}"
    return hashlib.md5(data_string.encode()).hexdigest()

def save_price(db: Session, card_id: int, price_jpy: int, status: str):
    # 1. 生成本次指紋
    current_hash = generate_price_hash(WEBSITE_NAME, "sell", price_jpy, status)
    
    # 2. 查詢該卡「最新」的一筆價格紀錄
    last_price = db.query(MarketPrice).filter(
        MarketPrice.card_id == card_id,
        MarketPrice.source == WEBSITE_NAME,
        MarketPrice.price_type == "sell"
    ).order_by(MarketPrice.timestamp.desc()).first()
    
    # 3. 比對指紋
    if last_price and last_price.data_hash == current_hash:
        # 指紋相同 -> 價格沒變 -> 跳過不存
        return False
    
    # 4. 指紋不同 (或沒有歷史紀錄) -> 新增紀錄
    new_price = MarketPrice(
        card_id=card_id,
        source=WEBSITE_NAME,
        price_type="sell",
        price_jpy=price_jpy,
        stock_status=status,
        data_hash=current_hash
    )
    db.add(new_price)
    db.commit()
    return True

# --- [爬蟲邏輯 (移植自 v3.5)] ---

def get_series_urls(page, series_page_url):
    print(f" -> 正在掃描系列頁面: {series_page_url}...")
    selector = "div.cate_navi_wrap ul.cate_navi li.cate_li a.cate_aa" 
    try:
        page.goto(series_page_url, wait_until='networkidle', timeout=60000)
        page.wait_for_selector(selector, timeout=30000) 
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        navi_wraps = soup.select("div.cate_navi_wrap")
        for wrap in navi_wraps:
            title_tag = wrap.find('h2', class_='cate_navi_ttl')
            if title_tag and ('BOOSTER' in title_tag.text or 'DECKS' in title_tag.text):
                series_link_tags = wrap.select("ul.cate_navi li.cate_li a.cate_aa")
                for link_tag in series_link_tags:
                    href = link_tag.get('href')
                    if href and ('/product-group/' in href):
                        if href.startswith(BASE_URL): href = href.replace(BASE_URL, "") 
                        href_without_params = href.split('?')[0]
                        if href_without_params not in links:
                            links.append(href_without_params) 
        return links
    except Exception as e:
        print(f" -> ❌ 掃描系列頁面失敗: {e}")
        return []

def main():
    print(f"\n>> TCGE-CIS 2.0: Mercadop 爬蟲 (資料庫版) 啟動...")
    
    # 1. 初始化資料庫連線
    db = SessionLocal()
    
    # 2. 確保 Game 存在
    game_obj = get_or_create_game(db, GAME_CODE, GAME_NAME)
    print(f"✅ 資料庫連線成功。目標遊戲: {game_obj.name}")

    with sync_playwright() as p:
        print("\n>> 啟動瀏覽器...")
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        # 3. 獲取系列連結
        series_urls = get_series_urls(page, SERIES_PAGE_URL)
        print(f"✅ 發現 {len(series_urls)} 個系列。")

        total_cards_processed = 0
        total_prices_updated = 0

        # 4. 遍歷系列
        for i, series_url_path in enumerate(series_urls):
            series_url = BASE_URL + series_url_path
            print(f"\n -> [{i+1}/{len(series_urls)}] 正在處理系列: {series_url}")
            
            # 從 URL 推測 Set Code (例如 /product-group/146 -> 無法推測，需從卡號推測)
            # 這裡我們先設為 "Unknown"，等抓到卡號再更新
            
            current_page = 1
            while True:
                page_url = f"{series_url}?page={current_page}"
                if current_page == 1: page_url = series_url
                
                try:
                    page.goto(page_url, wait_until='networkidle', timeout=30000)
                    # 檢查是否有商品
                    if page.locator("li.list_item_cell").count() == 0:
                        break
                        
                    html = page.content()
                    soup = BeautifulSoup(html, 'html.parser')
                    card_items = soup.select("li.list_item_cell")
                    
                    if not card_items: break
                    
                    print(f"    -> Page {current_page}: 發現 {len(card_items)} 張卡片...")

                    for item in card_items:
                        try:
                            # 解析 HTML
                            item_data = item.find('div', class_='item_data')
                            if not item_data: continue
                            
                            name_tag = item_data.find('span', class_='goods_name')
                            price_tag = item_data.find('span', class_='figure')
                            stock_tag = item_data.find('p', class_='stock')
                            model_tag = item_data.find('span', class_='model_number_value')
                            
                            if not name_tag or not price_tag: continue
                            
                            item_name = name_tag.text.strip()
                            price_jpy = int(re.sub(r'[^\d]', '', price_tag.text))
                            
                            # 狀態判斷
                            status = "In Stock"
                            if (stock_tag and "soldout" in str(stock_tag)) or 'soldout' in item.get('class', []):
                                status = "Out of Stock"
                            
                            # 卡號解析
                            item_card_number = ""
                            if model_tag:
                                match = re.search(r'([A-Z]{2,3}\d{2,3}-?[A-Z]?\d{3})', model_tag.text)
                                if match: item_card_number = match.group(1)
                            if not item_card_number:
                                match_name = re.search(r'([A-Z]{2,3}\d{2,3}-?[A-Z]?\d{3})', item_name)
                                if match_name: item_card_number = match_name.group(1)
                            
                            if not item_card_number: continue

                            # 圖片 URL
                            image_url = ""
                            img_tag = item_data.select_one('div.global_photo')
                            if img_tag and img_tag.has_attr('data-src'):
                                image_url = img_tag['data-src'].strip()
                                if image_url.startswith('//'): image_url = 'https:' + image_url
                                elif image_url.startswith('/'): image_url = BASE_URL + image_url

                            # 版本判斷 (Version)
                            version = "Normal"
                            if "パラレル" in item_name: version = "Parallel"
                            elif "未開封" in item_name: version = "Sealed"
                            
                            # --- [資料庫操作核心] ---
                            
                            # 1. 取得或建立 Set (從卡號前綴推測，例如 OP01)
                            set_code = item_card_number.split('-')[0] if '-' in item_card_number else "Unknown"
                            card_set = get_or_create_set(db, game_obj.id, set_code)
                            
                            # 2. 取得或建立 Card (靜態資料)
                            card = get_or_create_card(db, card_set.id, item_card_number, item_name, image_url, version)
                            
                            # 3. 儲存價格 (動態資料 - 只有變動時才存)
                            is_updated = save_price(db, card.id, price_jpy, status)
                            
                            if is_updated:
                                print(f"      [UP] 💰 價格變動: {item_card_number} -> {price_jpy} JPY")
                                total_prices_updated += 1
                            
                            total_cards_processed += 1

                        except Exception as e:
                            print(f"      ❌ 解析錯誤: {e}")
                            continue

                    # 下一頁檢查
                    next_page = soup.select_one('a.to_next_page')
                    if not next_page: break
                    current_page += 1
                    time.sleep(1) # 禮貌性等待

                except Exception as e:
                    print(f"    ❌ 頁面錯誤: {e}")
                    break
        
        print(f"\n{'='*50}")
        print(f"🎉 任務完成！")
        print(f"📊 總掃描卡片: {total_cards_processed}")
        print(f"💾 新增價格紀錄: {total_prices_updated} (節省了 {total_cards_processed - total_prices_updated} 筆無效寫入)")
        print(f"{'='*50}")
        
        browser.close()
    db.close()

if __name__ == "__main__":
    main()
