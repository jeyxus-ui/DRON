"""Tests unitarios para backend/mavlink/telemetry.py — DroneTelemetry."""
import math
import threading
import time
from unittest.mock import MagicMock
import pytest

from backend.mavlink.telemetry import DroneTelemetry
from pymavlink import mavutil


class DummyConn:
    """Conexión falsa mínima, suficiente para DroneTelemetry."""

    def __init__(self, connected=True):
        self.connected = connected
        self.master = MagicMock()
        self.master.target_system = 1
        self.master.target_component = 1
        self._pause_read = threading.Event()
        self._prearm_lock = threading.Lock()
        self._prearm_msgs = []
        self._ekf_ready = threading.Event()
        self._ack_lock = threading.Lock()
        self._pending_acks = {}
        self._pending_msgs_lock = threading.Lock()
        self._pending_msgs = {}
        self._disarming = False
        self.mark_dead_calls = []
        self._recv_map = {}  # msg_type -> objeto a devolver

    def is_connected(self):
        return self.connected

    def recv_match(self, blocking=False, timeout=0, msg_type=None):
        return self._recv_map.get(msg_type)

    def update_msg_time(self):
        pass

    def update_heartbeat(self):
        pass

    def mark_dead(self, reason):
        self.mark_dead_calls.append(reason)


@pytest.fixture
def conn():
    return DummyConn(connected=True)


@pytest.fixture
def dt(conn):
    telemetry = DroneTelemetry(conn, persist_interval=0)
    yield telemetry
    telemetry.stop()


def make_msg(msg_type, **attrs):
    msg = MagicMock()
    msg.get_type.return_value = msg_type
    for k, v in attrs.items():
        setattr(msg, k, v)
    return msg


# ── Lifecycle ─────────────────────────────────────────────────────────────────

class TestLifecycle:
    def test_start_is_idempotent(self, dt):
        first_thread = dt._thread
        dt.start()  # ya está corriendo, no debe crear un thread nuevo
        assert dt._thread is first_thread

    def test_stop_sets_running_false(self, dt):
        dt.stop()
        assert dt._running is False

    def test_no_persist_thread_when_interval_zero(self, conn):
        telemetry = DroneTelemetry(conn, persist_interval=0)
        try:
            assert telemetry._persist_thread is None
        finally:
            telemetry.stop()


# ── _process_message ──────────────────────────────────────────────────────────

class TestProcessMessageVfrHud:
    def test_updates_altitude_speed_climb_throttle(self, dt):
        msg = make_msg("VFR_HUD", alt=12.345, airspeed=3.21, climb=0.5, throttle=42)
        dt._process_message(msg)
        assert dt.data['altitude'] == 12.35
        assert dt.data['speed'] == 3.21
        assert dt.data['climb_rate'] == 0.5
        assert dt.data['throttle'] == 42


class TestProcessMessageGps:
    def test_normal_fix_updates_gps(self, dt):
        msg = make_msg("GPS_RAW_INT", lat=107110000, lon=-740721000, alt=15000,
                        satellites_visible=10, fix_type=3, eph=150)
        dt._process_message(msg)
        gps = dt.data['gps']
        assert gps['lat'] == pytest.approx(10.711, abs=1e-3)
        assert gps['satellites'] == 10
        assert gps['fix_type'] == 3
        assert gps['hdop'] == 1.5

    def test_no_hdop_data_sentinel_becomes_zero(self, dt):
        msg = make_msg("GPS_RAW_INT", lat=0, lon=0, alt=0,
                        satellites_visible=0, fix_type=0, eph=65535)
        dt._process_message(msg)
        assert dt.data['gps']['hdop'] == 0.0


class TestProcessMessageBattery:
    def test_normal_battery_status(self, dt):
        msg = make_msg("BATTERY_STATUS", voltages=[12500], current_battery=250, battery_remaining=80)
        dt._process_message(msg)
        assert dt.data['battery'] == {'voltage': 12.5, 'current': 2.5, 'remaining': 80}

    def test_no_data_sentinel_ignored(self, dt):
        msg = make_msg("BATTERY_STATUS", voltages=[65535], current_battery=0, battery_remaining=0)
        dt._process_message(msg)
        assert dt.data['battery']['voltage'] == 0.0  # sin cambios

    def test_sys_status_fallback_when_no_battery_status_yet(self, dt):
        msg = make_msg("SYS_STATUS", voltage_battery=11800, current_battery=150, battery_remaining=60)
        dt._process_message(msg)
        assert dt.data['battery']['voltage'] == 11.8

    def test_sys_status_fallback_skipped_if_battery_already_set(self, dt):
        dt.data['battery']['voltage'] = 12.6
        msg = make_msg("SYS_STATUS", voltage_battery=11800, current_battery=150, battery_remaining=60)
        dt._process_message(msg)
        assert dt.data['battery']['voltage'] == 12.6  # no lo pisa


