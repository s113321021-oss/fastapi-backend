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

## 校園活動首頁

首頁採 mobile-first 響應式版面，包含活動導覽、分類篩選、關鍵字搜尋、活動卡片與詳情視窗。活動由資料庫 API 提供；學生及未登入訪客只能讀取已發布活動，管理員登入後可在首頁使用活動管理區。`app/static/data/activities.json` 僅保留為舊版展示資料，不會作為公開活動資料來源。

活動支援分類、主辦單位、活動時間/時長、地點、描述、報名截止、最大名額及來源連結。來源連結限定為下列暨大官方網站；管理員可手動同步公告，解析結果先進入待檢視清單，不會直接公開：

- [終身學習與地方創生中心](https://ccweb.ncnu.edu.tw/SLLL/z958B653E5831540D4E4B6D3B52D5660E7D30list.asp)
- [語言教學中心](https://ltrc.ncnu.edu.tw/web/quiz/quiz_sign.jsp)
- [教學發展中心](https://ctld.ncnu.edu.tw/)

## 使用者與權限 API

登入採本系統帳號與密碼，不串接校內 SSO、不寄送驗證信，也不讀取郵件內容。學生註冊僅接受 `s學號@ncnu.edu.tw` 格式，建立後預設為 `student`；這只檢查信箱格式，不能證明帳號屬於本人或仍具在學資格。管理員與簽到人員不可自行註冊，須由管理員建立或更新角色。密碼以 Argon2id 雜湊儲存，最低長度為 12 字元。

首次啟用時，先建立資料庫並以受信任的資料庫管理工具新增至少一名管理員到 `users`。舊版 `external_subject` 欄位會保留為 nullable 相容欄位；帳號以正規化 email 對應。產生初始密碼雜湊（密碼由 getpass 隱藏輸入）：

```powershell
.\venv\Scripts\python.exe -c "from getpass import getpass; from app.core.password_auth import hash_password; print(hash_password(getpass('Initial password: ')))"
```

把輸出的 Argon2id 雜湊填入下方 SQL。管理員登入後可用 `POST /api/admin/users` 建立或更新帳號及角色，新增帳號時需提供至少 12 字元的初始密碼。應用程式啟動時會初始化使用者、活動、報名與 session 資料表。

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
| 查看活動來源 | `GET /api/activity-sources` |
| 管理員同步官方公告 | `POST /api/admin/activity-imports/sync`，body 可帶 `source_id` (`slll`/`ltrc`/`ctld`)，省略時同步全部來源 |
| 管理員查看匯入結果與同步歷史 | `GET /api/admin/activity-imports`、`GET /api/admin/activity-import-runs` |
| 建立活動草稿或忽略公告 | `POST /api/admin/activity-imports/{import_id}/create-draft`、`POST /api/admin/activity-imports/{import_id}/ignore` |
| 瀏覽已發布活動 | `GET /api/activities`、`GET /api/activities/{activity_id}` |
| 學生報名及查看自己的紀錄 | `POST /api/activities/{activity_id}/registrations`、`GET /api/registrations/me` |
| 管理使用者、建立/編輯/廢棄草稿、審核/發布活動、查看統計 | `/api/admin/...` |
| 查詢報名及確認簽到 | `GET /api/check-in/registrations`、`POST /api/check-in/registrations/{registration_id}/confirm` |

活動狀態流程為「草稿 → 核准 → 發布」；已拒絕的活動可編輯後重新送審或廢棄。任何未發布活動皆可編輯或廢棄，編輯會將狀態重設為草稿並清除舊審核意見；發布後不可透過管理 API 直接修改。拒絕時必須提供審核意見；公開列表、詳情及報名只會使用已發布活動。報名會同時檢查截止時間、名額與重複報名。

公告同步使用固定 HTTPS allowlist，只抓取 `ccweb.ncnu.edu.tw`、`ltrc.ncnu.edu.tw`、`ctld.ncnu.edu.tw`，不接受任意 URL、不跟隨外站轉址，且限制回應大小。每次同步由管理員手動觸發；系統依來源公告網址去重，保存匯入候選、最後抓取時間、解析缺漏/錯誤及每次同步結果。缺少活動日期、地點或其他必填資料時，管理員需先補齊才能建立活動草稿；建立後沿用既有審核及發布流程。同步不會登入學校網站或讀取 Webmail。

請將 `SECRET_KEY` 換成唯一、至少 32 字元的隨機值；範例佔位值會被登入模組拒絕。正式環境使用 HTTPS，並將 `SESSION_COOKIE_SECURE=True`；登入 session 為資料庫管理的 HttpOnly/SameSite cookie，最長 14 天，登出時立即撤銷。系統只驗證所輸入帳號密碼，不連線學校 Webmail，也不使用校內 SSO 密碼。

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
DATABASE_URL=postgresql://dev_user:dev_password@localhost:5432/fastapi_dev
ROOT_PATH=/s113321021
```

若你在反向代理底下部署，請讓 `ROOT_PATH` 與實際網址前綴完全一致。

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
