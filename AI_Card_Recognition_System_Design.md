# AI 卡片識別系統設計方案

**版本:** 1.0  
**日期:** 2025-12-01  
**作者:** TCGE 技術團隊

---

## 📌 問題分析

你目前的知識庫系統使用的是：
- **OCR + 色彩分析 + 規則匹配** 的傳統方式
- 準確度受限於：OCR 識別率、色彩變異、特徵提取精度

**eBay 等大平台使用的技術：**
- **深度學習圖像嵌入 (Image Embeddings)**
- **向量相似度搜尋 (Vector Similarity Search)**
- **CLIP 多模態模型**

---

## 🚀 推薦方案：三層架構

### 方案對比

| 方案 | 準確度 | 成本 | 開發時間 | 適用場景 |
|:---|:---:|:---:|:---:|:---|
| **方案 A: CLIP + 向量資料庫** | ⭐⭐⭐⭐⭐ | 低 | 1-2 週 | ✅ **推薦** |
| **方案 B: 自訓練 CNN 模型** | ⭐⭐⭐⭐ | 高 | 4-8 週 | 需要極高準確度 |
| **方案 C: 商業 API (Google Vision)** | ⭐⭐⭐⭐ | 中 | 1 週 | 快速上線 |

---

## 📦 方案 A：CLIP + Milvus 向量資料庫 (強烈推薦)

這是 **eBay 使用的核心技術**，適合你的場景：

### 工作原理
```
拍照/上傳圖片 → CLIP 模型提取圖像特徵向量 (512維)
                            ↓
                    向量資料庫 (Milvus/Pinecone)
                            ↓
                    找出最相似的卡片 (Top-5)
                            ↓
                    返回卡號、價格等資訊
```

### 架構圖
```
┌─────────────────────────────────────────────────────────────────┐
│                        用戶界面                                  │
│   📷 拍照上傳 → 預覽裁切 → 識別結果 → 確認卡片 → 加入買取單      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI 後端                               │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐   │
│  │ 圖像預處理    │→ │ CLIP 模型     │→ │ 向量相似度搜尋    │   │
│  │ (裁切/縮放)   │  │ (特徵提取)    │  │ (Milvus/Pinecone) │   │
│  └───────────────┘  └───────────────┘  └───────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        資料層                                    │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ PostgreSQL      │  │ Milvus          │                       │
│  │ (卡片資料/價格) │  │ (圖像向量索引)  │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

### 核心優勢

1. **零樣本學習 (Zero-Shot)**
   - 新卡片上架時，只需將圖片轉成向量存入資料庫
   - 無需重新訓練模型

2. **高準確度**
   - CLIP 在 ImageNet 達到 76.2% 準確度
   - 對於特定領域（卡牌），準確度更高

3. **快速搜尋**
   - Milvus 可在毫秒內搜尋數百萬張卡片
   - 支援 GPU 加速

---

## 🔧 技術實作

### Step 1: 建立卡片向量資料庫

```python
# card_embedding_builder.py
import torch
import clip
from PIL import Image
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType

class CardEmbeddingBuilder:
    def __init__(self):
        # 載入 CLIP 模型
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        
        # 連接 Milvus
        connections.connect("default", host="localhost", port="19530")
    
    def extract_embedding(self, image_path: str) -> list:
        """提取卡片圖像的特徵向量"""
        image = Image.open(image_path)
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            # 正規化向量
            image_features /= image_features.norm(dim=-1, keepdim=True)
        
        return image_features.cpu().numpy()[0].tolist()
    
    def build_index(self, cards_data: list):
        """建立卡片向量索引"""
        # 定義 Collection Schema
        fields = [
            FieldSchema(name="card_id", dtype=DataType.INT64, is_primary=True),
            FieldSchema(name="card_number", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="game_type", dtype=DataType.VARCHAR, max_length=10),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=512)
        ]
        schema = CollectionSchema(fields, "Card Image Embeddings")
        collection = Collection("card_embeddings", schema)
        
        # 批量插入向量
        for card in cards_data:
            embedding = self.extract_embedding(card["image_path"])
            collection.insert([
                [card["id"]],
                [card["card_number"]],
                [card["game_type"]],
                [embedding]
            ])
        
        # 建立 HNSW 索引 (高效近似最近鄰搜尋)
        index_params = {
            "metric_type": "IP",  # 內積 (Inner Product)
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256}
        }
        collection.create_index("embedding", index_params)
        collection.load()
        
        return collection
```

### Step 2: 卡片識別 API

```python
# card_recognizer.py
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from typing import List
import torch
import clip
from PIL import Image
from pymilvus import connections, Collection
import io

