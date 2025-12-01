# TCGE Card Intelligence System (TCGE-CIS) 2.0 - 系統設計藍圖

**版本:** 2.0  
**日期:** 2025-12-01  
**狀態:** 開發中 - Phase 4 進行中

---

## 📊 開發進度總覽

| Phase | 任務 | 狀態 | 完成度 |
|:---:|:---|:---:|:---:|
| **Phase 1** | 基礎建設 | ✅ 完成 | 100% |
| **Phase 2** | 爬蟲重構 | ✅ 完成 | 100% |
| **Phase 3** | 前端開發 | ✅ 完成 | 100% |
| **Phase 4** | 進階功能 | 🔄 進行中 | 70% |

### Phase 4 細項進度

| 功能 | 狀態 | 說明 |
|:---|:---:|:---|
| 買取單系統 UI | ✅ 完成 | `/ai-buy` 頁面已上線 |
| 圖像識別 v4.0 | ✅ 完成 | 多區域 OCR + 知識庫系統 |
| 知識庫建立 | ✅ 完成 | 4款遊戲完整特徵資料 |
| 儀表板 | ⏳ 待開發 | 漲跌風向標、套利警示 |

---

## 📅 開發日誌

### 2025-12-01
- ✅ 建立 `card_knowledge_base.py` 知識庫模組
  - OP: 6色系、費用0-10、力量1000-12000、角色名映射
  - UA: 6色系、BP值、作品代碼(JJK/HTR/TLR等)
  - VG: 國家/氏族、Grade 0-5、力量/盾值、觸發類型
  - DM: 5文明+零、法力費用、生物類型
- ✅ 重構 `main.py` 至 v4.0 識別系統
  - `perform_advanced_ocr()` - 多區域OCR (6個區域)
  - `analyze_card_features_v4()` - 增強色彩分析
  - `detect_game_type()` - 遊戲類型識別
  - `search_cards_by_features_v4()` - 智能搜尋
- ✅ 伺服器運行成功 (port 8000)

### 2025-11-30
- ✅ 完成價格爬蟲整合至 PostgreSQL
  - `price_scraper_akiba_db.py` - 秋葉原價格
  - `price_scraper_uniari_db.py` - Uniari價格
  - `price_scraper_cardrush_db.py` - CardRush價格
- ✅ 資料庫統計: 共 23,978 張卡牌
  - OP: 2,923 張
  - UA: 6,187 張
  - DM: 8,522 張
  - VG: 6,346 張

### 2025-11-29
- ✅ 建立 PostgreSQL 資料庫 `tcge_db`
- ✅ 設計並實作資料模型 (SQLAlchemy ORM)
- ✅ 建立 FastAPI 後端框架
- ✅ 完成 React 前端基礎頁面

---

## 1. 專案願景
將現有的 Google Sheets 自動化流程升級為企業級 Web 應用程式。目標是解決數據量限制、提升查詢速度、優化員工操作體驗，並引入圖像識別與自動化買取流程。

## 2. 核心架構 (Tech Stack)

| 組件 | 技術選擇 | 原因 |
| :--- | :--- | :--- |
| **前端 (Frontend)** | **React.js** 或 **Next.js** | 現代化響應式 UI，操作流暢，組件可重用。 |
| **後端 (Backend)** | **Python FastAPI** | 高效能非同步 API，完美整合現有 Python 爬蟲代碼。 |
| **資料庫 (Database)** | **PostgreSQL** | 關聯式資料庫，輕鬆處理百萬級歷史數據與複雜查詢。 |
| **排程與隊列** | **Celery + Redis** | 背景執行爬蟲任務，確保前台操作不卡頓。 |
| **部署 (Deployment)** | **Docker** | 容器化部署，確保開發與生產環境一致，易於遷移。 |

## 3. 資料庫模型設計 (Database Schema)

系統將從「平面表格」轉向「關聯式模型」，大幅節省空間並提升速度。

### 3.1 核心表 (Core Tables)
*   **`games`**: 遊戲分類 (ID, Name: OP, UA, DM, VG...)
*   **`sets`**: 彈數系列 (ID, GameID, Code: OP01, Name: Romance Dawn...)
*   **`cards`**: 卡牌主檔 (靜態數據，極少變動)
    *   `id` (PK)
    *   `card_number` (e.g., OP01-001)
    *   `name` (e.g., ロロノア・ゾロ)
    *   `version` (e.g., L, Parallel, Promo)
    *   `rarity`
    *   `image_url`
*   **`market_prices`**: 市場價格 (動態數據，頻繁變動)
    *   `id` (PK)
    *   `card_id` (FK -> cards.id)
    *   `source` (e.g., Mercadop, CardRush)
    *   `price_type` (Sell/Buy)
    *   `price_jpy`
    *   `timestamp`
*   **`internal_prices`**: TCGE 內部定價
    *   `card_id` (FK)
    *   `tcge_buy_hkd`
    *   `tcge_sell_hkd`
    *   `updated_at`

## 4. 功能模組詳解

### 4.1 智能搜尋與定價 (Smart Search & Pricing)
*   **即時匯率換算:** 前端提供匯率輸入框，即時計算所有顯示價格。
*   **聚合視圖:** 搜尋 "OP01-001" 時，自動聚合該卡號下所有版本 (L, P, 異圖)，並並列顯示各網站最新價格。
*   **價格趨勢:** 點擊卡片顯示 30 天價格走勢折線圖。

