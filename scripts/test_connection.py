import sys
import time
import argparse
from pymavlink import mavutil

def wait_heartbeat(connection):
    """
    Waits for a heartbeat from the drone and prints information.
    """
    print(f"Esperando heartbeat en {connection.address}...")
    try:
        # Wait for the first heartbeat
        # This sets the system and component ID of remote system for the link
        connection.wait_heartbeat(timeout=10)
    except Exception as e:
        print(f"Error esperando heartbeat: {e}")
        return False

    if connection.target_system == 0:
        print("No se recibió heartbeat (Time out). Verifica la conexión.")
        return False

    print(f"¡Conectado! Heartbeat recibido de Sistema {connection.target_system}, Componente {connection.target_component}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Prueba de conexión con Dron Real via MAVLink")
    parser.add_argument("--connect", required=True, help="Connection string (ej. COM3, /dev/ttyUSB0, udp:127.0.0.1:14550)")
    parser.add_argument("--baud", type=int, default=57600, help="Baud rate (default: 57600). Usa 115200 para USB directo.")
    
    args = parser.parse_args()

    print(f"Intentando conectar a: {args.connect} con baudios {args.baud}")
    
    try:
        # Create the connection
        # source_system=255 means we act as a GCS (Ground Control Station)
        connection = mavutil.mavlink_connection(args.connect, baud=args.baud, source_system=255)
    except Exception as e:
        print(f"Error creando conexión: {e}")
        return

    if wait_heartbeat(connection):
        print("\n--- Escuchando Mensajes (Ctrl+C para salir) ---")
        try:
            while True:
                msg = connection.recv_match(blocking=True, timeout=1.0)
                if not msg:
                    continue
                
                # Filter interesting messages to avoid spam
                if msg.get_type() == 'HEARTBEAT':
                    mode = mavutil.mode_string_v10(msg)
                    print(f"HEARTBEAT: Mode={mode}, BaseMode={msg.base_mode}, State={msg.system_status}")
                elif msg.get_type() == 'ATTITUDE':
                    print(f"ATTITUDE: Roll={msg.roll:.2f}, Pitch={msg.pitch:.2f}, Yaw={msg.yaw:.2f}")
                elif msg.get_type() == 'SYS_STATUS':
                    print(f"Bateria: {msg.voltage_battery/1000.0:.1f}V, Carga: {msg.load/10.0}%")
                    
        except KeyboardInterrupt:
            print("\nDeteniendo prueba.")
        finally:
            connection.close()

if _name_ == "_main_":
    main()