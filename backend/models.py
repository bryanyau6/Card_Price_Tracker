from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# 1. 遊戲分類表 (例如: OP, UA, DM, VG)
class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True) # e.g., "OP", "UA"
    name = Column(String(100)) # e.g., "One Piece Card Game"
    
    sets = relationship("CardSet", back_populates="game")

# 2. 系列/彈數表 (例如: OP01, OP02)
class CardSet(Base):
    __tablename__ = "card_sets"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    code = Column(String(20), index=True) # e.g., "OP01"
    name = Column(String(200)) # e.g., "Romance Dawn"
    release_date = Column(DateTime, nullable=True)

    game = relationship("Game", back_populates="sets")
    cards = relationship("Card", back_populates="card_set")

# 3. 卡牌主檔表 (靜態資料)
# 這裡只存不會變的東西：卡號、名稱、圖片
class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    card_set_id = Column(Integer, ForeignKey("card_sets.id"))
    
    card_number = Column(String(50), index=True) # e.g., "OP01-001"
    name = Column(String(200), index=True) # e.g., "Roronoa Zoro"
    version = Column(String(100)) # e.g., "L", "Parallel", "Promo"
    rarity = Column(String(20)) # e.g., "SR", "L", "SEC"
    card_type = Column(String(50)) # e.g., "Character", "Event"
    image_url = Column(Text) # 圖片連結
    
    # 複合唯一索引：確保同一個系列下，卡號+版本是唯一的
    # 這樣就不會重複建立同一張卡
    __table_args__ = (
        Index('idx_card_unique', 'card_number', 'version', unique=True),
    )

    card_set = relationship("CardSet", back_populates="cards")
    market_prices = relationship("MarketPrice", back_populates="card")
    internal_price = relationship("InternalPrice", back_populates="card", uselist=False)

# 4. 市場價格表 (動態資料 - 爬蟲寫入這裡)
# 這是系統的核心，記錄所有歷史價格
class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), index=True)
    
    source = Column(String(50)) # e.g., "Mercadop", "CardRush", "Akiba"
    price_type = Column(String(20)) # "sell" (售價) or "buy" (買取)
    price_jpy = Column(Integer) # 日幣價格
    stock_status = Column(String(50)) # "In Stock", "Out of Stock", "買取中"
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # 數據指紋 (Hash)，用於增量更新比對
    # 內容通常是 hash(source + price_type + price_jpy + stock_status)
    data_hash = Column(String(64), index=True) 

    card = relationship("Card", back_populates="market_prices")

# 5. TCGE 內部定價表 (店內價格)
class InternalPrice(Base):
    __tablename__ = "internal_prices"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), unique=True)
    
    tcge_sell_hkd = Column(Float, default=0.0) # 我們的售價 (HKD)
    tcge_buy_hkd = Column(Float, default=0.0)  # 我們的買取價 (HKD)
    
    # 自動計算的參考匯率 (可選)
    ref_exchange_rate = Column(Float, default=0.05) 
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    card = relationship("Card", back_populates="internal_price")
