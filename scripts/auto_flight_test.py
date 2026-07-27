import json, urllib.request, time

def api(method, path, body=None, timeout=15):
    url = f'http://127.0.0.1:8000{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def show(label):
    t = api('GET', '/api/telemetry')
    alt = round(t.get('altitude', 584) - 584, 1)
    gps = t.get('latitude', 0), t.get('longitude', 0)
    att = t.get('attitude', {})
    print(f'  [{label}] armed={t.get("armed")} mode={t.get("mode")} '
          f'alt={alt}m lat={gps[0]:.6f} lon={gps[1]:.6f} '
          f'yaw={round(att.get("yaw",0),1)} speed={round(t.get("speed",0),1)}m/s')

HOME_LAT = -35.363262
HOME_LON = 149.165237

WAYPOINTS = [
    {"lat": HOME_LAT + 0.0005, "lon": HOME_LON,              "alt": 15, "name": "WP1 (Norte)"},
    {"lat": HOME_LAT + 0.0005, "lon": HOME_LON + 0.0005,     "alt": 15, "name": "WP2 (NE)"},
    {"lat": HOME_LAT,          "lon": HOME_LON + 0.0005,     "alt": 15, "name": "WP3 (Este)"},
    {"lat": HOME_LAT,          "lon": HOME_LON,              "alt": 15, "name": "WP4 (Home)"},
]

print('='*65)
print('  VUELO AUTONOMO: RUTA DE 4 WAYPOINTS')
print('='*65)

print('\n--- 1. Cambiar a GUIDED ---')
r = api('POST', '/api/mode', {"mode": "GUIDED"})
print(f'  {r}')
time.sleep(1)
show('POST-GUIDED')

print('\n--- 2. ARMAR ---')
r = api('POST', '/api/arm', {"force": True}, timeout=60)
print(f'  {r}')
time.sleep(3)
show('POST-ARM')

print('\n--- 3. TAKEOFF 15m ---')
r = api('POST', '/api/takeoff', {"altitude": 15})
print(f'  {r}')
for i in range(20):
    time.sleep(1)
    t = api('GET', '/api/telemetry')
    alt = round(t.get('altitude', 584) - 584, 1)
    print(f'  t={i+1}s alt={alt}m')
    if alt > 12:
        break
show('POST-TAKEOFF')

print('\n--- 4. RUTA DE WAYPOINTS ---')
for i, wp in enumerate(WAYPOINTS):
    print(f'\n  >> WP{i+1}: {wp["name"]} ({wp["lat"]:.6f}, {wp["lon"]:.6f}, {wp["alt"]}m)')
    r = api('POST', '/api/goto', {"latitude": wp["lat"], "longitude": wp["lon"], "altitude": wp["alt"]}, timeout=30)
    print(f'  goto result: {r}')
    for j in range(20):
        time.sleep(1)
        t = api('GET', '/api/telemetry')
        alt = round(t.get('altitude', 584) - 584, 1)
        lat = t.get('latitude', 0)
        lon = t.get('longitude', 0)
        dist_lat = abs(lat - wp['lat']) * 111000
        dist_lon = abs(lon - wp['lon']) * 111000
        dist = round((dist_lat**2 + dist_lon**2)**0.5, 1)
        print(f'    t={j+1}s alt={alt}m dist={dist}m')
        if dist < 5:
            print(f'    >>> WP{i+1} ALCANZADO')
            break
    show(f'POST-WP{i+1}')

print('\n--- 5. RTL (Return to Launch) ---')
r = api('POST', '/api/rtl')
print(f'  {r}')
for i in range(30):
    time.sleep(1)
    t = api('GET', '/api/telemetry')
    alt = round(t.get('altitude', 584) - 584, 1)
    mode = t.get('mode')
    armed = t.get('armed')
    print(f'  t={i+1}s alt={alt}m mode={mode} armed={armed}')
    if alt < 1:
        break
show('POST-RTL')

print('\n--- 6. Health final ---')
h = api('GET', '/api/connection/status')
print(f'  healthy={h.get("healthy")} connected={h.get("connected")} '
      f'probe={h.get("probe_failures")} reconnecting={h.get("reconnecting")} '
      f'hb_age={h.get("heartbeat_age_s")}s')

s = api('GET', '/api/status')
if h.get('healthy'):
    print('\n=== VUELO AUTONOMO COMPLETADO ===')
else:
    print('\n=== HAY FALLOS ===')