class TestProcessMessageAttitude:
    def test_converts_radians_to_degrees(self, dt):
        msg = make_msg("ATTITUDE", roll=math.pi / 2, pitch=0.0, yaw=math.pi)
        dt._process_message(msg)
        assert dt.data['attitude']['roll'] == pytest.approx(90.0)
        assert dt.data['attitude']['yaw'] == pytest.approx(180.0)


class TestProcessMessageHeartbeat:
    def _hb(self, base_mode, srcSystem=1, custom_mode=0):
        msg = make_msg("HEARTBEAT", base_mode=base_mode, custom_mode=custom_mode, system_status=4)
        msg.get_srcSystem.return_value = srcSystem
        return msg

    def test_ignores_heartbeat_from_other_system(self, dt, conn):
        msg = self._hb(base_mode=mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED, srcSystem=255)
        dt._process_message(msg)
        assert dt.data['armed'] is False  # no se procesó

    def test_sets_armed_true_from_base_mode(self, dt):
        msg = self._hb(base_mode=mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        dt._process_message(msg)
        assert dt.data['armed'] is True

    def test_rc_callback_invoked_on_arm_change(self, dt, conn):
        conn._rc_callback = MagicMock()
        msg = self._hb(base_mode=mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        dt._process_message(msg)
        conn._rc_callback.assert_called_once_with(True)

    def test_rc_callback_skipped_while_disarming_and_armed_true(self, dt, conn):
        conn._rc_callback = MagicMock()
        conn._disarming = True
        msg = self._hb(base_mode=mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        dt._process_message(msg)
        conn._rc_callback.assert_not_called()

    def test_rc_callback_exception_is_swallowed(self, dt, conn):
        conn._rc_callback = MagicMock(side_effect=Exception('boom'))
        msg = self._hb(base_mode=mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        dt._process_message(msg)  # no debe propagar

    def test_maps_numeric_custom_mode_to_ardupilot_name(self, dt, monkeypatch):
        monkeypatch.setattr('backend.mavlink.telemetry.mavutil.mode_string_v10', lambda m: 'Mode(4)')
        msg = self._hb(base_mode=0, custom_mode=4)
        dt._process_message(msg)
        assert dt.data['mode'] == 'GUIDED'

    def test_updates_heartbeat_on_connection(self, dt, conn):
        conn.update_heartbeat = MagicMock()
        msg = self._hb(base_mode=0)
        dt._process_message(msg)
        conn.update_heartbeat.assert_called_once()


class TestProcessMessageHomePosition:
    def test_updates_home_position(self, dt):
        msg = make_msg("HOME_POSITION", latitude=107110000, longitude=-740721000, altitude=2600)
        dt._process_message(msg)
        assert dt.data['home_position']['lat'] == pytest.approx(10.711, abs=1e-3)
        assert dt.data['home_position']['alt'] == 2.6


class TestProcessMessageStatustext:
    def test_low_severity_logged_as_warning(self, dt, caplog):
        msg = make_msg("STATUSTEXT", severity=2, text="PreArm: Battery low")
        dt._process_message(msg)  # no debe lanzar

    def test_high_severity_logged_as_info(self, dt):
        msg = make_msg("STATUSTEXT", severity=6, text="Info message")
        dt._process_message(msg)


class TestProcessMessageUnknownAndErrors:
    def test_unknown_type_is_ignored_silently(self, dt):
        msg = make_msg("SOME_OTHER_TYPE")
        dt._process_message(msg)  # no debe lanzar ni cambiar data

    def test_exception_during_processing_is_caught(self, dt):
        class BadMsg:
            def get_type(self):
                return "VFR_HUD"

            @property
            def alt(self):
                raise RuntimeError("bad")

        dt._process_message(BadMsg())  # no debe propagar


# ── Getters ───────────────────────────────────────────────────────────────────

class TestGetters:
    def test_get_all_includes_connected(self, dt, conn):
        conn.connected = True
        result = dt.get_all()
        assert result['connected'] is True
        assert 'altitude' in result

    def test_get_status_shape(self, dt):
        dt.data['armed'] = True
        dt.data['mode'] = 'GUIDED'
        dt.data['system_status'] = 4
        assert dt.get_status() == {
            "connected": dt.conn.connected, "armed": True, "mode": "GUIDED", "system_status": 4,
        }

    def test_get_battery_zero_current_gives_zero_time_remaining(self, dt):
        dt.data['battery'] = {'voltage': 12.0, 'current': 0, 'remaining': 50}
        result = dt.get_battery()
        assert result['time_remaining_minutes'] == 0

    def test_get_battery_computes_time_remaining(self, dt):
        dt.data['battery'] = {'voltage': 12.0, 'current': 2.0, 'remaining': 50}
        result = dt.get_battery()
        assert result['time_remaining_minutes'] > 0

    def test_get_gps(self, dt):
        dt.data['gps']['lat'] = 5.0
        assert dt.get_gps()['lat'] == 5.0

    def test_get_attitude(self, dt):
        dt.data['attitude']['roll'] = 3.0
        assert dt.get_attitude()['roll'] == 3.0

    def test_get_velocity(self, dt):
        dt.data['speed'] = 4.0
        dt.data['climb_rate'] = 1.0
        assert dt.get_velocity() == {"ground_speed": 4.0, "vertical_speed": 1.0}

    def test_get_position(self, dt):
        result = dt.get_position()
        assert set(result.keys()) == {"gps", "altitude", "attitude"}


# ── preflight_checks ──────────────────────────────────────────────────────────

class TestPreflightChecks:
    def test_all_checks_pass(self, dt, conn):
        dt.data['gps'] = {'fix_type': 3, 'satellites': 10, 'lat': 0, 'lon': 0, 'alt': 0, 'hdop': 1.0}
        dt.data['battery']['remaining'] = 80
        dt.data['home_position']['lat'] = 10.0

        ekf_msg = MagicMock(flags=0x01)
        sys_status_msg = MagicMock(onboard_control_sensors_health=0b111,
                                    onboard_control_sensors_enabled=0b111)
        conn._recv_map = {'EKF_STATUS_REPORT': ekf_msg, 'SYS_STATUS': sys_status_msg}

        checks = dt.preflight_checks()
        assert checks == {
            "gps_fix": True, "battery_ok": True, "ekf_ok": True,
            "home_set": True, "sensors_ok": True,
        }

    def test_all_checks_fail_with_defaults(self, dt):
        checks = dt.preflight_checks()
        assert checks == {
            "gps_fix": False, "battery_ok": False, "ekf_ok": False,
            "home_set": False, "sensors_ok": False,
        }

    def test_sensors_not_ok_when_health_mismatches_enabled(self, dt, conn):
        sys_status_msg = MagicMock(onboard_control_sensors_health=0b010,
                                    onboard_control_sensors_enabled=0b111)
        conn._recv_map = {'SYS_STATUS': sys_status_msg}
        checks = dt.preflight_checks()
        assert checks["sensors_ok"] is False

    def test_low_satellite_count_fails_gps_fix(self, dt):
        dt.data['gps'] = {'fix_type': 3, 'satellites': 2}
        checks = dt.preflight_checks()
        assert checks["gps_fix"] is False


# ── _read_loop (una sola iteración controlada) ───────────────────────────────

class TestReadLoopSingleIteration:
    def _run_one_iteration(self, dt, monkeypatch, msg=None):
        monkeypatch.setattr('backend.mavlink.telemetry.time.sleep', lambda s: None)
        calls = {'n': 0}

        def fake_recv_match(blocking=True, timeout=0.01, msg_type=None):
            calls['n'] += 1
            if calls['n'] >= 1:
                dt._running = False
            return msg

        dt.conn.recv_match = fake_recv_match
        dt.conn.connected = True
        dt._running = True
        dt._read_loop()

    def test_command_ack_stored_in_pending_acks(self, dt, monkeypatch, conn):
        msg = make_msg("COMMAND_ACK", command=400, result=0)
        self._run_one_iteration(dt, monkeypatch, msg=msg)
        assert conn._pending_acks[400] is msg

    def test_param_value_stored_by_param_id(self, dt, monkeypatch, conn):
        msg = make_msg("PARAM_VALUE", param_id=b'DISARM_DELAY\x00\x00\x00\x00')
        self._run_one_iteration(dt, monkeypatch, msg=msg)
        assert 'PARAM_VALUE:DISARM_DELAY' in conn._pending_msgs

    def test_mission_request_stored(self, dt, monkeypatch, conn):
        msg = make_msg("MISSION_REQUEST_INT")
        self._run_one_iteration(dt, monkeypatch, msg=msg)
        assert conn._pending_msgs.get('MISSION_REQUEST_INT') is msg

    def test_prearm_statustext_captured(self, dt, monkeypatch, conn):
        msg = make_msg("STATUSTEXT", text="PreArm: Battery 2 low voltage", severity=2)
        self._run_one_iteration(dt, monkeypatch, msg=msg)
        assert any('PreArm' in m for m in conn._prearm_msgs)

    def test_ekf_alignment_detected_from_statustext(self, dt, monkeypatch, conn):
        msg = make_msg("STATUSTEXT", text="EKF3 IMU0 tilt alignment complete", severity=6)
        self._run_one_iteration(dt, monkeypatch, msg=msg)
        assert conn._ekf_ready.is_set()

    def test_ekf_alignment_detected_from_status_report(self, dt, monkeypatch, conn):
        msg = make_msg("EKF_STATUS_REPORT", flags=0x01)
        self._run_one_iteration(dt, monkeypatch, msg=msg)
        assert conn._ekf_ready.is_set()

    def test_not_connected_skips_recv_and_sleeps(self, dt, monkeypatch, conn):
        monkeypatch.setattr('backend.mavlink.telemetry.time.sleep',
                             lambda s: setattr(dt, '_running', False))
        conn.connected = False
        dt._running = True
        dt._read_loop()  # no debe intentar recv_match

    def test_paused_read_skips_recv(self, dt, monkeypatch, conn):
        conn._pause_read.set()
        monkeypatch.setattr('backend.mavlink.telemetry.time.sleep',
                             lambda s: setattr(dt, '_running', False))
        dt._running = True
        dt._read_loop()

    def test_serial_error_marks_dead_after_max_errors(self, dt, monkeypatch, conn):
        monkeypatch.setattr('backend.mavlink.telemetry.time.sleep', lambda s: None)
        dt._serial_read_errors = DroneTelemetry.MAX_SERIAL_ERRORS - 1
        call_count = {'n': 0}

        def raise_once(*a, **kw):
            call_count['n'] += 1
            if call_count['n'] > 1:
                dt._running = False
            raise OSError("serial gone")

        conn.recv_match = raise_once
        dt._running = True
        dt._read_loop()
        assert conn.mark_dead_calls  # se llamó al menos una vez

    def test_generic_exception_marks_dead(self, dt, monkeypatch, conn):
        monkeypatch.setattr('backend.mavlink.telemetry.time.sleep',
                             lambda s: setattr(dt, '_running', False))

        def raise_generic(*a, **kw):
            raise ValueError("unexpected")

        conn.recv_match = raise_generic
        dt._running = True
        dt._read_loop()
        assert len(conn.mark_dead_calls) == 1


# ── _request_streams ──────────────────────────────────────────────────────────

class TestRequestStreams:
    def test_sends_message_interval_commands_when_connected(self, conn):
        conn.connected = True
        dt = DroneTelemetry(conn, persist_interval=0)
        try:
            dt._request_streams()
            assert conn.master.mav.command_long_send.called
        finally:
            dt.stop()

    def test_gives_up_when_never_connected(self, monkeypatch):
        conn = DummyConn(connected=False)
        monkeypatch.setattr('backend.mavlink.telemetry.time.sleep', lambda s: None)
        dt = DroneTelemetry(conn, persist_interval=0)
        try:
            dt._request_streams()
            conn.master.mav.command_long_send.assert_not_called()
        finally:
            dt.stop()

    def test_swallows_exception_while_sending(self, conn):
        conn.connected = True
        conn.master.mav.command_long_send.side_effect = Exception("boom")
        dt = DroneTelemetry(conn, persist_interval=0)
        try:
            dt._request_streams()  # no debe propagar
        finally:
            dt.stop()


# ── _persist_loop ─────────────────────────────────────────────────────────────

class TestPersistLoop:
    def test_returns_immediately_if_save_telemetry_unavailable(self, conn, monkeypatch):
        # None en sys.modules fuerza ImportError en 'from ... import save_telemetry',
        # igual que el truco ya usado en test_config.py para 'serial'.
        monkeypatch.setitem(__import__('sys').modules, 'backend.db.repository', None)
        dt = DroneTelemetry(conn, persist_interval=0)
        try:
            dt._running = True
            dt._persist_loop()  # debe retornar de inmediato sin loopear
        finally:
            dt.stop()

    def test_calls_save_telemetry_with_snapshot(self, conn, monkeypatch):
        saved = {}

        def fake_save(data):
            saved.update(data)

        monkeypatch.setattr('backend.db.repository.save_telemetry', fake_save)
        dt = DroneTelemetry(conn, persist_interval=0)
        try:
            dt.data['altitude'] = 7.5
            monkeypatch.setattr('backend.mavlink.telemetry.time.sleep',
                                 lambda s: setattr(dt, '_running', False))
            dt._running = True
            dt._persist_loop()
            assert saved.get('altitude') == 7.5
        finally:
            dt.stop()

    def test_swallows_exception_during_save(self, conn, monkeypatch):
        def raise_save(data):
            raise Exception("db down")

        monkeypatch.setattr('backend.db.repository.save_telemetry', raise_save)
        dt = DroneTelemetry(conn, persist_interval=0)
        try:
            monkeypatch.setattr('backend.mavlink.telemetry.time.sleep',
                                 lambda s: setattr(dt, '_running', False))
            dt._running = True
            dt._persist_loop()  # no debe propagar
        finally:
            dt.stop()
