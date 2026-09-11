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
from .depth_camera import DepthCameraSensor

logger = logging.getLogger(__name__)


class SensorManager:
    def __init__(self, sim_mode: bool = True):
        self.sim_mode = sim_mode
        self.mtf01 = MTF01Sensor(sim_mode=sim_mode)
        self.lidar = YDLidarX4(sim_mode=sim_mode)
        # Camara de profundidad: arranca inerte. Solo se activa si alguien le
        # conecta un proveedor de frames (ver enable_depth_camera). Asi el
        # manager funciona igual en equipos sin RealSense.
        self.depth_cam = DepthCameraSensor(sim_mode=False)
        self.obstacle_map = ObstacleMap(width_m=20, height_m=20, resolution_m=0.2)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._latest_mtf01 = DistanceReading(timestamp=0, valid=False)
        self._latest_lidar = LidarScan(timestamp=0, valid=False)
        self._latest_depth = LidarScan(timestamp=0, valid=False)
        self._drone_yaw = 0.0
        self._latest_vision: list = []      # detecciones YOLO/ArUco del último frame
        self._vision_lock = threading.Lock()
        self._last_frame_width: int = 640

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

    def enable_depth_camera(self, frame_provider, fx: float = None, cx: float = None,
                            invert_horizontal: bool = False) -> bool:
        """
        Activa la RealSense como fuente de obstaculos.

        frame_provider() debe devolver (array_profundidad, escala_metros).
        Se llama desde donde se inicializa la camara, para no acoplar el
        modulo de sensores con el de video.

        OJO: verificar invert_horizontal con una prueba fisica antes de volar
        (ver nota en depth_camera._column_to_angle).
        """
        self.depth_cam.invert_horizontal = invert_horizontal
        self.depth_cam.set_frame_provider(frame_provider)
        if fx:
            self.depth_cam.set_intrinsics(fx, cx)
        ok = self.depth_cam.start()
        logger.info('[SENSORES] Camara de profundidad %s',
                    'activada' if ok else 'NO pudo activarse')
        return ok

    def _depth_summary(self) -> dict:
        """Resumen del ultimo barrido de la camara de profundidad."""
        if not self.depth_cam.is_running:
            return {'active': False, 'points': 0,
                    'closest_distance': None, 'closest_angle': None}
        closest = self.depth_cam.closest_obstacle()
        return {
            'active': True,
            'points': len(self._latest_depth.points) if self._latest_depth.valid else 0,
            'closest_distance': round(closest[0], 3) if closest else None,
            'closest_angle': round(closest[1], 1) if closest else None,
            'valid': self._latest_depth.valid,
        }

    def _loop(self):
        while self._running:
            mtf = self.mtf01.read()
            lid = self.lidar.read()
            # Solo lee si alguien conecto la camara (si no, devuelve invalido barato)
            dep = self.depth_cam.read() if self.depth_cam.is_running else None
            with self._lock:
                self._latest_mtf01 = mtf
                self._latest_lidar = lid
                if lid.valid and lid.points:
                    self.obstacle_map.update_from_lidar(lid.points, self._drone_yaw)
                # La profundidad entrega LidarPoint, asi que reusa la misma
                # entrada del mapa que el lidar. No hace falta metodo nuevo.
                if dep is not None and dep.valid and dep.points:
                    self._latest_depth = dep
                    self.obstacle_map.update_from_lidar(dep.points, self._drone_yaw)
                if mtf.valid:
                    self.obstacle_map.update_from_ultrasonic(mtf.distance_m, self._drone_yaw)
                self.obstacle_map.decay(0.995)
            time.sleep(0.05)

    def set_drone_yaw(self, yaw_deg: float):
        self._drone_yaw = yaw_deg

    def update_from_vision(self, detections, drone_yaw_deg: float = None, frame_width: int = 640):
        """Recibe detecciones de la cámara, las fusiona en el obstacle_map y las guarda."""
        yaw = drone_yaw_deg if drone_yaw_deg is not None else self._drone_yaw
        with self._vision_lock:
            self._latest_vision = list(detections)
            self._last_frame_width = frame_width      # guardado para calcular ángulo en get_data()
        with self._lock:
            self.obstacle_map.update_from_vision(detections, yaw, frame_width)

    def get_forward_distance(self) -> float | None:
        """Distancia al frente según MTF-01 (usado como fallback para estimación de cámara)."""
        with self._lock:
            return self._latest_mtf01.distance_m if self._latest_mtf01.valid else None

    def get_data(self) -> dict:
        # Capturar todo con los locks en una sola pasada — sin lecturas fuera de lock
        with self._lock:
            closest_lidar = None
            if self._latest_lidar.valid and self._latest_lidar.points:
                closest_lidar = min(self._latest_lidar.points, key=lambda p: p.distance_m)
            mtf_dist = self._latest_mtf01.distance_m if self._latest_mtf01.valid else None
            mtf_valid = self._latest_mtf01.valid
            lidar_pts = len(self._latest_lidar.points) if self._latest_lidar.valid else 0
            lidar_valid = self._latest_lidar.valid
            obs_map = self.obstacle_map.to_dict()
            drone_yaw = self._drone_yaw
            safe_dir = self.obstacle_map.find_free_direction(drone_yaw, min_clearance_m=2.0)

        with self._vision_lock:
            vision_list = list(self._latest_vision)
            fw = self._last_frame_width

        # Obstáculo de cámara más cercano, con ángulo respecto al frente del dron
        vision_closest = None
        if vision_list:
            valid_v = [d for d in vision_list if getattr(d, 'distance', 999) < 10.0]
            if valid_v:
                cv = min(valid_v, key=lambda d: getattr(d, 'distance', 999))
                try:
                    x1, y1, x2, y2 = cv.bbox
                    cx_norm = ((x1 + x2) / 2.0) / max(fw, 1)
                    angle_offset = round((cx_norm - 0.5) * 62.0, 1)   # 62° HFOV típico
                except Exception:
                    angle_offset = 0.0
                vision_closest = {
                    'distance_m': round(getattr(cv, 'distance', 999), 2),
                    'zone': getattr(cv, 'zone', 'unknown'),
                    'label': getattr(cv, 'label', ''),
                    'angle_offset_deg': angle_offset,   # >0=derecha, <0=izquierda
                }

        return {
            'mtf01': {'distance_m': mtf_dist, 'valid': mtf_valid},
            'lidar': {
                'points': lidar_pts,
                'closest_distance': round(closest_lidar.distance_m, 3) if closest_lidar else None,
                'closest_angle': round(closest_lidar.angle_deg, 1) if closest_lidar else None,
                'valid': lidar_valid,
            },
            'vision': {
                'closest': vision_closest,
                'count': len(vision_list),
                'valid': len(vision_list) > 0,
            },
            'depth_camera': self._depth_summary(),
            'obstacle_map': obs_map,
            'drone_yaw': drone_yaw,
            'safe_direction': safe_dir,
        }

    def get_status(self) -> dict:
        return {
            'running': self._running,
            'sim_mode': self.sim_mode,
            'mtf01': self.mtf01.status,
            'lidar': self.lidar.status,
            'depth_camera': self.depth_cam.status,
        }

    def has_obstacle_ahead(self, threshold_m: float = 2.0) -> bool:
        with self._lock:
            mtf_dist = self._latest_mtf01.distance_m if self._latest_mtf01.valid else float('inf')
            if mtf_dist < threshold_m:
                return True
            if self._latest_lidar.valid and self._latest_lidar.points:
                for p in self._latest_lidar.points:
                    if p.distance_m < threshold_m and abs(p.angle_deg) < 45:
                        return True
            # La camara de profundidad ve obstaculos que el MTF-01 (un solo haz
            # al frente) y el lidar (plano horizontal unico) se pierden: mesas,
            # cables, ramas a distinta altura.
            if self._latest_depth.valid and self._latest_depth.points:
                for p in self._latest_depth.points:
                    if p.distance_m < threshold_m and abs(p.angle_deg) < 45:
                        return True
            return False

    @property
    def safe_direction(self) -> float:
        with self._lock:
            return self.obstacle_map.find_free_direction(self._drone_yaw, min_clearance_m=2.0)
