"""Tests unitarios para backend/navigation/controller.py — NavigationController."""
from unittest.mock import MagicMock
import pytest

from backend.navigation.controller import NavigationController


def make_nc(telemetry=None, avoid_result=None, sensor_data=None):
    mav = MagicMock()
    mav.get_telemetry.return_value = telemetry or {
        'gps': {'lat': 0.0, 'lon': 0.0}, 'altitude': 10.0, 'attitude': {'yaw': 0.0},
    }
    sensors = MagicMock()
    sensors.get_data.return_value = sensor_data or {}
    sensors.obstacle_map = None
    avoidance = MagicMock()
    avoidance.evaluate.return_value = avoid_result or {'action': 'NONE'}
    avoidance.is_active = True
    planner = MagicMock()
    planner.plan_to_waypoint.return_value = []
    return NavigationController(mav, sensors, avoidance, planner), mav, sensors, avoidance, planner


@pytest.fixture
def nc():
    return make_nc()[0]


# ── API pública ──────────────────────────────────────────────────────────────

class TestPublicApi:
    def test_initial_mode_is_idle(self, nc):
        assert nc.mode == 'IDLE'

    def test_navigate_to_sets_mode_and_target(self, nc):
        nc.navigate_to(1.0, 2.0, 15.0)
        assert nc.mode == 'NAVIGATING'
        assert nc._target == {'lat': 1.0, 'lon': 2.0, 'alt': 15.0}
        assert nc._planned_path == []

    def test_navigate_to_default_altitude(self, nc):
        nc.navigate_to(1.0, 2.0)
        assert nc._target['alt'] == 10.0

    def test_start_mission_sets_mode_and_waypoints(self, nc):
        wps = [{'lat': 1.0, 'lon': 1.0}, {'lat': 2.0, 'lon': 2.0}]
        nc.start_mission(wps)
        assert nc.mode == 'MISSION'
        assert nc._waypoints == wps
        assert nc._wp_index == 0

    def test_stop_navigation_resets_state(self, nc):
        nc.navigate_to(1.0, 2.0)
        nc.stop_navigation()
        assert nc.mode == 'IDLE'
        assert nc._target is None
        assert nc._planned_path == []
        assert nc._waypoints == []
        assert nc._avoid_target is None

    def test_get_status_shape(self, nc):
        nc.navigate_to(1.0, 2.0)
        status = nc.get_status()
        assert status == {
            'mode': 'NAVIGATING',
            'target': {'lat': 1.0, 'lon': 2.0, 'alt': 10.0},
            'waypoint_index': 0,
            'total_waypoints': 0,
            'avoidance_active': True,
            'planned_path_length': 0,
        }

    def test_set_emergency_callback(self, nc):
        cb = MagicMock()
        nc.set_emergency_callback(cb)
        assert nc._on_emergency is cb

    def test_start_launches_thread(self, nc):
        nc.start()
        try:
            assert nc._running is True
            assert nc._thread is not None
            assert nc._thread.is_alive()
        finally:
            nc.stop()
            nc._thread.join(timeout=1)

    def test_stop_sets_running_false(self, nc):
        nc.start()
        nc.stop()
        assert nc._running is False


# ── Helpers estáticos ────────────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert NavigationController._haversine(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0, abs=1e-6)

    def test_one_degree_latitude_is_about_111km(self):
        dist = NavigationController._haversine(0.0, 0.0, 1.0, 0.0)
        assert dist == pytest.approx(111194.9, rel=1e-3)

    def test_symmetric(self):
        d1 = NavigationController._haversine(10.0, 20.0, 10.001, 20.001)
        d2 = NavigationController._haversine(10.001, 20.001, 10.0, 20.0)
        assert d1 == pytest.approx(d2)


class TestAngleDiff:
    def test_same_angle_is_zero(self):
        assert NavigationController._angle_diff(90, 90) == 0

    def test_opposite_angles_is_180(self):
        assert NavigationController._angle_diff(0, 180) == 180

    def test_wraps_around_360(self):
        assert NavigationController._angle_diff(350, 10) == pytest.approx(20.0)

    def test_symmetric_regardless_of_order(self):
        assert NavigationController._angle_diff(10, 350) == NavigationController._angle_diff(350, 10)


