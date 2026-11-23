# 校園活動管理系統

以 FastAPI、PostgreSQL 與原生前端 JavaScript 建立的校園活動管理系統。系統提供活動瀏覽、學生報名、管理員審核與發布、現場簽到，以及個人報名 QR Code。

前端採 responsive mobile-first 設計，FastAPI 同時提供靜態頁面與 API。正式資料來源是 PostgreSQL，`app/static/data/activities.json` 不再作為公開活動資料來源。

## 主要功能

- 活動分類、關鍵字搜尋、活動詳情與報名人數瀏覽
- 學生帳號註冊、登入、登出及個人報名紀錄
- 管理員建立、編輯、審核、發布、封存活動
- 草稿、核准、拒絕、發布、封存等活動狀態流程
- 管理員指派與撤銷現場簽到人員
- 報名 QR Code、QR token 查詢與原子化簽到確認
- 報名統計，包括報名、簽到、未簽到、剩餘名額與簽到率
- 完整的 session、登入嘗試及密碼雜湊處理

## 技術棧

- Python 3.11+
- FastAPI、Uvicorn
- Pydantic
- PostgreSQL
- psycopg 3 binary driver
- Argon2 password hashing
- segno QR Code 產生
- python-dotenv
- 原生 HTML、CSS 與 JavaScript

本專案使用 PostgreSQL 專用 SQL，不支援 SQLite，也未使用 SQLAlchemy ORM。

## 專案結構

```text
fastapi-backend/
├── app/
│   ├── core/
│   │   ├── db.py                 # PostgreSQL 連線與資料表初始化
│   │   ├── password_auth.py      # 密碼雜湊、session 與權限驗證
│   │   └── registration_qr.py    # 報名 QR token 與 SVG
│   ├── models/
│   │   └── main.py               # Pydantic 請求及回應模型
│   ├── routers/
│   │   ├── auth.py               # 註冊、登入、登出
│   │   ├── notes.py              # Notes CRUD 範例 API
│   │   ├── system.py             # health、version
│   │   └── user_access.py        # 活動、報名、管理與簽到 API
│   ├── static/
│   │   ├── assets/css/style.css
│   │   ├── assets/js/app.js
│   │   ├── data/activities.json
│   │   └── index.html
│   └── main.py                   # FastAPI app、靜態檔案與啟動初始化
├── tests/
│   ├── test_activity_model.py
│   ├── test_api_integration.py
│   ├── test_auth_logout.py
│   ├── test_password_auth.py
│   └── test_registration_qr.py
├── .env.example
├── README.md
├── requirements.txt
└── run.bat
```

啟動時會自動建立或補齊所需資料表，包括使用者、session、登入嘗試、活動、報名、活動人員及備註資料表。

## 安裝與啟動

### 1. 建立虛擬環境

Windows：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Linux / macOS：

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 3. 設定環境變數

複製範例設定：

```powershell
Copy-Item .env.example .env
```

Linux / macOS：

```bash
cp .env.example .env
```

主要設定：

```env
DATABASE_URL=postgresql://username:password@localhost:5432/fastapi_db
SECRET_KEY=replace-with-a-unique-random-secret-at-least-32-characters
ROOT_PATH=/s113321021
SESSION_COOKIE_SECURE=False
CORS_ORIGINS=["http://localhost:3000"]
```

可從 `.env.example` 開始設定。`DATABASE_URL` 未設定時，應用程式仍可啟動，但需要資料庫時會回報錯誤且不會執行資料表初始化。

`SECRET_KEY` 必須是唯一且至少 32 字元的隨機值；範例佔位值會被登入與 QR 模組拒絕。正式環境應使用 HTTPS 並設定 `SESSION_COOKIE_SECURE=True`。`ROOT_PATH` 必須與反向代理公開前綴一致。

### 4. 啟動開發伺服器

使用預設子路徑：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 7777 --root-path /s113321021 --reload
```

也可直接執行 Windows 腳本：

```powershell
.\run.bat
```

不使用子路徑時：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 7777 --reload
```

啟動後可查看：

- 首頁：`http://localhost:7777/s113321021/`
- Swagger UI：`http://localhost:7777/s113321021/docs`
- ReDoc：`http://localhost:7777/s113321021/redoc`
- OpenAPI：`http://localhost:7777/s113321021/openapi.json`

使用根目錄啟動時，將上述網址中的 `/s113321021` 移除。

## 帳號與權限

系統支援三種角色：

| 角色 | 權限 |
| --- | --- |
| `student` | 註冊學生帳號、瀏覽已發布活動、報名及查看個人 QR |
| `admin` | 管理使用者與活動、審核發布、指派簽到人員及查看統計 |
| `checkin` | 搜尋報名、解析 QR token、確認現場簽到 |

學生註冊只接受 `s學號@ncnu.edu.tw` 格式，建立後角色固定為 `student`。此檢查只驗證信箱格式，不代表已驗證學生身分或在學資格。管理員及簽到人員不可自行註冊，需由管理員建立或更新。

