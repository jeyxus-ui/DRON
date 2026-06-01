@echo off
set PYTHONPATH=C:\Users\Julian\Desktop\hh\Dron
set MAVLINK_DEVICE=SIM
cd /d C:\Users\Julian\Desktop\hh\Dron
C:\Users\Julian\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
