"""Tests unitarios para backend/mavlink/controller.py — MAVController (modo SIM
y wrappers del modo real, mockeando la conexión)."""
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from backend.mavlink.controller import MAVController


# ── Modo SIM — controlador simulado real, sin mocks de MAVLink ──────────────

@pytest.fixture
def sim_ctrl():
    ctrl = MAVController('SIM', 115200)
    yield ctrl
    ctrl._sim._running = False


class TestSimMode:
    def test_is_connected_always_true(self, sim_ctrl):
        assert sim_ctrl.is_connected() is True

    def test_starts_disarmed(self, sim_ctrl):
        assert sim_ctrl.is_armed() is False
        assert sim_ctrl.get_mode() == 'STANDBY'

    def test_arm_disarm(self, sim_ctrl):
        assert sim_ctrl.arm() is True
        assert sim_ctrl.is_armed() is True
        assert sim_ctrl.disarm() is True
        assert sim_ctrl.is_armed() is False

    def test_set_mode(self, sim_ctrl):
        assert sim_ctrl.set_mode('GUIDED') is True
        assert sim_ctrl.get_mode() == 'GUIDED'

    def test_takeoff_arms_and_sets_altitude(self, sim_ctrl):
        assert sim_ctrl.takeoff(15.0) is True
        assert sim_ctrl.is_armed() is True
        assert sim_ctrl.get_mode() == 'GUIDED'
        tel = sim_ctrl.get_telemetry()
        assert tel['altitude'] == 15.0

    def test_land_resets_altitude(self, sim_ctrl):
        sim_ctrl.takeoff(10.0)
        assert sim_ctrl.land() is True
        assert sim_ctrl.get_mode() == 'LAND'
        assert sim_ctrl.get_telemetry()['altitude'] == 0.0

    def test_rtl(self, sim_ctrl):
        assert sim_ctrl.rtl() is True
        assert sim_ctrl.get_mode() == 'RTL'

    def test_return_to_launch_alias(self, sim_ctrl):
        assert sim_ctrl.return_to_launch() is True
        assert sim_ctrl.get_mode() == 'RTL'

    def test_goto(self, sim_ctrl):
        assert sim_ctrl.goto(1.0, 2.0, 30.0) is True
        gps = sim_ctrl.get_gps()
        assert gps['lat'] == 1.0
        assert gps['lon'] == 2.0

    def test_kill_motors_returns_false(self, sim_ctrl):
        assert sim_ctrl.kill_motors() is False

    def test_get_system_status_constant(self, sim_ctrl):
        assert sim_ctrl.get_system_status() == 4

    def test_set_and_get_param(self, sim_ctrl):
        sim_ctrl.set_param('DISARM_DELAY', 60)
        result = sim_ctrl.get_param('DISARM_DELAY')
        assert result['value'] == 60

    def test_upload_and_start_mission(self, sim_ctrl):
        wps = [{'lat': 1, 'lon': 1, 'alt': 10}]
        assert sim_ctrl.upload_mission(wps) is True
        assert sim_ctrl.start_mission() is True
        assert sim_ctrl.get_mode() == 'AUTO'

    def test_start_mission_without_upload_raises(self, sim_ctrl):
        with pytest.raises(ValueError):
            sim_ctrl.start_mission()

    def test_clear_mission(self, sim_ctrl):
        sim_ctrl.upload_mission([{'lat': 1, 'lon': 1, 'alt': 10}])
        assert sim_ctrl.clear_mission() is True
        with pytest.raises(ValueError):
            sim_ctrl.start_mission()

    def test_preflight_checks_reflect_battery(self, sim_ctrl):
        checks = sim_ctrl.preflight_checks()
        assert checks['battery_ok'] is True
        sim_ctrl._sim._state['battery']['remaining'] = 10
        checks = sim_ctrl.preflight_checks()
        assert checks['battery_ok'] is False

    def test_get_battery_includes_time_remaining(self, sim_ctrl):
        battery = sim_ctrl.get_battery()
        assert battery['time_remaining_minutes'] == 999

    def test_get_flight_logs_empty(self, sim_ctrl):
        assert sim_ctrl.get_flight_logs() == []

    def test_test_motor(self, sim_ctrl):
        assert sim_ctrl.test_motor(0, 10, 0.01) is True

    def test_get_servo_output_raw_not_wired_to_public_api(self, sim_ctrl):
        # NOTA: get_servo_output_raw/get_rc_channels NO están en la lista de
        # proxies de __init__ para modo SIM — self.conn es None, así que la
        # implementación real de MAVController (que espera self.conn.master)
        # responde "no connection" en vez de delegar a _sim. El método de
        # _SimulatedController existe pero hoy es inalcanzable vía la API
        # pública en modo SIM (hallazgo, no corregido acá).
        assert sim_ctrl.get_servo_output_raw() == {"error": "no connection"}

    def test_sim_get_servo_output_raw_direct(self, sim_ctrl):
        assert sim_ctrl._sim.get_servo_output_raw()['sim'] is True

    def test_sim_get_rc_channels_direct(self, sim_ctrl):
        assert sim_ctrl._sim.get_rc_channels()['sim'] is True

    def test_get_critical_params(self, sim_ctrl):
        sim_ctrl.set_param('FOO', 1)
        result = sim_ctrl._sim.get_critical_params()
        assert 'FOO' in result['__params__']

    def test_tick_loop_climbs_when_armed_and_guided(self, sim_ctrl):
        sim_ctrl.set_mode('GUIDED')
        sim_ctrl.arm()
        time.sleep(0.3)
        assert sim_ctrl.get_telemetry()['altitude'] > 0


