#!/usr/bin/env python3
"""Diagnostic: check connection status every 1s for 40s after killing SITL."""
import os
import subprocess
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api/connection/status"

def check():
    try:
        with urllib.request.urlopen(BASE, timeout=3) as r:
            return __import__('json').loads(r.read())
    except Exception:
        return {"error": "not reachable"}

def is_wsl():
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False

IN_WSL = is_wsl()

def run_cmd(cmd):
    if IN_WSL:
        subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=5)
    else:
        subprocess.run(["wsl", "-e", "bash", "-c", cmd], capture_output=True, timeout=5)

print("Initial:", check())
print(f"\nRunning inside WSL: {IN_WSL}")
print("Killing SITL...")
run_cmd("killall -9 arducopter; screen -S sitl -X quit 2>/dev/null")
print("SITL killed.\n")

for i in range(40):
    time.sleep(1)
    s = check()
    age = s.get('heartbeat_age_s', '?')
    healthy = s.get('healthy', '?')
    conn = s.get('connected', '?')
    reconnecting = s.get('reconnecting', '?')
    sock = s.get('socket_alive', '?')
    probe = s.get('probe_failures', '?')
    print(f"  t={i+1:2d}s  connected={conn}  healthy={healthy}  hb_age={age}  socket={sock}  probe={probe}")
    if i == 5:
        print("  >>> Restarting SITL...")
        run_cmd("screen -dmS sitl /home/usuario/ardupilot/build/sitl/bin/arducopter "
                "--model quad --speedup 1 --serial0 tcp:5760")
        print("  SITL restarted")
    if healthy == True and i > 5:
        print("  >>> HEARTBEAT RESTORED!")
        break

print("\nFinal:", check())
