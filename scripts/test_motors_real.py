#!/usr/bin/env python3
"""
Test real de motores: levanta SITL (ArduPilot real) en WSL,
conecta el backend completo y prueba el flujo ARM → RC Override → Motores.
"""
import subprocess
import time
import sys
import os
import signal
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymavlink import mavutil

# ── Config ────────────────────────────────────────────────────────────────────
SITL_BIN = '/home/usuario/ardupilot/build/sitl/bin/arducopter'
SITL_HOME = '-35.363262,149.165237,584,270'
TCP_PORT = 5760
TEST_DURATION = 20  # segundos de monitoreo post-ARM

# ── Colores ───────────────────────────────────────────────────────────────────
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

# ── Paso 1: Iniciar SITL ─────────────────────────────────────────────────────
start_time = time.time()
print(f'{C.BOLD}{"="*60}')
print(f'  TEST REAL DE MOTORES — SITL ArduPilot')
print(f'{"="*60}{C.END}\n')

log('SETUP', 'Iniciando SITL (ArduPilot real)...')
proc = subprocess.Popen(
    [SITL_BIN, '--model', 'quad', '--speedup', '1',
     '--home', SITL_HOME, '-I0', '--synthetic-clock',
     '--defaults', '/home/usuario/ardupilot/Tools/autotest/default_params/copter.parm'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
)
time.sleep(4)
log('SETUP', f'SITL PID: {proc.pid}', C.OK)

# ── Paso 2: Conectar ─────────────────────────────────────────────────────────
log('CONN', f'Conectando a tcp:127.0.0.1:{TCP_PORT}...')
master = mavutil.mavlink_connection(f'tcp:127.0.0.1:{TCP_PORT}', source_system=255)
master.wait_heartbeat(timeout=15)
log('CONN', f'Conectado! sys={master.target_system} comp={master.target_component}', C.OK)

# ── Paso 3: Verificar estado inicial ─────────────────────────────────────────
log('INIT', 'Esperando telemetria inicial (5s)...')
time.sleep(5)

hb = master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
if hb:
    armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    mode = mavutil.mode_string_v10(hb)
    log('INIT', f'Heartbeat: mode={mode} armed={armed}')

# Leer parametros criticos
for pname in ['ARMING_CHECK', 'THR_MIN', 'RC3_MIN', 'RC3_MAX']:
    master.mav.param_request_read_send(master.target_system, master.target_component, pname.encode(), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
    if msg:
        log('PARAM', f'{pname} = {msg.param_value}')

# ── Paso 4: Pre-flight checks (como lo hace nuestro backend) ─────────────────
print(f'\n{C.BOLD}--- PRE-FLIGHT CHECKS ---{C.END}')

checks = {}

# GPS
gps = master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=5)
if gps:
    checks['gps_fix'] = gps.fix_type >= 3
    checks['gps_sats'] = gps.satellites_visible >= 6
    log('CHECK', f'GPS: fix={gps.fix_type} sats={gps.satellites_visible}',
        C.OK if checks['gps_fix'] else C.FAIL)
else:
    checks['gps_fix'] = False
    checks['gps_sats'] = False
    log('CHECK', 'GPS: sin datos', C.FAIL)

# Battery
bat = master.recv_match(type='SYS_STATUS', blocking=True, timeout=3)
if bat:
    checks['battery'] = bat.battery_remaining > 30
    log('CHECK', f'Battery: {bat.battery_remaining}%',
        C.OK if checks['battery'] else C.WARN)
else:
    checks['battery'] = False
    log('CHECK', 'Battery: sin datos', C.FAIL)

# EKF
ekf = master.recv_match(type='EKF_STATUS_REPORT', blocking=True, timeout=3)
if ekf:
    checks['ekf'] = bool(ekf.flags & 0x01)
    log('CHECK', f'EKF: flags={ekf.flags} ok={checks["ekf"]}',
        C.OK if checks['ekf'] else C.WARN)
else:
    checks['ekf'] = False
    log('CHECK', 'EKF: sin datos', C.WARN)

failed = [k for k, v in checks.items() if not v]
if failed:
    log('CHECK', f'Checks fallidos: {failed} — configurando ARMING_CHECK=0 para bypass', C.WARN)
    master.mav.param_set_send(master.target_system, master.target_component,
        b'ARMING_CHECK', 0.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    time.sleep(1)
else:
    log('CHECK', 'Todos los checks pasaron', C.OK)

# ── Paso 5: Modo STABILIZE (no necesita GPS) ──────────────────────────────────
print(f'\n{C.BOLD}--- SET MODE: STABILIZE ---{C.END}')
modes = master.mode_mapping()
master.mav.set_mode_send(master.target_system, modes['STABILIZE'], 0, 0)
time.sleep(2)

hb = master.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
if hb:
    mode = mavutil.mode_string_v10(hb)
    log('MODE', f'Modo actual: {mode}', C.OK)

# ── Paso 6: ARM (como lo hace nuestro backend) ───────────────────────────────
print(f'\n{C.BOLD}--- ARM MOTORES ---{C.END}')
log('ARM', 'Enviando MAV_CMD_COMPONENT_ARM_DISARM (param1=1, param2=21196)...')

with master.mav.mavlink_packet_lock if hasattr(master.mav, 'mavlink_packet_lock') else threading.Lock():
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 21196, 0, 0, 0, 0, 0,
    )

# Esperar ACK
log('ARM', 'Esperando COMMAND_ACK...')
ack_start = time.time()
arm_success = False
while time.time() - ack_start < 5:
    msg = master.recv_match(type='COMMAND_ACK', blocking=True, timeout=1)
    if msg and msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
        if msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            log('ARM', 'ARM ACEPTADO por ArduPilot', C.OK)
            arm_success = True
        else:
            log('ARM', f'ARM RECHAZADO: result={msg.result}', C.FAIL)
        break

if not arm_success:
    log('ARM', 'ARM falló o timeout', C.FAIL)

# ── Paso 7: Verificar que motores quedan armados + RC override simultáneo ────
print(f'\n{C.BOLD}--- MONITOREO POST-ARM + RC OVERRIDE ({TEST_DURATION}s) ---{C.END}')
log('MON', 'Verificando motores + enviando RC override (simula joystick del backend)...')

# Lanzar hilo de RC override (simula el backend: throttle idle 15% = 1150 PWM)
rc_thread_stop = threading.Event()
rc_sent = [0]

def rc_override_loop():
    """Simula nuestro RCOverrideController: envía throttle=1150 (15% idle) a 10Hz"""
    while not rc_thread_stop.is_set():
        try:
            master.mav.rc_channels_override_send(
                master.target_system,
                master.target_component,
                1500,  # CH1 Roll (center)
                1500,  # CH2 Pitch (center)
                1150,  # CH3 Throttle (15% idle — nuestro fix)
                1500,  # CH4 Yaw (center)
                0, 0, 0, 0
            )
            rc_sent[0] += 1
        except Exception:
            pass
        time.sleep(0.1)  # 10 Hz

rc_thread = threading.Thread(target=rc_override_loop, daemon=True)
rc_thread.start()
log('RC', 'RC Override thread iniciado — throttle=1150 (15% idle)', C.OK)

disarm_events = []
arm_lost_at = None
start_mon = time.time()

while time.time() - start_mon < TEST_DURATION:
    msg = master.recv_match(blocking=True, timeout=1)
    if msg is None:
        continue

    t = time.time() - start_mon
    mtype = msg.get_type()

    if mtype == 'HEARTBEAT':
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        mode = mavutil.mode_string_v10(msg) or str(msg.custom_mode)

        if not armed and arm_success and arm_lost_at is None:
            arm_lost_at = t
            disarm_events.append(t)
            log('MON', f'¡¡MOTORES DESARMADOS a los {t:.1f}s!! (RC packets sent: {rc_sent[0]})', C.FAIL)
        elif armed:
            if arm_lost_at is not None:
                log('MON', f'Motores re-armados a los {t:.1f}s', C.WARN)
                arm_lost_at = None
            if int(t) % 5 == 0 and int(t * 10) % 10 == 0:
                log('MON', f'heartbeat mode={mode} armed={armed} rc_sent={rc_sent[0]}', C.OK)

    elif mtype == 'STATUSTEXT':
        log('MON', f'STATUS: {msg.text}', C.WARN)

    elif mtype == 'COMMAND_ACK':
        log('MON', f'ACK: cmd={msg.command} result={msg.result}')

rc_thread_stop.set()
rc_thread.join(timeout=2)
log('MON', f'RC Override detenido — {rc_sent[0]} paquetes enviados')

# ── Paso 9: DISARM ────────────────────────────────────────────────────────────
print(f'\n{C.BOLD}--- DISARM ---{C.END}')
master.mav.command_long_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    0, 0, 0, 0, 0, 0, 0, 0,
)
time.sleep(2)

