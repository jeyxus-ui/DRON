"""
backend/mavlink/controller.py

Controlador de alto nivel que combina conexión, comandos y telemetría
Exponer los métodos que espera la API REST.
"""
from .rc_override import RCOverrideController
from .connection import MAVLinkConnection
from .commands import DroneCommands
from .telemetry import DroneTelemetry
from pymavlink import mavutil
import logging
import time

logger = logging.getLogger(__name__)


class MAVController:
    def __init__(self, device, baud):
        # Soporte de simulador local (device == 'SIM')
        if isinstance(device, str) and device.upper() == 'SIM':
            # Crear un controlador simulado ligero
            self._sim = _SimulatedController()
            self.conn = None
            self.cmd = None
            self.telemetry = None
            self.master = None

            # Proxy simple: reasignar métodos públicos a los del simulador
            self.get_telemetry = self._sim.get_telemetry
            self.get_status = self._sim.get_status
            self.get_battery = self._sim.get_battery
            self.get_gps = self._sim.get_gps
            self.preflight_checks = self._sim.preflight_checks
            self.arm = self._sim.arm
            self.disarm = self._sim.disarm
            self.set_mode = self._sim.set_mode
            self.takeoff = self._sim.takeoff
            self.land = self._sim.land
            self.rtl = self._sim.rtl
            self.goto_position = self._sim.goto_position
            self.set_param = self._sim.set_param
            self.get_param = self._sim.get_param
            self.upload_mission = self._sim.upload_mission
            self.start_mission = self._sim.start_mission
            self.clear_mission = self._sim.clear_mission
            self.get_flight_logs = self._sim.get_flight_logs
            self.is_connected = lambda: True
            self.is_armed = lambda: self._sim._state["armed"]
            self.get_mode = lambda: self._sim._state["mode"]
            self.get_system_status = lambda: 4
            self.return_to_launch = self._sim.rtl
            self.goto = lambda lat, lon, alt: self._sim.goto_position(lat, lon, alt)
            self.kill_motors = lambda: False

            return

        self.conn = MAVLinkConnection(device, baud)
        # Habilitar reconexión automática en segundo plano
        try:
            self.conn.start_auto_reconnect()
        except Exception:
            logger.debug("No se pudo iniciar auto-reconnect automáticamente")
        self.cmd = DroneCommands(self.conn)
        self.telemetry = DroneTelemetry(self.conn)
        self.cmd.telemetry = self.telemetry
        self.master = self.conn.master
        self.rc = RCOverrideController(self.conn)
        self.rc._reconnect_callback = self._rearm_after_failsafe
        self.rc.start()
        # Callback desde telemetría HEARTBEAT para detectar armado real
        self.conn._rc_callback = self.rc.set_armed
        logger.info("RC Override Controller iniciado")

    def setup_params(self):
        """Set critical Pixhawk parameters for safe operation."""
        params = {
            'DISARM_DELAY': 60,
        }
        for name, value in params.items():
            try:
                result = self.set_param(name, value)
                logger.info('✅ Param set %s = %s', name, result)
            except Exception as e:
                logger.warning('⚠️ Param set %s failed: %s', name, e)

        # Verificar configuración de RC override (joystick virtual)
        try:
            ov_time = self.read_param_safe('RC_OVERRIDE_TIME')
            if ov_time is not None and ov_time.get('value') == 0:
                logger.warning('⚠️ RC_OVERRIDE_TIME=0 — los overrides RC están DESACTIVADOS; el joystick no funcionará')
            opts = self.read_param_safe('RC_OPTIONS')
            if opts is not None and (int(opts.get('value', 0)) & 2):
                logger.warning('⚠️ RC_OPTIONS bit 1 activado — ArduPilot ignora los overrides RC del GCS')
        except Exception as e:
            logger.debug('No se pudo verificar configuración RC override: %s', e)

        try:
            fence_en = self.read_param_safe('FENCE_ENABLE')
            if fence_en is not None and fence_en.get('value') == 0:
                logger.info('ℹ️ FENCE_ENABLE=0 — el límite de altura solo se aplica en la app, no en el autopiloto')
        except Exception as e:
            logger.debug('No se pudo verificar FENCE_ENABLE: %s', e)

    def read_param_safe(self, name):
        """Read a Pixhawk parameter, return None on failure."""
        try:
            result = self.get_param(name)
            return result
        except Exception as e:
            logger.warning('⚠️ Could not read param %s: %s', name, e)
            return None

    def get_critical_params(self) -> dict:
        """Read and return critical diagnostic parameters."""
        critical = [
            'MOT_SPIN_ARM', 'MOT_SPIN_MIN', 'MOT_SPIN_MAX',
            'MOT_PWM_MIN', 'MOT_PWM_MAX',
            'DISARM_DELAY', 'ARMING_CHECK',
            'RC_OVERRIDE_TIME', 'RC_OPTIONS', 'BRD_SAFETY_DEFLT',
            'BATT_MONITOR', 'BATT_N_CELLS', 'BATT_LOW_VOLT', 'BATT_FS_LOW_ACT',
            'FENCE_ENABLE', 'FENCE_ALT_MAX',
        ]
        result = {}
        for name in critical:
            val = self.read_param_safe(name)
            if val is not None:
                result[name] = val
        return result

    def get_servo_output_raw(self) -> dict:
        """Read SERVO_OUTPUT_RAW from Pixhawk (actual PWM output)."""
        result = {}
        master = getattr(self.conn, 'master', None)
        if not master:
            return {"error": "no connection"}
        try:
            master.mav.command_long_send(
                master.target_system, master.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                0, mavutil.mavlink.MAVLINK_MSG_ID_SERVO_OUTPUT_RAW, 200_000,
                0, 0, 0, 0, 0,
            )
            msg = master.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=2)
            if msg:
                for i in range(1, 9):
                    pwm = getattr(msg, f'servo{i}_raw', 0)
                    result[f'ch{i}'] = pwm
                result['port'] = msg.port
            else:
                result["error"] = "timeout waiting for SERVO_OUTPUT_RAW"
        except Exception as e:
            result["error"] = str(e)
        return result

    def get_rc_channels(self) -> dict:
        """Read RC_CHANNELS from Pixhawk (what it sees as input)."""
        result = {}
        master = getattr(self.conn, 'master', None)
        if not master:
            return {"error": "no connection"}
        try:
            master.mav.command_long_send(
                master.target_system, master.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                0, mavutil.mavlink.MAVLINK_MSG_ID_RC_CHANNELS, 200_000,
                0, 0, 0, 0, 0,
            )
            msg = master.recv_match(type='RC_CHANNELS', blocking=True, timeout=2)
            if msg:
                for i in range(1, 19):
                    chan = getattr(msg, f'chan{i}_raw', 0)
                    if chan != 65535 and chan != 0:
                        result[f'ch{i}'] = chan
                result['rssi'] = getattr(msg, 'rssi', 0)
            else:
                result["error"] = "timeout waiting for RC_CHANNELS"
        except Exception as e:
            result["error"] = str(e)
        return result

    # Telemetry / status wrappers
    def get_telemetry(self):
        return self.telemetry.get_all()

    def get_status(self):
        return self.telemetry.get_status()

    def get_battery(self):
        return self.telemetry.get_battery()

    def get_gps(self):
        return self.telemetry.get_gps()

    def preflight_checks(self):
        return self.telemetry.preflight_checks()

    # ── Re-arm automático tras failsafe ───────────────────────────────────

    def _rearm_after_failsafe(self):
        """Dispara re-arm en un hilo separado para no bloquear al caller."""
        import threading
        t = threading.Thread(target=self._do_rearm, daemon=True)
        t.start()

    def _do_rearm(self):
        """Re-arma el Pixhawk tras un failsafe disarm."""
        logger.warning('🚁 Re-armando tras failsafe...')
        time.sleep(0.5)
        try:
            result = self.cmd.arm(force=True)
            if result:
                logger.warning('✅ Re-arm exitoso tras failsafe')
                self.rc.set_armed(True)
            else:
                logger.error('❌ Re-arm falló tras failsafe')
        except Exception as e:
            logger.error('❌ Error en re-arm tras failsafe: %s', e)

    # Basic commands
    def arm(self, force=True):
        self.rc.set_armed(True)
        try:
            result = self.cmd.arm(force=force)
            if not result and not self.is_armed():
                self.rc.set_armed(False)
            return result
        except Exception:
            self.rc.set_armed(False)
            raise

    def disarm(self, force=False):
        # Detener RC Override primero (throttle=0) para que Pixhawk acepte disarm
        self.rc.set_armed(False)
        time.sleep(0.5)
        try:
            result = self.cmd.disarm(force=force)
            if result or not self.is_armed():
                self.rc.set_armed(False)
            return result
        except Exception:
            if not self.is_armed():
                self.rc.set_armed(False)
            raise

    def set_mode(self, mode):
        return self.cmd.set_mode(mode)

    def takeoff(self, altitude):
        return self.cmd.takeoff(altitude)

    def land(self):
        return self.cmd.land()

    def rtl(self):
        return self.cmd.rtl()

    def goto_position(self, lat, lon, alt):
        return self.cmd.goto_position(lat, lon, alt)

    # API esperada por REST/WebSocket
    def is_connected(self):
        return self.conn is not None and self.conn.is_connected()

    def is_armed(self):
        st = self.get_status()
        armed = st.get("armed", False) if isinstance(st, dict) else False
        if armed and self.conn and not self.conn.is_heartbeat_healthy():
            return False
        return armed

    def get_mode(self):
        st = self.get_status()
        return st.get("mode", "UNKNOWN") if isinstance(st, dict) else "UNKNOWN"

    def get_system_status(self):
        st = self.get_status()
        return st.get("system_status", 0) if isinstance(st, dict) else 0

    def return_to_launch(self):
        return self.rtl()

    def goto(self, lat, lon, alt):
        return self.goto_position(lat, lon, alt)

    def kill_motors(self):
        """Emergencia: detener motores. Stub si no está en commands."""
        try:
            if self.cmd and hasattr(self.cmd, "kill_motors"):
                return self.cmd.kill_motors()
            logger.warning("kill_motors no implementado")
            return False
        except Exception as e:
            logger.error("kill_motors: %s", e)
            return False

    def set_param(self, name, value):
        """Establecer un parámetro y esperar su confirmación"""
        try:
            self.master.mav.param_set_send(
                self.master.target_system,
                self.master.target_component,
                name.encode('utf-8'),
                float(value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32
            )

            # Esperar PARAM_VALUE con el nombre esperado
            start = time.time()
            while time.time() - start < 5:
                msg = self.master.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
                if not msg:
                    continue
                try:
                    pid = msg.param_id.decode('utf-8').strip('\x00')
                except Exception:
                    pid = str(msg.param_id)
                if pid == name:
                    return msg.param_value
            raise TimeoutError("No se confirmó el parámetro")
        except Exception as e:
            logger.error(f"Error setting param {name}: {e}")
            raise

    def get_param(self, name):
        try:
            self.master.mav.param_request_read_send(
                self.master.target_system,
                self.master.target_component,
                name.encode('utf-8'),
                -1
            )

            msg = self.master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
            if not msg:
                raise TimeoutError("No se recibió PARAM_VALUE")

            try:
                pid = msg.param_id.decode('utf-8').strip('\x00')
            except Exception:
                pid = str(msg.param_id)

            return {
                'param_id': pid,
                'value': msg.param_value,
                'type': msg.param_type
            }
        except Exception as e:
            logger.error(f"Error getting param {name}: {e}")
            raise

    # Missions (simplified implementation)
    def upload_mission(self, waypoints):
        """Subir una misión simple basada en waypoints [{lat,lon,alt}, ...]"""
        if not waypoints:
            raise ValueError("No waypoints provided")

        # Pausar _read_loop para evitar race condition
        with self.conn.pause_read():
            return self._do_upload_mission(waypoints)

    def _do_upload_mission(self, waypoints):
        try:
            count = len(waypoints)
            self.master.mav.mission_count_send(
                self.master.target_system,
                self.master.target_component,
                count
            )

            start_time = time.time()

            while True:
                # Esperar petición de misión (usando protected para evitar race con _read_loop)
                msg = self.conn.recv_match_protected('MISSION_REQUEST_INT', timeout=5)
                if not msg:
                    if time.time() - start_time > 10:
                        raise TimeoutError("Timeout waiting for MISSION_REQUEST_INT")
                    continue

                req_seq = msg.seq
                if req_seq < 0 or req_seq >= count:
                    logger.warning(f"Received invalid mission request seq={req_seq}")
                    continue

                wp = waypoints[req_seq]
                lat = int(wp['lat'] * 1e7)
                lon = int(wp['lon'] * 1e7)
                alt = float(wp.get('alt', 10.0))

                # Enviar MISSION_ITEM_INT
                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    req_seq,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0, 1, 0, 0, 0, 0,
                    lat, lon, alt
                )

                if req_seq == count - 1:
                    # Esperar ACK (protected contra race con _read_loop)
                    ack = self.conn.recv_match_protected('MISSION_ACK', timeout=5)
                    if ack:
                        return True
                    else:
                        raise TimeoutError("No se recibió MISSION_ACK")

        except Exception as e:
            logger.error(f"Error uploading mission: {e}")
            raise

    def start_mission(self):
        with self.conn.pause_read():
            return self._do_start_mission()

    def _do_start_mission(self):
        try:
            # Establecer índice de misión en 0 y cambiar a AUTO
            self.master.mav.mission_set_current_send(
                self.master.target_system,
                self.master.target_component,
                0
            )
            time.sleep(0.5)
            self.set_mode('AUTO')
            return True
        except Exception as e:
            logger.error(f"Error starting mission: {e}")
            raise

    def clear_mission(self):
        try:
            self.master.mav.mission_clear_all_send(
                self.master.target_system,
                self.master.target_component
            )
            # Esperar ACK opcional
            return True
        except Exception as e:
            logger.error(f"Error clearing mission: {e}")
            raise

    def get_flight_logs(self):
        # Implementación mínima: muchos autopilotos requieren descargar archivos de logs.
        # Por ahora devolvemos lista vacía para evitar operaciones largas en tiempo real.
        return []


