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
        self._pending_ack = None                 # COMMAND_ACK almacenado por _read_loop
        self._ack_lock = threading.Lock()
        self._pending_msgs = {}                  # msg_type -> msg, para mensajes capturados por _read_loop
        self._pending_msgs_lock = threading.Lock()
        self._pause_read = threading.Event()     # Pausar _read_loop durante comandos sensitivos

        self.connect()

    # ── Conexión ───────────────────────────────────────────────────────────────

    def connect(self, max_retries: int = 5, backoff_factor: float = 1.0):
        attempt    = 0
        last_exc   = None

        while attempt < max_retries:
            try:
                logger.info(f"🔌 Conectando a {self.device} @ {self.baud} baud (intento {attempt+1}/{max_retries})")
                with self._lock:
                    self.master = mavutil.mavlink_connection(
                        self.device,
                        baud=self.baud,
                        source_system=255,
                    )

                logger.info("⏳ Esperando heartbeat...")
                self.master.wait_heartbeat(timeout=10)
                self.connected = True
                logger.info(f"✅ Conectado (System: {self.master.target_system}, Component: {self.master.target_component})")
                return True

            except Exception as e:
                last_exc      = e
                self.connected = False
                logger.warning(f"❌ Error en intento {attempt+1}: {e}")
                attempt += 1
                if attempt >= max_retries:
                    break
                sleep_time = backoff_factor * (2 ** (attempt - 1))
                logger.info(f"⏱ Reintentando en {sleep_time}s...")
                time.sleep(sleep_time)

        raise ConnectionError(f"No se pudo conectar a {self.device} tras {max_retries} intentos: {last_exc}")

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

    def start_auto_reconnect(self, interval: float = 5.0):
        if self._auto_reconnect_thread and self._auto_reconnect_thread.is_alive():
            return
        self._auto_reconnect_stop = threading.Event()

        def _loop():
            logger.info("🔁 Auto-reconnect thread iniciado")
            while not self._auto_reconnect_stop.is_set():
                if not self.is_connected():
                    try:
                        self.connect(max_retries=1)
                    except Exception:
                        logger.debug("Auto-reconnect: intento fallido")
                self._auto_reconnect_stop.wait(interval)
            logger.info("🔁 Auto-reconnect thread detenido")

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
        return self.master.recv_match(
            type=msg_type,
            blocking=blocking,
            timeout=timeout,
        )

    def pause_read(self):
        """Context manager para pausar _read_loop durante operaciones exclusivas."""
        class _PauseCtx:
            def __init__(self, conn):
                self.conn = conn
            def __enter__(self):
                self.conn._pause_read.set()
                time.sleep(0.05)
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

    def wait_ack(self, command_id=None, timeout=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._ack_lock:
                pending = self._pending_ack
                if pending is not None:
                    if command_id is None or pending.command == command_id:
                        self._pending_ack = None
                        if pending.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                            logger.debug(f"ACK recibido cmd={pending.command}")
                            return True
                        logger.warning(f"ACK rechazado cmd={pending.command} result={pending.result}")
                        return False
            time.sleep(0.05)

        logger.warning(f"wait_ack timeout cmd={command_id}t={timeout}s")
        return False