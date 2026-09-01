"""
MAVLink proxy minimalista.
- SITL TCP:5760 (servidor) — proxy se conecta como cliente, lo mantiene vivo
- Backend UDP:14550 (servidor) — proxy reenvía datos de SITL al backend
- El proxy actúa como GCS intermediario
"""
import socket
import threading
import time

SITL_HOST = "127.0.0.1"
SITL_PORT = 5760
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 14550   # el backend escucha aqui con udpin:0.0.0.0:14550


def connect_sitl():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((SITL_HOST, SITL_PORT))
            s.settimeout(None)
            print(f"[proxy] Conectado a SITL TCP {SITL_HOST}:{SITL_PORT}")
            return s
        except Exception as e:
            print(f"[proxy] Esperando SITL: {e}")
            time.sleep(2)


def main():
    sitl = connect_sitl()

    # Socket UDP para hablar con el backend
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("0.0.0.0", 0))  # puerto efímero
    proxy_port = udp.getsockname()[1]
    print(f"[proxy] UDP proxy en puerto {proxy_port} → backend {BACKEND_HOST}:{BACKEND_PORT}")

    backend_reply_addr = None

    def sitl_to_backend():
        """Lee del SITL y manda al backend UDP."""
        while True:
            try:
                data = sitl.recv(4096)
                if not data:
                    print("[proxy] SITL cerró TCP")
                    break
                udp.sendto(data, (BACKEND_HOST, BACKEND_PORT))
            except Exception as e:
                print(f"[proxy] sitl→backend error: {e}")
                break

    def backend_to_sitl():
        """Recibe respuestas del backend y las manda al SITL TCP."""
        nonlocal backend_reply_addr
        while True:
            try:
                data, addr = udp.recvfrom(4096)
                backend_reply_addr = addr
                sitl.sendall(data)
            except Exception as e:
                print(f"[proxy] backend→sitl error: {e}")
                break

    t1 = threading.Thread(target=sitl_to_backend, daemon=True)
    t2 = threading.Thread(target=backend_to_sitl, daemon=True)
    t1.start(); t2.start()
    print("[proxy] Corriendo. Ctrl+C para detener.")
    try:
        while t1.is_alive() and t2.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    print("[proxy] Terminado.")


if __name__ == "__main__":
    main()
