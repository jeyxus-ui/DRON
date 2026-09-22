"""Tests unitarios adicionales para backend/mavlink/commands.py — DroneCommands.

Complementa backend/tests/test_motores.py (que ya cubre arm()/test_motor()/
_wait_ack_direct en detalle) con el resto de los métodos: disarm, set_mode,
takeoff, land, rtl/loiter, set_nav_speed, goto_position, set_velocity,
emergency_stop, kill_motors, get_current_mode, reboot_autopilot.
"""
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from backend.mavlink.commands import DroneCommands
from pymavlink import mavutil


@pytest.fixture
def cmd():
    conn = MagicMock()
    conn.master = MagicMock()
    conn.master.target_system = 1
    conn.master.target_component = 1
    conn.master.mav = MagicMock()
    conn._lock = threading.Lock()
    conn._ack_lock = threading.Lock()
    conn._pending_acks = {}
    conn._prearm_lock = threading.Lock()
    conn._prearm_msgs = []
    conn._disarming = False
    conn._rc_callback = None
    conn.recv_match = MagicMock(return_value=None)
    conn.is_connected = MagicMock(return_value=True)
    conn.connected = True
    c = DroneCommands(conn)
    c.telemetry = MagicMock()
    c.telemetry.data = {'armed': False, 'mode': 'STABILIZE'}
    return c


def ack(command, result=0):
    m = MagicMock()
    m.command = command
    m.result = result
    return m


class TestGetPrearmReason:
    def test_empty_when_no_messages(self, cmd):
        assert cmd._get_prearm_reason() == ""

    def test_joins_messages(self, cmd):
        cmd.conn._prearm_msgs = ["PreArm: GPS", "PreArm: Compass"]
        result = cmd._get_prearm_reason()
        assert "GPS" in result and "Compass" in result

    def test_swallows_exception(self, cmd):
        cmd.conn._prearm_lock = MagicMock()
        cmd.conn._prearm_lock.__enter__.side_effect = Exception('boom')
        assert cmd._get_prearm_reason() == ""


class TestIsArmed:
    def test_true_from_telemetry(self, cmd):
        cmd.telemetry.data['armed'] = True
        assert cmd._is_armed() is True

    def test_false_without_telemetry(self, cmd):
        cmd.telemetry = None
        assert cmd._is_armed() is False

    def test_false_on_exception(self, cmd):
        cmd.telemetry = MagicMock()
        type(cmd.telemetry).data = property(lambda self: (_ for _ in ()).throw(Exception('x')))
        assert cmd._is_armed() is False


