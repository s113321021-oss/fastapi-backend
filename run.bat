@echo off
cd /d "%~dp0"

REM Activate venv
call .\venv\Scripts\activate.bat

REM Local development settings
set HOST=0.0.0.0
set PORT=7777
set ROOT_PATH=/s113321021
set SESSION_COOKIE_SECURE=False
set ENABLE_DOCS=True
set TRUST_PROXY_HEADERS=False

REM Start local development server
uvicorn app.main:app --host %HOST% --port %PORT% --root-path %ROOT_PATH% --reload

pause
