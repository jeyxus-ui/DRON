import json, urllib.request, time, sys

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

def telemetry():
    t = api('GET', '/api/telemetry')
    alt = t.get('altitude', 584) - 584
    att = t.get('attitude', {})
    bat = t.get('battery', {})
    return {
        'alt': round(alt, 1),
        'roll': round(att.get('roll', 0), 1),
        'pitch': round(att.get('pitch', 0), 1),
        'yaw': round(att.get('yaw', 0), 1),
        'speed': round(t.get('speed', 0), 1),
        'armed': t.get('armed'),
        'mode': t.get('mode'),
        'vbat': bat.get('voltage', 0),
    }

def show(label):
    t = telemetry()
    print(f'  [{label}] armed={t["armed"]} mode={t["mode"]} alt={t["alt"]}m '
          f'roll={t["roll"]} pitch={t["pitch"]} yaw={t["yaw"]} '
          f'speed={t["speed"]}m/s vbat={t["vbat"]}V')

print('='*60)
print('  PRUEBA MANUAL: JOYSTICK')
print('='*60)

print('\n--- Estado inicial ---')
show('INICIO')

print('\n--- Joystick: ARMAR ---')
r = api('POST', '/api/arm', {"force": True}, timeout=60)
print(f'  ARM: {r}')
time.sleep(3)
show('POST-ARM')

print('\n--- Joystick: THROTTLE 65% (subir) 5s ---')
for i in range(50):
    api('POST', '/api/rc/control', {"throttle": 0.65, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
show('THROTTLE 65%')

print('\n--- Joystick: SOSTENER throttle 65% 5s más ---')
for i in range(50):
    api('POST', '/api/rc/control', {"throttle": 0.65, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
show('SOSTENER')

print('\n--- Joystick: PITCH ADELANTE -30% 3s ---')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.65, "yaw": 0.0, "pitch": -0.30, "roll": 0.0})
    time.sleep(0.1)
show('PITCH FWD')

print('\n--- Joystick: ROLL DERECHA +30% 3s ---')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.65, "yaw": 0.0, "pitch": 0.0, "roll": 0.30})
    time.sleep(0.1)
show('ROLL DER')

print('\n--- Joystick: YAW IZQUIERDA -30% 3s ---')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.65, "yaw": -0.30, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
show('YAW IZQ')

print('\n--- Joystick: THROTTLE BAJA 20% (aterrizar) 5s ---')
for i in range(50):
    throttle = 0.65 - (i / 50.0) * 0.50
    api('POST', '/api/rc/control', {"throttle": throttle, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
show('BAJANDO')

print('\n--- Throttle idle 15% ---')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.15, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
time.sleep(2)
show('IDLE')

print('\n--- Joystick: DISARMAR ---')
r = api('POST', '/api/disarm', {"force": True}, timeout=60)
print(f'  DISARM: {r}')
time.sleep(5)
show('POST-DISARM')

print('\n--- Health final ---')
h = api('GET', '/api/connection/status')
print(f'  healthy={h.get("healthy")} connected={h.get("connected")} '
      f'probe={h.get("probe_failures")} reconnecting={h.get("reconnecting")} '
      f'hb_age={h.get("heartbeat_age_s")}s msg_age={h.get("last_msg_age_s")}s')

s = api('GET', '/api/status')
if not s.get('armed') and h.get('healthy'):
    print('\n=== PRUEBA MANUAL COMPLETADA EXITOSAMENTE ===')
else:
    print('\n=== HAY FALLOS ===')
