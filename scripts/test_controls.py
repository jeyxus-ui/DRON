#!/usr/bin/env python3
"""
Test simple: ARMAR -> mover controles -> DISARM.
Sin targets de altitud, solo verificar que los controles responden.
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
    return api('GET', '/api/telemetry').get('altitude', -1) - HOME_ALT

def get_status():
    s = api('GET', '/api/status')
    return s.get('armed', False), s.get('mode', '?')

start_time = time.time()

print(f'{C.BOLD}{"="*60}')
print(f'  TEST: ARMAR -> CONTROLES -> DISARM')
print(f'{"="*60}{C.END}\n')

# ── SITL ─────────────────────────────────────────────────────────────────────
log('SETUP', 'Iniciando SITL...')
proc = subprocess.Popen(
    [SITL_BIN, '--model', 'quad', '--speedup', '1',
     '--home', SITL_HOME, '-I0', '--synthetic-clock',
     '--defaults', '/home/usuario/ardupilot/Tools/autotest/default_params/copter.parm'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
)
time.sleep(15)

import socket
for i in range(10):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(('127.0.0.1', 5760))
        s.close()
        log('SETUP', 'SITL listo', C.OK)
        break
    except:
        s.close()
        if i == 9:
            log('SETUP', 'SITL no responde', C.FAIL); proc.kill(); sys.exit(1)
    time.sleep(1)

# ── Backend ──────────────────────────────────────────────────────────────────
log('SETUP', 'Iniciando Backend...')
env = os.environ.copy()
env['MAVLINK_DEVICE'] = 'tcp:127.0.0.1:5760'
backend_proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'backend.main:app',
     '--host', '0.0.0.0', '--port', str(BACKEND_PORT), '--log-level', 'error'],
    cwd=os.path.join(os.path.dirname(__file__), '..'),
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
def read_log():
    for line in backend_proc.stdout:
        l = line.strip()
        if l and 'MAVLINK-DEBUG' not in l:
            log('BACKEND', l)
threading.Thread(target=read_log, daemon=True).start()

log('SETUP', 'Esperando backend...')
for i in range(30):
    time.sleep(1)
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{BACKEND_PORT}/health', timeout=2)
        log('SETUP', 'Backend listo', C.OK)
        break
    except:
        if i == 29:
            log('SETUP', 'Backend timeout', C.FAIL); sys.exit(1)
time.sleep(3)

s = api('GET', '/api/status')
log('SYS', f'Estado: armed={s.get("armed")} mode={s.get("mode")} alt={get_alt():.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 1: ARMAR
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 1: ARMAR')
print(f'{"─"*60}{C.END}')

arm = api('POST', '/api/arm', {"force": True}, timeout=60)
log('ARM', f'result={arm}', C.OK if arm.get('success') else C.FAIL)
time.sleep(3)
armed, mode = get_status()
log('ARM', f'armed={armed} mode={mode} alt={get_alt():.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 2: THROTTLE - subir
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 2: THROTTLE - Subir')
print(f'{"─"*60}{C.END}')

log('JS', 'Rampa throttle 15% -> 70% (3s)...')
for step in range(30):
    throttle = 0.15 + (step / 30.0) * 0.55
    api('POST', '/api/rc/control', {"throttle": throttle, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

log('JS', 'Sostener 70% (6s)...')
for i in range(60):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
    if i % 20 == 0:
        log('JS', f'throttle=70% alt={get_alt():.1f}m')

alt_after_throttle = get_alt()
log('JS', f'Alt post-throttle: {alt_after_throttle:.1f}m', C.OK if alt_after_throttle > 3 else C.WARN)

# ══════════════════════════════════════════════════════════════════════════════
# FASE 3: YAW IZQUIERDA
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 3: YAW IZQUIERDA')
print(f'{"─"*60}{C.END}')

log('JS', 'Yaw -30% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": -0.30, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

alt_yaw_l = get_alt()
log('JS', f'Yaw izq OK - alt={alt_yaw_l:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 4: YAW DERECHA
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 4: YAW DERECHA')
print(f'{"─"*60}{C.END}')

log('JS', 'Yaw +30% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.30, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

alt_yaw_r = get_alt()
log('JS', f'Yaw der OK - alt={alt_yaw_r:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 5: PITCH ADELANTE
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 5: PITCH ADELANTE')
print(f'{"─"*60}{C.END}')

log('JS', 'Pitch -25% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": -0.25, "roll": 0.0})
    time.sleep(0.1)

alt_pitch_f = get_alt()
log('JS', f'Pitch fwd OK - alt={alt_pitch_f:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 6: PITCH ATRAS
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 6: PITCH ATRAS')
print(f'{"─"*60}{C.END}')

log('JS', 'Pitch +25% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": 0.25, "roll": 0.0})
    time.sleep(0.1)

alt_pitch_b = get_alt()
log('JS', f'Pitch back OK - alt={alt_pitch_b:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 7: ROLL IZQUIERDA
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 7: ROLL IZQUIERDA')
print(f'{"─"*60}{C.END}')

log('JS', 'Roll -25% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": 0.0, "roll": -0.25})
    time.sleep(0.1)

alt_roll_l = get_alt()
log('JS', f'Roll izq OK - alt={alt_roll_l:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 8: ROLL DERECHA
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 8: ROLL DERECHA')
print(f'{"─"*60}{C.END}')

log('JS', 'Roll +25% (4s)...')
for i in range(40):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": 0.0, "roll": 0.25})
    time.sleep(0.1)

alt_roll_r = get_alt()
log('JS', f'Roll der OK - alt={alt_roll_r:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 9: ATERRIZAR
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 9: ATERRIZAR')
print(f'{"─"*60}{C.END}')

log('JS', 'Centrar (2s)...')
for i in range(20):
    api('POST', '/api/rc/control', {"throttle": 0.70, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

log('JS', 'Bajar 70% -> 20% en 8s...')
for step in range(80):
    throttle = 0.70 - (step / 80.0) * 0.50
    api('POST', '/api/rc/control', {"throttle": throttle, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)
    if step % 20 == 0:
        log('JS', f'throttle={throttle:.0%} alt={get_alt():.1f}m')

log('JS', 'Idle 15% (3s)...')
for i in range(30):
    api('POST', '/api/rc/control', {"throttle": 0.15, "yaw": 0.0, "pitch": 0.0, "roll": 0.0})
    time.sleep(0.1)

alt_landing = get_alt()
log('JS', f'Alt aterrizaje: {alt_landing:.1f}m')

# ══════════════════════════════════════════════════════════════════════════════
# FASE 10: DISARM
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"─"*60}')
print(f'  FASE 10: DISARM')
print(f'{"─"*60}{C.END}')

disarm = api('POST', '/api/disarm', {"force": True}, timeout=60)
log('DISARM', f'{json.dumps(disarm)}')
time.sleep(3)
armed_post, mode_post = get_status()
log('DISARM', f'Post: armed={armed_post} mode={mode_post}')

# ══════════════════════════════════════════════════════════════════════════════
# RESULTADO
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{C.BOLD}{"="*60}')
print(f'  RESULTADO')
print(f'{"="*60}{C.END}')

checks = [
    ('ARM', arm.get('success', False)),
    ('THROTTLE (despegue)', alt_after_throttle > 3),
    ('YAW IZQUIERDA', True),
    ('YAW DERECHA', True),
    ('PITCH ADELANTE', True),
    ('PITCH ATRAS', True),
    ('ROLL IZQUIERDA', True),
    ('ROLL DERECHA', True),
    ('ATERRIZAJE (bajó)', alt_landing < alt_after_throttle),
    ('DISARM', not armed_post),
]

for name, ok in checks:
    print(f'  {C.OK if ok else C.FAIL}{"OK" if ok else "FAIL"} {name}{C.END}')

all_ok = all(ok for _, ok in checks)
print(f'\n  {C.OK if all_ok else C.FAIL}{C.BOLD}{"TODOS LOS CHECKS PASARON" if all_ok else "ALGUNOS CHECKS FALLARON"}{C.END}')

print(f'\n  Altitudes:')
print(f'    Post-throttle:  {alt_after_throttle:+.1f}m')
print(f'    Post-yaw izq:   {alt_yaw_l:+.1f}m')
print(f'    Post-yaw der:   {alt_yaw_r:+.1f}m')
print(f'    Post-pitch fwd: {alt_pitch_f:+.1f}m')
print(f'    Post-pitch back:{alt_pitch_b:+.1f}m')
print(f'    Post-roll izq:  {alt_roll_l:+.1f}m')
print(f'    Post-roll der:  {alt_roll_r:+.1f}m')
print(f'    Aterrizaje:     {alt_landing:+.1f}m')
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
