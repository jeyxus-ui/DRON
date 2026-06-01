"""
Control RC Override para joysticks virtuales
Permite control manual del dron mediante comandos RC_CHANNELS_OVERRIDE

CORRECCIÓN: Este módulo espera valores NORMALIZADOS (-1.0 a 1.0).
El frontend NO debe pre-convertir a PWM — eso lo hace este módulo.
"""
import threading
import time
import logging

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

        self.lock = threading.Lock()
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
                    ch_roll     = self._to_pwm(self.roll)
                    ch_pitch    = self._to_pwm(self.pitch)
                    ch_throttle = self._to_pwm_throttle(self.throttle)
                    ch_yaw      = self._to_pwm(self.yaw)

                master = self.conn.master
                if master:
                    master.mav.rc_channels_override_send(
                        master.target_system,
                        master.target_component,
                        ch_roll,     # CH1 Roll
                        ch_pitch,    # CH2 Pitch
                        ch_throttle, # CH3 Throttle
                        ch_yaw,      # CH4 Yaw
                        0, 0, 0, 0   # CH5-8 sin usar
                    )

                time.sleep(0.1)  # 10 Hz

            except Exception as e:
                logger.error(f"Error enviando RC override: {e}")
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

    def set_controls(self, throttle=None, yaw=None, pitch=None, roll=None):
        """
        Establece múltiples controles normalizados a la vez.
        Todos los valores deben estar en rango normalizado (no PWM).
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

    def reset_controls(self):
        with self.lock:
            self.throttle = self.yaw = self.pitch = self.roll = 0.0

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
            }