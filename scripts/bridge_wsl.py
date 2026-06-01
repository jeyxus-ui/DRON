"""Bridge TCP MAVLink (WSL arducopter) → UDP (Windows QGC/backend).
Connects to arducopter TCP 5760, forwards to UDP 14550/14551 on Windows.
Also forwards UDP commands back to TCP.
Runs in WSL environment."""
import socket, select, sys, time

TCP_HOST = "127.0.0.1"
TCP_PORT = 5760
WINDOWS_HOST = "172.28.240.1"
QGC_PORT = 14550
BACKEND_PORT = 14551

def main():
    while True:
        try:
            run_bridge()
        except Exception as e:
            print(f"Bridge error: {e}, reconnecting in 3s...", flush=True)
            time.sleep(3)

def run_bridge():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(60)
    print(f"Connecting to arducopter at {TCP_HOST}:{TCP_PORT}...", flush=True)
    sock.connect((TCP_HOST, TCP_PORT))
    sock.setblocking(False)
    print("Connected to arducopter!", flush=True)

    # UDP socket for forwarding to Windows
    udp_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # UDP socket for receiving commands (bind on WSL side)
    udp_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_in.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_in.bind(("0.0.0.0", 14550))
    udp_in.setblocking(False)

    buf = b""
    while True:
        r, _, e = select.select([sock, udp_in], [], [sock, udp_in], 1)
        if e:
            print("Socket error", flush=True)
            break
        for s in r:
            if s is sock:
                data = s.recv(4096)
                if not data:
                    print("TCP closed", flush=True)
                    return
                udp_out.sendto(data, (WINDOWS_HOST, QGC_PORT))
                udp_out.sendto(data, (WINDOWS_HOST, BACKEND_PORT))
            elif s is udp_in:
                data, addr = s.recvfrom(4096)
                try:
                    sock.send(data)
                except:
                    pass
        time.sleep(0.001)

if __name__ == "__main__":
    main()
