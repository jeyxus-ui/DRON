#!/usr/bin/env python3
"""
Test MANUAL -> AUTONOMOUS -> MANUAL -> LAND transitions.
Simulates: User flies manually via RC, then uploads a mission and starts it,
monitors AUTO flight, then takes manual control again and lands.

State transitions tested:
  STABILIZE -> GUIDED -> ARM -> TAKEOFF -> MANUAL(RC) -> AUTO(mission) -> GUIDED -> LAND -> DISARM
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

def log_state(label):
    t = telemetry()
    print(f"  [{label}] mode={t['mode']:10s} armed={t['armed']} alt={t['altitude']:.1f}m "
          f"speed={t['ground_speed']:.1f}m/s vspd={t['vertical_speed']:.1f}m/s", flush=True)
    return t

def rc(roll=0.0, pitch=0.0, throttle=0.0, yaw=0.0):
    return api("POST", "/rc/control", {
        "roll": roll, "pitch": pitch, "throttle": throttle, "yaw": yaw,
    })

def rc_center():
    return rc(0.0, 0.0, 0.0, 0.0)

def main():
    print("=" * 70)
    print("  TEST: MANUAL -> AUTONOMOUS -> MANUAL -> LAND")
    print("  State transitions within a single session")
    print("=" * 70)

    print("\n--- 0. HEALTH CHECK ---")
    h = status()
    print(f"  healthy={h['healthy']} connected={h['connected']} probe_failures={h['probe_failures']}")
    if not h['healthy']:
        print("  FATAL: Backend not healthy!")
        return

    # ── Phase 1: Takeoff ──
    print("\n--- 1. GUIDED + ARM + TAKEOFF (15m) ---")
    r = api("POST", "/mode", {"mode": "GUIDED"})
    print(f"  SET_MODE: {r['message']} (mode={r['mode']})")
    log_state("POST-GUIDED")

    r = api("POST", "/arm", {"force": True}, timeout=90)
    print(f"  ARM: {r['message']}")
    time.sleep(2)
    log_state("POST-ARM")

    r = api("POST", "/takeoff", {"altitude": 15}, timeout=60)
    print(f"  TAKEOFF: {r['message']}")
    
    for i in range(30):
        time.sleep(1)
        t = log_state(f"CLIMB t={i+1}s")
        if t['altitude'] >= 13:
            print(f"  Reached {t['altitude']:.1f}m -- ready for manual")
            break

    # ── Phase 2: Manual flight via RC override ──
    print("\n--- 2. MANUAL FLIGHT (RC Override, 10s) ---")
    print("  Sending: roll=+0.2 throttle=+0.1 (climb + drift right)")
    
    for i in range(10):
        rc(roll=0.2, pitch=0.0, throttle=0.1, yaw=0.0)
        time.sleep(1)
        t = log_state(f"MANUAL t={i+1}s")

    print("  Centering controls")
    rc_center()
    time.sleep(2)
    log_state("POST-RC-CENTER")

    # ── Phase 3: Transition to AUTONOMOUS ──
    print("\n--- 3. TRANSITION TO AUTONOMOUS (upload + start mission) ---")
    r = api("POST", "/mode", {"mode": "GUIDED"})
    print(f"  SET_MODE GUIDED: {r['message']} (mode={r['mode']})")
    log_state("POST-GUIDED2")

    t = telemetry()
    lat = t['latitude']
    lon = t['longitude']
    alt = t['altitude']
    print(f"  Current: lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}m")

    waypoints = [
        {"lat": lat, "lon": lon, "alt": alt, "type": "WAYPOINT"},
        {"lat": lat + 0.0001, "lon": lon, "alt": alt, "type": "WAYPOINT"},
        {"lat": lat + 0.0001, "lon": lon + 0.0001, "alt": alt, "type": "WAYPOINT"},
        {"lat": lat, "lon": lon + 0.0001, "alt": alt, "type": "WAYPOINT"},
    ]

    print(f"  Uploading {len(waypoints)} waypoints...")
    r = api("POST", "/upload_mission", {"waypoints": waypoints}, timeout=30)
    print(f"  UPLOAD: {r['message']}")
    log_state("POST-UPLOAD")

    print("  Starting mission...")
    r = api("POST", "/start_mission", timeout=30)
    print(f"  START: {r['message']}")
    log_state("POST-START")

    # ── Phase 4: Monitor AUTO, interrupt with manual, resume ──
    print("\n--- 4. AUTO FLIGHT (30s, with mid-flight manual interruption) ---")
    for i in range(30):
        time.sleep(1)
        t = log_state(f"AUTO t={i+1}s")

        if i == 10:
            print("\n  === INTERRUPT: switching to GUIDED + RC manual ===")
            r = api("POST", "/mode", {"mode": "GUIDED"})
            print(f"  SET_MODE GUIDED: {r['message']} (mode={r['mode']})")
            log_state("INTERRUPT-GUIDED")

            print("  Manual control: pitch=+0.3 (forward)")
            for j in range(5):
                rc(roll=0.0, pitch=0.3, throttle=0.0, yaw=0.0)
                time.sleep(1)
                log_state(f"MANUAL2 t={j+1}s")

            print("  Centering + resuming mission")
            rc_center()
            time.sleep(1)
            r = api("POST", "/start_mission", timeout=30)
            print(f"  RESUME: {r['message']}")
            log_state("RESUME")

    # ── Phase 5: LAND ──
    print("\n--- 5. LAND + DISARM ---")
    r = api("POST", "/land", timeout=60)
    print(f"  LAND: {r['message']}")
    
    for i in range(30):
        time.sleep(1)
        t = log_state(f"LANDING t={i+1}s")
        if not t['armed']:
            print("  Disarmed!")
            break

    r = api("POST", "/disarm", {"force": True}, timeout=15)
    print(f"  DISARM: {r['message']}")
    log_state("FINAL")

    print("\n--- HEALTH CHECK ---")
    h = status()
    print(f"  healthy={h['healthy']} connected={h['connected']} probe_failures={h['probe_failures']}")

    print("\n" + "=" * 70)
    print("  TRANSITION TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
