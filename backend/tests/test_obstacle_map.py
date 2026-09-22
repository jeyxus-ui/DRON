"""Tests unitarios para backend/sensors/obstacle_map.py — ObstacleMap."""
from types import SimpleNamespace
import pytest

from backend.sensors.obstacle_map import ObstacleMap


@pytest.fixture
def omap():
    return ObstacleMap(width_m=10.0, height_m=10.0, resolution_m=1.0)


def lidar_point(angle_deg, distance_m, quality=100):
    return SimpleNamespace(angle_deg=angle_deg, distance_m=distance_m, quality=quality)


class TestWorldToGrid:
    def test_origin_maps_to_center(self, omap):
        gx, gy = omap._world_to_grid(0.0, 0.0)
        assert gx == omap.center_x
        assert gy == omap.center_y

    def test_out_of_bounds_clamps_to_edges(self, omap):
        gx, gy = omap._world_to_grid(1000.0, -1000.0)
        assert gx == omap.cols - 1
        assert gy == 0


class TestUpdateFromLidar:
    def test_valid_point_increases_occupancy(self, omap):
        omap.update_from_lidar([lidar_point(0, 3.0)], drone_yaw_deg=0.0)
        assert omap.get_occupancy(3.0, 0.0) > 0

    def test_too_close_point_ignored(self, omap):
        omap.update_from_lidar([lidar_point(0, 0.05)], drone_yaw_deg=0.0)
        assert all(v == 0.0 for row in omap.grid for v in row)

    def test_too_far_point_ignored(self, omap):
        omap.update_from_lidar([lidar_point(0, 20.0)], drone_yaw_deg=0.0)
        assert all(v == 0.0 for row in omap.grid for v in row)

    def test_clears_ray_between_drone_and_point(self, omap):
        # Pre-cargar una celda intermedia como si tuviera algo de ocupación.
        omap.grid[omap.center_y][omap.center_x + 1] = 0.5
        omap.update_from_lidar([lidar_point(0, 4.0)], drone_yaw_deg=0.0)
        # La celda intermedia debe haber decrecido (ray clearing).
        assert omap.grid[omap.center_y][omap.center_x + 1] < 0.5


class TestUpdateFromUltrasonic:
    def test_valid_distance_increases_occupancy(self, omap):
        omap.update_from_ultrasonic(3.0, drone_yaw_deg=0.0)
        assert omap.get_occupancy(3.0, 0.0) > 0

    def test_zero_or_negative_distance_ignored(self, omap):
        omap.update_from_ultrasonic(0.0, drone_yaw_deg=0.0)
        omap.update_from_ultrasonic(-1.0, drone_yaw_deg=0.0)
        assert all(v == 0.0 for row in omap.grid for v in row)


class TestOccupancyAndBlocked:
    def test_is_blocked_respects_threshold(self, omap):
        omap.grid[omap.center_y][omap.center_x] = 0.4
        assert omap.is_blocked(0.0, 0.0, threshold=0.5) is False
        omap.grid[omap.center_y][omap.center_x] = 0.6
        assert omap.is_blocked(0.0, 0.0, threshold=0.5) is True


class TestFindFreeDirection:
    def test_returns_current_heading_when_clear(self, omap):
        assert omap.find_free_direction(0.0, min_clearance_m=2.0) == 0.0

    def test_returns_alternate_when_forward_blocked(self, omap):
        # Bloquear directamente las celdas del eje frontal (0°) dentro del
        # rango de clearance chequeado (evita el auto-clear de _clear_ray
        # que tendría update_from_ultrasonic al llamarlo varias veces).
        for d in range(1, 3):  # min_clearance_m=2.0, resolution=1.0 → celdas d=1,2
            gx, gy = omap._world_to_grid(float(d), 0.0)
            omap.grid[gy][gx] = 1.0
        result = omap.find_free_direction(0.0, min_clearance_m=2.0)
        assert result != 0.0

    def test_returns_180_fallback_when_fully_surrounded(self, omap):
        # Saturar todo el grid como bloqueado.
        omap.grid = [[1.0] * omap.cols for _ in range(omap.rows)]
        result = omap.find_free_direction(10.0, min_clearance_m=1.0)
        assert result == 190.0


class TestDecay:
    def test_multiplies_all_cells(self, omap):
        omap.grid[0][0] = 1.0
        omap.decay(0.5)
        assert omap.grid[0][0] == 0.5


class TestToDict:
    def test_shape_and_keys(self, omap):
        result = omap.to_dict()
        assert set(result.keys()) == {'width_m', 'height_m', 'resolution', 'obstacles', 'last_update'}
        assert result['obstacles'] == []

    def test_includes_high_occupancy_cells(self, omap):
        omap.grid[omap.center_y][omap.center_x] = 0.9
        result = omap.to_dict()
        assert len(result['obstacles']) >= 1

    def test_caps_obstacles_at_200(self, omap):
        big = ObstacleMap(width_m=100.0, height_m=100.0, resolution_m=1.0)
        big.grid = [[1.0] * big.cols for _ in range(big.rows)]
        result = big.to_dict()
        assert len(result['obstacles']) <= 200


class TestUpdateFromVision:
    def test_object_style_detection(self, omap):
        det = SimpleNamespace(distance=3.0, bbox=(100, 100, 200, 200), zone='critical')
        omap.update_from_vision([det], drone_yaw_deg=0.0, frame_width=640)
        assert omap.last_update > 0

    def test_dict_style_detection(self, omap):
        det = {'distance': 3.0, 'bbox': {'x1': 100, 'y1': 100, 'x2': 200, 'y2': 200}, 'zone': 'warning'}
        omap.update_from_vision([det], drone_yaw_deg=0.0, frame_width=640)
        assert omap.last_update > 0

    def test_out_of_range_distance_skipped(self, omap):
        det = SimpleNamespace(distance=999, bbox=(0, 0, 10, 10), zone='safe')
        omap.update_from_vision([det], drone_yaw_deg=0.0)
        assert all(v == 0.0 for row in omap.grid for v in row)

    def test_bad_bbox_is_skipped_without_raising(self, omap):
        det = SimpleNamespace(distance=3.0, bbox=None, zone='safe')
        omap.update_from_vision([det], drone_yaw_deg=0.0)  # no debe propagar

    def test_critical_zone_weighs_more_than_default(self, omap):
        det_critical = SimpleNamespace(distance=3.0, bbox=(300, 220, 340, 260), zone='critical')
        omap.update_from_vision([det_critical], drone_yaw_deg=0.0, frame_width=640)
        critical_value = max(v for row in omap.grid for v in row)

        omap2 = ObstacleMap(width_m=10.0, height_m=10.0, resolution_m=1.0)
        det_safe = SimpleNamespace(distance=3.0, bbox=(300, 220, 340, 260), zone='safe')
        omap2.update_from_vision([det_safe], drone_yaw_deg=0.0, frame_width=640)
        safe_value = max(v for row in omap2.grid for v in row)

        assert critical_value > safe_value


class TestReset:
    def test_clears_grid(self, omap):
        omap.grid[0][0] = 1.0
        omap.reset()
        assert all(v == 0.0 for row in omap.grid for v in row)
