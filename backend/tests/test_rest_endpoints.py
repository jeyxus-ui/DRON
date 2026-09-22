"""Tests unitarios para backend/api/rest.py — endpoints REST del dron."""
import time
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app
import backend.api.rest as rest

client = TestClient(app)

ADMIN_USER = "test_admin_rest"
ADMIN_PASS = "TestPass1234"


@pytest.fixture(autouse=True)
def _isolated_users(tmp_path, monkeypatch):
    from backend.api import auth
    monkeypatch.setattr(auth.store, "path", tmp_path / "users.json")
    auth.rate_limiter._records.clear()
    auth.sessions._sessions.clear()
    auth.ensure_admin_user(ADMIN_USER, ADMIN_PASS)


@pytest.fixture(autouse=True)
def _reset_rest_globals(monkeypatch):
    """Cada test arranca con mav/sensor_manager/nav_controller en None,
    salvo que el propio test los setee."""
    monkeypatch.setattr(rest, 'mav', None)
    monkeypatch.setattr(rest, 'sensor_manager', None)
    monkeypatch.setattr(rest, 'nav_controller', None)
    monkeypatch.setattr(rest, '_external_sensor_data', {})
    monkeypatch.setattr(rest, '_external_mavlink_data', {})
    monkeypatch.setattr(rest, '_external_update_time', 0.0)


@pytest.fixture
def auth_headers():
    r = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_ctrl(monkeypatch):
    ctrl = MagicMock()
    ctrl.is_connected.return_value = True
    ctrl.is_armed.return_value = False
    ctrl.get_mode.return_value = "STABILIZE"
    ctrl.get_system_status.return_value = 4
    monkeypatch.setattr(rest, 'mav', ctrl)
    return ctrl


# ── Auth / disponibilidad de MAVLink ─────────────────────────────────────────

class TestAuthAndAvailability:
    def test_status_without_mav_returns_error(self, auth_headers, monkeypatch):
        # NOTA — dos comportamientos preexistentes documentados acá, no
        # corregidos (fuera del alcance de este trabajo de cobertura):
        # 1) get_mav_controller() lanza HTTPException(503), pero el except
        #    Exception genérico de cada endpoint la re-envuelve como 500
        #    (HTTPException es subclase de Exception).
        # 2) Esa re-envoltura usa detail=str(e) — y str(HTTPException(...))
        #    devuelve '' en esta versión de Starlette (no incluye .detail
        #    en __str__) — el mensaje original se pierde por completo.
        # Se mockea get_mav_controller directamente (en vez de depender del
        # global 'mav') porque el startup real de la app corre un hilo de
        # fondo que puede reasignar 'mav' en paralelo durante la suite completa.
        from fastapi import HTTPException

        def raise_unavailable():
            raise HTTPException(status_code=503, detail="MAVLink no conectado")

        monkeypatch.setattr(rest, 'get_mav_controller', raise_unavailable)
        r = client.get("/api/status", headers=auth_headers)
        assert r.status_code == 500
        assert r.json()["detail"] == ""

    def test_status_requires_auth(self):
        r = client.get("/api/status")
        assert r.status_code == 401


