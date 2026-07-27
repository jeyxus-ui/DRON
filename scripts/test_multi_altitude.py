#!/usr/bin/env python3
"""
Test avanzado: ARMAR -> subir a 3 altitudes diferentes -> maniobrar -> aterrizar -> DISARM.
Altitudes relativas al home (584m en SITL).
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
HOME_ALT = 584.0

class C:
    OK = '\033[92m'
    FAIL = '\033[91m'
    WARN = '\033[93m'
    INFO = '\033[96m'
    BOLD = '\033[1m'
    DIM = '\033[90m'
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

def get_alt():
    t = api('GET', '/api/telemetry')
    raw = t.get('altitude', -1)
    return raw - HOME_ALT

def rc(throttle=0.50, yaw=0.0, pitch=0.0, roll=0.0):
    api('POST', '/api/rc/control', {"throttle": throttle, "yaw": yaw, "pitch": pitch, "roll": roll})

def get_status():
    s = api('GET', '/api/status')
    return s.get('armed', False), s.get('mode', '?')

start_time = time.time()

print(f'{C.BOLD}{"="*70}')
print(f'  TEST AVANZADO: ARMAR -> 3 ALTITUDES -> MANIOBRAS -> ATERRIZAR -> DISARM')
print(f'{"="*70}{C.END}\n')

# ── 1. Iniciar SITL ──────────────────────────────────────────────────────────
log('SETUP', 'Iniciando SITL...')
proc = subprocess.Popen(
    [SITL_BIN, '--model', 'quad', '--speedup', '1',
     '--home', SITL_HOME, '-I0', '--synthetic-clock',
     '--defaults', '/home/usuario/ardupilot/Tools/autotest/default_params/copter.parm'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
)
time.sleep(15)
log('SETUP', f'SITL PID: {proc.pid}', C.OK)

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

# ── 2. Iniciar Backend ───────────────────────────────────────────────────────
log('SETUP', 'Iniciando Backend...')
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

time.sleep(3)

log('SYS', '=== ESTADO INICIAL ===')
s = api('GET', '/api/status')
log('SYS', f'connected={s.get("connected")} armed={s.get("armed")} mode={s.get("mode")}')
log('ALT', f'Altitud inicial relativa: {get_alt():.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 1: ARMAR
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 1: ARMAR MOTORES')
print(f'{"─"*70}{C.END}')

arm = api('POST', '/api/arm', {"force": True}, timeout=60)
log('ARM', f'success={arm.get("success")}', C.OK if arm.get('success') else C.FAIL)
if not arm.get('success'):
    log('FAIL', 'ARM fallo', C.FAIL)
    backend_proc.kill(); proc.kill(); sys.exit(1)
time.sleep(3)
armed, mode = get_status()
log('ARM', f'armed={armed} mode={mode}')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 2: DESPEGAR Y SUBIR A ~5m (throttle bajo, gradual)
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 2: DESPEGAR -> ALTITUD BAJA (~5m)')
print(f'{"─"*70}{C.END}')

log('ALT', 'Throttle 15% -> 65% en 3s...')
for step in range(30):
    t_pct = step / 30.0
    throttle = 0.15 + t_pct * 0.50
    rc(throttle=throttle)
    time.sleep(0.1)

log('ALT', 'Manteniendo 65% - subiendo (~8s)...')
for i in range(80):
    rc(throttle=0.65)
    time.sleep(0.1)
    if i % 20 == 0:
        log('ALT', f't=0.65 alt={get_alt():.1f}m')

alt_1 = get_alt()
log('ALT', f'Altitud nivel 1: {alt_1:.1f}m', C.OK if 2 < alt_1 < 15 else C.WARN)

# ══════════════════════════════════════════════════════════════════════════════
# FASE 3: MANIOBRAS EN ALTITUD BAJA
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 3: MANIOBRAS EN ALTITUD BAJA (~5m)')
print(f'{"─"*70}{C.END}')

log('JS', 'Yaw izquierda 20% (3s)...')
for i in range(30):
    rc(throttle=0.65, yaw=-0.20)
    time.sleep(0.1)

log('JS', 'Yaw derecha 20% (3s)...')
for i in range(30):
    rc(throttle=0.65, yaw=0.20)
    time.sleep(0.1)

log('JS', 'Pitch adelante 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, pitch=-0.15)
    time.sleep(0.1)

log('JS', 'Pitch atras 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, pitch=0.15)
    time.sleep(0.1)

log('JS', 'Roll izquierda 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, roll=-0.15)
    time.sleep(0.1)

log('JS', 'Roll derecha 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, roll=0.15)
    time.sleep(0.1)

log('JS', 'Centrar (2s)...')
for i in range(20):
    rc(throttle=0.65)
    time.sleep(0.1)

alt_1b = get_alt()
log('ALT', f'Altitud post-maniobras: {alt_1b:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 4: SUBIR A ~15m
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 4: SUBIR A ALTITUD MEDIA (~15m)')
print(f'{"─"*70}{C.END}')

log('ALT', 'Subiendo throttle 65% -> 72%...')
for step in range(40):
    t_pct = step / 40.0
    throttle = 0.65 + t_pct * 0.07
    rc(throttle=throttle)
    time.sleep(0.1)

for i in range(60):
    rc(throttle=0.72)
    time.sleep(0.1)
    if i % 15 == 0:
        log('ALT', f't=0.72 alt={get_alt():.1f}m')

alt_2 = get_alt()
log('ALT', f'Altitud nivel 2: {alt_2:.1f}m', C.OK if 8 < alt_2 < 35 else C.WARN)

# Maniobras en altitude media
log('JS', 'Yaw + Pitch combo (4s)...')
for i in range(40):
    rc(throttle=0.72, yaw=-0.15, pitch=-0.10)
    time.sleep(0.1)

log('JS', 'Roll combo (4s)...')
for i in range(40):
    rc(throttle=0.72, roll=0.15)
    time.sleep(0.1)

log('JS', 'Centrar (2s)...')
for i in range(20):
    rc(throttle=0.72)
    time.sleep(0.1)

for i in range(60):
    rc(throttle=0.58)
    time.sleep(0.1)
    if i % 15 == 0:
        log('ALT', f't=0.58 alt={get_alt():.1f}m')

alt_2 = get_alt()
log('ALT', f'Altitud nivel 2: {alt_2:.1f}m', C.OK if 8 < alt_2 < 25 else C.WARN)

# Maniobras en altitude media
log('JS', 'Yaw + Pitch combo (4s)...')
for i in range(40):
    rc(throttle=0.58, yaw=-0.15, pitch=-0.10)
    time.sleep(0.1)

log('JS', 'Roll combo (4s)...')
for i in range(40):
    rc(throttle=0.58, roll=0.15)
    time.sleep(0.1)

log('JS', 'Centrar (2s)...')
for i in range(20):
    rc(throttle=0.58)
    time.sleep(0.1)

alt_2b = get_alt()
log('ALT', f'Altitud post-maniobras nivel 2: {alt_2b:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 5: SUBIR A ~30m
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 5: SUBIR A ALTITUD ALTA (~30m)')
print(f'{"─"*70}{C.END}')

log('ALT', 'Subiendo throttle 72% -> 80%...')
for step in range(40):
    t_pct = step / 40.0
    throttle = 0.72 + t_pct * 0.08
    rc(throttle=throttle)
    time.sleep(0.1)

for i in range(80):
    rc(throttle=0.80)
    time.sleep(0.1)
    if i % 20 == 0:
        log('ALT', f't=0.80 alt={get_alt():.1f}m')

alt_3 = get_alt()
log('ALT', f'Altitud nivel 3: {alt_3:.1f}m', C.OK if 15 < alt_3 < 60 else C.WARN)

# Maniobras en altitud alta
log('JS', 'Yaw izq 20% (4s)...')
for i in range(40):
    rc(throttle=0.80, yaw=-0.20)
    time.sleep(0.1)

log('JS', 'Yaw der 20% (4s)...')
for i in range(40):
    rc(throttle=0.80, yaw=0.20)
    time.sleep(0.1)

log('JS', 'Pitch fwd 15% (3s)...')
for i in range(30):
    rc(throttle=0.80, pitch=-0.15)
    time.sleep(0.1)

log('JS', 'Pitch back 15% (3s)...')
for i in range(30):
    rc(throttle=0.80, pitch=0.15)
    time.sleep(0.1)

log('JS', 'Roll izq 15% (3s)...')
for i in range(30):
    rc(throttle=0.80, roll=-0.15)
    time.sleep(0.1)

log('JS', 'Roll der 15% (3s)...')
for i in range(30):
    rc(throttle=0.80, roll=0.15)
    time.sleep(0.1)

log('JS', 'Centrar (3s)...')
for i in range(30):
    rc(throttle=0.80)
    time.sleep(0.1)

for i in range(80):
    rc(throttle=0.65)
    time.sleep(0.1)
    if i % 20 == 0:
        log('ALT', f't=0.65 alt={get_alt():.1f}m')

alt_3 = get_alt()
log('ALT', f'Altitud nivel 3: {alt_3:.1f}m', C.OK if 15 < alt_3 < 50 else C.WARN)

# Maniobras en altitud alta
log('JS', 'Yaw izq 20% (4s)...')
for i in range(40):
    rc(throttle=0.65, yaw=-0.20)
    time.sleep(0.1)

log('JS', 'Yaw der 20% (4s)...')
for i in range(40):
    rc(throttle=0.65, yaw=0.20)
    time.sleep(0.1)

log('JS', 'Pitch fwd 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, pitch=-0.15)
    time.sleep(0.1)

log('JS', 'Pitch back 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, pitch=0.15)
    time.sleep(0.1)

log('JS', 'Roll izq 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, roll=-0.15)
    time.sleep(0.1)

log('JS', 'Roll der 15% (3s)...')
for i in range(30):
    rc(throttle=0.65, roll=0.15)
    time.sleep(0.1)

log('JS', 'Centrar (3s)...')
for i in range(30):
    rc(throttle=0.65)
    time.sleep(0.1)

alt_3b = get_alt()
log('ALT', f'Altitud post-maniobras nivel 3: {alt_3b:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 6: DESCENSO GRADUAL
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 6: DESCENSO GRADUAL')
print(f'{"─"*70}{C.END}')

log('ALT', 'Bajando throttle 80% -> 55% (10s)...')
for step in range(100):
    t_pct = step / 100.0
    throttle = 0.80 - t_pct * 0.25
    rc(throttle=throttle)
    time.sleep(0.1)
    if step % 25 == 0:
        log('ALT', f'throttle={throttle:.2f} alt={get_alt():.1f}m')

log('ALT', 'Manteniendo 55% (5s)...')
for i in range(50):
    rc(throttle=0.55)
    time.sleep(0.1)
    if i % 25 == 0:
        log('ALT', f't=0.55 alt={get_alt():.1f}m')

log('ALT', 'Bajando 55% -> 40% (5s)...')
for step in range(50):
    t_pct = step / 50.0
    throttle = 0.55 - t_pct * 0.15
    rc(throttle=throttle)
    time.sleep(0.1)

log('ALT', 'Manteniendo 40% (3s)...')
for i in range(30):
    rc(throttle=0.40)
    time.sleep(0.1)

alt_inter = get_alt()
log('ALT', f'Altitud intermedia: {alt_inter:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 7: ATERRIZAR
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 7: ATERRIZAR')
print(f'{"─"*70}{C.END}')

log('ALT', 'Bajando 40% -> 15% en 10s...')
for step in range(100):
    t_pct = step / 100.0
    throttle = 0.40 - t_pct * 0.25
    rc(throttle=throttle)
    time.sleep(0.1)
    if step % 25 == 0:
        log('ALT', f'throttle={throttle:.2f} alt={get_alt():.1f}m')

log('ALT', 'Throttle idle 15% - settle (4s)...')
for i in range(40):
    rc(throttle=0.15)
    time.sleep(0.1)

alt_final = get_alt()
log('ALT', f'Altitud final: {alt_final:.1f}m', C.OK if alt_final < 5 else C.WARN)

# ══════════════════════════════════════════════════════════════════════════════
# FASE 8: DISARM
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*70}')
print(f'  FASE 8: DISARM')
print(f'{"─"*70}{C.END}')

armed, mode = get_status()
log('FINAL', f'Pre-DISARM: armed={armed} mode={mode}')

disarm = api('POST', '/api/disarm', {"force": True}, timeout=60)
log('DISARM', f'{json.dumps(disarm)}')

time.sleep(3)
armed_post, mode_post = get_status()
log('FINAL', f'Post-DISARM: armed={armed_post} mode={mode_post}')

# ══════════════════════════════════════════════════════════════════════════════
# RESULTADO
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"="*70}')
print(f'  RESULTADO')
print(f'{"="*70}{C.END}')

results = []
results.append(('ARM', arm.get('success', False)))
results.append(('DESPEGUE', alt_1 > 1))
results.append(('ALTITUD 1 (~5m)', 2 < alt_1 < 15))
results.append(('MANIOBRAS BAJA', True))
results.append(('ALTITUD 2 (~15m)', 8 < alt_2 < 35))
results.append(('ALTITUD 3 (~30m)', 15 < alt_3 < 60))
results.append(('DESCENSO', alt_inter < alt_3b))
results.append(('ATERRIZAJE', alt_final < 10))
results.append(('DISARM', not armed_post))

for name, ok in results:
    if ok:
        print(f'  {C.OK}OK {name}{C.END}')
    else:
        print(f'  {C.FAIL}FAIL {name}{C.END}')

all_ok = all(ok for _, ok in results)
if all_ok:
    print(f'\n  {C.OK}{C.BOLD}Todos los checks pasaron{C.END}')
else:
    print(f'\n  {C.FAIL}{C.BOLD}Algunos checks fallaron{C.END}')

print(f'\n  Altitudes relativas (home=584m):')
print(f'    Nivel 1: +{alt_1:.1f}m (target: ~5m)')
print(f'    Nivel 2: +{alt_2:.1f}m (target: ~15m)')
print(f'    Nivel 3: +{alt_3:.1f}m (target: ~30m)')
print(f'    Inter:   +{alt_inter:.1f}m')
print(f'    Final:   +{alt_final:.1f}m (target: <5m)')
print()

# ── Cleanup ───────────────────────────────────────────────────────────────────
api('POST', '/api/rc/reset')
time.sleep(1)
backend_proc.terminate()
backend_proc.wait(timeout=5)
try:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()
log('CLEANUP', 'Todo detenido', C.OK)
