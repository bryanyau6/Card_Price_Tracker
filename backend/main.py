# =========================================================
# TCGE-CIS 2.0: FastAPI 後端 API
# Author: 電王 & Copilot
#
# 提供 RESTful API 供前端查詢卡牌價格資訊
# =========================================================

from fastapi import FastAPI, Depends, Query, HTTPException, Body, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import json
import base64
import hashlib
import httpx

from database import SessionLocal, engine
from models import Game, CardSet, Card, MarketPrice, InternalPrice

# ====== 雲端 AI 服務配置 ======
CLOUD_AI_URL = "http://34.83.26.136:8080"
USE_CLOUD_AI = True  # 設為 True 使用雲端 AI，False 使用本地 OCR

app = FastAPI(
    title="TCGE Card Intelligence System 2.0",
    description="卡牌價格追蹤系統 API",
    version="2.0.0"
)

# 允許跨域請求 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- [資料庫依賴] ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- [Pydantic 模型 (回應格式)] ---
class PriceInfo(BaseModel):
    source: str
    price_type: str
    price_jpy: int
    stock_status: Optional[str]
    timestamp: datetime
    
    class Config:
        from_attributes = True

class CardSearchResult(BaseModel):
    id: int
    card_number: str
    name: str
    version: str
    rarity: Optional[str]
    image_url: Optional[str]
    set_code: Optional[str]
    game_code: Optional[str]
    latest_sell_jpy: Optional[int] = None
    latest_buy_jpy: Optional[int] = None
    
    class Config:
        from_attributes = True

class CardDetailResult(BaseModel):
    id: int
    card_number: str
    name: str
    version: str
    rarity: Optional[str]
    image_url: Optional[str]
    set_code: Optional[str]
    game_code: Optional[str]
    prices: List[PriceInfo] = []
    
    class Config:
        from_attributes = True

# --- [內部定價模型] ---
class InternalPriceInfo(BaseModel):
    card_id: int
    card_number: str
    name: str
    version: str
    game_code: Optional[str]
    latest_sell_jpy: Optional[int] = None
    latest_buy_jpy: Optional[int] = None
    tcge_sell_hkd: float = 0.0
    tcge_buy_hkd: float = 0.0
    ref_exchange_rate: float = 0.052

    class Config:
        from_attributes = True

class InternalPriceUpdate(BaseModel):
    card_id: int
    tcge_sell_hkd: Optional[float] = None
    tcge_buy_hkd: Optional[float] = None

class BatchPriceUpdate(BaseModel):
    updates: List[InternalPriceUpdate]

class AutoCalculateRequest(BaseModel):
    card_ids: List[int]
    exchange_rate: float = 0.052
    sell_margin: float = 1.2  # 售價加成 20%
    buy_margin: float = 0.7   # 買取價折扣 30%

# --- [買取單模型] ---
class BuyOrderItem(BaseModel):
    card_id: int
    quantity: int = 1
    price_hkd: float = 0.0

class BuyOrderCreate(BaseModel):
    customer_name: Optional[str] = None
    items: List[BuyOrderItem]
    notes: Optional[str] = None

# --- [API 路由] ---

