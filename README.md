# 校園活動管理系統

本專案提供校園活動瀏覽、學生註冊與登入、活動審核發布、活動報名及現場 QR Code 簽到功能，並附有響應式網頁介面。

## 專案簡介

本專案包含以下主要模組：

- app
  - 應用程式入口
- routers
  - API 路由與端點
- core
  - 資料庫連線、資料表初始化與共用邏輯
- models
  - Pydantic 請求／回應模型與列舉定義

## 校園活動首頁

首頁採 mobile-first 響應式版面，包含活動導覽、分類篩選、關鍵字搜尋、活動卡片與詳情視窗。活動由資料庫 API 提供；學生及未登入訪客只能讀取已發布活動，管理員登入後可在首頁使用活動管理區。`app/static/data/activities.json` 僅保留為舊版展示資料，不會作為公開活動資料來源。

活動支援分類、主辦單位、活動起訖時間、報名起訖時間、地點、描述及最大名額。活動資料由管理員手動建立與維護。

## 使用者與權限 API

登入採本系統帳號與密碼，不串接校內 SSO、不寄送驗證信，也不讀取郵件內容。學生註冊僅接受 `s學號@ncnu.edu.tw` 格式，建立後預設為 `student`；這只檢查信箱格式，不能證明帳號屬於本人或仍具在學資格。管理員與簽到人員不可自行註冊，須由管理員建立或更新角色。密碼以 Argon2id 雜湊儲存，最低長度為 12 字元。

首次啟用時，先建立資料庫並以受信任的資料庫管理工具新增至少一名管理員到 `users`。舊版 `external_subject` 欄位會保留為 nullable 相容欄位；帳號以正規化 email 對應。產生初始密碼雜湊（密碼由 getpass 隱藏輸入）：

```powershell
.\venv\Scripts\python.exe -c "from getpass import getpass; from app.core.password_auth import hash_password; print(hash_password(getpass('Initial password: ')))"
```

把輸出的 Argon2id 雜湊填入下方 SQL。管理員登入後可用 `POST /api/admin/users` 建立或更新帳號及角色，新增帳號時需提供至少 12 字元的初始密碼。學生忘記密碼時，目前沒有自助重設或重設郵件功能，請聯絡系統管理員，透過此 API 為帳號設定新密碼。應用程式啟動時會初始化使用者、活動、報名與 session 資料表。

初始管理員資料列範例（替換信箱與產生的 Argon2id 雜湊）：

```sql
INSERT INTO users (email, display_name, role, password_hash)
VALUES ('admin@ncnu.edu.tw', '系統管理員', 'admin', '<argon2id-hash>')
ON CONFLICT (lower(email))
DO UPDATE SET display_name = EXCLUDED.display_name,
              role = EXCLUDED.role,
              password_hash = EXCLUDED.password_hash;
```

角色為 `admin`（管理員）、`student`（學生）及 `checkin`（現場簽到人員）。權限路由如下：

| 操作 | API |
| --- | --- |
| 建立學生帳號 | `POST /api/auth/register` |
| 信箱/密碼登入 | `POST /api/auth/login` |
| 查看登入使用者 | `GET /api/auth/me` |
| 登出並撤銷 session | `POST /api/auth/logout` |
| 瀏覽已發布活動 | `GET /api/activities`、`GET /api/activities/{activity_id}` |
| 學生報名及查看自己的紀錄 | `POST /api/activities/{activity_id}/registrations`、`GET /api/registrations/me` |
| 學生查看單筆專屬 QR Code | `GET /api/registrations/me/{registration_id}/qr`（回傳 SVG） |
| 管理使用者、建立/編輯/廢棄草稿、審核/發布活動、查看統計 | `/api/admin/...` |
| 管理員/簽到人員搜尋報名（姓名、信箱或 Registration ID） | `GET /api/check-in/registrations?activity_id={id}&search={query}` |
| 管理員/簽到人員以 QR token 查詢 | `POST /api/check-in/qr/lookup`，body 包含 `token` 與 `activity_id` |
| 管理員/簽到人員核對後確認簽到 | `POST /api/check-in/registrations/{registration_id}/confirm` |
| 管理員查看報名、簽到、未簽到、剩餘名額與簽到率 | `GET /api/admin/activities/statistics` |
| 簽到人員以 QR token 查詢報名 | `POST /api/check-in/qr/lookup` |

活動狀態流程為「草稿 → 核准 → 發布」；已拒絕的活動可編輯後重新送審或廢棄。任何未發布活動皆可編輯或廢棄，編輯會將狀態重設為草稿並清除舊審核意見；發布後不可透過管理 API 直接修改。拒絕時必須提供審核意見；公開列表、詳情及報名只會使用已發布活動。報名會同時檢查截止時間、名額與重複報名。

