#!/usr/bin/env python3
"""Test WebSocket connection and verify connection_alert welcome message."""
import asyncio
import json

try:
    import websockets
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'websockets', '--break-system-packages'])
    import websockets


async def test():
    uri = 'ws://127.0.0.1:8000/ws/telemetry'
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        print("=== WS Connected ===")
        msgs = []
        for i in range(5):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(raw)
                t = data.get("type", "?")
                if t == "connection_alert":
                    alert = data.get("alert")
                    mav = data.get("mavlink")
                    print(f"  MSG {i+1}: type={t}  alert={alert}  mavlink={json.dumps(mav) if mav else 'none'}")
                elif t == "telemetry":
                    ch = data.get("data", {}).get("connection_health")
                    healthy = ch.get("healthy") if ch else None
                    age = ch.get("heartbeat_age_s") if ch else None
                    print(f"  MSG {i+1}: type={t}  armed={data['data'].get('armed')}  mode={data['data'].get('mode')}  healthy={healthy}  hb_age={age}")
                elif t == "command_ack":
                    print(f"  MSG {i+1}: type={t}  cmd={data.get('command')}  result={data.get('result',{}).get('message','')}")
                else:
                    print(f"  MSG {i+1}: type={t}")
                msgs.append(data)
            except asyncio.TimeoutError:
                print(f"  MSG {i+1}: TIMEOUT (no message in 5s)")
                break

        # Verify we got a connection_alert
        alerts = [m for m in msgs if m.get("type") == "connection_alert"]
        telemetries = [m for m in msgs if m.get("type") == "telemetry"]

        print(f"\n=== Results ===")
        print(f"  Total messages: {len(msgs)}")
        print(f"  connection_alert messages: {len(alerts)}")
        print(f"  telemetry messages: {len(telemetries)}")

        if alerts:
            print(f"  PASSED: Got connection_alert welcome message")
        else:
            print(f"  FAILED: No connection_alert received")

        health_in_telemetry = any(
            m.get("data", {}).get("connection_health") for m in telemetries
        )
        if health_in_telemetry:
            print(f"  PASSED: Telemetry includes connection_health")
        else:
            print(f"  FAILED: Telemetry missing connection_health")

        print("\n=== WebSocket Test DONE ===")


if __name__ == "__main__":
    asyncio.run(test())
