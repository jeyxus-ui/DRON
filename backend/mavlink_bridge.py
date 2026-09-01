"""
MAVLink bridge: conecta a SITL TCP:5760 como cliente primario y
re-expone el trafico en TCP:5762 (para MP) y TCP:5763 (para backend).
Mantiene SITL vivo con una conexion permanente.
"""
import socket
import threading
import time
import sys
import struct
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('bridge')

SITL_HOST = '127.0.0.1'
SITL_PORT = 5760      # SITL TCP (primario)
BRIDGE_MP   = 5762    # para Mission Planner
BRIDGE_BACK = 5763    # para backend

RECONNECT_DELAY = 2.0

clients_lock = threading.Lock()
clients: list[socket.socket] = []

def parse_mavlink_length(data: bytes, offset: int) -> int:
    """Retorna longitud total del paquete MAVLink en offset, o 0 si incompleto."""
    if offset + 1 >= len(data):
        return 0
    magic = data[offset]
    if magic == 0xFE:          # MAVLink 1
        if offset + 6 > len(data):
            return 0
        payload_len = data[offset + 1]
        return 6 + payload_len + 2   # header + payload + crc
    elif magic == 0xFD:        # MAVLink 2
        if offset + 10 > len(data):
            return 0
        payload_len = data[offset + 1]
        incompat = data[offset + 2]
        signed = bool(incompat & 0x01)
        return 10 + payload_len + 2 + (13 if signed else 0)
    return 0


def broadcast(data: bytes, exclude: socket.socket = None):
    """Envía data a todos los clientes downstream."""
    with clients_lock:
        dead = []
        for c in clients:
            if c is exclude:
                continue
            try:
                c.sendall(data)
            except Exception:
                dead.append(c)
        for c in dead:
            clients.remove(c)
            try:
                c.close()
            except Exception:
                pass


class SITLLink:
    """Conexion persistente al SITL."""
    def __init__(self):
        self.sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._stop = False

    def connect(self):
        while not self._stop:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((SITL_HOST, SITL_PORT))
                s.settimeout(None)
                with self._lock:
                    self.sock = s
                log.info(f"Conectado a SITL {SITL_HOST}:{SITL_PORT}")
                self._read_loop(s)
            except Exception as e:
                log.warning(f"SITL {e} — reintentando en {RECONNECT_DELAY}s")
                time.sleep(RECONNECT_DELAY)

    def _read_loop(self, s: socket.socket):
        buf = b''
        try:
            while not self._stop:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                # forward all complete MAVLink packets to downstream clients
                i = 0
                while i < len(buf):
                    pkt_len = parse_mavlink_length(buf, i)
                    if pkt_len == 0 or i + pkt_len > len(buf):
                        break
                    broadcast(buf[i:i+pkt_len])
                    i += pkt_len
                buf = buf[i:]
        except Exception as e:
            log.warning(f"SITL read error: {e}")
        finally:
            with self._lock:
                self.sock = None
            try:
                s.close()
            except Exception:
                pass
            log.info("SITL desconectado")

    def send(self, data: bytes):
        with self._lock:
            if self.sock:
                try:
                    self.sock.sendall(data)
                except Exception as e:
                    log.warning(f"SITL send error: {e}")

    def stop(self):
        self._stop = True
        with self._lock:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass


sitl = SITLLink()


def handle_client(conn: socket.socket, addr):
    log.info(f"Cliente conectado: {addr}")
    with clients_lock:
        clients.append(conn)
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            # Forward client → SITL
            sitl.send(data)
    except Exception as e:
        log.debug(f"Cliente {addr} error: {e}")
    finally:
        with clients_lock:
            if conn in clients:
                clients.remove(conn)
        try:
            conn.close()
        except Exception:
            pass
        log.info(f"Cliente desconectado: {addr}")


def serve(port: int, label: str):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', port))
    srv.listen(5)
    log.info(f"Bridge escuchando en :{port} ({label})")
    while True:
        try:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except Exception as e:
            log.error(f"Accept error {label}: {e}")


if __name__ == '__main__':
    log.info("MAVLink Bridge iniciado")
    log.info(f"  SITL: tcp:{SITL_HOST}:{SITL_PORT}")
    log.info(f"  MP:   tcp:0.0.0.0:{BRIDGE_MP}")
    log.info(f"  Backend: tcp:0.0.0.0:{BRIDGE_BACK}")

    # Hilo de conexion al SITL
    t_sitl = threading.Thread(target=sitl.connect, daemon=True)
    t_sitl.start()

    # Servidor para MP
    t_mp = threading.Thread(target=serve, args=(BRIDGE_MP, 'MissionPlanner'), daemon=True)
    t_mp.start()

    # Servidor para backend (no daemon so main thread stays alive)
    serve(BRIDGE_BACK, 'Backend')
