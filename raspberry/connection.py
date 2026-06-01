"""
Companion MAVLink Connection - Raspberry Pi
Conexión minimalista al Pixhawk via USB/UART
"""

from pymavlink import mavutil
import logging
import threading
import time

logger = logging.getLogger(__name__)


class MAVLinkConnection:
    """Conexión MAVLink minimalista para Raspberry Pi Companion"""
    
    def __init__(self, device, baud):
        """
        Inicializar conexión
        
        Args:
            device: Puerto serial (/dev/ttyUSB0, /dev/ttyAMA0, etc)
            baud: Baudrate (57600, 115200, etc)
        """
        self.device = device
        self.baud = baud
        self.master = None
        self.connected = False
        self._lock = threading.Lock()
        self._auto_reconnect_thread = None
        self._auto_reconnect_stop = None

        # Intentar conectar
        self.connect()
    
    def connect(self):
        """Establecer conexión con Pixhawk (con reintentos)"""
        max_retries = 5
        backoff_factor = 1.0
        attempt = 0
        last_exc = None

        while attempt < max_retries:
            try:
                logger.info(f"🔌 Conectando a {self.device} @ {self.baud} baud... (intento {attempt+1}/{max_retries})")
                
                with self._lock:
                    self.master = mavutil.mavlink_connection(
                        self.device,
                        baud=self.baud,
                        source_system=255  # GCS
                    )
                
                logger.info("⏳ Esperando heartbeat (timeout=10s)...")
                self.master.wait_heartbeat(timeout=10)
                
                self.connected = True
                logger.info(f"✅ Conectado (System: {self.master.target_system}, Component: {self.master.target_component})")
                return True
                
            except Exception as e:
                last_exc = e
                self.connected = False
                logger.warning(f"❌ Error en intento {attempt+1}: {e}")
                
                attempt += 1
                if attempt >= max_retries:
                    break
                
                sleep_time = backoff_factor * (2 ** (attempt - 1))
                logger.info(f"⏱ Reintentando en {sleep_time}s...")
                time.sleep(sleep_time)
        
        logger.error(f"No se pudo conectar a {self.device}: {last_exc}")
        raise ConnectionError(f"No se pudo conectar a {self.device}: {last_exc}")
    
    def disconnect(self):
        """Cerrar conexión"""
        # Detener auto-reconnect si está activo
        if self._auto_reconnect_stop:
            try:
                self._auto_reconnect_stop.set()
            except Exception:
                pass
        if self._auto_reconnect_thread:
            try:
                self._auto_reconnect_thread.join(timeout=2)
            except Exception:
                pass

        self.connected = False
        if self.master:
            with self._lock:
                try:
                    self.master.close()
                except Exception:
                    pass
                self.master = None
        logger.info("🔌 Desconectado")
    
    def is_connected(self):
        """Verificar si está conectado"""
        return self.connected and self.master is not None
    
    def recv_match(self, msg_type=None, blocking=False, timeout=None):
        """
        Recibir mensaje MAVLink
        
        Args:
            msg_type: Tipo de mensaje a esperar (ej: 'HEARTBEAT')
            blocking: Si debe bloquear hasta recibir
            timeout: Tiempo máximo de espera (segundos)
        
        Returns:
            Mensaje recibido o None
        """
        if not self.is_connected():
            return None
        
        with self._lock:
            return self.master.recv_match(
                type=msg_type,
                blocking=blocking,
                timeout=timeout
            )

    def start_auto_reconnect(self, interval: float = 5.0, backoff_factor: float = 1.0):
        """Inicia un hilo que intentará reconectar periódicamente si la conexión se pierde.

        El hilo intentará `connect()` y aplicará backoff exponencial en fallos.
        """
        if self._auto_reconnect_thread and getattr(self._auto_reconnect_thread, 'is_alive', lambda: False)():
            return

        self._auto_reconnect_stop = threading.Event()

        def _loop():
            logger.info("🔁 Auto-reconnect thread iniciado")
            backoff = interval
            while not self._auto_reconnect_stop.is_set():
                if self.is_connected():
                    backoff = interval
                    time.sleep(interval)
                    continue

                try:
                    # Intento único; connect tiene su propio retry interno
                    self.connect()
                    backoff = interval
                except Exception as e:
                    logger.debug(f"Auto-reconnect intento fallido: {e}")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)

            logger.info("🔁 Auto-reconnect thread detenido")

        self._auto_reconnect_thread = threading.Thread(target=_loop, daemon=True)
        self._auto_reconnect_thread.start()

    def stop_auto_reconnect(self):
        """Detiene el hilo de reconexión automática (si existe)."""
        if self._auto_reconnect_stop:
            try:
                self._auto_reconnect_stop.set()
            except Exception:
                pass
        if self._auto_reconnect_thread:
            try:
                self._auto_reconnect_thread.join(timeout=2)
            except Exception:
                pass
            self._auto_reconnect_thread = None
            self._auto_reconnect_stop = None
    
    def wait_ack(self, command_id=None, timeout=3):
        """
        Esperar confirmación (ACK) de comando
        
        Args:
            command_id: ID del comando (opcional)
            timeout: Tiempo de espera
        
        Returns:
            True si fue aceptado, False si no
        """
        ack = self.recv_match('COMMAND_ACK', blocking=True, timeout=timeout)
        
        if not ack:
            logger.warning("⚠️ No se recibió ACK")
            return False
        
        if command_id and ack.command != command_id:
            return False
        
        if ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            logger.debug("✅ Comando aceptado")
            return True
        else:
            logger.warning(f"⚠️ Comando rechazado (código: {ack.result})")
            return False
    
    def start_telemetry_loop(self, interval=0.01):
        """
        Inicia thread de lectura de telemetría (no bloqueante)
        
        Args:
            interval: Tiempo entre iteraciones (segundos)
        """
        self._telemetry_running = True
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop,
            kwargs={'interval': interval},
            daemon=True
        )
        self._telemetry_thread.start()
        logger.info(f"📡 Thread de telemetría iniciado (intervalo={interval}s)")
    
    def _telemetry_loop(self, interval=0.01):
        """Loop interno de lectura de telemetría"""
        # Mantener el thread vivo incluso si la conexión se pierde; cuando no hay
        # conexión, el loop duerme y espera reconexión.
        while getattr(self, '_telemetry_running', False):
            try:
                if not self.is_connected():
                    time.sleep(0.5)
                    continue

                msg = self.recv_match(blocking=False)
                if msg:
                    msg_type = msg.get_type()
                    if msg_type == "HEARTBEAT":
                        self._log_heartbeat(msg)
                    elif msg_type == "VFR_HUD":
                        self._log_vfr_hud(msg)
                    elif msg_type == "GPS_RAW_INT":
                        self._log_gps(msg)
                    elif msg_type == "BATTERY_STATUS":
                        self._log_battery(msg)

                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error en telemetry_loop: {e}")
                time.sleep(0.1)
    
    def stop_telemetry_loop(self):
        """Detener thread de telemetría"""
        self._telemetry_running = False
        if hasattr(self, '_telemetry_thread'):
            self._telemetry_thread.join(timeout=2)
        logger.info("📡 Thread de telemetría detenido")
    
    # ============================================
    # Handlers de telemetría (logging simple)
    # ============================================
    
    def _log_heartbeat(self, msg):
        """Procesar HEARTBEAT"""
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        mode = mavutil.mode_string_v10(msg)
        logger.debug(f"💚 HEARTBEAT: Armed={armed}, Mode={mode}")
    
    def _log_vfr_hud(self, msg):
        """Procesar VFR_HUD (velocidad, altitud, climb)"""
        logger.debug(f"📊 VFR_HUD: Alt={msg.alt:.1f}m, Speed={msg.airspeed:.1f}m/s, Climb={msg.climb:.1f}m/s")
    
    def _log_gps(self, msg):
        """Procesar GPS_RAW_INT"""
        lat = msg.lat / 1e7
        lon = msg.lon / 1e7
        alt = msg.alt / 1000.0
        sats = msg.satellites_visible
        logger.debug(f"📍 GPS: ({lat:.6f}, {lon:.6f}), Alt={alt:.1f}m, Sats={sats}")
    
    def _log_battery(self, msg):
        """Procesar BATTERY_STATUS"""
        voltage = msg.voltages[0] / 1000.0 if msg.voltages else 0
        current = msg.current_battery / 100.0
        remaining = msg.battery_remaining
        logger.debug(f"🔋 BATTERY: {voltage:.2f}V, {current:.1f}A, {remaining}%")
    
    # ============================================
    # Comandos básicos
    # ============================================
    
    def send_arm(self):
        """Armar motores"""
        logger.info("🔴 ARM - Armando motores...")
        with self._lock:
            master = self.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")

            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 1, 0, 0, 0, 0, 0, 0
            )

        return self.wait_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
    
    def send_disarm(self):
        """Desarmar motores"""
        logger.info("🟢 DISARM - Desarmando motores...")
        with self._lock:
            master = self.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")

            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 0, 0, 0, 0, 0, 0, 0
            )

        return self.wait_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
    
    def send_mode(self, mode_name):
        """Cambiar modo de vuelo"""
        logger.info(f"🔄 Cambiando a modo: {mode_name}")
        with self._lock:
            master = self.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")

            if mode_name not in master.mode_mapping():
                raise ValueError(f"Modo inválido: {mode_name}")
            mode_id = master.mode_mapping()[mode_name]
            master.set_mode(mode_id)

        return True
