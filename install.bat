@echo off
cd /d "%~dp0"
set TARGET_ARG=
if not "%~1"=="" set TARGET_ARG=-TargetDir "%~1"
set PORT_ARG=-Port 8000
if not "%~2"=="" set PORT_ARG=-Port %~2
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer.ps1" %TARGET_ARG% %PORT_ARG%
if errorlevel 1 (
    echo.
    echo [ERROR] Qua trinh cai dat gap loi. Vui long kiem tra thong bao phia tren.
    pause
    exit /b 1
)
pause
