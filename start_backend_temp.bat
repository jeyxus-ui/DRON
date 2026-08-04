@echo off
set MAVLINK_DEVICE=tcp:127.0.0.1:5760
set PYTHONDONTWRITEBYTECODE=1
cd /d "%~dp0"
python -m backend.run