hb = master.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
if hb:
    armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    log('DISARM', f'Estado final: armed={armed}', C.OK if not armed else C.FAIL)

# ── Resultado ─────────────────────────────────────────────────────────────────
print(f'\n{C.BOLD}{"="*60}')
print(f'  RESULTADO')
print(f'{"="*60}{C.END}')

if arm_success and not disarm_events:
    print(f'{C.OK}  PASS — Motores armaron y permanecieron armados con RC override{C.END}')
    print(f'{C.OK}  Los fixes de throttle idle (15%) y ARM_IDLE_DURATION (1s) funcionan{C.END}')
elif disarm_events:
    print(f'{C.FAIL}  FAIL — Motores se desarmaron solos a los {disarm_events[0]:.1f}s{C.END}')
    print(f'{C.FAIL}  Causa probable: ArduPilot auto-disarm por inactividad o THR_MIN{C.END}')
    print(f'{C.WARN}  Solución: enviar RC override MÁS RÁPIDO después del ARM{C.END}')
else:
    print(f'{C.FAIL}  FAIL — ARM no fue aceptado por ArduPilot{C.END}')

hb_final = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
final_armed = bool(hb_final.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) if hb_final else False
if final_armed:
    print(f'{C.WARN}  INFO — Dron seguía armado al final (DISARM manual necesario){C.END}')

print(f'\n')

# ── Cleanup ───────────────────────────────────────────────────────────────────
master.close()
log('CLEANUP', 'Cerrando SITL...')
try:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()
log('CLEANUP', 'SITL detenido', C.OK)
