"""檢查資料庫統計"""
from database import SessionLocal
from models import Game, CardSet, Card, MarketPrice

db = SessionLocal()

print("=" * 50)
print("          TCGE CIS 2.0 資料庫統計報告")
print("=" * 50)

# 遊戲列表
games = db.query(Game).all()
print(f"\n📦 遊戲數量: {len(games)}")
for g in games:
    print(f"   • {g.name} ({g.code})")

# 總計
sets = db.query(CardSet).count()
cards = db.query(Card).count()
prices = db.query(MarketPrice).count()

print(f"\n📁 卡組數量: {sets}")
print(f"🎴 卡片數量: {cards}")
print(f"💰 價格記錄: {prices}")

# 各遊戲詳細
print("\n" + "=" * 50)
print("          各遊戲詳細統計")
print("=" * 50)

for g in games:
    set_count = db.query(CardSet).filter(CardSet.game_id == g.id).count()
    card_count = db.query(Card).join(CardSet).filter(CardSet.game_id == g.id).count()
    price_count = db.query(MarketPrice).join(Card).join(CardSet).filter(CardSet.game_id == g.id).count()
    print(f"\n🎮 {g.code} - {g.name}")
    print(f"   卡組: {set_count}")
    print(f"   卡片: {card_count}")
    print(f"   價格: {price_count}")

# 來源統計
print("\n" + "=" * 50)
print("          價格來源統計")
print("=" * 50)

from sqlalchemy import func
sources = db.query(
    MarketPrice.source,
    MarketPrice.price_type,
    func.count(MarketPrice.id)
).group_by(MarketPrice.source, MarketPrice.price_type).all()

for source, ptype, count in sources:
    print(f"   {source} ({ptype}): {count} 筆")

db.close()

print("\n" + "=" * 50)
print("          統計完成")
print("=" * 50)