class TestOffsetPosition:
    def test_heading_north_increases_latitude_only(self):
        lat, lon = NavigationController._offset_position(0.0, 0.0, 1000.0, 0.0)
        assert lat > 0
        assert lon == pytest.approx(0.0, abs=1e-9)

    def test_heading_east_increases_longitude_only(self):
        lat, lon = NavigationController._offset_position(0.0, 0.0, 1000.0, 90.0)
        assert lon > 0
        assert lat == pytest.approx(0.0, abs=1e-6)


class TestCanSendGoto:
    def test_first_call_true(self, nc):
        assert nc._can_send_goto() is True

    def test_immediate_second_call_false(self, nc):
        nc._can_send_goto()
        assert nc._can_send_goto() is False


class TestSendGoto:
    def test_calls_mav_goto(self, nc):
        nc.mav.goto = MagicMock()
        nc._send_goto(1.0, 2.0, 3.0)
        nc.mav.goto.assert_called_once_with(1.0, 2.0, 3.0)

    def test_swallows_exception(self, nc):
        nc.mav.goto = MagicMock(side_effect=Exception('boom'))
        nc._send_goto(1.0, 2.0, 3.0)  # no debe propagar


class TestNextMode:
    def test_returns_navigating_if_target_set(self, nc):
        nc._target = {'lat': 1, 'lon': 1}
        assert nc._next_mode() == 'NAVIGATING'

    def test_returns_mission_if_waypoints_remaining(self, nc):
        nc._waypoints = [{'lat': 1, 'lon': 1}]
        nc._wp_index = 0
        assert nc._next_mode() == 'MISSION'

    def test_returns_idle_otherwise(self, nc):
        assert nc._next_mode() == 'IDLE'


# ── Ejecución de navegación/misión ───────────────────────────────────────────

