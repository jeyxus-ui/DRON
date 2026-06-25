#!/usr/bin/env python3
"""
Puente entre sensores/MAVLink locales y el backend vía HTTP POST.

Lee MAVLink del Pixhawk (USB/UART), MTF01 (I2C) y YDLIDAR (serial),
y envía todo al endpoint POST /api/sensors del backend cada ~100ms.
"""
import logging
import os
import sys
import threading
import time
import json
from datetime import datetime

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
except ImportError:
    from urllib2 import Request, urlopen, URLError

logger = logging.getLogger(__name__)

# Intentar importar sensores del backend (mismo repo)
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

BACKEND_URL = os.getenv('BACKEND_URL', 'http://127.0.0.1:8000')
SENSOR_INTERVAL = float(os.getenv('SENSOR_INTERVAL', '0.1'))  # 10 Hz
MAVLINK_DEVICE = os.getenv('MAVLINK_DEVICE', '/dev/ttyUSB0')
MAVLINK_BAUD = int(os.getenv('MAVLINK_BAUD', '57600'))


class DroneBridge:
    """Puente que lee hardware y envía datos al backend."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        self._mav = None
        self._mtf01 = None
        self._lidar = None

        self._last_sensor_data = {}
        self._last_mavlink_data = {}
        self._last_send = 0.0
        self._consecutive_errors = 0

    def start(self) -> bool:
        self._running = True
        self._init_hardware()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info('[BRIDGE] Iniciado — POST a %s cada %.1fs', BACKEND_URL, SENSOR_INTERVAL)
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._close_hardware()
        logger.info('[BRIDGE] Detenido')

    # ── Inicialización de hardware ──────────────────────────────────────────

    def _init_hardware(self):
        self._init_mavlink()
        self._init_sensors()

    def _init_mavlink(self):
        try:
            from connection import MAVLinkConnection
            self._mav = MAVLinkConnection(MAVLINK_DEVICE, MAVLINK_BAUD)
            if self._mav.is_connected():
                self._mav.start_telemetry_loop(interval=0.05)
                logger.info('[BRIDGE] MAVLink conectado: %s @ %s', MAVLINK_DEVICE, MAVLINK_BAUD)
            else:
                logger.warning('[BRIDGE] MAVLink no conectado')
        except Exception as e:
            logger.warning('[BRIDGE] Error MAVLink: %s', e)
            self._mav = None

    def _init_sensors(self):
        # MTF01
        try:
            from backend.sensors.mtf01 import MTF01Sensor
            self._mtf01 = MTF01Sensor(
                sim_mode=os.getenv('SIM_MODE', '0') == '1',
                i2c_bus=int(os.getenv('I2C_BUS', '1')),
            )
            if self._mtf01.start():
                logger.info('[BRIDGE] MTF01 iniciado')
            else:
                logger.warning('[BRIDGE] MTF01 no pudo iniciarse')
        except Exception as e:
            logger.warning('[BRIDGE] Error MTF01: %s', e)
            self._mtf01 = None

        # YDLIDAR
        try:
            from backend.sensors.ydlidar_x4 import YDLidarX4
            self._lidar = YDLidarX4(
                sim_mode=os.getenv('SIM_MODE', '0') == '1',
                port=os.getenv('LIDAR_PORT', '/dev/ttyUSB1'),
            )
            if self._lidar.start():
                logger.info('[BRIDGE] YDLIDAR iniciado')
            else:
                logger.warning('[BRIDGE] YDLIDAR no pudo iniciarse')
        except Exception as e:
            logger.warning('[BRIDGE] Error YDLIDAR: %s', e)
            self._lidar = None

    def _close_hardware(self):
        if self._mav:
            try:
                self._mav.stop_telemetry_loop()
                self._mav.disconnect()
            except Exception:
                pass
            self._mav = None
        if self._mtf01:
            try:
                self._mtf01.stop()
            except Exception:
                pass
            self._mtf01 = None
        if self._lidar:
            try:
                self._lidar.stop()
            except Exception:
                pass
            self._lidar = None

    # ── Loop principal ──────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                self._read_mavlink()
                self._read_sensors()
                self._send_to_backend()
            except Exception as e:
                logger.error('[BRIDGE] Error en loop: %s', e)
            time.sleep(SENSOR_INTERVAL)

    def _read_mavlink(self):
        if not self._mav or not self._mav.is_connected():
            return
        try:
            hb = self._mav.recv_match('HEARTBEAT', blocking=False)
            if hb:
                armed = bool(hb.base_mode & 0x80)
                mode = self._mav.master.mode_mapping() is not None and \
                       next((k for k, v in (self._mav.master.mode_mapping() or {}).items()
                             if v == hb.custom_mode), str(hb.custom_mode))
                with self._lock:
                    self._last_mavlink_data.update({
                        'armed': armed,
                        'mode': mode if isinstance(mode, str) else str(hb.custom_mode),
                    })

            vfr = self._mav.recv_match('VFR_HUD', blocking=False)
            if vfr:
                with self._lock:
                    self._last_mavlink_data.update({
                        'altitude': vfr.alt,
                        'ground_speed': vfr.groundspeed,
                        'vertical_speed': vfr.climb,
                    })

            gps = self._mav.recv_match('GPS_RAW_INT', blocking=False)
            if gps:
                with self._lock:
                    self._last_mavlink_data.update({
                        'latitude': gps.lat / 1e7,
                        'longitude': gps.lon / 1e7,
                        'altitude': gps.alt / 1000.0 if gps.alt < 100000 else self._last_mavlink_data.get('altitude'),
                        'satellites': gps.satellites_visible,
                        'hdop': gps.eph / 100.0 if gps.eph < 10000 else 99.9,
                    })

            bat = self._mav.recv_match('BATTERY_STATUS', blocking=False)
            if bat:
                voltage = bat.voltages[0] / 1000.0 if bat.voltages else 0
                with self._lock:
                    self._last_mavlink_data.update({
                        'battery_voltage': round(voltage, 2),
                        'battery_remaining': bat.battery_remaining,
                    })
        except Exception as e:
            logger.debug('[BRIDGE] Error leyendo MAVLink: %s', e)

    def _read_sensors(self):
        sensor_data = {}
        if self._mtf01 and self._mtf01.is_running:
            try:
                reading = self._mtf01.read()
                sensor_data['mtf01'] = {
                    'distance_m': reading.distance_m if reading.valid else None,
                    'valid': reading.valid,
                }
            except Exception as e:
                logger.debug('[BRIDGE] Error MTF01: %s', e)
                sensor_data['mtf01'] = {'distance_m': None, 'valid': False}

        if self._lidar and self._lidar.is_running:
            try:
                scan = self._lidar.read()
                if scan.valid and scan.points:
                    closest = min(scan.points, key=lambda p: p.distance_m)
                    sensor_data['lidar'] = {
                        'points': len(scan.points),
                        'closest_distance': round(closest.distance_m, 3),
                        'closest_angle': round(closest.angle_deg, 1),
                        'valid': True,
                    }
                else:
                    sensor_data['lidar'] = {'points': 0, 'closest_distance': None, 'closest_angle': None, 'valid': False}
            except Exception as e:
                logger.debug('[BRIDGE] Error LIDAR: %s', e)
                sensor_data['lidar'] = {'points': 0, 'closest_distance': None, 'closest_angle': None, 'valid': False}

        with self._lock:
            self._last_sensor_data = sensor_data

    # ── Envío al backend ────────────────────────────────────────────────────

    def _send_to_backend(self):
        now = time.time()
        if now - self._last_send < SENSOR_INTERVAL:
            return

        with self._lock:
            payload = {
                'sensors': dict(self._last_sensor_data),
                'mavlink': dict(self._last_mavlink_data),
            }

        if not payload['sensors'] and not payload['mavlink']:
            return

        try:
            data = json.dumps(payload).encode('utf-8')
            req = Request(
                f'{BACKEND_URL}/api/sensors',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            resp = urlopen(req, timeout=2)
            self._last_send = now
            self._consecutive_errors = 0
            resp.read()
            resp.close()
        except URLError as e:
            self._consecutive_errors += 1
            if self._consecutive_errors <= 3 or self._consecutive_errors % 50 == 0:
                logger.warning('[BRIDGE] Error enviando al backend (%d): %s',
                               self._consecutive_errors, e.reason)
        except Exception as e:
            self._consecutive_errors += 1
            if self._consecutive_errors <= 3:
                logger.warning('[BRIDGE] Error enviando al backend: %s', e)


if __name__ == '__main__':
    logging.basicConfig(
        level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
        format='[%(asctime)s] %(levelname)s - %(message)s',
    )
    bridge = DroneBridge()
    bridge.start()
    logger.info('[BRIDGE] Corriendo. Ctrl+C para detener.')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info('[BRIDGE] Deteniendo...')
    finally:
        bridge.stop()
