"""
SensorManager: orquesta todos los sensores, los lee en un loop y
mantiene el mapa de obstáculos actualizado.
"""
import logging
import threading
import time
from typing import Optional
from .base import LidarScan, DistanceReading
from .mtf01 import MTF01Sensor
from .ydlidar_x4 import YDLidarX4
from .obstacle_map import ObstacleMap

logger = logging.getLogger(__name__)


class SensorManager:
    def __init__(self, sim_mode: bool = True):
        self.sim_mode = sim_mode
        self.mtf01 = MTF01Sensor(sim_mode=sim_mode)
        self.lidar = YDLidarX4(sim_mode=sim_mode)
        self.obstacle_map = ObstacleMap(width_m=20, height_m=20, resolution_m=0.2)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._latest_mtf01 = DistanceReading(timestamp=0, valid=False)
        self._latest_lidar = LidarScan(timestamp=0, valid=False)
        self._drone_yaw = 0.0

    def start(self) -> bool:
        ok1 = self.mtf01.start()
        ok2 = self.lidar.start()
        if not ok1 and not ok2:
            logger.warning('[SENSORES] Ningún sensor pudo iniciarse')
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info('[SENSORES] Manager iniciado — MTF01=%s LIDAR=%s', ok1, ok2)
        return True

    def stop(self):
        self._running = False
        self.mtf01.stop()
        self.lidar.stop()
        logger.info('[SENSORES] Manager detenido')

    def _loop(self):
        while self._running:
            mtf = self.mtf01.read()
            lid = self.lidar.read()
            with self._lock:
                self._latest_mtf01 = mtf
                self._latest_lidar = lid
            if lid.valid and lid.points:
                self.obstacle_map.update_from_lidar(lid.points, self._drone_yaw)
            if mtf.valid:
                self.obstacle_map.update_from_ultrasonic(mtf.distance_m, self._drone_yaw)
            self.obstacle_map.decay(0.995)
            time.sleep(0.05)

    def set_drone_yaw(self, yaw_deg: float):
        self._drone_yaw = yaw_deg

    def get_data(self) -> dict:
        with self._lock:
            closest_lidar = None
            if self._latest_lidar.valid and self._latest_lidar.points:
                closest_lidar = min(self._latest_lidar.points, key=lambda p: p.distance_m)
            return {
                'mtf01': {
                    'distance_m': self._latest_mtf01.distance_m if self._latest_mtf01.valid else None,
                    'valid': self._latest_mtf01.valid,
                },
                'lidar': {
                    'points': len(self._latest_lidar.points) if self._latest_lidar.valid else 0,
                    'closest_distance': round(closest_lidar.distance_m, 3) if closest_lidar else None,
                    'closest_angle': round(closest_lidar.angle_deg, 1) if closest_lidar else None,
                    'valid': self._latest_lidar.valid,
                },
                'obstacle_map': self.obstacle_map.to_dict(),
                'drone_yaw': self._drone_yaw,
                'safe_direction': self.safe_direction,
            }

    def get_status(self) -> dict:
        return {
            'running': self._running,
            'sim_mode': self.sim_mode,
            'mtf01': self.mtf01.status,
            'lidar': self.lidar.status,
        }

    @property
    def has_obstacle_ahead(self, threshold_m: float = 2.0) -> bool:
        mtf_dist = self._latest_mtf01.distance_m if self._latest_mtf01.valid else float('inf')
        if mtf_dist < threshold_m:
            return True
        if self._latest_lidar.valid and self._latest_lidar.points:
            front = self.lidar.get_obstacles_in_zone(0, fov=45, max_dist=threshold_m)
            if front:
                return True
        return False

    @property
    def safe_direction(self) -> float:
        return self.obstacle_map.find_free_direction(self._drone_yaw, min_clearance_m=2.0)