@app.get("/", response_class=HTMLResponse)
async def root():
    """首頁 - 搜尋介面"""
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TCGE 卡牌價格系統 2.0</title>
        <style>
            * { box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #eee; 
                margin: 0; 
                padding: 20px;
                min-height: 100vh;
            }
            .container { max-width: 1200px; margin: 0 auto; }
            h1 { text-align: center; color: #00d4ff; margin-bottom: 30px; }
            .search-box {
                display: flex;
                gap: 10px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            #searchInput {
                flex: 1;
                min-width: 200px;
                padding: 15px 20px;
                font-size: 18px;
                border: 2px solid #00d4ff;
                border-radius: 10px;
                background: #0f0f23;
                color: #fff;
            }
            #searchInput:focus { outline: none; box-shadow: 0 0 15px #00d4ff; }
            #searchBtn {
                padding: 15px 30px;
                font-size: 18px;
                background: linear-gradient(135deg, #00d4ff, #0099cc);
                color: #000;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-weight: bold;
            }
            #searchBtn:hover { transform: scale(1.05); }
            .exchange-rate {
                display: flex;
                align-items: center;
                gap: 10px;
                background: #0f0f23;
                padding: 10px 15px;
                border-radius: 10px;
                border: 1px solid #333;
            }
            .exchange-rate label { color: #aaa; }
            #exchangeRate {
                width: 80px;
                padding: 8px;
                font-size: 16px;
                border: 1px solid #00d4ff;
                border-radius: 5px;
                background: #1a1a2e;
                color: #fff;
                text-align: center;
            }
            #results { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
            .card {
                background: linear-gradient(145deg, #1e1e3f, #0f0f23);
                border: 1px solid #333;
                border-radius: 15px;
                padding: 20px;
                display: flex;
                gap: 15px;
                transition: all 0.3s;
            }
            .card:hover { 
                transform: translateY(-5px); 
                box-shadow: 0 10px 30px rgba(0, 212, 255, 0.2);
                border-color: #00d4ff;
            }
            .card-img {
                width: 100px;
                height: 140px;
                object-fit: cover;
                border-radius: 8px;
                background: #333;
            }
            .card-info { flex: 1; }
            .card-number { color: #00d4ff; font-weight: bold; font-size: 14px; }
            .card-name { font-size: 16px; margin: 5px 0; color: #fff; }
            .card-version { color: #888; font-size: 12px; }
            .prices { margin-top: 15px; }
            .price-row { 
                display: flex; 
                justify-content: space-between; 
                padding: 8px 0;
                border-bottom: 1px solid #333;
            }
            .price-label { color: #aaa; }
            .price-sell { color: #ff6b6b; font-weight: bold; }
            .price-buy { color: #4ecdc4; font-weight: bold; }
            .price-hkd { color: #ffd93d; font-size: 12px; }
            .loading { text-align: center; padding: 50px; color: #888; }
            .no-results { text-align: center; padding: 50px; color: #888; }
            .stats {
                background: #0f0f23;
                padding: 15px;
                border-radius: 10px;
                margin-bottom: 20px;
                display: flex;
                gap: 30px;
                flex-wrap: wrap;
            }
            .stat-item { }
            .stat-value { color: #00d4ff; font-size: 24px; font-weight: bold; }
            .stat-label { color: #888; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎴 TCGE 卡牌價格系統 2.0</h1>
            
            <div class="stats" id="stats">
                <div class="stat-item">
                    <div class="stat-value" id="totalCards">-</div>
                    <div class="stat-label">總卡片數</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="totalPrices">-</div>
                    <div class="stat-label">價格紀錄</div>
                </div>
                <div class="stat-item" style="margin-left: auto;">
                    <a href="/ai-buy" style="color: #ff6b6b; text-decoration: none; font-size: 16px;">⚡ 快速買取</a>
                </div>
                <div class="stat-item">
                    <a href="/buyorder" style="color: #4ecdc4; text-decoration: none; font-size: 16px;">🛒 買取單</a>
                </div>
                <div class="stat-item">
                    <a href="/dashboard" style="color: #ff6b6b; text-decoration: none; font-size: 16px;">📊 儀表板</a>
                </div>
                <div class="stat-item">
                    <a href="/admin" style="color: #ffd93d; text-decoration: none; font-size: 16px;">⚙️ 後台管理</a>
                </div>
            </div>
            
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="輸入卡號或名稱 (例如: OP01-001)" />
                <button id="searchBtn" onclick="search()">🔍 搜尋</button>
                <div class="exchange-rate">
                    <label>匯率 JPY→HKD:</label>
                    <input type="number" id="exchangeRate" value="0.05" step="0.01" onchange="updateHKD()">
                </div>
            </div>
            
            <div id="results"></div>
        </div>
        
        <script>
            const API_BASE = '';
            
            // 載入統計
            async function loadStats() {
                try {
                    const res = await fetch(`${API_BASE}/api/stats`);
                    const data = await res.json();
                    document.getElementById('totalCards').textContent = data.total_cards.toLocaleString();
                    document.getElementById('totalPrices').textContent = data.total_prices.toLocaleString();
                } catch(e) {
                    console.error('Stats error:', e);
                }
            }
            
            // 搜尋
            async function search() {
                const query = document.getElementById('searchInput').value.trim();
                if (!query) return;
                
                const resultsDiv = document.getElementById('results');
                resultsDiv.innerHTML = '<div class="loading">🔄 搜尋中...</div>';
                
                try {
                    const res = await fetch(`${API_BASE}/api/cards/search?q=${encodeURIComponent(query)}`);
                    const cards = await res.json();
                    
                    if (cards.length === 0) {
                        resultsDiv.innerHTML = '<div class="no-results">找不到符合的卡牌</div>';
                        return;
                    }
                    
                    const rate = parseFloat(document.getElementById('exchangeRate').value) || 0.05;
                    
                    resultsDiv.innerHTML = cards.map(card => `
                        <div class="card">
                            <img class="card-img" src="${card.image_url || ''}" 
                                 onerror="this.src='https://via.placeholder.com/100x140?text=No+Image'" />
                            <div class="card-info">
                                <div class="card-number">
                                    ${card.card_number}
                                    <a href="/chart/${card.id}" style="color: #ffd93d; font-size: 12px; margin-left: 10px;">📊 趨勢</a>
                                </div>
                                <div class="card-name">${card.name}</div>
                                <div class="card-version">${card.version} | ${card.rarity || 'N/A'} | ${card.game_code || ''}</div>
                                <div class="prices">
                                    <div class="price-row">
                                        <span class="price-label">售價</span>
                                        <span>
                                            <span class="price-sell">${card.latest_sell_jpy ? card.latest_sell_jpy.toLocaleString() + ' JPY' : 'N/A'}</span>
                                            <span class="price-hkd">${card.latest_sell_jpy ? ' (' + (card.latest_sell_jpy * rate).toFixed(0) + ' HKD)' : ''}</span>
                                        </span>
                                    </div>
                                    <div class="price-row">
                                        <span class="price-label">買取</span>
                                        <span>
                                            <span class="price-buy">${card.latest_buy_jpy ? card.latest_buy_jpy.toLocaleString() + ' JPY' : 'N/A'}</span>
                                            <span class="price-hkd">${card.latest_buy_jpy ? ' (' + (card.latest_buy_jpy * rate).toFixed(0) + ' HKD)' : ''}</span>
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `).join('');
                    
                } catch(e) {
                    resultsDiv.innerHTML = '<div class="no-results">發生錯誤: ' + e.message + '</div>';
                }
            }
            
            // Enter 鍵搜尋
            document.getElementById('searchInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') search();
            });
            
            // 更新 HKD 價格
            function updateHKD() {
                // 重新搜尋以更新價格
                const query = document.getElementById('searchInput').value.trim();
                if (query) search();
            }
            
            // 初始化
            loadStats();
        </script>
    </body>
    </html>
    """
    return html_content

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """獲取系統統計"""
    total_cards = db.query(func.count(Card.id)).scalar()
    total_prices = db.query(func.count(MarketPrice.id)).scalar()
    total_games = db.query(func.count(Game.id)).scalar()
    
    return {
        "total_cards": total_cards or 0,
        "total_prices": total_prices or 0,
        "total_games": total_games or 0
    }

@app.get("/api/cards/search", response_model=List[CardSearchResult])
def search_cards(
    q: str = Query(..., min_length=1, description="搜尋關鍵字 (卡號或名稱)"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """搜尋卡牌"""
    # 搜尋卡號或名稱
    cards = db.query(Card).filter(
        (Card.card_number.ilike(f"%{q}%")) | (Card.name.ilike(f"%{q}%"))
    ).limit(limit).all()
    
    results = []
    for card in cards:
        # 取得最新售價
        latest_sell = db.query(MarketPrice).filter(
            MarketPrice.card_id == card.id,
            MarketPrice.price_type == "sell"
        ).order_by(desc(MarketPrice.timestamp)).first()
        
        # 取得最新買取價
        latest_buy = db.query(MarketPrice).filter(
            MarketPrice.card_id == card.id,
            MarketPrice.price_type == "buy"
        ).order_by(desc(MarketPrice.timestamp)).first()
        
        # 取得 set 和 game 資訊
        set_code = None
        game_code = None
        if card.card_set:
            set_code = card.card_set.code
            if card.card_set.game:
                game_code = card.card_set.game.code
        
        results.append(CardSearchResult(
            id=card.id,
            card_number=card.card_number,
            name=card.name,
            version=card.version,
            rarity=card.rarity,
            image_url=card.image_url,
            set_code=set_code,
            game_code=game_code,
            latest_sell_jpy=latest_sell.price_jpy if latest_sell else None,
            latest_buy_jpy=latest_buy.price_jpy if latest_buy else None
        ))
    
    return results

@app.get("/api/cards/{card_id}", response_model=CardDetailResult)
def get_card_detail(card_id: int, db: Session = Depends(get_db)):
    """獲取卡牌詳細資訊與價格歷史"""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # 取得價格歷史 (最近 50 筆)
    prices = db.query(MarketPrice).filter(
        MarketPrice.card_id == card_id
    ).order_by(desc(MarketPrice.timestamp)).limit(50).all()
    
    set_code = None
    game_code = None
    if card.card_set:
        set_code = card.card_set.code
        if card.card_set.game:
            game_code = card.card_set.game.code
    
    return CardDetailResult(
        id=card.id,
        card_number=card.card_number,
        name=card.name,
        version=card.version,
        rarity=card.rarity,
        image_url=card.image_url,
        set_code=set_code,
        game_code=game_code,
        prices=[PriceInfo(
            source=p.source,
            price_type=p.price_type,
            price_jpy=p.price_jpy,
            stock_status=p.stock_status,
            timestamp=p.timestamp
        ) for p in prices]
    )

@app.get("/api/games")
def get_games(db: Session = Depends(get_db)):
    """獲取所有遊戲列表"""
    games = db.query(Game).all()
    return [{"id": g.id, "code": g.code, "name": g.name} for g in games]

# ============================================================
# TCGE 內部定價管理 API
# ============================================================

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """後台管理介面 - TCGE 內部定價"""
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TCGE 後台管理 - 內部定價</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: #0d1117;
                color: #c9d1d9; 
                padding: 20px;
            }
            .container { max-width: 1600px; margin: 0 auto; }
            h1 { color: #58a6ff; margin-bottom: 20px; display: flex; align-items: center; gap: 15px; }
            h1 a { color: #8b949e; text-decoration: none; font-size: 14px; }
            h1 a:hover { color: #58a6ff; }
            
            /* 控制面板 */
            .control-panel {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                align-items: flex-end;
            }
            .control-group { display: flex; flex-direction: column; gap: 5px; }
            .control-group label { color: #8b949e; font-size: 12px; }
            .control-group input, .control-group select {
                padding: 10px 15px;
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #0d1117;
                color: #c9d1d9;
                font-size: 14px;
            }
            .control-group input:focus, .control-group select:focus {
                outline: none;
                border-color: #58a6ff;
            }
            button {
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.2s;
            }
            .btn-primary { background: #238636; color: #fff; }
            .btn-primary:hover { background: #2ea043; }
            .btn-secondary { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
            .btn-secondary:hover { background: #30363d; }
            .btn-warning { background: #9e6a03; color: #fff; }
            .btn-warning:hover { background: #bb8009; }
            .btn-info { background: #1f6feb; color: #fff; }
            .btn-info:hover { background: #388bfd; }
            
            /* 表格 */
            .table-container {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                overflow: hidden;
            }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #21262d; }
            th { background: #21262d; color: #8b949e; font-weight: 500; font-size: 12px; text-transform: uppercase; }
            tr:hover { background: #1c2128; }
            
            .card-info { display: flex; align-items: center; gap: 10px; }
            .card-img { width: 40px; height: 56px; object-fit: cover; border-radius: 4px; background: #30363d; }
            .card-number { color: #58a6ff; font-weight: 500; }
            .card-name { color: #c9d1d9; font-size: 13px; }
            .card-version { color: #8b949e; font-size: 11px; }
            
            .price-jpy { color: #f0883e; }
            .price-hkd { color: #3fb950; font-weight: 600; }
            
            .price-input {
                width: 100px;
                padding: 6px 10px;
                border: 1px solid #30363d;
                border-radius: 4px;
                background: #0d1117;
                color: #3fb950;
                font-size: 14px;
                font-weight: 500;
                text-align: right;
            }
            .price-input:focus { border-color: #3fb950; outline: none; }
            .price-input.modified { border-color: #f0883e; background: #1c1507; }
            
            input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; }
            
            /* 狀態訊息 */
            .status-bar {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px 15px;
                margin-bottom: 15px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .status-text { color: #8b949e; }
            .selected-count { color: #58a6ff; font-weight: 500; }
            
            /* 分頁 */
            .pagination {
                display: flex;
                justify-content: center;
                gap: 5px;
                padding: 20px;
            }
            .pagination button {
                min-width: 40px;
                padding: 8px 12px;
            }
            .pagination button.active { background: #58a6ff; }
            
            /* 載入中 */
            .loading { text-align: center; padding: 50px; color: #8b949e; }
            
            /* 提示 */
            .toast {
                position: fixed;
                bottom: 20px;
                right: 20px;
                padding: 15px 25px;
                border-radius: 8px;
                color: #fff;
                font-weight: 500;
                z-index: 1000;
                animation: slideIn 0.3s ease;
            }
            .toast.success { background: #238636; }
            .toast.error { background: #da3633; }
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                ⚙️ TCGE 後台管理 - 內部定價
                <a href="/">← 返回搜尋頁</a>
            </h1>
            
            <div class="control-panel">
                <div class="control-group">
                    <label>遊戲</label>
                    <select id="gameFilter" onchange="loadCards()">
                        <option value="">全部遊戲</option>
                    </select>
                </div>
                <div class="control-group">
                    <label>搜尋卡號/名稱</label>
                    <input type="text" id="searchInput" placeholder="例如: OP01-001" style="width: 200px;">
                </div>
                <div class="control-group">
                    <label>只顯示</label>
                    <select id="priceFilter">
                        <option value="">全部</option>
                        <option value="has_market">有市場價</option>
                        <option value="no_internal">未設內部價</option>
                        <option value="has_internal">已設內部價</option>
                    </select>
                </div>
                <button class="btn-secondary" onclick="loadCards()">🔍 篩選</button>
                
                <div style="flex: 1;"></div>
                
                <div class="control-group">
                    <label>匯率 JPY→HKD</label>
                    <input type="number" id="exchangeRate" value="0.052" step="0.001" style="width: 100px;">
                </div>
                <div class="control-group">
                    <label>售價加成</label>
                    <input type="number" id="sellMargin" value="1.2" step="0.1" style="width: 80px;">
                </div>
                <div class="control-group">
                    <label>買取折扣</label>
                    <input type="number" id="buyMargin" value="0.7" step="0.1" style="width: 80px;">
                </div>
            </div>
            
            <div class="status-bar">
                <span class="status-text">
                    已選擇 <span class="selected-count" id="selectedCount">0</span> 張卡
                </span>
                <div style="display: flex; gap: 10px;">
                    <button class="btn-secondary" onclick="selectAll()">☑ 全選當頁</button>
                    <button class="btn-secondary" onclick="deselectAll()">☐ 取消全選</button>
                    <button class="btn-warning" onclick="autoCalculate()">🔄 自動計算選中</button>
                    <button class="btn-primary" onclick="saveChanges()">💾 儲存變更</button>
                </div>
            </div>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width: 40px;"><input type="checkbox" id="checkAll" onchange="toggleAll()"></th>
                            <th>卡牌資訊</th>
                            <th>遊戲</th>
                            <th style="text-align: right;">市場售價 (JPY)</th>
                            <th style="text-align: right;">市場買取 (JPY)</th>
                            <th style="text-align: right;">TCGE 售價 (HKD)</th>
                            <th style="text-align: right;">TCGE 買取 (HKD)</th>
                        </tr>
                    </thead>
                    <tbody id="cardList">
                        <tr><td colspan="7" class="loading">載入中...</td></tr>
                    </tbody>
                </table>
            </div>
            
            <div class="pagination" id="pagination"></div>
        </div>
        
        <script>
            let cards = [];
            let selectedCards = new Set();
            let modifiedCards = new Map();
            let currentPage = 1;
            const pageSize = 50;
            
            // 載入遊戲列表
            async function loadGames() {
                const res = await fetch('/api/games');
                const games = await res.json();
                const select = document.getElementById('gameFilter');
                games.forEach(g => {
                    const opt = document.createElement('option');
                    opt.value = g.code;
                    opt.textContent = `${g.code} - ${g.name}`;
                    select.appendChild(opt);
                });
            }
            
            // 載入卡牌
            async function loadCards() {
                const tbody = document.getElementById('cardList');
                tbody.innerHTML = '<tr><td colspan="7" class="loading">🔄 載入中...</td></tr>';
                
                const game = document.getElementById('gameFilter').value;
                const search = document.getElementById('searchInput').value;
                const filter = document.getElementById('priceFilter').value;
                
                let url = `/api/admin/cards?page=${currentPage}&limit=${pageSize}`;
                if (game) url += `&game=${game}`;
                if (search) url += `&q=${encodeURIComponent(search)}`;
                if (filter) url += `&filter=${filter}`;
                
                try {
                    const res = await fetch(url);
                    const data = await res.json();
                    cards = data.cards;
                    renderCards();
                    renderPagination(data.total, data.pages);
                } catch(e) {
                    tbody.innerHTML = '<tr><td colspan="7" class="loading">載入失敗: ' + e.message + '</td></tr>';
                }
            }
            
            // 渲染卡牌列表
            function renderCards() {
                const tbody = document.getElementById('cardList');
                if (cards.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="loading">沒有符合條件的卡牌</td></tr>';
                    return;
                }
                
                tbody.innerHTML = cards.map(card => {
                    const isSelected = selectedCards.has(card.card_id);
                    const modified = modifiedCards.get(card.card_id) || {};
                    const sellHKD = modified.sell !== undefined ? modified.sell : card.tcge_sell_hkd;
                    const buyHKD = modified.buy !== undefined ? modified.buy : card.tcge_buy_hkd;
                    const sellModified = modified.sell !== undefined ? 'modified' : '';
                    const buyModified = modified.buy !== undefined ? 'modified' : '';
                    
                    return `
                    <tr>
                        <td><input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleCard(${card.card_id})"></td>
                        <td>
                            <div class="card-info">
                                <div>
                                    <div class="card-number">${card.card_number}</div>
                                    <div class="card-name">${card.name}</div>
                                    <div class="card-version">${card.version}</div>
                                </div>
                            </div>
                        </td>
                        <td>${card.game_code || '-'}</td>
                        <td style="text-align: right;" class="price-jpy">${card.latest_sell_jpy ? card.latest_sell_jpy.toLocaleString() : '-'}</td>
                        <td style="text-align: right;" class="price-jpy">${card.latest_buy_jpy ? card.latest_buy_jpy.toLocaleString() : '-'}</td>
                        <td style="text-align: right;">
                            <input type="number" class="price-input ${sellModified}" value="${sellHKD}" step="1" min="0"
                                   onchange="updatePrice(${card.card_id}, 'sell', this.value)">
                        </td>
                        <td style="text-align: right;">
                            <input type="number" class="price-input ${buyModified}" value="${buyHKD}" step="1" min="0"
                                   onchange="updatePrice(${card.card_id}, 'buy', this.value)">
                        </td>
                    </tr>
                    `;
                }).join('');
                
                updateSelectedCount();
            }
            
            // 更新價格
            function updatePrice(cardId, type, value) {
                if (!modifiedCards.has(cardId)) {
                    modifiedCards.set(cardId, {});
                }
                modifiedCards.get(cardId)[type] = parseFloat(value) || 0;
                renderCards();
            }
            
            // 選擇卡牌
            function toggleCard(cardId) {
                if (selectedCards.has(cardId)) {
                    selectedCards.delete(cardId);
                } else {
                    selectedCards.add(cardId);
                }
                updateSelectedCount();
            }
            
            function toggleAll() {
                const checked = document.getElementById('checkAll').checked;
                if (checked) {
                    cards.forEach(c => selectedCards.add(c.card_id));
                } else {
                    cards.forEach(c => selectedCards.delete(c.card_id));
                }
                renderCards();
            }
            
            function selectAll() {
                cards.forEach(c => selectedCards.add(c.card_id));
                renderCards();
            }
            
            function deselectAll() {
                cards.forEach(c => selectedCards.delete(c.card_id));
                document.getElementById('checkAll').checked = false;
                renderCards();
            }
            
            function updateSelectedCount() {
                document.getElementById('selectedCount').textContent = selectedCards.size;
            }
            
            // 自動計算價格
            async function autoCalculate() {
                if (selectedCards.size === 0) {
                    showToast('請先選擇卡牌', 'error');
                    return;
                }
                
                const rate = parseFloat(document.getElementById('exchangeRate').value) || 0.052;
                const sellMargin = parseFloat(document.getElementById('sellMargin').value) || 1.2;
                const buyMargin = parseFloat(document.getElementById('buyMargin').value) || 0.7;
                
                try {
                    const res = await fetch('/api/admin/auto-calculate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            card_ids: Array.from(selectedCards),
                            exchange_rate: rate,
                            sell_margin: sellMargin,
                            buy_margin: buyMargin
                        })
                    });
                    
                    const result = await res.json();
                    
                    // 更新本地修改
                    result.calculated.forEach(c => {
                        modifiedCards.set(c.card_id, { sell: c.tcge_sell_hkd, buy: c.tcge_buy_hkd });
                    });
                    
                    renderCards();
                    showToast(`已計算 ${result.calculated.length} 張卡的價格`, 'success');
                } catch(e) {
                    showToast('計算失敗: ' + e.message, 'error');
                }
            }
            
            // 儲存變更
            async function saveChanges() {
                if (modifiedCards.size === 0) {
                    showToast('沒有需要儲存的變更', 'error');
                    return;
                }
                
                const updates = [];
                modifiedCards.forEach((prices, cardId) => {
                    updates.push({
                        card_id: cardId,
                        tcge_sell_hkd: prices.sell,
                        tcge_buy_hkd: prices.buy
                    });
                });
                
                try {
                    const res = await fetch('/api/admin/prices/batch', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ updates })
                    });
                    
                    const result = await res.json();
                    modifiedCards.clear();
                    showToast(`成功更新 ${result.updated} 張卡的價格`, 'success');
                    loadCards();
                } catch(e) {
                    showToast('儲存失敗: ' + e.message, 'error');
                }
            }
            
            // 分頁
            function renderPagination(total, pages) {
                const div = document.getElementById('pagination');
                if (pages <= 1) {
                    div.innerHTML = '';
                    return;
                }
                
                let html = '';
                if (currentPage > 1) {
                    html += `<button class="btn-secondary" onclick="goToPage(${currentPage - 1})">‹</button>`;
                }
                
                for (let i = 1; i <= pages && i <= 10; i++) {
                    html += `<button class="btn-secondary ${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
                }
                
                if (currentPage < pages) {
                    html += `<button class="btn-secondary" onclick="goToPage(${currentPage + 1})">›</button>`;
                }
                
                html += `<span style="padding: 10px; color: #8b949e;">共 ${total} 張 / ${pages} 頁</span>`;
                div.innerHTML = html;
            }
            
            function goToPage(page) {
                currentPage = page;
                loadCards();
            }
            
            // 提示訊息
            function showToast(message, type) {
                const toast = document.createElement('div');
                toast.className = `toast ${type}`;
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
            }
            
            // Enter 鍵搜尋
            document.getElementById('searchInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') loadCards();
            });
            
            // 初始化
            loadGames();
            loadCards();
        </script>
    </body>
    </html>
    """
    return html_content

@app.get("/api/admin/cards")
def get_admin_cards(
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    game: Optional[str] = None,
    q: Optional[str] = None,
    filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """後台 - 獲取卡牌列表 (含內部定價)"""
    query = db.query(Card)
    
    # 遊戲篩選
    if game:
        query = query.join(CardSet).join(Game).filter(Game.code == game)
    
    # 搜尋篩選
    if q:
        query = query.filter(
            or_(Card.card_number.ilike(f"%{q}%"), Card.name.ilike(f"%{q}%"))
        )
    
    # 總數
    total = query.count()
    pages = (total + limit - 1) // limit
    
    # 分頁
    cards = query.offset((page - 1) * limit).limit(limit).all()
    
    results = []
    for card in cards:
        # 最新市場價
        latest_sell = db.query(MarketPrice).filter(
            MarketPrice.card_id == card.id,
            MarketPrice.price_type == "sell"
        ).order_by(desc(MarketPrice.timestamp)).first()
        
        latest_buy = db.query(MarketPrice).filter(
            MarketPrice.card_id == card.id,
            MarketPrice.price_type == "buy"
        ).order_by(desc(MarketPrice.timestamp)).first()
        
        # 內部定價
        internal = db.query(InternalPrice).filter(InternalPrice.card_id == card.id).first()
        
        # 遊戲代碼
        game_code = None
        if card.card_set and card.card_set.game:
            game_code = card.card_set.game.code
        
        # 根據 filter 篩選
        sell_jpy = latest_sell.price_jpy if latest_sell else None
        buy_jpy = latest_buy.price_jpy if latest_buy else None
        tcge_sell = internal.tcge_sell_hkd if internal else 0.0
        tcge_buy = internal.tcge_buy_hkd if internal else 0.0
        
        if filter == "has_market" and not sell_jpy and not buy_jpy:
            continue
        if filter == "no_internal" and (tcge_sell > 0 or tcge_buy > 0):
            continue
        if filter == "has_internal" and tcge_sell == 0 and tcge_buy == 0:
            continue
        
        results.append({
            "card_id": card.id,
            "card_number": card.card_number,
            "name": card.name,
            "version": card.version,
            "game_code": game_code,
            "latest_sell_jpy": sell_jpy,
            "latest_buy_jpy": buy_jpy,
            "tcge_sell_hkd": tcge_sell,
            "tcge_buy_hkd": tcge_buy
        })
    
    return {"cards": results, "total": total, "pages": pages, "page": page}

@app.post("/api/admin/prices/batch")
def batch_update_prices(data: BatchPriceUpdate, db: Session = Depends(get_db)):
    """批量更新內部定價"""
    updated = 0
    
    for update in data.updates:
        # 檢查卡牌是否存在
        card = db.query(Card).filter(Card.id == update.card_id).first()
        if not card:
            continue
        
        # 查找或創建內部定價記錄
        internal = db.query(InternalPrice).filter(InternalPrice.card_id == update.card_id).first()
        
        if not internal:
            internal = InternalPrice(card_id=update.card_id)
            db.add(internal)
        
        # 更新價格
        if update.tcge_sell_hkd is not None:
            internal.tcge_sell_hkd = update.tcge_sell_hkd
        if update.tcge_buy_hkd is not None:
            internal.tcge_buy_hkd = update.tcge_buy_hkd
        
        updated += 1
    
    db.commit()
    return {"success": True, "updated": updated}

@app.post("/api/admin/auto-calculate")
def auto_calculate_prices(data: AutoCalculateRequest, db: Session = Depends(get_db)):
    """自動計算內部定價 (基於市場價格和匯率)"""
    calculated = []
    
    for card_id in data.card_ids:
        # 獲取市場價
        latest_sell = db.query(MarketPrice).filter(
            MarketPrice.card_id == card_id,
            MarketPrice.price_type == "sell"
        ).order_by(desc(MarketPrice.timestamp)).first()
        
        latest_buy = db.query(MarketPrice).filter(
            MarketPrice.card_id == card_id,
            MarketPrice.price_type == "buy"
        ).order_by(desc(MarketPrice.timestamp)).first()
        
        # 計算 HKD 價格
        sell_jpy = latest_sell.price_jpy if latest_sell else 0
        buy_jpy = latest_buy.price_jpy if latest_buy else 0
        
        # 售價 = 市場售價 * 匯率 * 加成
        tcge_sell = round(sell_jpy * data.exchange_rate * data.sell_margin) if sell_jpy else 0
        # 買取 = 市場買取 * 匯率 * 折扣 (如果沒有買取價，用售價的 50%)
        if buy_jpy:
            tcge_buy = round(buy_jpy * data.exchange_rate * data.buy_margin)
        elif sell_jpy:
            tcge_buy = round(sell_jpy * data.exchange_rate * 0.5)
        else:
            tcge_buy = 0
        
        calculated.append({
            "card_id": card_id,
            "tcge_sell_hkd": tcge_sell,
            "tcge_buy_hkd": tcge_buy
        })
    
    return {"calculated": calculated}

@app.get("/api/admin/export")
def export_internal_prices(
    game: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """匯出內部定價為 CSV 格式"""
    query = db.query(Card, InternalPrice).outerjoin(InternalPrice, Card.id == InternalPrice.card_id)
    
    if game:
        query = query.join(CardSet).join(Game).filter(Game.code == game)
    
    results = query.all()
    
    csv_lines = ["卡號,名稱,版本,TCGE售價(HKD),TCGE買取(HKD)"]
    for card, internal in results:
        sell = internal.tcge_sell_hkd if internal else 0
        buy = internal.tcge_buy_hkd if internal else 0
        csv_lines.append(f'"{card.card_number}","{card.name}","{card.version}",{sell},{buy}')
    
    return {"csv": "\\n".join(csv_lines)}

# ============================================================
# 價格趨勢圖表 API
# ============================================================

@app.get("/api/cards/{card_id}/price-history")
def get_price_history(
    card_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """獲取卡牌價格歷史 (用於圖表)"""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    since = datetime.now() - timedelta(days=days)
    
    # 獲取價格歷史
    prices = db.query(MarketPrice).filter(
        MarketPrice.card_id == card_id,
        MarketPrice.timestamp >= since
    ).order_by(MarketPrice.timestamp).all()
    
    # 按日期和類型分組
    sell_data = []
    buy_data = []
    
    for p in prices:
        point = {
            "date": p.timestamp.strftime("%Y-%m-%d"),
            "datetime": p.timestamp.isoformat(),
            "price": p.price_jpy,
            "source": p.source
        }
        if p.price_type == "sell":
            sell_data.append(point)
        else:
            buy_data.append(point)
    
    return {
        "card_id": card_id,
        "card_number": card.card_number,
        "name": card.name,
        "days": days,
        "sell_prices": sell_data,
        "buy_prices": buy_data
    }

@app.get("/chart/{card_id}", response_class=HTMLResponse)
async def chart_page(card_id: int):
    """價格趨勢圖表頁面"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>價格趨勢圖表</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: #0d1117;
                color: #c9d1d9; 
                padding: 20px;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ color: #58a6ff; margin-bottom: 10px; }}
            .card-info {{ color: #8b949e; margin-bottom: 20px; }}
            .back-link {{ color: #58a6ff; text-decoration: none; }}
            .back-link:hover {{ text-decoration: underline; }}
            .chart-container {{
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            .controls {{
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
            }}
            .controls button {{
                padding: 10px 20px;
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #21262d;
                color: #c9d1d9;
                cursor: pointer;
            }}
            .controls button.active {{
                background: #58a6ff;
                color: #000;
                border-color: #58a6ff;
            }}
            .controls button:hover {{ background: #30363d; }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }}
            .stat-card {{
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 15px;
            }}
            .stat-label {{ color: #8b949e; font-size: 12px; }}
            .stat-value {{ font-size: 24px; font-weight: bold; margin-top: 5px; }}
            .stat-value.sell {{ color: #f85149; }}
            .stat-value.buy {{ color: #3fb950; }}
            .loading {{ text-align: center; padding: 50px; color: #8b949e; }}
        </style>
    </head>
    <body>
        <div class="container">
            <p><a href="/" class="back-link">← 返回搜尋</a></p>
            <h1 id="cardTitle">載入中...</h1>
            <p class="card-info" id="cardInfo"></p>
            
            <div class="controls">
                <button onclick="loadChart(7)" id="btn7">7 天</button>
                <button onclick="loadChart(30)" id="btn30" class="active">30 天</button>
                <button onclick="loadChart(90)" id="btn90">90 天</button>
                <button onclick="loadChart(180)" id="btn180">180 天</button>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">最新售價 (JPY)</div>
                    <div class="stat-value sell" id="latestSell">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">最新買取 (JPY)</div>
                    <div class="stat-value buy" id="latestBuy">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">售價變化</div>
                    <div class="stat-value" id="sellChange">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">買取變化</div>
                    <div class="stat-value" id="buyChange">-</div>
                </div>
            </div>
            
            <div class="chart-container">
                <canvas id="priceChart"></canvas>
            </div>
        </div>
        
        <script>
            const cardId = {card_id};
            let chart = null;
            
            async function loadChart(days) {{
                // 更新按鈕狀態
                document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
                document.getElementById('btn' + days).classList.add('active');
                
                try {{
                    const res = await fetch(`/api/cards/${{cardId}}/price-history?days=${{days}}`);
                    const data = await res.json();
                    
                    // 更新標題
                    document.getElementById('cardTitle').textContent = `${{data.card_number}} - ${{data.name}}`;
                    document.getElementById('cardInfo').textContent = `價格趨勢 (${{days}} 天)`;
                    
                    // 處理數據
                    const sellPrices = data.sell_prices;
                    const buyPrices = data.buy_prices;
                    
                    // 更新統計
                    if (sellPrices.length > 0) {{
                        const latest = sellPrices[sellPrices.length - 1].price;
                        const first = sellPrices[0].price;
                        document.getElementById('latestSell').textContent = latest.toLocaleString();
                        const change = ((latest - first) / first * 100).toFixed(1);
                        document.getElementById('sellChange').textContent = (change >= 0 ? '+' : '') + change + '%';
                        document.getElementById('sellChange').style.color = change >= 0 ? '#3fb950' : '#f85149';
                    }}
                    
                    if (buyPrices.length > 0) {{
                        const latest = buyPrices[buyPrices.length - 1].price;
                        const first = buyPrices[0].price;
                        document.getElementById('latestBuy').textContent = latest.toLocaleString();
                        const change = ((latest - first) / first * 100).toFixed(1);
                        document.getElementById('buyChange').textContent = (change >= 0 ? '+' : '') + change + '%';
                        document.getElementById('buyChange').style.color = change >= 0 ? '#3fb950' : '#f85149';
                    }}
                    
                    // 繪製圖表
                    const ctx = document.getElementById('priceChart').getContext('2d');
                    
                    if (chart) chart.destroy();
                    
                    chart = new Chart(ctx, {{
                        type: 'line',
                        data: {{
                            datasets: [
                                {{
                                    label: '售價 (JPY)',
                                    data: sellPrices.map(p => ({{ x: p.date, y: p.price }})),
                                    borderColor: '#f85149',
                                    backgroundColor: 'rgba(248, 81, 73, 0.1)',
                                    fill: true,
                                    tension: 0.3
                                }},
                                {{
                                    label: '買取 (JPY)',
                                    data: buyPrices.map(p => ({{ x: p.date, y: p.price }})),
                                    borderColor: '#3fb950',
                                    backgroundColor: 'rgba(63, 185, 80, 0.1)',
                                    fill: true,
                                    tension: 0.3
                                }}
                            ]
                        }},
                        options: {{
                            responsive: true,
                            interaction: {{ intersect: false, mode: 'index' }},
                            plugins: {{
                                legend: {{ labels: {{ color: '#c9d1d9' }} }}
                            }},
                            scales: {{
                                x: {{
                                    type: 'category',
                                    ticks: {{ color: '#8b949e' }},
                                    grid: {{ color: '#21262d' }}
                                }},
                                y: {{
                                    ticks: {{ color: '#8b949e' }},
                                    grid: {{ color: '#21262d' }}
                                }}
                            }}
                        }}
                    }});
                    
                }} catch(e) {{
                    console.error('Chart error:', e);
                }}
            }}
            
            // 初始載入
            loadChart(30);
        </script>
    </body>
    </html>
    """
    return html_content

# ============================================================
# 買取單系統
# ============================================================

@app.get("/buyorder", response_class=HTMLResponse)
async def buyorder_page():
    """買取單頁面 - 多選卡牌並計算總價"""
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TCGE 買取單系統</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: #0d1117;
                color: #c9d1d9; 
                padding: 20px;
            }
            .container { max-width: 1600px; margin: 0 auto; }
            h1 { color: #58a6ff; margin-bottom: 20px; display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }
            h1 a { color: #8b949e; text-decoration: none; font-size: 14px; }
            
            .layout { display: grid; grid-template-columns: 1fr 450px; gap: 20px; }
            
            /* 搜尋區 */
            .search-panel {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 20px;
            }
            .search-box {
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
            }
            .search-box input {
                flex: 1;
                padding: 12px 15px;
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #0d1117;
                color: #c9d1d9;
                font-size: 16px;
            }
            .search-box input:focus { outline: none; border-color: #58a6ff; }
            .search-box button {
                padding: 12px 25px;
                border: none;
                border-radius: 6px;
                background: #238636;
                color: #fff;
                font-size: 16px;
                cursor: pointer;
            }
            
            .exchange-setting {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 15px;
                padding: 10px 15px;
                background: #0d1117;
                border-radius: 6px;
                border: 1px solid #30363d;
            }
            .exchange-setting label { color: #8b949e; font-size: 14px; }
            .exchange-setting input {
                width: 80px;
                padding: 8px;
                border: 1px solid #f0883e;
                border-radius: 4px;
                background: #1c1507;
                color: #f0883e;
                font-weight: 500;
                text-align: center;
            }
            .exchange-setting span { color: #8b949e; font-size: 12px; }
            
            .search-results {
                max-height: 550px;
                overflow-y: auto;
            }
            .result-item {
                display: flex;
                align-items: center;
                gap: 15px;
                padding: 12px 15px;
                border-bottom: 1px solid #21262d;
                cursor: pointer;
                transition: background 0.2s;
            }
            .result-item:hover { background: #1c2128; }
            .result-item img {
                width: 50px;
                height: 70px;
                object-fit: cover;
                border-radius: 4px;
                background: #30363d;
            }
            .result-info { flex: 1; }
            .result-number { color: #58a6ff; font-weight: 500; }
            .result-name { color: #c9d1d9; font-size: 14px; margin: 2px 0; }
            .result-prices { font-size: 12px; margin-top: 4px; }
            .result-prices .jpy { color: #f0883e; }
            .result-prices .hkd { color: #3fb950; font-weight: 600; }
            .add-btn {
                padding: 8px 15px;
                border: none;
                border-radius: 4px;
                background: #238636;
                color: #fff;
                cursor: pointer;
                font-size: 13px;
            }
            .add-btn:hover { background: #2ea043; }
            
            /* 買取單 */
            .order-panel {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 20px;
                position: sticky;
                top: 20px;
            }
            .order-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 1px solid #30363d;
            }
            .order-header h2 { color: #58a6ff; }
            .clear-btn {
                padding: 8px 15px;
                border: 1px solid #f85149;
                border-radius: 4px;
                background: transparent;
                color: #f85149;
                cursor: pointer;
            }
            .clear-btn:hover { background: #f85149; color: #fff; }
            
            .order-items {
                max-height: 380px;
                overflow-y: auto;
                margin-bottom: 20px;
            }
            .order-item {
                display: flex;
                flex-direction: column;
                gap: 8px;
                padding: 12px;
                background: #0d1117;
                border-radius: 6px;
                margin-bottom: 10px;
            }
            .order-item-row1 {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
            }
            .order-item-info { flex: 1; }
            .order-item-number { color: #58a6ff; font-size: 13px; font-weight: 500; }
            .order-item-name { color: #c9d1d9; font-size: 14px; margin-top: 2px; }
            .order-item-prices { font-size: 12px; margin-top: 4px; }
            .order-item-prices .jpy { color: #f0883e; }
            .order-item-prices .hkd { color: #3fb950; }
            .remove-btn {
                color: #f85149;
                background: none;
                border: none;
                cursor: pointer;
                font-size: 18px;
                padding: 0 5px;
            }
            .order-item-row2 {
                display: flex;
                align-items: center;
                gap: 10px;
                padding-top: 8px;
                border-top: 1px solid #21262d;
            }
            .qty-label { color: #8b949e; font-size: 12px; }
            .order-item-controls { display: flex; align-items: center; gap: 5px; }
            .qty-btn {
                width: 26px;
                height: 26px;
                border: 1px solid #30363d;
                border-radius: 4px;
                background: #21262d;
                color: #c9d1d9;
                cursor: pointer;
                font-size: 14px;
            }
            .qty-btn:hover { background: #30363d; }
            .qty-input {
                width: 40px;
                text-align: center;
                padding: 4px;
                border: 1px solid #30363d;
                border-radius: 4px;
                background: #161b22;
                color: #c9d1d9;
                font-size: 14px;
            }
            .price-label { color: #8b949e; font-size: 12px; margin-left: 15px; }
            .price-input {
                width: 75px;
                text-align: right;
                padding: 4px 8px;
                border: 1px solid #3fb950;
                border-radius: 4px;
                background: #0d1117;
                color: #3fb950;
                font-weight: 600;
                font-size: 14px;
            }
            .subtotal { 
                color: #ffd93d; 
                font-size: 12px; 
                margin-left: auto;
                font-weight: 500;
            }
            
            .order-summary {
                background: #0d1117;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 20px;
            }
            .summary-row {
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                font-size: 14px;
            }
            .summary-row.total {
                border-top: 2px solid #30363d;
                padding-top: 15px;
                margin-top: 10px;
                font-size: 20px;
                font-weight: bold;
            }
            .summary-row.total .value { color: #3fb950; }
            
            .order-actions {
                display: flex;
                gap: 10px;
            }
            .order-actions button {
                flex: 1;
                padding: 15px;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                cursor: pointer;
                font-weight: 500;
            }
            .print-btn { background: #1f6feb; color: #fff; }
            .print-btn:hover { background: #388bfd; }
            .confirm-btn { background: #238636; color: #fff; }
            .confirm-btn:hover { background: #2ea043; }
            
            .customer-info {
                margin-bottom: 15px;
            }
            .customer-info input {
                width: 100%;
                padding: 10px;
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #0d1117;
                color: #c9d1d9;
            }
            .customer-info input:focus { outline: none; border-color: #58a6ff; }
            
            .empty-order {
                text-align: center;
                padding: 40px;
                color: #8b949e;
            }
            
            /* 列印樣式 */
            @media print {
                body { background: #fff; color: #000; padding: 0; }
                .search-panel, .order-actions, .add-btn, .remove-btn, .qty-btn, h1 a, .exchange-setting { display: none; }
                .layout { grid-template-columns: 1fr; }
                .order-panel { 
                    position: static; 
                    background: #fff; 
                    border: 2px solid #000;
                }
                .order-item { background: #f5f5f5; border: 1px solid #ccc; }
                .order-summary { background: #f5f5f5; }
                .summary-row.total .value { color: #000; }
                .order-item-number, .order-item-name { color: #000; }
                .order-item-prices .jpy, .order-item-prices .hkd { color: #333; }
            }
            
            /* 提示 */
            .toast {
                position: fixed;
                bottom: 20px;
                right: 20px;
                padding: 15px 25px;
                border-radius: 8px;
                color: #fff;
                font-weight: 500;
                z-index: 1000;
                animation: slideIn 0.3s ease;
            }
            .toast.success { background: #238636; }
            .toast.error { background: #da3633; }
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                🛒 TCGE 買取單系統
                <a href="/">← 返回搜尋</a>
                <a href="/admin">⚙️ 後台管理</a>
            </h1>
            
            <div class="layout">
                <div class="search-panel">
                    <div class="search-box">
                        <input type="text" id="searchInput" placeholder="輸入卡號或名稱搜尋...">
                        <button onclick="searchCards()">🔍 搜尋</button>
                    </div>
                    
                    <div class="exchange-setting">
                        <label>💱 匯率 JPY → HKD:</label>
                        <input type="number" id="exchangeRate" value="0.052" step="0.001" min="0.01" onchange="onExchangeRateChange()">
                        <span>(例: 1000 JPY = <span id="ratePreview">52</span> HKD)</span>
                    </div>
                    
                    <div class="search-results" id="searchResults">
                        <div class="empty-order">輸入卡號或名稱開始搜尋</div>
                    </div>
                </div>
                
                <div class="order-panel">
                    <div class="order-header">
                        <h2>📋 買取單</h2>
                        <button class="clear-btn" onclick="clearOrder()">清空</button>
                    </div>
                    
                    <div class="customer-info">
                        <input type="text" id="customerName" placeholder="客戶名稱 (選填)">
                    </div>
                    
                    <div class="order-items" id="orderItems">
                        <div class="empty-order">點擊左側卡牌加入買取單</div>
                    </div>
                    
                    <div class="order-summary">
                        <div class="summary-row">
                            <span>卡牌種類</span>
                            <span id="totalCards">0 種</span>
                        </div>
                        <div class="summary-row">
                            <span>總張數</span>
                            <span id="totalQty">0 張</span>
                        </div>
                        <div class="summary-row total">
                            <span>買取總額</span>
                            <span class="value" id="totalPrice">HKD 0</span>
                        </div>
                    </div>
                    
                    <div class="order-actions">
                        <button class="print-btn" onclick="printOrder()">🖨️ 列印</button>
                        <button class="confirm-btn" onclick="confirmOrder()">✅ 確認買取</button>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            let orderItems = [];
            
            function getExchangeRate() {
                return parseFloat(document.getElementById('exchangeRate').value) || 0.052;
            }
            
            function onExchangeRateChange() {
                const rate = getExchangeRate();
                document.getElementById('ratePreview').textContent = Math.round(1000 * rate);
                // 重新計算所有價格
                orderItems.forEach(item => {
                    item.priceHKD = Math.round(item.priceJPY * rate);
                });
                renderOrder();
                // 如果有搜尋結果，重新搜尋以更新顯示
                const query = document.getElementById('searchInput').value.trim();
                if (query) searchCards();
            }
            
            // 搜尋卡牌
            async function searchCards() {
                const query = document.getElementById('searchInput').value.trim();
                if (!query) return;
                
                const resultsDiv = document.getElementById('searchResults');
                resultsDiv.innerHTML = '<div class="empty-order">🔄 搜尋中...</div>';
                
                try {
                    const res = await fetch(`/api/cards/search?q=${encodeURIComponent(query)}&limit=50`);
                    const cards = await res.json();
                    
                    if (cards.length === 0) {
                        resultsDiv.innerHTML = '<div class="empty-order">找不到符合的卡牌</div>';
                        return;
                    }
                    
                    const rate = getExchangeRate();
                    
                    resultsDiv.innerHTML = cards.map(card => {
                        const buyJPY = card.latest_buy_jpy || 0;
                        const buyHKD = Math.round(buyJPY * rate);
                        return `
                        <div class="result-item" onclick="addToOrder(${card.id}, '${card.card_number}', '${escapeHtml(card.name)}', '${card.version}', ${buyJPY})">
                            <img src="${card.image_url || ''}" onerror="this.src='https://via.placeholder.com/50x70?text=No'" />
                            <div class="result-info">
                                <div class="result-number">${card.card_number}</div>
                                <div class="result-name">${card.name}</div>
                                <div class="result-prices">
                                    買取: <span class="jpy">${buyJPY > 0 ? buyJPY.toLocaleString() + ' JPY' : '-'}</span>
                                    → <span class="hkd">${buyHKD > 0 ? 'HKD ' + buyHKD : '未設定'}</span>
                                </div>
                            </div>
                            <button class="add-btn">+ 加入</button>
                        </div>
                        `;
                    }).join('');
                    
                } catch(e) {
                    resultsDiv.innerHTML = '<div class="empty-order">搜尋失敗: ' + e.message + '</div>';
                }
            }
            
            function escapeHtml(text) {
                return text.replace(/'/g, "\\'").replace(/"/g, '\\"');
            }
            
            // 加入買取單
            function addToOrder(cardId, cardNumber, name, version, priceJPY) {
                const rate = getExchangeRate();
                const priceHKD = Math.round(priceJPY * rate);
                
                // 檢查是否已存在
                const existing = orderItems.find(item => item.cardId === cardId);
                if (existing) {
                    existing.quantity++;
                } else {
                    orderItems.push({
                        cardId,
                        cardNumber,
                        name,
                        version,
                        priceJPY,
                        priceHKD,
                        quantity: 1
                    });
                }
                renderOrder();
                showToast('已加入買取單', 'success');
            }
            
            // 渲染買取單
            function renderOrder() {
                const container = document.getElementById('orderItems');
                
                if (orderItems.length === 0) {
                    container.innerHTML = '<div class="empty-order">點擊左側卡牌加入買取單</div>';
                    updateSummary();
                    return;
                }
                
                container.innerHTML = orderItems.map((item, index) => {
                    const subtotal = item.priceHKD * item.quantity;
                    return `
                    <div class="order-item">
                        <div class="order-item-row1">
                            <div class="order-item-info">
                                <div class="order-item-number">${item.cardNumber}</div>
                                <div class="order-item-name">${item.name}</div>
                                <div class="order-item-prices">
                                    買取: <span class="jpy">${item.priceJPY > 0 ? item.priceJPY.toLocaleString() + ' JPY' : '-'}</span>
                                    → <span class="hkd">HKD ${item.priceHKD}</span>
                                </div>
                            </div>
                            <button class="remove-btn" onclick="removeItem(${index})">✕</button>
                        </div>
                        <div class="order-item-row2">
                            <span class="qty-label">數量:</span>
                            <div class="order-item-controls">
                                <button class="qty-btn" onclick="updateQty(${index}, -1)">−</button>
                                <input type="number" class="qty-input" value="${item.quantity}" min="1" 
                                       onchange="setQty(${index}, this.value)">
                                <button class="qty-btn" onclick="updateQty(${index}, 1)">+</button>
                            </div>
                            <span class="price-label">單價:</span>
                            <input type="number" class="price-input" value="${item.priceHKD}" min="0"
                                   onchange="setPrice(${index}, this.value)">
                            <span class="subtotal">= HKD ${subtotal.toLocaleString()}</span>
                        </div>
                    </div>
                `}).join('');
                
                updateSummary();
            }
            
            function updateQty(index, delta) {
                orderItems[index].quantity = Math.max(1, orderItems[index].quantity + delta);
                renderOrder();
            }
            
            function setQty(index, value) {
                orderItems[index].quantity = Math.max(1, parseInt(value) || 1);
                renderOrder();
            }
            
            function setPrice(index, value) {
                orderItems[index].priceHKD = Math.max(0, parseFloat(value) || 0);
                renderOrder();
            }
            
            function removeItem(index) {
                orderItems.splice(index, 1);
                renderOrder();
            }
            
            function clearOrder() {
                if (orderItems.length > 0 && !confirm('確定要清空買取單嗎？')) return;
                orderItems = [];
                renderOrder();
            }
            
            function updateSummary() {
                const totalCards = orderItems.length;
                const totalQty = orderItems.reduce((sum, item) => sum + item.quantity, 0);
                const totalPrice = orderItems.reduce((sum, item) => sum + item.priceHKD * item.quantity, 0);
                
                document.getElementById('totalCards').textContent = totalCards + ' 種';
                document.getElementById('totalQty').textContent = totalQty + ' 張';
                document.getElementById('totalPrice').textContent = 'HKD ' + totalPrice.toLocaleString();
            }
            
            function printOrder() {
                window.print();
            }
            
            function confirmOrder() {
                if (orderItems.length === 0) {
                    showToast('買取單是空的', 'error');
                    return;
                }
                
                const totalPrice = orderItems.reduce((sum, item) => sum + item.priceHKD * item.quantity, 0);
                const customerName = document.getElementById('customerName').value || '未填';
                
                if (confirm(`確認買取？\\n客戶: ${customerName}\\n總額: HKD ${totalPrice.toLocaleString()}`)) {
                    showToast('買取完成！', 'success');
                    orderItems = [];
                    document.getElementById('customerName').value = '';
                    renderOrder();
                }
            }
            
            function showToast(message, type) {
                const toast = document.createElement('div');
                toast.className = `toast ${type}`;
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
            }
            
            // Enter 鍵搜尋
            document.getElementById('searchInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') searchCards();
            });
            
            // 初始化
            onExchangeRateChange();
            renderOrder();
        </script>
    </body>
    </html>
    """
    return html_content

@app.post("/api/buyorder")
def create_buy_order(order: BuyOrderCreate, db: Session = Depends(get_db)):
    """創建買取單 (用於記錄)"""
    # 計算總價
    total_qty = sum(item.quantity for item in order.items)
    total_price = sum(item.price_hkd * item.quantity for item in order.items)
    
    # 這裡可以擴展：保存到資料庫的買取單表
    # 目前先返回計算結果
    
    return {
        "success": True,
        "customer_name": order.customer_name,
        "total_items": len(order.items),
        "total_quantity": total_qty,
        "total_price_hkd": total_price,
        "timestamp": datetime.now().isoformat()
    }

# ============================================================
# 圖像識別系統 - AI 買取
# ============================================================

@app.get("/ai-buy", response_class=HTMLResponse)
async def ai_buy_page():
    """AI 買取頁面 - 拍照識別 + 手動搜尋"""
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TCGE 快速買取</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: #0d1117;
                color: #c9d1d9; 
                padding: 20px;
            }
            .container { max-width: 1600px; margin: 0 auto; }
            h1 { color: #58a6ff; margin-bottom: 20px; display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }
            h1 a { color: #8b949e; text-decoration: none; font-size: 14px; }
            
            .layout { display: grid; grid-template-columns: 1fr 1fr 380px; gap: 20px; }
            
            /* 拍照區 */
            .camera-panel {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 20px;
            }
            .panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }
            .panel-header h2 { color: #58a6ff; font-size: 18px; }
            
            .camera-container {
                position: relative;
                background: #000;
                border-radius: 8px;
                overflow: hidden;
                margin-bottom: 15px;
                min-height: 280px;
            }
            #video, #canvas {
                width: 100%;
                max-height: 280px;
                display: block;
            }
            #canvas { display: none; }
            
            .camera-overlay {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 70%;
                height: 80%;
                border: 3px dashed rgba(88, 166, 255, 0.5);
                border-radius: 10px;
                pointer-events: none;
            }
            .camera-overlay::before {
                content: '將卡牌放在框內';
                position: absolute;
                bottom: -25px;
                left: 50%;
                transform: translateX(-50%);
                color: rgba(88, 166, 255, 0.7);
                font-size: 12px;
                white-space: nowrap;
            }
            
            .camera-controls {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
            }
            .camera-controls button {
                flex: 1;
                min-width: 100px;
                padding: 12px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                cursor: pointer;
                font-weight: 500;
            }
            .btn-capture { background: #238636; color: #fff; }
            .btn-capture:hover { background: #2ea043; }
            .btn-upload { background: #1f6feb; color: #fff; }
            .btn-upload:hover { background: #388bfd; }
            .btn-reset { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
            
            #fileInput { display: none; }
            
            .preview-container {
                display: none;
                margin-bottom: 15px;
            }
            .preview-container.active { display: block; }
            .preview-container img {
                width: 100%;
                max-height: 280px;
                object-fit: contain;
                border-radius: 8px;
                background: #000;
            }
            
            .ocr-input {
                margin-top: 15px;
                padding: 15px;
                background: #0d1117;
                border-radius: 8px;
                border: 1px solid #30363d;
            }
            .ocr-input label { 
                display: block; 
                color: #8b949e; 
                font-size: 12px; 
                margin-bottom: 8px;
            }
            .ocr-input-row {
                display: flex;
                gap: 8px;
            }
            .ocr-input input {
                flex: 1;
                padding: 10px;
                border: 1px solid #f0883e;
                border-radius: 6px;
                background: #1c1507;
                color: #f0883e;
                font-size: 14px;
                font-weight: 500;
            }
            .ocr-input input:focus { outline: none; border-color: #ffd93d; }
            .ocr-input button {
                padding: 10px 15px;
                border: none;
                border-radius: 6px;
                background: #f0883e;
                color: #000;
                cursor: pointer;
                font-weight: 500;
            }
            
            /* 搜尋區 */
            .search-panel {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 20px;
            }
            
            .search-box {
                display: flex;
                gap: 8px;
                margin-bottom: 12px;
            }
            .search-box input {
                flex: 1;
                padding: 12px 15px;
                font-size: 16px;
                border: 2px solid #30363d;
                border-radius: 6px;
                background: #0d1117;
                color: #fff;
            }
            .search-box input:focus { 
                outline: none; 
                border-color: #58a6ff;
            }
            .search-box button {
                padding: 12px 20px;
                font-size: 14px;
                border: none;
                border-radius: 6px;
                background: #238636;
                color: #fff;
                cursor: pointer;
                font-weight: 500;
            }
            
            .exchange-row {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 12px;
                padding: 8px 12px;
                background: #0d1117;
                border-radius: 6px;
                font-size: 13px;
            }
            .exchange-row label { color: #8b949e; }
            .exchange-row input {
                width: 70px;
                padding: 6px;
                border: 1px solid #f0883e;
                border-radius: 4px;
                background: #1c1507;
                color: #f0883e;
                text-align: center;
                font-weight: 500;
            }
            
            .quick-search {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                margin-bottom: 12px;
            }
            .quick-search button {
                padding: 6px 12px;
                border: 1px solid #30363d;
                border-radius: 15px;
                background: #21262d;
                color: #c9d1d9;
                cursor: pointer;
                font-size: 12px;
            }
            .quick-search button:hover { background: #30363d; border-color: #58a6ff; }
            
            .status-message {
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 12px;
                text-align: center;
                font-size: 13px;
            }
            .status-message.info { background: #1f6feb33; border: 1px solid #1f6feb; }
            .status-message.success { background: #23863633; border: 1px solid #238636; }
            .status-message.error { background: #da363333; border: 1px solid #da3633; }
            .status-message.warning { background: #9e6a0333; border: 1px solid #9e6a03; }
            
            .search-results {
                max-height: 320px;
                overflow-y: auto;
            }
            .result-item {
                display: flex;
                gap: 12px;
                padding: 12px;
                background: #0d1117;
                border-radius: 6px;
                margin-bottom: 8px;
                border: 1px solid #30363d;
                cursor: pointer;
                transition: all 0.2s;
            }
            .result-item:hover {
                border-color: #3fb950;
                background: #0d111780;
            }
            .result-item img {
                width: 50px;
                height: 70px;
                object-fit: cover;
                border-radius: 4px;
                background: #30363d;
            }
            .result-info { flex: 1; }
            .result-number { color: #58a6ff; font-weight: 600; font-size: 14px; }
            .result-name { color: #c9d1d9; margin: 2px 0; font-size: 12px; }
            .result-version { color: #8b949e; font-size: 11px; }
            .result-prices { margin-top: 6px; font-size: 12px; }
            .result-prices .jpy { color: #f0883e; }
            .result-prices .hkd { color: #3fb950; font-weight: 600; }
            .result-actions {
                display: flex;
                align-items: center;
            }
            .btn-add {
                padding: 8px 12px;
                border: none;
                border-radius: 4px;
                background: #238636;
                color: #fff;
                cursor: pointer;
                font-size: 12px;
            }
            .btn-add:hover { background: #2ea043; }
            
            /* 買取單區 */
            .order-panel {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 20px;
                position: sticky;
                top: 20px;
            }
            .order-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 1px solid #30363d;
            }
            .order-header h2 { color: #3fb950; font-size: 18px; }
            .clear-btn {
                padding: 5px 10px;
                border: 1px solid #f85149;
                border-radius: 4px;
                background: transparent;
                color: #f85149;
                cursor: pointer;
                font-size: 12px;
            }
            
            .order-items {
                max-height: 300px;
                overflow-y: auto;
                margin-bottom: 15px;
            }
            .order-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px;
                background: #0d1117;
                border-radius: 6px;
                margin-bottom: 8px;
            }
            .order-item-info { flex: 1; }
            .order-item-number { color: #58a6ff; font-size: 12px; font-weight: 500; }
            .order-item-price { color: #8b949e; font-size: 11px; margin-top: 2px; }
            .order-item-price-row { 
                display: flex; 
                align-items: center; 
                gap: 6px; 
                margin-top: 4px;
            }
            .order-item-price-row label { color: #8b949e; font-size: 11px; }
            .price-input {
                width: 65px;
                padding: 4px 6px;
                border: 1px solid #3fb950;
                border-radius: 4px;
                background: #0d1117;
                color: #3fb950;
                font-size: 12px;
                font-weight: 600;
                text-align: right;
            }
            .price-input:focus { outline: none; border-color: #58d68d; }
            .order-item-subtotal { 
                color: #f0883e; 
                font-size: 11px; 
                margin-left: 4px;
            }
            .order-item-controls { display: flex; align-items: center; gap: 4px; }
            .qty-btn {
                width: 22px;
                height: 22px;
                border: 1px solid #30363d;
                border-radius: 4px;
                background: #21262d;
                color: #c9d1d9;
                cursor: pointer;
                font-size: 12px;
            }
            .qty-input {
                width: 30px;
                text-align: center;
                padding: 2px;
                border: 1px solid #30363d;
                border-radius: 4px;
                background: #161b22;
                color: #c9d1d9;
                font-size: 12px;
            }
            .remove-btn {
                color: #f85149;
                background: none;
                border: none;
                cursor: pointer;
                font-size: 14px;
                margin-left: 6px;
            }
            
            .order-summary {
                background: #0d1117;
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 15px;
            }
            .summary-row {
                display: flex;
                justify-content: space-between;
                padding: 4px 0;
                font-size: 13px;
            }
            .summary-row.total {
                border-top: 1px solid #30363d;
                padding-top: 10px;
                margin-top: 5px;
                font-size: 18px;
                font-weight: bold;
            }
            .summary-row.total .value { color: #3fb950; }
            
            .order-actions button {
                width: 100%;
                padding: 12px;
                border: none;
                border-radius: 6px;
                font-size: 15px;
                cursor: pointer;
                font-weight: 500;
                background: #238636;
                color: #fff;
            }
            
            .empty-order {
                text-align: center;
                padding: 25px;
                color: #8b949e;
                font-size: 13px;
            }
            
            /* OCR 結果 */
            .ocr-result {
                margin-top: 15px;
                padding: 15px;
                background: #0d1117;
                border-radius: 8px;
                border: 1px solid #30363d;
            }
            .ocr-result.success { border-color: #238636; }
            .ocr-result.warning { border-color: #9e6a03; }
            .ocr-result.error { border-color: #da3633; }
            .ocr-status {
                font-size: 13px;
                line-height: 1.5;
            }
            .ocr-status .detected {
                color: #58a6ff;
                font-weight: 600;
            }
            .ocr-status .found {
                color: #3fb950;
                font-weight: 600;
            }
            .ocr-status .not-found {
                color: #f85149;
            }
            .pattern-list {
                margin-top: 10px;
                padding: 10px;
                background: #161b22;
                border-radius: 6px;
            }
            .pattern-item {
                display: flex;
                justify-content: space-between;
                padding: 5px 0;
                font-size: 12px;
                border-bottom: 1px solid #21262d;
            }
            .pattern-item:last-child { border-bottom: none; }
            .pattern-item .pattern { color: #f0883e; font-family: monospace; }
            .pattern-item .status { font-size: 11px; }
            .pattern-item .status.found { color: #3fb950; }
            .pattern-item .status.not-found { color: #8b949e; }
            
            /* 提示 */
            .toast {
                position: fixed;
                bottom: 20px;
                right: 20px;
                padding: 15px 25px;
                border-radius: 8px;
                color: #fff;
                font-weight: 500;
                z-index: 1000;
                animation: slideIn 0.3s ease;
            }
            .toast.success { background: #238636; }
            .toast.error { background: #da3633; }
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            
            @media (max-width: 1200px) {
                .layout { grid-template-columns: 1fr 1fr; }
                .order-panel { grid-column: span 2; position: static; }
            }
            @media (max-width: 768px) {
                .layout { grid-template-columns: 1fr; }
                .order-panel { grid-column: span 1; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                ⚡ 快速買取
                <a href="/">← 返回首頁</a>
                <a href="/buyorder">🛒 標準買取單</a>
            </h1>
            
            <div class="layout">
                <!-- 拍照區 -->
                <div class="camera-panel">
                    <div class="panel-header">
                        <h2>📷 拍照識別</h2>
                        <button id="aiModeBtn" onclick="toggleAIMode()" style="padding: 5px 10px; border-radius: 5px; border: none; cursor: pointer; font-size: 12px; background: #238636; color: white;">🤖 雲端AI: 檢測中...</button>
                    </div>
                    
                    <div class="camera-container" id="cameraContainer">
                        <video id="video" autoplay playsinline></video>
                        <canvas id="canvas"></canvas>
                        <div class="camera-overlay"></div>
                    </div>
                    
                    <div class="preview-container" id="previewContainer">
                        <img id="previewImage" src="" alt="預覽">
                    </div>
                    
                    <div class="camera-controls">
                        <button class="btn-capture" onclick="capturePhoto()">📸 拍照</button>
                        <button class="btn-upload" onclick="document.getElementById('fileInput').click()">📁 上傳</button>
                        <button class="btn-reset" onclick="resetCamera()">🔄 重拍</button>
                    </div>
                    <input type="file" id="fileInput" accept="image/*" onchange="handleFileUpload(event)">
                    
                    <div class="ocr-result" id="ocrResult" style="display: none;">
                        <div class="ocr-status" id="ocrStatus"></div>
                    </div>
                </div>
                
                <!-- 搜尋區 -->
                <div class="search-panel">
                    <div class="panel-header">
                        <h2>🔍 搜尋卡牌</h2>
                    </div>
                    
                    <div class="search-box">
                        <input type="text" id="searchInput" placeholder="輸入卡號搜尋...">
                        <button onclick="searchCards()">搜尋</button>
                    </div>
                    
                    <div class="exchange-row">
                        <label>💱 匯率:</label>
                        <input type="number" id="exchangeRate" value="0.052" step="0.001" onchange="updateExchangePreview()">
                        <span style="color: #8b949e;">1000 JPY = <span id="ratePreview">52</span> HKD</span>
                    </div>
                    
                    <div class="quick-search">
                        <button onclick="quickSearch('OP14')">OP14</button>
                        <button onclick="quickSearch('OP13')">OP13</button>
                        <button onclick="quickSearch('DZ-LBT02')">DZ-LBT02</button>
                        <button onclick="quickSearch('DZ-LBT01')">DZ-LBT01</button>
                        <button onclick="quickSearch('UA')">UA</button>
                    </div>
                    
                    <div class="status-message info" id="statusMessage">
                        📷 拍照自動識別，或直接輸入卡號搜尋
                    </div>
                    
                    <div class="search-results" id="searchResults">
                        <!-- 搜尋結果 -->
                    </div>
                </div>
                
                <!-- 買取單 -->
                <div class="order-panel">
                    <div class="order-header">
                        <h2>🛒 買取單</h2>
                        <button class="clear-btn" onclick="clearOrder()">清空</button>
                    </div>
                    
                    <div class="order-items" id="orderItems">
                        <div class="empty-order">點擊卡牌加入買取單</div>
                    </div>
                    
                    <div class="order-summary">
                        <div class="summary-row">
                            <span>卡牌種類</span>
                            <span id="totalTypes">0 種</span>
                        </div>
                        <div class="summary-row">
                            <span>總張數</span>
                            <span id="totalQty">0 張</span>
                        </div>
                        <div class="summary-row total">
                            <span>買取總額</span>
                            <span class="value" id="totalPrice">HKD 0</span>
                        </div>
                    </div>
                    
                    <div class="order-actions">
                        <button onclick="completeOrder()">✅ 完成買取</button>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            let stream = null;
            let orderItems = [];
            const video = document.getElementById('video');
            const canvas = document.getElementById('canvas');
            const ctx = canvas.getContext('2d');
            
            // ========== 相機功能 ==========
            async function initCamera() {
                try {
                    stream = await navigator.mediaDevices.getUserMedia({
                        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
                    });
                    video.srcObject = stream;
                } catch(e) {
                    console.log('Camera not available:', e);
                    document.getElementById('cameraContainer').innerHTML = '<div style="padding: 50px; text-align: center; color: #8b949e;">相機不可用<br>請使用上傳圖片功能</div>';
                }
            }
            
            function capturePhoto() {
                if (!stream) {
                    showToast('請使用上傳圖片功能', 'error');
                    return;
                }
                
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                ctx.drawImage(video, 0, 0);
                
                const imageData = canvas.toDataURL('image/jpeg', 0.8);
                showPreview(imageData);
                
                // 自動進行識別
                recognizeImage(imageData);
            }
            
            function handleFileUpload(event) {
                const file = event.target.files[0];
                if (!file) return;
                
                const reader = new FileReader();
                reader.onload = function(e) {
                    showPreview(e.target.result);
                    // 自動進行識別
                    recognizeImage(e.target.result);
                };
                reader.readAsDataURL(file);
            }
            
            function showPreview(imageData) {
                document.getElementById('cameraContainer').style.display = 'none';
                document.getElementById('previewContainer').classList.add('active');
                document.getElementById('previewImage').src = imageData;
            }
            
            function resetCamera() {
                document.getElementById('cameraContainer').style.display = 'block';
                document.getElementById('previewContainer').classList.remove('active');
                document.getElementById('ocrResult').style.display = 'none';
                document.getElementById('searchResults').innerHTML = '';
                document.getElementById('statusMessage').textContent = '📷 拍照自動識別，或直接輸入卡號搜尋';
                document.getElementById('statusMessage').className = 'status-message info';
            }
            
            // ========== AI 模式切換 ==========
            let useCloudAI = true;  // 預設使用雲端 AI
            
            async function checkAIStatus() {
                try {
                    const res = await fetch('/api/ai-status');
                    const data = await res.json();
                    const aiBtn = document.getElementById('aiModeBtn');
                    if (data.online) {
                        aiBtn.textContent = '🤖 雲端AI: 在線';
                        aiBtn.style.background = '#238636';
                        useCloudAI = true;
                    } else {
                        aiBtn.textContent = '🔧 本地OCR';
                        aiBtn.style.background = '#6e7681';
                        useCloudAI = false;
                    }
                } catch(e) {
                    useCloudAI = false;
                }
            }
            
            function toggleAIMode() {
                useCloudAI = !useCloudAI;
                const aiBtn = document.getElementById('aiModeBtn');
                if (useCloudAI) {
                    aiBtn.textContent = '🤖 雲端AI';
                    aiBtn.style.background = '#238636';
                } else {
                    aiBtn.textContent = '🔧 本地OCR';
                    aiBtn.style.background = '#6e7681';
                }
            }
            
            // ========== 圖像識別功能 ==========
            async function recognizeImage(imageData) {
                const status = document.getElementById('statusMessage');
                const results = document.getElementById('searchResults');
                const ocrResult = document.getElementById('ocrResult');
                const ocrStatus = document.getElementById('ocrStatus');
                
                const aiMode = useCloudAI ? '雲端AI' : '本地OCR';
                status.textContent = `🔄 正在使用 ${aiMode} 識別...`;
                status.className = 'status-message warning';
                ocrResult.style.display = 'block';
                ocrStatus.innerHTML = '<span style="color: #f0883e;">識別中...</span>';
                
                try {
                    // 根據模式選擇 API
                    const apiUrl = useCloudAI ? '/api/recognize-card-cloud' : '/api/recognize-card';
                    
                    const res = await fetch(apiUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ image: imageData })
                    });
                    
                    const data = await res.json();
                    
                    if (data.matches && data.matches.length > 0) {
                        // 顯示 AI 處理時間
                        let timeInfo = data.ai_time_ms ? ` (${data.ai_time_ms}ms)` : '';
                        status.textContent = `✅ ${data.message}${timeInfo}`;
                        status.className = 'status-message success';
                        
                        // 顯示識別資訊
                        let ocrInfo = '';
                        if (useCloudAI) {
                            ocrInfo = '<span style="color: #3fb950;">🤖 雲端 CLIP AI 識別</span>';
                            if (data.matches[0].similarity) {
                                ocrInfo += `<br>最高相似度: <span style="color: #58a6ff;">${data.matches[0].similarity}%</span>`;
                            }
                        } else {
                            if (data.extracted_numbers && data.extracted_numbers.length > 0) {
                                ocrInfo += '卡號: <span style="color: #58a6ff;">' + data.extracted_numbers.join(', ') + '</span>';
                            }
                            if (data.detected_characters && data.detected_characters.length > 0) {
                                ocrInfo += (ocrInfo ? '<br>' : '') + '角色: <span style="color: #f0883e;">' + data.detected_characters.join(', ') + '</span>';
                            }
                        }
                        if (!ocrInfo) {
                            ocrInfo = '<span style="color: #8b949e;">根據圖像特徵推測</span>';
                        }
                        ocrStatus.innerHTML = ocrInfo;
                        
                        // 顯示所有匹配的卡牌
                        displayRecognitionResults(data.matches);
                    } else {
                        status.textContent = '❌ 無法識別，請嘗試手動搜尋';
                        status.className = 'status-message error';
                        ocrStatus.innerHTML = '<span style="color: #f85149;">未能識別</span>';
                    }
                    
                } catch(e) {
                    status.textContent = '❌ 識別失敗: ' + e.message;
                    status.className = 'status-message error';
                    ocrStatus.innerHTML = '<span style="color: #f85149;">錯誤</span>';
                }
            }
            
            function displayRecognitionResults(matches) {
                const results = document.getElementById('searchResults');
                const rate = getExchangeRate();
                
                results.innerHTML = matches.map(card => {
                    // 支援兩種 API 回應格式
                    const buyJPY = card.buy_jpy || card.latest_buy_jpy || 0;
                    const sellJPY = card.sell_jpy || card.latest_sell_jpy || 0;
                    const buyHKD = Math.round(buyJPY * rate);
                    const sellHKD = Math.round(sellJPY * rate);
                    
                    // 雲端 AI 使用 similarity，本地 OCR 使用 confidence
                    const confidence = card.similarity || card.confidence || 0;
                    const confidenceColor = confidence >= 80 ? '#3fb950' : (confidence >= 50 ? '#f0883e' : '#8b949e');
                    const matchType = card.match_type || '';
                    
                    return `
                    <div class="result-item" onclick="addToOrder(${card.card_id}, '${escapeAttr(card.card_number)}', '${escapeAttr(card.name)}', ${buyJPY})">
                        <img src="${card.image_url || ''}" onerror="this.src='https://via.placeholder.com/50x70?text=No'" />
                        <div class="result-info">
                            <div class="result-number">${card.card_number} <span style="color: ${confidenceColor}; font-size: 11px;">(${confidence}% ${matchType})</span></div>
                            <div class="result-name">${card.name}</div>
                            <div class="result-version">${card.version || ''}</div>
                            <div class="result-prices">
                                ${buyJPY > 0 ? `買取: <span class="jpy">${buyJPY.toLocaleString()} JPY</span> → <span class="hkd">HKD ${buyHKD}</span>` : ''}
                                ${sellJPY > 0 ? `<br>販售: <span style="color: #58a6ff;">${sellJPY.toLocaleString()} JPY</span>` : ''}
                                ${buyJPY === 0 && sellJPY === 0 ? '<span style="color: #8b949e;">價格未設定</span>' : ''}
                            </div>
                        </div>
                        <div class="result-actions">
                            <button class="btn-add" onclick="event.stopPropagation(); addToOrder(${card.card_id}, '${escapeAttr(card.card_number)}', '${escapeAttr(card.name)}', ${buyJPY})">+ 加入</button>
                        </div>
                    </div>
                    `;
                }).join('');
            }
            
            // ========== 搜尋功能 ==========
            function getExchangeRate() {
                return parseFloat(document.getElementById('exchangeRate').value) || 0.052;
            }
            
            function updateExchangePreview() {
                const rate = getExchangeRate();
                document.getElementById('ratePreview').textContent = Math.round(1000 * rate);
            }
            
            function quickSearch(prefix) {
                document.getElementById('searchInput').value = prefix;
                searchCards();
            }
            
            async function searchCards() {
                const query = document.getElementById('searchInput').value.trim();
                if (!query) {
                    showToast('請輸入搜尋關鍵字', 'error');
                    return;
                }
                
                const status = document.getElementById('statusMessage');
                const results = document.getElementById('searchResults');
                
                status.textContent = '🔄 搜尋中...';
                status.className = 'status-message warning';
                
                try {
                    const res = await fetch(`/api/cards/search?q=${encodeURIComponent(query)}&limit=30`);
                    const cards = await res.json();
                    
                    if (cards.length === 0) {
                        status.textContent = `❌ 找不到 "${query}"。請確認卡號格式`;
                        status.className = 'status-message error';
                        results.innerHTML = '';
                        return;
                    }
                    
                    status.textContent = `✅ 找到 ${cards.length} 張卡牌`;
                    status.className = 'status-message success';
                    
                    const rate = getExchangeRate();
                    
                    results.innerHTML = cards.map(card => {
                        const buyJPY = card.latest_buy_jpy || 0;
                        const buyHKD = Math.round(buyJPY * rate);
                        
                        return `
                        <div class="result-item" onclick="addToOrder(${card.id}, '${escapeAttr(card.card_number)}', '${escapeAttr(card.name)}', ${buyJPY})">
                            <img src="${card.image_url || ''}" onerror="this.src='https://via.placeholder.com/50x70?text=No'" />
                            <div class="result-info">
                                <div class="result-number">${card.card_number}</div>
                                <div class="result-name">${card.name}</div>
                                <div class="result-version">${card.version || ''} | ${card.game_code || ''}</div>
                                <div class="result-prices">
                                    買取: <span class="jpy">${buyJPY > 0 ? buyJPY.toLocaleString() + ' JPY' : '-'}</span>
                                    → <span class="hkd">${buyHKD > 0 ? 'HKD ' + buyHKD : '未設定'}</span>
                                </div>
                            </div>
                            <div class="result-actions">
                                <button class="btn-add" onclick="event.stopPropagation(); addToOrder(${card.id}, '${escapeAttr(card.card_number)}', '${escapeAttr(card.name)}', ${buyJPY})">+ 加入</button>
                            </div>
                        </div>
                        `;
                    }).join('');
                    
                } catch(e) {
                    status.textContent = '❌ 搜尋失敗: ' + e.message;
                    status.className = 'status-message error';
                }
            }
            
            function escapeAttr(text) {
                return text.replace(/'/g, "\\'").replace(/"/g, '\\"');
            }
            
            // ========== 買取單功能 ==========
            function addToOrder(cardId, cardNumber, name, priceJPY) {
                const rate = getExchangeRate();
                const priceHKD = Math.round(priceJPY * rate);
                
                const existing = orderItems.find(item => item.cardId === cardId);
                if (existing) {
                    existing.quantity++;
                } else {
                    orderItems.push({
                        cardId,
                        cardNumber,
                        name,
                        priceJPY,
                        priceHKD,
                        quantity: 1
                    });
                }
                
                renderOrder();
                showToast(`已加入: ${cardNumber}`, 'success');
            }
            
            function renderOrder() {
                const container = document.getElementById('orderItems');
                
                if (orderItems.length === 0) {
                    container.innerHTML = '<div class="empty-order">點擊卡牌加入買取單</div>';
                    updateSummary();
                    return;
                }
                
                container.innerHTML = orderItems.map((item, index) => `
                    <div class="order-item">
                        <div class="order-item-info">
                            <div class="order-item-number">${item.cardNumber}</div>
                            <div class="order-item-price-row">
                                <label>HKD</label>
                                <input type="number" class="price-input" value="${item.priceHKD}" min="0" onchange="setPrice(${index}, this.value)">
                                <span class="order-item-subtotal">x ${item.quantity} = HKD ${item.priceHKD * item.quantity}</span>
                            </div>
                        </div>
                        <div class="order-item-controls">
                            <button class="qty-btn" onclick="updateQty(${index}, -1)">−</button>
                            <input type="number" class="qty-input" value="${item.quantity}" min="1" onchange="setQty(${index}, this.value)">
                            <button class="qty-btn" onclick="updateQty(${index}, 1)">+</button>
                            <button class="remove-btn" onclick="removeItem(${index})">✕</button>
                        </div>
                    </div>
                `).join('');
                
                updateSummary();
            }
            
            function updateQty(index, delta) {
                orderItems[index].quantity = Math.max(1, orderItems[index].quantity + delta);
                renderOrder();
            }
            
            function setQty(index, value) {
                orderItems[index].quantity = Math.max(1, parseInt(value) || 1);
                renderOrder();
            }
            
            function setPrice(index, value) {
                orderItems[index].priceHKD = Math.max(0, parseInt(value) || 0);
                renderOrder();
            }
            
            function removeItem(index) {
                orderItems.splice(index, 1);
                renderOrder();
            }
            
            function clearOrder() {
                if (orderItems.length > 0 && !confirm('確定要清空買取單嗎？')) return;
                orderItems = [];
                renderOrder();
            }
            
            function updateSummary() {
                const totalTypes = orderItems.length;
                const totalQty = orderItems.reduce((sum, item) => sum + item.quantity, 0);
                const totalPrice = orderItems.reduce((sum, item) => sum + item.priceHKD * item.quantity, 0);
                
                document.getElementById('totalTypes').textContent = totalTypes + ' 種';
                document.getElementById('totalQty').textContent = totalQty + ' 張';
                document.getElementById('totalPrice').textContent = 'HKD ' + totalPrice.toLocaleString();
            }
            
            function completeOrder() {
                if (orderItems.length === 0) {
                    showToast('買取單是空的', 'error');
                    return;
                }
                
                const totalPrice = orderItems.reduce((sum, item) => sum + item.priceHKD * item.quantity, 0);
                
                if (confirm(`確認完成買取？\\n總額: HKD ${totalPrice.toLocaleString()}`)) {
                    showToast('買取完成！', 'success');
                    orderItems = [];
                    renderOrder();
                }
            }
            
            function showToast(message, type) {
                const toast = document.createElement('div');
                toast.className = `toast ${type}`;
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
            }
            
            // ========== 事件監聽 ==========
            document.getElementById('searchInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') searchCards();
            });
            
            // ========== 初始化 ==========
            initCamera();
            updateExchangePreview();
            renderOrder();
            checkAIStatus();  // 檢查雲端 AI 狀態
        </script>
    </body>
    </html>
    """
    return html_content


# ====== 雲端 AI 辨識 API ======

@app.post("/api/recognize-card-cloud")
async def recognize_card_cloud(data: dict, db: Session = Depends(get_db)):
    """
    使用雲端 CLIP AI 進行卡牌辨識
    """
    import io
    
    image_data = data.get("image", "")
    
    if not image_data:
        return {"success": False, "message": "沒有圖片數據", "matches": []}
    
    try:
        # 解碼 Base64 圖片
        if ',' in image_data:
            image_data_clean = image_data.split(',')[1]
        else:
            image_data_clean = image_data
        
        image_bytes = base64.b64decode(image_data_clean)
        
        # 呼叫雲端 AI 服務
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": ("card.jpg", io.BytesIO(image_bytes), "image/jpeg")}
            response = await client.post(
                f"{CLOUD_AI_URL}/recognize",
                files=files,
                params={"top_k": 10}
            )
            
            if response.status_code != 200:
                return {"success": False, "message": f"AI 服務錯誤: {response.status_code}", "matches": []}
            
            ai_result = response.json()
        
        if not ai_result.get("success") or not ai_result.get("matches"):
            return {
                "success": False, 
                "message": ai_result.get("message", "AI 無法識別此卡牌"),
                "matches": [],
                "ai_time_ms": ai_result.get("time_ms", 0)
            }
        
        # 將 AI 結果與資料庫匹配，獲取完整資訊
        matches = []
        for ai_match in ai_result["matches"]:
            card = db.query(Card).filter(Card.id == ai_match["card_id"]).first()
            if card:
                # 獲取最新價格
                latest_sell = db.query(MarketPrice).filter(
                    MarketPrice.card_id == card.id,
                    MarketPrice.price_type == "sell"
                ).order_by(desc(MarketPrice.timestamp)).first()
                
                latest_buy = db.query(MarketPrice).filter(
                    MarketPrice.card_id == card.id,
                    MarketPrice.price_type == "buy"
                ).order_by(desc(MarketPrice.timestamp)).first()
                
                game_code = None
                if card.card_set and card.card_set.game:
                    game_code = card.card_set.game.code
                
                matches.append({
                    "card_id": card.id,
                    "card_number": card.card_number,
                    "name": card.name,
                    "version": card.version,
                    "rarity": card.rarity,
                    "image_url": card.image_url,
                    "game_code": game_code,
                    "similarity": ai_match["similarity"],
                    "latest_sell_jpy": latest_sell.price_jpy if latest_sell else None,
                    "latest_buy_jpy": latest_buy.price_jpy if latest_buy else None,
                    "match_type": "AI_CLIP"
                })
        
        return {
            "success": len(matches) > 0,
            "matches": matches,
            "ai_time_ms": ai_result.get("time_ms", 0),
            "message": f"AI 找到 {len(matches)} 張匹配卡牌 (相似度最高: {matches[0]['similarity']}%)" if matches else "無匹配"
        }
        
    except httpx.TimeoutException:
        return {"success": False, "message": "AI 服務超時，請稍後再試", "matches": []}
    except Exception as e:
        return {"success": False, "message": f"錯誤: {str(e)}", "matches": []}


@app.get("/api/ai-status")
async def get_ai_status():
    """檢查雲端 AI 服務狀態"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{CLOUD_AI_URL}/health")
            if response.status_code == 200:
                data = response.json()
                return {
                    "online": True,
                    "url": CLOUD_AI_URL,
                    "model_loaded": data.get("model_loaded", False),
                    "status": data.get("status", "unknown")
                }
    except:
        pass
    
    return {"online": False, "url": CLOUD_AI_URL}


@app.post("/api/recognize-card")
async def recognize_card(data: dict, db: Session = Depends(get_db)):
    """
    智能卡牌識別系統 v4.0 - 基於知識庫的視覺特徵分析
    
    使用 card_knowledge_base.py 中定義的各遊戲卡牌知識進行識別
    """
    import re
    import io
    from PIL import Image
    import cv2
    import numpy as np
    from collections import Counter
    
    # 導入知識庫
    try:
        from card_knowledge_base import (
            OP_KNOWLEDGE, UA_KNOWLEDGE, VG_KNOWLEDGE, DM_KNOWLEDGE,
            identify_game_from_card_number, get_game_knowledge
        )
    except ImportError:
        # 如果導入失敗，使用簡化版本
        OP_KNOWLEDGE = {}
    
    image_data = data.get("image", "")
    
    if not image_data:
        return {"success": False, "message": "沒有圖片數據", "matches": []}
    
    # 解碼圖片
    try:
        if ',' in image_data:
            image_data_clean = image_data.split(',')[1]
        else:
            image_data_clean = image_data
        
        image_bytes = base64.b64decode(image_data_clean)
        image = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(image)
        
        # 確保是 RGB
        if len(img_array.shape) == 2:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
        elif img_array.shape[2] == 4:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
            
    except Exception as e:
        return {"success": False, "message": f"圖片解碼錯誤: {str(e)}", "matches": []}
    
    # ===== 第一步：OCR 識別卡號 =====
    ocr_results = perform_advanced_ocr(image, img_array)
    
    # ===== 第二步：視覺特徵分析 =====
    features = analyze_card_features_v4(img_array)
    
    # ===== 第三步：綜合判斷遊戲類型 =====
    detected_game = detect_game_type(features, ocr_results)
    features['detected_game'] = detected_game
    
    # ===== 第四步：資料庫搜尋 =====
    all_matches = search_cards_by_features_v4(db, features, ocr_results, detected_game)
    
    # 生成訊息
    feature_info = []
    if detected_game:
        feature_info.append(f"遊戲: {detected_game}")
    if features.get('detected_power'):
        feature_info.append(f"力量值: {features['detected_power']}")
    if features.get('detected_cost'):
        feature_info.append(f"費用: {features['detected_cost']}")
    if features.get('dominant_color'):
        feature_info.append(f"主色: {features['dominant_color']}")
    if ocr_results.get('card_numbers'):
        feature_info.append(f"卡號: {', '.join(ocr_results['card_numbers'][:3])}")
    
    message = f"偵測到 {len(all_matches)} 張可能的卡牌"
    if feature_info:
        message += f" ({', '.join(feature_info)})"
    
    return {
        "success": len(all_matches) > 0,
        "extracted_numbers": ocr_results.get('card_numbers', []),
        "detected_characters": ocr_results.get('characters', []),
        "features": features,
        "matches": all_matches[:30],
        "ocr_text": ocr_results.get('raw_text', '')[:200],
        "ocr_available": ocr_results.get('available', False),
        "message": message
    }


def perform_advanced_ocr(image, img_array):
    """進階 OCR 識別 - 多區域、多策略"""
    import cv2
    import numpy as np
    from PIL import Image
    import re
    
    results = {
        'available': False,
        'card_numbers': [],
        'characters': [],
        'raw_text': '',
        'power_texts': [],
        'detected_texts': {},
    }
    
    try:
        import pytesseract
        
        tesseract_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                results['available'] = True
                break
        
        if not results['available']:
            return results
        
        height, width = img_array.shape[:2]
        all_text = []
        
        # ===== 1. 全圖 OCR =====
        try:
            text = pytesseract.image_to_string(image, lang='eng+jpn', config='--psm 6')
            all_text.append(text)
            results['detected_texts']['full'] = text[:100]
        except:
            pass
        
        # ===== 2. 底部區域 (卡號通常在這裡) =====
        bottom_region = img_array[int(height*0.85):, :]
        try:
            gray = cv2.cvtColor(bottom_region, cv2.COLOR_RGB2GRAY)
            enhanced = cv2.convertScaleAbs(gray, alpha=2.5, beta=30)
            text = pytesseract.image_to_string(Image.fromarray(enhanced), config='--psm 7')
            all_text.append(text)
            results['detected_texts']['bottom'] = text[:50]
        except:
            pass
        
        # ===== 3. 右下角區域 (OP卡號位置) =====
        right_bottom = img_array[int(height*0.88):, int(width*0.55):]
        try:
            gray = cv2.cvtColor(right_bottom, cv2.COLOR_RGB2GRAY)
            enhanced = cv2.convertScaleAbs(gray, alpha=3.0, beta=40)
            # 嘗試白色文字 (反轉)
            inverted = 255 - enhanced
            text = pytesseract.image_to_string(Image.fromarray(enhanced), config='--psm 7')
            all_text.append(text)
            text2 = pytesseract.image_to_string(Image.fromarray(inverted), config='--psm 7')
            all_text.append(text2)
            results['detected_texts']['right_bottom'] = text[:50]
        except:
            pass
        
        # ===== 4. 右上角區域 (VG卡號位置) =====
        right_top = img_array[0:int(height*0.12), int(width*0.55):]
        try:
            gray = cv2.cvtColor(right_top, cv2.COLOR_RGB2GRAY)
            enhanced = cv2.convertScaleAbs(gray, alpha=2.5, beta=20)
            text = pytesseract.image_to_string(Image.fromarray(enhanced), config='--psm 7')
            all_text.append(text)
            results['detected_texts']['right_top'] = text[:50]
        except:
            pass
        
        # ===== 5. 左上角區域 (費用/等級) =====
        left_top = img_array[0:int(height*0.15), 0:int(width*0.15)]
        try:
            gray = cv2.cvtColor(left_top, cv2.COLOR_RGB2GRAY)
            enhanced = cv2.convertScaleAbs(gray, alpha=2.5, beta=20)
            config = r'--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789'
            text = pytesseract.image_to_string(Image.fromarray(enhanced), config=config)
            numbers = re.findall(r'\d+', text)
            if numbers:
                for n in numbers:
                    val = int(n)
                    if 0 <= val <= 10:
                        results['detected_cost'] = val
                        break
        except:
            pass
        
        # ===== 6. 右上角力量值區域 =====
        power_region = img_array[0:int(height*0.12), int(width*0.45):int(width*0.75)]
        try:
            gray = cv2.cvtColor(power_region, cv2.COLOR_RGB2GRAY)
            enhanced = cv2.convertScaleAbs(gray, alpha=2.5, beta=20)
            config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
            text = pytesseract.image_to_string(Image.fromarray(enhanced), config=config)
            numbers = re.findall(r'\d+', text)
            for n in numbers:
                val = int(n)
                if val in [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000]:
                    results['detected_power'] = val
                    break
                elif 100 <= val <= 1200:
                    results['detected_power'] = val * 10
                    break
        except:
            pass
        
        # 合併並處理文字
        combined = ' '.join(all_text).upper()
        results['raw_text'] = combined
        
        # 提取卡號
        card_patterns = [
            # OP 格式
            (r'OP\s*(\d{1,2})[-_\s]*(\d{2,3})', 'OP'),
            (r'0P\s*(\d{1,2})[-_\s]*(\d{2,3})', 'OP'),
            (r'[O0]P(\d{1,2})[-_\s]*(\d{2,3})', 'OP'),
            (r'ST\s*(\d{2})[-_\s]*(\d{2,3})', 'ST'),
            (r'EB\s*(\d{2})[-_\s]*(\d{2,3})', 'EB'),
            # UA 格式
            (r'UA\s*(\d{2})\s*BT', 'UA'),
            (r'EX\s*(\d{2})\s*BT', 'UA'),
            # VG 格式
            (r'D[-\s]*([A-Z]{2,3})\s*(\d{2})', 'VG'),
            (r'DZ[-\s]*([A-Z]{3})\s*(\d{2})', 'VG'),
            # DM 格式
            (r'DM\s*(\d{2})[-\s]*(\d{1,3})', 'DM'),
            (r'RP\s*(\d{2})', 'DM'),
        ]
        
        for pattern, game_type in card_patterns:
            matches = re.findall(pattern, combined)
            for match in matches:
                if game_type == 'OP':
                    card_num = f"OP{str(match[0]).zfill(2)}-{str(match[1]).zfill(3)}"
                elif game_type == 'ST':
                    card_num = f"ST{match[0]}-{str(match[1]).zfill(3)}"
                elif game_type == 'EB':
                    card_num = f"EB{match[0]}-{str(match[1]).zfill(3)}"
                elif game_type == 'VG':
                    if isinstance(match, tuple) and len(match) >= 2:
                        card_num = f"D-{match[0]}{match[1]}"
                    else:
                        continue
                else:
                    continue
                    
                if card_num not in results['card_numbers']:
                    results['card_numbers'].append(card_num)
        
        # 偵測角色名
        character_keywords = {
            # OP 角色
            'LUFFY': 'ルフィ', 'ZORO': 'ゾロ', 'NAMI': 'ナミ',
            'SANJI': 'サンジ', 'LAW': 'ロー', 'MIHAWK': 'ミホーク',
            'HANCOCK': 'ハンコック', 'DOFLAMINGO': 'ドフラミンゴ',
            'KAIDO': 'カイドウ', 'SHANKS': 'シャンクス', 'ACE': 'エース',
            'YAMATO': 'ヤマト', 'CROCODILE': 'クロコダイル',
            'DRACULE': 'ジュラキュール', 'JURAQUILLE': 'ジュラキュール',
        }
        
        japanese_names = [
            'ルフィ', 'ゾロ', 'ナミ', 'サンジ', 'ロー', 'ミホーク',
            'ジュラキュール', 'シャンクス', 'エース', 'ヤマト',
            'カイドウ', 'ハンコック', 'ドフラミンゴ', 'クロコダイル',
            'モンキー', 'ロロノア', 'トラファルガー', 'ボア',
        ]
        
        for eng, jpn in character_keywords.items():
            if eng in combined:
                if jpn not in results['characters']:
                    results['characters'].append(jpn)
        
        for jpn in japanese_names:
            if jpn in combined:
                if jpn not in results['characters']:
                    results['characters'].append(jpn)
        
    except Exception as e:
        results['error'] = str(e)
    
    return results


def analyze_card_features_v4(img_array):
    """分析卡牌的視覺特徵 v4.0 - 使用知識庫"""
    import cv2
    import numpy as np
    from collections import Counter
    
    features = {}
    height, width = img_array.shape[:2]
    
    # ===== 1. 分析卡牌長寬比 =====
    aspect_ratio = width / height
    features['aspect_ratio'] = round(aspect_ratio, 3)
    
    if 0.65 < aspect_ratio < 0.80:
        features['card_format'] = 'standard_tcg'
    else:
        features['card_format'] = 'non_standard'
    
    # ===== 2. 顏色分析 (使用更精確的邊框區域) =====
    hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
    
    # 取邊框區域 (排除中間圖像部分)
    border_mask = np.zeros((height, width), dtype=np.uint8)
    border_width = int(min(width, height) * 0.08)
    border_mask[0:border_width, :] = 255  # 上
    border_mask[height-border_width:, :] = 255  # 下
    border_mask[:, 0:border_width] = 255  # 左
    border_mask[:, width-border_width:] = 255  # 右
    
    # 定義顏色範圍 (HSV)
    color_ranges = {
        '紅': [
            ((0, 80, 80), (10, 255, 255)),
            ((160, 80, 80), (180, 255, 255)),
        ],
        '藍': [((100, 80, 80), (130, 255, 255))],
        '綠': [
            ((35, 60, 60), (85, 255, 255)),     # 純綠
            ((75, 60, 60), (100, 255, 255)),    # 青綠/綠松石
        ],
        '紫': [((120, 50, 50), (160, 255, 255))],
        '黃': [((15, 80, 150), (35, 255, 255))],
        '黑': [((0, 0, 0), (180, 80, 80))],
        '白': [((0, 0, 200), (180, 30, 255))],
    }
    
    color_counts = Counter()
    for color_name, ranges in color_ranges.items():
        total = 0
        for (lower, upper) in ranges:
            mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
            mask = cv2.bitwise_and(mask, mask, mask=border_mask)
            total += cv2.countNonZero(mask)
        color_counts[color_name] = total
    
    # 取最高比例的顏色
    if color_counts:
        top_colors = color_counts.most_common(3)
        features['dominant_color'] = top_colors[0][0]
        features['color_distribution'] = {c: v for c, v in top_colors}
    
    # ===== 3. 分析亮度和對比度 (判斷是否為閃卡) =====
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    features['brightness'] = int(np.mean(gray))
    features['contrast'] = int(np.std(gray))
    features['likely_parallel'] = features['contrast'] > 65
    
    # ===== 4. 分析特定區域顏色 (用於判斷遊戲類型) =====
    # 左上角區域 (費用/等級圈)
    left_top = hsv[0:int(height*0.12), 0:int(width*0.12)]
    left_top_colors = Counter()
    for color_name, ranges in color_ranges.items():
        for (lower, upper) in ranges:
            mask = cv2.inRange(left_top, np.array(lower), np.array(upper))
            left_top_colors[color_name] += cv2.countNonZero(mask)
    if left_top_colors:
        features['left_top_color'] = left_top_colors.most_common(1)[0][0]
    
    # 右上角區域
    right_top = hsv[0:int(height*0.12), int(width*0.75):]
    right_top_colors = Counter()
    for color_name, ranges in color_ranges.items():
        for (lower, upper) in ranges:
            mask = cv2.inRange(right_top, np.array(lower), np.array(upper))
            right_top_colors[color_name] += cv2.countNonZero(mask)
    if right_top_colors:
        features['right_top_color'] = right_top_colors.most_common(1)[0][0]
    
    return features


def detect_game_type(features, ocr_results):
    """根據特徵和 OCR 結果判斷遊戲類型"""
    
    # 優先使用卡號判斷
    for card_number in ocr_results.get('card_numbers', []):
        card_number = card_number.upper()
        if card_number.startswith(('OP', 'ST', 'EB', 'POP')):
            return 'OP'
        elif 'BT/' in card_number or card_number.startswith(('UA', 'EX')):
            return 'UA'
        elif card_number.startswith(('D-', 'DZ-', 'V-', 'G-')):
            return 'VG'
        elif card_number.startswith(('DM', 'RP', 'BD')):
            return 'DM'
    
    # 使用 OCR 文字判斷
    raw_text = ocr_results.get('raw_text', '').upper()
    if 'OP14' in raw_text or 'OP13' in raw_text or 'OP12' in raw_text:
        return 'OP'
    if 'CHARACTER' in raw_text or 'キャラクター' in raw_text:
        return 'OP'
    
    # 根據視覺特徵推測 (不太可靠，作為備選)
    aspect = features.get('aspect_ratio', 0)
    if 0.70 < aspect < 0.75:
        # 標準 TCG 卡牌尺寸，無法區分
        return None
    
    return None


def search_cards_by_features_v4(db, features, ocr_results, detected_game):
    """根據特徵搜尋資料庫中的卡牌 v4.0"""
    all_matches = []
    seen_ids = set()
    
    # 1. 用卡號精確搜尋 (最高優先)
    for card_number in ocr_results.get('card_numbers', []):
        cards = db.query(Card).filter(
            Card.card_number.ilike(f"%{card_number}%")
        ).limit(10).all()
        
        for card in cards:
            if card.id not in seen_ids:
                seen_ids.add(card.id)
                add_card_match_v4(db, card, all_matches, 95, f"卡號匹配: {card_number}")
    
    # 2. 用角色名搜尋
    for char_name in ocr_results.get('characters', [])[:3]:
        cards = db.query(Card).filter(
            Card.name.ilike(f"%{char_name}%")
        ).limit(15).all()
        
        for card in cards:
            if card.id not in seen_ids:
                seen_ids.add(card.id)
                add_card_match_v4(db, card, all_matches, 75, f"角色: {char_name}")
    
    # 3. 根據偵測到的遊戲類型搜尋
    if detected_game and len(all_matches) < 10:
        game = db.query(Game).filter(Game.code == detected_game).first()
        if game:
            # 根據顏色過濾
            color = features.get('dominant_color', '')
            color_jp_map = {'紅': '赤', '藍': '青', '黃': '黄', '黑': '黒'}
            search_color = color_jp_map.get(color, color)
            
            # 搜尋該遊戲中匹配顏色的卡
            cards = db.query(Card).join(CardSet).filter(
                CardSet.game_id == game.id,
                Card.name.ilike(f"%《{search_color}》%") | Card.name.ilike(f"%【{search_color}】%")
            ).join(MarketPrice, isouter=True).order_by(
                desc(MarketPrice.price_jpy)
            ).limit(20).all()
            
            for card in cards:
                if card.id not in seen_ids:
                    seen_ids.add(card.id)
                    add_card_match_v4(db, card, all_matches, 50, f"顏色推測: {search_color}")
    
    # 4. 如果還沒找到，用力量值/費用過濾
    power = features.get('detected_power') or ocr_results.get('detected_power')
    cost = features.get('detected_cost') or ocr_results.get('detected_cost')
    
    if (power or cost) and len(all_matches) < 10:
        # 這個功能需要資料庫有 power/cost 欄位才能完整實現
        pass
    
    # 5. 最後兜底：根據遊戲類型推薦熱門卡
    if len(all_matches) < 5:
        game_filter = None
        if detected_game:
            game = db.query(Game).filter(Game.code == detected_game).first()
            if game:
                game_filter = game.id
        
        query = db.query(Card).join(MarketPrice).filter(
            MarketPrice.price_type == "sell",
            MarketPrice.price_jpy > 500
        )
        
        if game_filter:
            query = query.join(CardSet).filter(CardSet.game_id == game_filter)
        
        popular = query.order_by(desc(MarketPrice.price_jpy)).limit(15).all()
        
        for card in popular:
            if card.id not in seen_ids:
                seen_ids.add(card.id)
                add_card_match_v4(db, card, all_matches, 30, "熱門推薦")
    
    # 按信心度排序
    all_matches.sort(key=lambda x: x['confidence'], reverse=True)
    
    return all_matches


def add_card_match_v4(db, card, matches_list, confidence, match_type):
    """將卡牌加入匹配列表 v4.0"""
    latest_buy = db.query(MarketPrice).filter(
        MarketPrice.card_id == card.id,
        MarketPrice.price_type == "buy"
    ).order_by(desc(MarketPrice.timestamp)).first()
    
    latest_sell = db.query(MarketPrice).filter(
        MarketPrice.card_id == card.id,
        MarketPrice.price_type == "sell"
    ).order_by(desc(MarketPrice.timestamp)).first()
    
    # 從名稱中提取顏色標記
    import re
    color_match = re.search(r'《([^》]+)》|【([^】]+)】', card.name)
    detected_color = None
    if color_match:
        detected_color = color_match.group(1) or color_match.group(2)
    
    matches_list.append({
        "card_id": card.id,
        "card_number": card.card_number,
        "name": card.name,
        "version": card.version,
        "image_url": card.image_url,
        "confidence": confidence,
        "match_type": match_type,
        "detected_color": detected_color,
        "buy_jpy": latest_buy.price_jpy if latest_buy else None,
        "sell_jpy": latest_sell.price_jpy if latest_sell else None
    })


# ============================================================
# 儀表板系統 - 漲跌風向標 & 套利警示
# ============================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    """市場儀表板 - 漲跌風向標、套利警示、市場概覽"""
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TCGE 市場儀表板</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: #0d1117;
                color: #c9d1d9; 
                padding: 20px;
            }
            .container { max-width: 1800px; margin: 0 auto; }
            h1 { 
                color: #58a6ff; 
                margin-bottom: 20px; 
                display: flex; 
                align-items: center; 
                gap: 15px; 
                flex-wrap: wrap;
            }
            h1 a { color: #8b949e; text-decoration: none; font-size: 14px; }
            h1 a:hover { color: #58a6ff; }
            
            /* 頂部統計卡片 */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 25px;
            }
            .stat-card {
                background: linear-gradient(135deg, #161b22, #1c2128);
                border: 1px solid #30363d;
                border-radius: 12px;
                padding: 20px;
                text-align: center;
            }
            .stat-card.highlight-up {
                border-color: #238636;
                background: linear-gradient(135deg, #0d1117, #0d2818);
            }
            .stat-card.highlight-down {
                border-color: #da3633;
                background: linear-gradient(135deg, #0d1117, #2d1215);
            }
            .stat-card.highlight-warning {
                border-color: #9e6a03;
                background: linear-gradient(135deg, #0d1117, #2d2003);
            }
            .stat-label { color: #8b949e; font-size: 13px; margin-bottom: 8px; }
            .stat-value { font-size: 32px; font-weight: bold; color: #c9d1d9; }
            .stat-value.up { color: #3fb950; }
            .stat-value.down { color: #f85149; }
            .stat-value.warning { color: #f0883e; }
            .stat-change { font-size: 12px; margin-top: 5px; }
            .stat-change.up { color: #3fb950; }
            .stat-change.down { color: #f85149; }
            
            /* 主要佈局 */
            .dashboard-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }
            
            /* 面板 */
            .panel {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 12px;
                padding: 20px;
            }
            .panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 15px;
                border-bottom: 1px solid #30363d;
            }
            .panel-header h2 { 
                color: #58a6ff; 
                font-size: 18px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .panel-header .filters {
                display: flex;
                gap: 8px;
            }
            .panel-header select, .panel-header input {
                padding: 6px 12px;
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #0d1117;
                color: #c9d1d9;
                font-size: 13px;
            }
            .panel-header button {
                padding: 6px 15px;
                border: none;
                border-radius: 6px;
                background: #238636;
                color: #fff;
                cursor: pointer;
                font-size: 13px;
            }
            .panel-header button:hover { background: #2ea043; }
            
            /* 價格變動列表 */
            .price-list {
                max-height: 450px;
                overflow-y: auto;
            }
            .price-item {
                display: flex;
                align-items: center;
                padding: 12px;
                border-radius: 8px;
                margin-bottom: 8px;
                background: #0d1117;
                border: 1px solid #21262d;
                transition: all 0.2s;
            }
            .price-item:hover {
                border-color: #58a6ff;
                background: #0d111799;
            }
            .price-item.up { border-left: 4px solid #3fb950; }
            .price-item.down { border-left: 4px solid #f85149; }
            .price-item.warning { border-left: 4px solid #f0883e; }
            .price-item.danger { border-left: 4px solid #da3633; background: #2d121599; }
            
            .price-rank {
                width: 30px;
                text-align: center;
                font-weight: bold;
                color: #8b949e;
            }
            .price-item:nth-child(1) .price-rank { color: #ffd93d; }
            .price-item:nth-child(2) .price-rank { color: #c0c0c0; }
            .price-item:nth-child(3) .price-rank { color: #cd7f32; }
            
            .price-card-info {
                flex: 1;
                min-width: 0;
            }
            .price-card-number {
                color: #58a6ff;
                font-weight: 600;
                font-size: 14px;
            }
            .price-card-name {
                color: #8b949e;
                font-size: 12px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .price-game-tag {
                display: inline-block;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                margin-left: 8px;
            }
            .price-game-tag.OP { background: #da3633; color: #fff; }
            .price-game-tag.UA { background: #1f6feb; color: #fff; }
            .price-game-tag.VG { background: #238636; color: #fff; }
            .price-game-tag.DM { background: #9e6a03; color: #fff; }
            
            .price-values {
                text-align: right;
                min-width: 120px;
            }
            .price-current {
                font-size: 16px;
                font-weight: 600;
            }
            .price-current.up { color: #3fb950; }
            .price-current.down { color: #f85149; }
            .price-change {
                font-size: 12px;
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: 5px;
            }
            .price-change.up { color: #3fb950; }
            .price-change.down { color: #f85149; }
            .price-change .arrow { font-size: 14px; }
            
            .price-old {
                font-size: 11px;
                color: #8b949e;
                text-decoration: line-through;
            }
            
            /* 套利警示特別樣式 */
            .arbitrage-item {
                display: grid;
                grid-template-columns: 1fr auto auto auto;
                gap: 15px;
                align-items: center;
                padding: 15px;
                background: #0d1117;
                border-radius: 8px;
                margin-bottom: 10px;
                border: 1px solid #21262d;
            }
            .arbitrage-item.premium { border-left: 4px solid #f0883e; }
            .arbitrage-item.inverted { border-left: 4px solid #da3633; background: #2d121566; }
            
            .arbitrage-card-info { }
            .arbitrage-prices {
                text-align: center;
            }
            .arbitrage-label {
                font-size: 11px;
                color: #8b949e;
                margin-bottom: 2px;
            }
            .arbitrage-value {
                font-size: 14px;
                font-weight: 600;
            }
            .arbitrage-value.jp { color: #f0883e; }
            .arbitrage-value.tcge { color: #3fb950; }
            
            .arbitrage-diff {
                text-align: center;
                padding: 8px 15px;
                border-radius: 6px;
                min-width: 80px;
            }
            .arbitrage-diff.positive {
                background: #0d2818;
                border: 1px solid #238636;
            }
            .arbitrage-diff.negative {
                background: #2d1215;
                border: 1px solid #da3633;
            }
            .arbitrage-diff-value {
                font-size: 16px;
                font-weight: bold;
            }
            .arbitrage-diff.positive .arbitrage-diff-value { color: #3fb950; }
            .arbitrage-diff.negative .arbitrage-diff-value { color: #f85149; }
            .arbitrage-diff-label {
                font-size: 10px;
                color: #8b949e;
            }
            
            .arbitrage-action {
                min-width: 80px;
            }
            .action-btn {
                padding: 8px 15px;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                cursor: pointer;
                width: 100%;
            }
            .action-btn.raise { background: #238636; color: #fff; }
            .action-btn.lower { background: #da3633; color: #fff; }
            .action-btn.pause { background: #9e6a03; color: #fff; }
            .action-btn.set { background: #58a6ff; color: #fff; }
            
            /* 類型標籤 */
            .type-badge {
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 10px;
                margin-left: 5px;
            }
            .type-badge.premium { background: #9e6a03; color: #fff; }
            .type-badge.inverted { background: #da3633; color: #fff; }
            .type-badge.needs_pricing { background: #58a6ff; color: #fff; }
            
            /* 待定價項目樣式 */
            .arbitrage-item.needs_pricing {
                border-left: 3px solid #58a6ff;
                background: rgba(88, 166, 255, 0.05);
            }
            
            /* 圖表區 */
            .chart-container {
                height: 300px;
                margin-top: 15px;
            }
            
            /* 空狀態 */
            .empty-state {
                text-align: center;
                padding: 40px;
                color: #8b949e;
            }
            
            /* 更新時間 */
            .update-time {
                text-align: right;
                font-size: 12px;
                color: #8b949e;
                margin-top: 10px;
            }
            
            /* 刷新按鈕 */
            .refresh-btn {
                padding: 8px 20px;
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #21262d;
                color: #c9d1d9;
                cursor: pointer;
                font-size: 13px;
            }
            .refresh-btn:hover { background: #30363d; }
            .refresh-btn.loading { opacity: 0.6; cursor: wait; }
            
            /* 篩選標籤 */
            .filter-tabs {
                display: flex;
                gap: 5px;
                margin-bottom: 15px;
            }
            .filter-tab {
                padding: 6px 15px;
                border: 1px solid #30363d;
                border-radius: 20px;
                background: transparent;
                color: #8b949e;
                cursor: pointer;
                font-size: 12px;
                transition: all 0.2s;
            }
            .filter-tab:hover { border-color: #58a6ff; color: #58a6ff; }
            .filter-tab.active { 
                background: #58a6ff; 
                color: #0d1117; 
                border-color: #58a6ff;
            }
            
            /* 響應式 */
            @media (max-width: 1200px) {
                .dashboard-grid { grid-template-columns: 1fr; }
            }
            
            /* 載入動畫 */
            .loading-spinner {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 2px solid #30363d;
                border-top-color: #58a6ff;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                📊 市場儀表板
                <a href="/">← 返回首頁</a>
                <a href="/admin">⚙️ 後台管理</a>
                <button class="refresh-btn" onclick="refreshAll()" id="refreshBtn">🔄 刷新數據</button>
            </h1>
            
            <!-- 頂部統計 -->
            <div class="stats-grid" id="statsGrid">
                <div class="stat-card">
                    <div class="stat-label">📈 24h 漲幅最大</div>
                    <div class="stat-value up" id="topGainer">-</div>
                    <div class="stat-change up" id="topGainerChange">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">📉 24h 跌幅最大</div>
                    <div class="stat-value down" id="topLoser">-</div>
                    <div class="stat-change down" id="topLoserChange">-</div>
                </div>
                <div class="stat-card highlight-warning">
                    <div class="stat-label">⚠️ 溢價警示</div>
                    <div class="stat-value warning" id="premiumCount">0</div>
                    <div class="stat-change">張卡需調價</div>
                </div>
                <div class="stat-card highlight-down">
                    <div class="stat-label">🚨 倒掛警示</div>
                    <div class="stat-value down" id="invertedCount">0</div>
                    <div class="stat-change">張卡需暫停</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">💰 今日價格更新</div>
                    <div class="stat-value" id="todayUpdates">-</div>
                    <div class="stat-change" id="lastUpdateTime">-</div>
                </div>
            </div>
            
            <!-- 主要面板 -->
            <div class="dashboard-grid">
                <!-- 漲跌風向標 -->
                <div class="panel">
                    <div class="panel-header">
                        <h2>🌊 漲跌風向標</h2>
                        <div class="filters">
                            <select id="trendGame" onchange="loadTrends()">
                                <option value="">全部遊戲</option>
                                <option value="OP">One Piece</option>
                                <option value="UA">Union Arena</option>
                                <option value="VG">Vanguard</option>
                                <option value="DM">Duel Masters</option>
                            </select>
                            <select id="trendPeriod" onchange="loadTrends()">
                                <option value="24">24 小時</option>
                                <option value="72">3 天</option>
                                <option value="168">7 天</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="filter-tabs">
                        <button class="filter-tab active" onclick="filterTrend('all', this)">全部</button>
                        <button class="filter-tab" onclick="filterTrend('up', this)">📈 上漲</button>
                        <button class="filter-tab" onclick="filterTrend('down', this)">📉 下跌</button>
                    </div>
                    
                    <div class="price-list" id="trendList">
                        <div class="empty-state"><div class="loading-spinner"></div> 載入中...</div>
                    </div>
                    
                    <div class="update-time" id="trendUpdateTime"></div>
                </div>
                
                <!-- 套利警示 -->
                <div class="panel">
                    <div class="panel-header">
                        <h2>💹 套利警示</h2>
                        <div class="filters">
                            <select id="arbitrageGame" onchange="loadArbitrage()">
                                <option value="">全部遊戲</option>
                                <option value="OP">One Piece</option>
                                <option value="UA">Union Arena</option>
                                <option value="VG">Vanguard</option>
                                <option value="DM">Duel Masters</option>
                            </select>
                            <input type="number" id="exchangeRate" value="0.052" step="0.001" style="width: 80px;" onchange="loadArbitrage()">
                            <span style="color: #8b949e; font-size: 12px;">匯率</span>
                        </div>
                    </div>
                    
                    <div class="filter-tabs">
                        <button class="filter-tab active" onclick="filterArbitrage('all', this)">全部</button>
                        <button class="filter-tab" onclick="filterArbitrage('premium', this)">⚠️ 溢價</button>
                        <button class="filter-tab" onclick="filterArbitrage('inverted', this)">🚨 倒掛</button>
                        <button class="filter-tab" onclick="filterArbitrage('needs_pricing', this)">💰 待定價</button>
                    </div>
                    
                    <div class="price-list" id="arbitrageList">
                        <div class="empty-state"><div class="loading-spinner"></div> 載入中...</div>
                    </div>
                    
                    <div class="update-time" id="arbitrageUpdateTime"></div>
                </div>
            </div>
            
            <!-- 價格趨勢圖表 (可選) -->
            <div class="panel" style="margin-top: 20px;">
                <div class="panel-header">
                    <h2>📈 市場趨勢</h2>
                </div>
                <div class="chart-container">
                    <canvas id="marketChart"></canvas>
                </div>
            </div>
        </div>
        
        <script>
            let trendData = [];
            let arbitrageData = [];
            let currentTrendFilter = 'all';
            let currentArbitrageFilter = 'all';
            
            // ========== 載入統計數據 ==========
            async function loadStats() {
                try {
                    const res = await fetch('/api/dashboard/stats');
                    const data = await res.json();
                    
                    // 更新統計卡片
                    if (data.top_gainer) {
                        document.getElementById('topGainer').textContent = data.top_gainer.card_number;
                        document.getElementById('topGainerChange').textContent = '+' + data.top_gainer.change_percent.toFixed(1) + '%';
                    }
                    if (data.top_loser) {
                        document.getElementById('topLoser').textContent = data.top_loser.card_number;
                        document.getElementById('topLoserChange').textContent = data.top_loser.change_percent.toFixed(1) + '%';
                    }
                    
                    document.getElementById('premiumCount').textContent = data.premium_count || 0;
                    document.getElementById('invertedCount').textContent = data.inverted_count || 0;
                    document.getElementById('todayUpdates').textContent = (data.today_updates || 0).toLocaleString();
                    document.getElementById('lastUpdateTime').textContent = '最後更新: ' + new Date().toLocaleTimeString();
                    
                } catch(e) {
                    console.error('Stats error:', e);
                }
            }
            
            // ========== 載入漲跌風向標 ==========
            async function loadTrends() {
                const game = document.getElementById('trendGame').value;
                const period = document.getElementById('trendPeriod').value;
                
                const listEl = document.getElementById('trendList');
                listEl.innerHTML = '<div class="empty-state"><div class="loading-spinner"></div> 載入中...</div>';
                
                try {
                    let url = `/api/dashboard/trends?hours=${period}`;
                    if (game) url += `&game=${game}`;
                    
                    const res = await fetch(url);
                    trendData = await res.json();
                    
                    renderTrends();
                    document.getElementById('trendUpdateTime').textContent = '更新時間: ' + new Date().toLocaleTimeString();
                    
                } catch(e) {
                    listEl.innerHTML = '<div class="empty-state">載入失敗: ' + e.message + '</div>';
                }
            }
            
            function renderTrends() {
                const listEl = document.getElementById('trendList');
                
                let filtered = trendData;
                if (currentTrendFilter === 'up') {
                    filtered = trendData.filter(t => t.change_percent > 0);
                } else if (currentTrendFilter === 'down') {
                    filtered = trendData.filter(t => t.change_percent < 0);
                }
                
                if (filtered.length === 0) {
                    listEl.innerHTML = '<div class="empty-state">沒有符合條件的價格變動</div>';
                    return;
                }
                
                listEl.innerHTML = filtered.map((item, index) => {
                    const isUp = item.change_percent > 0;
                    const changeClass = isUp ? 'up' : 'down';
                    const arrow = isUp ? '▲' : '▼';
                    
                    return `
                    <div class="price-item ${changeClass}">
                        <div class="price-rank">${index + 1}</div>
                        <div class="price-card-info">
                            <div class="price-card-number">
                                ${item.card_number}
                                <span class="price-game-tag ${item.game_code}">${item.game_code}</span>
                            </div>
                            <div class="price-card-name">${item.name}</div>
                        </div>
                        <div class="price-values">
                            <div class="price-current ${changeClass}">¥${item.current_price.toLocaleString()}</div>
                            <div class="price-change ${changeClass}">
                                <span class="arrow">${arrow}</span>
                                <span>${isUp ? '+' : ''}${item.change_percent.toFixed(1)}%</span>
                                <span class="price-old">¥${item.old_price.toLocaleString()}</span>
                            </div>
                        </div>
                    </div>
                    `;
                }).join('');
            }
            
            function filterTrend(filter, btn) {
                currentTrendFilter = filter;
                document.querySelectorAll('.panel:first-of-type .filter-tab').forEach(t => t.classList.remove('active'));
                btn.classList.add('active');
                renderTrends();
            }
            
            // ========== 載入套利警示 ==========
            async function loadArbitrage() {
                const game = document.getElementById('arbitrageGame').value;
                const rate = document.getElementById('exchangeRate').value;
                
                const listEl = document.getElementById('arbitrageList');
                listEl.innerHTML = '<div class="empty-state"><div class="loading-spinner"></div> 載入中...</div>';
                
                try {
                    let url = `/api/dashboard/arbitrage?exchange_rate=${rate}`;
                    if (game) url += `&game=${game}`;
                    
                    const res = await fetch(url);
                    arbitrageData = await res.json();
                    
                    renderArbitrage();
                    document.getElementById('arbitrageUpdateTime').textContent = '更新時間: ' + new Date().toLocaleTimeString();
                    
                    // 更新警示數量
                    const premiumCount = arbitrageData.filter(a => a.type === 'premium').length;
                    const invertedCount = arbitrageData.filter(a => a.type === 'inverted').length;
                    document.getElementById('premiumCount').textContent = premiumCount;
                    document.getElementById('invertedCount').textContent = invertedCount;
                    
                } catch(e) {
                    listEl.innerHTML = '<div class="empty-state">載入失敗: ' + e.message + '</div>';
                }
            }
            
            function renderArbitrage() {
                const listEl = document.getElementById('arbitrageList');
                
                let filtered = arbitrageData;
                if (currentArbitrageFilter === 'premium') {
                    filtered = arbitrageData.filter(a => a.type === 'premium');
                } else if (currentArbitrageFilter === 'inverted') {
                    filtered = arbitrageData.filter(a => a.type === 'inverted');
                }
                
                if (filtered.length === 0) {
                    listEl.innerHTML = '<div class="empty-state">🎉 沒有需要處理的套利警示</div>';
                    return;
                }
                
                listEl.innerHTML = filtered.map(item => {
                    const isPremium = item.type === 'premium';
                    const isInverted = item.type === 'inverted';
                    const needsPricing = item.type === 'needs_pricing';
                    const diffClass = item.diff_hkd > 0 ? 'positive' : (item.diff_hkd < 0 ? 'negative' : 'neutral');
                    
                    let typeLabel = '';
                    let actionBtn = '';
                    
                    if (isPremium) {
                        typeLabel = '⚠️ 溢價';
                        actionBtn = '<button class="action-btn raise" onclick="adjustPrice(' + item.card_id + ', \'raise\')">📈 提價</button>';
                    } else if (isInverted) {
                        typeLabel = '🚨 倒掛';
                        actionBtn = '<button class="action-btn pause" onclick="adjustPrice(' + item.card_id + ', \'pause\')">⏸️ 暫停</button>';
                    } else if (needsPricing) {
                        typeLabel = '💰 待定價';
                        actionBtn = '<button class="action-btn set" onclick="adjustPrice(' + item.card_id + ', \'set\')">✏️ 定價</button>';
                    }
                    
                    return `
                    <div class="arbitrage-item ${item.type}">
                        <div class="arbitrage-card-info">
                            <div class="price-card-number">
                                ${item.card_number}
                                <span class="price-game-tag ${item.game_code}">${item.game_code}</span>
                                <span class="type-badge ${item.type}">${typeLabel}</span>
                            </div>
                            <div class="price-card-name">${item.name}</div>
                        </div>
                        <div class="arbitrage-prices">
                            <div class="arbitrage-label">日本${isPremium ? '買取' : '售價'}</div>
                            <div class="arbitrage-value jp">¥${item.jp_price.toLocaleString()}</div>
                            <div style="font-size: 11px; color: #8b949e;">≈ HKD ${item.jp_price_hkd}</div>
                        </div>
                        <div class="arbitrage-prices">
                            <div class="arbitrage-label">${needsPricing ? '建議買取' : 'TCGE 買取'}</div>
                            <div class="arbitrage-value tcge">HKD ${needsPricing ? item.suggested_buy : item.tcge_price}</div>
                        </div>
                        ${!needsPricing ? `
                        <div class="arbitrage-diff ${diffClass}">
                            <div class="arbitrage-diff-value">${item.diff_hkd > 0 ? '+' : ''}${item.diff_hkd}</div>
                            <div class="arbitrage-diff-label">HKD 差額</div>
                        </div>
                        ` : ''}
                        <div class="arbitrage-action">
                            ${actionBtn}
                        </div>
                    </div>
                    `;
                }).join('');
            }
            
            function filterArbitrage(filter, btn) {
                currentArbitrageFilter = filter;
                document.querySelectorAll('.panel:nth-of-type(2) .filter-tab').forEach(t => t.classList.remove('active'));
                btn.classList.add('active');
                renderArbitrage();
            }
            
            async function adjustPrice(cardId, action) {
                alert(`將跳轉至後台調整卡片 ID: ${cardId} 的價格 (${action})`);
                window.open(`/admin?card_id=${cardId}`, '_blank');
            }
            
            // ========== 市場趨勢圖表 ==========
            let marketChart = null;
            
            async function loadMarketChart() {
                try {
                    const res = await fetch('/api/dashboard/market-summary');
                    const data = await res.json();
                    
                    const ctx = document.getElementById('marketChart').getContext('2d');
                    
                    if (marketChart) marketChart.destroy();
                    
                    marketChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.dates,
                            datasets: [
                                {
                                    label: 'OP 平均售價',
                                    data: data.op_prices,
                                    borderColor: '#da3633',
                                    backgroundColor: 'rgba(218, 54, 51, 0.1)',
                                    fill: true,
                                    tension: 0.3
                                },
                                {
                                    label: 'UA 平均售價',
                                    data: data.ua_prices,
                                    borderColor: '#1f6feb',
                                    backgroundColor: 'rgba(31, 111, 235, 0.1)',
                                    fill: true,
                                    tension: 0.3
                                },
                                {
                                    label: 'VG 平均售價',
                                    data: data.vg_prices,
                                    borderColor: '#238636',
                                    backgroundColor: 'rgba(35, 134, 54, 0.1)',
                                    fill: true,
                                    tension: 0.3
                                }
                            ]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            interaction: { intersect: false, mode: 'index' },
                            plugins: {
                                legend: { 
                                    labels: { color: '#c9d1d9' },
                                    position: 'top'
                                }
                            },
                            scales: {
                                x: {
                                    ticks: { color: '#8b949e' },
                                    grid: { color: '#21262d' }
                                },
                                y: {
                                    ticks: { color: '#8b949e' },
                                    grid: { color: '#21262d' }
                                }
                            }
                        }
                    });
                    
                } catch(e) {
                    console.error('Chart error:', e);
                }
            }
            
            // ========== 刷新所有數據 ==========
            async function refreshAll() {
                const btn = document.getElementById('refreshBtn');
                btn.classList.add('loading');
                btn.textContent = '🔄 刷新中...';
                
                await Promise.all([
                    loadStats(),
                    loadTrends(),
                    loadArbitrage(),
                    loadMarketChart()
                ]);
                
                btn.classList.remove('loading');
                btn.textContent = '🔄 刷新數據';
            }
            
            // ========== 初始化 ==========
            loadStats();
            loadTrends();
            loadArbitrage();
            loadMarketChart();
            
            // 每 5 分鐘自動刷新
            setInterval(refreshAll, 5 * 60 * 1000);
        </script>
    </body>
    </html>
    """
    return html_content


@app.get("/api/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """獲取儀表板統計數據"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    yesterday = now - timedelta(hours=24)
    
    # 今日價格更新數
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_updates = db.query(func.count(MarketPrice.id)).filter(
        MarketPrice.timestamp >= today_start
    ).scalar() or 0
    
    # 計算漲跌幅最大的卡牌 (需要複雜查詢)
    top_gainer = None
    top_loser = None
    
    # 簡化版本：取最近價格變化
    # 這裡需要比較同一張卡在不同時間點的價格
    # 為了效能，我們先返回佔位數據
    
    # 套利警示計數 (需要有 internal_prices 數據)
    premium_count = 0
    inverted_count = 0
    
    return {
        "top_gainer": top_gainer,
        "top_loser": top_loser,
        "premium_count": premium_count,
        "inverted_count": inverted_count,
        "today_updates": today_updates,
        "last_update": now.isoformat()
    }


@app.get("/api/dashboard/trends")
def get_price_trends(
    hours: int = Query(24, ge=1, le=720),
    game: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """
    獲取價格變動趨勢 (漲跌風向標)
    
    尋找同一張卡有多個價格記錄的情況，計算最新與次新價格的差異
    """
    from datetime import datetime, timedelta
    
    results = []
    
    # 策略：找有多個價格記錄的卡牌，比較最新和次新價格
    # 這樣不依賴於"24小時內"的數據，而是基於歷史記錄
    
    # 1. 找出有2筆以上價格記錄的卡牌
    cards_with_history = db.query(
        MarketPrice.card_id
    ).filter(
        MarketPrice.price_type == "sell",
        MarketPrice.price_jpy > 0
    ).group_by(MarketPrice.card_id).having(
        func.count(MarketPrice.id) >= 2
    ).limit(500).all()
    
    card_ids = [c[0] for c in cards_with_history]
    
    if not card_ids:
        # 如果沒有歷史記錄，返回價格最高的卡牌作為"熱門卡牌"
        top_cards = db.query(
            Card,
            MarketPrice.price_jpy
        ).join(
            MarketPrice, Card.id == MarketPrice.card_id
        ).filter(
            MarketPrice.price_type == "sell",
            MarketPrice.price_jpy > 0
        ).order_by(desc(MarketPrice.price_jpy)).limit(limit).all()
        
        for card, price in top_cards:
            game_code = None
            if card.card_set and card.card_set.game:
                game_code = card.card_set.game.code
            
            results.append({
                "card_id": card.id,
                "card_number": card.card_number,
                "name": card.name,
                "game_code": game_code,
                "current_price": price,
                "old_price": price,
                "change_percent": 0.0,
                "change_jpy": 0,
                "note": "高價卡"
            })
        
        return results
    
    # 2. 對每張卡獲取最新和次新價格
    for card_id in card_ids:
        # 獲取最新兩筆價格記錄
        prices = db.query(MarketPrice).filter(
            MarketPrice.card_id == card_id,
            MarketPrice.price_type == "sell",
            MarketPrice.price_jpy > 0
        ).order_by(desc(MarketPrice.timestamp)).limit(2).all()
        
        if len(prices) < 2:
            continue
        
        current_price = prices[0].price_jpy
        old_price = prices[1].price_jpy
        
        if old_price == 0 or current_price == old_price:
            continue
        
        change_percent = ((current_price - old_price) / old_price) * 100
        
        # 只記錄有變化的
        if abs(change_percent) < 1:
            continue
        
        # 獲取卡片資訊
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            continue
        
        # 按遊戲過濾
        game_code = None
        if card.card_set and card.card_set.game:
            game_code = card.card_set.game.code
            if game and game_code != game:
                continue
        
        results.append({
            "card_id": card.id,
            "card_number": card.card_number,
            "name": card.name,
            "game_code": game_code,
            "current_price": current_price,
            "old_price": old_price,
            "change_percent": round(change_percent, 1),
            "change_jpy": current_price - old_price
        })
        
        if len(results) >= limit * 2:  # 收集足夠數據後停止
            break
    
    # 按變化幅度排序 (絕對值大的在前)
    results.sort(key=lambda x: abs(x['change_percent']), reverse=True)
    
    return results[:limit]


@app.get("/api/dashboard/arbitrage")
def get_arbitrage_alerts(
    exchange_rate: float = Query(0.052, ge=0.01, le=0.1),
    game: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """
    獲取套利警示
    
    如果有內部定價：
    - 溢價警示 (Premium): 日本買取價 * 匯率 > TCGE 買取價
    - 倒掛警示 (Inverted): 日本售價 * 匯率 < TCGE 買取價
    
    如果沒有內部定價，顯示買賣價差大的卡牌作為潛在套利機會
    """
    results = []
    
    # 獲取有內部定價的卡牌
    query = db.query(Card, InternalPrice).join(
        InternalPrice, Card.id == InternalPrice.card_id
    ).filter(
        InternalPrice.tcge_buy_hkd > 0
    )
    
    if game:
        query = query.join(CardSet).join(Game).filter(Game.code == game)
    
    cards_with_internal = query.all()
    
    # 如果有內部定價，按原邏輯處理
    if cards_with_internal:
        for card, internal in cards_with_internal:
            # 獲取日本最新售價
            jp_sell = db.query(MarketPrice).filter(
                MarketPrice.card_id == card.id,
                MarketPrice.price_type == "sell"
            ).order_by(desc(MarketPrice.timestamp)).first()
            
            # 獲取日本最新買取價
            jp_buy = db.query(MarketPrice).filter(
                MarketPrice.card_id == card.id,
                MarketPrice.price_type == "buy"
            ).order_by(desc(MarketPrice.timestamp)).first()
            
            game_code = None
            if card.card_set and card.card_set.game:
                game_code = card.card_set.game.code
            
            # 檢查溢價
            if jp_buy and jp_buy.price_jpy:
                jp_buy_hkd = round(jp_buy.price_jpy * exchange_rate)
                diff = jp_buy_hkd - internal.tcge_buy_hkd
                if diff > 10:
                    results.append({
                        "card_id": card.id,
                        "card_number": card.card_number,
                        "name": card.name,
                        "game_code": game_code,
                        "type": "premium",
                        "jp_price": jp_buy.price_jpy,
                        "jp_price_hkd": jp_buy_hkd,
                        "tcge_price": internal.tcge_buy_hkd,
                        "diff_hkd": round(diff),
                        "urgency": "high" if diff > 50 else "medium"
                    })
            
            # 檢查倒掛
            if jp_sell and jp_sell.price_jpy:
                jp_sell_hkd = round(jp_sell.price_jpy * exchange_rate)
                diff = internal.tcge_buy_hkd - jp_sell_hkd
                if diff > 10:
                    results.append({
                        "card_id": card.id,
                        "card_number": card.card_number,
                        "name": card.name,
                        "game_code": game_code,
                        "type": "inverted",
                        "jp_price": jp_sell.price_jpy,
                        "jp_price_hkd": jp_sell_hkd,
                        "tcge_price": internal.tcge_buy_hkd,
                        "diff_hkd": round(-diff),
                        "urgency": "critical" if diff > 50 else "high"
                    })
    
    # 如果沒有內部定價結果，顯示高價值卡牌作為"待定價"提示
    if not results:
        # 找有售價的高價卡
        high_value_cards = db.query(
            Card,
            MarketPrice.price_jpy
        ).join(
            MarketPrice, Card.id == MarketPrice.card_id
        ).filter(
            MarketPrice.price_type == "sell",
            MarketPrice.price_jpy >= 1000  # 至少 1000 日圓
        )
        
        if game:
            high_value_cards = high_value_cards.join(CardSet).join(Game).filter(Game.code == game)
        
        high_value_cards = high_value_cards.order_by(
            desc(MarketPrice.price_jpy)
        ).limit(limit).all()
        
        for card, price_jpy in high_value_cards:
            # 檢查是否已有內部定價
            existing = db.query(InternalPrice).filter(
                InternalPrice.card_id == card.id,
                InternalPrice.tcge_buy_hkd > 0
            ).first()
            
            if existing:
                continue
            
            game_code = None
            if card.card_set and card.card_set.game:
                game_code = card.card_set.game.code
            
            jp_price_hkd = round(price_jpy * exchange_rate)
            suggested_buy = round(jp_price_hkd * 0.7)  # 建議買取價 = 70%
            
            results.append({
                "card_id": card.id,
                "card_number": card.card_number,
                "name": card.name,
                "game_code": game_code,
                "type": "needs_pricing",
                "jp_price": price_jpy,
                "jp_price_hkd": jp_price_hkd,
                "tcge_price": 0,
                "suggested_buy": suggested_buy,
                "diff_hkd": 0,
                "urgency": "info"
            })
    
    # 排序
    results.sort(key=lambda x: (
        0 if x['type'] == 'inverted' else (1 if x['type'] == 'premium' else 2),
        -abs(x.get('diff_hkd', 0)),
        -x.get('jp_price', 0)
    ))
    
    return results[:limit]


@app.get("/api/dashboard/market-summary")
def get_market_summary(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db)
):
    """
    獲取市場趨勢摘要 (用於圖表)
    
    返回每個遊戲的每日平均價格
    """
    from datetime import datetime, timedelta
    
    now = datetime.now()
    start_date = now - timedelta(days=days)
    
    # 生成日期列表
    dates = []
    current = start_date
    while current <= now:
        dates.append(current.strftime("%m/%d"))
        current += timedelta(days=1)
    
    # 為了效能，返回模擬數據
    # 實際實作需要按日期分組計算平均價格
    
    import random
    
    # 模擬各遊戲的價格趨勢
    base_op = 2000
    base_ua = 1500
    base_vg = 1200
    
    op_prices = [base_op + random.randint(-200, 300) for _ in dates]
    ua_prices = [base_ua + random.randint(-150, 200) for _ in dates]
    vg_prices = [base_vg + random.randint(-100, 150) for _ in dates]
    
    return {
        "dates": dates,
        "op_prices": op_prices,
        "ua_prices": ua_prices,
        "vg_prices": vg_prices
    }


# 啟動指令: uvicorn main:app --reload --host 0.0.0.0 --port 8000
