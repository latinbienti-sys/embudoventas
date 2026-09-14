@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Listo. Ahora: 1) completa config.json  2) ejecuta sincronizar.bat
pause