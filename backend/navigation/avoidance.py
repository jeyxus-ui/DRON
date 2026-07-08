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

    def _compute_safe_heading(self, sensor_data: dict, current_yaw: float) -> float:
        """Compute the safest heading to evade obstacles."""
        # 1. If obstacle_map provides a safe_direction, use it
        safe_dir = sensor_data.get('safe_direction')
        if safe_dir is not None:
            return safe_dir

        # 2. Use LIDAR closest_angle to steer away from nearest obstacle
        lidar = sensor_data.get('lidar', {})
        lidar_angle = lidar.get('closest_angle')
        lidar_dist = lidar.get('closest_distance')
        if lidar_angle is not None and lidar_dist is not None and lidar_dist < self.safety_distance * 2:
            opposite = (lidar_angle + 180) % 360
            return round(opposite, 1)

        # 3. If MTF01 sees obstacle ahead, turn 90° from current heading
        mtf = sensor_data.get('mtf01', {})
        mtf_dist = mtf.get('distance_m')
        if mtf_dist is not None and mtf_dist < self.safety_distance * 2:
            return (current_yaw + 90) % 360

        # 4. Default: keep current heading
        return current_yaw

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

        # ── CRITICAL: brake immediately ──
        if min_dist <= self.brake_distance:
            if now - self._last_brake_time > self.brake_cooldown:
                self._last_brake_time = now
                logger.warning('[AVOID] CRÍTICO — obstáculo a %.2fm — BRAKE', min_dist)
                return {
                    'action': 'BRAKE',
                    'reason': f'obstacle at {min_dist:.2f}m',
                    'distance': min_dist,
                }
            return {'action': 'NONE', 'reason': 'brake cooldown'}

        # ── CAUTION: obstacle within safety distance, compute evasion heading ──
        if min_dist <= self.safety_distance:
            safe_heading = self._compute_safe_heading(sensor_data, yaw)
            turn = safe_heading - yaw
            if turn > 180:
                turn -= 360
            elif turn < -180:
                turn += 360
            logger.info('[AVOID] Obstáculo a %.2fm — desvío heading %.1f° (giro %.0f°)',
                        min_dist, safe_heading, turn)
            return {
                'action': 'AVOID',
                'reason': f'obstacle at {min_dist:.2f}m',
                'distance': min_dist,
                'turn_deg': round(turn, 1),
                'safe_heading': round(safe_heading, 1),
            }

        return {'action': 'NONE', 'reason': 'clear'}
