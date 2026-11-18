@echo off
chcp 65001 > nul
title TikTok OpenReel AI - Local Webapp Dashboard

set "ROOT_DIR=%~dp0"
set "VENV_ACTIVATE=%ROOT_DIR%03_voice_clone\venv\Scripts\activate.bat"
set "URL=http://localhost:8000"

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo ============================================================
echo   TIKTOK OPENREEL AI - LOCAL WEBAPP DASHBOARD (ZERO-COPY)
echo ============================================================

if not exist "%VENV_ACTIVATE%" (
    echo [LOI] Khong tim thay moi truong ao Python tai: %VENV_ACTIVATE%
    pause
    exit /b 1
)

call "%VENV_ACTIVATE%"

netstat -ano | findstr /C:":8000 " | findstr /C:"LISTENING" > nul
if %errorlevel%==0 (
    echo [OK] Dashboard da chay san tai %URL%
    start "" "%URL%"
    exit /b 0
)

echo [1/2] Dang mo trinh duyet tai %URL% ...
start "" cmd /c "timeout /t 3 /nobreak > nul && start "" "%URL%""

echo [2/2] Dang khoi chay FastAPI Server tai %URL% (Ctrl+C de dung)...
cd /d "%ROOT_DIR%"
"%ROOT_DIR%03_voice_clone\venv\Scripts\python.exe" -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port 8000
pause
