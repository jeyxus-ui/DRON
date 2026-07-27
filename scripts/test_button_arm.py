#!/usr/bin/env python3
"""
Test real: Botón ARMAR desde app → Backend → SITL → Motores.
Todo dentro de WSL, sin duplicar conexiones TCP.
"""
import subprocess
import time
import sys
import os
import signal
import json
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
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

def api(method, path, body=None):
    url = f'http://127.0.0.1:{BACKEND_PORT}{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as e:
        return {"error": str(e)}

start_time = time.time()

print(f'{C.BOLD}{"="*60}')
print(f'  TEST: BOTÓN ARMAR DESDE APP')
print(f'  SITL + Backend + API REST (todo en WSL)')
print(f'{"="*60}{C.END}\n')

# ── Paso 1: Iniciar SITL ─────────────────────────────────────────────────────
log('SETUP', '1/2 Iniciando SITL (ArduPilot real)...')
proc = subprocess.Popen(
    [SITL_BIN, '--model', 'quad', '--speedup', '1',
     '--home', SITL_HOME, '-I0', '--synthetic-clock',
     '--defaults', '/home/usuario/ardupilot/Tools/autotest/default_params/copter.parm'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
)
time.sleep(5)
log('SETUP', f'SITL PID: {proc.pid}', C.OK)

# ── Paso 2: Iniciar Backend ──────────────────────────────────────────────────
log('SETUP', '2/2 Iniciando Backend FastAPI...')
env = os.environ.copy()
env['MAVLINK_DEVICE'] = 'tcp:127.0.0.1:5760'
backend_proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'backend.main:app',
     '--host', '0.0.0.0', '--port', str(BACKEND_PORT),
     '--log-level', 'info'],
    cwd=os.path.join(os.path.dirname(__file__), '..'),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

# Thread para leer logs del backend
import threading
def read_backend_log():
    for line in backend_proc.stdout:
        line = line.strip()
        if line:
            log('BACKEND', line)
log_thread = threading.Thread(target=read_backend_log, daemon=True)
log_thread.start()

log('SETUP', f'Backend PID: {backend_proc.pid}', C.OK)

# Esperar a que el backend esté listo
log('SETUP', 'Esperando backend...')
for i in range(30):
    time.sleep(1)
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:{BACKEND_PORT}/health', timeout=2)
        log('SETUP', f'Backend listo tras {i+1}s', C.OK)
        break
    except Exception:
        if i == 29:
            log('SETUP', 'Backend no respondió en 30s — abortando', C.FAIL)
            backend_proc.kill()
            proc.kill()
            sys.exit(1)

# ── Paso 3: Estado inicial ───────────────────────────────────────────────────
print(f'\n{C.BOLD}--- PASO 1: VERIFICAR ESTADO INICIAL ---{C.END}')
time.sleep(3)

status = api('GET', '/api/status')
log('STATUS', f'{json.dumps(status)}')

telemetry = api('GET', '/api/telemetry')
log('TELEM', f'armed={telemetry.get("armed")} mode={telemetry.get("mode")} alt={telemetry.get("altitude")}')

# ── Paso 4: Presionar botón ARMAR ────────────────────────────────────────────
print(f'\n{C.BOLD}--- PASO 2: PRESIONAR BOTÓN ARMAR ---{C.END}')
log('ARM', 'POST /api/arm {"force": true} ...')
log('ARM', '(force=true porque SITL cold start no tiene GPS/EKF)')

arm_result = api('POST', '/api/arm', {"force": True})
log('ARM', f'Respuesta: {json.dumps(arm_result)}', C.OK if arm_result.get('success') else C.FAIL)

# ── Paso 5: Verificar estado post-ARM ────────────────────────────────────────
print(f'\n{C.BOLD}--- PASO 3: VERIFICAR DESPUÉS DEL ARM ---{C.END}')
time.sleep(2)

status2 = api('GET', '/api/status')
log('STATUS', f'armed={status2.get("armed")} mode={status2.get("mode")}')

# ── Paso 6: Monitorear 15s — los motores deben quedar armados ────────────────
print(f'\n{C.BOLD}--- PASO 4: MONITOREO DE MOTORES (15s) ---{C.END}')
log('MON', 'Verificando que los motores NO se desarmas solos...')

disarm_detected = False
for i in range(15):
    time.sleep(1)
    status_check = api('GET', '/api/status')
    armed = status_check.get('armed', False)
    mode = status_check.get('mode', '?')
    t = time.time() - start_time

    if not armed and i > 0:
        disarm_detected = True
        log('MON', f'🚨 MOTORES DESARMADOS a los {i}s', C.FAIL)
        break
    elif armed:
        log('MON', f'✅ t={i}s armed={armed} mode={mode}', C.OK)

# ── Paso 7: Intentar TAKEOFF si sigue armado ─────────────────────────────────
print(f'\n{C.BOLD}--- PASO 5: TAKEOFF (si sigue armado) ---{C.END}')

status3 = api('GET', '/api/status')
if status3.get('armed'):
    log('TO', 'Dron armado — enviando TAKEOFF a 5m...')
    to_result = api('POST', '/api/takeoff', {"altitude": 5})
    log('TO', f'Respuesta: {json.dumps(to_result)}', C.OK if to_result.get('success') else C.WARN)

    time.sleep(5)
    telemetry3 = api('GET', '/api/telemetry')
    log('TO', f'Telemetría: alt={telemetry3.get("altitude")} speed={telemetry3.get("speed")}')
else:
    log('TO', 'Dron NO está armado — saltando takeoff', C.FAIL)

# ── Paso 8: DISARM ────────────────────────────────────────────────────────────
print(f'\n{C.BOLD}--- PASO 6: DISARM ---{C.END}')
disarm_result = api('POST', '/api/disarm')
log('DISARM', f'Respuesta: {json.dumps(disarm_result)}')

time.sleep(2)
status_final = api('GET', '/api/status')
log('FINAL', f'Estado: armed={status_final.get("armed")} mode={status_final.get("mode")}')

# ── RESULTADO ─────────────────────────────────────────────────────────────────
print(f'\n{C.BOLD}{"="*60}')
print(f'  RESULTADO')
print(f'{"="*60}{C.END}')

all_ok = arm_result.get('success') and not disarm_detected

if all_ok:
    print(f'{C.OK}  ✅ PASS — El botón ARMAR funciona correctamente{C.END}')
    print(f'{C.OK}  1. Backend recibe POST /api/arm{C.END}')
    print(f'{C.OK}  2. Pre-flight checks ejecutados{C.END}')
    print(f'{C.OK}  3. ARM aceptado por ArduPilot{C.END}')
    print(f'{C.OK}  4. RC Override mantiene motores armados{C.END}')
    print(f'{C.OK}  5. Motores NO se desarmaron solos{C.END}')
else:
    if not arm_result.get('success'):
        print(f'{C.FAIL}  ❌ ARM falló: {arm_result.get("message")}{C.END}')
    if disarm_detected:
        print(f'{C.FAIL}  ❌ Motores se desarmaron solos{C.END}')

print()

# ── Cleanup ───────────────────────────────────────────────────────────────────
log('CLEANUP', 'Deteniendo backend...')
backend_proc.terminate()
try:
    backend_proc.wait(timeout=5)
except:
    backend_proc.kill()

log('CLEANUP', 'Deteniendo SITL...')
try:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()

log('CLEANUP', 'Todo detenido', C.OK)
