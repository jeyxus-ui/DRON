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

    # ── Comandos básicos ───────────────────────────────────────────────────────

    def _is_armed(self) -> bool:
        """Verifica si el dron está armado desde telemetry o HEARTBEAT directo."""
        try:
            # 1. Cache de telemetry (rápido, sin bloqueo)
            telemetry_available = getattr(self, 'telemetry', None) and self.telemetry.data
            if telemetry_available:
                armed = self.telemetry.data.get('armed', False)
                if armed:
                    return True
                # Cache dice False — no confiamos ciegamente, verificamos con HEARTBEAT
                if self.conn and self.conn.is_connected():
                    msg = self.conn.recv_match_protected('HEARTBEAT', timeout=0.2)
                    if msg:
                        from pymavlink import mavutil as mu
                        actual = bool(msg.base_mode & mu.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                        if actual:
                            self.telemetry.data['armed'] = True
                            return True
                return False

            # 2. Sin cache — HEARTBEAT directo
            if self.conn and self.conn.is_connected():
                msg = self.conn.recv_match_protected('HEARTBEAT', timeout=0.2)
                if msg:
                    from pymavlink import mavutil as mu
                    return bool(msg.base_mode & mu.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        except Exception:
            pass
        return False

    def arm(self, force=True):
        logger.info("🔴 ARM — Armando motores...")
        if not self.conn or not self.conn.master:
            raise ConnectionError("No hay conexión con Pixhawk — verifica cable USB / puerto serie")
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

        if self.conn.wait_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM):
            logger.info("✅ Motores armados")
            return True
        raise ConnectionError("Pixhawk no respondió al comando ARM — verifica conexión MAVLink y heartbeat")

    def disarm(self, force=False):
        logger.info("🟢 DISARM — Desarmando motores...")
        if not self.conn or not self.conn.master:
            raise ConnectionError("No hay conexión con Pixhawk — verifica cable USB / puerto serie")
        with self.conn._lock:
            master = self.conn.master
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 0,
                21196 if force else 0,
                0, 0, 0, 0, 0,
            )

        if self.conn.wait_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM):
            logger.info("✅ Motores desarmados")
            return True
        raise ConnectionError("Pixhawk no respondió al comando DISARM — verifica conexión MAVLink y heartbeat")

    def set_mode(self, mode_name):
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

        time.sleep(0.5)
        logger.info(f"✅ Modo enviado: {mode_name}")
        return True

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

        if self.conn.wait_ack(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF):
            logger.info(f"✅ Despegando a {altitude}m")
            return True
        logger.error("❌ TAKEOFF wait_ack timeout")
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

        if self.conn.wait_ack(mavutil.mavlink.MAV_CMD_NAV_LAND):
            logger.info("✅ Aterrizando")
            return True
        logger.error("❌ Comando de aterrizaje rechazado")
        return False

    def rtl(self):
        logger.info("🏠 RTL — Return to Launch")
        return self.set_mode("RTL")

    def loiter(self):
        return self.set_mode("LOITER")

    # ── Navegación ─────────────────────────────────────────────────────────────

    def goto_position(self, lat, lon, alt):
        logger.info(f"📍 GOTO — ({lat:.6f}, {lon:.6f}) @ {alt}m")
        current_mode = self.get_current_mode()
        if current_mode != "GUIDED":
            self.set_mode("GUIDED")
            time.sleep(1)

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

    # ── Utilidades ─────────────────────────────────────────────────────────────

    def get_current_mode(self):
        """
        Obtener modo actual del dron.
        CORRECCIÓN: usa self.conn.recv_match que sí existe.
        """
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