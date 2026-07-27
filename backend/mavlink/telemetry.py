# backend/mavlink/telemetry.py
"""
Lectura y procesamiento de telemetría
"""

from pymavlink import mavutil
import logging
import threading
import time
import math

logger = logging.getLogger(__name__)


class DroneTelemetry:
    """Clase para leer y almacenar telemetría del dron"""
    
    def __init__(self, connection, persist_interval: float = 5.0):
        self.conn = connection
        
        self.data = {
            'altitude': 0.0,
            'speed': 0.0,
            'climb_rate': 0.0,
            'throttle': 0,
            'armed': False,
            'mode': 'UNKNOWN',
            'system_status': 0,
            'gps': {
                'lat': 0.0,
                'lon': 0.0,
                'alt': 0.0,
                'satellites': 0,
                'fix_type': 0,
                'hdop': 0.0
            },
            'battery': {
                'voltage': 0.0,
                'current': 0.0,
                'remaining': 0
            },
            'attitude': {
                'roll': 0.0,
                'pitch': 0.0,
                'yaw': 0.0
            },
            'home_position': {
                'lat': 0.0,
                'lon': 0.0,
                'alt': 0.0
            }
        }
        
        self._running = False
        self._thread = None
        self._persist_interval = float(persist_interval) if persist_interval else 0
        self._persist_thread = None
        
        self.start()

        if self._persist_interval and self._persist_interval > 0:
            self._persist_thread = threading.Thread(target=self._persist_loop, daemon=True)
            self._persist_thread.start()

    # ============================================
    # STREAMS
    # ============================================

    def _request_streams(self):
        """Solicitar data streams al Pixhawk — espera conexión activa primero."""
        logger.info("⏳ Esperando conexión para solicitar streams...")

        for _ in range(40):  # hasta 20 segundos
            if self.conn.is_connected():
                break
            time.sleep(0.5)

        if not self.conn.is_connected():
            logger.warning("⚠️ No se pudo solicitar streams: sin conexión")
            return

        try:
            master = self.conn.master
            target_sys = master.target_system
            comps = [master.target_component] if master.target_component != 0 else [1, 0]
            STREAMS = [
                (mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_POSITION, 5),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 5),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA2, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA3, 1),
            ]
            for comp in comps:
                for stream_id, rate_hz in STREAMS:
                    master.mav.request_data_stream_send(
                        target_sys, comp, stream_id, rate_hz, 1,
                    )
            logger.info(f"✅ Streams solicitados al Pixhawk (comps={comps}, max=5 Hz)")
        except Exception as e:
            logger.error(f"❌ Error solicitando streams: {e}")

    # ============================================
    # PERSISTENCIA
    # ============================================

    def _persist_loop(self):
        """Guardar snapshot de telemetría en la BD periódicamente."""
        try:
            from backend.db.repository import save_telemetry
        except Exception as e:
            logger.warning(f"save_telemetry no disponible, persistencia desactivada: {e}")
            return

        while self._running:
            try:
                snapshot = {
                    'altitude': self.data.get('altitude'),
                    'speed': self.data.get('speed'),
                    'pitch': self.data.get('attitude', {}).get('pitch'),
                    'roll': self.data.get('attitude', {}).get('roll'),
                    'yaw': self.data.get('attitude', {}).get('yaw'),
                    'battery': self.data.get('battery', {}).get('voltage')
                }
                save_telemetry(snapshot)
            except Exception as e:
                logger.error(f"Error guardando telemetría: {e}")
            time.sleep(self._persist_interval)

    # ============================================
    # LIFECYCLE
    # ============================================

    def start(self):
        """Iniciar threads de lectura y solicitud de streams"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("📡 Thread de telemetría iniciado")

        # Solicitar streams en thread separado para no bloquear el arranque
        threading.Thread(target=self._request_streams, daemon=True).start()
    
    def stop(self):
        """Detener threads"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._persist_thread:
            self._persist_thread.join(timeout=2)
        logger.info("📡 Thread de telemetría detenido")

    # ============================================
    # LECTURA
    # ============================================

    def _read_loop(self):
        """Loop principal de lectura"""
        while self._running:
            try:
                if not self.conn.is_connected():
                    time.sleep(0.5)
                    continue

                # Pausar si otro hilo necesita acceso exclusivo (upload_mission, etc)
                if self.conn._pause_read.is_set():
                    time.sleep(0.01)
                    continue

                msg = self.conn.recv_match(blocking=False)
                
                if msg:
                    # Track ANY message received
                    self.conn.update_msg_time()
                    mtype = msg.get_type()
                    if mtype == "COMMAND_ACK":
                        print(f"[MAVLINK-DEBUG] COMMAND_ACK received: cmd={msg.command} result={msg.result}", flush=True)
                    elif mtype == "STATUSTEXT":
                        try:
                            text = msg.text.decode('utf-8', errors='replace') if isinstance(msg.text, bytes) else str(msg.text)
                        except Exception:
                            text = str(msg.text)
                        print(f"[MAVLINK-DEBUG] STATUSTEXT: {text}", flush=True)
                        if not self.conn._ekf_ready.is_set() and ("tilt alignment complete" in text or "yaw alignment complete" in text):
                            self.conn._ekf_ready.set()
                            logger.info("✅ EKF alignment detected: %s", text)
                    elif mtype == "EKF_STATUS_REPORT":
                        if not self.conn._ekf_ready.is_set():
                            flags = getattr(msg, 'flags', 0)
                            if flags & 0x07:
                                self.conn._ekf_ready.set()
                                logger.info("✅ EKF alignment detected from STATUS_REPORT (flags=0x%02x)", flags)
                    elif mtype not in ("VFR_HUD", "HEARTBEAT", "GPS_RAW_INT", "BATTERY_STATUS", "ATTITUDE", "LOCAL_POSITION_NED", "SYS_STATUS", "GLOBAL_POSITION_INT", "RAW_IMU"):
                        print(f"[MAVLINK-DEBUG] Other msg: {mtype}", flush=True)
                    # Guardar COMMAND_ACK para wait_ack
                    if mtype == "COMMAND_ACK":
                        with self.conn._ack_lock:
                            self.conn._pending_acks[msg.command] = msg
                            logger.info(f"COMMAND_ACK stored: cmd={msg.command} result={msg.result}")
                        self.conn.update_ack_time()
                    # Guardar mensajes de misión para upload_mission
                    elif mtype in ("MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"):
                        with self.conn._pending_msgs_lock:
                            self.conn._pending_msgs[mtype] = msg
                    self._process_message(msg)
                else:
                    # No message received — dormir un poco y seguir
                    pass
                
                time.sleep(0.01)  # 100 Hz
                
            except Exception as e:
                print(f"[READ_LOOP-ERROR] {type(e).__name__}: {e}", flush=True)
                logger.error("Error en read_loop: %s — marking connection dead", e, exc_info=True)
                self.conn.mark_dead(f"read_loop exception: {type(e).__name__}: {e}")
                time.sleep(1)
    
    def _process_message(self, msg):
        """Procesar mensaje MAVLink"""
        msg_type = msg.get_type()
        
        try:
            if msg_type == "VFR_HUD":
                self.data['altitude'] = round(msg.alt, 2)
                self.data['speed'] = round(msg.airspeed, 2)
                self.data['climb_rate'] = round(msg.climb, 2)
                self.data['throttle'] = msg.throttle
                logger.debug(f"VFR_HUD → alt={msg.alt} speed={msg.airspeed}")
            
            elif msg_type == "GPS_RAW_INT":
                hdop_raw = msg.eph
                self.data['gps'] = {
                    'lat': round(msg.lat / 1e7, 7),
                    'lon': round(msg.lon / 1e7, 7),
                    'alt': round(msg.alt / 1000.0, 2),
                    'satellites': msg.satellites_visible,
                    'fix_type': msg.fix_type,
                    'hdop': round(hdop_raw / 100.0, 2) if hdop_raw != 65535 else 0.0
    
    }

            elif msg_type == "BATTERY_STATUS":
                volts = msg.voltages[0]
                # 65535 = no data
                if volts != 65535:
                    self.data['battery'] = {
                        'voltage': round(volts / 1000.0, 2),
                        'current': round(msg.current_battery / 100.0, 2),
                        'remaining': msg.battery_remaining
                    }

            elif msg_type == "SYS_STATUS":
                # Fallback de batería si BATTERY_STATUS no llega
                if self.data['battery']['voltage'] == 0.0:
                    v = msg.voltage_battery
                    if v and v != 65535:
                        self.data['battery']['voltage'] = round(v / 1000.0, 2)
                        self.data['battery']['current'] = round(msg.current_battery / 100.0, 2)
                        self.data['battery']['remaining'] = msg.battery_remaining
            
            elif msg_type == "ATTITUDE":
                self.data['attitude'] = {
                    'roll': round(math.degrees(msg.roll), 2),
                    'pitch': round(math.degrees(msg.pitch), 2),
                    'yaw': round(math.degrees(msg.yaw), 2)
                }
            
            elif msg_type == "HEARTBEAT":
                self.conn.update_heartbeat()
                was_armed = self.data['armed']
                self.data['armed'] = bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
                # Notificar al RC controller si cambia el estado armado
                # SKIP si estamos en proceso de DISARM — no re-activar RC override
                disarming = getattr(self.conn, '_disarming', False)
                if was_armed != self.data['armed'] and hasattr(self.conn, '_rc_callback'):
                    if disarming and self.data['armed']:
                        pass
                    else:
                        try:
                            self.conn._rc_callback(self.data['armed'])
                        except Exception as e:
                            logger.error("Error en RC callback: %s", e)
                mode_str = mavutil.mode_string_v10(msg)
                # ArduPilot Copter mode numbers when mode_string_v10 returns raw format
                ARDU_COPTER_MODES = {
                    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO",
                    4: "GUIDED", 5: "LOITER", 6: "RTL", 7: "CIRCLE",
                    8: "POSHOLD", 9: "LAND", 10: "OF_LOITER", 11: "DRIFT",
                    12: "SPORT", 13: "FLIP", 14: "SIMPLE", 15: "AUTO_RTL",
                    16: "SMARTRTL", 17: "THROW", 18: "AVOID_ADSB", 19: "GUIDED_NOGPS",
                    20: "FLOWHOLD", 21: "FOLLOW", 22: "ZIGZAG", 23: "SYSTEMID",
                }
                if mode_str.startswith("Mode(") and hasattr(msg, 'custom_mode'):
                    mode_str = ARDU_COPTER_MODES.get(msg.custom_mode, mode_str)
                self.data['mode'] = mode_str
                self.data['system_status'] = msg.system_status
            
            elif msg_type == "HOME_POSITION":
                self.data['home_position'] = {
                    'lat': round(msg.latitude / 1e7, 7),
                    'lon': round(msg.longitude / 1e7, 7),
                    'alt': round(msg.altitude / 1000.0, 2)
                }
        
        except Exception as e:
            logger.error(f"Error procesando {msg_type}: {e}")

    # ============================================
    # GETTERS
    # ============================================
    
    def get_all(self):
        return {
            "connected": self.conn.connected,
            **self.data
        }
    
    def get_status(self):
        return {
            "connected": self.conn.connected,
            "armed": self.data['armed'],
            "mode": self.data['mode'],
            "system_status": self.data['system_status']
        }
    
    def get_battery(self):
        battery = self.data['battery']
        current = battery['current']
        remaining_percent = battery['remaining']
        
        if current > 0:
            battery_capacity = 5000  # mAh — ajusta según tu batería
            remaining_mah = (remaining_percent / 100) * battery_capacity
            time_remaining_min = (remaining_mah / (current * 1000)) * 60
        else:
            time_remaining_min = 0
        
        return {
            **battery,
            "time_remaining_minutes": round(time_remaining_min, 1)
        }
    
    def get_gps(self):
        return self.data['gps']
    
    def get_attitude(self):
        return self.data['attitude']

    def get_velocity(self):
        return {
            "ground_speed": self.data.get("speed", 0.0),
            "vertical_speed": self.data.get("climb_rate", 0.0),
        }
    
    def get_position(self):
        return {
            "gps": self.data['gps'],
            "altitude": self.data['altitude'],
            "attitude": self.data['attitude']
        }

    # ============================================
    # PRE-FLIGHT CHECKS
    # ============================================
    
    def preflight_checks(self):
        checks = {
            "gps_fix": False,
            "battery_ok": False,
            "ekf_ok": False,
            "home_set": False,
            "sensors_ok": False
        }
        
        gps = self.data['gps']
        if gps['fix_type'] >= 3 and gps['satellites'] >= 6:
            checks["gps_fix"] = True
        
        battery = self.data['battery']
        if battery['remaining'] > 30:
            checks["battery_ok"] = True
        
        ekf = self.conn.recv_match(msg_type='EKF_STATUS_REPORT', blocking=True, timeout=2)
        if ekf and (ekf.flags & 0x01):
            checks["ekf_ok"] = True
        
        if self.data['home_position']['lat'] != 0:
            checks["home_set"] = True
        
        sys_status = self.conn.recv_match(msg_type='SYS_STATUS', blocking=True, timeout=2)
        if sys_status:
            sensors_ok = (
                sys_status.onboard_control_sensors_health &
                sys_status.onboard_control_sensors_enabled
            ) == sys_status.onboard_control_sensors_enabled
            checks["sensors_ok"] = sensors_ok
        
        return checks