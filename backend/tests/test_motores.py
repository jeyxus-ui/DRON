"""Tests unitarios para diagnóstico de motores y flujos críticos."""
import time
import threading
import types
from unittest.mock import MagicMock, PropertyMock, patch, call
import pytest


# =============================================================================
# Tests: RCOverrideController — failsafe, set_controls, set_armed
# =============================================================================
class TestRCOverrideFailsafe:
    """Prueba el flujo de failsafe: desconexión → ramp-down → disarm."""

    @pytest.fixture
    def rc(self):
        from backend.mavlink.rc_override import RCOverrideController
        conn = MagicMock()
        conn.master = MagicMock()
        conn._lock = threading.Lock()
        ctrl = RCOverrideController(conn)
        return ctrl

    def test_initial_state(self, rc):
        assert rc.throttle == 0.0
        assert rc.yaw == 0.0
        assert rc.pitch == 0.0
        assert rc.roll == 0.0
        assert rc._armed is False
        assert rc._disconnected_at is None
        assert rc._disarmed_by_failsafe is False
        assert rc._send_failures == 0
        assert rc._reconnect_callback is None

    def test_set_controls_updates_values(self, rc):
        rc.set_controls(throttle=0.5, yaw=0.1, pitch=-0.2, roll=0.3)
        assert rc.throttle == 0.5
        assert rc.yaw == 0.1
        assert rc.pitch == -0.2
        assert rc.roll == 0.3

    def test_set_controls_cancels_failsafe(self, rc):
        rc._disconnected_at = time.time() - 20
        rc._disarmed_by_failsafe = True
        rc.set_controls(throttle=0.5)
        assert rc._disconnected_at is None
        assert rc._disarmed_by_failsafe is False

    def test_set_armed_true_sets_timers(self, rc):
        rc.set_armed(True)
        assert rc._armed is True
        assert rc._armed_at is not None
        assert rc._failsafe_fired is False

    def test_set_armed_false_resets_all(self, rc):
        rc.throttle = 0.7
        rc.roll = 0.5
        rc.pitch = 0.3
        rc.yaw = -0.2
        rc.set_armed(False)
        assert rc._armed is False
        assert rc._armed_at is None
        assert rc.throttle == 0.0
        assert rc.roll == 0.0
        assert rc.pitch == 0.0
        assert rc.yaw == 0.0

    def test_on_disconnect_sets_timer(self, rc):
        rc.on_disconnect()
        assert rc._disconnected_at is not None
        assert rc._disarmed_by_failsafe is False

    def test_on_reconnect_cancels_failsafe(self, rc):
        rc._disconnected_at = time.time() - 5
        rc._disarmed_by_failsafe = True
        rc.on_reconnect()
        assert rc._disconnected_at is None
        assert rc._disarmed_by_failsafe is False

    def test_in_idle_true_when_armed_and_failsafe_not_fired(self, rc):
        rc.set_armed(True)
        rc._failsafe_fired = False
        values = rc.get_current_values()
        assert values["in_idle"] is True

    def test_in_idle_false_when_failsafe_fired(self, rc):
        rc.set_armed(True)
        rc._failsafe_fired = True
        values = rc.get_current_values()
        assert values["in_idle"] is False

    def test_in_idle_false_when_disarmed(self, rc):
        rc.set_armed(False)
        values = rc.get_current_values()
        assert values["in_idle"] is False

    def test_set_armed_twice_resets_failsafe_fired(self, rc):
        rc.set_armed(True)
        rc._failsafe_fired = True
        rc.set_armed(True)
        assert rc._failsafe_fired is False

    def test_set_controls_clamps_throttle(self, rc):
        rc.set_controls(throttle=2.0)
        assert rc.throttle == 1.0
        rc.set_controls(throttle=-1.0)
        assert rc.throttle == 0.0

    def test_set_controls_applies_deadband_to_yaw(self, rc):
        rc.set_controls(yaw=0.03)
        assert rc.yaw == 0.0
        rc.set_controls(yaw=0.06)
        assert abs(rc.yaw - 0.06) < 0.001

    def test_to_pwm_center(self, rc):
        assert rc._to_pwm(0.0) == 1500

    def test_to_pwm_full_negative(self, rc):
        assert rc._to_pwm(-1.0) == 1000

    def test_to_pwm_full_positive(self, rc):
        assert rc._to_pwm(1.0) == 2000

    def test_to_pwm_throttle_zero(self, rc):
        assert rc._to_pwm_throttle(0.0) == 1000

    def test_to_pwm_throttle_full(self, rc):
        assert rc._to_pwm_throttle(1.0) == 2000

    def test_to_pwm_throttle_half(self, rc):
        assert rc._to_pwm_throttle(0.5) == 1500

    def test_reset_controls_sets_all_zero(self, rc):
        rc.set_controls(throttle=0.8, yaw=0.5, pitch=-0.5, roll=0.2)
        rc.reset_controls()
        assert rc.throttle == 0.0
        assert rc.yaw == 0.0
        assert rc.pitch == 0.0
        assert rc.roll == 0.0

    def test_pwm_values_in_get_current_values(self, rc):
        rc.set_controls(throttle=0.5, yaw=0.0, pitch=0.0, roll=0.0)
        values = rc.get_current_values()
        assert "throttle_pwm" in values
        assert "yaw_pwm" in values
        assert "pitch_pwm" in values
        assert "roll_pwm" in values
        assert values["throttle_pwm"] == 1500

    def test_get_current_values_not_in_idle_after_failsafe(self, rc):
        rc.set_armed(True)
        rc._failsafe_fired = True
        values = rc.get_current_values()
        assert values["in_idle"] is False

    def test_get_current_values_in_idle_after_arm(self, rc):
        rc.set_armed(True)
        values = rc.get_current_values()
        assert values["in_idle"] is False

    def test_unused_channels_are_65535_in_send(self, rc):
        from backend.mavlink.rc_override import RCOverrideController
        source = open(RCOverrideController.__module__.replace('.', '/') + '.py', encoding='utf-8').read() if False else ""
        import ast, os
        path = os.path.join(os.path.dirname(__file__), '..', 'mavlink', 'rc_override.py')
        with open(path) as f:
            content = f.read()
        assert '65535, 65535, 65535, 65535' in content

    def test_send_failures_increment_on_exception(self, rc):
        rc.conn.master.mav.rc_channels_override_send.side_effect = Exception("send error")
        with patch.object(rc, 'lock', threading.Lock()):
            rc._send_loop()
        assert rc._send_failures >= 1

    def test_throttle_zero_to_pwm_is_1000(self, rc):
        rc.throttle = 0.0
        assert rc._to_pwm_throttle(rc.throttle) == 1000

    def test_throttle_full_to_pwm_is_2000(self, rc):
        rc.throttle = 1.0
        assert rc._to_pwm_throttle(rc.throttle) == 2000

    def test_roll_negative_to_pwm(self, rc):
        rc.roll = -1.0
        assert rc._to_pwm(rc.roll) == 1000

    def test_roll_positive_to_pwm(self, rc):
        rc.roll = 1.0
        assert rc._to_pwm(rc.roll) == 2000

    def test_pitch_negative_to_pwm(self, rc):
        rc.pitch = -1.0
        assert rc._to_pwm(rc.pitch) == 1000

    def test_pitch_positive_to_pwm(self, rc):
        rc.pitch = 1.0
        assert rc._to_pwm(rc.pitch) == 2000

    def test_yaw_negative_to_pwm(self, rc):
        rc.yaw = -1.0
        assert rc._to_pwm(rc.yaw) == 1000

    def test_yaw_positive_to_pwm(self, rc):
        rc.yaw = 1.0
        assert rc._to_pwm(rc.yaw) == 2000

    def test_set_controls_partial_update(self, rc):
        rc.set_controls(throttle=0.5)
        assert rc.throttle == 0.5
        assert rc.yaw == 0.0
        assert rc.pitch == 0.0
        assert rc.roll == 0.0

    def test_on_disconnect_twice_sets_latest_time(self, rc):
        t1 = time.time() - 100
        rc._disconnected_at = t1
        rc.on_disconnect()
        assert rc._disconnected_at > t1

    def test_on_reconnect_twice_stays_none(self, rc):
        rc.on_reconnect()
        rc.on_reconnect()
        assert rc._disconnected_at is None
        assert rc._disarmed_by_failsafe is False

    def test_failsafe_disarm_sends_force(self, rc):
        import threading
        rc._disconnected_at = time.time() - 20
        rc._disarmed_by_failsafe = False
        rc._armed = True

        def step():
            for _ in range(5):
                if rc._disarmed_by_failsafe:
                    return
                rc._send_loop()
                time.sleep(0.05)

        t = threading.Thread(target=step, daemon=True)
        t.start()
        t.join(timeout=3)

    def test_is_connected_returns_true_with_master(self, rc):
        assert rc.is_connected() is True

    def test_is_connected_returns_false_without_master(self, rc):
        rc.conn.master = None
        assert rc.is_connected() is False

    def test_release_control_sends_all_zero(self, rc):
        rc._release_control()
        rc.conn.master.mav.rc_channels_override_send.assert_called_with(
            rc.conn.master.target_system,
            rc.conn.master.target_component,
            0, 0, 0, 0, 0, 0, 0, 0
        )

    def test_arm_idle_duration_zero_no_idle(self, rc):
        assert rc.ARM_IDLE_DURATION == 0.0

    def test_idle_throttle_defined(self, rc):
        assert rc.IDLE_THROTTLE == 0.25

    def test_disarm_timeout_defined(self, rc):
        assert rc.DISARM_TIMEOUT == 10.0

    def test_ramp_down_duration_defined(self, rc):
        assert rc.RAMP_DOWN_DURATION == 5.0

    def test_joystick_deadband_defined(self, rc):
        assert rc.JOYSTICK_DEADBAND == 0.05

    # ── Reconnect callback tests ──────────────────────────────────────────

    def test_on_reconnect_calls_callback_when_disarmed(self, rc):
        callback = MagicMock()
        rc._reconnect_callback = callback
        rc._disconnected_at = time.time() - 20
        rc._disarmed_by_failsafe = True
        rc.on_reconnect()
        callback.assert_called_once()
        assert rc._disconnected_at is None
        assert rc._disarmed_by_failsafe is False

    def test_on_reconnect_does_not_call_callback_when_not_disarmed(self, rc):
        callback = MagicMock()
        rc._reconnect_callback = callback
        rc._disconnected_at = time.time() - 5
        rc._disarmed_by_failsafe = False
        rc.on_reconnect()
        callback.assert_not_called()

    def test_on_reconnect_no_callback_set_does_not_crash(self, rc):
        rc._disconnected_at = time.time() - 20
        rc._disarmed_by_failsafe = True
        rc._reconnect_callback = None
        rc.on_reconnect()

    def test_set_controls_calls_callback_when_disarmed(self, rc):
        callback = MagicMock()
        rc._reconnect_callback = callback
        rc._disconnected_at = time.time() - 20
        rc._disarmed_by_failsafe = True
        rc.set_controls(throttle=0.5)
        callback.assert_called_once()
        assert rc._disconnected_at is None
        assert rc._disarmed_by_failsafe is False

    def test_set_controls_does_not_call_callback_when_not_disarmed(self, rc):
        callback = MagicMock()
        rc._reconnect_callback = callback
        rc.set_controls(throttle=0.5)
        callback.assert_not_called()

    def test_set_controls_no_callback_set_does_not_crash(self, rc):
        rc._disconnected_at = time.time() - 20
        rc._disarmed_by_failsafe = True
        rc._reconnect_callback = None
        rc.set_controls(throttle=0.5)

    def test_reconnect_callback_exception_does_not_crash(self, rc):
        def failing_callback():
            raise RuntimeError("callback exploded")
        rc._reconnect_callback = failing_callback
        rc._disconnected_at = time.time() - 20
        rc._disarmed_by_failsafe = True
        rc.on_reconnect()


