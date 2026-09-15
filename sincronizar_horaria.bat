@echo off
chcp 65001 >nul
cd /d "%~dp0"
python sync_to_local.py --backfill 3 >> sync_horaria.log 2>&1
python export_static.py >> sync_horaria.log 2>&1