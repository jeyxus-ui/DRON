#!/bin/bash
cd "/mnt/c/Users/USUARIO/Desktop/Drones/dron r/Dron"
export MAVLINK_DEVICE="tcp:127.0.0.1:5760"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
exec python3 -m backend.run 2>&1 | tee /tmp/backend_latest.log
