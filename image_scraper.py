"""
卡牌圖片爬蟲 - 從 Akiba 網站抓取卡牌圖片 URL
並更新到本地資料庫 + 同步到雲端 AI

這個腳本會：
1. 讀取資料庫中沒有圖片的卡牌
2. 從 Akiba 網站搜尋並抓取圖片 URL
3. 更新資料庫
4. 自動同步到雲端 AI 知識庫
"""

import sys
import os
import time
import re
import requests
from io import BytesIO
from datetime import datetime

# 添加 backend 目錄到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import Card, CardSet, Game

# 配置
CLOUD_AI_URL = "http://34.83.26.136:8080"
AKIBA_SEARCH_URL = "https://akihabara-cardshop.com/?s={}"

# 遊戲對應的搜尋頁面
GAME_IMAGE_SOURCES = {
    "OP": "https://akihabara-cardshop.com/op-kaitori-shindan/",
    "UA": "https://akihabara-cardshop.com/ua-kaitori-shindan/",
    # 可以添加更多遊戲
}

def get_db():
    """獲取資料庫連接"""
    return SessionLocal()

def get_cards_without_images(db: Session, game_code: str = None, limit: int = 100):
    """獲取沒有圖片的卡牌"""
    query = db.query(Card).filter(
        (Card.image_url == None) | (Card.image_url == "")
    )
    
    if game_code:
        query = query.join(CardSet).join(Game).filter(Game.code == game_code)
    
    return query.limit(limit).all()

def search_card_image_akiba(card_number: str):
    """從 Akiba 網站搜尋卡牌圖片"""
    try:
        # 嘗試直接搜尋卡號
        search_url = AKIBA_SEARCH_URL.format(card_number)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(search_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 尋找卡牌圖片
            # Akiba 網站通常使用 img 標籤
            images = soup.find_all('img')
            
            for img in images:
                src = img.get('src') or img.get('data-src') or ''
                alt = img.get('alt') or ''
                
                # 檢查是否是卡牌圖片
                if card_number.lower() in src.lower() or card_number.lower() in alt.lower():
                    if src.startswith('http'):
                        return src
                    elif src.startswith('/'):
                        return f"https://akihabara-cardshop.com{src}"
        
    except Exception as e:
        print(f"    搜尋錯誤: {e}")
    
    return None

def search_card_image_cardmarket(card_number: str, game_code: str):
    """備用：從 CardMarket 風格網站搜尋"""
    # 這是一個通用的圖片搜尋方法
    # 可以根據需要添加更多來源
    return None

def download_image(url: str):
    """下載圖片"""
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

def register_to_cloud_ai(card_id: int, card_number: str, name: str, image_bytes: bytes):
    """註冊卡牌到雲端 AI"""
    try:
        files = {"file": ("card.jpg", BytesIO(image_bytes), "image/jpeg")}
        params = {
            "card_id": card_id,
            "card_number": card_number,
            "name": name
        }
        
        response = requests.post(
            f"{CLOUD_AI_URL}/register",
            params=params,  # 使用 URL 參數
            files=files,
            timeout=30
        )
        
        return response.status_code == 200
    except:
        return False

def check_ai_status():
    """檢查 AI 服務狀態"""
    try:
        response = requests.get(f"{CLOUD_AI_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def scrape_and_sync(game_code: str = None, max_cards: int = 50, sync_to_ai: bool = True):
    """主函數：爬取圖片並同步"""
    
    print("=" * 60)
    print("🖼️ 卡牌圖片爬蟲 + 雲端 AI 同步")
    print("=" * 60)
    
    # 檢查 AI 服務
    if sync_to_ai:
        ai_status = check_ai_status()
        if ai_status:
            print(f"✅ 雲端 AI 在線，目前有 {ai_status.get('total_cards', 0)} 張卡牌")
        else:
            print("⚠️ 雲端 AI 離線，將只更新資料庫")
            sync_to_ai = False
    
    # 連接資料庫
    db = get_db()
    
    # 獲取沒有圖片的卡牌
    cards = get_cards_without_images(db, game_code, max_cards)
    print(f"\n📋 找到 {len(cards)} 張沒有圖片的卡牌")
    
    if not cards:
        print("沒有需要處理的卡牌")
        return
    
    # 統計
    stats = {
        "processed": 0,
        "image_found": 0,
        "image_downloaded": 0,
        "db_updated": 0,
        "ai_synced": 0,
        "failed": 0
    }
    
    for card in cards:
        stats["processed"] += 1
        
        card_number = card.card_number
        name = card.name or ""
        
        print(f"\n[{stats['processed']}/{len(cards)}] 處理: {card_number} - {name[:20]}")
        
        # 搜尋圖片
        image_url = search_card_image_akiba(card_number)
        
        if not image_url:
            print(f"    ❌ 找不到圖片")
            stats["failed"] += 1
            continue
        
        print(f"    ✅ 找到圖片: {image_url[:50]}...")
        stats["image_found"] += 1
        
        # 下載圖片
        image_bytes = download_image(image_url)
        
        if not image_bytes:
            print(f"    ⚠️ 下載失敗")
            # 仍然更新 URL
        else:
            stats["image_downloaded"] += 1
        
        # 更新資料庫
        try:
            card.image_url = image_url
            db.commit()
            stats["db_updated"] += 1
            print(f"    ✅ 資料庫已更新")
        except Exception as e:
            print(f"    ❌ 資料庫更新失敗: {e}")
            db.rollback()
        
        # 同步到 AI
        if sync_to_ai and image_bytes:
            if register_to_cloud_ai(card.id, card_number, name, image_bytes):
                stats["ai_synced"] += 1
                print(f"    ✅ 已同步到雲端 AI")
            else:
                print(f"    ⚠️ AI 同步失敗")
        
        # 避免請求過快
        time.sleep(1)
    
    # 關閉資料庫
    db.close()
    
    # 報告
    print("\n" + "=" * 60)
    print("📊 處理完成報告")
    print("=" * 60)
    print(f"  處理總數: {stats['processed']}")
    print(f"  ✅ 找到圖片: {stats['image_found']}")
    print(f"  ✅ 下載成功: {stats['image_downloaded']}")
    print(f"  ✅ 資料庫更新: {stats['db_updated']}")
    print(f"  ✅ AI 同步: {stats['ai_synced']}")
    print(f"  ❌ 失敗: {stats['failed']}")
    
    if sync_to_ai:
        final_status = check_ai_status()
        if final_status:
            print(f"\n🤖 雲端 AI 現有: {final_status.get('total_cards', 0)} 張卡牌")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="卡牌圖片爬蟲")
    parser.add_argument("--game", type=str, default=None, help="遊戲代碼 (OP, UA, VG, DM)")
    parser.add_argument("--max", type=int, default=50, help="最多處理數量")
    parser.add_argument("--no-ai", action="store_true", help="不同步到 AI")
    
    args = parser.parse_args()
    
    print(f"\n將處理最多 {args.max} 張卡牌")
    if args.game:
        print(f"遊戲過濾: {args.game}")
    
    scrape_and_sync(
        game_code=args.game,
        max_cards=args.max,
        sync_to_ai=not args.no_ai
    )
