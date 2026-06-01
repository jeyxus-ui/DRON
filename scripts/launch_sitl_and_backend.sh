#!/usr/bin/env bash
set -euo pipefail

# launch_sitl_and_backend.sh
# Minimal helper for WSL2 to start ArduPilot SITL (from ./ardupilot) and
# then run the project backend with MAVLINK_DEVICE pointing at SITL UDP.
# Usage: ./launch_sitl_and_backend.sh

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
ARDUPILOT_DIR="$REPO_ROOT/ardupilot"

if [ ! -d "$ARDUPILOT_DIR" ]; then
  echo "Error: ardupilot directory not found at $ARDUPILOT_DIR"
  echo "Clone ArduPilot in $ARDUPILOT_DIR or adjust the script." >&2
  exit 1
fi

echo "Starting SITL (ArduCopter) in background..."
(
  cd "$ARDUPILOT_DIR"
  # Start SITL and export MAVLink via UDP 127.0.0.1:14550
  Tools/autotest/sim_vehicle.py -v ArduCopter --console --map --out=udp:127.0.0.1:14550
) &

SITL_PID=$!
echo "SITL started (PID: $SITL_PID). Waiting 3s for it to initialize..."
sleep 3

echo "Activating virtualenv (venv) and launching backend..."
if [ ! -d "$REPO_ROOT/venv" ]; then
  echo "Virtualenv not found at $REPO_ROOT/venv - creating one and installing requirements"
  python3 -m venv "$REPO_ROOT/venv"
  source "$REPO_ROOT/venv/bin/activate"
  pip install -r "$REPO_ROOT/requirements.txt"
else
  source "$REPO_ROOT/venv/bin/activate"
fi

export MAVLINK_DEVICE="udp:127.0.0.1:14550"
export MAVLINK_BAUD="57600"

echo "Running backend with MAVLINK_DEVICE=$MAVLINK_DEVICE"
python3 backend/run_with_device.py
