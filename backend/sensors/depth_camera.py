"""
DepthCameraSensor: convierte el mapa de profundidad de la RealSense D435i
en un barrido tipo lidar, para alimentar el ObstacleMap.

Por que existe
--------------
La profundidad de la camara solo se consumia dentro de VisionDetector.detect(),
que en la Raspberry Pi 4 esta deshabilitado (DRON_VISION_ENABLED=0, ver
AGENTS.md: PyTorch crashea con SIGILL en Cortex-A72). Sin este modulo la
profundidad se capturaba y se descartaba.

Este sensor NO usa YOLO ni PyTorch: solo lee el array de profundidad con
numpy. Detecta cualquier obstaculo fisico -- paredes, cables, ramas, sillas --
no solo las 80 clases COCO que reconoce el detector.

Como funciona
-------------
Toma una franja horizontal del centro del mapa de profundidad. Cada columna
de esa franja es una direccion; se queda con el obstaculo mas cercano de la
columna. El resultado son puntos (angulo, distancia) identicos en forma a los
del YDLidar, asi que ObstacleMap.update_from_lidar() los consume sin cambios.
"""
import logging
import math
import time

import numpy as np

from .base import BaseSensor, LidarScan, LidarPoint

logger = logging.getLogger(__name__)

# Campo de vision horizontal nominal del sensor de profundidad de la D435i.
# Solo se usa como respaldo: si la camara entrega sus intrinsecos reales (fx),
# el angulo se calcula con ellos, que es exacto.
D435I_HFOV_DEG = 87.0

# Rango util de la D435i. Fuera de esto el dato no es confiable.
MIN_DIST_M = 0.20
MAX_DIST_M = 10.0


