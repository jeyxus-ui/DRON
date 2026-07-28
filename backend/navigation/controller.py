"""
NavigationController: high-level autonomous navigation.
Combines sensors, obstacle avoidance, and path planning to
navigate the drone autonomously.
"""
import logging
import math
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class NavigationController:
    def __init__(self, mav_controller, sensor_manager, avoidance, planner):
        self.mav = mav_controller
        self.sensors = sensor_manager
        self.avoidance = avoidance
        self.planner = planner
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mode = 'IDLE'
        self._target = None
        self._planned_path = []
        self._path_index = 0
        self._waypoints = []
        self._wp_index = 0
        self._on_emergency: Optional[Callable] = None
        self._last_goto_time = 0
        self._goto_interval = 1.0
        self._avoid_target = None
        self._avoid_heading = None
        self._avoid_clear_time = 0  # cuándo se vio libre el obstáculo por última vez
        self._avoid_clear_delay = 3.0  # segundos sin obstáculo antes de reanudar
        self._last_avoid_log = 0

    def set_emergency_callback(self, cb: Callable):
        self._on_emergency = cb

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._nav_loop, daemon=True)
        self._thread.start()
        logger.info('[NAV] Navigation controller iniciado')

    def stop(self):
        self._running = False
        logger.info('[NAV] Navigation controller detenido')

    @property
    def mode(self) -> str:
        return self._mode

    def navigate_to(self, lat: float, lon: float, alt: float = 10.0):
        self._target = {'lat': lat, 'lon': lon, 'alt': alt}
        self._planned_path = []
        self._mode = 'NAVIGATING'
        logger.info('[NAV] Navegando a (%.6f, %.6f, %.1f)', lat, lon, alt)

    def start_mission(self, waypoints: list):
        self._waypoints = waypoints
        self._wp_index = 0
        self._mode = 'MISSION'
        logger.info('[NAV] Misión iniciada con %d waypoints', len(waypoints))

    def stop_navigation(self):
        self._mode = 'IDLE'
        self._target = None
        self._planned_path = []
        self._waypoints = []
        self._avoid_target = None
        self._avoid_heading = None
        self._avoid_clear_time = 0
        logger.info('[NAV] Navegación detenida')

    # ── helpers ────────────────────────────────────────────────────────────────

    def _can_send_goto(self) -> bool:
        now = time.time()
        if now - self._last_goto_time >= self._goto_interval:
            self._last_goto_time = now
            return True
        return False

    def _get_pos(self) -> dict:
        tel = self.mav.get_telemetry()
        gps = tel.get('gps', {})
        return {
            'lat': gps.get('lat', 0),
            'lon': gps.get('lon', 0),
            'alt': tel.get('altitude', 0),
            'yaw': tel.get('attitude', {}).get('yaw', 0),
        }

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
        R = 6371000
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _angle_diff(a: float, b: float) -> float:
        diff = abs(a - b) % 360
        return diff if diff <= 180 else 360 - diff

    @staticmethod
    def _offset_position(lat: float, lon: float, distance_m: float, heading_deg: float):
        R = 6371000
        rad = math.radians(heading_deg)
        dlat = distance_m * math.cos(rad) / R
        dlon = distance_m * math.sin(rad) / (R * math.cos(math.radians(lat)))
        return lat + math.degrees(dlat), lon + math.degrees(dlon)

    def _send_goto(self, lat: float, lon: float, alt: float):
        try:
            self.mav.goto(lat, lon, alt)
        except Exception as e:
            logger.error('[NAV] Error en goto: %s', e)

    # ── main loop ──────────────────────────────────────────────────────────────

    def _nav_loop(self):
        while self._running:
            try:
                sensor_data = self.sensors.get_data()
                pos = self._get_pos()
                self.sensors.set_drone_yaw(pos['yaw'])
                avoid = self.avoidance.evaluate(sensor_data)
                now = time.time()

                # ── BRAKE: obstacle too close ──
                if avoid['action'] == 'BRAKE':
                    try:
                        self.mav.set_mode('BRAKE')
                        if now - self._last_avoid_log > 2:
                            logger.warning('[NAV] 🛑 BRAKE — obstáculo a %.2fm', avoid.get('distance', 0))
                            self._last_avoid_log = now
                    except Exception as e:
                        logger.error('[NAV] Error BRAKE: %s', e)
                    if self._on_emergency:
                        self._on_emergency('BRAKE', avoid)
                    self._mode = 'AVOIDING'
                    self._avoid_target = None
                    time.sleep(0.2)
                    continue

                # ── AVOIDING / BRAKE / BRAKE_DELAYED → steer away from obstacle ──
                if avoid['action'] in ('AVOID', 'BRAKE', 'BRAKE_DELAYED'):
                    safe_heading = avoid.get('safe_heading', pos['yaw'])
                    if (self._mode != 'AVOIDING' or
                        self._avoid_heading is None or
                        self._angle_diff(self._avoid_heading, safe_heading) > 45):
                        self._avoid_heading = safe_heading
                        avoid_lat, avoid_lon = self._offset_position(
                            pos['lat'], pos['lon'], 200.0, safe_heading)
                        self._avoid_target = {'lat': avoid_lat, 'lon': avoid_lon, 'alt': pos['alt']}
                        logger.info('[NAV] Esquivando → heading %.1f° → (%.6f, %.6f)',
                                    safe_heading, avoid_lat, avoid_lon)
                    self._avoid_clear_time = 0
                    self._mode = 'AVOIDING'

                # ── Obstacle cleared with hysteresis → resume mission ──
                if avoid['action'] == 'NONE' and self._mode == 'AVOIDING':
                    if self._avoid_clear_time == 0:
                        self._avoid_clear_time = now
                    elif now - self._avoid_clear_time >= self._avoid_clear_delay:
                        self._avoid_target = None
                        self._avoid_heading = None
                        self._avoid_clear_time = 0
                        self._planned_path = []  # force replan from current position
                        self._mode = self._next_mode()
                        logger.info('[NAV] Obstáculo superado (%gs sin detectar) → modo %s',
                                    self._avoid_clear_delay, self._mode)
                else:
                    self._avoid_clear_time = 0  # reset timer if obstacle still present

                # ── Execute movement ──
                if self._mode == 'AVOIDING' and self._avoid_target:
                    if self._can_send_goto():
                        self._send_goto(self._avoid_target['lat'],
                                        self._avoid_target['lon'],
                                        self._avoid_target['alt'])

                elif self._mode == 'NAVIGATING' and self._target:
                    self._exec_nav(pos)

                elif self._mode == 'MISSION':
                    self._exec_mission(pos)

            except Exception as e:
                logger.error('[NAV] Error en loop: %s', e, exc_info=True)

            time.sleep(0.2)

    def _next_mode(self) -> str:
        if self._target:
            return 'NAVIGATING'
        if self._waypoints and self._wp_index < len(self._waypoints):
            return 'MISSION'
        return 'IDLE'

    # ── navigation execution ──────────────────────────────────────────────────

    def _exec_nav(self, pos: dict):
        if not self._target or pos['lat'] is None or pos['lon'] is None:
            return
        t = self._target
        dst = self._haversine(pos['lat'], pos['lon'], t['lat'], t['lon'])
        if dst < 2.0:
            logger.info('[NAV] ✅ Destino alcanzado (%.1fm)', dst)
            self._target = None
            self._mode = 'IDLE'
            return

        # Replan if needed (first time or after avoidance detour)
        if not self._planned_path:
            obs_map = getattr(self.sensors, 'obstacle_map', None)
            self._planned_path = self.planner.plan_to_waypoint(
                pos['lat'], pos['lon'],
                t['lat'], t['lon'],
                obs_map,
            )
            self._path_index = 0
            logger.info('[NAV] Ruta planificada: %d waypoints', len(self._planned_path))

        if self._planned_path and self._path_index < len(self._planned_path):
            wp = self._planned_path[self._path_index]
            wp_dst = self._haversine(pos['lat'], pos['lon'], wp['lat'], wp['lon'])
            if wp_dst < 2.0:
                self._path_index += 1
                if self._path_index >= len(self._planned_path):
                    self._planned_path = []
                    return
                wp = self._planned_path[self._path_index]
            if self._can_send_goto():
                self._send_goto(wp['lat'], wp['lon'], wp.get('alt', t['alt']))
        else:
            if self._can_send_goto():
                self._send_goto(t['lat'], t['lon'], t['alt'])

    def _exec_mission(self, pos: dict):
        if not self._waypoints or self._wp_index >= len(self._waypoints):
            logger.info('[NAV] ✅ Misión completada')
            self._mode = 'IDLE'
            self._waypoints = []
            return
        wp = self._waypoints[self._wp_index]
        if pos['lat'] is not None and pos['lon'] is not None:
            dst = self._haversine(pos['lat'], pos['lon'], wp['lat'], wp['lon'])
            if dst < 2.0:
                self._wp_index += 1
                logger.info('[NAV] Waypoint %d/%d alcanzado', self._wp_index, len(self._waypoints))
                return
        if self._can_send_goto():
            self._send_goto(wp['lat'], wp['lon'], wp.get('alt', 10))

    # ── status ─────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            'mode': self._mode,
            'target': self._target,
            'waypoint_index': self._wp_index,
            'total_waypoints': len(self._waypoints),
            'avoidance_active': self.avoidance.is_active,
            'planned_path_length': len(self._planned_path),
        }
