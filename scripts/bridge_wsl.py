"""Bridge TCP MAVLink (WSL arducopter) ↔ UDP (Windows backend).
Single UDP port (14551) for bidirectional communication.
TCP stays inside WSL (reliable). UDP bridges to Windows (no port forwarding issues).

Flow:
  Bridge listens on UDP 14551
  Backend (udpin:0.0.0.0:14551) sends heartbeat → bridge learns backend address
  Bridge sends SITL telemetry to backend on 14551
  Backend sends commands to bridge on 14551 → bridge forwards to SITL via TCP
"""
import socket, select, time

TCP_HOST = "127.0.0.1"
TCP_PORT = 5760
UDP_PORT = 14551

def get_windows_ip():
    try:
        import subprocess
        r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
        return r.stdout.split()[2]
    except Exception:
        return "172.28.240.1"

WINDOWS_HOST = get_windows_ip()
print(f"Windows IP: {WINDOWS_HOST}", flush=True)

def main():
    while True:
        try:
            run_bridge()
        except Exception as e:
            print(f"Bridge error: {e}, reconnecting in 3s...", flush=True)
            time.sleep(3)

def run_bridge():
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.settimeout(60)
    print(f"Connecting to arducopter at {TCP_HOST}:{TCP_PORT}...", flush=True)
    tcp_sock.connect((TCP_HOST, TCP_PORT))
    tcp_sock.setblocking(False)
    print("Connected to arducopter!", flush=True)

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(("0.0.0.0", UDP_PORT))
    udp.setblocking(False)
    print(f"UDP bidirectional on 0.0.0.0:{UDP_PORT}", flush=True)

    backend_addr = None

    while True:
        r, _, e = select.select([tcp_sock, udp], [], [tcp_sock, udp], 1)
        if e:
            print("Socket error", flush=True)
            break
        for s in r:
            if s is tcp_sock:
                data = s.recv(4096)
                if not data:
                    print("TCP closed by SITL", flush=True)
                    return
                if backend_addr:
                    udp.sendto(data, backend_addr)
            elif s is udp:
                data, addr = udp.recvfrom(4096)
                if backend_addr is None:
                    print(f"Backend connected from {addr}", flush=True)
                backend_addr = addr
                try:
                    tcp_sock.send(data)
                except Exception as ex:
                    print(f"TCP send error: {ex}", flush=True)
                    return
        time.sleep(0.001)

if __name__ == "__main__":
    main()