密碼使用 Argon2id 儲存，註冊與管理員建立帳號時密碼最少為 12 字元。session 儲存在資料庫中，透過 HttpOnly、SameSite=Lax cookie 管理，預設最長 14 天，登出時立即撤銷。

### 建立初始管理員

先設定 `DATABASE_URL` 並啟動一次應用程式以初始化資料表。再產生 Argon2id 密碼雜湊：

```powershell
.\venv\Scripts\python.exe -c "from getpass import getpass; from app.core.password_auth import hash_password; print(hash_password(getpass('Initial password: ')))"
```

將雜湊填入下列 SQL，透過受信任的資料庫管理工具執行：

```sql
INSERT INTO users (email, display_name, role, password_hash)
VALUES ('admin@ncnu.edu.tw', '系統管理員', 'admin', '<argon2id-hash>')
ON CONFLICT (lower(email))
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    role = EXCLUDED.role,
    password_hash = EXCLUDED.password_hash;
```

完成後可使用管理員 API 建立或更新其他帳號：

```http
POST /api/admin/users
```

學生忘記密碼時，目前沒有自助重設或重設郵件流程；管理員可透過上述管理 API 設定新密碼。

## API 摘要

系統 API 的公開前綴為 `/api`：

| 操作 | 端點 |
| --- | --- |
| 系統健康與版本 | `GET /api/health`、`GET /api/version` |
| 註冊、登入、登出、目前使用者 | `POST /api/auth/register`、`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me` |
| 公開活動瀏覽 | `GET /api/activities`、`GET /api/activities/{activity_id}` |
| 學生報名與個人紀錄 | `POST /api/activities/{activity_id}/registrations`、`GET /api/registrations/me` |
| 個人專屬 QR | `GET /api/registrations/me/{registration_id}/qr` |
| 管理使用者與活動 | `/api/admin/users`、`/api/admin/activities/...` |
| 活動簽到人員 | `/api/admin/activities/{activity_id}/staff`、`/api/admin/check-in-staff` |
| 現場簽到 | `GET /api/check-in/activities`、`GET /api/check-in/registrations`、`POST /api/check-in/qr/lookup`、`POST /api/check-in/registrations/{registration_id}/confirm` |
| 活動統計 | `GET /api/admin/activities/statistics` |
| Notes 範例 CRUD | `GET/POST/PUT/DELETE /api/notes` 或 `/api/note/{id}` |

完整參數與請求／回應格式請查看 Swagger UI。

## 活動與報名流程

活動狀態為：

```text
draft -> approved -> published -> archived
           |
           +-> rejected -> （編輯後重新送審或廢棄）
```

- 草稿：可編輯或廢棄。
- 核准：管理員審核通過。
- 發布：公開活動列表可見，學生可在報名期限內報名。
- 封存：從公開列表、詳情及報名功能下架，既有報名與簽到紀錄仍保留於統計中。
- 拒絕：必須提供審核意見；編輯後會重設為草稿並清除舊審核意見。

發布後不可透過管理 API 直接修改；封存不會刪除任何報名紀錄。報名時會檢查活動發布狀態、報名開放時間、截止時間、名額上限及重複報名。

QR token 是以 `SECRET_KEY` 簽署的不可偽造 token，資料庫只保存雜湊。只有學生本人可取得自己的 QR SVG；管理員或簽到人員可透過 QR lookup 查詢報名。簽到仍須核對本人與校園證件，簽到更新採原子操作並記錄時間與操作人員。

相機掃碼使用瀏覽器 `BarcodeDetector`，需要支援 QR 格式、相機權限，以及 HTTPS 或 localhost 安全來源。不支援相機掃碼的瀏覽器可貼上 QR token 查詢。

## 環境變數

| 變數 | 說明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 連線字串 |
| `TEST_DATABASE_URL` | 整合測試使用的可丟棄 PostgreSQL 資料庫 |
| `SECRET_KEY` | 密碼相關簽名及 QR token secret，至少 32 字元 |
| `ROOT_PATH` | 反向代理公開路徑前綴 |
| `CORS_ORIGINS` | JSON 格式允許來源，例如 `["https://example.edu"]` |
| `SESSION_COOKIE_SECURE` | HTTPS 正式環境設為 `True`；本機 HTTP 可設為 `False` |

請勿將 `.env` 提交至版本控制。

## 測試

執行一般單元測試：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

API 整合測試需要可丟棄的 PostgreSQL 測試資料庫：

```powershell
$env:TEST_DATABASE_URL = "postgresql://user:password@localhost:5432/fastapi_test"
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

整合測試只使用 `TEST_DATABASE_URL`，並建立隨機名稱的隔離 schema；結束後刪除該 schema，不會清空 `DATABASE_URL` 指向的應用程式資料庫。未設定 `TEST_DATABASE_URL` 時，整合測試會被略過。
