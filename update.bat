@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\updater.ps1" %*
if errorlevel 1 (
    echo.
    echo [ERROR] Cap nhat gap su co. Vui long kiem tra thong bao o tren.
    pause
    exit /b 1
)
echo.
pause