# ── Modo real — wrappers de MAVController (conexión/comandos mockeados) ─────

@pytest.fixture
def real_ctrl():
    with patch('backend.mavlink.controller.MAVLinkConnection') as MockConn, \
         patch('backend.mavlink.controller.DroneTelemetry') as MockTel, \
         patch('backend.mavlink.controller.RCOverrideController') as MockRc:
        mock_conn = MagicMock()
        mock_conn.master = MagicMock()
        mock_conn.start_auto_reconnect = MagicMock()
        MockConn.return_value = mock_conn

        mock_tel = MagicMock()
        mock_tel.data = {'armed': False, 'mode': 'STABILIZE', 'system_status': 4}
        mock_tel.get_status.side_effect = lambda: {
            'armed': mock_tel.data.get('armed', False),
            'mode': mock_tel.data.get('mode', 'UNKNOWN'),
            'system_status': mock_tel.data.get('system_status', 0),
        }
        MockTel.return_value = mock_tel

        mock_rc = MagicMock()
        MockRc.return_value = mock_rc

        ctrl = MAVController('tcp:127.0.0.1:5760', 115200)
        ctrl._mock_conn = mock_conn
        ctrl._mock_tel = mock_tel
        ctrl._mock_rc = mock_rc
        yield ctrl


class TestRealModeConstruction:
    def test_starts_rc_override(self, real_ctrl):
        real_ctrl._mock_rc.start.assert_called_once()

    def test_wires_rc_callback_for_heartbeat(self, real_ctrl):
        assert real_ctrl._mock_conn._rc_callback == real_ctrl._mock_rc.set_armed


class TestRealModeArmDisarm:
    def test_arm_success_sets_rc_armed(self, real_ctrl):
        real_ctrl.cmd.arm = MagicMock(return_value=True)
        assert real_ctrl.arm() is True
        real_ctrl._mock_rc.set_armed.assert_called_with(True)

    def test_arm_failure_propagates_and_disarms_rc(self, real_ctrl):
        real_ctrl.cmd.arm = MagicMock(side_effect=ConnectionError('rejected'))
        with pytest.raises(ConnectionError):
            real_ctrl.arm()
        real_ctrl._mock_rc.set_armed.assert_called_with(False)

    def test_disarm_releases_rc_before_and_after(self, real_ctrl):
        real_ctrl.cmd.disarm = MagicMock(return_value=True)
        real_ctrl.is_armed = MagicMock(return_value=False)
        assert real_ctrl.disarm() is True
        real_ctrl._mock_rc.set_armed.assert_any_call(False)