class TestArmEdgeCases:
    def test_no_connection_raises(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.arm()

    def test_already_armed_returns_true_immediately(self, cmd):
        cmd.telemetry.data['armed'] = True
        assert cmd.arm() is True

    def test_ekf_not_ready_still_proceeds_after_wait(self, cmd):
        cmd.conn._ekf_ready = threading.Event()  # nunca se setea
        cmd.conn._ack_lock = threading.Lock()
        with cmd.conn._ack_lock:
            cmd.conn._pending_acks[mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM] = ack(
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)
        with patch('backend.mavlink.commands.time.sleep'):
            result = cmd.arm(force=True)
        assert result is True


class TestDisarm:
    def test_no_connection_raises(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.disarm()

    def test_success_via_ack(self, cmd):
        with cmd.conn._ack_lock:
            cmd.conn._pending_acks[mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM] = ack(
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.disarm() is True
        assert cmd._disarming is False
        assert cmd.conn._disarming is False

    def test_calls_rc_callback_false_before_disarm(self, cmd):
        cmd.conn._rc_callback = MagicMock()
        with cmd.conn._ack_lock:
            cmd.conn._pending_acks[mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM] = ack(
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)
        with patch('backend.mavlink.commands.time.sleep'):
            cmd.disarm()
        cmd.conn._rc_callback.assert_called_once_with(False)

    def test_rejected_without_force_retries_with_force(self, cmd):
        acks = iter([
            ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 4),  # rechazado
            ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0),  # con force
        ])

        def fake_wait_ack_direct(command_id, timeout=10):
            a = next(acks, None)
            if a is None:
                return False
            if a.result == 0:
                return True
            raise ConnectionError(f"rejected result={a.result}")

        cmd._wait_ack_direct = fake_wait_ack_direct
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.disarm(force=False) is True

    def test_falls_back_to_telemetry_confirmation(self, cmd):
        cmd._wait_ack_direct = MagicMock(return_value=False)
        cmd.telemetry.data['armed'] = False
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.disarm(force=True) is True

    def test_raises_when_nothing_confirms(self, cmd):
        cmd._wait_ack_direct = MagicMock(return_value=False)
        cmd.telemetry.data['armed'] = True
        with patch('backend.mavlink.commands.time.time', side_effect=list(range(0, 200, 1))), \
             patch('backend.mavlink.commands.time.sleep'):
            with pytest.raises(ConnectionError):
                cmd.disarm(force=True)


class TestSetMode:
    def test_no_connection_raises(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.set_mode('STABILIZE')

    def test_invalid_mode_raises(self, cmd):
        cmd.conn.master.mode_mapping.return_value = {'STABILIZE': 0}
        with pytest.raises(ValueError):
            cmd.set_mode('NOT_A_MODE')

    def test_no_verify_returns_true_immediately(self, cmd):
        cmd.conn.master.mode_mapping.return_value = {'GUIDED': 4}
        assert cmd.set_mode('GUIDED', verify=False) is True
        cmd.conn.master.set_mode.assert_called_once_with(4)

    def test_verify_success_first_try(self, cmd):
        cmd.conn.master.mode_mapping.return_value = {'GUIDED': 4}
        cmd.get_current_mode = MagicMock(return_value='GUIDED')
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.set_mode('GUIDED') is True

    def test_verify_fails_after_max_attempts(self, cmd):
        cmd.conn.master.mode_mapping.return_value = {'GUIDED': 4}
        cmd.get_current_mode = MagicMock(return_value='STABILIZE')
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.set_mode('GUIDED', max_attempts=2) is False


class TestTakeoff:
    def test_arms_if_not_armed(self, cmd):
        cmd.telemetry.data['armed'] = False
        cmd.set_mode = MagicMock(return_value=True)
        cmd.arm = MagicMock(return_value=True)
        cmd._wait_ack_direct = MagicMock(return_value=True)
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.takeoff(10.0) is True
        cmd.arm.assert_called_once()

    def test_raises_when_arm_fails(self, cmd):
        cmd.telemetry.data['armed'] = False
        cmd.set_mode = MagicMock(return_value=True)
        cmd.arm = MagicMock(return_value=False)
        with patch('backend.mavlink.commands.time.sleep'):
            with pytest.raises(Exception):
                cmd.takeoff(10.0)

    def test_already_armed_skips_arm_call(self, cmd):
        cmd.telemetry.data['armed'] = True
        cmd.set_mode = MagicMock(return_value=True)
        cmd.arm = MagicMock()
        cmd._wait_ack_direct = MagicMock(return_value=True)
        with patch('backend.mavlink.commands.time.sleep'):
            cmd.takeoff(10.0)
        cmd.arm.assert_not_called()

    def test_falls_back_to_altitude_telemetry(self, cmd):
        cmd.telemetry.data = {'armed': True, 'mode': 'GUIDED', 'altitude': 5.0}
        cmd.set_mode = MagicMock(return_value=True)
        cmd._wait_ack_direct = MagicMock(return_value=False)
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.takeoff(10.0) is True

    def test_falls_back_to_armed_assumption(self, cmd):
        cmd.telemetry.data = {'armed': True, 'mode': 'GUIDED', 'altitude': 0.0}
        cmd.set_mode = MagicMock(return_value=True)
        cmd._wait_ack_direct = MagicMock(return_value=False)
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.takeoff(10.0) is True

    def test_returns_false_when_nothing_confirms(self, cmd):
        cmd.telemetry.data = {'armed': False, 'mode': 'GUIDED', 'altitude': 0.0}
        cmd.set_mode = MagicMock(return_value=True)
        cmd.arm = MagicMock(return_value=True)  # arm() reporta éxito...
        cmd._is_armed = MagicMock(return_value=False)  # ...pero telemetry nunca lo confirma
        cmd._wait_ack_direct = MagicMock(return_value=False)
        with patch('backend.mavlink.commands.time.time', side_effect=list(range(0, 200))), \
             patch('backend.mavlink.commands.time.sleep'):
            assert cmd.takeoff(10.0) is False


class TestLand:
    def test_success_via_ack(self, cmd):
        cmd._wait_ack_direct = MagicMock(return_value=True)
        assert cmd.land() is True

    def test_success_via_recv_match_fallback(self, cmd):
        cmd._wait_ack_direct = MagicMock(return_value=False)
        cmd.conn.recv_match.return_value = ack(mavutil.mavlink.MAV_CMD_NAV_LAND, 0)
        assert cmd.land() is True

    def test_rejected_returns_false(self, cmd):
        cmd._wait_ack_direct = MagicMock(return_value=False)
        cmd.conn.recv_match.return_value = None
        assert cmd.land() is False

    def test_no_connection_raises(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.land()


class TestRtlLoiter:
    def test_rtl_delegates_to_set_mode(self, cmd):
        cmd.set_mode = MagicMock(return_value=True)
        assert cmd.rtl() is True
        cmd.set_mode.assert_called_once_with('RTL')

    def test_loiter_delegates_to_set_mode(self, cmd):
        cmd.set_mode = MagicMock(return_value=True)
        cmd.loiter()
        cmd.set_mode.assert_called_once_with('LOITER')


class TestSetNavSpeed:
    def test_no_connection_raises(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.set_nav_speed(2.0)

    def test_sends_command_and_stores_speed(self, cmd):
        cmd.set_nav_speed(3.5)
        assert cmd._nav_speed == 3.5
        cmd.conn.master.mav.command_long_send.assert_called_once()


class TestGotoPosition:
    def test_switches_to_guided_if_needed(self, cmd):
        cmd.get_current_mode = MagicMock(return_value='STABILIZE')
        cmd.set_mode = MagicMock(return_value=True)
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.goto_position(1.0, 2.0, 10.0) is True
        cmd.set_mode.assert_called_once_with('GUIDED')

    def test_skips_mode_switch_if_already_guided(self, cmd):
        cmd.get_current_mode = MagicMock(return_value='GUIDED')
        cmd.set_mode = MagicMock()
        cmd.goto_position(1.0, 2.0, 10.0)
        cmd.set_mode.assert_not_called()

    def test_applies_nav_speed_if_set(self, cmd):
        cmd.get_current_mode = MagicMock(return_value='GUIDED')
        cmd._nav_speed = 4.0
        cmd.set_nav_speed = MagicMock()
        cmd.goto_position(1.0, 2.0, 10.0)
        cmd.set_nav_speed.assert_called_once_with(4.0)

    def test_no_connection_raises(self, cmd):
        cmd.get_current_mode = MagicMock(return_value='GUIDED')
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.goto_position(1.0, 2.0, 10.0)


class TestSetVelocity:
    def test_sends_local_ned_target(self, cmd):
        cmd.set_velocity(1.0, 0.0, -0.5, yaw_rate=0.1)
        cmd.conn.master.mav.set_position_target_local_ned_send.assert_called_once()

    def test_no_connection_raises(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.set_velocity(0, 0, 0)


class TestEmergencyStop:
    def test_rtl_success(self, cmd):
        cmd.rtl = MagicMock(return_value=True)
        cmd.get_current_mode = MagicMock(return_value='RTL')
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.emergency_stop() is True

    def test_falls_back_to_land(self, cmd):
        cmd.rtl = MagicMock(return_value=True)
        cmd.land = MagicMock(return_value=True)
        cmd.get_current_mode = MagicMock(side_effect=['STABILIZE', 'LAND'])
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.emergency_stop() is True
        cmd.land.assert_called_once()

    def test_falls_back_to_disarm(self, cmd):
        cmd.rtl = MagicMock(return_value=True)
        cmd.land = MagicMock(return_value=True)
        cmd.get_current_mode = MagicMock(return_value='STABILIZE')
        cmd.disarm = MagicMock(return_value=True)
        with patch('backend.mavlink.commands.time.sleep'):
            assert cmd.emergency_stop() is True
        cmd.disarm.assert_called_once_with(force=True)

    def test_swallows_exception_returns_false(self, cmd):
        cmd.rtl = MagicMock(side_effect=Exception('boom'))
        assert cmd.emergency_stop() is False


class TestKillMotors:
    def test_delegates_to_disarm_force(self, cmd):
        cmd.disarm = MagicMock(return_value=True)
        assert cmd.kill_motors() is True
        cmd.disarm.assert_called_once_with(force=True)


class TestGetCurrentMode:
    def test_returns_telemetry_mode_when_known(self, cmd):
        cmd.telemetry.data['mode'] = 'GUIDED'
        assert cmd.get_current_mode() == 'GUIDED'

    def test_falls_back_to_heartbeat_when_unknown(self, cmd, monkeypatch):
        cmd.telemetry.data['mode'] = 'UNKNOWN'
        hb_msg = MagicMock()
        cmd.conn.recv_match.return_value = hb_msg
        monkeypatch.setattr('backend.mavlink.commands.mavutil.mode_string_v10', lambda m: 'STABILIZE')
        assert cmd.get_current_mode() == 'STABILIZE'

    def test_returns_none_when_no_heartbeat(self, cmd):
        cmd.telemetry = None
        cmd.conn.recv_match.return_value = None
        assert cmd.get_current_mode() is None


class TestRebootAutopilot:
    def test_sends_reboot_and_disconnects(self, cmd):
        cmd.reboot_autopilot()
        cmd.conn.master.mav.command_long_send.assert_called_once()
        cmd.conn.disconnect.assert_called_once()

    def test_no_connection_raises(self, cmd):
        cmd.conn.master = None
        with pytest.raises(ConnectionError):
            cmd.reboot_autopilot()
