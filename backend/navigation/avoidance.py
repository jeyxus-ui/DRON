"""
Obstacle avoidance module.
Uses sensor data to detect obstacles and compute evasive maneuvers.
"""
import logging
import math
import time

logger = logging.getLogger(__name__)


class ObstacleAvoidance:
    def __init__(self, safety_distance_m: float = 2.0, brake_distance_m: float = 1.0):
        self.safety_distance = safety_distance_m
        self.brake_distance = brake_distance_m
        self._last_brake_time = 0
        self.brake_cooldown = 3.0
        self._active = True

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool):
        self._active = active
        logger.info('[AVOID] Avoidance %s', 'activado' if active else 'desactivado')

    def evaluate(self, sensor_data: dict) -> dict:
        if not self._active:
            return {'action': 'NONE', 'reason': 'avoidance disabled'}

        mtf = sensor_data.get('mtf01', {})
        lidar = sensor_data.get('lidar', {})
        yaw = sensor_data.get('drone_yaw', 0.0)

        mtf_dist = mtf.get('distance_m')
        lidar_closest = lidar.get('closest_distance')

        min_dist = float('inf')
        if mtf_dist is not None:
            min_dist = min(min_dist, mtf_dist)
        if lidar_closest is not None:
            min_dist = min(min_dist, lidar_closest)

        now = time.time()
        if min_dist <= self.brake_distance:
            if now - self._last_brake_time > self.brake_cooldown:
                self._last_brake_time = now
                logger.warning('[AVOID] CRÍTICO — obstáculo a %.2fm — BRAKE', min_dist)
                return {
                    'action': 'BRAKE',
                    'reason': f'obstacle at {min_dist:.2f}m',
                    'distance': min_dist,
                }
            return {'action': 'NONE', 'reason': 'cooldown'}

        if min_dist <= self.safety_distance:
            safe_yaw = sensor_data.get('safe_direction', yaw)
            turn = safe_yaw - yaw
            if turn > 180:
                turn -= 360
            elif turn < -180:
                turn += 360
            logger.info('[AVOID] ADVERTENCIA — obstáculo a %.2fm — giro %.0f°', min_dist, turn)
            return {
                'action': 'AVOID',
                'reason': f'obstacle at {min_dist:.2f}m',
                'distance': min_dist,
                'turn_deg': round(turn, 1),
                'safe_heading': round(safe_yaw, 1),
            }

        return {'action': 'NONE', 'reason': 'clear'}
