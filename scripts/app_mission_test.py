import json, urllib.request, time, asyncio, websockets, sys

API = "http://127.0.0.1:8000"
WS  = "ws://127.0.0.1:8000/ws/telemetry"

def api(method, path, body=None, timeout=90):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f'{API}{path}', data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

async def run():
    HOME_LAT = -35.363262
    HOME_LON = 149.165237

    WAYPOINTS = [
        {"latitude": HOME_LAT + 0.0003, "longitude": HOME_LON,          "altitude": 15},
        {"latitude": HOME_LAT + 0.0003, "longitude": HOME_LON + 0.0003, "altitude": 15},
        {"latitude": HOME_LAT,          "longitude": HOME_LON + 0.0003, "altitude": 15},
        {"latitude": HOME_LAT,          "longitude": HOME_LON,          "altitude": 15},
    ]

    print('='*65)
    print('  RUTA DESDE APP (REST + WebSocket telemetry)')
    print('='*65)

    async with websockets.connect(WS, ping_interval=None, ping_timeout=None) as ws:
        await asyncio.sleep(2)

        print('\n--- GUIDED ---')
        r = api('POST', '/api/mode', {"mode": "GUIDED"})
        print(f'  {r}')
        time.sleep(2)

        print('\n--- ARM ---')
        r = api('POST', '/api/arm', {"force": True}, timeout=90)
        print(f'  {r}')
        time.sleep(3)

        s = api('GET', '/api/status')
        print(f'  armed={s.get("armed")} mode={s.get("mode")}')

        if not s.get("armed"):
            print('  FALLO: dron no armado')
            return

        print('\n--- TAKEOFF 10m ---')
        r = api('POST', '/api/takeoff', {"altitude": 10}, timeout=60)
        print(f'  {r}')

        alt = 0
        for i in range(45):
            time.sleep(1)
            try:
                t = api('GET', '/api/telemetry', timeout=5)
            except Exception:
                continue
            alt = round(t.get('altitude', 584) - 584, 1)
            if i % 5 == 0:
                print(f'    t={i+1}s alt={alt}m')
            if alt > 8:
                print(f'    Listo a {alt}m')
                break

        if alt < 3:
            print(f'  TAKEOFF falló (alt={alt}m) — intentando LAND+DISARM')
            try:
                api('POST', '/api/land', timeout=30)
                time.sleep(5)
                api('POST', '/api/disarm', {"force": True}, timeout=30)
            except Exception as e:
                print(f'  Error en cleanup: {e}')
            return

        print('\n--- SUBIR RUTA ---')
        formatted = [{"latitude": wp["latitude"], "longitude": wp["longitude"], "altitude": wp["altitude"]} for wp in WAYPOINTS]
        try:
            r = api('POST', '/api/upload_mission', {"waypoints": formatted}, timeout=60)
            print(f'  UPLOAD: {r}')
        except Exception as e:
            print(f'  UPLOAD error: {e}')
            print('  Intentando RTL...')
            try:
                api('POST', '/api/land', timeout=30)
                time.sleep(10)
                api('POST', '/api/disarm', {"force": True}, timeout=30)
            except Exception:
                pass
            return

        time.sleep(2)

        print('\n--- INICIAR MISION ---')
        try:
            r = api('POST', '/api/start_mission', timeout=60)
            print(f'  START: {r}')
        except Exception as e:
            print(f'  START error: {e}')
            return

        print('\n--- Monitoreando vuelo (180s) ---')
        wp_reached = set()
        home_idx = 3
        start = time.time()
        last_print = 0
        ws_ok = True
        while time.time() - start < 180:
            if ws_ok:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f'  WS error: {e} — fallback a REST polling')
                    ws_ok = False
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if data.get("type") != "telemetry":
                    continue
                t = data.get("data", {})
            else:
                try:
                    t = api('GET', '/api/telemetry', timeout=5)
                except Exception:
                    time.sleep(2)
                    continue
                time.sleep(1)
            alt = round(t.get('altitude', 584) - 584, 1)
            lat = t.get('latitude', 0)
            lon = t.get('longitude', 0)
            mode = t.get('mode')
            elapsed = round(time.time() - start, 0)

            if elapsed - last_print < 2 and len(wp_reached) == 0:
                continue
            last_print = elapsed

            for i, wp in enumerate(WAYPOINTS):
                if i in wp_reached:
                    continue
                dlat = abs(lat - wp['latitude']) * 111000
                dlon = abs(lon - wp['longitude']) * 111000
                dist = round((dlat**2 + dlon**2)**0.5, 1)
                if dist < 17:
                    if i == home_idx and len(wp_reached) < 2:
                        continue
                    wp_reached.add(i)
                    print(f'  [{elapsed:3.0f}s] >>> WP{i+1} ALCANZADO! (dist={dist:.0f}m)')

            print(f'  [{elapsed:3.0f}s] alt={alt:6.1f}m mode={mode:10s} wp={len(wp_reached)}/4')

            if len(wp_reached) >= 4:
                print('  >>> TODOS LOS WAYPOINTS ALCANZADOS')
                break

            if mode in ("LAND", "RTL") and alt < 1:
                print(f'  >>> Misión completada (mode={mode}, alt={alt}m)')
                break

        print('\n--- LAND ---')
        r = api('POST', '/api/land')
        print(f'  {r}')
        for i in range(30):
            time.sleep(1)
            try:
                t = api('GET', '/api/telemetry', timeout=5)
            except Exception:
                continue
            alt = round(t.get('altitude', 584) - 584, 1)
            if alt < 1:
                print(f'  Aterrizado a {alt}m')
                break

        print('\n--- DISARM ---')
        time.sleep(2)
        r = api('POST', '/api/disarm', {"force": True}, timeout=60)
        print(f'  {r}')

        print('\n--- Health final ---')
        h = api('GET', '/api/connection/status')
        for k in ['healthy','connected','probe_failures','reconnecting','heartbeat_age_s','last_msg_age_s']:
            print(f'  {k}: {h.get(k)}')

        if h.get('healthy'):
            print('\n=== RUTA COMPLETADA ===')
        else:
            print('\n=== HAY FALLOS ===')

asyncio.run(run())
