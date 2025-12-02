"""
卡牌圖片同步到雲端 AI 知識庫
將資料庫中有圖片的卡牌註冊到 GCP 上的 CLIP AI 服務

直接讀取 PostgreSQL 資料庫，不依賴本地 API
"""

import requests
import time
import sys
import os
from io import BytesIO
from PIL import Image

# 添加路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import SessionLocal
from models import Card

# 配置
CLOUD_AI_URL = "http://34.83.26.136:8080"

def get_cards_with_images(limit=100, offset=0):
    """直接從資料庫獲取有圖片的卡牌"""
    try:
        db = SessionLocal()
        cards = db.query(Card).filter(
            Card.image_url != None, 
            Card.image_url != ""
        ).offset(offset).limit(limit).all()
        
        total = db.query(Card).filter(
            Card.image_url != None, 
            Card.image_url != ""
        ).count()
        
        result = []
        for card in cards:
            result.append({
                "card_id": card.id,
                "card_number": card.card_number,
                "name": card.name or "",
                "image_url": card.image_url
            })
        
        db.close()
        return result, total
    except Exception as e:
        print(f"獲取卡牌失敗: {e}")
    return [], 0

def download_image(url):
    """下載圖片"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

def register_card_to_ai(card_id, card_number, name, image_bytes):
    """註冊單張卡牌到雲端 AI"""
    try:
        files = {"file": ("card.jpg", BytesIO(image_bytes), "image/jpeg")}
        
        # 使用 query parameters 而不是 form data
        params = {
            "card_id": card_id,
            "card_number": card_number,
            "name": name
        }
        
        response = requests.post(
            f"{CLOUD_AI_URL}/register",
            params=params,  # 作為 URL 參數
            files=files,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_ai_status():
    """檢查 AI 服務狀態"""
    try:
        # 先檢查健康狀態
        health_response = requests.get(f"{CLOUD_AI_URL}/health", timeout=5)
        if health_response.status_code != 200:
            return None
        
        # 獲取統計數據
        stats_response = requests.get(f"{CLOUD_AI_URL}/stats", timeout=5)
        if stats_response.status_code == 200:
            stats = stats_response.json()
            return {
                "status": "running",
                "total_cards": stats.get("total_cards", 0),
                "cards": stats.get("total_cards", 0)  # 兼容舊格式
            }
    except:
        pass
    return None

def sync_cards(max_cards=1000, batch_size=50):
    """同步卡牌到雲端 AI"""
    
    print("=" * 60)
    print("🚀 卡牌圖片同步到雲端 AI 知識庫")
    print("=" * 60)
    
    # 檢查 AI 服務
    status = check_ai_status()
    if not status:
        print("❌ 無法連接到雲端 AI 服務")
        return
    
    print(f"✅ 雲端 AI 在線，目前已有 {status.get('cards', 0)} 張卡牌")
    print()
    
    # 統計
    total_processed = 0
    total_success = 0
    total_failed = 0
    total_no_image = 0
    
    offset = 0
    
    while total_processed < max_cards:
        # 獲取卡牌
        cards, total = get_cards_with_images(limit=batch_size, offset=offset)
        
        if not cards:
            print("沒有更多卡牌了")
            break
        
        print(f"\n📦 處理批次 {offset // batch_size + 1} ({len(cards)} 張卡牌)")
        
        for card in cards:
            if total_processed >= max_cards:
                break
                
            card_id = card.get("card_id")
            card_number = card.get("card_number", "")
            name = card.get("name", "")
            image_url = card.get("image_url") or ""
            
            total_processed += 1
            
            # 跳過沒有圖片的卡牌
            if not image_url or image_url == "":
                total_no_image += 1
                continue
            
            # 下載圖片
            image_bytes = download_image(image_url)
            if not image_bytes:
                print(f"  ⚠️ 無法下載圖片: {card_number}")
                total_failed += 1
                continue
            
            # 註冊到 AI
            result = register_card_to_ai(card_id, card_number, name, image_bytes)
            
            if result.get("success"):
                total_success += 1
                if total_success % 10 == 0:
                    print(f"  ✅ 已註冊 {total_success} 張卡牌...")
            else:
                print(f"  ❌ 註冊失敗: {card_number} - {result.get('error', 'unknown')}")
                total_failed += 1
            
            # 稍微延遲避免過載
            time.sleep(0.1)
        
        offset += batch_size
        
        # 每批次後檢查 AI 狀態
        status = check_ai_status()
        if status:
            print(f"  📊 知識庫現有: {status.get('total_cards', 0)} 張卡牌")
    
    # 最終報告
    print()
    print("=" * 60)
    print("📊 同步完成報告")
    print("=" * 60)
    print(f"  處理總數: {total_processed}")
    print(f"  ✅ 成功: {total_success}")
    print(f"  ❌ 失敗: {total_failed}")
    print(f"  ⏭️ 無圖片: {total_no_image}")
    
    # 最終狀態
    final_status = check_ai_status()
    if final_status:
        print(f"\n🎉 雲端 AI 知識庫現有: {final_status.get('total_cards', 0)} 張卡牌")
    
    print("=" * 60)

if __name__ == "__main__":
    # 可以指定同步數量
    max_cards = 100  # 預設同步前 100 張
    
    if len(sys.argv) > 1:
        try:
            max_cards = int(sys.argv[1])
        except:
            pass
    
    print(f"\n將同步最多 {max_cards} 張卡牌到雲端 AI")
    print("直接讀取 PostgreSQL 資料庫\n")
    
    sync_cards(max_cards=max_cards)
