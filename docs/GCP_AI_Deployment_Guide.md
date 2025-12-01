# 🚀 GCP 免費層 AI 卡牌辨識系統部署指南

> 本指南將帶你從零開始，在 Google Cloud Platform 上部署 CLIP + Milvus 卡牌辨識系統，完全使用免費層資源。

---

## 📋 目錄

1. [準備工作](#1-準備工作)
2. [建立 GCP 帳號](#2-建立-gcp-帳號)
3. [建立免費 VM 實例](#3-建立免費-vm-實例)
4. [連接到 VM](#4-連接到-vm)
5. [安裝系統環境](#5-安裝系統環境)
6. [部署 AI 辨識服務](#6-部署-ai-辨識服務)
7. [設定開機自動啟動](#7-設定開機自動啟動)
8. [測試與驗證](#8-測試與驗證)
9. [連接到本地系統](#9-連接到本地系統)
10. [監控與維護](#10-監控與維護)

---

## 1. 準備工作

### 你需要準備：
- ✅ 一個 Google 帳號 (Gmail)
- ✅ 一張信用卡/扣帳卡 (僅作驗證，不會收費)
- ✅ 約 30-60 分鐘的時間

### 預期結果：
- 🎯 一個 24/7 運行的免費 AI 伺服器
- 🎯 可處理每日數千次卡牌辨識請求
- 🎯 月費用：$0

---

## 2. 建立 GCP 帳號

### 步驟 2.1：前往 GCP 官網

1. 開啟瀏覽器，前往：https://cloud.google.com/
2. 點擊右上角 **「免費開始使用」** 或 **「Get started for free」**

### 步驟 2.2：登入 Google 帳號

1. 使用你的 Gmail 帳號登入
2. 如果沒有，先建立一個 Gmail 帳號

### 步驟 2.3：填寫註冊資訊

1. **國家/地區**：選擇 `香港` 或你所在地區
2. **帳號類型**：選擇 `個人` (Individual)
3. **付款資料**：
   - 輸入信用卡/扣帳卡資訊
   - ⚠️ **放心**：這只是身份驗證，免費層不會收費
   - Google 會先扣 $1 USD 驗證，然後立即退還

### 步驟 2.4：獲得免費額度

註冊成功後，你會獲得：
- 💰 **$300 USD 免費試用額度** (90 天內使用)
- 💰 **永久免費層資源** (Always Free)

---

## 3. 建立免費 VM 實例

### 步驟 3.1：進入 Compute Engine

1. 登入 GCP Console：https://console.cloud.google.com/
2. 左側選單點擊 **「Compute Engine」** → **「VM instances」**
3. 如果是第一次使用，等待 API 啟用 (約 1-2 分鐘)

### 步驟 3.2：建立新的 VM

1. 點擊上方 **「CREATE INSTANCE」** 按鈕

### 步驟 3.3：配置 VM (重要！)

請完全按照以下設定，才能保持免費：

```
┌─────────────────────────────────────────────────────────────┐
│  基本設定                                                    │
├─────────────────────────────────────────────────────────────┤
│  Name (名稱):           tcge-ai-server                      │
│  Region (地區):         us-west1 (Oregon)     ⚠️ 重要！      │
│  Zone (區域):           us-west1-b                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  機器配置                                                    │
├─────────────────────────────────────────────────────────────┤
│  Series (系列):         E2                                  │
│  Machine type:          e2-micro (2 vCPU, 1 GB memory)      │
│                         ⚠️ 必須選這個才免費！                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  開機磁碟 (Boot disk) - 點擊「Change」修改                   │
├─────────────────────────────────────────────────────────────┤
│  Operating system:      Ubuntu                              │
│  Version:               Ubuntu 22.04 LTS                    │
│  Boot disk type:        Standard persistent disk            │
│  Size (GB):             30    ⚠️ 免費額度上限                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  防火牆 (Firewall)                                          │
├─────────────────────────────────────────────────────────────┤
│  ☑️ Allow HTTP traffic                                      │
│  ☑️ Allow HTTPS traffic                                     │
└─────────────────────────────────────────────────────────────┘
```

### ⚠️ 免費層地區限制

只有以下地區的 e2-micro 是免費的：
- `us-west1` (Oregon) ✅ 推薦
- `us-central1` (Iowa)
- `us-east1` (South Carolina)

### 步驟 3.4：建立 VM

1. 確認右側顯示 **「$0.00/month estimate」** 或接近 $0
2. 點擊 **「Create」** 建立

等待 1-2 分鐘，VM 就會建立完成。

---

## 4. 連接到 VM

### 步驟 4.1：使用瀏覽器 SSH

1. 在 VM 列表中找到 `tcge-ai-server`
2. 點擊 **「SSH」** 按鈕 (在 Connect 欄位)
3. 會開啟一個新視窗，自動連接到 VM

### 步驟 4.2：確認連接成功

你會看到類似這樣的畫面：
```
Welcome to Ubuntu 22.04 LTS
yourname@tcge-ai-server:~$
```

恭喜！你已經成功連接到你的免費雲端伺服器！

---

## 5. 安裝系統環境

在 SSH 視窗中，依次執行以下指令：

### 步驟 5.1：更新系統

```bash
sudo apt update && sudo apt upgrade -y
```

### 步驟 5.2：安裝 Python 3.10+

```bash
sudo apt install -y python3 python3-pip python3-venv
```

### 步驟 5.3：安裝 Docker (用於 Milvus)

```bash
# 安裝 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 將當前用戶加入 docker 群組
sudo usermod -aG docker $USER

# 安裝 Docker Compose
sudo apt install -y docker-compose

# 重新登入以套用群組變更
exit
```

退出後，再次點擊 **「SSH」** 重新連接。

### 步驟 5.4：驗證安裝

```bash
python3 --version    # 應該顯示 Python 3.10+
docker --version     # 應該顯示 Docker 24+
docker-compose --version
```

---

## 6. 部署 AI 辨識服務

### 步驟 6.1：建立專案目錄

```bash
mkdir -p ~/tcge-ai
cd ~/tcge-ai
```

### 步驟 6.2：建立 Docker Compose 檔案 (Milvus Lite)

由於 e2-micro 記憶體有限，我們使用輕量級配置：

```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # Milvus Lite - 單機版向量資料庫
  milvus:
    image: milvusdb/milvus:v2.3.3
    container_name: milvus-standalone
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_USE_EMBED: "true"
      ETCD_DATA_DIR: "/var/lib/milvus/etcd"
      COMMON_STORAGETYPE: "local"
    volumes:
      - ./milvus-data:/var/lib/milvus
    ports:
      - "19530:19530"
      - "9091:9091"
    deploy:
      resources:
        limits:
          memory: 512M
    restart: unless-stopped

  # AI 辨識 API 服務
  ai-api:
    build: ./ai-service
    container_name: tcge-ai-api
    ports:
      - "8080:8080"
    environment:
      - MILVUS_HOST=milvus
      - MILVUS_PORT=19530
    depends_on:
      - milvus
    deploy:
      resources:
        limits:
          memory: 400M
    restart: unless-stopped
EOF
```

### 步驟 6.3：建立 AI 服務程式碼

```bash
mkdir -p ai-service
cat > ai-service/Dockerfile << 'EOF'
FROM python:3.10-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 複製並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 預下載 CLIP 模型 (在建構時下載，節省啟動時間)
RUN python -c "import clip; clip.load('ViT-B/32', device='cpu')"

EXPOSE 8080

CMD ["python", "app.py"]
EOF
```

### 步驟 6.4：建立 Python 依賴檔案

```bash
cat > ai-service/requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn==0.24.0
pillow==10.1.0
numpy==1.24.3
torch==2.1.0+cpu
torchvision==0.16.0+cpu
ftfy==6.1.1
regex==2023.10.3
tqdm==4.66.1
pymilvus==2.3.3
python-multipart==0.0.6
--extra-index-url https://download.pytorch.org/whl/cpu
git+https://github.com/openai/CLIP.git
EOF
```

### 步驟 6.5：建立主程式

```bash
cat > ai-service/app.py << 'EOF'
"""
TCGE AI 卡牌辨識服務
使用 CLIP 模型進行圖像特徵提取，Milvus 進行向量搜索
"""

import os
import io
import base64
import logging
from typing import Optional, List
from datetime import datetime

import numpy as np
import torch
import clip
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymilvus import (
    connections, Collection, FieldSchema, 
    CollectionSchema, DataType, utility
)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境變數
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
COLLECTION_NAME = "card_images"
EMBEDDING_DIM = 512  # CLIP ViT-B/32 輸出維度

# 初始化 FastAPI
app = FastAPI(
    title="TCGE AI Card Recognition API",
    description="使用 CLIP + Milvus 的卡牌圖像辨識服務",
    version="1.0.0"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全域變數
model = None
preprocess = None
device = None
collection = None

# ============ 資料模型 ============

class CardMatch(BaseModel):
    card_id: int
    card_number: str
    name: str
    similarity: float
    image_url: Optional[str] = None

class RecognitionResult(BaseModel):
    success: bool
    matches: List[CardMatch]
    processing_time_ms: int
    message: Optional[str] = None

class CardRegistration(BaseModel):
    card_id: int
    card_number: str
    name: str
    image_url: Optional[str] = None

# ============ 初始化 ============

@app.on_event("startup")
async def startup():
    """應用啟動時初始化模型和資料庫連接"""
    global model, preprocess, device, collection
    
    logger.info("🚀 正在初始化 AI 服務...")
    
    # 1. 載入 CLIP 模型
    logger.info("📦 載入 CLIP 模型...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess = clip.load("ViT-B/32", device=device)
    model.eval()
    logger.info(f"✅ CLIP 模型載入完成 (使用 {device})")
    
    # 2. 連接 Milvus
    logger.info("🔗 連接 Milvus 向量資料庫...")
    try:
        connections.connect(
            alias="default",
            host=MILVUS_HOST,
            port=MILVUS_PORT,
            timeout=30
        )
        logger.info("✅ Milvus 連接成功")
    except Exception as e:
        logger.warning(f"⚠️ Milvus 連接失敗: {e}，將在首次請求時重試")
    
    # 3. 初始化或載入集合
    await init_collection()
    
    logger.info("🎉 AI 服務初始化完成！")

async def init_collection():
    """初始化 Milvus 集合"""
    global collection
    
    try:
        if utility.has_collection(COLLECTION_NAME):
            collection = Collection(COLLECTION_NAME)
            collection.load()
            logger.info(f"✅ 載入現有集合: {COLLECTION_NAME}")
        else:
            # 建立新集合
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="card_id", dtype=DataType.INT64),
                FieldSchema(name="card_number", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=200),
                FieldSchema(name="image_url", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
            ]
            schema = CollectionSchema(fields, description="Card image embeddings")
            collection = Collection(COLLECTION_NAME, schema)
            
            # 建立索引
            index_params = {
                "metric_type": "IP",  # Inner Product (餘弦相似度)
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            collection.create_index("embedding", index_params)
            collection.load()
            logger.info(f"✅ 建立新集合: {COLLECTION_NAME}")
    except Exception as e:
        logger.error(f"❌ 集合初始化失敗: {e}")

# ============ 圖像處理 ============

def extract_embedding(image: Image.Image) -> np.ndarray:
    """從圖像提取 CLIP 特徵向量"""
    global model, preprocess, device
    
    # 預處理圖像
    image_input = preprocess(image).unsqueeze(0).to(device)
    
    # 提取特徵
    with torch.no_grad():
        features = model.encode_image(image_input)
        # 正規化
        features = features / features.norm(dim=-1, keepdim=True)
    
    return features.cpu().numpy().flatten()

# ============ API 端點 ============

@app.get("/")
async def root():
    """健康檢查"""
    return {
        "status": "running",
        "service": "TCGE AI Card Recognition",
        "version": "1.0.0",
        "model": "CLIP ViT-B/32",
        "milvus_connected": collection is not None
    }

@app.get("/health")
async def health_check():
    """詳細健康狀態"""
    milvus_ok = False
    card_count = 0
    
    try:
        if collection:
            card_count = collection.num_entities
            milvus_ok = True
    except:
        pass
    
    return {
        "status": "healthy" if milvus_ok else "degraded",
        "components": {
            "clip_model": model is not None,
            "milvus": milvus_ok,
            "cards_indexed": card_count
        }
    }

@app.post("/recognize", response_model=RecognitionResult)
async def recognize_card(
    file: UploadFile = File(...),
    top_k: int = 5
):
    """
    辨識上傳的卡牌圖片
    
    - **file**: 卡牌圖片 (JPG/PNG)
    - **top_k**: 返回最相似的前 K 張卡
    """
    import time
    start_time = time.time()
    
    try:
        # 1. 讀取和處理圖片
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        
        # 2. 提取特徵向量
        embedding = extract_embedding(image)
        
        # 3. 在 Milvus 中搜索
        if collection is None or collection.num_entities == 0:
            return RecognitionResult(
                success=False,
                matches=[],
                processing_time_ms=int((time.time() - start_time) * 1000),
                message="知識庫為空，請先註冊卡牌圖片"
            )
        
        search_params = {"metric_type": "IP", "params": {"nprobe": 16}}
        results = collection.search(
            data=[embedding.tolist()],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["card_id", "card_number", "name", "image_url"]
        )
        
        # 4. 整理結果
        matches = []
        for hits in results:
            for hit in hits:
                matches.append(CardMatch(
                    card_id=hit.entity.get("card_id"),
                    card_number=hit.entity.get("card_number"),
                    name=hit.entity.get("name"),
                    similarity=round(float(hit.score) * 100, 2),  # 轉換為百分比
                    image_url=hit.entity.get("image_url")
                ))
        
        processing_time = int((time.time() - start_time) * 1000)
        
        return RecognitionResult(
            success=True,
            matches=matches,
            processing_time_ms=processing_time,
            message=f"找到 {len(matches)} 個匹配結果"
        )
        
    except Exception as e:
        logger.error(f"辨識錯誤: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/register")
async def register_card(
    card_id: int,
    card_number: str,
    name: str,
    file: UploadFile = File(...),
    image_url: Optional[str] = None
):
    """
    註冊新卡牌到知識庫
    
    - **card_id**: 卡牌 ID
    - **card_number**: 卡號 (如 OP01-001)
    - **name**: 卡牌名稱
    - **file**: 卡牌圖片
    - **image_url**: 圖片 URL (可選)
    """
    try:
        # 1. 讀取圖片
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        
        # 2. 提取特徵
        embedding = extract_embedding(image)
        
        # 3. 插入到 Milvus
        data = [
            [card_id],
            [card_number],
            [name],
            [image_url or ""],
            [embedding.tolist()]
        ]
        
        collection.insert(data)
        collection.flush()
        
        return {
            "success": True,
            "message": f"卡牌 {card_number} 已成功註冊",
            "total_cards": collection.num_entities
        }
        
    except Exception as e:
        logger.error(f"註冊錯誤: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/register-batch")
async def register_batch(cards: List[dict]):
    """
    批量註冊卡牌 (用於初始化知識庫)
    
    每個卡牌需要: card_id, card_number, name, image_base64
    """
    registered = 0
    errors = []
    
    for card in cards:
        try:
            # 解碼 Base64 圖片
            image_data = base64.b64decode(card["image_base64"])
            image = Image.open(io.BytesIO(image_data)).convert("RGB")
            
            # 提取特徵
            embedding = extract_embedding(image)
            
            # 插入
            data = [
                [card["card_id"]],
                [card["card_number"]],
                [card["name"]],
                [card.get("image_url", "")],
                [embedding.tolist()]
            ]
            collection.insert(data)
            registered += 1
            
        except Exception as e:
            errors.append({"card_id": card.get("card_id"), "error": str(e)})
    
    collection.flush()
    
    return {
        "success": True,
        "registered": registered,
        "errors": errors,
        "total_cards": collection.num_entities
    }

@app.get("/stats")
async def get_stats():
    """獲取知識庫統計"""
    return {
        "total_cards": collection.num_entities if collection else 0,
        "model": "CLIP ViT-B/32",
        "embedding_dim": EMBEDDING_DIM,
        "milvus_host": MILVUS_HOST
    }

@app.delete("/clear")
async def clear_collection():
    """清空知識庫 (謹慎使用)"""
    global collection
    
    try:
        if collection:
            utility.drop_collection(COLLECTION_NAME)
            await init_collection()
            return {"success": True, "message": "知識庫已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ 啟動服務 ============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
EOF
```

### 步驟 6.6：啟動服務

```bash
cd ~/tcge-ai

# 首次啟動 (會下載映像檔，約需 5-10 分鐘)
docker-compose up -d

# 查看日誌
docker-compose logs -f
```

等待看到以下訊息表示啟動成功：
```
tcge-ai-api | 🎉 AI 服務初始化完成！
tcge-ai-api | INFO: Uvicorn running on http://0.0.0.0:8080
```

按 `Ctrl+C` 退出日誌查看。

---

## 7. 設定開機自動啟動

```bash
# 建立 systemd 服務
sudo tee /etc/systemd/system/tcge-ai.service << 'EOF'
[Unit]
Description=TCGE AI Card Recognition Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/$USER/tcge-ai
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
User=$USER

[Install]
WantedBy=multi-user.target
EOF

# 啟用服務
sudo systemctl enable tcge-ai
sudo systemctl start tcge-ai
```

---

## 8. 測試與驗證

### 步驟 8.1：取得 VM 外部 IP

1. 回到 GCP Console → Compute Engine → VM instances
2. 找到 `tcge-ai-server`，記下 **External IP** (例如: `35.xxx.xxx.xxx`)

### 步驟 8.2：設定防火牆規則

1. 左側選單 → **VPC network** → **Firewall**
2. 點擊 **CREATE FIREWALL RULE**
3. 設定如下：

```
Name:           allow-tcge-ai
Direction:      Ingress
Targets:        All instances in the network
Source IP:      0.0.0.0/0
Protocols:      TCP: 8080
```

4. 點擊 **Create**

### 步驟 8.3：測試 API

在你的本機瀏覽器開啟：

```
http://35.xxx.xxx.xxx:8080/
```

應該看到：
```json
{
  "status": "running",
  "service": "TCGE AI Card Recognition",
  "version": "1.0.0"
}
```

### 步驟 8.4：測試辨識功能

使用 curl 或 Postman：

```bash
# 測試健康狀態
curl http://35.xxx.xxx.xxx:8080/health

# 測試辨識 (需要先註冊卡牌)
curl -X POST http://35.xxx.xxx.xxx:8080/recognize \
  -F "file=@test_card.jpg" \
  -F "top_k=5"
```

---

## 9. 連接到本地系統

### 步驟 9.1：更新本地 TCGE 系統

在你的 Windows 電腦上，修改 `main.py` 中的 AI 辨識配置：

```python
# 在 main.py 頂部添加
AI_SERVICE_URL = "http://35.xxx.xxx.xxx:8080"  # 替換為你的 GCP IP

# 修改辨識函數
async def recognize_card_cloud(image_file):
    """使用雲端 AI 服務辨識卡牌"""
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field('file', image_file, filename='card.jpg')
        data.add_field('top_k', '5')
        
        async with session.post(f"{AI_SERVICE_URL}/recognize", data=data) as resp:
            result = await resp.json()
            return result
```

### 步驟 9.2：同步知識庫

建立一個腳本將本地卡牌圖片同步到雲端：

```python
# sync_knowledge_base.py
import requests
import base64
from pathlib import Path

AI_SERVICE_URL = "http://35.xxx.xxx.xxx:8080"

def sync_card(card_id, card_number, name, image_path):
    """同步單張卡牌到雲端"""
    with open(image_path, 'rb') as f:
        files = {'file': f}
        data = {
            'card_id': card_id,
            'card_number': card_number,
            'name': name
        }
        response = requests.post(
            f"{AI_SERVICE_URL}/register",
            files=files,
            data=data
        )
        return response.json()

# 使用範例
# sync_card(1, "OP01-001", "路飛", "images/op01-001.jpg")
```

---

## 10. 監控與維護

### 查看服務狀態

```bash
# SSH 進入 VM 後
cd ~/tcge-ai
docker-compose ps
docker-compose logs --tail=100
```

### 重啟服務

```bash
docker-compose restart
```

### 查看資源使用

```bash
docker stats
```

### 備份知識庫

```bash
# 備份 Milvus 數據
tar -czf milvus-backup-$(date +%Y%m%d).tar.gz ~/tcge-ai/milvus-data
```

### 監控免費額度

1. GCP Console → **Billing** → **Budgets & alerts**
2. 設定當費用接近免費額度時發送警報

---

## ❓ 常見問題

### Q1: VM 很慢怎麼辦？

e2-micro 的 CPU 是共享的，首次載入模型會較慢。之後的辨識速度約 1-3 秒/張。

### Q2: 如何升級配置？

如果需要更快的速度，可以升級到 e2-small 或 e2-medium，但會產生費用。

### Q3: 記憶體不足怎麼辦？

可以添加 swap 空間：
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Q4: 如何使用固定 IP？

GCP Console → VPC network → External IP addresses → 將 IP 從「臨時」改為「靜態」。
注意：靜態 IP 在 VM 關機時會收費。

---

## 📊 成本預估

| 資源 | 配置 | 每月費用 |
|------|------|---------|
| e2-micro VM | 24/7 運行 | $0 (免費) |
| 30GB 標準硬碟 | 永久使用 | $0 (免費) |
| 網路流量 | <1GB 出站 | $0 (免費) |
| **總計** | | **$0** |

---

## 🎉 完成！

恭喜你已經成功在 GCP 上部署了 AI 卡牌辨識系統！

現在你的店舖可以：
- ✅ 24/7 使用 AI 辨識卡牌
- ✅ 每日處理數千次辨識請求
- ✅ 完全免費運行

如有問題，請參考 [GCP 官方文檔](https://cloud.google.com/docs) 或聯繫支援。
