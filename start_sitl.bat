@echo off
echo === Iniciando SITL + Backend para pruebas ===

:: Matar instancias anteriores
taskkill /IM ArduCopter.exe /F 2>nul
taskkill /IM python.exe /F 2>nul
taskkill /IM py.exe /F 2>nul
timeout /t 2 /nobreak >nul

:: Iniciar SITL con 3 puertos MAVLink
:: 5760 = Mission Planner | 5762 = extra | 5763 = backend
echo Iniciando SITL...
start "SITL" "C:\Users\Julian\Documents\Mission Planner\sitl\ArduCopter.exe" ^
  --model + --speedup 1 ^
  --home -34.603700,-58.381600,0,0 ^
  --serial0=tcp:5760 ^
  --serial1=tcp:5762 ^
  --serial2=tcp:5763

timeout /t 5 /nobreak >nul
echo SITL listo en puertos 5760/5762/5763

:: Copiar .env para SITL
copy /Y "C:\Users\Julian\Desktop\hh\Dron\backend\.env.sitl" ^
       "C:\Users\Julian\Desktop\hh\Dron\backend\.env" >nul

:: Iniciar backend
echo Iniciando Backend en :8000...
cd /d C:\Users\Julian\Desktop\hh\Dron
start "Backend" py -3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

:: Reconectar Mission Planner a SITL automaticamente
echo Reconectando Mission Planner a SITL...
timeout /t 3 /nobreak >nul
powershell -ExecutionPolicy Bypass -File "%~dp0reconnect_mp.ps1"

echo.
echo === Stack iniciado ===
echo   SITL:    TCP 5760 (MP), 5762, 5763 (backend)
echo   Backend: http://0.0.0.0:8000
echo   MP:      reconectado automaticamente a 127.0.0.1:5760
echo.