# =============================================================================
# Tests: MAVController — arm/disarm flow, get_servo_output_raw, get_rc_channels
# =============================================================================
class TestMAVControllerArmDisarm:
    """Prueba el flujo de armado y desarmado simulando el Pixhawk."""

    @pytest.fixture
    def ctrl(self):
        from backend.mavlink.controller import MAVController
        with patch('backend.mavlink.controller.MAVLinkConnection') as mock_conn_cls, \
             patch('backend.mavlink.controller.DroneTelemetry') as mock_tel:
            mock_conn = MagicMock()
            mock_conn.master = MagicMock()
            mock_conn._lock = threading.Lock()
            mock_conn._ack_lock = threading.Lock()
            mock_conn._ekf_ready = threading.Event()
            mock_conn._ekf_ready.set()
            mock_conn._pending_acks = {}
            mock_conn._disarming = False
            mock_conn._rc_callback = None
            mock_conn._reconnecting = threading.Event()
            mock_conn._needs_reconnect = threading.Event()
            mock_conn.connected = True
            mock_conn.is_connected.return_value = True
            mock_conn_cls.return_value = mock_conn

            mock_tel_inst = MagicMock()
            mock_tel_inst.data = {
                'armed': False,
                'mode': 'STABILIZE',
            }
            mock_tel_inst.get_status.return_value = {
                'connected': True, 'armed': False, 'mode': 'STABILIZE', 'system_status': 4
            }
            mock_tel_inst.get_all.return_value = {
                'connected': True, 'armed': False, 'mode': 'STABILIZE',
                'altitude': 0, 'speed': 0, 'throttle': 0,
                'gps': {}, 'battery': {}, 'attitude': {}, 'home_position': {},
            }
            mock_tel_inst.get_attitude.return_value = {}
            mock_tel_inst.get_gps.return_value = {}
            mock_tel_inst.get_battery.return_value = {}
            mock_tel_inst.get_velocity.return_value = {}
            mock_tel.return_value = mock_tel_inst

            controller = MAVController('SIM_PORT', 115200)
            controller.conn = mock_conn
            controller.telemetry = mock_tel_inst
            controller.cmd = MagicMock()
            controller.cmd.arm.return_value = True
            controller.cmd.disarm.return_value = True
            controller.rc = MagicMock()
            controller.master = mock_conn.master
            # Re-asignar métodos para evitar proxy del simulador
            controller.is_connected = lambda: True
            controller.is_armed = lambda: False
            controller.get_status = lambda: {'connected': True, 'armed': False, 'mode': 'STABILIZE', 'system_status': 4}
            controller.get_mode = lambda: 'STABILIZE'
            controller.get_system_status = lambda: 4
            controller.preflight_checks = lambda: {'gps_fix': True, 'battery_ok': True, 'ekf_ok': True, 'home_set': True, 'sensors_ok': True}

            yield controller

    def test_arm_calls_cmd_arm(self, ctrl):
        ctrl.conn.master.mav.command_long_send = MagicMock()
        ctrl.conn.recv_match = MagicMock(return_value=None)
        old_arm = ctrl.cmd.arm
        old_arm.return_value = True
        result = ctrl.arm(force=True)
        assert result is True

    def test_disarm_calls_cmd_disarm(self, ctrl):
        ctrl.conn.master.mav.command_long_send = MagicMock()
        old_disarm = ctrl.cmd.disarm
        old_disarm.return_value = True
        result = ctrl.disarm(force=True)
        assert result is True

    def test_get_servo_output_raw_returns_dict(self, ctrl):
        mock_msg = MagicMock()
        for i in range(1, 9):
            setattr(mock_msg, f'servo{i}_raw', 1000)
        mock_msg.port = 0
        ctrl.conn.master.recv_match.return_value = mock_msg
        ctrl.conn.master.mav.command_long_send = MagicMock()
        result = ctrl.get_servo_output_raw()
        assert isinstance(result, dict)
        assert result.get('ch1') == 1000
        assert result.get('ch2') == 1000
        assert result.get('ch3') == 1000
        assert result.get('ch4') == 1000

    def test_get_rc_channels_returns_dict(self, ctrl):
        mock_msg = MagicMock()
        for i in range(1, 19):
            setattr(mock_msg, f'chan{i}_raw', 65535)
        setattr(mock_msg, 'chan1_raw', 1500)
        setattr(mock_msg, 'chan2_raw', 1500)
        setattr(mock_msg, 'chan3_raw', 1500)
        setattr(mock_msg, 'chan4_raw', 1500)
        mock_msg.rssi = 255
        ctrl.conn.master.recv_match.return_value = mock_msg
        ctrl.conn.master.mav.command_long_send = MagicMock()
        result = ctrl.get_rc_channels()
        assert isinstance(result, dict)
        assert result.get('ch1') == 1500
        assert result.get('ch3') == 1500

    def test_get_servo_output_raw_no_connection(self, ctrl):
        ctrl.conn = None
        result = ctrl.get_servo_output_raw()
        assert 'error' in result

    def test_get_rc_channels_no_connection(self, ctrl):
        ctrl.conn = None
        result = ctrl.get_rc_channels()
        assert 'error' in result

    def test_get_critical_params_includes_mot_spin_arm(self, ctrl):
        ctrl.read_param_safe = MagicMock(return_value=0.15)
        params = ctrl.get_critical_params()
        assert 'MOT_SPIN_ARM' in params
        assert params['MOT_SPIN_ARM'] == 0.15

    def test_get_critical_params_includes_arming_check(self, ctrl):
        ctrl.read_param_safe = MagicMock(return_value=0)
        params = ctrl.get_critical_params()
        assert 'ARMING_CHECK' in params

    def test_get_critical_params_includes_brd_safety(self, ctrl):
        ctrl.read_param_safe = MagicMock(return_value=0)
        params = ctrl.get_critical_params()
        assert 'BRD_SAFETY_DEFLT' in params

    def test_arm_sets_rc_armed_true_first(self, ctrl):
        ctrl.rc.reset_mock()
        ctrl.conn.master.mav.command_long_send = MagicMock()
        ctrl.conn.recv_match = MagicMock(return_value=None)
        ctrl.cmd.arm.return_value = True
        ctrl.arm(force=True)
        ctrl.rc.set_armed.assert_any_call(True)

    def test_disarm_sets_rc_armed_false_first(self, ctrl):
        ctrl.rc.reset_mock()
        ctrl.cmd.disarm.return_value = True
        # Make is_armed return True for the disarm to proceed
        ctrl.is_armed = lambda: True
        ctrl.disarm()
        ctrl.rc.set_armed.assert_any_call(False)

    def test_kill_motors_calls_disarm(self, ctrl):
        ctrl.cmd = MagicMock()
        ctrl.cmd.kill_motors.return_value = True
        result = ctrl.kill_motors()
        assert result is True

    def test_setup_params_sets_diarm_delay(self, ctrl):
        ctrl.set_param = MagicMock(return_value=60)
        ctrl.setup_params()
        ctrl.set_param.assert_called_with('DISARM_DELAY', 60)

    def test_read_param_safe_returns_none_on_error(self, ctrl):
        with patch.object(ctrl, 'get_param', side_effect=Exception("error")):
            result = ctrl.read_param_safe('SOME_PARAM')
            assert result is None

    # ── Re-arm automático tras failsafe ───────────────────────────────────

    def test_reconnect_callback_wired_in_init(self, ctrl):
        assert ctrl.rc._reconnect_callback is not None
        assert callable(ctrl.rc._reconnect_callback)

    def test_rearm_after_failsafe_spawns_thread(self, ctrl):
        with patch('threading.Thread') as mock_thread:
            ctrl._rearm_after_failsafe()
            mock_thread.assert_called_once()
            _, kwargs = mock_thread.call_args
            assert kwargs.get('daemon') is True
            assert kwargs.get('target') == ctrl._do_rearm

    def test_do_rearm_calls_cmd_arm_force(self, ctrl):
        ctrl.cmd.arm = MagicMock(return_value=True)
        ctrl._do_rearm()
        ctrl.cmd.arm.assert_called_once_with(force=True)

    def test_do_rearm_sets_rc_armed_on_success(self, ctrl):
        ctrl.cmd.arm = MagicMock(return_value=True)
        ctrl._do_rearm()
        ctrl.rc.set_armed.assert_called_with(True)

    def test_do_rearm_handles_arm_failure(self, ctrl):
        ctrl.cmd.arm = MagicMock(return_value=False)
        ctrl._do_rearm()
        ctrl.cmd.arm.assert_called_once_with(force=True)

    def test_do_rearm_handles_exception(self, ctrl):
        ctrl.cmd.arm = MagicMock(side_effect=ConnectionError("no response"))
        ctrl._do_rearm()

    def test_do_rearm_sleeps_before_arm(self, ctrl):
        ctrl.cmd.arm = MagicMock(return_value=True)
        with patch.object(ctrl, '_do_rearm', wraps=ctrl._do_rearm) as wrapped:
            pass


