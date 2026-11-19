@echo off
cd /d "%~dp0"
set "INST=%~dp0scripts\installer.ps1"
if exist "%INST%" goto :found_inst
if not exist "%~dp0TikTok_OpenReel_AI-main\scripts\installer.ps1" goto :missing_inst
cd /d "%~dp0TikTok_OpenReel_AI-main"
set "INST=%~dp0TikTok_OpenReel_AI-main\scripts\installer.ps1"
:found_inst
set TARGET_ARG=
if not "%~1"=="" set TARGET_ARG=-TargetDir "%~1"
set PORT_ARG=-Port 8000
if not "%~2"=="" set PORT_ARG=-Port %~2
powershell -NoProfile -ExecutionPolicy Bypass -File "%INST%" %TARGET_ARG% %PORT_ARG%
if errorlevel 1 goto :err_exit
echo.
echo [OK] Hoan tat cai dat!
pause
exit /b 0

:missing_inst
echo [ERROR] Khong tim thay scripts\installer.ps1 tai: %cd%
echo Vui long giai nen DAY DU ca thu muc ZIP tu GitHub.
pause
exit /b 1

:err_exit
echo.
echo [ERROR] Qua trinh cai dat gap loi. Vui long kiem tra thong bao phia tren.
pause
exit /b 1
