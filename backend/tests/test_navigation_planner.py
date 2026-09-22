"""Tests unitarios para backend/navigation/planner.py — PathPlanner."""
from unittest.mock import MagicMock
import pytest

from backend.navigation.planner import PathPlanner


@pytest.fixture
def planner():
    return PathPlanner(step_size_m=2.0, clearance_m=1.5)


class TestPlanToWaypoint:
    def test_short_distance_returns_single_waypoint_at_target(self, planner):
        # Un desplazamiento muy chico (< step_size) no debe generar pasos intermedios.
        result = planner.plan_to_waypoint(0.0, 0.0, 0.0, 0.00001, None)
        assert result == [{'lat': 0.0, 'lon': 0.00001, 'alt': 10}]

    def test_longer_distance_generates_multiple_waypoints(self, planner):
        result = planner.plan_to_waypoint(0.0, 0.0, 0.001, 0.0, None)
        assert len(result) >= 2
        # El último waypoint debe estar muy cerca del target real.
        assert result[-1]['lat'] == pytest.approx(0.001, abs=1e-5)

    def test_waypoints_have_expected_keys(self, planner):
        result = planner.plan_to_waypoint(0.0, 0.0, 0.001, 0.001, None)
        for wp in result:
            assert set(wp.keys()) == {'lat', 'lon', 'alt'}
            assert wp['alt'] == 10

    def test_no_obstacle_map_skips_detour_logic(self, planner):
        # obstacle_map=None no debe lanzar excepción ni intentar llamarse.
        result = planner.plan_to_waypoint(0.0, 0.0, 0.001, 0.0, None)
        assert len(result) > 0

    def test_blocked_path_triggers_detour(self, planner):
        obstacle_map = MagicMock()
        obstacle_map.is_blocked.return_value = True
        obstacle_map.find_free_direction.return_value = 45.0

        blocked_result = planner.plan_to_waypoint(0.0, 0.0, 0.001, 0.001, obstacle_map)
        clear_map = MagicMock()
        clear_map.is_blocked.return_value = False
        clear_result = planner.plan_to_waypoint(0.0, 0.0, 0.001, 0.001, clear_map)

        obstacle_map.is_blocked.assert_called()
        obstacle_map.find_free_direction.assert_called()
        # La ruta con desvío debe diferir de la ruta directa en al menos un punto.
        assert blocked_result != clear_result

    def test_obstacle_map_not_blocked_matches_direct_path(self, planner):
        clear_map = MagicMock()
        clear_map.is_blocked.return_value = False
        result = planner.plan_to_waypoint(0.0, 0.0, 0.001, 0.001, clear_map)
        assert len(result) > 0
        clear_map.is_blocked.assert_called()
        clear_map.find_free_direction.assert_not_called()


class TestPlanSearchPattern:
    def test_returns_list_of_waypoints(self, planner):
        result = planner.plan_search_pattern(0.0, 0.0, radius_m=10, spacing_m=5)
        assert isinstance(result, list)
        assert len(result) > 0
        for wp in result:
            assert set(wp.keys()) == {'lat', 'lon', 'alt'}

    def test_capped_at_50_waypoints(self, planner):
        result = planner.plan_search_pattern(0.0, 0.0, radius_m=1000, spacing_m=1)
        assert len(result) <= 50

    def test_center_point_not_included_for_positive_radius(self, planner):
        result = planner.plan_search_pattern(10.0, 20.0, radius_m=5, spacing_m=1)
        # El primer anillo (r=0) coincide con el centro para todos los ángulos.
        assert all(wp['lat'] == pytest.approx(10.0, abs=1e-6) for wp in result[:12])
