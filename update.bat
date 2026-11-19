@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\updater.ps1" %*
if errorlevel 1 goto :err_upd
echo.
pause
exit /b 0

:err_upd
echo.
echo [ERROR] Cap nhat gap su co. Vui long kiem tra thong bao o tren.
pause
exit /b 1
