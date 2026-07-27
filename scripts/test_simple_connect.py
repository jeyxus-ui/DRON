"""Test: blocking recv para ver si algo llega"""
from pymavlink import mavutil
import time

print("Conectando...")
master = mavutil.mavlink_connection('tcp:172.28.252.91:5760', source_system=255)
master.wait_heartbeat(timeout=10)
print(f"Heartbeat OK! sys={master.target_system}")

master.mav.request_data_stream_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1
)

print("Esperando 1er mensaje (blocking=True, timeout=5)...")
msg = master.recv_match(blocking=True, timeout=5)
if msg:
    print(f"RECIBIDO: {msg.get_type()}")
else:
    print("NADA con blocking=True")

print("\nIntentando recv raw 5 segundos...")
start = time.time()
while time.time() - start < 5:
    msg = master.recv_match(blocking=False)
    if msg:
        print(f"  -> {msg.get_type()}")
    time.sleep(0.05)

print("\nIntentando recv_match con type específico...")
for mtype in ["HEARTBEAT", "VFR_HUD", "SYS_STATUS", "GPS_RAW_INT"]:
    msg = master.recv_match(type=mtype, blocking=True, timeout=3)
    if msg:
        print(f"  {mtype}: SI")
    else:
        print(f"  {mtype}: NO")

master.close()
print("Listo")
