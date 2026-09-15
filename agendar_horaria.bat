@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Programando sincronizacion horaria (cada 1 hora)...
schtasks /Create /TN "EmbudoVentasSyncHoraria" /TR "%~dp0sincronizar_horaria.bat" /SC HOURLY /F
echo.
echo Programando envio del cierre de gestion por WhatsApp (todos los dias 20:00)...
schtasks /Create /TN "EmbudoVentasGestion" /TR "%~dp0enviar_gestion.bat" /SC DAILY /ST 20:00 /F
echo.
echo Tareas programadas:
echo   - EmbudoVentasSyncHoraria : sync + web cada hora
echo   - EmbudoVentasGestion     : envio WhatsApp a las 20:00
echo.
echo Nota: al ejecutar la primera vez pedira permisos de administrador.
pause