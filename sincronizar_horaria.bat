@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [%date% %time%] Sync horaria iniciada >> sync_horaria.log
python sync_to_local.py --backfill 3 >> sync_horaria.log 2>&1
if errorlevel 1 goto :error
python export_static.py >> sync_horaria.log 2>&1
if errorlevel 1 goto :error
echo Publicando en GitHub Pages...
git add docs
git commit -m "Actualizacion horaria tablero embudo" -q
git push origin master -q
if errorlevel 1 goto :error
echo [%date% %time%] Sync horaria OK >> sync_horaria.log
exit /b 0
:error
echo [%date% %time%] ERROR en sync horaria >> sync_horaria.log
exit /b 1