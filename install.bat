@echo off
cd /d "%~dp0"
set "INST=%~dp0scripts\installer.ps1"
if not exist "%INST%" (
    if exist "%~dp0TikTok_OpenReel_AI-main\scripts\installer.ps1" (
        cd /d "%~dp0TikTok_OpenReel_AI-main"
        set "INST=%~dp0TikTok_OpenReel_AI-main\scripts\installer.ps1"
    )
)
if not exist "%INST%" (
    echo [ERROR] Khong tim thay thu muc scripts\installer.ps1 tai: %cd%
    echo Vui long giai nen DAY DU ca thu muc ZIP tu GitHub ^(khong chi copy rieng file install.bat^).
    echo Hoac chay: git clone https://github.com/viphuygia/TikTok_OpenReel_AI.git
    pause
    exit /b 1
)
set TARGET_ARG=
if not "%~1"=="" set TARGET_ARG=-TargetDir "%~1"
set PORT_ARG=-Port 8000
if not "%~2"=="" set PORT_ARG=-Port %~2
powershell -NoProfile -ExecutionPolicy Bypass -File "%INST%" %TARGET_ARG% %PORT_ARG%
if errorlevel 1 (
    echo.
    echo [ERROR] Qua trinh cai dat gap loi. Vui long kiem tra thong bao phia tren.
    pause
    exit /b 1
)
pause
