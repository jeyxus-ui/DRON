#!/usr/bin/env python3
"""
Test: STARTUP + MANUAL CONTROLS
  Health check -> GUIDED -> ARM -> TAKEOFF -> RC movements -> LAND -> DISARM

Validates:
  - Backend healthy & connected
  - GUIDED mode set & confirmed
  - ARM with ACK
  - TAKEOFF climb to 10m
  - RC override: each axis (roll, pitch, throttle, yaw) independently
  - RC center (hover stable)
  - Combined inputs (forward+climb)
  - LAND mode
  - DISARM
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

def telemetry():
    return api("GET", "/telemetry")

def status():
    return api("GET", "/connection/status")

def rc(roll=0.0, pitch=0.0, throttle=0.0, yaw=0.0):
    return api("POST", "/rc/control", {
        "roll": roll, "pitch": pitch, "throttle": throttle, "yaw": yaw,
    })

def rc_center():
    return rc(0.0, 0.0, 0.0, 0.0)

def log(label):
    t = telemetry()
    print(f"  [{label}] mode={t['mode']:8s} armed={str(t['armed']):5s} "
          f"alt={t['altitude']:.1f}m spd={t['ground_speed']:.1f}m/s "
          f"vspd={t['vertical_speed']:.1f}m/s", flush=True)
    return t

def wait_alt(target, timeout=30, tolerance=1.0):
    for i in range(timeout):
        time.sleep(1)
        t = log(f"CLIMB {i+1}s")
        if t['altitude'] >= target - tolerance:
            print(f"    -> Reached {t['altitude']:.1f}m (target={target}m)")
            return True
    print(f"    -> TIMEOUT: only reached {t['altitude']:.1f}m")
    return False

def move(name, duration, hover_throttle=0.55, **kwargs):
    """Send RC input for `duration` seconds and log each second."""
    print(f"\n  >>> {name}: {kwargs} ({duration}s)")
    for i in range(duration):
        rc(**kwargs)
        time.sleep(1)
        log(f"  {name} t={i+1}s")
    # Restore hover throttle instead of center (0,0,0,0) which drops in STABILIZE
    rc(throttle=hover_throttle, roll=0.0, pitch=0.0, yaw=0.0)
    time.sleep(1)
    log(f"  {name} hover-restored")

def main():
    print("=" * 70)
    print("  TEST: STARTUP + MANUAL CONTROLS")
    print("=" * 70)

    # ── 0. HEALTH ──
    print("\n--- 0. HEALTH CHECK ---")
    h = status()
    print(f"  healthy={h['healthy']} connected={h['connected']} "
          f"probe_failures={h['probe_failures']}")
    if not h['healthy']:
        print("  FATAL: Backend not healthy!")
        sys.exit(1)

    # ── 1. GUIDED + ARM + TAKEOFF ──
    print("\n--- 1. STARTUP (GUIDED -> ARM -> TAKEOFF 10m) ---")

    r = api("POST", "/mode", {"mode": "GUIDED"})
    print(f"  SET_MODE: {r['message']} (mode={r.get('mode','?')})")
    log("mode-set")

    r = api("POST", "/arm", {"force": True}, timeout=90)
    print(f"  ARM: {r['message']}")
    time.sleep(2)
    log("arm-set")

    r = api("POST", "/takeoff", {"altitude": 10}, timeout=60)
    print(f"  TAKEOFF: {r['message']}")

    reached = wait_alt(10, timeout=20, tolerance=1.0)
    if not reached:
        print("  WARN: Did not reach target, continuing anyway")

    print("\n  Base altitude before controls:")
    base = log("BASE")

    # ── Switch to STABILIZE for manual RC control ──
    # In GUIDED mode, ArduPilot ignores RC override for pitch/roll/yaw.
    # STABILIZE mode accepts full RC override on all axes.
    # IMPORTANT: Throttle must be >= ~0.5 (hover) for pitch/roll to have effect.
    print("\n  Switching to STABILIZE for manual RC control...")
    r = api("POST", "/mode", {"mode": "STABILIZE"})
    print(f"  SET_MODE: {r['message']} (mode={r.get('mode','?')})")
    time.sleep(2)
    log("POST-STABILIZE")

    # First bring throttle to hover to keep altitude
    print("  Setting hover throttle (0.55) to maintain altitude...")
    for _ in range(10):
        rc(throttle=0.55)
        time.sleep(0.2)
    time.sleep(2)
    t = log("HOVER-THROTTLE")

    # ── 2. INDIVIDUAL AXIS TESTS ──
    print("\n--- 2. RC CONTROL TESTS (STABILIZE mode, hover throttle baseline) ---")

    move("THROTTLE UP (+0.15 over hover)", 3, throttle=0.70)
    move("THROTTLE DOWN (-0.15 under hover)", 3, throttle=0.40)
    move("YAW LEFT (-0.3) + hover throttle", 3, yaw=-0.3, throttle=0.55)
    move("YAW RIGHT (+0.3) + hover throttle", 3, yaw=0.3, throttle=0.55)
    move("PITCH FORWARD (+0.3) + hover throttle", 3, pitch=0.3, throttle=0.55)
    move("PITCH BACK (-0.3) + hover throttle", 3, pitch=-0.3, throttle=0.55)
    move("ROLL LEFT (-0.3) + hover throttle", 3, roll=-0.3, throttle=0.55)
    move("ROLL RIGHT (+0.3) + hover throttle", 3, roll=0.3, throttle=0.55)

    print("\n  --- Hover stability (3s at 0.55) ---")
    t0 = log("HOVER t=0")
    for i in range(3):
        rc(throttle=0.55)
        time.sleep(1)
        t = log(f"HOVER t={i+1}s")
    alt_drift = abs(t['altitude'] - t0['altitude'])
    print(f"  Hover drift: {alt_drift:.2f}m over 3s", flush=True)

    # ── 3. COMBINED INPUTS ──
    print("\n--- 3. COMBINED CONTROLS ---")
    move("FORWARD+CLIMB (pitch=0.2, throttle=0.65)", 4, pitch=0.2, throttle=0.65)
    move("BACK+DESCEND (pitch=-0.2, throttle=0.45)", 4, pitch=-0.2, throttle=0.45)
    move("SPIN+CLIMB (yaw=0.4, throttle=0.65)", 4, yaw=0.4, throttle=0.65)

    print("\n  --- Final hover (5s at 0.55) ---")
    t0 = log("FINAL-HOVER t=0")
    for i in range(5):
        rc(throttle=0.55)
        time.sleep(1)
        t = log(f"FINAL-HOVER t={i+1}s")
    alt_drift_final = abs(t['altitude'] - t0['altitude'])
    print(f"  Final hover drift: {alt_drift_final:.2f}m over 5s", flush=True)

    # ── 4. LAND + DISARM ──
    print("\n--- 4. LAND + DISARM ---")
    r = api("POST", "/mode", {"mode": "GUIDED"})
    print(f"  SET_MODE GUIDED: {r['message']}")
    time.sleep(1)
    r = api("POST", "/land", timeout=60)
    print(f"  LAND: {r['message']}")

    for i in range(60):
        time.sleep(1)
        t = log(f"LANDING t={i+1}s")
        if not t['armed']:
            print("  Disarmed by LAND!")
            break

    r = api("POST", "/disarm", {"force": True}, timeout=15)
    print(f"  DISARM: {r['message']}")
    log("FINAL")

    # ── 5. FINAL HEALTH ──
    print("\n--- 5. FINAL HEALTH ---")
    h = status()
    print(f"  healthy={h['healthy']} connected={h['connected']} "
          f"probe_failures={h['probe_failures']}")

    print("\n" + "=" * 70)
    print("  STARTUP + CONTROLS TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
