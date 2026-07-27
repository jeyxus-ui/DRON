#!/usr/bin/env python3
import pymavlink.mavutil as m
import time
import sys

print("Conectando a SITL en tcp:127.0.0.1:5760...")
try:
    mav = m.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
    print("Esperando heartbeat...")
    mav.wait_heartbeat(timeout=10)
    print(f"OK: sys={mav.target_system} comp={mav.target_component}")
    
    # Test ARM
    print("Enviando ARM...")
    mav.arducopter_arm()
    r = mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
    if r:
        print(f"ARM ACK: result={r.result} command={r.command}")
    else:
        print("ARM: no ACK recibido")
    
    time.sleep(2)
    print("Enviando DISARM...")
    mav.arducopter_disarm()
    r2 = mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
    if r2:
        print(f"DISARM ACK: result={r2.result} command={r2.command}")
    else:
        print("DISARM: no ACK recibido")
    
    mav.close()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
