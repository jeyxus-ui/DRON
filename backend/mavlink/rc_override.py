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

    IDLE_THROTTLE = 0.25    # 25% = ~1250 PWM (evita auto-disarm)
    ARM_IDLE_DURATION = 0.0  # sin idle — joystick responde inmediatamente
    JOYSTICK_DEADBAND = 0.05  # valores |v| < 0.05 se tratan como 0
    DISARM_TIMEOUT = 10.0    # segundos sin conexión → empezar a reducir
    RAMP_DOWN_DURATION = 5.0  # segundos para reducir throttle de actual → 0

    def __init__(self, mavlink_connection):
        self.conn    = mavlink_connection
        self.channels = [0] * 8
        self.running  = False
        self.thread   = None

        # Valores normalizados de joystick
        self.throttle = 0.0
        self.yaw      = 0.0
        self.pitch    = 0.0
        self.roll     = 0.0
        self._armed   = False
        # En GUIDED mode, liberamos todos los canales (65535) para que el
        # autopilot controle throttle via su controlador de posición.
        self._guided_mode = False

        self.lock = threading.Lock()
        self._send_failures = 0
        self._send_count = 0
        self._armed_at = None
        self._failsafe_fired = False
        self._disconnected_at: float | None = None
        self._disarmed_by_failsafe = False
        self._reconnect_callback = None  # opcional: se llama si failsafe había desarmado
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
                with self.lock:
                    use_throttle = self.throttle
                    use_yaw      = self.yaw
                    use_pitch    = self.pitch
                    use_roll     = self.roll
                    disconnected = self._disconnected_at
                    disarmed     = self._disarmed_by_failsafe

                    # ── Idle post-armado ──────────────────────────────────
                    if self._armed_at is not None:
                        idle_remaining = self.ARM_IDLE_DURATION - (time.time() - self._armed_at)
                        if idle_remaining > 0:
                            use_throttle = self.IDLE_THROTTLE
                            use_yaw = 0.0
                            use_pitch = 0.0
                            use_roll = 0.0
                            if int(idle_remaining) != int(idle_remaining + 0.1):
                                logger.info('⏳ IDLE ARM — %.0f s restantes (joystick bloqueado)', idle_remaining)
                        elif not self._failsafe_fired:
                            self._failsafe_fired = True
                            logger.info('✅ IDLE ARM — periodo de idle completado, joystick activo')

                    # ── Deadband (evita drift del joystick mvil) ───────
                    if abs(use_roll)  <= self.JOYSTICK_DEADBAND:  use_roll = 0.0
                    if abs(use_pitch) <= self.JOYSTICK_DEADBAND:  use_pitch = 0.0
                    if abs(use_yaw)   <= self.JOYSTICK_DEADBAND:  use_yaw = 0.0

                    # ── Sticks no forzados — el usuario controla roll/pitch/yaw ─

                # ── Ramp-down por desconexin (fuera del lock) ────────────
                now = time.time()
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
                            logger.critical('🚨 FAILSAFE — throttle 0, desarmando motores')
                            for _ in range(3):
                                master = getattr(self.conn, 'master', None)
                                if master is not None:
                                    try:
                                        master.mav.command_long_send(
                                            master.target_system,
                                            master.target_component,
                                            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                            0, 0, 21196, 0, 0, 0, 0, 0,
                                        )
                                        logger.critical('✅ FAILSAFE — comando DISARM enviado (force)')
                                        break
                                    except Exception as e:
                                        logger.critical('❌ FAILSAFE — error enviando DISARM: %s', e)
                                time.sleep(1.0)
                            continue

                # ── Convertir a PWM y enviar ─────────────────────────────
                # En GUIDED mode: liberar todos los canales (65535) para que
                # el autopilot controle throttle via su controlador de posición.
                # Los comandos de movimiento se envían como velocidades en este modo.
                with self.lock:
                    in_guided = self._guided_mode

                if in_guided:
                    ch_roll = ch_pitch = ch_throttle = ch_yaw = 65535
                else:
                    ch_roll     = self._to_pwm(use_roll)
                    ch_pitch    = self._to_pwm(use_pitch)
                    ch_throttle = self._to_pwm_throttle(use_throttle)
                    ch_yaw      = self._to_pwm(use_yaw)

                master = getattr(self.conn, 'master', None)
                if master is not None:
                    try:
                        with getattr(self.conn, '_lock', threading.Lock()):
                            master.mav.rc_channels_override_send(
                            master.target_system,
                            master.target_component,
                            ch_roll,     # CH1 Roll
                            ch_pitch,    # CH2 Pitch
                            ch_throttle, # CH3 Throttle
                            ch_yaw,      # CH4 Yaw
                            65535, 65535, 65535, 65535   # CH5-8 sin usar (65535=no cambio)
                        )
                        if self._send_failures > 0:
                            logger.info('RC override reconectado tras %d fallos', self._send_failures)
                        self._send_failures = 0
                        self._send_count += 1
                        if self._send_count % 50 == 0:
                            logger.info(
                                'RC override OK (%d sent) — armed=%s throttle=%.2f(%d) roll=%d pitch=%d yaw=%d',
                                self._send_count, self._armed,
                                use_throttle, ch_throttle, ch_roll, ch_pitch, ch_yaw
                            )
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

    def _apply_deadband(self, value: float) -> float:
        return 0.0 if abs(value) < self.JOYSTICK_DEADBAND else float(value)

    def set_throttle(self, value: float):
        with self.lock:
            self.throttle = max(0.0, min(1.0, float(value)))

    def set_yaw(self, value: float):
        with self.lock:
            self.yaw = self._apply_deadband(value)

    def set_pitch(self, value: float):
        with self.lock:
            self.pitch = self._apply_deadband(value)

    def set_roll(self, value: float):
        with self.lock:
            self.roll = self._apply_deadband(value)

    def on_disconnect(self):
        """
        Marca desconexión del cliente — NO resetea controles.
        El dron mantiene la última velocidad/actitud.
        Si no hay reconexión en DISARM_TIMEOUT segundos,
        el _send_loop desarma automáticamente.
        """
        with self.lock:
            self._disconnected_at = time.time()
            self._disarmed_by_failsafe = False
            logger.warning('⏸ RC desconectado — failsafe en %.0f s si no reconecta', self.DISARM_TIMEOUT)

    def on_reconnect(self):
        """
        Cancela el failsafe de desconexión.
        Si el failsafe ya había desarmado el Pixhawk, dispara re-arm automático.
        """
        was_disarmed = False
        with self.lock:
            was_disarmed = self._disarmed_by_failsafe
            self._disconnected_at = None
            self._disarmed_by_failsafe = False
            logger.info('🔁 RC reconectado — failsafe cancelado')
        if was_disarmed and self._reconnect_callback:
            try:
                logger.warning('🔁 FAILSAFE HABÍA DESARMADO — re-armando motores...')
                self._reconnect_callback()
            except Exception as e:
                logger.error('Error en callback de re-arm: %s', e)

    def set_controls(self, throttle=None, yaw=None, pitch=None, roll=None):
        """
        Establece múltiples controles normalizados a la vez.
        Todos los valores deben estar en rango normalizado (no PWM).
        """
        was_disarmed = False
        with self.lock:
            if throttle is not None:
                self.throttle = max(0.0, min(1.0, float(throttle)))
            if yaw is not None:
                self.yaw = self._apply_deadband(yaw)
            if pitch is not None:
                self.pitch = self._apply_deadband(pitch)
            if roll is not None:
                self.roll = self._apply_deadband(roll)
            # Cualquier set_controls implica cliente activo → cancela failsafe
            if self._disconnected_at is not None:
                was_disarmed = self._disarmed_by_failsafe
                self._disconnected_at = None
                self._disarmed_by_failsafe = False
                logger.info('🔁 RC reconectado por set_controls — failsafe cancelado')
        if was_disarmed and self._reconnect_callback:
            try:
                logger.warning('🔁 FAILSAFE HABÍA DESARMADO — re-armando motores...')
                self._reconnect_callback()
            except Exception as e:
                logger.error('Error en callback de re-arm: %s', e)

    def reset_controls(self):
        with self.lock:
            self.throttle = self.yaw = self.pitch = self.roll = 0.0

    def set_guided_mode(self, is_guided: bool):
        """Indica al RC controller si el drone está en GUIDED mode.
        En GUIDED: libera todos los canales RC para que el autopilot controle throttle."""
        with self.lock:
            if is_guided != self._guided_mode:
                self._guided_mode = is_guided
                logger.info('RC override: modo GUIDED=%s — canales %s',
                           is_guided, 'LIBERADOS (65535)' if is_guided else 'ACTIVOS')

    def set_armed(self, armed: bool):
        with self.lock:
            self._armed = armed
            if armed:
                self._armed_at = time.time()
                self._failsafe_fired = False
                logger.info('⏳ ARM — idle throttle %.0f%%', self.IDLE_THROTTLE * 100)
            else:
                self._armed_at = None
                self.throttle = 0.0
                self.roll = self.pitch = self.yaw = 0.0
                self._failsafe_fired = False
                logger.info('⏹ DISARM — controles reseteados a 0')

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
                "in_idle":      self._armed and not self._failsafe_fired,
                "idle_remaining": 0,
            }