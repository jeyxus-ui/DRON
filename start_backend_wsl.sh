#!/bin/bash
cd "/mnt/c/Users/USUARIO/Desktop/Drones/dron r/Dron"
export PYTHONDONTWRITEBYTECODE=1
export MAVLINK_DEVICE='tcp:127.0.0.1:5760'
python3 -m backend.run > /tmp/backend.log 2>&1