class RecognitionResult(BaseModel):
    card_id: int
    card_number: str
    game_type: str
    similarity: float
    name: str
    price_buy: int
    price_sell: int

class CardRecognizer:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        
        connections.connect("default", host="localhost", port="19530")
        self.collection = Collection("card_embeddings")
        self.collection.load()
    
    def recognize(self, image_bytes: bytes, top_k: int = 5) -> List[dict]:
        """識別卡片，返回 Top-K 最相似結果"""
        # 轉換圖像
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)
        
        # 提取特徵向量
        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)
        
        query_vector = image_features.cpu().numpy()[0].tolist()
        
        # 向量相似度搜尋
        search_params = {"metric_type": "IP", "params": {"ef": 128}}
        results = self.collection.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["card_id", "card_number", "game_type"]
        )
        
        # 格式化結果
        matches = []
        for hit in results[0]:
            matches.append({
                "card_id": hit.entity.get("card_id"),
                "card_number": hit.entity.get("card_number"),
                "game_type": hit.entity.get("game_type"),
                "similarity": hit.distance  # 相似度分數 (0-1)
            })
        
        return matches

# FastAPI 端點
app = FastAPI()
recognizer = CardRecognizer()

@app.post("/api/v2/recognize-card", response_model=List[RecognitionResult])
async def recognize_card(file: UploadFile = File(...)):
    """
    V2 版卡片識別 API
    使用 CLIP + Milvus 向量搜尋
    """
    image_bytes = await file.read()
    matches = recognizer.recognize(image_bytes, top_k=5)
    
    # 從 PostgreSQL 獲取詳細資訊
    results = []
    for match in matches:
        # 查詢卡片詳細資訊和價格
        card_info = get_card_details(match["card_id"])  # 你現有的資料庫查詢
        results.append(RecognitionResult(
            **match,
            name=card_info["name"],
            price_buy=card_info["buy_price"],
            price_sell=card_info["sell_price"]
        ))
    
    return results
```

### Step 3: 前端整合

```jsx
// AIBuyV2.jsx - 新版 AI 買取頁面
import React, { useState, useRef } from 'react';

