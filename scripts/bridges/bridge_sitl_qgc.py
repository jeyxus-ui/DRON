"""
Bridge: SITL (TCP via WSL) -> UDP local (for QGC auto-discover).
"""
from pymavlink import mavutil
import socket, time, threading, struct

WSL_IP = '172.28.252.91'
SITL_TCP_PORT = 5760
LOCAL_UDP_PORT = 14550

# Connect to SITL via TCP
master = mavutil.mavlink_connection(f'tcp:{WSL_IP}:{SITL_TCP_PORT}', source_system=255)
master.wait_heartbeat(timeout=15)
print(f'Connected to SITL! target_sys={master.target_system}')

# Create UDP socket for QGC
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
udp_sock.bind(('0.0.0.0', 0))  # any free port for sending

# Forward thread: SITL -> UDP broadcast
def forward_to_udp():
    while True:
        msg = master.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        buf = msg.get_msgbuf()
        if buf:
            udp_sock.sendto(buf, ('255.255.255.255', LOCAL_UDP_PORT))
            udp_sock.sendto(buf, ('127.0.0.1', LOCAL_UDP_PORT))

t = threading.Thread(target=forward_to_udp, daemon=True)
t.start()

# Forward UDP -> SITL (for commands from QGC)
def forward_from_udp():
    local_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    local_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    local_udp.bind(('0.0.0.0', LOCAL_UDP_PORT))
    while True:
        data, addr = local_udp.recvfrom(4096)
        if data:
            master.mav.send(mavutil.mavlink.MAVLink_message(data))

t2 = threading.Thread(target=forward_from_udp, daemon=True)
t2.start()

print(f'Forwarding SITL (TCP {WSL_IP}:{SITL_TCP_PORT}) <-> UDP {LOCAL_UDP_PORT}')
print('QGC should auto-discover. Press Ctrl+C to stop.')

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print('\nStopping...')
    master.close()
