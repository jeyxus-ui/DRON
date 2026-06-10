@echo off
cd /d C:\Users\Julian\Desktop\hh\Dron
set MAVLINK_DEVICE=SIM
echo Starting drone API server (SIM mode)...
C:\Users\Julian\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
