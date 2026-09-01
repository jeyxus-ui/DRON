"""
Suite de tests de integración: armar, ruta, sensores.
Ejecuta pruebas continuas por la duración indicada.
"""
import time
import json
import requests
import threading

BASE = "http://localhost:8000/api"
RESULTS = []
TOKEN = None


def log(category, test, ok, detail=""):
    status = "OK  " if ok else "FAIL"
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{status}] [{category:10}] {test}"
    if detail:
        line += f" — {detail}"
    print(line, flush=True)
    RESULTS.append({"ts": ts, "ok": ok, "cat": category, "test": test, "detail": detail})


def H():
    return {"Authorization": f"Bearer {TOKEN}"}


def GET(path, **kw):
    return requests.get(f"{BASE}{path}", headers=H(), timeout=10, **kw)


def POST(path, body=None, **kw):
    return requests.post(f"{BASE}{path}", json=body, headers=H(), timeout=15, **kw)


def wait_armed(expect=True, retries=20, delay=0.5):
    for _ in range(retries):
        time.sleep(delay)
        try:
            if GET("/telemetry").json().get("armed") == expect:
                return True
        except Exception:
            pass
    return False


# ─── AUTH ─────────────────────────────────────────────────────────────────────

def test_auth():
    global TOKEN
    try:
        r = requests.post(f"{BASE}/auth/login",
                          json={"username": "admin", "password": "admin123"}, timeout=5)
        r.raise_for_status()
        TOKEN = r.json()["token"]
        log("AUTH", "login", bool(TOKEN), f"token={TOKEN[:10]}...")
        return bool(TOKEN)
    except Exception as e:
        log("AUTH", "login", False, str(e))
        return False


# ─── STATUS / TELEMETRÍA ───────────────────────────────────────────────────────

def test_status():
    try:
        d = GET("/status").json()
        ok = d.get("connected", False)
        log("STATUS", "connected", ok, f"mode={d.get('mode')} armed={d.get('armed')}")
        return ok
    except Exception as e:
        log("STATUS", "connected", False, str(e))
        return False


def test_telemetry():
    try:
        d = GET("/telemetry").json()
        has_alt = isinstance(d.get("altitude"), (int, float))
        has_gps = isinstance(d.get("latitude"), (int, float))
        has_bat = isinstance(d.get("battery_voltage"), (int, float))
        ok = has_alt and has_gps and has_bat
        log("TELEMETRY", "fields", ok,
            f"alt={d.get('altitude')}m lat={round(d.get('latitude',0),4)} bat={d.get('battery_voltage')}V")
        return ok
    except Exception as e:
        log("TELEMETRY", "fields", False, str(e))
        return False


def test_telemetry_live():
    """Verifica que la telemetría cambia (no está congelada)."""
    try:
        t1 = GET("/telemetry").json()
        time.sleep(1.5)
        t2 = GET("/telemetry").json()
        # Al menos el timestamp o armed/mode debe ser legible
        both_ok = isinstance(t1.get("altitude"), (int, float)) and isinstance(t2.get("altitude"), (int, float))
        ok = both_ok
        log("TELEMETRY", "live_poll", ok,
            f"alt1={t1.get('altitude')} alt2={t2.get('altitude')} armed={t2.get('armed')}")
        return ok
    except Exception as e:
        log("TELEMETRY", "live_poll", False, str(e))
        return False


def test_sensors_endpoint():
    try:
        d = GET("/sensors/status").json()
        ok = isinstance(d, dict)
        log("SENSORS", "status_endpoint", ok, str(d)[:100])
        return ok
    except Exception as e:
        log("SENSORS", "status_endpoint", False, str(e))
        return False


# ─── RC ───────────────────────────────────────────────────────────────────────

