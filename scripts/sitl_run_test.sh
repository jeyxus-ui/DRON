#!/usr/bin/env bash
set -e

REPO="/mnt/c/Users/USUARIO/Desktop/Drones/dron r/Dron"
ARDUPILOT="/home/usuario/ardupilot"

pkill -f arducopter || true
sleep 2
export SDL_VIDEODRIVER=dummy
script -qefc "$ARDUPILOT/build/sitl/bin/arducopter --home=-35.363261,149.165230,584,353 --model=quad" /tmp/sitl_test.log > /dev/null 2>&1 &

echo "Esperando que SITL arranque (10s)..."
sleep 10

cd "$REPO"
PYTHONDONTWRITEBYTECODE=1 python3 scripts/sitl_rc_test.py tcp:127.0.0.1:5760 2>&1 | grep -vE 'EOF on TCP|Connection reset'

pkill -f arducopter || true
echo "=== done ==="
