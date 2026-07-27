#!/usr/bin/env python3
"""Test: kill SITL → verify mavlink_lost alert → restart SITL → verify mavlink_restored."""
import asyncio
import json
import os
import subprocess
import time

try:
    import websockets
except ImportError:
    import sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'websockets', '--break-system-packages'])
    import websockets


def is_wsl():
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False

IN_WSL = is_wsl()

def run_cmd(cmd):
    if IN_WSL:
        result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
    else:
        result = subprocess.run(["wsl", "-e", "bash", "-c", cmd], capture_output=True, text=True, timeout=10)
    return result

def run_cmd_long(cmd, timeout=15):
    if IN_WSL:
        result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    else:
        result = subprocess.run(["wsl", "-e", "bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    return result

def sitl_alive():
    r = run_cmd("pgrep -x arducopter || true")
    return bool(r.stdout.strip())

def kill_sitl():
    run_cmd("killall -9 arducopter 2>/dev/null || true")
    run_cmd("screen -S sitl -X quit 2>/dev/null || true")
    run_cmd("screen -wipe >/dev/null 2>&1 || true")

def start_sitl():
    run_cmd_long(
        "screen -dmS sitl /home/usuario/ardupilot/build/sitl/bin/arducopter "
        "--model quad --speedup 1 --serial0 tcp:5760"
    )


async def test():
    uri = 'ws://127.0.0.1:8000/ws/telemetry'
    print(f"Connecting to {uri}...")
    print(f"Running inside WSL: {IN_WSL}")

    alive_before = sitl_alive()
    print(f"  SITL alive before test: {alive_before}")

    async with websockets.connect(uri) as ws:
        print("=== WS Connected ===")

        # Drain initial messages (welcome + a few telemetry)
        for _ in range(5):
            try:
                await asyncio.wait_for(ws.recv(), timeout=3)
            except asyncio.TimeoutError:
                break
        print("  Drained initial messages")

        # Kill SITL and verify
        print("\n>>> Killing SITL...")
        kill_sitl()

        for attempt in range(10):
            if not sitl_alive():
                print(f"  SITL confirmed dead after {attempt+1} checks")
                break
            await asyncio.sleep(0.5)
        else:
            print("  WARNING: SITL may still be alive after kill attempts")
            kill_sitl()
            await asyncio.sleep(2)

        print("  Waiting for mavlink_lost alert (up to 30s)...")

        # Wait for mavlink_lost alert
        got_lost = False
        got_restored = False
        deadline = time.time() + 30
        msg_count = 0
        hb_false_count = 0

        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=3)
                data = json.loads(raw)
                t = data.get("type", "")
                if t == "connection_alert":
                    alert = data.get("alert")
                    print(f"  ALERT: {alert} — {data.get('message', '')}")
                    if alert == "mavlink_lost":
                        got_lost = True
                        print("  >>> PASSED: mavlink_lost received!")
                        # Now restart SITL
                        print("\n>>> Restarting SITL...")
                        start_sitl()
                        print("  SITL restarted. Waiting for mavlink_restored (up to 60s)...")
                        deadline = time.time() + 60
                    elif alert == "mavlink_restored":
                        got_restored = True
                        print("  >>> PASSED: mavlink_restored received!")
                        break
                elif t == "telemetry":
                    ch = data.get("data", {}).get("connection_health")
                    if ch:
                        healthy = ch.get("healthy", "?")
                        sconn = ch.get("sconnected", "?")
                        conn = ch.get("connected", "?")
                        hb_age = ch.get("heartbeat_age_s", "?")
                        msg_age = ch.get("last_msg_age_s", "?")
                        needs = ch.get("needs_reconnect", "?")
                        sock = ch.get("socket_alive", "?")
                        probe = ch.get("probe_failures", "?")
                        msg_count += 1
                        if not healthy:
                            hb_false_count += 1
                        if msg_count % 25 == 0 or not healthy:
                            print(f"  HEALTH [{msg_count}]: healthy={healthy} socket={sock} probe={probe} "
                                  f"conn={conn} sconn={sconn} hb_age={hb_age} msg_age={msg_age} needs={needs}")
            except asyncio.TimeoutError:
                continue

        print(f"\n=== Results ===")
        print(f"  Total telemetry msgs: {msg_count}")
        print(f"  Messages with healthy=False: {hb_false_count}")
        print(f"  mavlink_lost received: {got_lost}")
        print(f"  mavlink_restored received: {got_restored}")
        if got_lost and got_restored:
            print("  ALL TESTS PASSED")
        elif got_lost:
            print("  PARTIAL: lost detected, restored not yet (may need more time)")
        else:
            print("  FAILED: no alerts received — check backend logs for [BROADCASTER] lines")
        print("=== Test DONE ===")


if __name__ == "__main__":
    asyncio.run(test())
