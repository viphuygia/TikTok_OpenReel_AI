@echo off
cd /d "%~dp0"
if "%PORT%"=="" set PORT=8000
set "PYT=%~dp003_voice_clone\venv\Scripts\python.exe"
if not exist "%PYT%" goto :no_venv
start "" "http://127.0.0.1:%PORT%"
"%PYT%" -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port %PORT%
pause
exit /b 0

:no_venv
echo [ERROR] Khong tim thay venv. Hay chay install.bat truoc!
pause
exit /b 1
