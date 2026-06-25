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
        self.rc.start()
        # Callback desde telemetría HEARTBEAT para detectar armado real
        self.conn._rc_callback = self.rc.set_armed
        logger.info("RC Override Controller iniciado")

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

    # Basic commands
    def arm(self, force=True):
        return self.cmd.arm(force=force)

    def disarm(self, force=False):
        return self.cmd.disarm(force=force)

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
        return st.get("armed", False) if isinstance(st, dict) else False

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
