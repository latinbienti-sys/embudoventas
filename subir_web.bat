@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Generando tablero estatico...
python export_static.py
if errorlevel 1 goto :error
echo Subiendo a GitHub Pages...
git add docs
git commit -m "Actualizacion tablero web embudo de ventas" -q
git push origin master -q
if errorlevel 1 goto :error
echo.
echo Tablero publicado: https://latinbienti-sys.github.io/embudoventas/
pause
exit /b 0
:error
echo.
echo Ocurrio un error. Revisa el mensaje anterior.
pause
exit /b 1