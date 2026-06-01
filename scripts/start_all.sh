#!/bin/bash
killall -9 arducopter 2>/dev/null
killall -9 sim_vehicle.py 2>/dev/null
rm -f /tmp/ArduCopter.log /tmp/sitl_run.log
cd /home/usuario/ardupilot
python3 ./Tools/autotest/sim_vehicle.py -v ArduCopter --no-rebuild --no-mavproxy -N --out=udp:172.28.240.1:14550 --out=udp:172.28.240.1:14551 > /tmp/sitl_run.log 2>&1 &
SIM_PID=$!
echo "sim_vehicle PID: $SIM_PID"
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if grep -q SERIAL0 /tmp/ArduCopter.log 2>/dev/null; then
    echo "ArduCopter ready after ${i}s"
    break
  fi
  sleep 1
done
echo "Starting bridge..."
python3 /tmp/bridge_wsl.py > /tmp/bridge.log 2>&1 &
echo "Bridge started"
echo ALL_DONE
