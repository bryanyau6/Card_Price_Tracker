from database import engine, Base
from models import Game, CardSet, Card, MarketPrice, InternalPrice

def init_db():
    print(">> 正在連接 PostgreSQL 資料庫...")
    print(">> 正在建立資料庫表格 (Schema)...")
    
    # 這行指令會根據 models.py 的定義，在資料庫中自動建立所有表格
    # 如果表格已存在，它會跳過 (不會刪除現有資料)
    Base.metadata.create_all(bind=engine)
    
    print("✅ 資料庫表格建立完成！")
    print("   - games")
    print("   - card_sets")
    print("   - cards")
    print("   - market_prices")
    print("   - internal_prices")

if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        print("請檢查：")
        print("1. PostgreSQL 服務是否已啟動？")
        print("2. .env 檔案中的密碼是否正確？")
        print("3. 資料庫名稱 (tcge_db) 是否已在 pgAdmin 4 中建立？")
