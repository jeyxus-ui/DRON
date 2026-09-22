"""Tests unitarios para backend/navigation/avoidance.py — ObstacleAvoidance."""
import time
import pytest

from backend.navigation.avoidance import ObstacleAvoidance


@pytest.fixture
def avoid():
    return ObstacleAvoidance(safety_distance_m=2.0, brake_distance_m=1.0)


class TestActiveFlag:
    def test_is_active_true_by_default(self, avoid):
        assert avoid.is_active is True

    def test_set_active_false(self, avoid):
        avoid.set_active(False)
        assert avoid.is_active is False

    def test_evaluate_returns_none_when_disabled(self, avoid):
        avoid.set_active(False)
        result = avoid.evaluate({'mtf01': {'distance_m': 0.1}})
        assert result == {'action': 'NONE', 'reason': 'avoidance disabled'}


class TestEvaluateNoObstacle:
    def test_no_sensor_data_returns_none(self, avoid):
        result = avoid.evaluate({})
        assert result['action'] == 'NONE'

    def test_far_obstacle_returns_none(self, avoid):
        result = avoid.evaluate({'mtf01': {'distance_m': 10.0}})
        assert result['action'] == 'NONE'


class TestEvaluateBrake:
    def test_close_obstacle_triggers_brake(self, avoid):
        result = avoid.evaluate({'mtf01': {'distance_m': 0.5}})
        assert result['action'] == 'BRAKE'
        assert result['distance'] == 0.5
        assert result['source'] == 'mtf01'

    def test_brake_cooldown_returns_delayed(self, avoid):
        avoid.evaluate({'mtf01': {'distance_m': 0.5}})  # primer BRAKE real
        result = avoid.evaluate({'mtf01': {'distance_m': 0.5}})  # inmediato después
        assert result['action'] == 'BRAKE_DELAYED'

    def test_brake_fires_again_after_cooldown(self, avoid):
        avoid.brake_cooldown = 0.05
        avoid.evaluate({'mtf01': {'distance_m': 0.5}})
        time.sleep(0.06)
        result = avoid.evaluate({'mtf01': {'distance_m': 0.5}})
        assert result['action'] == 'BRAKE'

    def test_exactly_at_brake_distance_triggers_brake(self, avoid):
        result = avoid.evaluate({'mtf01': {'distance_m': 1.0}})
        assert result['action'] == 'BRAKE'


class TestEvaluateAvoid:
    def test_obstacle_in_safety_zone_returns_avoid(self, avoid):
        result = avoid.evaluate({'mtf01': {'distance_m': 1.5}, 'drone_yaw': 0.0})
        assert result['action'] == 'AVOID'
        assert result['distance'] == 1.5
        assert 'safe_heading' in result
        assert 'turn_deg' in result

    def test_avoid_uses_safe_direction_from_sensor_data(self, avoid):
        result = avoid.evaluate({
            'mtf01': {'distance_m': 1.5},
            'safe_direction': 270,
            'drone_yaw': 0.0,
        })
        assert result['safe_heading'] == 270

    def test_avoid_turn_deg_wraps_to_shortest_path_positive(self, avoid):
        # yaw=350, safe_heading=10 -> diferencia natural 340, debe normalizar a +20
        result = avoid.evaluate({
            'mtf01': {'distance_m': 1.5},
            'safe_direction': 10,
            'drone_yaw': 350.0,
        })
        assert result['turn_deg'] == pytest.approx(20.0)

    def test_avoid_turn_deg_wraps_to_shortest_path_negative(self, avoid):
        # yaw=10, safe_heading=350 -> diferencia natural -340, debe normalizar a -20
        result = avoid.evaluate({
            'mtf01': {'distance_m': 1.5},
            'safe_direction': 350,
            'drone_yaw': 10.0,
        })
        assert result['turn_deg'] == pytest.approx(-20.0)


class TestComputeSafeHeading:
    def test_lidar_used_when_close_enough(self, avoid):
        result = avoid.evaluate({
            'lidar': {'closest_distance': 1.5, 'closest_angle': 30},
            'drone_yaw': 0.0,
        })
        assert result['action'] == 'AVOID'
        assert result['safe_heading'] == pytest.approx(210.0)  # opuesto a 30°

    def test_mtf01_only_turns_right_by_default(self, avoid):
        result = avoid.evaluate({
            'mtf01': {'distance_m': 1.5},
            'drone_yaw': 0.0,
        })
        assert result['safe_heading'] == pytest.approx(90.0)

    def test_mtf01_prefers_left_when_lidar_closer_to_right(self, avoid):
        # lidar closest_angle=90 (coincide con el giro a la derecha) pero lejos
        # (>2x safety_distance) para no activar la rama LIDAR por sí sola.
        result = avoid.evaluate({
            'mtf01': {'distance_m': 1.5},
            'lidar': {'closest_angle': 90, 'closest_distance': 100.0},
            'drone_yaw': 0.0,
        })
        assert result['safe_heading'] == pytest.approx(270.0)  # izquierda, evita el lado derecho

    def test_default_keeps_current_heading_with_no_directional_hint(self, avoid):
        # Fuerza min_dist vía vision (sin mtf01/lidar) para llegar al branch default.
        result = avoid.evaluate({
            'vision': {'closest': {'distance_m': 1.5, 'zone': 'warning', 'angle_offset_deg': 0}},
            'drone_yaw': 123.0,
        })
        assert result['safe_heading'] == pytest.approx(123.0)


class TestVisionContribution:
    def test_vision_ignored_outside_frontal_arc(self, avoid):
        result = avoid.evaluate({
            'vision': {'closest': {'distance_m': 0.3, 'zone': 'critical', 'angle_offset_deg': 60}},
        })
        assert result['action'] == 'NONE'

    def test_vision_ignored_when_safe_zone(self, avoid):
        result = avoid.evaluate({
            'vision': {'closest': {'distance_m': 0.3, 'zone': 'safe', 'angle_offset_deg': 0}},
        })
        assert result['action'] == 'NONE'

    def test_vision_triggers_brake_within_frontal_arc(self, avoid):
        result = avoid.evaluate({
            'vision': {'closest': {'distance_m': 0.5, 'zone': 'critical', 'angle_offset_deg': 10}},
        })
        assert result['action'] == 'BRAKE'
        assert 'vision' in result['source']

    def test_closest_of_multiple_sources_wins(self, avoid):
        result = avoid.evaluate({
            'mtf01': {'distance_m': 1.8},
            'lidar': {'closest_distance': 0.5, 'closest_angle': 45},
        })
        assert result['distance'] == 0.5
        assert result['source'] == 'lidar'
