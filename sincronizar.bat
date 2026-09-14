@echo off
chcp 65001 >nul
cd /d "%~dp0"
python sync_to_local.py --backfill 45
echo.
pause