function AIBuyV2() {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedCard, setSelectedCard] = useState(null);
  const videoRef = useRef(null);

  const handleCapture = async () => {
    setLoading(true);
    
    // 從相機或上傳獲取圖片
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    canvas.getContext('2d').drawImage(videoRef.current, 0, 0);
    
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
    const formData = new FormData();
    formData.append('file', blob, 'card.jpg');
    
    try {
      const response = await fetch('/api/v2/recognize-card', {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      setResults(data);
    } catch (error) {
      console.error('識別失敗:', error);
    }
    
    setLoading(false);
  };

  return (
    <div className="ai-buy-v2">
      <div className="camera-section">
        <video ref={videoRef} autoPlay playsInline />
        <button onClick={handleCapture} disabled={loading}>
          {loading ? '識別中...' : '📷 拍攝識別'}
        </button>
      </div>
      
      <div className="results-section">
        <h3>識別結果 (Top 5)</h3>
        {results.map((result, index) => (
          <div 
            key={result.card_id}
            className={`result-card ${selectedCard?.card_id === result.card_id ? 'selected' : ''}`}
            onClick={() => setSelectedCard(result)}
          >
            <span className="rank">#{index + 1}</span>
            <span className="similarity">{(result.similarity * 100).toFixed(1)}%</span>
            <span className="card-number">{result.card_number}</span>
            <span className="name">{result.name}</span>
            <span className="price">¥{result.price_buy}</span>
          </div>
        ))}
      </div>
      
      {selectedCard && (
        <div className="confirm-section">
          <h3>確認卡片</h3>
          <p>{selectedCard.card_number} - {selectedCard.name}</p>
          <button onClick={() => addToBuyList(selectedCard)}>
            ✅ 加入買取單
          </button>
        </div>
      )}
    </div>
  );
}
```

---

## 📊 持續學習機制

### 1. 用戶回饋學習

```python
# feedback_learning.py
class FeedbackLearner:
    """
    收集用戶確認/修正的結果
    用於微調模型和改善識別
    """
    
    def record_feedback(self, image_hash: str, predicted: str, corrected: str):
        """
        記錄用戶的修正行為
        - image_hash: 圖片哈希值
        - predicted: 系統預測的卡號
        - corrected: 用戶修正後的卡號 (None 表示預測正確)
        """
        if corrected and predicted != corrected:
            # 儲存錯誤案例用於後續分析
            self.save_error_case(image_hash, predicted, corrected)
            
            # 更新卡片的特徵向量 (增強學習)
            self.update_embedding_weight(corrected, boost=1.2)
    
    def retrain_monthly(self):
        """
        每月基於收集的回饋數據微調模型
        """
        error_cases = self.load_error_cases()
        if len(error_cases) > 100:
            # 使用對比學習微調 CLIP
            self.finetune_clip(error_cases)
```

### 2. 新卡自動入庫

```python
# auto_indexer.py
class AutoCardIndexer:
    """
    當爬蟲抓取到新卡資料時
    自動下載卡圖並建立向量索引
    """
    
    async def index_new_cards(self, new_cards: list):
        for card in new_cards:
            # 下載卡圖
            image_path = await self.download_card_image(card["image_url"])
            
            # 提取向量
            embedding = self.embedding_builder.extract_embedding(image_path)
            
            # 插入向量資料庫
            self.collection.insert([
                [card["id"]],
                [card["card_number"]],
                [card["game_type"]],
                [embedding]
            ])
        
        # 重建索引
        self.collection.release()
        self.collection.load()
```

---

## 🛠️ 部署需求

### 硬體需求

| 組件 | 最低配置 | 推薦配置 |
|:---|:---|:---|
| CPU | 4 核心 | 8 核心 |
| RAM | 8 GB | 16 GB |
| GPU | 無 (CPU 推理) | NVIDIA GTX 1060+ |
| 儲存 | 50 GB SSD | 100 GB SSD |

### 軟體依賴

```bash
# requirements.txt
torch>=2.0.0
clip-by-openai
Pillow>=9.0.0
pymilvus>=2.3.0
fastapi>=0.100.0
uvicorn>=0.22.0
```

### Docker 部署

```yaml
# docker-compose.yml
version: '3.8'

services:
  milvus:
    image: milvusdb/milvus:v2.3.0
    ports:
      - "19530:19530"
    volumes:
      - milvus_data:/var/lib/milvus
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000

  etcd:
    image: quay.io/coreos/etcd:v3.5.0

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin

  card-recognizer:
    build: ./backend
    ports:
      - "8001:8000"
    depends_on:
      - milvus
    environment:
      MILVUS_HOST: milvus
      MILVUS_PORT: 19530

volumes:
  milvus_data:
```

---

## 📈 預期效果

| 指標 | 當前 v4.0 | 預期 v5.0 (CLIP) |
|:---|:---:|:---:|
| 識別準確率 | ~60% | 95%+ |
| 識別速度 | 2-3 秒 | <500ms |
| 支援版本區分 | ❌ | ✅ (異圖/普卡) |
| 光線適應性 | 弱 | 強 |
| 角度容錯 | 弱 | 中等 |

---

## 🗓️ 實施路線圖

### Phase 1 (第 1 週)
- [ ] 安裝 Milvus 向量資料庫
- [ ] 下載所有卡片圖片 (約 24,000 張)
- [ ] 建立初始向量索引

### Phase 2 (第 2 週)
- [ ] 開發 v2 識別 API
- [ ] 整合前端 AIBuy 頁面
- [ ] 內部測試

### Phase 3 (第 3-4 週)
- [ ] 收集用戶回饋
- [ ] 優化識別邊緣案例
- [ ] 正式上線

---

## 💡 進階優化 (未來)

1. **多視角識別**
   - 支援卡片正面/背面
   - 支援多張卡片批量識別

2. **條碼輔助**
   - 結合條碼掃描提高準確度
   - 條碼 → 卡號 → 向量驗證

3. **本地離線模型**
   - 將模型輕量化 (MobileNet + ONNX)
   - 支援離線使用

---

## ❓ 常見問題

**Q: 需要 GPU 嗎？**
A: 不需要。CPU 推理速度約 200-500ms，足夠使用。GPU 可加速至 50ms。

**Q: 如何處理相似卡片 (同卡不同版本)？**
A: CLIP 可以區分細微差異。對於極相似的卡片，返回 Top-5 讓用戶選擇。

**Q: 訓練需要多少數據？**
A: **不需要訓練**！CLIP 是預訓練模型，直接使用。我們只需建立圖片向量庫。

**Q: 成本多少？**
A: 
- Milvus: 開源免費
- 伺服器: 約 $50-100/月 (雲端)
- 無 API 調用費用

---

## 📚 參考資料

- [OpenAI CLIP 論文](https://arxiv.org/abs/2103.00020)
- [Milvus 官方文檔](https://milvus.io/docs)
- [Pinecone Image Search 教程](https://www.pinecone.io/learn/series/image-search/)
- [eBay 圖像識別技術博客](https://tech.ebayinc.com/)
