#!/usr/bin/env python3
"""
Test: ARRANCAR + ACELERAR
  GUIDED → ARM → TAKEOFF → STABILIZE → throttle gradual → pitch+throttle → LAND
"""
import time
import json
import urllib.request
import sys

def api(method, path, body=None, timeout=60):
    url = f"http://localhost:8000/api{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def t():
    d = api("GET", "/telemetry")
    print(f"  [{d['mode']:8s}] armed={str(d['armed']):5s} alt={d['altitude']:.1f}m "
          f"spd={d['ground_speed']:.1f}m/s vspd={d['vertical_speed']:.1f}m/s", flush=True)
    return d

def rc(**kw):
    api("POST", "/rc/control", kw)

def main():
    print("=" * 60)
    print("  ARRANQUE + ACELERAR")
    print("=" * 60)

    # ── GUIDED + ARM + TAKEOFF ──
    print("\n--- ARRANQUE ---")
    api("POST", "/mode", {"mode": "GUIDED"})
    api("POST", "/arm", {"force": True}, timeout=90)
    time.sleep(2)
    api("POST", "/takeoff", {"altitude": 10}, timeout=60)
    for i in range(10):
        time.sleep(1)
        d = t()
        if d["altitude"] >= 585:
            break

    # ── STABILIZE ──
    api("POST", "/mode", {"mode": "STABILIZE"})
    time.sleep(1)

    for _ in range(10):
        rc(throttle=0.55)
        time.sleep(0.1)

    # ── THROTTLE GRADUAL ──
    print("\n--- THROTTLE GRADUAL ---")
    t()
    for pct in [60, 65, 70, 75, 80, 85]:
        thr = pct / 100.0
        print(f"\n  >>> Throttle {pct}%")
        for i in range(3):
            rc(throttle=thr)
            time.sleep(1)
            t()

    # ── PITCH + THROTTLE (acelerar horizontal) ──
    print("\n--- PITCH FORWARD + THROTTLE ---")
    for pct in [65, 70, 75, 80]:
        thr = pct / 100.0
        print(f"\n  >>> Pitch 0.4 + Throttle {pct}%")
        for i in range(3):
            rc(pitch=0.4, throttle=thr)
            time.sleep(1)
            t()

    # ── LAND ──
    print("\n--- LAND ---")
    rc(throttle=0.0)
    time.sleep(1)
    api("POST", "/mode", {"mode": "GUIDED"})
    api("POST", "/land", timeout=120)
    for i in range(120):
        time.sleep(1)
        d = t()
        if not d["armed"]:
            print("  Desarmado!")
            break

    api("POST", "/disarm", {"force": True}, timeout=15)
    print("\n--- HEALTH ---")
    h = api("GET", "/connection/status")
    print(f"  probe_failures={h['probe_failures']}")
    print("\n=== FIN ===")

if __name__ == "__main__":
    main()
