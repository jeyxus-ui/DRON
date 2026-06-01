"""
Bridge SITL (TCP WSL) <-> TCP localhost for QGC.
Usage: python bridge_qgc.py
Then in QGC: Add TCP link -> 127.0.0.1:14551
"""
from pymavlink import mavutil
import socket, threading, time

WSL_IP = '172.28.252.91'
TCP_SITL = 5760
TCP_LOCAL = 14551

sitl = mavutil.mavlink_connection(f'tcp:{WSL_IP}:{TCP_SITL}', source_system=255)
sitl.wait_heartbeat(timeout=15)
print(f'Connected to SITL! sys={sitl.target_system}')

qgc_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
qgc_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
qgc_server.bind(('0.0.0.0', TCP_LOCAL))
qgc_server.listen(1)
qgc_server.settimeout(1)

qgc_conn = None

def to_qgc():
    global qgc_conn
    while True:
        if not qgc_conn:
            time.sleep(0.5)
            continue
        msg = sitl.recv_match(blocking=True, timeout=0.5)
        if msg:
            buf = msg.get_msgbuf()
            if buf:
                try:
                    qgc_conn.sendall(buf)
                except:
                    qgc_conn = None

def from_qgc():
    global qgc_conn
    while True:
        try:
            conn, addr = qgc_server.accept()
            print(f'QGC connected: {addr}')
            qgc_conn = conn
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                for b in data:
                    msg = sitl.mav.parse_char(bytes([b]))
                if msg:
                    sitl.mav.send(msg)
        except socket.timeout:
            pass
        except Exception as e:
            print(f'Connection error: {e}')
            qgc_conn = None

threading.Thread(target=to_qgc, daemon=True).start()
threading.Thread(target=from_qgc, daemon=True).start()

print(f'Bridge ready! SITL <-> TCP 0.0.0.0:{TCP_LOCAL}')
print('Open QGC -> Application Settings -> Comm Links -> Add')
print(f'Type: TCP, Address: 127.0.0.1, Port: {TCP_LOCAL}')
print('Press Ctrl+C to stop')
while True:
    time.sleep(1)