class TestExecNav:
    def test_no_target_is_noop(self, nc):
        nc._exec_nav({'lat': 0.0, 'lon': 0.0, 'alt': 0.0, 'yaw': 0.0})
        nc.mav.goto.assert_not_called()

    def test_target_reached_clears_target_and_sets_idle(self, nc):
        nc._mode = 'NAVIGATING'
        nc._target = {'lat': 0.0, 'lon': 0.0, 'alt': 10.0}
        nc._exec_nav({'lat': 0.0000001, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        assert nc._target is None
        assert nc.mode == 'IDLE'

    def test_target_not_reached_plans_path(self, nc):
        nc._target = {'lat': 1.0, 'lon': 1.0, 'alt': 10.0}
        nc.planner.plan_to_waypoint.return_value = [{'lat': 0.5, 'lon': 0.5, 'alt': 10}]
        nc._exec_nav({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        nc.planner.plan_to_waypoint.assert_called_once()
        assert nc._planned_path == [{'lat': 0.5, 'lon': 0.5, 'alt': 10}]

    def test_sends_goto_towards_planned_waypoint(self, nc):
        nc._target = {'lat': 1.0, 'lon': 1.0, 'alt': 10.0}
        nc._planned_path = [{'lat': 0.5, 'lon': 0.5, 'alt': 10}]
        nc._path_index = 0
        nc.mav.goto = MagicMock()
        nc._exec_nav({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        nc.mav.goto.assert_called_once_with(0.5, 0.5, 10)

    def test_advances_path_index_when_waypoint_reached(self, nc):
        nc._target = {'lat': 1.0, 'lon': 1.0, 'alt': 10.0}
        nc._planned_path = [
            {'lat': 0.0000001, 'lon': 0.0, 'alt': 10},
            {'lat': 0.5, 'lon': 0.5, 'alt': 10},
        ]
        nc._path_index = 0
        nc.mav.goto = MagicMock()
        nc._exec_nav({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        assert nc._path_index == 1
        nc.mav.goto.assert_called_once_with(0.5, 0.5, 10)

    def test_clears_planned_path_when_exhausted(self, nc):
        nc._target = {'lat': 1.0, 'lon': 1.0, 'alt': 10.0}
        nc._planned_path = [{'lat': 0.0000001, 'lon': 0.0, 'alt': 10}]
        nc._path_index = 0
        nc._exec_nav({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        assert nc._planned_path == []


class TestExecMission:
    def test_no_waypoints_sets_idle(self, nc):
        nc._mode = 'MISSION'
        nc._exec_mission({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        assert nc.mode == 'IDLE'

    def test_waypoint_reached_advances_index(self, nc):
        nc._waypoints = [{'lat': 0.0000001, 'lon': 0.0}, {'lat': 1.0, 'lon': 1.0}]
        nc._wp_index = 0
        nc._exec_mission({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        assert nc._wp_index == 1

    def test_waypoint_not_reached_sends_goto(self, nc):
        nc._waypoints = [{'lat': 5.0, 'lon': 5.0}]
        nc._wp_index = 0
        nc.mav.goto = MagicMock()
        nc._exec_mission({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})
        nc.mav.goto.assert_called_once()

    def test_all_waypoints_done_clears_and_sets_idle(self, nc):
        nc._waypoints = [{'lat': 0.0000001, 'lon': 0.0}]
        nc._wp_index = 0
        nc._exec_mission({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})  # avanza a index 1 (fuera de rango)
        nc._exec_mission({'lat': 0.0, 'lon': 0.0, 'alt': 10.0, 'yaw': 0.0})  # detecta fin de misión
        assert nc.mode == 'IDLE'
        assert nc._waypoints == []


# ── _nav_loop (una sola iteración, sin hilo real) ────────────────────────────

class TestNavLoopSingleIteration:
    def _run_one_iteration(self, nc, monkeypatch):
        """Ejecuta _nav_loop hasta completar exactamente una vuelta del while,
        sin sleeps reales ni hilo de fondo."""
        monkeypatch.setattr('backend.navigation.controller.time.sleep', lambda s: None)
        nc._running = True
        return_value = nc.sensors.get_data.return_value

        def stop_after_one(*a, **kw):
            nc._running = False
            return return_value

        nc.sensors.get_data.side_effect = stop_after_one
        nc._nav_loop()

    def test_brake_action_sets_mode_avoiding_and_calls_set_mode(self, monkeypatch):
        nc, mav, sensors, avoidance, planner = make_nc(
            avoid_result={'action': 'BRAKE', 'distance': 0.3}
        )
        self._run_one_iteration(nc, monkeypatch)
        mav.set_mode.assert_called_with('BRAKE')
        assert nc.mode == 'AVOIDING'

    def test_brake_triggers_emergency_callback(self, monkeypatch):
        nc, mav, sensors, avoidance, planner = make_nc(
            avoid_result={'action': 'BRAKE', 'distance': 0.3}
        )
        cb = MagicMock()
        nc.set_emergency_callback(cb)
        self._run_one_iteration(nc, monkeypatch)
        cb.assert_called_once_with('BRAKE', {'action': 'BRAKE', 'distance': 0.3})

    def test_avoid_action_sets_avoid_target_and_mode(self, monkeypatch):
        nc, mav, sensors, avoidance, planner = make_nc(
            avoid_result={'action': 'AVOID', 'distance': 1.5, 'safe_heading': 90.0}
        )
        self._run_one_iteration(nc, monkeypatch)
        assert nc.mode == 'AVOIDING'
        assert nc._avoid_target is not None

    def test_none_action_dispatches_to_exec_nav(self, monkeypatch):
        nc, mav, sensors, avoidance, planner = make_nc(avoid_result={'action': 'NONE'})
        nc.navigate_to(5.0, 5.0, 10.0)
        mav.goto = MagicMock()
        self._run_one_iteration(nc, monkeypatch)
        # _exec_nav debió intentar planificar/enviar hacia el target
        assert planner.plan_to_waypoint.called or mav.goto.called

    def test_none_action_dispatches_to_exec_mission(self, monkeypatch):
        nc, mav, sensors, avoidance, planner = make_nc(avoid_result={'action': 'NONE'})
        nc.start_mission([{'lat': 5.0, 'lon': 5.0}])
        mav.goto = MagicMock()
        self._run_one_iteration(nc, monkeypatch)
        mav.goto.assert_called()

    def test_exception_in_loop_body_does_not_propagate(self, monkeypatch):
        nc, mav, sensors, avoidance, planner = make_nc()
        sensors.get_data.side_effect = Exception('sensor failure')
        nc._running = True
        monkeypatch.setattr('backend.navigation.controller.time.sleep',
                             lambda s: setattr(nc, '_running', False))
        nc._nav_loop()  # no debe propagar la excepción
