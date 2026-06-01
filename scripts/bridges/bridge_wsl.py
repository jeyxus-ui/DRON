"""
Bridge inside WSL: SITL (localhost TCP) -> TCP server (0.0.0.0) for Windows/QGC.
Run this inside WSL.
"""
from pymavlink import mavutil
import socket, threading, time, sys

TCP_SITL = 5760
TCP_OUT = 14551  # accessible from Windows via WSL2 IP

sitl = mavutil.mavlink_connection(f'tcp:127.0.0.1:{TCP_SITL}', source_system=255)
print(f'Connecting to SITL...', flush=True)
sitl.wait_heartbeat(timeout=15)
print(f'Connected! sys={sitl.target_system}', flush=True)

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', TCP_OUT))
srv.listen(1)
srv.settimeout(1)
print(f'Listening on 0.0.0.0:{TCP_OUT}', flush=True)

clients = []

def to_clients():
    while True:
        msg = sitl.recv_match(blocking=True, timeout=0.5)
        if msg and clients:
            buf = msg.get_msgbuf()
            if buf:
                for c in clients[:]:
                    try:
                        c.sendall(buf)
                    except:
                        clients.remove(c)

def from_clients():
    while True:
        try:
            conn, addr = srv.accept()
            print(f'Client connected: {addr}', flush=True)
            clients.append(conn)
        except socket.timeout:
            continue
        buf = b''
        while True:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while len(buf) >= 1:
                    msg = sitl.mav.parse_char(buf[0:1])
                    buf = buf[1:]
                    if msg:
                        sitl.mav.send(msg)
            except:
                break
        if conn in clients:
            clients.remove(conn)
        print(f'Client disconnected: {addr}', flush=True)

threading.Thread(target=to_clients, daemon=True).start()
threading.Thread(target=from_clients, daemon=True).start()

print('Bridge running! Connect QGC to WSL2 IP (172.28.252.91):14551', flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print('Stopping...')
