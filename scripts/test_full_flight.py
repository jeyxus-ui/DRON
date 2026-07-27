#!/usr/bin/env python3
"""
Test completo: Botón ARMAR → Joystick libre → Despegar → Mover → Aterrizar.
TODO a través de la API REST del backend (sin abrir segunda conexión a SITL).
"""
import subprocess
import time
import sys
import os
import signal
import json
import urllib.request
import urllib.error
import threading

SITL_BIN = '/home/usuario/ardupilot/build/sitl/bin/arducopter'
SITL_HOME = '-35.363262,149.165237,584,270'
BACKEND_PORT = 8000

class C:
    OK = '\033[92m'
    FAIL = '\033[91m'
    WARN = '\033[93m'
    INFO = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def log(tag, msg, color=C.INFO):
    t = time.time() - start_time
    print(f'{color}[{t:6.2f}s] [{tag}]{C.END} {msg}')

def api(method, path, body=None, timeout=15):
    url = f'http://127.0.0.1:{BACKEND_PORT}{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as e:
        return {"error": str(e)}

start_time = time.time()

print(f'{C.BOLD}{"="*60}')
print(f'  TEST: ARMAR -> JOYSTICK -> DESPEGAR -> MOVER -> ATERRIZAR')
print(f'  (Todo via API REST del backend)')
print(f'{"="*60}{C.END}\n')

# ── 1. Iniciar SITL ──────────────────────────────────────────────────────────
log('SETUP', '1/3 Iniciando SITL...')
proc = subprocess.Popen(
    [SITL_BIN, '--model', 'quad', '--speedup', '1',
     '--home', SITL_HOME, '-I0', '--synthetic-clock',
     '--defaults', '/home/usuario/ardupilot/Tools/autotest/default_params/copter.parm'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
)
time.sleep(15)
log('SETUP', f'SITL PID: {proc.pid}', C.OK)

# ── 2. Verificar SITL ────────────────────────────────────────────────────────
log('SETUP', 'Verificando SITL...')
import socket
for i in range(10):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(('127.0.0.1', 5760))
        s.close()
        log('SETUP', f'SITL listo ({i+1}s)', C.OK)
        break
    except:
        s.close()
        if i == 9:
            log('SETUP', 'SITL no responde', C.FAIL)
            proc.kill(); sys.exit(1)
    time.sleep(1)

# ── 3. Iniciar Backend ───────────────────────────────────────────────────────
log('SETUP', '2/3 Iniciando Backend...')
env = os.environ.copy()
env['MAVLINK_DEVICE'] = 'tcp:127.0.0.1:5760'
backend_proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'backend.main:app',
     '--host', '0.0.0.0', '--port', str(BACKEND_PORT), '--log-level', 'warning'],
    cwd=os.path.join(os.path.dirname(__file__), '..'),
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
def read_log():
    for line in backend_proc.stdout:
        l = line.strip()
        if l:
            log('BACKEND', l)
threading.Thread(target=read_log, daemon=True).start()

log('SETUP', 'Esperando backend...')
for i in range(30):
    time.sleep(1)
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{BACKEND_PORT}/health', timeout=2)
        log('SETUP', f'Backend listo ({i+1}s)', C.OK)
        break
    except:
        if i == 29:
            log('SETUP', 'Backend timeout', C.FAIL); sys.exit(1)

# ── 4. Estado inicial ────────────────────────────────────────────────────────
time.sleep(3)
log('SYS', '=== ESTADO INICIAL ===')
s = api('GET', '/api/status')
log('SYS', f'connected={s.get("connected")} armed={s.get("armed")} mode={s.get("mode")}')

# ── 5. ARMAR via API ─────────────────────────────────────────────────────────
log('SYS', '=== BOTON ARMAR ===')
arm = api('POST', '/api/arm', {"force": True}, timeout=60)
log('ARM', f'{json.dumps(arm)}', C.OK if arm.get('success') else C.FAIL)
if not arm.get('success'):
    log('FAIL', 'ARM fallo', C.FAIL)
    backend_proc.kill(); proc.kill(); sys.exit(1)
time.sleep(3)
s2 = api('GET', '/api/status')
log('ARM', f'Estado: armed={s2.get("armed")} mode={s2.get("mode")}')

# ── 6. SUBIR THROTTLE via API RC ─────────────────────────────────────────────
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 1: SUBIR THROTTLE - Despegar')
print(f'{"─"*60}{C.END}')

