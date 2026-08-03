# backend/mavlink/connection.py
"""
Gestión de la conexión MAVLink con Pixhawk.

CORRECCIÓN:
- recv_match ya NO adquiere self._lock. El lock sólo protege escrituras/envíos.
  De esta forma wait_ack (que llama recv_match) no causa deadlock cuando otro
  hilo tiene el lock para enviar un comando.
- send_command ahora tiene implementación real con el lock.
"""

from pymavlink import mavutil
import logging
import select
import socket
import threading
import time

logger = logging.getLogger(__name__)


class MAVLinkConnection:

    def __init__(self, device, baud):
        self.device  = device
        self.baud    = baud
        self.master  = None
        self.connected = False
        self._lock   = threading.Lock()          # Sólo para ESCRITURAS/ENVÍOS
        self._auto_reconnect_thread = None
        self._auto_reconnect_stop   = None
        self._pending_acks = {}                   # dict[command_id] -> COMMAND_ACK, almacenado por _read_loop
        self._ack_lock = threading.Lock()
        self._pending_msgs = {}                  # msg_type -> msg, para mensajes capturados por _read_loop
        self._pending_msgs_lock = threading.Lock()
        self._pause_read = threading.Event()     # Pausar _read_loop durante comandos sensitivos
        self._ekf_ready = threading.Event()      # Señaliza cuando EKF terminó de alinearse
        self._disarming = False                  # Flag compartido: en proceso de DISARM
        self._reconnecting = threading.Event()   # Set durante reconnect — suprime mark_dead()
        self._needs_reconnect = threading.Event() # SITL caído — reconectar sin bajar connected
        self._post_reconnect = None               # callback después de reconectar con éxito
        self._suppress_probe = False              # Suprimir probes durante ARM/TAKEOFF/misión

        # Heartbeat health tracking
        self.last_heartbeat: float = 0.0         # timestamp del último HEARTBEAT recibido
        self.heartbeat_healthy = False           # True si se recibió HEARTBEAT recientemente
        self._heartbeat_lock = threading.Lock()
        self.HEARTBEAT_TIMEOUT = 5.0             # segundos sin HEARTBEAT → conexión muerta

        # General message tracking (any MAVLink message)
        self.last_msg_time: float = 0.0          # timestamp del último mensaje de CUALquier tipo
        self._msg_lock = threading.Lock()

        # Send-probe tracking: detect zombie TCP connections (WSL2 port forwarding)
        self._last_ack_time: float = 0.0         # last COMMAND_ACK or meaningful response received
        self._probe_fail_count: int = 0          # consecutive probe failures
        self._probe_lock = threading.Lock()
        PROBE_INTERVAL = 20.0                    # send probe every N seconds
        PROBE_TIMEOUT = 10.0                     # wait this long for response
        PROBE_MAX_FAILURES = 5                   # consecutive failures → mark dead (5 fallos = 100s+ para reconectar)
        self.PROBE_INTERVAL = PROBE_INTERVAL
        self.PROBE_TIMEOUT = PROBE_TIMEOUT
        self.PROBE_MAX_FAILURES = PROBE_MAX_FAILURES

        self.connect()

    # ── Conexión ───────────────────────────────────────────────────────────────

    def connect(self, max_retries: int = 5, backoff_factor: float = 1.0, _keep_alive: bool = False):
        attempt    = 0
        last_exc   = None

        while attempt < max_retries:
            try:
                logger.info(f"🔌 Conectando a {self.device} @ {self.baud} baud (intento {attempt+1}/{max_retries})")

                if _keep_alive:
                    self._close_socket()
                else:
                    self.disconnect()

                new_master = mavutil.mavlink_connection(
                    self.device,
                    baud=self.baud,
                    source_system=255,
                )
                with self._lock:
                    self.master = new_master

                logger.info("⏳ Esperando heartbeat...")
                self.master.wait_heartbeat(timeout=5)
                self.connected = True
                self._setup_tcp_keepalive()
                with self._heartbeat_lock:
                    self.last_heartbeat = time.time()
                    self.heartbeat_healthy = True
                with self._msg_lock:
                    self.last_msg_time = time.time()
                with self._probe_lock:
                    self._last_ack_time = time.time()
                    self._probe_fail_count = 0
                logger.info(f"✅ Conectado (System: {self.master.target_system}, Component: {self.master.target_component})")
                return True

            except Exception as e:
                last_exc      = e
                if not _keep_alive:
                    self.connected = False
                logger.warning(f"❌ Error en intento {attempt+1}: {e}")
                try:
                    if self.master:
                        self.master.close()
                except Exception:
                    pass
                self.master = None
                attempt += 1
                if attempt >= max_retries:
                    break
                sleep_time = backoff_factor * (2 ** (attempt - 1))
                logger.info(f"⏱ Reintentando en {sleep_time}s...")
                time.sleep(sleep_time)

        raise ConnectionError(f"No se pudo conectar a {self.device} tras {max_retries} intentos: {last_exc}")

    def _close_socket(self):
        """Cerrar socket sin cambiar connected — para auto-reconnect."""
        with self._lock:
            if self.master:
                try:
                    self.master.close()
                except Exception:
                    pass
                self.master = None

    def _setup_tcp_keepalive(self):
        """Configure TCP keepalive on the socket to detect dead connections faster."""
        try:
            sock = getattr(self.master, 'socket', None)
            if sock is None:
                return
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # Linux: TCP_KEEPIDLE=6, TCP_KEEPINTVL=4, TCP_KEEPCNT=3 → dead in ~18s
            if hasattr(socket, 'TCP_KEEPIDLE'):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 6)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 4)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            # Windows: TCP_KEEPALIVE (SIO_KEEPALIVE_VALS) — 5s interval
            elif hasattr(socket, 'SIO_KEEPALIVE_VALS'):
                import struct
                sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 5000, 4000))
            logger.info("TCP keepalive configured on socket")
        except Exception as e:
            logger.debug("TCP keepalive setup failed: %s", e)

    def disconnect(self):
        self.connected = False
        with self._lock:
            if self.master:
                self.master.close()
                self.master = None
        logger.info("🔌 Desconectado")

    def reconnect(self, max_retries: int = 5, backoff_factor: float = 1.0):
        try:
            self.disconnect()
        except Exception:
            pass
        return self.connect(max_retries=max_retries, backoff_factor=backoff_factor)

    def start_auto_reconnect(self, initial_interval: float = 5.0, max_interval: float = 30.0):
        """
        Auto-reconnect robusto para uso constante del dron.

        Estrategia:
        - NO reconectar solo porque faltan heartbeats (puede ser normal en SITL).
        - Solo reconectar cuando:
          1. El probe falla 2 veces consecutivas (zombie TCP / conexión muerta), O
          2. El socket TCP está muerto (select falla), O
          3. Alguien llamó mark_dead() (error en read_loop, etc.)
        - Backoff exponencial: 5s → 10s → 20s → 30s (cap).
        """
        if self._auto_reconnect_thread and self._auto_reconnect_thread.is_alive():
            return
        self._auto_reconnect_stop = threading.Event()

        def _loop():
            logger.info("🔁 Auto-reconnect thread iniciado (estable, backoff: %.0fs→%.0fs)", initial_interval, max_interval)
            current_interval = initial_interval
            last_probe_time = 0.0
            while not self._auto_reconnect_stop.is_set():
                try:
                    now = time.time()

                    if self.is_connected() and not self._reconnecting.is_set():

                        # Check 1: Probe periódico para detectar zombie TCP / conexión muerta
                        # Suprimir durante ARM/TAKEOFF/misión para no interrumpir
                        if not self._suppress_probe and now - last_probe_time >= self.PROBE_INTERVAL:
                            last_probe_time = now
                            self.run_probe_check()

                        # Check 2: Socket TCP muerto → reconectar
                        if not self._suppress_probe and not self.is_socket_alive():
                            print("[AUTO-RECONNECT] Socket TCP muerto — reconectando", flush=True)
                            logger.warning("Socket TCP muerto, forzando reconnect")
                            self._needs_reconnect.set()

                        # Check 3: mark_dead() fue llamado (error en read_loop, etc.)
                        # _needs_reconnect ya está set por mark_dead()

                    # Reconectar si hay señal
                    if self._needs_reconnect.is_set() and not self._reconnecting.is_set():
                        print(f"[AUTO-RECONNECT] Reconectando (backoff={current_interval:.0f}s)...", flush=True)
                        try:
                            self._reconnecting.set()
                            try:
                                self.connect(max_retries=1, _keep_alive=True)
                            finally:
                                self._reconnecting.clear()
                            if self.is_connected():
                                self._needs_reconnect.clear()
                                current_interval = initial_interval
                                print("[AUTO-RECONNECT] Reconectado!", flush=True)
                                logger.info("Reconectado (backoff reset a %.0fs)", current_interval)
                                if self._post_reconnect:
                                    try:
                                        self._post_reconnect()
                                    except Exception as e:
                                        logger.error("post_reconnect callback error: %s", e)
                            else:
                                logger.warning("Connect returned pero sigue sin conexion, backoff=%.0fs", current_interval)
                        except Exception as e:
                            print(f"[AUTO-RECONNECT] Connect fallido: {type(e).__name__}: {e}", flush=True)
                            logger.debug("Auto-reconnect: intento fallido (%s), backoff=%.0fs", type(e).__name__, current_interval)
                    else:
                        current_interval = initial_interval

                except Exception as e:
                    print(f"[AUTO-RECONNECT] Loop error: {type(e).__name__}: {e}", flush=True)
                    logger.error("Auto-reconnect loop error: %s", e, exc_info=True)

                self._auto_reconnect_stop.wait(current_interval)
                current_interval = min(current_interval * 2, max_interval)

            logger.info("Auto-reconnect thread detenido")

        self._auto_reconnect_thread = threading.Thread(target=_loop, daemon=True)
        self._auto_reconnect_thread.start()

    def stop_auto_reconnect(self):
        if self._auto_reconnect_stop:
            self._auto_reconnect_stop.set()
        if self._auto_reconnect_thread:
            self._auto_reconnect_thread.join(timeout=2)
            self._auto_reconnect_thread = None
            self._auto_reconnect_stop   = None

    def is_connected(self):
        return self.connected and self.master is not None

    # ── Heartbeat Health ─────────────────────────────────────────────────────

    def update_heartbeat(self):
        """Llamar desde telemetry._process_message cuando se recibe HEARTBEAT."""
        with self._heartbeat_lock:
            self.last_heartbeat = time.time()
            self.heartbeat_healthy = True

    def is_heartbeat_healthy(self) -> bool:
        """True si se recibió un HEARTBEAT en los últimos HEARTBEAT_TIMEOUT segundos."""
        with self._heartbeat_lock:
            if self.last_heartbeat == 0.0:
                return False
            return (time.time() - self.last_heartbeat) < self.HEARTBEAT_TIMEOUT

    def heartbeat_age(self) -> float:
        """Segundos desde el último HEARTBEAT. inf si nunca se recibió."""
        with self._heartbeat_lock:
            if self.last_heartbeat == 0.0:
                return float('inf')
            return time.time() - self.last_heartbeat

    def update_msg_time(self):
        """Llamar desde _read_loop cuando se recibe CUALQUIER mensaje MAVLink.
        Resetea probe_fail_count — si hay tráfico, la conexión está viva."""
        with self._msg_lock:
            self.last_msg_time = time.time()
        with self._probe_lock:
            if self._probe_fail_count > 0:
                self._probe_fail_count = 0

    def msg_age(self) -> float:
        """Segundos desde el último mensaje de cualquier tipo. inf si nunca se recibió."""
        with self._msg_lock:
            if self.last_msg_time == 0.0:
                return float('inf')
            return time.time() - self.last_msg_time

    def is_socket_alive(self) -> bool:
        """Verificar si la conexión está viva.
        Usa select() + MSG_PEEK como verificación principal.
        Si hay mensajes fluyendo recientemente (<10s), se considera viva aunque select falle."""
        if not self.master:
            return False
        try:
            sock = getattr(self.master, 'socket', None)
            if sock is None:
                return self.msg_age() < 10.0
            readable, _, _ = select.select([sock], [], [], 0)
            if readable:
                data = sock.recv(1, socket.MSG_PEEK)
                if not data:
                    return self.msg_age() < 10.0
            return True
        except (OSError, ValueError, AttributeError):
            return self.msg_age() < 10.0

    def mark_dead(self, reason: str = "unknown"):
        """Marcar conexión como muerta y activar reconexión automática.
        NO baja connected=False — el app siempre ve connected=True.
        En vez de eso, setea _needs_reconnect para que auto-reconnect restaure la conexión."""
        if self._reconnecting.is_set() or self._needs_reconnect.is_set():
            logger.debug("mark_dead suppressed during reconnect: %s", reason)
            return
        logger.warning("Connection marked dead: %s — triggering auto-reconnect", reason)
        self._needs_reconnect.set()

    def suppress_probe(self, suppress: bool):
        """Suprimir/reaktivar probes y reconexión automática durante operaciones activas."""
        self._suppress_probe = suppress
        if suppress:
            logger.info("🔍 Probes suprimidos — operación activa")
        else:
            logger.info("🔍 Probes reactivados")

    # ── Send-Probe: detect zombie TCP connections ──────────────────────────────

    def update_ack_time(self):
        """Llamar cuando se recibe COMMAND_ACK u otra respuesta significativa."""
        with self._probe_lock:
            self._last_ack_time = time.time()
            self._probe_fail_count = 0

    def _send_probe(self) -> bool:
        """Send a lightweight command and check for ACK. Returns True if connection is alive."""
        if not self.is_connected():
            return False
        try:
            with self._lock:
                self.master.mav.command_long_send(
                    self.master.target_system,
                    self.master.target_component,
                    mavutil.mavlink.MAV_CMD_REQUEST_PROTOCOL_VERSION,
                    0, 0, 0, 0, 0, 0, 0, 0,
                )
            deadline = time.time() + self.PROBE_TIMEOUT
            while time.time() < deadline:
                with self._ack_lock:
                    if mavutil.mavlink.MAV_CMD_REQUEST_PROTOCOL_VERSION in self._pending_acks:
                        ack = self._pending_acks.pop(
                            mavutil.mavlink.MAV_CMD_REQUEST_PROTOCOL_VERSION
                        )
                        if ack.result in (0, 3):
                            return True
                time.sleep(0.05)
            return False
        except Exception as e:
            logger.debug("Probe send failed: %s", e)
            return False

    def run_probe_check(self):
        """Called by auto-reconnect thread periodically. Detects zombie TCP connections.
        Safety net: if ANY messages are flowing (msg_age < 5s), don't count as failure."""
        if not self.is_connected() or self._reconnecting.is_set() or self._needs_reconnect.is_set():
            return

        # Safety net: si hay tráfico reciente, la conexión está viva
        # (el probe ACK puede haberse perdido entre otros mensajes)
        if self.msg_age() < 5.0:
            with self._probe_lock:
                if self._probe_fail_count > 0:
                    print(f"[PROBE] msgs flowing — resetting fail count", flush=True)
                self._probe_fail_count = 0
            return

        alive = self._send_probe()
        with self._probe_lock:
            if not alive:
                self._probe_fail_count += 1
                print(f"[PROBE] Failed ({self._probe_fail_count}/{self.PROBE_MAX_FAILURES})", flush=True)
                logger.warning("⚠️ Send probe failed (%d/%d)", self._probe_fail_count, self.PROBE_MAX_FAILURES)
                if self._probe_fail_count >= self.PROBE_MAX_FAILURES:
                    print(f"[PROBE] Zombie connection detected — triggering reconnect", flush=True)
                    logger.warning("💀 Zombie TCP connection detected (WSL2?) — forcing reconnect")
                    with self._heartbeat_lock:
                        self.heartbeat_healthy = False
                    self._needs_reconnect.set()
            else:
                if self._probe_fail_count > 0:
                    print(f"[PROBE] Connection alive again", flush=True)
                self._probe_fail_count = 0

    def get_connection_health(self) -> dict:
        """Estado completo de salud de la conexión para endpoints/status."""
        with self._heartbeat_lock:
            hb_age = time.time() - self.last_heartbeat if self.last_heartbeat > 0 else float('inf')
        msg_a = self.msg_age()
        needs = self._needs_reconnect.is_set()
        with self._probe_lock:
            probe_fails = self._probe_fail_count
        socket_alive = self.is_socket_alive()
        healthy = self.connected and socket_alive and probe_fails < self.PROBE_MAX_FAILURES and not needs
        return {
            "connected": self.connected,
            "sconnected": self.is_connected(),
            "healthy": healthy,
            "heartbeat_age_s": round(hb_age, 2) if hb_age != float('inf') else None,
            "last_msg_age_s": round(msg_a, 2) if msg_a != float('inf') else None,
            "socket_alive": socket_alive,
            "reconnecting": self._reconnecting.is_set(),
            "needs_reconnect": needs,
            "probe_failures": probe_fails,
            "device": self.device,
        }

    # ── Envío (con lock) ───────────────────────────────────────────────────────

    def send_command(self, command_fn, *args, **kwargs):
        """
        Wrapper genérico para envíos que requieren el lock.
        Uso: self.conn.send_command(master.mav.command_long_send, ...)
        """
        if not self.is_connected():
            raise ConnectionError("No hay conexión con Pixhawk")
        with self._lock:
            command_fn(*args, **kwargs)

    # ── Recepción (SIN lock para evitar deadlock) ──────────────────────────────

    def recv_match(self, msg_type=None, blocking=True, timeout=None):
        """
        Recibir mensaje MAVLink.

        CORRECCIÓN: NO adquiere self._lock. pymavlink.recv_match es thread-safe
        internamente, y adquirir el lock aquí causaba deadlock cuando wait_ack
        (que llama recv_match) era invocado mientras otro hilo tenía el lock
        para enviar un comando (bloqueante hasta 3 s).
        """
        if not self.is_connected():
            return None
        try:
            return self.master.recv_match(
                type=msg_type,
                blocking=blocking,
                timeout=timeout,
            )
        except (OSError, IOError) as e:
            logger.debug("recv_match serial error: %s", e)
            return None

    def pause_read(self):
        """Context manager para pausar _read_loop durante operaciones exclusivas."""
        class _PauseCtx:
            def __init__(self, conn):
                self.conn = conn
            def __enter__(self):
                self.conn._pause_read.set()
                time.sleep(0.2)
                return self
            def __exit__(self, *args):
                self.conn._pause_read.clear()
        return _PauseCtx(self)

    def recv_match_protected(self, msg_type, timeout=5):
        """
        Recibir mensaje evitando race con _read_loop.
        Revisa _pending_msgs en un loop cada 50ms.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._pending_msgs_lock:
                pending = self._pending_msgs.pop(msg_type, None)
                if pending is not None:
                    return pending
            msg = self.recv_match(msg_type=msg_type, blocking=False)
            if msg is not None:
                return msg
            time.sleep(0.05)
        return None

    # ── ACK ────────────────────────────────────────────────────────────────────

    def wait_ack(self, command_id=None, timeout=5):
        MAV_RESULT_ACCEPTED = 0
        MAV_RESULT_IN_PROGRESS = 4
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._ack_lock:
                if command_id is not None and command_id in self._pending_acks:
                    ack = self._pending_acks.pop(command_id)
                    if ack.result == MAV_RESULT_ACCEPTED:
                        logger.debug(f"ACK recibido cmd={ack.command}")
                        return True
                    if ack.result == MAV_RESULT_IN_PROGRESS:
                        logger.debug(f"ACK IN_PROGRESS cmd={ack.command} — esperando más...")
                        self._pending_acks[command_id] = ack
                    else:
                        logger.warning(f"ACK rechazado cmd={ack.command} result={ack.result}")
                        return False
                elif command_id is None and self._pending_acks:
                    cmd_id, ack = next(iter(self._pending_acks.items()))
                    if ack.result == MAV_RESULT_ACCEPTED:
                        self._pending_acks.pop(cmd_id)
                        logger.debug(f"ACK recibido cmd={ack.command}")
                        return True
                    if ack.result == MAV_RESULT_IN_PROGRESS:
                        logger.debug(f"ACK IN_PROGRESS cmd={ack.command} — esperando más...")
                    else:
                        self._pending_acks.pop(cmd_id)
                        logger.warning(f"ACK rechazado cmd={ack.command} result={ack.result}")
                        return False
            time.sleep(0.05)

        logger.warning(f"wait_ack timeout cmd={command_id} t={timeout}s")
        return False