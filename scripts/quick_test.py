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

s = api('GET', '/api/status')
print(f'Status: armed={s.get("armed")} mode={s.get("mode")}')

print('\n--- ARM ---')
arm = api('POST', '/api/arm', {"force": True}, timeout=60)
print(f'ARM result: {arm}')
time.sleep(3)
s = api('GET', '/api/status')
print(f'After ARM: armed={s.get("armed")} mode={s.get("mode")}')

print('\n--- THROTTLE 70% (5s) ---')
for i in range(50):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
t = api('GET', '/api/telemetry')
print(f'Alt: {t.get("altitude",0) - 584:.1f}m  speed: {t.get("speed",0):.1f}m/s')

print('\n--- PITCH FWD (3s) ---')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": -0.25, "roll": 0.0})
    time.sleep(0.1)
t = api('GET', '/api/telemetry')
print(f'Alt: {t.get("altitude",0) - 584:.1f}m  pitch: {t.get("attitude",{}).get("pitch",0):.1f}deg')

print('\n--- ROLL RIGHT (3s) ---')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": 0.0, "roll": 0.25})
    time.sleep(0.1)
t = api('GET', '/api/telemetry')
print(f'Alt: {t.get("altitude",0) - 584:.1f}m  roll: {t.get("attitude",{}).get("roll",0):.1f}deg')

print('\n--- YAW LEFT (3s) ---')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": -0.30, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
t = api('GET', '/api/telemetry')
print(f'Alt: {t.get("altitude",0) - 584:.1f}m  yaw: {t.get("attitude",{}).get("yaw",0):.1f}deg')

print('\n--- IDLE (throttle 15%, 2s) ---')
for i in range(20):
    api('POST', '/api/rc/control', {"throttle": 0.15, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
time.sleep(2)
t = api('GET', '/api/telemetry')
s = api('GET', '/api/status')
print(f'Alt: {t.get("altitude",0) - 584:.1f}m  armed={s.get("armed")} mode={s.get("mode")}')

print('\n--- DISARM ---')
disarm = api('POST', '/api/disarm', {"force": True}, timeout=60)
print(f'DISARM result: {disarm}')
time.sleep(5)
s = api('GET', '/api/status')
print(f'After DISARM: armed={s.get("armed")} mode={s.get("mode")}')

h = api('GET', '/api/connection/status')
print(f'\n--- HEALTH ---')
for k in ['healthy','connected','socket_alive','probe_failures','reconnecting','needs_reconnect','heartbeat_age_s','last_msg_age_s']:
    print(f'  {k}: {h.get(k)}')

if not s.get('armed') and h.get('healthy'):
    print('\n=== TODOS LOS TESTS PASARON ===')
else:
    print('\n=== HAY FALLOS ===')
