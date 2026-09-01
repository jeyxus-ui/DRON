@echo off
echo.
echo ╔══════════════════════════════════════════╗
echo ║     DRON - Cambiar modo de conexion      ║
echo ╚══════════════════════════════════════════╝
echo.
echo   [1] SITL  - Mission Planner simulador
echo   [2] REAL  - Pixhawk fisico (UDP bridge)
echo   [3] SIM   - Simulador interno basico
echo.
set /p choice=Elige modo (1/2/3):

if "%choice%"=="1" (
    copy /y "%~dp0.env.sitl" "%~dp0.env" > nul
    echo ✅ Modo SITL activado - abre Mission Planner ^> Simulation ^> Start
)
if "%choice%"=="2" (
    echo MAVLINK_DEVICE=udpin:0.0.0.0:14550 > "%~dp0.env"
    echo MAVLINK_BAUD=57600 >> "%~dp0.env"
    echo INDOOR_MODE=1 >> "%~dp0.env"
    echo API_HOST=0.0.0.0 >> "%~dp0.env"
    echo API_PORT=8000 >> "%~dp0.env"
    echo ✅ Modo REAL activado - conecta la Raspberry Pi
)
if "%choice%"=="3" (
    echo MAVLINK_DEVICE=SIM > "%~dp0.env"
    echo INDOOR_MODE=1 >> "%~dp0.env"
    echo API_HOST=0.0.0.0 >> "%~dp0.env"
    echo API_PORT=8000 >> "%~dp0.env"
    echo ✅ Modo SIM basico activado
)

echo.
echo Reinicia el backend para aplicar los cambios.
pause