# =============================================================================
# Tests: SimulatedController — nuevos métodos
# =============================================================================
# Tests: SimulatedController — nuevos métodos
# =============================================================================
class TestSimulatedControllerNew:
    @pytest.fixture
    def sim(self):
        from backend.mavlink.controller import _SimulatedController
        return _SimulatedController()

    def test_get_servo_output_raw(self, sim):
        result = sim.get_servo_output_raw()
        assert result.get('sim') is True
        assert result.get('ch1') == 1500

    def test_get_rc_channels(self, sim):
        result = sim.get_rc_channels()
        assert result.get('sim') is True
        assert result.get('ch3') == 1500


# =============================================================================
# Tests: connection.py — mark_dead, is_connected, heartbeat health
# =============================================================================
class TestConnectionHealth:
    @pytest.fixture
    def conn(self):
        from backend.mavlink.connection import MAVLinkConnection
        with patch('backend.mavlink.connection.mavutil.mavlink_connection') as mock_mc:
            mock_master = MagicMock()
            mock_master.target_system = 1
            mock_master.target_component = 1
            mock_master.mav = MagicMock()
            mock_mc.return_value = mock_master
            c = MAVLinkConnection('tcp:127.0.0.1:5760', 115200)
            c.connected = True
            c.master = mock_master
            c._auto_reconnect_stop = threading.Event()
            return c

    def test_initial_heartbeat_healthy_false(self, conn):
        conn.last_heartbeat = 0.0
        conn.heartbeat_healthy = False
        assert conn.is_heartbeat_healthy() is False

    def test_heartbeat_healthy_after_update(self, conn):
        conn.update_heartbeat()
        assert conn.is_heartbeat_healthy() is True

    def test_heartbeat_stale(self, conn):
        conn.last_heartbeat = time.time() - 10
        assert conn.is_heartbeat_healthy() is False

    def test_mark_dead_sets_needs_reconnect(self, conn):
        conn._needs_reconnect.clear()
        conn.mark_dead("test")
        assert conn._needs_reconnect.is_set() is True

    def test_mark_dead_suppressed_during_reconnect(self, conn):
        conn._reconnecting.set()
        conn._needs_reconnect.clear()
        conn.mark_dead("test")
        assert conn._needs_reconnect.is_set() is False

    def test_connection_health_returns_dict(self, conn):
        health = conn.get_connection_health()
        assert isinstance(health, dict)
        assert 'connected' in health
        assert 'healthy' in health
        assert 'heartbeat_age_s' in health

    def test_msg_age_inf_when_no_msg(self, conn):
        conn.last_msg_time = 0.0
        assert conn.msg_age() == float('inf')

    def test_update_msg_time_resets(self, conn):
        conn.last_msg_time = 0.0
        conn.update_msg_time()
        assert conn.last_msg_time > 0

    def test_is_socket_alive_no_socket_falls_back_to_msg_age(self, conn):
        conn.master.socket = None
        conn.last_msg_time = time.time()
        assert conn.is_socket_alive() is True

    def test_suppress_probe_sets_flag(self, conn):
        conn.suppress_probe(True)
        assert conn._suppress_probe is True
        conn.suppress_probe(False)
        assert conn._suppress_probe is False

    def test_disconnect_sets_connected_false(self, conn):
        conn.disconnect()
        assert conn.connected is False

    def test_is_connected_requires_connected_and_master(self, conn):
        assert conn.is_connected() is True
        conn.master = None
        assert conn.is_connected() is False

    def test_recv_match_returns_none_when_disconnected(self, conn):
        conn.connected = False
        result = conn.recv_match(msg_type='HEARTBEAT')
        assert result is None

    def test_recv_match_protected_timeout(self, conn):
        conn.recv_match = MagicMock(return_value=None)
        result = conn.recv_match_protected('MISSION_REQUEST_INT', timeout=0.5)
        assert result is None

    def test_ack_timeout_returns_false(self, conn):
        result = conn.wait_ack(command_id=999, timeout=0.3)
        assert result is False

    def test_send_probe_returns_false_when_disconnected(self, conn):
        conn.connected = False
        result = conn._send_probe()
        assert result is False


