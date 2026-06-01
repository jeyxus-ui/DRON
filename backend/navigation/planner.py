"""
Simple path planner that generates waypoints avoiding known obstacles.
Uses the obstacle map to find clear paths.
"""
import logging
import math
from typing import List, Tuple

logger = logging.getLogger(__name__)


class PathPlanner:
    def __init__(self, step_size_m: float = 2.0, clearance_m: float = 1.5):
        self.step_size = step_size_m
        self.clearance = clearance_m

    def plan_to_waypoint(self, start_lat: float, start_lon: float,
                          target_lat: float, target_lon: float,
                          obstacle_map) -> List[dict]:
        dx = (target_lon - start_lon) * 111320.0 * math.cos(math.radians((start_lat + target_lat) / 2))
        dy = (target_lat - start_lat) * 111320.0
        total_dist = math.sqrt(dx**2 + dy**2)
        if total_dist < self.step_size:
            return [{'lat': target_lat, 'lon': target_lon, 'alt': 10}]
        steps = max(2, int(total_dist / self.step_size))
        waypoints = []
        for i in range(1, steps + 1):
            frac = i / steps
            lon = start_lon + (target_lon - start_lon) * frac
            lat = start_lat + (target_lat - start_lat) * frac
            local_x = (lon - start_lon) * 111320.0 * math.cos(math.radians(lat))
            local_y = (lat - start_lat) * 111320.0
            if obstacle_map and obstacle_map.is_blocked(local_x, local_y, threshold=0.5):
                safe_heading = obstacle_map.find_free_direction(
                    math.degrees(math.atan2(dy, dx)),
                    min_clearance_m=self.clearance,
                )
                detour_rad = math.radians(safe_heading)
                lon += (2.0 * math.cos(detour_rad)) / (111320.0 * math.cos(math.radians(lat)))
                lat += (2.0 * math.sin(detour_rad)) / 111320.0
                logger.info('[PLANNER] Desvío en paso %d — nuevo heading %.0f°', i, safe_heading)
            waypoints.append({'lat': round(lat, 6), 'lon': round(lon, 6), 'alt': 10})
        return waypoints

    def plan_search_pattern(self, center_lat: float, center_lon: float,
                            radius_m: float, spacing_m: float) -> List[dict]:
        waypoints = []
        lat_per_m = 1.0 / 111320.0
        lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(center_lat)))
        for r in range(0, int(radius_m), int(spacing_m)):
            for theta_deg in range(0, 360, 30):
                rad = math.radians(theta_deg)
                lon = center_lon + r * math.cos(rad) * lon_per_m
                lat = center_lat + r * math.sin(rad) * lat_per_m
                waypoints.append({'lat': round(lat, 6), 'lon': round(lon, 6), 'alt': 10})
        return waypoints[:50]
