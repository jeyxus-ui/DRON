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
        self._waypoints = []
        self._wp_index = 0
        self._on_emergency: Optional[Callable] = None

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
        self._waypoints = []
        logger.info('[NAV] Navegación detenida')

    def _nav_loop(self):
        last_avoid_time = 0
        while self._running:
            try:
                sensor_data = self.sensors.get_data()
                self.sensors.set_drone_yaw(self.mav.get_telemetry().get('attitude', {}).get('yaw', 0))

                avoid = self.avoidance.evaluate(sensor_data)
                now = time.time()

                if avoid['action'] == 'BRAKE':
                    if now - last_avoid_time > 3.0:
                        last_avoid_time = now
                        try:
                            self.mav.set_mode('BRAKE')
                            logger.warning('[NAV] 🛑 BRAKE por obstáculo')
                        except Exception as e:
                            logger.error('[NAV] Error BRAKE: %s', e)
                        if self._on_emergency:
                            self._on_emergency('BRAKE', avoid)
                    self._mode = 'AVOIDING'

                elif avoid['action'] == 'AVOID':
                    safe_heading = avoid.get('safe_heading')
                    if safe_heading and now - last_avoid_time > 1.0:
                        logger.info('[NAV] Esquivando — heading %.1f°', safe_heading)
                        last_avoid_time = now
                    self._mode = 'AVOIDING'

                elif self._mode == 'AVOIDING':
                    self._mode = 'NAVIGATING' if self._target else ('MISSION' if self._waypoints else 'IDLE')

                if self._mode == 'NAVIGATING' and self._target:
                    self._execute_navigation_step()

                elif self._mode == 'MISSION':
                    self._execute_mission_step()

            except Exception as e:
                logger.error('[NAV] Error en loop: %s', e)

            time.sleep(0.2)

    def _execute_navigation_step(self):
        if not self._target:
            return
        tel = self.mav.get_telemetry()
        gps = tel.get('gps', {})
        cur_lat = gps.get('lat', 0)
        cur_lon = gps.get('lon', 0)
        if not cur_lat or not cur_lon:
            return
        t = self._target
        dist = haversine(cur_lat, cur_lon, t['lat'], t['lon'])
        if dist < 2.0:
            logger.info('[NAV] ✅ Destino alcanzado')
            self._target = None
            self._mode = 'IDLE'
            return
        try:
            self.mav.goto(t['lat'], t['lon'], t['alt'])
        except Exception as e:
            logger.error('[NAV] Error goto: %s', e)

    def _execute_mission_step(self):
        if not self._waypoints or self._wp_index >= len(self._waypoints):
            logger.info('[NAV] ✅ Misión completada')
            self._mode = 'IDLE'
            self._waypoints = []
            return
        wp = self._waypoints[self._wp_index]
        tel = self.mav.get_telemetry()
        gps = tel.get('gps', {})
        cur_lat = gps.get('lat', 0)
        cur_lon = gps.get('lon', 0)
        if cur_lat and cur_lon:
            dist = haversine(cur_lat, cur_lon, wp['lat'], wp['lon'])
            if dist < 2.0:
                self._wp_index += 1
                logger.info('[NAV] Waypoint %d alcanzado', self._wp_index)
                return
        try:
            self.mav.goto(wp['lat'], wp['lon'], wp.get('alt', 10))
        except Exception as e:
            logger.error('[NAV] Error en waypoint %d: %s', self._wp_index, e)

    def get_status(self) -> dict:
        return {
            'mode': self._mode,
            'target': self._target,
            'waypoint_index': self._wp_index,
            'total_waypoints': len(self._waypoints),
            'avoidance_active': self.avoidance.is_active,
        }


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