### 4.2 圖像識別買取系統 (AI Buy Order)
*   **流程:** 拍照/上傳 -> OCR/圖像比對 -> 自動識別卡號 -> 填入買取單。
*   **人工介入:** 員工只需確認版本與數量，系統自動計算總額。

### 4.3 市場儀表板 (Market Dashboard)
*   **漲跌風向標:** 監控 24 小時內價格波動劇烈的卡牌。
*   **套利警示:** 
    *   **溢價警示:** 日本買取價 > TCGE 內部買取價 (需提高收購價)。
    *   **倒掛警示:** 日本售價 < TCGE 內部買取價 (需暫停收購或降價)。

## 5. 爬蟲系統升級方案 (Scraper Engine 2.0)

### 5.1 增量更新策略 (Incremental Update)
*   **指紋比對 (Fingerprinting):** 
    *   每次爬蟲抓取數據後，生成一個「數據指紋」(Hash)。
    *   比對資料庫中該卡上一次的指紋。
    *   **若指紋相同:** 代表價格與狀態未變，**不寫入資料庫** (節省空間)。
    *   **若指紋不同:** 寫入新價格記錄。

### 5.2 智能調度
*   **熱門卡頻繁抓:** 針對「風向標」中的熱門卡，每 1 小時抓一次。
*   **冷門卡低頻抓:** 針對舊彈或低價卡，每 24 小時抓一次。

## 6. 開發路線圖 (Roadmap)

| Phase | 任務 | 狀態 |
|:---:|:---|:---:|
| 1 | **基礎建設** - 建立 DB，遷移 Card_Master 數據，建立基礎 API | ✅ 完成 |
| 2 | **爬蟲重構** - 將現有 Python 腳本改寫為寫入 DB，實作增量更新 | ✅ 完成 |
| 3 | **前端開發** - 搜尋介面、價格列表、匯率計算 | ✅ 完成 |
| 4 | **進階功能** - 買取單系統、圖像識別、儀表板 | 🔄 進行中 |

---

## 7. 技術架構詳情

### 7.1 已部署組件
```
c:\projects\TCGE_CIS_2.0\
├── backend\
│   ├── main.py              # FastAPI 主程式 (v4.0)
│   ├── database.py          # PostgreSQL 連線
│   ├── models.py            # SQLAlchemy ORM
│   ├── card_knowledge_base.py   # 卡牌知識庫 ⭐NEW
│   ├── price_scraper_akiba_db.py
│   ├── price_scraper_uniari_db.py
│   └── price_scraper_cardrush_db.py
└── frontend\
    └── src\
        ├── pages\
        │   ├── Search.jsx   # 搜尋頁面
        │   └── AIBuy.jsx    # AI買取頁面
        └── components\
```

### 7.2 資料庫連線
- **Host:** localhost:5432
- **Database:** tcge_db
- **User:** postgres

### 7.3 API 端點
| 端點 | 方法 | 說明 |
|:---|:---:|:---|
| `/cards/search` | GET | 卡牌搜尋 |
| `/cards/{id}/prices` | GET | 價格歷史 |
| `/recognize-card` | POST | 圖像識別 v4.0 |
| `/stats` | GET | 系統統計 |

---

## 8. 下一步計劃

### 短期目標 (本週) - Phase 4 儀表板
- [ ] 完成儀表板 - 漲跌風向標
- [ ] 實作套利警示系統
- [ ] 添加價格趨勢圖表

### 中期目標 (本月)
- [ ] 測試圖像識別系統 (OP14-119 鷹眼)
- [ ] 根據測試結果微調 HSV 色彩範圍
- [ ] 優化 OCR 卡號提取準確度

### 長期目標
- [ ] Docker 容器化部署
- [ ] Celery + Redis 背景任務
- [ ] 多用戶權限管理

---

## 9. 待決定事項 (Pending Decisions)

### 🔮 Phase 5: AI 圖像識別升級 (CLIP + 向量資料庫)

**狀態:** ⏸️ 待決定

**方案概述:**
使用 CLIP 模型 + Milvus 向量資料庫，取代現有 OCR + 知識庫系統
- 預期準確率: 60% → 95%+
- 識別速度: 2-3秒 → <500ms
- 技術: OpenAI CLIP (開源免費) + Milvus (開源免費)

**部署選項:**

| 選項 | 說明 | 費用 |
|:---|:---|:---:|
| **A. 自建伺服器** | 用公司電腦 24 小時運行 | $0 |
| **B. 雲端伺服器** | Linode/DigitalOcean | ~$320-400 HKD/月 |
| **C. 雲端伺服器** | AWS/GCP/Azure | ~$400-650 HKD/月 |

**硬體需求 (自建):**
- CPU: i5 以上
- RAM: 8GB (建議 16GB)
- 硬碟: 50GB SSD
- GPU: 不需要 (有會更快)
- ⚠️ 需要 24 小時開機

**待決定:**
- [ ] 選擇部署方式 (自建 vs 雲端)
- [ ] 確認有無可用電腦作伺服器

**詳細設計文檔:** `AI_Card_Recognition_System_Design.md`