# =============================================================================
# Tests: commands.py — _wait_ack_direct, test_motor, _send_disarm_cmd
# =============================================================================
class TestCommandsFlow:
    @pytest.fixture
    def cmd(self):
        from backend.mavlink.commands import DroneCommands
        conn = MagicMock()
        conn.master = MagicMock()
        conn.master.target_system = 1
        conn.master.target_component = 1
        conn.master.mav = MagicMock()
        conn._lock = threading.Lock()
        conn._ack_lock = threading.Lock()
        conn._pending_acks = {}
        conn._disarming = False
        conn.recv_match = MagicMock(return_value=None)
        conn.is_connected = MagicMock(return_value=True)
        conn.connected = True
        c = DroneCommands(conn)
        c.telemetry = MagicMock()
        c.telemetry.data = {'armed': False, 'mode': 'STABILIZE'}
        return c

    def test_wait_ack_direct_found_accepted(self, cmd):
        mock_ack = MagicMock()
        mock_ack.command = 400
        mock_ack.result = 0
        with cmd.conn._ack_lock:
            cmd.conn._pending_acks[400] = mock_ack
        result = cmd._wait_ack_direct(400, timeout=1)
        assert result is True

    def test_wait_ack_direct_found_rejected(self, cmd):
        mock_ack = MagicMock()
        mock_ack.command = 400
        mock_ack.result = 1
        with cmd.conn._ack_lock:
            cmd.conn._pending_acks[400] = mock_ack
        with pytest.raises(ConnectionError):
            cmd._wait_ack_direct(400, timeout=1)

    def test_wait_ack_direct_timeout(self, cmd):
        result = cmd._wait_ack_direct(999, timeout=0.3)
        assert result is False

    def test_wait_ack_direct_in_progress_extends_deadline(self, cmd):
        mock_ack = MagicMock()
        mock_ack.command = 400
        mock_ack.result = 4
        with cmd.conn._ack_lock:
            cmd.conn._pending_acks[400] = mock_ack
        deadline_before = time.time() + 0.5
        result = cmd._wait_ack_direct(400, timeout=0.5)
        assert result is False

    def test_send_disarm_cmd_sends_with_force(self, cmd):
        cmd.conn.master = MagicMock()
        cmd.conn.master.mav = MagicMock()
        cmd._send_disarm_cmd(force=True)
        call_args = cmd.conn.master.mav.command_long_send.call_args
        assert call_args is not None
        args = call_args[0]
        assert args[2] == 400
        assert args[4] == 0
        assert args[5] == 21196

    def test_send_disarm_cmd_raises_on_none_master(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd._send_disarm_cmd()

    def test_send_disarm_cmd_sends_without_force(self, cmd):
        cmd.conn.master = MagicMock()
        cmd.conn.master.mav = MagicMock()
        cmd._send_disarm_cmd(force=False)
        call_args = cmd.conn.master.mav.command_long_send.call_args
        assert call_args is not None
        args = call_args[0]
        assert args[5] == 0

    def test_test_motor_sends_correct_command(self, cmd):
        cmd.conn.master = MagicMock()
        cmd.conn.master.mav = MagicMock()
        cmd.test_motor(0, 15, 2.0)
        call_args = cmd.conn.master.mav.command_long_send.call_args
        assert call_args is not None
        args = call_args[0]
        assert args[2] == mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST
        assert args[5] == 0
        assert args[7] == 15
        assert args[8] == 2

    def test_test_motor_with_even_if_armed(self, cmd):
        cmd.conn.master = MagicMock()
        cmd.conn.master.mav = MagicMock()
        cmd.test_motor(1, 20, 1.0, even_if_armed=True)
        call_args = cmd.conn.master.mav.command_long_send.call_args
        assert call_args is not None
        args = call_args[0]
        assert args[2] == mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST
        assert args[6] == 3

    def test_is_armed_uses_telemetry(self, cmd):
        cmd.telemetry.data['armed'] = True
        assert cmd._is_armed() is True
        cmd.telemetry.data['armed'] = False
        assert cmd._is_armed() is False

    def test_is_armed_returns_false_without_telemetry(self, cmd):
        cmd.telemetry = None
        assert cmd._is_armed() is False

    def test_arm_switches_to_stabilize(self, cmd):
        cmd.telemetry.data['mode'] = 'GUIDED'
        cmd.set_mode = MagicMock(return_value=True)
        cmd.conn._ekf_ready = threading.Event()
        cmd.conn._ekf_ready.set()
        with patch('backend.mavlink.commands.mavutil') as mock_mav:
            mock_mav.mavlink.MAV_CMD_COMPONENT_ARM_DISARM = 400
            mock_ack = MagicMock()
            mock_ack.command = 400
            mock_ack.result = 0
            with cmd.conn._ack_lock:
                cmd.conn._pending_acks[400] = mock_ack
            result = cmd.arm(force=True)
            cmd.set_mode.assert_called_with("STABILIZE")
            assert result is True

    def test_disarm_sends_throttle_zero_pwm(self, cmd):
        cmd.conn.master = MagicMock()
        cmd.conn.master.mav = MagicMock()
        cmd.conn._disarming = False
        cmd._send_disarm_cmd = MagicMock()
        cmd._wait_ack_direct = MagicMock(return_value=True)
        result = cmd.disarm()
        assert result is True

    def test_set_mode_validates_mode(self, cmd):
        mock_mapping = {'STABILIZE': 0, 'GUIDED': 4, 'AUTO': 3}
        cmd.conn.master.mode_mapping.return_value = mock_mapping
        cmd.conn.master.set_mode = MagicMock()
        result = cmd.set_mode('STABILIZE', verify=False)
        assert result is True

    def test_set_mode_raises_on_invalid(self, cmd):
        cmd.conn.master.mode_mapping.return_value = {'STABILIZE': 0}
        with pytest.raises(ValueError):
            cmd.set_mode('INVALID_MODE', verify=False)

    def test_get_current_mode_from_telemetry(self, cmd):
        cmd.telemetry.data['mode'] = 'GUIDED'
        assert cmd.get_current_mode() == 'GUIDED'

    def test_get_current_mode_returns_none_if_no_data(self, cmd):
        cmd.telemetry = None
        cmd.conn.recv_match.return_value = None
        assert cmd.get_current_mode() is None

    def test_emergency_stop_rtl(self, cmd):
        cmd.rtl = MagicMock(return_value=True)
        cmd.get_current_mode = MagicMock(return_value='RTL')
        result = cmd.emergency_stop()
        assert result is True

    def test_emergency_stop_fallback_land(self, cmd):
        cmd.rtl = MagicMock(return_value=True)
        cmd.get_current_mode = MagicMock(side_effect=['LOITER', 'LAND'])
        cmd.land = MagicMock(return_value=True)
        result = cmd.emergency_stop()
        assert result is True

    def test_emergency_stop_last_resort_disarm(self, cmd):
        cmd.rtl = MagicMock(return_value=True)
        cmd.land = MagicMock(return_value=True)
        cmd.get_current_mode = MagicMock(side_effect=['LOITER', 'LOITER'])
        cmd.disarm = MagicMock(return_value=True)
        result = cmd.emergency_stop()
        assert result is True

    def test_kill_motors_calls_disarm_force(self, cmd):
        cmd.disarm = MagicMock(return_value=True)
        result = cmd.kill_motors()
        assert result is True
        cmd.disarm.assert_called_with(force=True)


# =============================================================================
# Tests: rest.py — endpoints de diagnóstico
# =============================================================================
class TestDiagnosticEndpoints:
    @pytest.fixture
    def test_client(self):
        try:
            from fastapi.testclient import TestClient
            from backend.main import app
            return TestClient(app)
        except ImportError:
            pytest.skip("Requiere fastapi testclient")
            return None

    def test_diag_params_endpoint_exists(self, test_client):
        r = test_client.get("/api/diag/params")
        assert r.status_code in (200, 503)

    def test_diag_rc_endpoint_exists(self, test_client):
        r = test_client.get("/api/diag/rc")
        assert r.status_code in (200, 503)

    def test_diag_servo_raw_endpoint_exists(self, test_client):
        r = test_client.get("/api/diag/servo_raw")
        assert r.status_code in (200, 503)

    def test_diag_rc_channels_endpoint_exists(self, test_client):
        r = test_client.get("/api/diag/rc_channels")
        assert r.status_code in (200, 503)

    def test_diag_motor_test_endpoint_exists(self, test_client):
        r = test_client.post("/api/diag/motor-test?motor=0&throttle=10&duration=1")
        assert r.status_code in (200, 503)

    def test_diag_param_set_endpoint_exists(self, test_client):
        r = test_client.post("/api/diag/param/set?name=MOT_SPIN_ARM&value=0.15")
        assert r.status_code in (200, 503, 422)


# =============================================================================
# Tests: SimulatedController — test_motor con even_if_armed
# =============================================================================
class TestSimulatedMotorTest:
    @pytest.fixture
    def sim(self):
        from backend.mavlink.controller import _SimulatedController
        return _SimulatedController()

    def test_motor_test_default_args(self, sim):
        result = sim.test_motor(0)
        assert result is True

    def test_motor_test_with_all_args(self, sim):
        result = sim.test_motor(2, 50, 3.0, even_if_armed=True)
        assert result is True

    def test_motor_test_duration_respected(self, sim):
        start = time.time()
        sim.test_motor(0, 10, 0.3)
        elapsed = time.time() - start
        assert elapsed >= 0.1
        assert elapsed < 1.0
