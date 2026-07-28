"""
Simple 2D grid map for real-time obstacle mapping.
Builds a local occupancy grid from LiDAR scans and ultrasonic readings.
"""
import logging
import math
import time

logger = logging.getLogger(__name__)


class ObstacleMap:
    def __init__(self, width_m: float = 20.0, height_m: float = 20.0, resolution_m: float = 0.2):
        self.width_m = width_m
        self.height_m = height_m
        self.resolution = resolution_m
        self.cols = round(width_m / resolution_m)
        self.rows = round(height_m / resolution_m)
        self.center_x = self.cols // 2
        self.center_y = self.rows // 2
        self.grid = [[0.0] * self.cols for _ in range(self.rows)]
        self.last_update = 0.0

    def _world_to_grid(self, x_m: float, y_m: float):
        gx = int((x_m + self.width_m / 2) / self.resolution)
        gy = int((y_m + self.height_m / 2) / self.resolution)
        return max(0, min(self.cols - 1, gx)), max(0, min(self.rows - 1, gy))

    def update_from_lidar(self, points, drone_yaw_deg: float = 0.0):
        yaw_rad = math.radians(drone_yaw_deg)
        for p in points:
            if p.distance_m <= 0.12 or p.distance_m > 10.0:
                continue
            angle_rad = math.radians(p.angle_deg) + yaw_rad
            x = p.distance_m * math.cos(angle_rad)
            y = p.distance_m * math.sin(angle_rad)
            gx, gy = self._world_to_grid(x, y)
            self.grid[gy][gx] = min(1.0, self.grid[gy][gx] + 0.3)
            self._clear_ray(0, 0, x, y)

    def update_from_ultrasonic(self, distance_m: float, drone_yaw_deg: float):
        if distance_m <= 0:
            return
        yaw_rad = math.radians(drone_yaw_deg)
        x = distance_m * math.cos(yaw_rad)
        y = distance_m * math.sin(yaw_rad)
        gx, gy = self._world_to_grid(x, y)
        self.grid[gy][gx] = min(1.0, self.grid[gy][gx] + 0.5)
        self._clear_ray(0, 0, x, y)

    def _clear_ray(self, x0, y0, x1, y1):
        steps = max(abs(x1 - x0), abs(y1 - y0)) / self.resolution
        steps = max(1, int(steps))
        for i in range(1, steps):
            frac = i / steps
            x = x0 + (x1 - x0) * frac
            y = y0 + (y1 - y0) * frac
            gx, gy = self._world_to_grid(x, y)
            if 0 <= gx < self.cols and 0 <= gy < self.rows:
                self.grid[gy][gx] = max(0.0, self.grid[gy][gx] - 0.1)

    def get_occupancy(self, x_m: float, y_m: float) -> float:
        gx, gy = self._world_to_grid(x_m, y_m)
        return self.grid[gy][gx]

    def is_blocked(self, x_m: float, y_m: float, threshold: float = 0.5) -> bool:
        return self.get_occupancy(x_m, y_m) >= threshold

    def find_free_direction(self, drone_yaw_deg: float, min_clearance_m: float = 2.0) -> float:
        for offset in [0, 30, -30, 60, -60, 90, -90, 120, -120, 180]:
            test_angle = drone_yaw_deg + offset
            blocked = False
            for d in range(1, int(min_clearance_m / self.resolution) + 1):
                dist = d * self.resolution
                rad = math.radians(test_angle)
                x = dist * math.cos(rad)
                y = dist * math.sin(rad)
                if self.is_blocked(x, y):
                    blocked = True
                    break
            if not blocked:
                return test_angle
        return drone_yaw_deg + 180

    def decay(self, factor: float = 0.99):
        for row in self.grid:
            for i in range(len(row)):
                row[i] *= factor

    def to_dict(self) -> dict:
        obstacles = []
        for gy in range(0, self.rows, max(1, self.rows // 10)):
            for gx in range(0, self.cols, max(1, self.cols // 10)):
                if self.grid[gy][gx] > 0.5:
                    x_m = (gx - self.center_x) * self.resolution
                    y_m = (gy - self.center_y) * self.resolution
                    obstacles.append({'x': round(x_m, 2), 'y': round(y_m, 2), 'occupancy': round(self.grid[gy][gx], 2)})
        return {
            'width_m': self.width_m,
            'height_m': self.height_m,
            'resolution': self.resolution,
            'obstacles': obstacles[:200],
            'last_update': self.last_update,
        }

    def reset(self):
        self.grid = [[0.0] * self.cols for _ in range(self.rows)]
