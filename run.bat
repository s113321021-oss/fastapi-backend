@echo off
cd /d "%~dp0"

REM 先啟用 venv
call .\venv\Scripts\activate.bat

REM 設定本機 IP 和 port
set HOST=0.0.0.0
set PORT=7777
set ROOT_PATH=/s113321021

REM 公開路徑必須與實際網址前綴完全一致
uvicorn app.main:app --host %HOST% --port %PORT% --root-path %ROOT_PATH% --reload

pause