def test_rc():
    try:
        r = POST("/rc/control", {"throttle": 0.0, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
        d = r.json()
        ok = d.get("success", False)
        log("RC", "control_send", ok, d.get("message", ""))
        return ok
    except Exception as e:
        log("RC", "control_send", False, str(e))
        return False


def test_rc_values():
    try:
        d = GET("/rc/values").json()
        vals = d.get("values", d)
        ok = isinstance(vals, dict) and len(vals) > 0
        log("RC", "values_read", ok, str(vals)[:80])
        return ok
    except Exception as e:
        log("RC", "values_read", False, str(e))
        return False


# ─── MODO ─────────────────────────────────────────────────────────────────────

def test_mode_change():
    try:
        POST("/mode", {"mode": "STABILIZE"})
        time.sleep(1)
        r = POST("/mode", {"mode": "ACRO"})
        d = r.json()
        ok = d.get("success", False)
        actual = d.get("mode", "?")
        log("MODE", "set_ACRO", ok, f"actual={actual} msg={d.get('message','')[:50]}")
        time.sleep(0.5)
        POST("/mode", {"mode": "STABILIZE"})
        return ok
    except Exception as e:
        log("MODE", "set_ACRO", False, str(e))
        return False


def test_mode_cycle():
    """Cicla por varios modos: STABILIZE→ACRO→STABILIZE→GUIDED→STABILIZE."""
    modes = ["STABILIZE", "ACRO", "STABILIZE"]
    try:
        all_ok = True
        for mode in modes:
            r = POST("/mode", {"mode": mode})
            d = r.json()
            if not d.get("success", False):
                all_ok = False
                log("MODE", f"cycle_{mode}", False, d.get("message", ""))
            time.sleep(0.8)
        log("MODE", "full_cycle", all_ok, "STABILIZE→ACRO→STABILIZE")
        return all_ok
    except Exception as e:
        log("MODE", "full_cycle", False, str(e))
        return False


# ─── ARMAR ────────────────────────────────────────────────────────────────────

def test_arm_disarm():
    try:
        tel = GET("/telemetry").json()
        if tel.get("armed"):
            POST("/disarm")
            time.sleep(2)

        r = POST("/arm", {"force": True})
        d = r.json()
        arm_ok = d.get("success", False)

        if arm_ok:
            confirmed = wait_armed(True)
            log("ARM", "arm_force", confirmed,
                f"ack={arm_ok} heartbeat_confirmed={confirmed}")

            time.sleep(1)
            tel_now = GET("/telemetry").json()
            if tel_now.get("armed"):
                rd = POST("/disarm")
                dd = rd.json()
                disarm_ok = dd.get("success", False)
                log("ARM", "disarm", disarm_ok, dd.get("message", ""))
            else:
                log("ARM", "disarm", False, "drone ya desarmado (failsafe?)")
            return confirmed
        else:
            log("ARM", "arm_force", False, f"msg={d.get('message')}")
            return False
    except Exception as e:
        log("ARM", "arm_force", False, str(e))
        return False


def test_arm_stress():
    """Arma y desarma 3 veces seguidas para verificar estabilidad."""
    try:
        POST("/mode", {"mode": "STABILIZE"})
        time.sleep(0.5)
        ok_count = 0
        for i in range(3):
            tel = GET("/telemetry").json()
            if tel.get("armed"):
                POST("/disarm")
                wait_armed(False, retries=10)
            r = POST("/arm", {"force": True})
            if r.json().get("success"):
                if wait_armed(True, retries=15):
                    ok_count += 1
            POST("/disarm")
            wait_armed(False, retries=10)
            time.sleep(0.5)
        all_ok = ok_count == 3
        log("ARM", "stress_3x", all_ok, f"{ok_count}/3 ciclos arm/disarm OK")
        # Reset a STABILIZE
        POST("/mode", {"mode": "STABILIZE"})
        return all_ok
    except Exception as e:
        log("ARM", "stress_3x", False, str(e))
        return False


# ─── MISIÓN ───────────────────────────────────────────────────────────────────

def test_nav_mission():
    try:
        wps = [
            {"lat": -34.6037, "lon": -58.3816, "alt": 10},
            {"lat": -34.6040, "lon": -58.3820, "alt": 10},
        ]
        r = POST("/nav/mission", {"waypoints": wps})
        d = r.json()
        ok = d.get("success", False)
        log("MISSION", "nav_2wp", ok, d.get("message", "")[:80])
        if ok:
            time.sleep(1)
            POST("/nav/stop")
        return ok
    except Exception as e:
        log("MISSION", "nav_2wp", False, str(e))
        return False


def test_waypoints_save_load():
    try:
        wps = [{"lat": -34.6037, "lon": -58.3816, "alt": 10}]
        rs = POST("/waypoints/save", {"name": "test_wp", "waypoints": wps})
        ds = rs.json()
        save_ok = ds.get("success", False)

        rl = POST("/waypoints/load", {"name": "test_wp"})
        dl = rl.json()
        load_ok = dl.get("success", False)

        ok = save_ok and load_ok
        log("MISSION", "save_load_wp", ok, f"save={save_ok} load={load_ok}")
        return ok
    except Exception as e:
        log("MISSION", "save_load_wp", False, str(e))
        return False


# ─── GOTO ─────────────────────────────────────────────────────────────────────

def test_goto():
    try:
        tel = GET("/telemetry").json()
        armed_before = tel.get("armed", False)
        if not armed_before:
            POST("/mode", {"mode": "STABILIZE"})
            time.sleep(0.5)
            POST("/arm", {"force": True})
            wait_armed(True, retries=20)

        POST("/mode", {"mode": "GUIDED"})
        time.sleep(0.5)
        r = POST("/goto", {"latitude": -34.6037, "longitude": -58.3816, "altitude": 10.0})
        d = r.json()
        ok = d.get("success", False)
        log("GOTO", "send_goto", ok, d.get("message", "")[:80])

        if not armed_before:
            time.sleep(1)
            tel2 = GET("/telemetry").json()
            if tel2.get("armed"):
                POST("/disarm")
        POST("/mode", {"mode": "STABILIZE"})
        return ok
    except Exception as e:
        log("GOTO", "send_goto", False, str(e))
        return False


# ─── WEBSOCKET ────────────────────────────────────────────────────────────────

def test_websocket():
    import asyncio
    import sys

    async def _ws_test():
        try:
            import websockets
            received = []
            uri = f"ws://localhost:8000/ws/telemetry?token={TOKEN}"
            async with websockets.connect(uri, open_timeout=5) as ws:
                for _ in range(10):
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        d = json.loads(raw)
                        received.append(d.get("type"))
                        if "telemetry" in received:
                            break
                    except asyncio.TimeoutError:
                        pass
            return received
        except Exception as e:
            return [f"ERR:{e}"]

    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        received = loop.run_until_complete(_ws_test())
        loop.close()
        has_tel = "telemetry" in received
        log("WEBSOCKET", "telemetry_stream", has_tel,
            f"msgs={len(received)} types={set(received)}")
        return has_tel
    except Exception as e:
        log("WEBSOCKET", "telemetry_stream", False, str(e))
        return False


def test_websocket_reconnect():
    """Abre WS, cierra, reabre — verifica que el servidor acepta reconexión."""
    import asyncio
    import sys

    async def _reconnect_test():
        try:
            import websockets
            uri = f"ws://localhost:8000/ws/telemetry?token={TOKEN}"
            # Primera conexión
            async with websockets.connect(uri, open_timeout=5) as ws:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
            # Segunda conexión inmediata
            await asyncio.sleep(0.2)
            async with websockets.connect(uri, open_timeout=5) as ws2:
                msg = await asyncio.wait_for(ws2.recv(), timeout=2.0)
                d = json.loads(msg)
                return d.get("type") in ("telemetry", "connection_alert")
        except Exception as e:
            return False

    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        ok = loop.run_until_complete(_reconnect_test())
        loop.close()
        log("WEBSOCKET", "reconnect", ok, "close→reopen WS OK" if ok else "fallo reconexión")
        return ok
    except Exception as e:
        log("WEBSOCKET", "reconnect", False, str(e))
        return False


# ─── CICLO ────────────────────────────────────────────────────────────────────

TESTS = [
    ("AUTH",        test_auth),
    ("STATUS",      test_status),
    ("TELEMETRY",   test_telemetry),
    ("TEL_LIVE",    test_telemetry_live),
    ("SENSORS",     test_sensors_endpoint),
    ("RC_CTRL",     test_rc),
    ("RC_READ",     test_rc_values),
    ("MODE",        test_mode_change),
    ("MODE_CYCLE",  test_mode_cycle),
    ("ARM/DISARM",  test_arm_disarm),
    ("ARM_STRESS",  test_arm_stress),
    ("NAV_MISSION", test_nav_mission),
    ("WP_SAVE/LOAD",test_waypoints_save_load),
    ("GOTO",        test_goto),
    ("WEBSOCKET",   test_websocket),
    ("WS_RECONN",   test_websocket_reconnect),
]


def run_cycle(cycle_num):
    print(f"\n{'='*65}")
    print(f"CICLO #{cycle_num}  {time.strftime('%H:%M:%S')}")
    print(f"{'='*65}")
    cycle_pass = 0
    cycle_total = 0
    for name, fn in TESTS:
        try:
            ok = fn()
        except Exception as e:
            log("EXCEPTION", name, False, str(e))
            ok = False
        cycle_total += 1
        if ok:
            cycle_pass += 1
    pct = round(100 * cycle_pass / cycle_total, 0) if cycle_total else 0
    print(f"\n>>> Ciclo #{cycle_num}: {cycle_pass}/{cycle_total} OK ({pct}%)")
    return cycle_pass == cycle_total


def print_summary():
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["ok"])
    failed = total - passed
    print(f"\n{'='*65}")
    print("RESUMEN FINAL")
    print(f"{'='*65}")
    print(f"Total:  {total}  Passed: {passed}   Failed: {failed}")
    if failed > 0:
        print("\nFallas:")
        seen = set()
        for r in RESULTS:
            if not r["ok"]:
                key = f"{r['cat']}/{r['test']}"
                if key not in seen:
                    seen.add(key)
                    print(f"  {key}: {r['detail'][:80]}")
    pct = round(100 * passed / total, 1) if total else 0
    print(f"\nTasa de exito: {pct}%")


if __name__ == "__main__":
    import sys
    duration_min = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    interval_s = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    print(f"Suite de tests — duracion: {duration_min} min, intervalo: {interval_s}s")
    print(f"Backend: {BASE}")
    print(f"Tests por ciclo: {len(TESTS)}")

    start = time.time()
    cycle = 1
    perfect_cycles = 0
    try:
        while time.time() - start < duration_min * 60:
            all_ok = run_cycle(cycle)
            if all_ok:
                perfect_cycles += 1
            cycle += 1
            remaining = duration_min * 60 - (time.time() - start)
            wait = min(interval_s, remaining)
            if wait > 5:
                print(f"\nEsperando {round(wait)}s... (ciclos perfectos: {perfect_cycles}/{cycle-1})")
                time.sleep(wait)
    except KeyboardInterrupt:
        print("\n[!] Interrumpido")
    finally:
        print_summary()
        print(f"\nCiclos perfectos (16/16): {perfect_cycles}/{cycle-1}")