class TestStatus:
    def test_status_returns_controller_data(self, auth_headers, mock_ctrl):
        r = client.get("/api/status", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data == {"connected": True, "armed": False, "mode": "STABILIZE", "system_status": 4}

    def test_status_exception_returns_500(self, auth_headers, mock_ctrl):
        mock_ctrl.is_connected.side_effect = RuntimeError("boom")
        r = client.get("/api/status", headers=auth_headers)
        assert r.status_code == 500


class TestTelemetry:
    def test_telemetry_uses_external_data_when_recent(self, auth_headers, monkeypatch):
        monkeypatch.setattr(rest, '_external_mavlink_data', {"armed": True, "mode": "GUIDED"})
        monkeypatch.setattr(rest, '_external_update_time', time.time())
        r = client.get("/api/telemetry", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["_source"] == "external"
        assert r.json()["armed"] is True

    def test_telemetry_falls_back_to_mav_when_external_stale(self, auth_headers, mock_ctrl, monkeypatch):
        monkeypatch.setattr(rest, '_external_mavlink_data', {"armed": True})
        monkeypatch.setattr(rest, '_external_update_time', time.time() - 60)  # > 30s, vencido
        mock_ctrl.telemetry = None
        mock_ctrl.get_telemetry.return_value = {
            "gps": {"lat": 1.0, "lon": 2.0}, "altitude": 5.0, "attitude": {"yaw": 90.0},
            "battery": {"voltage": 12.0, "remaining": 80},
        }
        r = client.get("/api/telemetry", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["latitude"] == 1.0
        assert data["altitude"] == 5.0

    def test_telemetry_uses_telemetry_object_when_present(self, auth_headers, mock_ctrl):
        tel = MagicMock()
        tel.get_attitude.return_value = {"roll": 1, "pitch": 2, "yaw": 3}
        tel.get_gps.return_value = {"lat": 10.0, "lon": 20.0, "satellites": 8, "hdop": 1.2}
        tel.get_battery.return_value = {"voltage": 12.4, "remaining": 90}
        tel.get_velocity.return_value = {"ground_speed": 1.5, "vertical_speed": 0.2}
        tel.data = {"altitude": 15.0}
        mock_ctrl.telemetry = tel
        r = client.get("/api/telemetry", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["latitude"] == 10.0
        assert data["hdop"] == 1.2

    def test_telemetry_caps_bad_hdop(self, auth_headers, mock_ctrl):
        tel = MagicMock()
        tel.get_attitude.return_value = {}
        tel.get_gps.return_value = {"hdop": 999}
        tel.get_battery.return_value = {}
        tel.get_velocity.return_value = {}
        tel.data = {}
        mock_ctrl.telemetry = tel
        r = client.get("/api/telemetry", headers=auth_headers)
        assert r.json()["hdop"] == 0


# ── Control básico ────────────────────────────────────────────────────────────

class TestArmDisarm:
    def test_arm_success(self, auth_headers, mock_ctrl):
        mock_ctrl.arm.return_value = True
        r = client.post("/api/arm", json={"force": True}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_arm_already_armed_without_force(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = True
        r = client.post("/api/arm", json={"force": False}, headers=auth_headers)
        assert r.json() == {"success": False, "message": "Dron ya está armado"}

    def test_disarm_already_disarmed(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = False
        r = client.post("/api/disarm", headers=auth_headers)
        assert r.json() == {"success": False, "message": "Dron ya está desarmado"}

    def test_disarm_success_notifies_rc(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = True
        mock_ctrl.disarm.return_value = True
        rc = MagicMock()
        mock_ctrl.rc = rc
        r = client.post("/api/disarm", headers=auth_headers)
        assert r.json()["success"] is True
        rc.set_armed.assert_called_with(False)


class TestTakeoff:
    def test_takeoff_requires_armed(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = False
        r = client.post("/api/takeoff", json={"altitude": 10}, headers=auth_headers)
        assert r.json() == {"success": False, "message": "Dron no está armado"}

    def test_takeoff_rejects_altitude_out_of_range(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = True
        r = client.post("/api/takeoff", json={"altitude": 500}, headers=auth_headers)
        assert r.json()["success"] is False

    def test_takeoff_success(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = True
        mock_ctrl.takeoff.return_value = True
        r = client.post("/api/takeoff", json={"altitude": 10}, headers=auth_headers)
        assert r.json()["success"] is True


class TestLandRtl:
    def test_land(self, auth_headers, mock_ctrl):
        mock_ctrl.land.return_value = True
        r = client.post("/api/land", headers=auth_headers)
        assert r.json()["success"] is True

    def test_rtl(self, auth_headers, mock_ctrl):
        mock_ctrl.return_to_launch.return_value = False
        r = client.post("/api/rtl", headers=auth_headers)
        assert r.json()["success"] is False


# ── RC ─────────────────────────────────────────────────────────────────────

class TestRcEndpoints:
    def test_rc_control_no_rc_available(self, auth_headers, mock_ctrl):
        mock_ctrl.rc = None
        r = client.post("/api/rc/control", json={"throttle": 0.5}, headers=auth_headers)
        assert r.json() == {"success": False, "message": "RC Controller no inicializado"}

    def test_rc_control_success(self, auth_headers, mock_ctrl):
        rc = MagicMock()
        rc.get_current_values.return_value = {"throttle": 0.5}
        mock_ctrl.rc = rc
        r = client.post("/api/rc/control", json={"throttle": 0.5, "yaw": 0.1}, headers=auth_headers)
        assert r.json()["success"] is True
        rc.set_controls.assert_called_once_with(throttle=0.5, yaw=0.1, pitch=None, roll=None)

    def test_rc_reset_without_rc(self, auth_headers, mock_ctrl):
        mock_ctrl.rc = None
        r = client.post("/api/rc/reset", headers=auth_headers)
        assert r.json()["success"] is False

    def test_rc_values_with_rc(self, auth_headers, mock_ctrl):
        rc = MagicMock()
        rc.get_current_values.return_value = {"throttle": 0.0}
        mock_ctrl.rc = rc
        r = client.get("/api/rc/values", headers=auth_headers)
        assert r.json() == {"success": True, "values": {"throttle": 0.0}}


# ── Emergencia ────────────────────────────────────────────────────────────────

class TestEmergency:
    def test_stop_brake_success(self, auth_headers, mock_ctrl):
        mock_ctrl.set_mode.return_value = True
        r = client.post("/api/emergency", json={"action": "stop"}, headers=auth_headers)
        assert r.json()["success"] is True
        mock_ctrl.set_mode.assert_called_with("BRAKE")

    def test_stop_falls_back_to_loiter_when_brake_fails(self, auth_headers, mock_ctrl):
        mock_ctrl.set_mode.side_effect = [False, True]
        r = client.post("/api/emergency", json={"action": "STOP"}, headers=auth_headers)
        assert r.json()["success"] is True
        assert mock_ctrl.set_mode.call_count == 2

    def test_rtl_action(self, auth_headers, mock_ctrl):
        mock_ctrl.return_to_launch.return_value = True
        r = client.post("/api/emergency", json={"action": "RTL"}, headers=auth_headers)
        assert r.json() == {"success": True, "action": "RTL", "message": "RTL activado"}

    def test_land_action(self, auth_headers, mock_ctrl):
        mock_ctrl.land.return_value = True
        r = client.post("/api/emergency", json={"action": "LAND"}, headers=auth_headers)
        assert r.json()["action"] == "LAND"

    def test_kill_action(self, auth_headers, mock_ctrl):
        mock_ctrl.kill_motors.return_value = True
        r = client.post("/api/emergency", json={"action": "KILL"}, headers=auth_headers)
        assert r.json()["message"] == "MOTORES DETENIDOS"

    def test_unknown_action(self, auth_headers, mock_ctrl):
        r = client.post("/api/emergency", json={"action": "DANCE"}, headers=auth_headers)
        assert r.json() == {"success": False, "message": "Acción desconocida: DANCE"}


# ── Modo ──────────────────────────────────────────────────────────────────────

class TestSetMode:
    def test_invalid_mode_rejected(self, auth_headers, mock_ctrl):
        r = client.post("/api/mode", json={"mode": "BANANA"}, headers=auth_headers)
        assert r.json()["success"] is False

    def test_valid_mode_notifies_rc_guided(self, auth_headers, mock_ctrl):
        mock_ctrl.set_mode.return_value = True
        rc = MagicMock()
        mock_ctrl.rc = rc
        r = client.post("/api/mode", json={"mode": "guided"}, headers=auth_headers)
        assert r.json()["success"] is True
        rc.set_guided_mode.assert_called_with(True)


# ── Waypoints (persistencia en disco) ────────────────────────────────────────

class TestWaypointsPersistence:
    @pytest.fixture(autouse=True)
    def _isolated_waypoints_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rest, '_WAYPOINTS_DIR', str(tmp_path))

    def test_save_and_load_roundtrip(self, auth_headers):
        wps = [{"lat": 1.0, "lon": 2.0}]
        r = client.post("/api/waypoints/save", json={"name": "route1", "waypoints": wps}, headers=auth_headers)
        assert r.json()["success"] is True

        r = client.post("/api/waypoints/load", json={"name": "route1"}, headers=auth_headers)
        assert r.json() == {"success": True, "waypoints": wps}

    def test_load_missing_returns_404(self, auth_headers):
        r = client.post("/api/waypoints/load", json={"name": "nope"}, headers=auth_headers)
        assert r.status_code == 404

    def test_list_includes_saved_route(self, auth_headers):
        client.post("/api/waypoints/save", json={"name": "abc", "waypoints": []}, headers=auth_headers)
        r = client.get("/api/waypoints/list", headers=auth_headers)
        assert "abc" in r.json()["names"]

    def test_delete_removes_route(self, auth_headers):
        client.post("/api/waypoints/save", json={"name": "todelete", "waypoints": []}, headers=auth_headers)
        r = client.delete("/api/waypoints/todelete", headers=auth_headers)
        assert r.json()["success"] is True
        r = client.get("/api/waypoints/list", headers=auth_headers)
        assert "todelete" not in r.json()["names"]

    def test_delete_missing_returns_404(self, auth_headers):
        r = client.delete("/api/waypoints/doesnotexist", headers=auth_headers)
        assert r.status_code == 404


# ── Goto ──────────────────────────────────────────────────────────────────────

class TestGoto:
    def test_goto_requires_armed(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = False
        r = client.post("/api/goto", json={"latitude": 1, "longitude": 2}, headers=auth_headers)
        assert r.json() == {"success": False, "message": "Dron debe estar armado"}

    def test_goto_success(self, auth_headers, mock_ctrl):
        mock_ctrl.is_armed.return_value = True
        mock_ctrl.goto.return_value = True
        r = client.post("/api/goto", json={"latitude": 1.0, "longitude": 2.0, "altitude": 5.0}, headers=auth_headers)
        assert r.json()["success"] is True
        assert r.json()["target"] == {"latitude": 1.0, "longitude": 2.0, "altitude": 5.0}


# ── Sensores ──────────────────────────────────────────────────────────────────

class TestSensors:
    def test_sensors_unavailable(self, auth_headers):
        r = client.get("/api/sensors", headers=auth_headers)
        assert r.json() == {"success": False, "message": "Sensores no disponibles"}

    def test_sensors_local_data(self, auth_headers, monkeypatch):
        sm = MagicMock()
        sm.get_data.return_value = {"mtf01": {"distance_m": 1.0}}
        monkeypatch.setattr(rest, 'sensor_manager', sm)
        r = client.get("/api/sensors", headers=auth_headers)
        assert r.json()["_source"] == "local"

    def test_sensors_external_data_takes_priority(self, auth_headers, monkeypatch):
        monkeypatch.setattr(rest, '_external_sensor_data', {"mtf01": {"distance_m": 2.0}})
        monkeypatch.setattr(rest, '_external_update_time', time.time())
        r = client.get("/api/sensors", headers=auth_headers)
        assert r.json()["data"]["_source"] == "external"

    def test_sensors_status_unavailable(self, auth_headers):
        r = client.get("/api/sensors/status", headers=auth_headers)
        assert r.json()["success"] is False

    def test_post_sensor_data_from_bridge(self, auth_headers):
        r = client.post("/api/sensors", json={
            "sensors": {"mtf01": {"distance_m": 3.0}},
            "mavlink": {"armed": True},
        }, headers=auth_headers)
        assert r.json()["success"] is True
        assert rest._external_sensor_data == {"mtf01": {"distance_m": 3.0}}
        assert rest._external_mavlink_data == {"armed": True}

    def test_sensor_source_reports_sim_by_default(self, auth_headers):
        r = client.get("/api/sensors/source", headers=auth_headers)
        assert r.json()["source"] == "sim"
        assert r.json()["sim_mode"] is True


# ── Navegación autónoma ───────────────────────────────────────────────────────

class TestNavigationEndpoints:
    def test_nav_status_unavailable(self, auth_headers):
        r = client.get("/api/nav/status", headers=auth_headers)
        assert r.json()["success"] is False

    def test_nav_status_available(self, auth_headers, monkeypatch):
        nc = MagicMock()
        nc.get_status.return_value = {"mode": "IDLE"}
        monkeypatch.setattr(rest, 'nav_controller', nc)
        r = client.get("/api/nav/status", headers=auth_headers)
        assert r.json() == {"success": True, "data": {"mode": "IDLE"}}

    def test_nav_goto_unavailable(self, auth_headers):
        r = client.post("/api/nav/goto", json={"latitude": 1, "longitude": 2}, headers=auth_headers)
        assert r.json()["success"] is False

    def test_nav_goto_success(self, auth_headers, monkeypatch):
        nc = MagicMock()
        monkeypatch.setattr(rest, 'nav_controller', nc)
        r = client.post("/api/nav/goto", json={"latitude": 1.0, "longitude": 2.0}, headers=auth_headers)
        assert r.json()["success"] is True
        nc.navigate_to.assert_called_once_with(1.0, 2.0, 10.0)

    def test_nav_mission_success(self, auth_headers, monkeypatch):
        nc = MagicMock()
        monkeypatch.setattr(rest, 'nav_controller', nc)
        r = client.post("/api/nav/mission", json={"waypoints": [{"lat": 1, "lon": 1}]}, headers=auth_headers)
        assert r.json()["success"] is True
        nc.start_mission.assert_called_once()

    def test_nav_stop(self, auth_headers, monkeypatch):
        nc = MagicMock()
        monkeypatch.setattr(rest, 'nav_controller', nc)
        r = client.post("/api/nav/stop", headers=auth_headers)
        assert r.json()["success"] is True
        nc.stop_navigation.assert_called_once()

    def test_toggle_avoidance(self, auth_headers, monkeypatch):
        nc = MagicMock()
        monkeypatch.setattr(rest, 'nav_controller', nc)
        r = client.post("/api/nav/avoidance?active=false", headers=auth_headers)
        assert r.json()["success"] is True
        nc.avoidance.set_active.assert_called_with(False)


class TestObstacleMap:
    def test_obstacle_map_unavailable(self, auth_headers):
        r = client.get("/api/obstacle-map", headers=auth_headers)
        assert r.json()["success"] is False

    def test_obstacle_map_data(self, auth_headers, monkeypatch):
        sm = MagicMock()
        sm.obstacle_map.to_dict.return_value = {"width_m": 20}
        monkeypatch.setattr(rest, 'sensor_manager', sm)
        r = client.get("/api/obstacle-map", headers=auth_headers)
        assert r.json() == {"success": True, "data": {"width_m": 20}}

    def test_obstacle_map_reset(self, auth_headers, monkeypatch):
        sm = MagicMock()
        monkeypatch.setattr(rest, 'sensor_manager', sm)
        r = client.post("/api/obstacle-map/reset", headers=auth_headers)
        assert r.json()["success"] is True
        sm.obstacle_map.reset.assert_called_once()


# ── Diagnóstico ───────────────────────────────────────────────────────────────

class TestDiagEndpoints:
    def test_diag_params(self, auth_headers, mock_ctrl):
        mock_ctrl.get_critical_params.return_value = {"DISARM_DELAY": 60}
        r = client.get("/api/diag/params", headers=auth_headers)
        assert r.json() == {"success": True, "params": {"DISARM_DELAY": 60}}

    def test_diag_param_set(self, auth_headers, mock_ctrl):
        mock_ctrl.set_param.return_value = 60
        r = client.post("/api/diag/param/set?name=DISARM_DELAY&value=60", headers=auth_headers)
        assert r.json()["success"] is True

    def test_diag_motor_test(self, auth_headers, mock_ctrl):
        mock_ctrl.cmd = MagicMock()
        r = client.post("/api/diag/motor-test?motor=0&throttle=10&duration=1", headers=auth_headers)
        assert r.json()["success"] is True

    def test_diag_rc_unavailable(self, auth_headers, mock_ctrl):
        mock_ctrl.rc = None
        r = client.get("/api/diag/rc", headers=auth_headers)
        assert r.json() == {"success": False, "message": "RC no disponible"}

    def test_diag_rc_available(self, auth_headers, mock_ctrl):
        rc = MagicMock()
        rc.get_current_values.return_value = {"throttle": 0.0}
        rc._send_failures = 0
        rc._send_count = 10
        rc._armed = False
        mock_ctrl.rc = rc
        r = client.get("/api/diag/rc", headers=auth_headers)
        assert r.json()["success"] is True

    def test_diag_servo_raw(self, auth_headers, mock_ctrl):
        mock_ctrl.get_servo_output_raw.return_value = {"ch1": 1500}
        r = client.get("/api/diag/servo_raw", headers=auth_headers)
        assert r.json()["success"] is True

    def test_diag_rc_channels(self, auth_headers, mock_ctrl):
        mock_ctrl.get_rc_channels.return_value = {"error": "timeout"}
        r = client.get("/api/diag/rc_channels", headers=auth_headers)
        assert r.json()["success"] is False


# ── Funciones de inicialización (llamadas directas, no HTTP) ────────────────

class TestInitFunctions:
    def test_init_mav_success(self, monkeypatch):
        fake_controller = MagicMock()
        monkeypatch.setattr('backend.mavlink.controller.MAVController', lambda d, b: fake_controller)
        assert rest.init_mav('SIM', 115200) is True
        assert rest.mav is fake_controller

    def test_init_mav_failure_returns_false(self, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError('no device')
        monkeypatch.setattr('backend.mavlink.controller.MAVController', boom)
        assert rest.init_mav('SIM', 115200) is False
        assert rest.mav is None

    def test_init_sensors_success(self, monkeypatch):
        fake_manager = MagicMock()
        monkeypatch.setattr('backend.sensors.manager.SensorManager', lambda sim_mode: fake_manager)
        assert rest.init_sensors(MagicMock()) is True
        assert rest.sensor_manager is fake_manager
        fake_manager.start.assert_called_once()

    def test_init_navigation_without_sensors_fails(self, monkeypatch):
        monkeypatch.setattr(rest, 'sensor_manager', None)
        assert rest.init_navigation(MagicMock()) is False

    def test_shutdown_sensors_and_nav(self, monkeypatch):
        nc = MagicMock()
        sm = MagicMock()
        monkeypatch.setattr(rest, 'nav_controller', nc)
        monkeypatch.setattr(rest, 'sensor_manager', sm)
        rest.shutdown_sensors_and_nav()
        nc.stop.assert_called_once()
        sm.stop.assert_called_once()
        assert rest.nav_controller is None
        assert rest.sensor_manager is None

    def test_start_monitoring_starts_thread(self, monkeypatch):
        rest.start_monitoring(baud=115200, interval=100)
        try:
            assert rest._monitor_thread is not None
            assert rest._monitor_thread.is_alive()
        finally:
            rest._monitor_thread._running = False
