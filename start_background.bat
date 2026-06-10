@echo off
cd /d C:\Users\Julian\Desktop\hh\Dron
set MAVLINK_DEVICE=SIM
start /B /MIN python backend/start_api_sim.py
echo Server started in background