個人報名與 QR API 僅接受 `student` session，查詢以登入者的 user ID 限定。QR 內容是以 `SECRET_KEY` 簽署的不可偽造 token，資料庫只保存 token 雜湊；只有本人可取得 QR SVG，管理員或簽到人員可用 `/api/check-in/qr/lookup` 解析。QR 僅供報名查找，現場仍須核對本人與校園照片證件；簽到更新採單次原子操作並記錄時間及操作人員。

現場相機掃碼使用瀏覽器 `BarcodeDetector`，需支援 QR 格式並在 HTTPS 或 localhost 安全來源執行、允許相機權限；不支援的瀏覽器可貼上 QR token 查詢。報名搜尋可輸入姓名、校內信箱或 Registration ID。簽到結果若已由其他工作人員更新，前端會重新查詢實際簽到狀態。

請將 `SECRET_KEY` 換成唯一、至少 32 字元的隨機值；範例佔位值會被登入模組拒絕。正式環境使用 HTTPS，並將 `SESSION_COOKIE_SECURE=True`；登入 session 為資料庫管理的 HttpOnly/SameSite cookie，最長 14 天，登出時立即撤銷。系統只驗證所輸入帳號密碼，不連線學校 Webmail，也不使用校內 SSO 密碼。

## 技術棧

- Python 3.11+
- FastAPI
- Uvicorn
- Pydantic
- PostgreSQL（唯一支援的資料庫）
- psycopg 3（PostgreSQL 驅動；資料存取使用 SQL）
- dotenv / Python 環境變數管理

本專案使用 PostgreSQL 專用 SQL 與資料型別，不支援 SQLite，也未使用 SQLAlchemy ORM。
路由集中於 `app/routers/`；資料驗證模型集中於 `app/models/main.py`；PostgreSQL 連線與資料表初始化由 `app/core/db.py` 管理。

## 專案結構

```text
fastapi-backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── db.py
│   │   ├── password_auth.py
│   │   └── registration_qr.py
│   ├── models/
│   │   └── main.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── notes.py
│   │   ├── system.py
│   │   └── user_access.py
│   └── static/
│       ├── assets/
│       │   ├── css/style.css
│       │   └── js/app.js
│       ├── data/activities.json
│       └── index.html
├── tests/
│   ├── test_activity_model.py
│   ├── test_api_integration.py
│   ├── test_auth_logout.py
│   ├── test_password_auth.py
│   └── test_registration_qr.py
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
└── run.bat
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

請設定 PostgreSQL 連線字串與足夠隨機且至少 32 字元的 `SECRET_KEY`。範例值僅供本機開發，不可用於正式環境。主要設定如下：

```env
DATABASE_URL=postgresql://username:password@localhost:5432/fastapi_db
SECRET_KEY=replace-with-a-unique-random-secret-at-least-32-characters
ROOT_PATH=/s113321021
SESSION_COOKIE_SECURE=False
```

`CORS_ORIGINS` 可設定允許的前端來源；正式環境使用 HTTPS 時，請將 `SESSION_COOKIE_SECURE=True`。若部署於反向代理底下，請讓 `ROOT_PATH` 與實際網址前綴完全一致。

### 4. 啟動開發伺服器

本機開發：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 7777 --reload
```

帶前綴部署：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 7777 --root-path /s113321021 --reload
```

啟動後，預設 API 文件可在以下位置查看：

- Swagger UI: http://localhost:7777/docs
- ReDoc: http://localhost:7777/redoc

若使用反向代理，請務必保持路徑前綴與 `ROOT_PATH` 一致，例如：

- https://demo.wke.csie.ncnu.edu.tw/s113321021/docs
- https://demo.wke.csie.ncnu.edu.tw/s113321021/openapi.json

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

### 執行測試

一般單元測試：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

登入／權限、活動審核發布、報名及簽到的 API 資料庫整合測試需要一個可丟棄的 PostgreSQL 測試資料庫。設定 `TEST_DATABASE_URL` 後再執行同一命令：

```powershell
$env:TEST_DATABASE_URL = "postgresql://user:password@localhost:5432/fastapi_test"
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

整合測試只使用 `TEST_DATABASE_URL`，並在其中建立隨機名稱的隔離 schema；測試結束後會刪除該 schema，不會清空 `DATABASE_URL` 指向的應用程式資料庫。未設定 `TEST_DATABASE_URL` 時，整合測試會明確標記為略過。

## 環境變數說明

- `DATABASE_URL`：PostgreSQL 連線字串；未設定時不會在啟動時初始化資料庫。
- `SECRET_KEY`：用於密碼驗證相關簽名及報名 QR token，需為唯一且至少 32 字元的隨機值。
- `ROOT_PATH`：反向代理公開路徑前綴；本機根目錄部署可設為空字串。
- `CORS_ORIGINS`：JSON 格式的允許來源清單，例如 `["https://example.edu"]`。
- `SESSION_COOKIE_SECURE`：正式 HTTPS 環境應設為 `True`；本機 HTTP 開發可設為 `False`。

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
