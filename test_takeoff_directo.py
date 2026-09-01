"""
Test directo de takeoff via pymavlink en puerto 5762 (sin backend).
Ejecutar MIENTRAS el SITL esta corriendo.
"""
import time
from pymavlink import mavutil

print("Conectando a SITL en puerto 5762...")
mav = mavutil.mavlink_connection('tcp:127.0.0.1:5762', source_system=1)
mav.wait_heartbeat(timeout=10)
print(f"HB: sys={mav.target_system} comp={mav.target_component}")

def get_mode(mav):
    hb = mav.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
    if hb:
        return hb.custom_mode
    return None

def arm():
    mav.mav.command_long_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 0, 0, 0, 0, 0, 0
    )
    ack = mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=10)
    print(f"ARM ACK: {ack}")
    return ack and ack.result == 0

def set_guided():
    mav.mav.command_long_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        0, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        4, 0, 0, 0, 0, 0  # 4 = GUIDED en ArduCopter
    )
    ack = mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
    print(f"SET_MODE GUIDED ACK: {ack}")

def takeoff(alt=3):
    mav.mav.command_long_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, 0, alt
    )
    ack = mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=10)
    print(f"TAKEOFF ACK: {ack}")
    return ack and ack.result == 0

print("\n--- Paso 1: Modo GUIDED ---")
set_guided()
time.sleep(1)

print("\n--- Paso 2: ARM ---")
ok = arm()
if not ok:
    print("ARM fallo, intentando con force...")
    mav.mav.command_long_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 21196, 0, 0, 0, 0, 0
    )
    ack = mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
    print(f"ARM force ACK: {ack}")
time.sleep(2)

print("\n--- Paso 3: TAKEOFF a 3m ---")
ok = takeoff(3)
if not ok:
    print("TAKEOFF rechazo — SITL no acepta el comando")
else:
    print("TAKEOFF aceptado — monitoreando altitud 10s...")
    for i in range(20):
        time.sleep(0.5)
        vfr = mav.recv_match(type='VFR_HUD', blocking=False)
        gps = mav.recv_match(type='GLOBAL_POSITION_INT', blocking=False)
        if vfr:
            alt = gps.relative_alt/1000 if gps else '?'
            print(f"  t={i*0.5:.1f}s THR={vfr.throttle}% alt={alt}m climb={vfr.climb:.2f}m/s")

print("\nListo.")
