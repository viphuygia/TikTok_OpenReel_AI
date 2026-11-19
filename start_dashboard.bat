@echo off
chcp 65001 > nul
title TikTok OpenReel AI - Local Webapp Dashboard
cd /d "%~dp0"

set "PYT=%~dp003_voice_clone\venv\Scripts\python.exe"
set "URL=http://localhost:8000"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo ============================================================
echo   TIKTOK OPENREEL AI - LOCAL WEBAPP DASHBOARD
echo ============================================================

if not exist "%PYT%" goto :no_venv

netstat -ano | findstr /C:":8000 " | findstr /C:"LISTENING" > nul
if errorlevel 1 goto :start_new
echo [OK] Dashboard da chay san tai %URL%
start "" "%URL%"
echo [INFO] Da mo trinh duyet. Nhan phim bat ky de dong cua so nay...
pause
exit /b 0

:start_new
echo [1/2] Dang mo trinh duyet tai %URL% ...
start "" /b cmd /c "timeout /t 3 /nobreak > nul & start %URL%"
echo [2/2] Dang khoi chay FastAPI Server tai %URL% (Ctrl+C de dung)...
"%PYT%" -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port 8000
echo.
pause
exit /b 0

:no_venv
echo [LOI] Khong tim thay Python venv tai: "%PYT%"
echo Hay chay install.bat truoc!
pause
exit /b 1