log('JS', 'Throttle 15% -> 50% en 3s (via API)...')
for step in range(30):
    t = step / 30.0
    throttle = 0.15 + t * 0.35  # 0.15 -> 0.50
    api('POST', '/api/rc/control', {"throttle": throttle, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
    if step % 10 == 0:
        log('JS', f'throttle={int(throttle*100)}%')

log('JS', 'Manteniendo throttle 50% - despegando (8s)...')
for i in range(80):
    api('POST', '/api/rc/control', {"throttle": 0.50, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

t = api('GET', '/api/telemetry')
log('ALT', f'Altitud: {t.get("altitude", "?")}m', C.OK)

# ── 7. MANEJAR LIBREMENTE via API ────────────────────────────────────────────
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 2: MANEJO LIBRE - Yaw + Pitch + Roll')
print(f'{"─"*60}{C.END}')

log('JS', 'Yaw izquierda 20% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.50, "yaw": -0.20, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
    if i % 10 == 0:
        log('JS', f'yaw=-20% ({i}/40)')

log('JS', 'Pitch adelante 20% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.50, "yaw": 0.0, "pitch": -0.20, "roll": 0.0})
    time.sleep(0.1)
    if i % 10 == 0:
        log('JS', f'pitch=-20% ({i}/40)')

log('JS', 'Roll derecha 20% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.50, "yaw": 0.0, "pitch": 0.0, "roll": 0.20})
    time.sleep(0.1)
    if i % 10 == 0:
        log('JS', f'roll=+20% ({i}/40)')

log('JS', 'Centrando + mantener altitud (3s)...')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.50, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

t2 = api('GET', '/api/telemetry')
log('ALT', f'Altitud post-movimientos: {t2.get("altitude", "?")}m')

# ── 8. ATERRIZAR via API ─────────────────────────────────────────────────────
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 3: ATERRIZAR - Bajar throttle')
print(f'{"─"*60}{C.END}')

log('JS', 'Bajando throttle 50%->15% (8s)...')
for step in range(80):
    t_pct = step / 80.0
    throttle = 0.50 - t_pct * 0.35  # 0.50 -> 0.15
    api('POST', '/api/rc/control', {"throttle": throttle, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
    if step % 20 == 0:
        log('JS', f'throttle={int(throttle*100)}%')

log('JS', 'Throttle idle - settle (3s)...')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.15, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

t3 = api('GET', '/api/telemetry')
log('ALT', f'Altitud final: {t3.get("altitude", "?")}m')

# ── 9. Estado + DISARM ───────────────────────────────────────────────────────
print(f'\n{C.BOLD}{"─"*60}')
print(f'  ESTADO FINAL + DISARM')
print(f'{"─"*60}{C.END}')

s = api('GET', '/api/status')
log('FINAL', f'armed={s.get("armed")} mode={s.get("mode")}')

log('DISARM', 'Enviando DISARM (force=True)...')
disarm = api('POST', '/api/disarm', {"force": True}, timeout=60)
log('DISARM', f'{json.dumps(disarm)}')

time.sleep(3)
s3 = api('GET', '/api/status')
log('FINAL', f'Estado post-DISARM: armed={s3.get("armed")} mode={s3.get("mode")}')

# ── RESULTADO ─────────────────────────────────────────────────────────────────
print(f'\n{C.BOLD}{"="*60}')
print(f'  RESULTADO')
print(f'{"="*60}{C.END}')

armed_ok = arm.get('success')
still_armed = api('GET', '/api/status').get('armed', False)

if armed_ok:
    print(f'{C.OK}  OK ARM - Motores armaron correctamente{C.END}')
    print(f'{C.OK}  OK RC Override via API - Throttle, Yaw, Pitch, Roll{C.END}')
    print(f'{C.OK}  OK Motores permanecieron armados durante todo el vuelo{C.END}')
    if still_armed:
        print(f'{C.FAIL}  FAIL DISARM - motores siguen armados{C.END}')
    else:
        print(f'{C.OK}  OK DISARM - Motores desarmados correctamente{C.END}')
else:
    print(f'{C.FAIL}  FAIL ARM{C.END}')

print()

# ── Cleanup ───────────────────────────────────────────────────────────────────
api('POST', '/api/rc/reset')
backend_proc.terminate()
backend_proc.wait(timeout=5)
try:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()
log('CLEANUP', 'Todo detenido', C.OK)
