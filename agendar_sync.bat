@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Programando sincronizacion diaria con Windows (06:30 am)...
schtasks /Create /TN "EmbudoVentasSync" /TR "%~dp0sincronizar.bat" /SC DAILY /ST 06:30 /F
echo.
echo Tarea programada: EmbudoVentasSync (diaria a las 06:30)
pause