class TestRealModeStatusWrappers:
    def test_is_armed_false_when_heartbeat_unhealthy(self, real_ctrl):
        real_ctrl._mock_tel.data['armed'] = True
        real_ctrl._mock_conn.is_heartbeat_healthy.return_value = False
        assert real_ctrl.is_armed() is False

    def test_is_armed_true_when_heartbeat_healthy(self, real_ctrl):
        real_ctrl._mock_tel.data['armed'] = True
        real_ctrl._mock_conn.is_heartbeat_healthy.return_value = True
        assert real_ctrl.is_armed() is True

    def test_get_mode_default_unknown(self, real_ctrl):
        real_ctrl._mock_tel.data.pop('mode', None)
        assert real_ctrl.get_mode() == 'UNKNOWN'

    def test_get_system_status(self, real_ctrl):
        assert real_ctrl.get_system_status() == 4


class TestRealModeDiagEndpointsHelpers:
    def test_get_servo_output_raw_no_master(self, real_ctrl):
        real_ctrl.conn.master = None
        assert real_ctrl.get_servo_output_raw() == {"error": "no connection"}

    def test_get_servo_output_raw_success(self, real_ctrl):
        master = real_ctrl.conn.master
        msg = MagicMock(port=0)
        for i in range(1, 9):
            setattr(msg, f'servo{i}_raw', 1500)
        master.recv_match.return_value = msg
        result = real_ctrl.get_servo_output_raw()
        assert result['ch1'] == 1500
        assert result['port'] == 0

    def test_get_servo_output_raw_timeout(self, real_ctrl):
        real_ctrl.conn.master.recv_match.return_value = None
        result = real_ctrl.get_servo_output_raw()
        assert 'error' in result

    def test_get_rc_channels_filters_unused(self, real_ctrl):
        master = real_ctrl.conn.master
        msg = MagicMock(rssi=200)
        for i in range(1, 19):
            setattr(msg, f'chan{i}_raw', 65535 if i > 4 else 1500)
        master.recv_match.return_value = msg
        result = real_ctrl.get_rc_channels()
        assert 'ch1' in result
        assert 'ch5' not in result  # 65535 filtrado
        assert result['rssi'] == 200

    def test_get_rc_channels_no_master(self, real_ctrl):
        real_ctrl.conn.master = None
        assert real_ctrl.get_rc_channels() == {"error": "no connection"}


class TestRealModeParams:
    def test_set_param_waits_for_confirmation(self, real_ctrl):
        real_ctrl.master = real_ctrl.conn.master
        real_ctrl.conn._pending_msgs_lock = threading.Lock()
        real_ctrl.conn._pending_msgs = {'PARAM_VALUE:DISARM_DELAY': MagicMock(param_value=60)}
        result = real_ctrl.set_param('DISARM_DELAY', 60)
        assert result == 60

    def test_set_param_timeout_raises(self, real_ctrl):
        real_ctrl.master = real_ctrl.conn.master
        real_ctrl.conn._pending_msgs_lock = threading.Lock()
        real_ctrl.conn._pending_msgs = {}
        with pytest.raises(TimeoutError):
            _run_with_short_deadline(real_ctrl, 'set_param', 'DISARM_DELAY', 60)

    def test_get_param_success(self, real_ctrl):
        real_ctrl.master = real_ctrl.conn.master
        real_ctrl.conn._pending_msgs_lock = threading.Lock()
        msg = MagicMock(param_value=42.0, param_type=9)
        msg.param_id.decode.return_value = 'FOO\x00\x00'
        real_ctrl.conn._pending_msgs = {'PARAM_VALUE:FOO': msg}
        result = real_ctrl.get_param('FOO')
        assert result['value'] == 42.0

    def test_read_param_safe_returns_none_on_exception(self, real_ctrl):
        real_ctrl.get_param = MagicMock(side_effect=Exception('boom'))
        assert real_ctrl.read_param_safe('FOO') is None

    def test_get_critical_params_skips_none(self, real_ctrl):
        real_ctrl.read_param_safe = MagicMock(side_effect=lambda name: {'value': 1} if name == 'DISARM_DELAY' else None)
        result = real_ctrl.get_critical_params()
        assert result == {'DISARM_DELAY': {'value': 1}}