class _SimulatedController:
    """Controlador simulado para pruebas locales sin hardware.

    Exponer la misma API pública que `MAVController`.
    """
    def __init__(self):
        import threading, time

        self._state = {
            'armed': False,
            'mode': 'STANDBY',
            'altitude': 0.0,
            'speed': 0.0,
            'climb_rate': 0.0,
            'throttle': 0,
            'gps': {'lat': -34.6037, 'lon': -58.3816, 'alt': 25.0, 'satellites': 10, 'fix_type': 3, 'hdop': 0.8},
            'battery': {'voltage': 12.6, 'current': 0.0, 'remaining': 100},
            'attitude': {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0},
            'velocity': {'ground_speed': 0.0, 'vertical_speed': 0.0},
            'home_position': {'lat': -34.6037, 'lon': -58.3816, 'alt': 25.0},
        }

        self._params = {}
        self._missions = []
        self._running = True

        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()

    def _tick_loop(self):
        import time, math
        while self._running:
            # Simular pequeños cambios
            if self._state['armed'] and self._state['mode'] == 'GUIDED' and self._state['altitude'] < 10.0:
                self._state['altitude'] += 0.1
                self._state['climb_rate'] = 0.1
            else:
                self._state['climb_rate'] = 0.0

            # Simular descarga de batería lenta
            if self._state['armed']:
                self._state['battery']['remaining'] = max(0, self._state['battery']['remaining'] - 0.01)

            time.sleep(0.1)

    # Telemetry / status
    def get_telemetry(self):
        return {'connected': True, **self._state}

    def get_status(self):
        return {'connected': True, 'armed': self._state['armed'], 'mode': self._state['mode'], 'system_status': 4}

    def get_battery(self):
        b = self._state['battery'].copy()
        b['time_remaining_minutes'] = 999
        return b

    def get_gps(self):
        return self._state['gps']

    def get_attitude(self):
        return self._state.get('attitude', {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0})

    def get_velocity(self):
        return self._state.get('velocity', {'ground_speed': 0.0, 'vertical_speed': 0.0})

    def preflight_checks(self):
        checks = {
            'gps_fix': True,
            'battery_ok': self._state['battery']['remaining'] > 30,
            'ekf_ok': True,
            'home_set': True,
            'sensors_ok': True
        }
        return checks

    # Commands
    def arm(self, force=True):
        self._state['armed'] = True
        return True

    def disarm(self, force=False):
        self._state['armed'] = False
        return True

    def set_mode(self, mode):
        self._state['mode'] = mode
        return True

    def takeoff(self, altitude):
        # Simular armar y subir
        self.set_mode('GUIDED')
        self.arm()
        self._state['altitude'] = float(altitude)
        return True

    def land(self):
        self._state['mode'] = 'LAND'
        self._state['altitude'] = 0.0
        return True

    def rtl(self):
        self._state['mode'] = 'RTL'
        return True

    def goto_position(self, lat, lon, alt):
        self._state['gps']['lat'] = float(lat)
        self._state['gps']['lon'] = float(lon)
        self._state['altitude'] = float(alt)
        return True

    def set_param(self, name, value):
        self._params[name] = float(value)
        return self._params[name]

    def get_param(self, name):
        return {'param_id': name, 'value': self._params.get(name, 0), 'type': 9}

    def upload_mission(self, waypoints):
        self._missions = list(waypoints)
        return True

    def start_mission(self):
        if not self._missions:
            raise ValueError('No mission uploaded')
        self._state['mode'] = 'AUTO'
        return True

    def clear_mission(self):
        self._missions = []
        return True

    def get_flight_logs(self):
        return []

    def get_critical_params(self) -> dict:
        return {'__mode__': 'SIM', '__params__': list(self._params.keys())}

    def test_motor(self, motor_id: int, throttle_pct: float = 10.0,
                   duration_s: float = 1.5, even_if_armed: bool = False) -> bool:
        logger.info(f"🔧 SIM MOTOR TEST — motor {motor_id} @ {throttle_pct}% for {duration_s}s")
        time.sleep(min(duration_s, 0.5))
        return True

    def get_servo_output_raw(self) -> dict:
        return {"sim": True, "ch1": 1500, "ch2": 1500, "ch3": 1500, "ch4": 1500}

    def get_rc_channels(self) -> dict:
        return {"sim": True, "ch3": 1500, "rssi": 255}
