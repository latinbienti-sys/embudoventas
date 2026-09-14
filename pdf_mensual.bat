@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Mes en formato AAA-MM (ejemplo 2026-08):
set /p MES=>
python monthly_pdf.py --month %MES%
pause