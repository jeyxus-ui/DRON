#!/usr/bin/env python3
"""
Test: Simulación de uso real de la app
  ARM → Control manual (volar) → Ruta autónoma → Control manual → Ruta → LAND

Simula el flujo real:
  1. Usuario arranca el dron
  2. Vuela manualmente con joystick
  3. Activa ruta autónoma (mission)
  4. Toma control manual en medio del vuelo
  5. Reanuda ruta
  6. Toma control de nuevo
  7. Aterriza
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

def log(label):
    t = telemetry()
    hdg = t.get('heading', 0)
    lat = t.get('latitude', 0)
    lon = t.get('longitude', 0)
    print(f"  [{label}] mode={t['mode']:8s} armed={str(t['armed']):5s} "
          f"alt={t['altitude']:.1f}m spd={t['ground_speed']:.1f}m/s "
          f"hdg={hdg:.0f} lat={lat:.6f} lon={lon:.6f}", flush=True)
    return t

def main():
    print("=" * 70)
    print("  SIMULACIÓN DE USO REAL DE LA APP")
    print("  ARM → Manual → Ruta → Manual → Ruta → LAND")
    print("=" * 70)

    # ── 0. HEALTH ──
    print("\n--- 0. HEALTH CHECK ---")
    h = status()
    print(f"  healthy={h['healthy']} connected={h['connected']} "
          f"probe_failures={h['probe_failures']}")
    if not h['healthy']:
        print("  FATAL: Backend not healthy!")
        sys.exit(1)

    # ── 1. ARRANQUE ──
    print("\n--- 1. ARRANQUE (GUIDED → ARM → TAKEOFF 12m) ---")
    r = api("POST", "/mode", {"mode": "GUIDED"})
    print(f"  SET_MODE: {r['message']}")
    log("mode-guided")

    r = api("POST", "/arm", {"force": True}, timeout=90)
    print(f"  ARM: {r['message']}")
    time.sleep(2)
    log("armed")

    r = api("POST", "/takeoff", {"altitude": 12}, timeout=60)
    print(f"  TAKEOFF: {r['message']}")

    for i in range(15):
        time.sleep(1)
        t = log(f"climb t={i+1}s")
        if t['altitude'] >= 585:
            print(f"    -> En el aire ({t['altitude']:.1f}m)")
            break

    # ── 2. CONTROL MANUAL: Volar en cuadrado ──
    print("\n--- 2. CONTROL MANUAL: Vuelo en cuadrado ---")
    r = api("POST", "/mode", {"mode": "STABILIZE"})
    print(f"  SET_MODE STABILIZE: {r['message']}")
    time.sleep(2)
    log("stab")

    base_throttle = 0.55
    corners = [
        ("Avanzar (Pitch forward)", {"pitch": 0.3, "throttle": base_throttle}),
        ("Girar derecha (Yaw right)", {"yaw": 0.4, "throttle": base_throttle}),
        ("Avanzar (Pitch forward)", {"pitch": 0.3, "throttle": base_throttle}),
        ("Girar derecha (Yaw right)", {"yaw": 0.4, "throttle": base_throttle}),
        ("Avanzar (Pitch forward)", {"pitch": 0.3, "throttle": base_throttle}),
        ("Girar derecha (Yaw right)", {"yaw": 0.4, "throttle": base_throttle}),
        ("Avanzar (Pitch forward)", {"pitch": 0.3, "throttle": base_throttle}),
    ]

    t0 = telemetry()
    for name, controls in corners:
        print(f"\n  >>> {name}")
        for i in range(3):
            rc(**controls)
            time.sleep(1)
            log(f"    t={i+1}s")
        rc(throttle=base_throttle)
        time.sleep(0.5)

    t1 = telemetry()
    dist_moved = ((t1['latitude'] - t0['latitude'])**2 +
                  (t1['longitude'] - t0['longitude'])**2) ** 0.5 * 111320
    print(f"\n  Distancia recorrida: ~{dist_moved:.1f}m")
    log("POST-MANUAL")

    # ── 3. PRIMERA RUTA AUTÓNOMA ──
    print("\n--- 3. PRIMERA RUTA AUTÓNOMA ---")
    r = api("POST", "/mode", {"mode": "GUIDED"})
    print(f"  SET_MODE GUIDED: {r['message']}")
    time.sleep(1)
    t = telemetry()
    lat, lon, alt = t['latitude'], t['longitude'], t['altitude']

    wps = [
        {"lat": lat + 0.0002, "lon": lon, "alt": alt, "type": "WAYPOINT"},
        {"lat": lat + 0.0002, "lon": lon + 0.0002, "alt": alt, "type": "WAYPOINT"},
        {"lat": lat, "lon": lon + 0.0002, "alt": alt, "type": "WAYPOINT"},
    ]
    print(f"  Subiendo {len(wps)} waypoints desde ({lat:.6f}, {lon:.6f})")
    r = api("POST", "/upload_mission", {"waypoints": wps}, timeout=30)
    print(f"  UPLOAD: {r['message']}")

    r = api("POST", "/start_mission", timeout=30)
    print(f"  START: {r['message']}")

    print("  Monitoreando vuelo autónomo...")
    wp_reached = 0
    for i in range(20):
        time.sleep(1)
        t = log(f"  AUTO1 t={i+1}s")

    print(f"  Ruta 1 completada, pasando a control manual...")

    # ── 4. CONTROL MANUAL INTERMEDIO ──
    print("\n--- 4. CONTROL MANUAL (interrumpir ruta) ---")
    r = api("POST", "/mode", {"mode": "STABILIZE"})
    print(f"  SET_MODE STABILIZE: {r['message']}")
    time.sleep(1)

    print("  >>> Subir (throttle up)")
    for i in range(3):
        rc(throttle=0.70)
        time.sleep(1)
        log(f"    climb t={i+1}s")

    print("  >>> Girar (yaw left)")
    for i in range(3):
        rc(yaw=-0.4, throttle=base_throttle)
        time.sleep(1)
        log(f"    yaw t={i+1}s")

    print("  >>> Avanzar (pitch forward)")
    for i in range(3):
        rc(pitch=0.3, throttle=base_throttle)
        time.sleep(1)
        log(f"    pitch t={i+1}s")

    log("POST-MANUAL2")

    # ── 5. SEGUNDA RUTA AUTÓNOMA ──
    print("\n--- 5. SEGUNDA RUTA AUTÓNOMA ---")
    r = api("POST", "/mode", {"mode": "GUIDED"})
    print(f"  SET_MODE GUIDED: {r['message']}")
    time.sleep(1)
    t = telemetry()
    lat2, lon2, alt2 = t['latitude'], t['longitude'], t['altitude']

    wps2 = [
        {"lat": lat2 - 0.0001, "lon": lon2, "alt": alt2, "type": "WAYPOINT"},
        {"lat": lat2 - 0.0001, "lon": lon2 - 0.0001, "alt": alt2, "type": "WAYPOINT"},
    ]
    print(f"  Subiendo {len(wps2)} waypoints desde ({lat2:.6f}, {lon2:.6f})")
    r = api("POST", "/upload_mission", {"waypoints": wps2}, timeout=30)
    print(f"  UPLOAD: {r['message']}")

    r = api("POST", "/start_mission", timeout=30)
    print(f"  START: {r['message']}")

    print("  Monitoreando vuelo autónomo...")
    for i in range(15):
        time.sleep(1)
        log(f"  AUTO2 t={i+1}s")

    # ── 6. ÚLTIMO CONTROL MANUAL + LAND ──
    print("\n--- 6. CONTROL FINAL → LAND → DISARM ---")
    r = api("POST", "/mode", {"mode": "STABILIZE"})
    print(f"  SET_MODE STABILIZE: {r['message']}")
    time.sleep(1)

    print("  >>> Descender suavemente")
    for i in range(5):
        rc(throttle=0.40, pitch=0.0, roll=0.0, yaw=0.0)
        time.sleep(1)
        log(f"    descend t={i+1}s")

    print("  Centrar y aterrizar")
    rc(throttle=0.0)
    time.sleep(1)
    r = api("POST", "/mode", {"mode": "GUIDED"})
    time.sleep(1)
    r = api("POST", "/land", timeout=120)
    print(f"  LAND: {r['message']}")

    for i in range(120):
        time.sleep(1)
        t = log(f"  LANDING t={i+1}s")
        if not t['armed']:
            print("  Desarmado por LAND!")
            break

    r = api("POST", "/disarm", {"force": True}, timeout=15)
    print(f"  DISARM: {r['message']}")
    log("FINAL")

    # ── 7. HEALTH FINAL ──
    print("\n--- 7. HEALTH FINAL ---")
    h = status()
    print(f"  healthy={h['healthy']} connected={h['connected']} "
          f"probe_failures={h['probe_failures']}")

    print("\n" + "=" * 70)
    print("  SIMULACIÓN COMPLETADA")
    print("=" * 70)

if __name__ == "__main__":
    main()
