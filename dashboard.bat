@echo off
chcp 65001 >nul
cd /d "%~dp0"
python dashboard_app.py
pause