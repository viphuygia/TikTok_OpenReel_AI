@echo off
cd /d "%~dp0"
if "%PORT%"=="" set PORT=8000
set PYT=%~dp003_voice_clone\venv\Scripts\python.exe
if not exist "%PYT%" (
    echo [ERROR] Khong tim thay 03_voice_clone\venv\Scripts\python.exe. Hay chay install.bat truoc!
    pause
    exit /b 1
)
:loop
echo [%date% %time%] Dang khoi dong TikTok Studio 24/7 tai http://0.0.0.0:%PORT% ...
"%PYT%" -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port %PORT%
echo [%date% %time%] Server da dung. Tu dong khoi dong lai sau 3 giay...
timeout /t 3 /nobreak >nul
goto loop
