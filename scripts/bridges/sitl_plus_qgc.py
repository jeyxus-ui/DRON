"""
One script: starts SITL (subprocess), connects via TCP, bridges to local port for QGC.
Run this from Windows. QGC connects to 127.0.0.1:14551.
"""
import subprocess, time, os, signal, socket, threading, sys

WSL_IP = '172.28.252.91'
BRIDGE_PORT = 14551

print('Starting SITL...', flush=True)
proc = subprocess.Popen(
    ['wsl', '-d', 'Ubuntu', '-u', 'usuario', '--',
     '/home/usuario/ardupilot/build/sitl/bin/arducopter',
     '--model', 'quad', '--speedup', '1',
     '--home', '-35.363262,149.165237,584,270',
     '-I0', '--synthetic-clock'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(10)

from pymavlink import mavutil

print('Connecting to SITL...', flush=True)
sitl = mavutil.mavlink_connection(f'tcp:{WSL_IP}:{5760}', source_system=255)
sitl.wait_heartbeat(timeout=10)
print(f'Connected! sys={sitl.target_system}', flush=True)

# TCP server for QGC
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', BRIDGE_PORT))
srv.listen(1)
srv.settimeout(1)
print(f'Bridge listening on 0.0.0.0:{BRIDGE_PORT}', flush=True)

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
            print(f'QGC connected: {addr}', flush=True)
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
                while buf:
                    msg = sitl.mav.parse_char(buf[0:1])
                    buf = buf[1:]
                    if msg:
                        sitl.mav.send(msg)
            except:
                break
        if conn in clients:
            clients.remove(conn)
        print(f'QGC disconnected', flush=True)

threading.Thread(target=to_clients, daemon=True).start()
threading.Thread(target=from_clients, daemon=True).start()

print(f'Ready! Open QGC -> Comm Links -> Add TCP -> 127.0.0.1:{BRIDGE_PORT}', flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print('\nShutting down...')
finally:
    proc.terminate()
    proc.wait(timeout=5)
