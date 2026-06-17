import logging
import math
import random
import time
import os
from .base import BaseSensor, LidarScan, LidarPoint

logger = logging.getLogger(__name__)

LIDAR_BAUD = 115200
LIDAR_TIMEOUT = 1.0
POINTS_PER_SCAN = 720
RETRY_INTERVAL = 5.0
MAX_CONSECUTIVE_ERRORS = 10
LOG_SUPPRESS_SECONDS = 5.0


class YDLidarX4(BaseSensor):
    def __init__(self, sim_mode: bool = True, port: str = '/dev/ttyUSB0'):
        super().__init__('YDLIDAR_X4', sim_mode)
        self.port = port
        self._serial = None
        self._sim_obstacles = []
        self._sim_start = 0.0
        self._last_scan = LidarScan(timestamp=time.time(), valid=False)
        self._is_dead = False
        self._consecutive_errors = 0
        self._last_error_log = 0.0
        self._last_retry = 0.0

    def start(self) -> bool:
        if self.sim_mode:
            logger.info('[YDLIDAR] Modo simulación — escaneos 360° simulados')
            self._sim_start = time.time()
            self._sim_obstacles = [
                {'angle': 45, 'dist': 3.0, 'size': 20},
                {'angle': 120, 'dist': 5.0, 'size': 15},
                {'angle': 200, 'dist': 2.5, 'size': 10},
                {'angle': 300, 'dist': 4.0, 'size': 25},
            ]
            self._running = True
            return True
        ok = self._try_connect()
        self._running = ok
        return ok

    def _find_port(self) -> str:
        if os.path.exists(self.port):
            return self.port
        base = os.path.dirname(self.port)
        if not os.path.isdir(base):
            return ''
        for f in sorted(os.listdir(base)):
            path = os.path.join(base, f)
            if f.startswith('ttyUSB') and os.path.exists(path):
                try:
                    import serial
                    s = serial.Serial(port=path, baudrate=LIDAR_BAUD, timeout=0.5)
                    s.close()
                    logger.info('[YDLIDAR] Puerto detectado: %s', path)
                    return path
                except Exception:
                    continue
        return ''

    def _try_connect(self) -> bool:
        port = self._find_port()
        if not port:
            self._log_error_rate_limited(f'Puerto {self.port} no disponible')
            self._is_dead = True
            return False
        if port != self.port:
            self.port = port
        try:
            import serial
            if self._serial:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
            self._serial = serial.Serial(
                port=self.port,
                baudrate=LIDAR_BAUD,
                timeout=LIDAR_TIMEOUT,
            )
            self._is_dead = False
            self._consecutive_errors = 0
            logger.info('[YDLIDAR] Conectado en %s a %d baud', self.port, LIDAR_BAUD)
            return True
        except ImportError:
            logger.error('[YDLIDAR] pyserial no disponible')
            return False
        except Exception as e:
            self._log_error_rate_limited(f'Error conectando: {e}')
            self._error_count += 1
            self._is_dead = True
            return False

    def stop(self):
        self._running = False
        ser = self._serial
        if ser:
                s = self._serial
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass
                self._serial = None
        logger.info('[YDLIDAR] Detenido')

    def read(self) -> LidarScan:
        t = time.time()
        if not self._running:
            return LidarScan(timestamp=t, valid=False)
        if self.sim_mode:
            scan = self._sim_scan(t)
        else:
            scan = self._real_scan(t)
        self._last_scan = scan
        return scan

    def _sim_scan(self, t: float) -> LidarScan:
        elapsed = t - self._sim_start
        points = []
        for i in range(POINTS_PER_SCAN):
            angle = (i / POINTS_PER_SCAN) * 360.0
            dist = 8.0 + 2.0 * math.sin(math.radians(angle * 2 + elapsed * 30))
            for obs in self._sim_obstacles:
                diff = abs(angle - obs['angle'])
                if diff < obs['size']:
                    overlap = 1.0 - (diff / obs['size'])
                    obstacle_dist = obs['dist'] + 0.5 * math.sin(elapsed * 0.5 + obs['angle'])
                    noise = random.gauss(0, 0.05)
                    dist = min(dist, obstacle_dist + noise)
            dist = max(0.12, min(10.0, dist))
            quality = max(0, min(255, int(150 - (dist / 10.0) * 100 + random.gauss(0, 10))))
            points.append(LidarPoint(angle_deg=angle, distance_m=round(dist, 3), quality=quality))
        return LidarScan(
            timestamp=t,
            valid=True,
            points=points,
            min_angle=0.0,
            max_angle=360.0,
        )

    def _real_scan(self, t: float) -> LidarScan:
        if self._is_dead:
            if t - self._last_retry > RETRY_INTERVAL:
                self._last_retry = t
                ok = self._try_connect()
                if not ok:
                    return LidarScan(timestamp=t, valid=False)
            else:
                return LidarScan(timestamp=t, valid=False)

        try:
            if self._serial is None:
                return LidarScan(timestamp=t, valid=False)
            raw = self._serial.read(2000)
            points = []
            for i in range(0, len(raw) - 4, 5):
                if i + 4 >= len(raw):
                    break
                angle = (raw[i] | (raw[i+1] << 8)) / 64.0
                dist_mm = raw[i+2] | (raw[i+3] << 8)
                quality = raw[i+4]
                if dist_mm > 0:
                    points.append(LidarPoint(
                        angle_deg=angle,
                        distance_m=dist_mm / 1000.0,
                        quality=quality,
                    ))
            self._consecutive_errors = 0
            return LidarScan(timestamp=t, valid=len(points) > 0, points=points)
        except Exception as e:
            self._consecutive_errors += 1
            self._error_count += 1
            if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                if not self._is_dead:
                    logger.error('[YDLIDAR] Demasiados errores consecutivos — sensor desactivado')
                    self._is_dead = True
                s = self._serial
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass
                self._serial = None
            else:
                self._log_error_rate_limited(f'Error en escaneo: {e}')
            return LidarScan(timestamp=t, valid=False)

    def _log_error_rate_limited(self, msg: str):
        now = time.time()
        if now - self._last_error_log > LOG_SUPPRESS_SECONDS:
            logger.error('[YDLIDAR] %s', msg)
            self._last_error_log = now

    def get_scan(self) -> LidarScan:
        return self._last_scan

    def get_closest_obstacle(self) -> dict:
        if not self._last_scan.valid or not self._last_scan.points:
            return {'distance': None, 'angle': None}
        closest = min(self._last_scan.points, key=lambda p: p.distance_m)
        return {'distance': closest.distance_m, 'angle': closest.angle_deg}

    def get_obstacles_in_zone(self, angle_deg: float, fov: float = 30.0, max_dist: float = 3.0) -> list:
        if not self._last_scan.valid:
            return []
        half = fov / 2.0
        return [
            p for p in self._last_scan.points
            if abs(p.angle_deg - angle_deg) <= half and p.distance_m <= max_dist
        ]
