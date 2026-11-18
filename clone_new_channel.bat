@echo off
cd /d "%~dp0"
echo ============================================================
echo   NHAN BAN KENH TIKTOK MOI (DOC LAP STYLE, PROJECT & PORT)
echo ============================================================
echo.
set "CLONE_DIR="
set /p CLONE_DIR=Nhap duong dan thu muc cho kenh moi (VD: ..\TikTok_Kenh_2): 
if "%CLONE_DIR%"=="" (
    echo [ERROR] Duong dan khong duoc de trong!
    pause
    exit /b 1
)
set "NEW_PORT="
set /p NEW_PORT=Nhap cong chay rieng (mac dinh 8001): 
if "%NEW_PORT%"=="" set NEW_PORT=8001

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer.ps1" -CloneTo "%CLONE_DIR%" -Port %NEW_PORT%
if errorlevel 1 (
    echo [ERROR] Nhan ban kenh that bai!
    pause
    exit /b 1
)
pause
