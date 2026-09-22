# FastAPI Backend

這是一個基於 FastAPI 的後端專案，結構清楚，適合用來作為 API 服務的基礎模板。

## 專案簡介

本專案包含以下主要模組：

- app
  - 應用程式入口
- api
  - API 路由與端點
- core
  - 核心配置、設定檔、共用邏輯
- models
  - 資料模型 / 資料庫模型

## 技術棧

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy / databases（視實際專案而定）
- Pydantic
- PostgreSQL / SQLite（依環境設定）
- dotenv / Python 環境變數管理

## 專案結構

```text
fastapi-backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   └── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── db.py
│   └── models/
│       ├── __init__.py
│       └── main.py
├── .env
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── venv/
└── ...
```

## 安裝與啟動

### 1. 建立虛擬環境

Windows:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Linux / macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 3. 設定環境變數

複製範例檔：

```bash
copy .env.example .env
```

或 Linux / macOS：

```bash
cp .env.example .env
```

範例內容：

```env
APP_NAME=fastapi-backend
DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///./app.db
```

### 4. 啟動開發伺服器

```bash
uvicorn app.main:app --reload
```

啟動後，預設 API 文件可在以下位置查看：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 常用命令

### 啟動服務

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 安裝新依賴

```bash
pip install package-name
```

### 儲存依賴列表

```bash
pip freeze > requirements.txt
```

## 環境變數說明

以下為常見配置項目，可依專案實際需求調整：

- APP_NAME：專案名稱
- DEBUG：是否開啟 debug 模式
- SECRET_KEY：JWT 或簽名用金鑰
- DATABASE_URL：資料庫連線字串
- ALLOWED_HOSTS：允許的 host
- CORS_ORIGINS：跨域來源設定

## 開發規範

- 不要將 `.env` 檔案提交到 GitHub
- 請保留 `.env.example` 作為範本
- 新增 API 時，建議保持路由與邏輯分離
- 使用 Pydantic 模型做資料驗證
- API 行為請對齊 RESTful 原則

## 部署建議

這個專案可部署於：

- Render
- Railway
- Heroku
- Docker + VPS
- Azure App Service
- AWS EC2 / ECS


## 授權

本專案目前未指定授權條款

## 聯絡方式

