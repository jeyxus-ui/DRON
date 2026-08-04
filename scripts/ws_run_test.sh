#!/usr/bin/env bash
REPO="/mnt/c/Users/USUARIO/Desktop/Drones/dron r/Dron"
ARDUPILOT="/home/usuario/ardupilot"

pkill -f arducopter || true
pkill -f "backend.run" || true
sleep 2

cd "$ARDUPILOT"
export SDL_VIDEODRIVER=dummy
script -qefc "./build/sitl/bin/arducopter --home=-35.363261,149.165230,584,353 --model=quad" /tmp/sitl_flow.log > /dev/null 2>&1 &
echo "Esperando SITL (12s)..."
sleep 12

cd "$REPO"
PYTHONDONTWRITEBYTECODE=1 MAVLINK_DEVICE='tcp:127.0.0.1:5760' nohup python3 -m backend.run > /tmp/backend_flow.log 2>&1 &
echo "Backend iniciado — esperando (18s)..."
sleep 18

cd "$REPO"
python3 scripts/ws_flow_test.py
TEST_RC=$?

echo "=== BACKEND LOG (tail) ==="
tail -n 60 /tmp/backend_flow.log
echo "=== TEST EXIT: $TEST_RC ==="

pkill -f arducopter || true
pkill -f "backend.run" || true
exit $TEST_RC
