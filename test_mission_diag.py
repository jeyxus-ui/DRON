"""
Diagnóstico de mission upload en SITL.
Conecta a puerto 5762 y 5763, manda MISSION_COUNT y loguea TODOS los mensajes.
Ejecutar con: py test_mission_diag.py
"""
import time
import threading
from pymavlink import mavutil

PORTS = [5762, 5763]
TIMEOUT = 10  # segundos de escucha

def test_port(port):
    print(f"\n{'='*50}")
    print(f"TEST PUERTO {port}")
    print(f"{'='*50}")
    try:
        m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{port}", source_system=254)
        m.wait_heartbeat(timeout=5)
        print(f"[{port}] ✅ Heartbeat — target_system={m.target_system} component={m.target_component}")
    except Exception as e:
        print(f"[{port}] ❌ Sin heartbeat: {e}")
        return

    # Escuchar mensajes en background
    received = []
    stop = threading.Event()

    def listener():
        while not stop.is_set():
            msg = m.recv_match(blocking=True, timeout=0.1)
            if msg:
                mtype = msg.get_type()
                if mtype not in ("RC_CHANNELS", "VFR_HUD", "HEARTBEAT", "ATTITUDE",
                                  "GPS_RAW_INT", "BATTERY_STATUS", "LOCAL_POSITION_NED",
                                  "SYS_STATUS", "GLOBAL_POSITION_INT", "RAW_IMU"):
                    ts = round(time.time() % 1000, 3)
                    print(f"[{port}] [{ts}] MSG: {mtype}")
                    received.append(mtype)

    t = threading.Thread(target=listener, daemon=True)
    t.start()

    time.sleep(1)  # esperar que se estabilice

    print(f"[{port}] Enviando MISSION_COUNT(1)...")
    m.mav.mission_count_send(m.target_system, m.target_component, 1)
    ts_send = time.time()

    # Esperar respuesta
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        if "MISSION_REQUEST" in received or "MISSION_REQUEST_INT" in received:
            print(f"[{port}] ✅ MISSION_REQUEST recibido después de {round(time.time()-ts_send,2)}s")
            # Responder con waypoint de prueba (Buenos Aires)
            if "MISSION_REQUEST_INT" in received:
                m.mav.mission_item_int_send(
                    m.target_system, m.target_component, 0,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0, 1, 0, 0, 0, 0,
                    int(-34.6037 * 1e7), int(-58.3816 * 1e7), 10.0
                )
            else:
                m.mav.mission_item_send(
                    m.target_system, m.target_component, 0,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0, 1, 0, 0, 0, 0,
                    -34.6037, -58.3816, 10.0
                )
            print(f"[{port}] MISSION_ITEM enviado — esperando ACK...")
        if "MISSION_ACK" in received:
            print(f"[{port}] ✅ MISSION_ACK recibido — upload OK")
            break
        time.sleep(0.05)
    else:
        print(f"[{port}] ❌ TIMEOUT — mensajes recibidos: {set(received)}")

    stop.set()
    m.close()

if __name__ == "__main__":
    for port in PORTS:
        test_port(port)
    print("\nDiagnóstico completado.")