class DepthCameraSensor(BaseSensor):
    """
    Lee el frame de profundidad de la camara y lo entrega como LidarScan.

    La camara no se abre aqui: RealSenseCamera ya la tiene abierta (solo un
    proceso puede usarla a la vez). Este sensor recibe un proveedor que le
    devuelve el ultimo frame capturado.
    """

    def __init__(self,
                 sim_mode: bool = False,
                 band_ratio: float = 0.25,
                 column_step: int = 8,
                 invert_horizontal: bool = False):
        """
        band_ratio        Fraccion vertical central de la imagen a usar (0.25 = 25%).
                          Una franja estrecha mira "al frente"; una ancha incluye
                          suelo y techo y genera falsos obstaculos.
        column_step       Submuestreo de columnas. 8 sobre 848px da ~106 puntos,
                          suficiente resolucion angular y barato en CPU.
        invert_horizontal Invierte el signo del angulo. VER NOTA DE CALIBRACION
                          en el docstring de _column_to_angle().
        """
        super().__init__(name='depth_camera', sim_mode=sim_mode)
        self.band_ratio = band_ratio
        self.column_step = column_step
        self.invert_horizontal = invert_horizontal

        self._provider = None       # callable -> (depth_array, depth_scale)
        self._fx = None             # focal length en px, de los intrinsecos
        self._cx = None             # centro optico en px
        self._last_scan = LidarScan(timestamp=0.0, valid=False)
        self._frames_read = 0
        self._frames_empty = 0

    # ── Conexion con la camara ───────────────────────────────────

    def set_frame_provider(self, provider):
        """
        Registra la funcion que entrega el frame de profundidad.

        provider() debe devolver (array_2d_uint16, escala_metros_por_unidad)
        o (None, escala) si no hay frame disponible.

        Se inyecta desde fuera para no importar camera_stream aqui (evita
        dependencia circular: camera_stream ya importa cosas de vision).
        """
        self._provider = provider
        logger.info('[DEPTH_CAM] Proveedor de frames conectado')

    def set_intrinsics(self, fx: float, cx: float = None):
        """
        Recibe los intrinsecos reales del stream de profundidad.

        Con fx el angulo de cada columna se calcula exacto. Sin el se usa el
        FOV nominal de 87 grados, que es aproximado (Intel especifica +/-3).
        """
        self._fx = fx
        self._cx = cx
        logger.info('[DEPTH_CAM] Intrinsecos: fx=%.1f cx=%s', fx, cx)

    # ── Ciclo de vida ────────────────────────────────────────────

    def start(self) -> bool:
        if self._provider is None and not self.sim_mode:
            logger.warning('[DEPTH_CAM] Sin proveedor de frames — no se inicia')
            return False
        self._running = True
        logger.info('[DEPTH_CAM] Iniciado (banda=%.0f%% paso=%dpx)',
                    self.band_ratio * 100, self.column_step)
        return True

    def stop(self):
        self._running = False
        logger.info('[DEPTH_CAM] Detenido (%d frames leidos, %d vacios)',
                    self._frames_read, self._frames_empty)

    # ── Conversion profundidad -> angulos ────────────────────────

    def _column_to_angle(self, col: int, width: int) -> float:
        """
        Convierte una columna de la imagen en un angulo respecto al frente.

        Angulo 0 = centro de la imagen = hacia donde apunta la camara.

        NOTA DE CALIBRACION — IMPORTANTE
        El signo sigue la convencion matematica que usa ObstacleMap
        (x = d*cos(ang), y = d*sin(ang)): positivo antihorario. Cual lado
        fisico corresponde a "positivo" depende de como este montada la
        camara en el dron y de la convencion de yaw del autopiloto.

        ESTO HAY QUE VERIFICARLO CON UNA PRUEBA FISICA antes de volar:
        poner un obstaculo claramente a un lado y confirmar que el mapa lo
        ubica del mismo lado. Si sale espejado, arrancar con
        invert_horizontal=True. Un signo invertido haria que el dron
        esquive HACIA el obstaculo.
        """
        if self._fx:
            cx = self._cx if self._cx is not None else width / 2.0
            angle = math.degrees(math.atan((col - cx) / self._fx))
        else:
            # Respaldo: reparte el FOV nominal linealmente entre las columnas.
            # Es aproximado — la relacion real es la tangente, no lineal.
            angle = (col / width - 0.5) * D435I_HFOV_DEG

        return -angle if self.invert_horizontal else angle

    def _depth_to_points(self, depth: np.ndarray, scale: float) -> list:
        """
        Reduce el mapa de profundidad a una lista de LidarPoint.

        Todo el trabajo pesado va vectorizado en numpy: en la Pi 4 un bucle
        Python sobre 848x480 seria inviable dentro del loop de sensores.
        """
        h, w = depth.shape

        # Franja horizontal centrada: es la que mira "al frente" del dron.
        band_h = max(1, int(h * self.band_ratio))
        y0 = (h - band_h) // 2
        band = depth[y0:y0 + band_h, :]

        # A metros. float32 basta y es mas rapido que float64 en ARM.
        band_m = band.astype(np.float32) * scale

        # Los ceros son "sin dato" (sombras del estereo), no "distancia cero".
        # Marcarlos como infinito para que no ganen el minimo.
        band_m[band_m < MIN_DIST_M] = np.inf
        band_m[band_m > MAX_DIST_M] = np.inf

        # Obstaculo mas cercano de cada columna.
        closest = band_m.min(axis=0)

        points = []
        for col in range(0, w, self.column_step):
            d = float(closest[col])
            if not math.isfinite(d):
                continue
            points.append(LidarPoint(
                angle_deg=self._column_to_angle(col, w),
                distance_m=round(d, 3),
                quality=255,   # el estereo no da calidad por punto; valor fijo
            ))
        return points

    # ── Lectura ──────────────────────────────────────────────────

    def read(self) -> LidarScan:
        if not self._running or self._provider is None:
            return LidarScan(timestamp=time.time(), valid=False)

        try:
            depth, scale = self._provider()
        except Exception as e:
            self._error_count += 1
            logger.debug('[DEPTH_CAM] Error pidiendo frame: %s', e)
            return LidarScan(timestamp=time.time(), valid=False)

        if depth is None or getattr(depth, 'size', 0) == 0:
            self._frames_empty += 1
            return LidarScan(timestamp=time.time(), valid=False)

        try:
            points = self._depth_to_points(depth, scale or 0.001)
        except Exception as e:
            self._error_count += 1
            logger.warning('[DEPTH_CAM] Error procesando profundidad: %s', e)
            return LidarScan(timestamp=time.time(), valid=False)

        self._frames_read += 1
        half_fov = D435I_HFOV_DEG / 2.0
        scan = LidarScan(
            timestamp=time.time(),
            valid=len(points) > 0,
            points=points,
            min_angle=-half_fov,
            max_angle=half_fov,
        )
        self._last_scan = scan
        return scan

    # ── Diagnostico ──────────────────────────────────────────────

    @property
    def status(self) -> dict:
        st = super().status
        st.update({
            'frames_read': self._frames_read,
            'frames_empty': self._frames_empty,
            'points_last_scan': len(self._last_scan.points),
            'has_intrinsics': self._fx is not None,
            'fx': round(self._fx, 1) if self._fx else None,
            'invert_horizontal': self.invert_horizontal,
        })
        return st

    def closest_obstacle(self):
        """Devuelve (distancia_m, angulo_deg) del punto mas cercano, o None."""
        if not self._last_scan.valid or not self._last_scan.points:
            return None
        p = min(self._last_scan.points, key=lambda q: q.distance_m)
        return p.distance_m, p.angle_deg

    def sectors(self, n: int = 5) -> list:
        """
        Reparte el ultimo barrido en n sectores angulares y devuelve la
        distancia mas cercana de cada uno.

        Pensado para mostrar el estado de un vistazo (una fila tipo radar),
        no para navegar: para eso esta el ObstacleMap, que ademas acumula
        en el tiempo y fusiona con los otros sensores.
        """
        if not self._last_scan.valid or not self._last_scan.points:
            return []
        pts = self._last_scan.points
        lo = min(p.angle_deg for p in pts)
        hi = max(p.angle_deg for p in pts)
        span = (hi - lo) or 1.0
        cubos = [[] for _ in range(n)]
        for p in pts:
            i = int((p.angle_deg - lo) / span * n)
            cubos[min(i, n - 1)].append(p.distance_m)
        salida = []
        for i, c in enumerate(cubos):
            a0 = lo + span * i / n
            a1 = lo + span * (i + 1) / n
            salida.append({
                'angle_from': round(a0, 1),
                'angle_to': round(a1, 1),
                'closest_m': round(min(c), 2) if c else None,
                'points': len(c),
            })
        return salida
