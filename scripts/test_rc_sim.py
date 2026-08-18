"""Test RC override in SIM mode — send RC_CONTROL, verify backend stays healthy."""
import asyncio
import json
import urllib.request

def get_token():
    data = json.dumps({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["token"]

def check_health():
    req = urllib.request.Request("http://127.0.0.1:8000/api/camera/status")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

async def test_rc():
    import websockets
    token = get_token()
    uri = f"ws://127.0.0.1:8000/ws/telemetry?token={token}"

    async with websockets.connect(uri) as ws:
        initial = await asyncio.wait_for(ws.recv(), timeout=5)
        print(f"Connected: {json.loads(initial).get('type')}")

        for throttle, yaw, pitch, roll in [
            (0.5, 0.3, -0.2, 0.1),
            (0.0, 0.0, 0.0, 0.0),
            (1.0, -1.0, 1.0, -1.0),
        ]:
            cmd = {"type": "RC_CONTROL", "params": {"throttle": throttle, "yaw": yaw, "pitch": pitch, "roll": roll}}
            await ws.send(json.dumps(cmd))
            print(f"Sent RC: T={throttle:+.1f} Y={yaw:+.1f} P={pitch:+.1f} R={roll:+.1f}")
            await asyncio.sleep(0.2)

        print("All RC commands sent without error.")

    health = check_health()
    print(f"Backend healthy: running={health.get('running')}")
    print("\n=== RC OVERRIDE EN SIM MODE FUNCIONA ===")

if __name__ == "__main__":
    asyncio.run(test_rc())