def _run_with_short_deadline(ctrl, method_name, *args):
    """Ejecuta set_param/get_param con un deadline artificialmente corto
    para no esperar los 5s reales del timeout. Nota: parchear time.time
    afecta también las llamadas internas de `logging` (usa time.time al
    crear cada LogRecord) — por eso se deja un búfer amplio de valores."""
    times = iter([0] + [100] * 20)
    with patch('backend.mavlink.controller.time.time', side_effect=lambda: next(times)):
        return getattr(ctrl, method_name)(*args)


class TestRealModeSetupParams:
    def test_setup_params_indoor_mode_adds_fence_disable(self, real_ctrl, monkeypatch):
        monkeypatch.setenv('INDOOR_MODE', '1')
        real_ctrl.set_param = MagicMock(return_value=60)
        real_ctrl.setup_params()
        real_ctrl.set_param.assert_any_call('FENCE_ENABLE', 0)

    def test_setup_params_swallows_param_errors(self, real_ctrl, monkeypatch):
        monkeypatch.delenv('INDOOR_MODE', raising=False)
        real_ctrl.set_param = MagicMock(side_effect=Exception('boom'))
        real_ctrl.setup_params()  # no debe propagar


class TestRealModeMissions:
    def test_upload_mission_empty_raises(self, real_ctrl):
        with pytest.raises(ValueError):
            real_ctrl.upload_mission([])

    def test_upload_mission_success(self, real_ctrl):
        real_ctrl.master = real_ctrl.conn.master
        real_ctrl.conn._pending_msgs_lock = threading.Lock()
        ack_msg = MagicMock()
        ack_msg.get_type.return_value = 'MISSION_ACK'
        req_msg = MagicMock()
        req_msg.get_type.return_value = 'MISSION_REQUEST_INT'
        req_msg.seq = 0

        call_state = {'n': 0}

        def pop_side_effect(mtype, default=None):
            call_state['n'] += 1
            if call_state['n'] == 1 and mtype == 'MISSION_REQUEST_INT':
                return req_msg
            if mtype == 'MISSION_ACK' and call_state['n'] > 1:
                return ack_msg
            return None

        real_ctrl.conn._pending_msgs = MagicMock()
        real_ctrl.conn._pending_msgs.pop.side_effect = pop_side_effect
        result = real_ctrl.upload_mission([{'lat': 1.0, 'lon': 2.0, 'alt': 10}])
        assert result is True

    def test_start_mission_sets_mode_auto(self, real_ctrl):
        real_ctrl.master = real_ctrl.conn.master
        real_ctrl.set_mode = MagicMock(return_value=True)
        real_ctrl.conn.pause_read.return_value.__enter__ = MagicMock()
        real_ctrl.conn.pause_read.return_value.__exit__ = MagicMock()
        assert real_ctrl.start_mission() is True
        real_ctrl.set_mode.assert_called_with('AUTO')

    def test_clear_mission_success(self, real_ctrl):
        real_ctrl.master = real_ctrl.conn.master
        assert real_ctrl.clear_mission() is True


class TestRealModeKillAndRearm:
    def test_kill_motors_delegates_to_cmd(self, real_ctrl):
        real_ctrl.cmd.kill_motors = MagicMock(return_value=True)
        assert real_ctrl.kill_motors() is True

    def test_kill_motors_missing_returns_false(self, real_ctrl):
        real_ctrl.cmd = MagicMock(spec=[])  # sin atributo kill_motors
        assert real_ctrl.kill_motors() is False

    def test_rearm_after_failsafe_runs_in_thread(self, real_ctrl):
        real_ctrl.cmd.arm = MagicMock(return_value=True)
        real_ctrl._rearm_after_failsafe()
        time.sleep(0.8)
        real_ctrl.cmd.arm.assert_called_once_with(force=True)
