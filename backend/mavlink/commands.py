# backend/mavlink/commands.py
"""
Comandos de control del dron.

CORRECCIONES:
- set_velocity: self.master → self.conn.master
- reboot_autopilot: self.master → self.conn.master
- emergency_stop: get_current_mode usa conn correctamente
"""

from pymavlink import mavutil
import logging
import time

logger = logging.getLogger(__name__)


class DroneCommands:

    def __init__(self, connection):
        self.conn = connection
        self._nav_speed = None  # m/s, None = usar WPNAV_SPEED del Pixhawk
        self._disarming = False  # Flag: estamos en proceso de DISARM

    # ── Comandos básicos ───────────────────────────────────────────────────────

    def _get_prearm_reason(self) -> str:
        """Devuelve los últimos mensajes PreArm de ArduPilot como string de diagnóstico."""
        try:
            with self.conn._prearm_lock:
                msgs = list(self.conn._prearm_msgs)
            if msgs:
                return ": " + " | ".join(msgs)
        except Exception:
            pass
        return ""

    def _is_armed(self) -> bool:
        """Verifica si el dron está armado usando la cache de telemetry.
        NO lee del socket directamente para evitar competir con _read_loop."""
        try:
            telemetry_available = getattr(self, 'telemetry', None) and self.telemetry.data
            if telemetry_available:
                return self.telemetry.data.get('armed', False)
        except Exception:
            pass
        return False

    def _wait_ack_direct(self, command_id, timeout=5):
        """
        Espera ACK verificando _pending_acks (capturado por _read_loop).
        Cuando recibe IN_PROGRESS (result=4), extiende el deadline 15s adicionales.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.conn._ack_lock:
                if command_id in self.conn._pending_acks:
                    ack = self.conn._pending_acks.pop(command_id)
                    logger.info(f"ACK found: cmd={ack.command} result={ack.result}")
                    if ack.result == 0:
                        return True
                    if ack.result == 5:  # MAV_RESULT_IN_PROGRESS (spec: 5, no 4)
                        deadline = time.time() + 15
                    else:
                        # 1=TEMPORARILY_REJECTED 2=DENIED 3=UNSUPPORTED 4=FAILED
                        prearm = self._get_prearm_reason()
                        raise ConnectionError(f"ARM rechazado por Pixhawk (result={ack.result}){prearm}")
            time.sleep(0.05)
        return False

    def arm(self, force=True, max_attempts=3):
        logger.info("🔴 ARM — Armando motores...")
        if not self.conn or not self.conn.master:
            raise ConnectionError("No hay conexión con Pixhawk — verifica cable USB / puerto serie")

        current_mode = getattr(self.telemetry, 'data', {}).get('mode', 'UNKNOWN')
        if current_mode not in ("STABILIZE", "ACRO", "ALT_HOLD"):
            logger.info(f"Modo actual: {current_mode}, cambiando a STABILIZE para armar")
            try:
                self.set_mode("STABILIZE")
            except Exception as e:
                logger.warning(f"No se pudo cambiar a STABILIZE: {e}")

        # Limpiar mensajes PreArm anteriores antes de este intento
        with self.conn._prearm_lock:
            self.conn._prearm_msgs.clear()

        if force and not self.conn._ekf_ready.is_set():
            logger.info("⏳ Esperando EKF alignment antes de enviar ARM...")
            if self.conn._ekf_ready.wait(timeout=30):
                logger.info("✅ EKF alineado — procediendo a ARM")
                time.sleep(1)
            else:
                logger.warning("⚠️ EKF timeout (30s) — intentando ARM de todas formas")
                time.sleep(3)

        for attempt in range(max_attempts):
            logger.info("ARM intento %d/%d", attempt + 1, max_attempts)

            with self.conn._lock:
                master = self.conn.master
                master.mav.command_long_send(
                    master.target_system,
                    master.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, 1,
                    21196 if force else 0,
                    0, 0, 0, 0, 0,
                )

            if self._wait_ack_direct(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM):
                logger.info("✅ Motores armados (ACK intento %d)", attempt + 1)
                return True

            logger.warning("⚠️ ACK timeout intento %d — intentando recv_match directo...", attempt + 1)
            ack = self.conn.recv_match(msg_type="COMMAND_ACK", blocking=True, timeout=3)
            if ack and ack.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                if ack.result == 0:
                    logger.info("✅ Motores armados (recv_match directo)")
                    return True
                else:
                    raise ConnectionError(f"ARM rechazado: result={ack.result}")

            logger.warning("⚠️ Intento %d falló — verificando estado...", attempt + 1)
            deadline = time.time() + 5
            while time.time() < deadline:
                if self._is_armed():
                    logger.info("✅ Dron armado (confirmado por HEARTBEAT)")
                    return True
                time.sleep(0.2)

            if attempt < max_attempts - 1:
                time.sleep(2)

        prearm = self._get_prearm_reason()
        if prearm:
            raise ConnectionError(f"ARM rechazado por Pixhawk{prearm}. Verifica: safety switch, GPS fix, calibración de brújula/IMU")
        raise ConnectionError("Pixhawk no respondió al comando ARM tras %d intentos — verifica: safety switch físico, conexión MAVLink y heartbeat" % max_attempts)

    def _send_disarm_cmd(self, force=False):
        """Enviar comando DISARM via command_long. force=True usa param2=21196 (magic_force_arm_disarm_value en ArduPilot).
        Quien llama debe tener self.conn._lock."""
        master = self.conn.master
        if not master:
            raise ConnectionError("No hay conexión con Pixhawk")
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            0,   # param1: 0=disarm (1=arm)
            21196 if force else 0,  # param2: 21196=force (magic_force_arm_disarm_value)
            0, 0, 0, 0, 0,
        )

    def disarm(self, force=False):
        logger.info("🟢 DISARM — Desarmando motores (force=%s)...", force)
        if not self.conn or not self.conn.master:
            raise ConnectionError("No hay conexión con Pixhawk — verifica cable USB / puerto serie")
        self._disarming = True
        if self.conn:
            self.conn._disarming = True
        try:
            if hasattr(self.conn, '_rc_callback') and self.conn._rc_callback:
                self.conn._rc_callback(False)
                logger.info("RC override desactivado antes de DISARM")
            master = self.conn.master
            logger.info("Enviando throttle=0 PWM para permitir disarm...")
            for _ in range(10):
                master.mav.rc_channels_override_send(
                    master.target_system, master.target_component,
                    1500, 1500, 1000, 1500, 65535, 65535, 65535, 65535
                )
                time.sleep(0.1)
            time.sleep(0.5)
            logger.info("Enviando DISARM (param1=0, param2=%s)...", 21196 if force else 0)
            with self.conn._lock:
                self._send_disarm_cmd(force=force)

            if self._wait_ack_direct(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, timeout=5):
                logger.info("✅ Motores desarmados (ACK recibido)")
                return True

            logger.warning("⚠️ DISARM ACK timeout — reintentando (force=%s)...", force)
            for attempt in range(2):
                logger.info("DISARM reintento %d/2", attempt + 1)
                with self.conn._lock:
                    self._send_disarm_cmd(force=force)
                if self._wait_ack_direct(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, timeout=5):
                    logger.info("✅ Motores desarmados (ACK reintento)")
                    return True

            logger.warning("⚠️ DISARM ACK timeout — verificando estado via telemetry...")
            deadline = time.time() + 15
            while time.time() < deadline:
                if self.telemetry and self.telemetry.data:
                    is_armed = self.telemetry.data.get('armed', False)
                    logger.info("DISARM telemetry check: armed=%s", is_armed)
                    if not is_armed:
                        logger.info("✅ Dron desarmado (confirmado por telemetry)")
                        return True
                time.sleep(0.3)

            raise ConnectionError("Pixhawk no respondió al comando DISARM — verifica conexión MAVLink y heartbeat")
        finally:
            self._disarming = False
            if self.conn:
                self.conn._disarming = False

    def set_mode(self, mode_name, verify=True, max_attempts=3):
        logger.info(f"🔄 Cambiando a modo: {mode_name}")
        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            if mode_name not in master.mode_mapping():
                valid = list(master.mode_mapping().keys())
                raise ValueError(f"Modo inválido '{mode_name}'. Válidos: {valid}")
            mode_id = master.mode_mapping()[mode_name]
            master.set_mode(mode_id)

        if not verify:
            logger.info(f"✅ Modo enviado: {mode_name}")
            return True

        for attempt in range(max_attempts):
            time.sleep(1)
            current = self.get_current_mode()
            if current == mode_name:
                logger.info(f"✅ Modo cambiado a {mode_name}")
                return True
            logger.warning(f"⚠️ Modo aún {current}, reenviando ({attempt+1}/{max_attempts})...")
            with self.conn._lock:
                master = self.conn.master
                if master:
                    master.set_mode(mode_id)

        current = self.get_current_mode()
        if current == mode_name:
            return True
        logger.warning(f"⚠️ Modo no verificado (actual: {current}) — no se confirmó cambio a {mode_name}")
        return False

    def takeoff(self, altitude):
        logger.info(f"🚁 TAKEOFF — Despegando a {altitude}m")
        try:
            self.set_mode("GUIDED")
        except Exception as e:
            logger.warning(f"set_mode GUIDED: {e}")
        time.sleep(1)

        if not self._is_armed():
            try:
                if not self.arm():
                    raise Exception("Arm falló")
            except Exception as e:
                logger.error(f"Arm: {e}")
                raise Exception("No se pudo armar el dron")
            time.sleep(2)
        else:
            logger.info("Dron ya está armado")
            time.sleep(0.5)

        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            logger.info(f"Enviando MAV_CMD_NAV_TAKEOFF alt={altitude}")
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0, 0, 0, 0, 0, 0, 0, altitude,
            )

        if self._wait_ack_direct(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, timeout=30):
            logger.info(f"✅ Despegando a {altitude}m (ACK recibido)")
            return True

        logger.warning("⚠️ TAKEOFF ACK timeout — verificando subida via HEARTBEAT/telemetry...")
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.telemetry and self.telemetry.data:
                alt = self.telemetry.data.get('altitude', 0)
                if alt > 1.0:
                    logger.info(f"✅ TAKEOFF confirmado por telemetry (alt={alt:.1f}m)")
                    return True
            if self._is_armed():
                logger.info("Dron armado y TAKEOFF enviado — asumiendo éxito (SITL ACK lento)")
                return True
            time.sleep(0.3)

        logger.error("❌ TAKEOFF falló — no se detectó subida")
        return False

    def land(self):
        logger.info("🛬 LAND — Aterrizando...")
        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_LAND,
                0, 0, 0, 0, 0, 0, 0, 0,
            )

        if self._wait_ack_direct(mavutil.mavlink.MAV_CMD_NAV_LAND):
            logger.info("✅ Aterrizando")
            return True

        logger.warning("⚠️ LAND ACK timeout — verificando recv_match directo...")
        ack = self.conn.recv_match(msg_type="COMMAND_ACK", blocking=True, timeout=3)
        if ack and ack.command == mavutil.mavlink.MAV_CMD_NAV_LAND:
            if ack.result == 0:
                logger.info("✅ Aterrizando (recv_match directo)")
                return True

        logger.error("❌ Comando de aterrizaje rechazado")
        return False

    def rtl(self):
        logger.info("🏠 RTL — Return to Launch")
        return self.set_mode("RTL")

    def loiter(self):
        return self.set_mode("LOITER")

    # ── Velocidad de navegación ────────────────────────────────────────────────

    def set_nav_speed(self, speed_mps: float):
        """Establecer velocidad de navegación vía MAV_CMD_DO_CHANGE_SPEED."""
        logger.info(f"🐢 NAV SPEED — {speed_mps:.1f} m/s")
        self._nav_speed = speed_mps
        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
                0,
                1,           # speed type: ground speed
                speed_mps,
                -1,          # throttle: no change
                0,           # absolute
                0, 0, 0,
            )
        logger.info(f"✅ Velocidad de navegación → {speed_mps:.1f} m/s")

    # ── Navegación ─────────────────────────────────────────────────────────────

    def goto_position(self, lat, lon, alt):
        logger.info(f"📍 GOTO — ({lat:.6f}, {lon:.6f}) @ {alt}m")
        current_mode = self.get_current_mode()
        if current_mode != "GUIDED":
            self.set_mode("GUIDED")
            time.sleep(1)

        # Aplicar velocidad de navegación si está configurada
        if self._nav_speed is not None:
            try:
                self.set_nav_speed(self._nav_speed)
            except Exception as e:
                logger.warning(f"No se pudo aplicar velocidad de navegación: {e}")

        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            master.mav.set_position_target_global_int_send(
                0,
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                int(0b110111111000),
                int(lat * 1e7),
                int(lon * 1e7),
                alt,
                0, 0, 0,
                0, 0, 0,
                0, 0,
            )

        logger.info("✅ Waypoint enviado")
        return True

    def set_velocity(self, vx, vy, vz, yaw_rate=0):
        """
        Establecer velocidad del dron.
        CORRECCIÓN: antes usaba self.master (no existe en DroneCommands).
        """
        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            master.mav.set_position_target_local_ned_send(
                0,
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                int(0b0000111111000111),
                0, 0, 0,
                vx, vy, vz,
                0, 0, 0,
                0, yaw_rate,
            )

    # ── Emergencia ─────────────────────────────────────────────────────────────

    def emergency_stop(self):
        logger.warning("🚨 EMERGENCY STOP")
        try:
            self.rtl()
            time.sleep(1)
            if self.get_current_mode() == "RTL":
                return True

            logger.warning("RTL falló, intentando LAND...")
            self.land()
            time.sleep(1)
            if self.get_current_mode() == "LAND":
                return True

            logger.critical("🚨 LAND falló — DESARMANDO (puede causar caída)")
            return self.disarm(force=True)
        except Exception as e:
            logger.critical(f"Error en emergency stop: {e}")
            return False

    def kill_motors(self):
        """Detener motores inmediatamente (PELIGROSO)."""
        logger.critical("💀 MOTOR KILL — Desarmando forzado")
        return self.disarm(force=True)

    def test_motor(self, motor_id: int, throttle_pct: float = 10.0, duration_s: float = 1.5, even_if_armed: bool = False):
        """Test individual motor at given throttle percentage for given duration."""
        logger.info(f"🔧 MOTOR TEST — motor {motor_id} @ {throttle_pct}% for {duration_s}s (even_if_armed={even_if_armed})")
        throttle_type = 3 if even_if_armed else 1
        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
                0,
                motor_id,
                throttle_type,
                int(throttle_pct),
                int(duration_s),
                1,
                0,
                0,
            )
        time.sleep(duration_s + 0.5)
        logger.info(f"✅ Motor {motor_id} test complete")
        return True

    # ── Utilidades ─────────────────────────────────────────────────────────────

    def get_current_mode(self):
        try:
            if hasattr(self, 'telemetry') and self.telemetry and self.telemetry.data:
                mode = self.telemetry.data.get('mode')
                if mode and mode != 'UNKNOWN':
                    return mode
        except Exception:
            pass
        msg = self.conn.recv_match(msg_type="HEARTBEAT", blocking=True, timeout=2)
        if msg:
            return mavutil.mode_string_v10(msg)
        return None

    def reboot_autopilot(self):
        """
        Reiniciar autopiloto.
        CORRECCIÓN: antes usaba self.master (no existe). Ahora usa self.conn.master.
        """
        logger.warning("🔄 Reiniciando autopiloto...")
        with self.conn._lock:
            master = self.conn.master
            if not master:
                raise ConnectionError("No hay conexión con Pixhawk")
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
                0,
                1, 0, 0, 0, 0, 0, 0,  # 1 = reboot autopilot
            )
        # Desconectar después del reboot (el autopiloto se reiniciará)
        self.conn.disconnect()
        logger.info("✅ Comando de reboot enviado — conexión cerrada")