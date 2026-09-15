@echo off
chcp 65001 >nul
cd /d "%~dp0"
python gohighlevel.py >> gestion_envio.log 2>&1