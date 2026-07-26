"""
Control RC Override para joysticks virtuales
Permite control manual del dron mediante comandos RC_CHANNELS_OVERRIDE

CORRECCIÓN: Este módulo espera valores NORMALIZADOS (-1.0 a 1.0).
El frontend NO debe pre-convertir a PWM — eso lo hace este módulo.
"""
import threading
import time
import logging
from pymavlink import mavutil

logger = logging.getLogger(__name__)


class RCOverrideController:
    """
    Controlador de RC Override para control manual del dron.
    Mapea valores de joystick normalizados (-1.0 a 1.0) a valores PWM (1000-2000).

    IMPORTANTE: Todos los valores de entrada deben estar normalizados:
      - throttle: 0.0 (mínimo) a 1.0 (máximo)
      - yaw, pitch, roll: -1.0 a 1.0
    """

    # Canales RC estándar ArduPilot
    CHANNEL_ROLL     = 0  # Aileron
    CHANNEL_PITCH    = 1  # Elevator
    CHANNEL_THROTTLE = 2  # Throttle
    CHANNEL_YAW      = 3  # Rudder

    PWM_MIN    = 1000
    PWM_MAX    = 2000
    PWM_CENTER = 1500

    # ── Constantes ───────────────────────────────────────────────────────────

    IDLE_THROTTLE = 0.15    # 15% = ~1150 PWM (idle armado)
    ARM_IDLE_DURATION = 1.0  # 1 segundo de espera post-armado antes de activar joystick
    DISARM_TIMEOUT = 60.0    # segundos sin NINGÚN cliente conectado → empezar a reducir
    RAMP_DOWN_DURATION = 15.0 # segundos para reducir throttle de actual → 0

    def __init__(self, mavlink_connection):
        self.conn    = mavlink_connection
        self.channels = [0] * 8
        self.running  = False
        self.thread   = None

        # Valores normalizados de joystick — throttle inicia en idle (15%)
        self.throttle = 0.15
        self.yaw      = 0.0
        self.pitch    = 0.0
        self.roll     = 0.0

        self.lock = threading.Lock()
        self._failsafe_fired = False
        self._idle_logged = False  # Solo loguear "idle completado" una vez
        self._armed_at: float | None = None  # timestamp de armado, None si desarmado
        self._send_failures = 0
        self._disconnected_at: float | None = None  # timestamp de desconexión WS
        self._disarmed_by_failsafe = False
        self._active = False  # Solo enviar RC override cuando esté activo (post-ARM)
        self._connected_clients = 0  # Contador de clientes WebSocket activos
        self._autonomous = False  # Pausar RC durante operaciones autónomas (TAKEOFF, misión)
        logger.info("RCOverrideController inicializado")

    def start(self):
        if not self.running:
            self.running = True
            self.thread  = threading.Thread(target=self._send_loop, daemon=True)
            self.thread.start()
            logger.info("RC Override iniciado — enviando a 10 Hz")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        self._release_control()
        logger.info("RC Override detenido")

    # ── Loop de envío ─────────────────────────────────────────────────────────

    def _send_loop(self):
        while self.running:
            try:
                now = time.time()

                # No enviar RC override antes del primer ARM (evita interferir con EKF init)
                if not self._active:
                    time.sleep(0.5)
                    continue

                # Enviar valores neutros durante operaciones autónomas (TAKEOFF, misión, etc.)
                if self._autonomous:
                    master = self.conn.master
                    if master is not None:
                        try:
                            master.mav.rc_channels_override_send(
                                master.target_system,
                                master.target_component,
                                self.PWM_CENTER,
                                self.PWM_CENTER,
                                self.PWM_CENTER,
                                self.PWM_CENTER,
                                0, 0, 0, 0,
                            )
                        except Exception:
                            pass
                    time.sleep(0.2)
                    continue

                # Pausar envío durante DISARM para no interferir con el comando
                if getattr(self.conn, '_disarming', False):
                    time.sleep(0.1)
                    continue

                with self.lock:
                    use_throttle = self.throttle
                    use_yaw      = self.yaw
                    use_pitch    = self.pitch
                    use_roll     = self.roll
                    disconnected = self._disconnected_at
                    disarmed     = self._disarmed_by_failsafe

                    # ── Idle post-armado ──────────────────────────────────
                    if self._armed_at is not None:
                        idle_remaining = self.ARM_IDLE_DURATION - (now - self._armed_at)
                        if idle_remaining > 0:
                            use_throttle = self.IDLE_THROTTLE
                            use_yaw = 0.0
                            use_pitch = 0.0
                            use_roll = 0.0
                            if int(idle_remaining) != int(idle_remaining + 0.1):
                                logger.info('⏳ IDLE ARM — %.0f s restantes (joystick bloqueado)', idle_remaining)
                        elif not self._idle_logged:
                            self._idle_logged = True
                            logger.info('✅ IDLE ARM — periodo de idle completado, joystick activo')

                # ── Ramp-down por desconexión (fuera del lock) ────────────
                if disconnected is not None and not disarmed:
                    elapsed = now - disconnected
                    if elapsed >= self.DISARM_TIMEOUT:
                        ramp_t = elapsed - self.DISARM_TIMEOUT
                        if ramp_t < self.RAMP_DOWN_DURATION:
                            factor = 1.0 - (ramp_t / self.RAMP_DOWN_DURATION)
                            use_throttle *= max(0.0, factor)
                            if int(ramp_t) != int(ramp_t - 0.1):
                                logger.warning('⏬ FAILSAFE — reduciendo throttle: %.0f%% restante', factor * 100)
                        else:
                            with self.lock:
                                self._disarmed_by_failsafe = True
                            logger.critical('🚨 FAILSAFE — throttle 0, desarmando motores (force)')
                            master = self.conn.master
                            if master is not None:
                                try:
                                    master.mav.command_long_send(
                                        master.target_system,
                                        master.target_component,
                                        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                        0,
                                        0,   # param1: 0=disarm
                                        21196,  # param2: magic_force_arm_disarm_value
                                        0, 0, 0, 0, 0,
                                    )
                                    logger.critical('✅ FAILSAFE — force DISARM enviado (param2=21196)')
                                except Exception as e:
                                    logger.critical('❌ FAILSAFE — error enviando DISARM: %s', e)
                            time.sleep(0.1)
                            continue

                # ── Convertir a PWM y enviar ─────────────────────────────
                ch_roll     = self._to_pwm(use_roll)
                ch_pitch    = self._to_pwm(use_pitch)
                ch_throttle = self._to_pwm_throttle(use_throttle)
                ch_yaw      = self._to_pwm(use_yaw)

                master = self.conn.master
                if master is not None:
                    try:
                        master.mav.rc_channels_override_send(
                            master.target_system,
                            master.target_component,
                            ch_roll,     # CH1 Roll
                            ch_pitch,    # CH2 Pitch
                            ch_throttle, # CH3 Throttle
                            ch_yaw,      # CH4 Yaw
                            0, 0, 0, 0   # CH5-8 sin usar
                        )
                        if self._send_failures > 0:
                            logger.info('RC override reconectado tras %d fallos', self._send_failures)
                        self._send_failures = 0
                    except Exception as e:
                        self._send_failures += 1
                        logger.warning('RC override error envío #%d: %s', self._send_failures, e)
                else:
                    self._send_failures += 1
                    if self._send_failures == 1:
                        logger.warning('RC override: master es None — píxhawk desconectado')
                    elif self._send_failures == 3:
                        logger.error('RC override: %d intentos fallidos — sin conexión con píxhawk', self._send_failures)
                    else:
                        logger.debug('RC override: master None (intento #%d)', self._send_failures)

                time.sleep(0.1)  # 10 Hz

            except Exception as e:
                self._send_failures += 1
                logger.error(f"RC override error en loop: {e}")
                time.sleep(0.5)

    def _release_control(self):
        """Libera el control RC (todos los canales a 0 = release)."""
        try:
            master = self.conn.master
            if master:
                master.mav.rc_channels_override_send(
                    master.target_system,
                    master.target_component,
                    0, 0, 0, 0, 0, 0, 0, 0
                )
            logger.info("Control RC liberado")
        except Exception as e:
            logger.error(f"Error liberando control RC: {e}")

    # ── Conversión PWM ─────────────────────────────────────────────────────────

    def _to_pwm(self, value: float) -> int:
        """Normalizado (-1.0 a 1.0) → PWM (1000-2000). Centro = 1500."""
        value = max(-1.0, min(1.0, float(value)))
        return int(max(self.PWM_MIN, min(self.PWM_MAX, self.PWM_CENTER + value * 500)))

    def _to_pwm_throttle(self, value: float) -> int:
        """Throttle normalizado (0.0 a 1.0) → PWM (1000-2000)."""
        value = max(0.0, min(1.0, float(value)))
        return int(max(self.PWM_MIN, min(self.PWM_MAX, self.PWM_MIN + value * 1000)))

    # ── API Pública ────────────────────────────────────────────────────────────

    def set_throttle(self, value: float):
        with self.lock:
            self.throttle = max(0.0, min(1.0, float(value)))

    def set_yaw(self, value: float):
        with self.lock:
            self.yaw = max(-1.0, min(1.0, float(value)))

    def set_pitch(self, value: float):
        with self.lock:
            self.pitch = max(-1.0, min(1.0, float(value)))

    def set_roll(self, value: float):
        with self.lock:
            self.roll = max(-1.0, min(1.0, float(value)))

    def on_disconnect(self):
        """
        Marca desconexión de UN cliente WebSocket.
        Solo activa failsafe si TODOS los clientes se desconectaron.
        """
        with self.lock:
            self._connected_clients = max(0, self._connected_clients - 1)
            if self._connected_clients > 0:
                logger.info('⏸ Cliente desconectado — %d cliente(s) activo(s), failsafe NO activado', self._connected_clients)
                return
            self._disconnected_at = time.time()
            self._disarmed_by_failsafe = False
            logger.warning('⏸ Sin clientes conectados — failsafe en %.0f s si no reconecta', self.DISARM_TIMEOUT)

    def on_reconnect(self):
        """
        Marca reconexión de UN cliente WebSocket.
        Cancela failsafe si estaba activo (al menos un cliente está vivo).
        """
        with self.lock:
            self._connected_clients += 1
            if self._disconnected_at is not None:
                self._disconnected_at = None
                self._disarmed_by_failsafe = False
                logger.info('🔁 Cliente reconectado — failsafe cancelado (%d activo(s))', self._connected_clients)
            else:
                logger.info('🔁 Cliente conectado (%d activo(s))', self._connected_clients)

    def set_controls(self, throttle=None, yaw=None, pitch=None, roll=None):
        """
        Establece múltiples controles normalizados a la vez.
        Todos los valores deben estar en rango normalizado (no PWM).
        También cancela failsafe si estaba activo.
        """
        with self.lock:
            if throttle is not None:
                self.throttle = max(0.0, min(1.0, float(throttle)))
            if yaw is not None:
                self.yaw = max(-1.0, min(1.0, float(yaw)))
            if pitch is not None:
                self.pitch = max(-1.0, min(1.0, float(pitch)))
            if roll is not None:
                self.roll = max(-1.0, min(1.0, float(roll)))
            if self._disconnected_at is not None:
                self._disconnected_at = None
                self._disarmed_by_failsafe = False
                logger.info('🔁 RC reconectado por set_controls — failsafe cancelado')

    def reset_controls(self):
        with self.lock:
            self.throttle = self.yaw = self.pitch = self.roll = 0.0
            self._failsafe_fired = False

    def set_autonomous(self, autonomous: bool):
        """Pausar/reanudar RC override durante operaciones autónomas (TAKEOFF, misión)."""
        with self.lock:
            self._autonomous = autonomous
            if autonomous:
                logger.info('🤖 RC override PAUSADO — modo autónomo activo')
            else:
                logger.info('🎮 RC override REANUDADO — modo manual')

    def set_armed(self, armed: bool):
        with self.lock:
            if armed:
                self._armed_at = time.time()
                self._failsafe_fired = False
                self._active = True
                logger.info('⏳ ARM — idle %.0f s activado (joystick bloqueado)', self.ARM_IDLE_DURATION)
            else:
                self._armed_at = None
                self.throttle = 0.0
                self.yaw = 0.0
                self.pitch = 0.0
                self.roll = 0.0
                self._failsafe_fired = False
                self._idle_logged = False
                self._active = False
                logger.info('⏹ DISARM — idle cancelado, RC reseteado, envío detenido')

    def is_in_idle(self) -> bool:
        with self.lock:
            if self._armed_at is None:
                return False
            return (time.time() - self._armed_at) < self.ARM_IDLE_DURATION

    def is_connected(self) -> bool:
        return self.conn is not None and self.conn.master is not None

    def get_current_values(self) -> dict:
        with self.lock:
            return {
                "throttle":     self.throttle,
                "yaw":          self.yaw,
                "pitch":        self.pitch,
                "roll":         self.roll,
                "throttle_pwm": self._to_pwm_throttle(self.throttle),
                "yaw_pwm":      self._to_pwm(self.yaw),
                "pitch_pwm":    self._to_pwm(self.pitch),
                "roll_pwm":     self._to_pwm(self.roll),
                "in_idle":      self._armed_at is not None and (time.time() - self._armed_at) < self.ARM_IDLE_DURATION,
                "idle_remaining": round(max(0, self.ARM_IDLE_DURATION - (time.time() - self._armed_at)), 1) if self._armed_at else 0,
                "connected_clients": self._connected_clients,
                "failsafe_active": self._disconnected_at is not None,
                "failsafe_remaining": round(max(0, self.DISARM_TIMEOUT - (time.time() - self._disconnected_at)), 1) if self._disconnected_at else None,
            }