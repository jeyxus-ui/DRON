@echo off
set PYTHONDONTWRITEBYTECODE=1
set MAVLINK_DEVICE=tcp:172.28.252.91:5760
echo Conectando a: %MAVLINK_DEVICE%
python -m backend.run
