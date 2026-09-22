"""Tests unitarios adicionales para backend/mavlink/connection.py.

Complementa la cobertura ya existente en test_motores.py::TestConnectionHealth
con el resto de los métodos: heartbeat health, msg_age, is_socket_alive,
mark_dead, probes, get_connection_health, send_command, recv_match,
recv_match_protected, wait_ack, pause_read.
"""
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from backend.mavlink.connection import MAVLinkConnection


@pytest.fixture
def conn():
    with patch('backend.mavlink.connection.mavutil.mavlink_connection') as mock_mc:
        mock_master = MagicMock()
        mock_master.target_system = 1
        mock_master.target_component = 1
        mock_master.mav = MagicMock()
        mock_master.socket = None  # evita ramas de socket real por defecto
        mock_mc.return_value = mock_master
        c = MAVLinkConnection('tcp:127.0.0.1:5760', 115200)
        c.connected = True
        c.master = mock_master
        c._auto_reconnect_stop = threading.Event()
        yield c
        c.stop_auto_reconnect()


def ack(command, result=0):
    m = MagicMock()
    m.command = command
    m.result = result
    return m


class TestIsConnected:
    def test_true_when_connected_and_master_set(self, conn):
        assert conn.is_connected() is True

    def test_false_when_master_none(self, conn):
        conn.master = None
        assert conn.is_connected() is False

    def test_false_when_not_connected(self, conn):
        conn.connected = False
        assert conn.is_connected() is False


class TestHeartbeatHealth:
    def test_unhealthy_before_first_heartbeat(self, conn):
        # connect() ya seteó last_heartbeat real al construir el fixture —
        # se resetea para probar genuinamente el estado "nunca recibido".
        conn.last_heartbeat = 0.0
        assert conn.is_heartbeat_healthy() is False

    def test_healthy_right_after_update(self, conn):
        conn.update_heartbeat()
        assert conn.is_heartbeat_healthy() is True

    def test_unhealthy_after_timeout(self, conn):
        conn.update_heartbeat()
        conn.HEARTBEAT_TIMEOUT = 0.01
        time.sleep(0.02)
        assert conn.is_heartbeat_healthy() is False

    def test_heartbeat_age_infinite_when_never_received(self, conn):
        conn.last_heartbeat = 0.0
        assert conn.heartbeat_age() == float('inf')

    def test_heartbeat_age_small_after_update(self, conn):
        conn.update_heartbeat()
        assert conn.heartbeat_age() < 1.0


class TestMsgAge:
    def test_infinite_when_never_received(self, conn):
        conn.last_msg_time = 0.0
        assert conn.msg_age() == float('inf')

    def test_small_after_update(self, conn):
        conn.update_msg_time()
        assert conn.msg_age() < 1.0

    def test_resets_probe_fail_count(self, conn):
        conn._probe_fail_count = 3
        conn.update_msg_time()
        assert conn._probe_fail_count == 0


class TestIsSocketAlive:
    def test_false_without_master(self, conn):
        conn.master = None
        assert conn.is_socket_alive() is False

    def test_true_when_no_socket_but_recent_message(self, conn):
        conn.master.socket = None
        conn.update_msg_time()
        assert conn.is_socket_alive() is True

    def test_false_when_no_socket_and_stale(self, conn):
        conn.master.socket = None
        conn.last_msg_time = time.time() - 20
        assert conn.is_socket_alive() is False

    def test_true_when_select_reports_not_readable(self, conn):
        fake_sock = MagicMock()
        conn.master.socket = fake_sock
        with patch('backend.mavlink.connection.select.select', return_value=([], [], [])):
            assert conn.is_socket_alive() is True

    def test_readable_with_data_is_alive(self, conn):
        fake_sock = MagicMock()
        fake_sock.recv.return_value = b'x'
        conn.master.socket = fake_sock
        with patch('backend.mavlink.connection.select.select', return_value=([fake_sock], [], [])):
            assert conn.is_socket_alive() is True

    def test_readable_with_no_data_falls_back_to_msg_age(self, conn):
        fake_sock = MagicMock()
        fake_sock.recv.return_value = b''
        conn.master.socket = fake_sock
        conn.update_msg_time()
        with patch('backend.mavlink.connection.select.select', return_value=([fake_sock], [], [])):
            assert conn.is_socket_alive() is True

    def test_exception_falls_back_to_msg_age(self, conn):
        fake_sock = MagicMock()
        conn.master.socket = fake_sock
        with patch('backend.mavlink.connection.select.select', side_effect=OSError('bad fd')):
            conn.last_msg_time = time.time() - 20
            assert conn.is_socket_alive() is False


class TestMarkDead:
    def test_sets_needs_reconnect(self, conn):
        conn.mark_dead("test reason")
        assert conn._needs_reconnect.is_set()

    def test_suppressed_while_reconnecting(self, conn):
        conn._reconnecting.set()
        conn.mark_dead("test reason")
        assert not conn._needs_reconnect.is_set()

    def test_suppressed_when_already_needs_reconnect(self, conn):
        conn._needs_reconnect.set()
        conn.mark_dead("another reason")  # no debe lanzar ni cambiar nada


class TestSuppressProbe:
    def test_sets_flag_true(self, conn):
        conn.suppress_probe(True)
        assert conn._suppress_probe is True

    def test_sets_flag_false(self, conn):
        conn.suppress_probe(False)
        assert conn._suppress_probe is False


class TestUpdateAckTime:
    def test_resets_probe_fail_count(self, conn):
        conn._probe_fail_count = 2
        conn.update_ack_time()
        assert conn._probe_fail_count == 0


class TestSendProbe:
    def test_false_when_not_connected(self, conn):
        conn.connected = False
        assert conn._send_probe() is False

    def test_true_on_accepted_ack(self, conn):
        from pymavlink import mavutil
        cmd_id = mavutil.mavlink.MAV_CMD_REQUEST_PROTOCOL_VERSION
        conn._pending_acks[cmd_id] = ack(cmd_id, 0)
        assert conn._send_probe() is True

    def test_false_on_timeout(self, conn):
        with patch('backend.mavlink.connection.time.time', side_effect=[0] + [100] * 20), \
             patch('backend.mavlink.connection.time.sleep'):
            assert conn._send_probe() is False

    def test_false_on_send_exception(self, conn):
        conn.master.mav.command_long_send.side_effect = Exception('boom')
        assert conn._send_probe() is False


class TestRunProbeCheck:
    def test_skipped_when_not_connected(self, conn):
        conn.connected = False
        conn.run_probe_check()  # no debe lanzar

    def test_skipped_when_recent_traffic(self, conn):
        conn.update_msg_time()
        conn._probe_fail_count = 2
        conn.run_probe_check()
        assert conn._probe_fail_count == 0

    def test_increments_fail_count_on_probe_failure(self, conn):
        conn.last_msg_time = time.time() - 20
        conn._send_probe = MagicMock(return_value=False)
        conn.run_probe_check()
        assert conn._probe_fail_count == 1

    def test_triggers_reconnect_after_max_failures(self, conn):
        conn.last_msg_time = time.time() - 20
        conn._send_probe = MagicMock(return_value=False)
        conn._probe_fail_count = conn.PROBE_MAX_FAILURES - 1
        conn.run_probe_check()
        assert conn._needs_reconnect.is_set()

    def test_resets_fail_count_on_success(self, conn):
        conn.last_msg_time = time.time() - 20
        conn._send_probe = MagicMock(return_value=True)
        conn._probe_fail_count = 3
        conn.run_probe_check()
        assert conn._probe_fail_count == 0


class TestGetConnectionHealth:
    def test_shape(self, conn):
        health = conn.get_connection_health()
        assert set(health.keys()) == {
            "connected", "sconnected", "healthy", "heartbeat_age_s",
            "last_msg_age_s", "socket_alive", "reconnecting",
            "needs_reconnect", "probe_failures", "device",
        }

    def test_none_ages_when_never_received(self, conn):
        conn.last_heartbeat = 0.0
        conn.last_msg_time = 0.0
        health = conn.get_connection_health()
        assert health["heartbeat_age_s"] is None
        assert health["last_msg_age_s"] is None

    def test_healthy_true_when_all_good(self, conn):
        conn.update_heartbeat()
        conn.update_msg_time()
        health = conn.get_connection_health()
        assert health["healthy"] is True

    def test_unhealthy_when_needs_reconnect(self, conn):
        conn.update_heartbeat()
        conn.update_msg_time()
        conn._needs_reconnect.set()
        health = conn.get_connection_health()
        assert health["healthy"] is False


class TestSendCommand:
    def test_raises_when_not_connected(self, conn):
        conn.connected = False
        with pytest.raises(ConnectionError):
            conn.send_command(lambda: None)

    def test_calls_function_with_args(self, conn):
        fn = MagicMock()
        conn.send_command(fn, 1, 2, key='val')
        fn.assert_called_once_with(1, 2, key='val')


class TestRecvMatch:
    def test_returns_none_when_not_connected(self, conn):
        conn.connected = False
        assert conn.recv_match() is None

    def test_delegates_to_master(self, conn):
        conn.master.recv_match.return_value = 'MSG'
        assert conn.recv_match(msg_type='HEARTBEAT', blocking=False, timeout=1) == 'MSG'

    def test_serial_error_returns_none(self, conn):
        conn.master.recv_match.side_effect = OSError('gone')
        assert conn.recv_match() is None


class TestRecvMatchProtected:
    def test_returns_pending_message_immediately(self, conn):
        msg = MagicMock()
        conn._pending_msgs['HEARTBEAT'] = msg
        assert conn.recv_match_protected('HEARTBEAT') is msg

    def test_falls_back_to_recv_match(self, conn):
        conn.master.recv_match.return_value = 'DIRECT'
        assert conn.recv_match_protected('HEARTBEAT', timeout=1) == 'DIRECT'

    def test_returns_none_on_timeout(self, conn):
        conn.master.recv_match.return_value = None
        with patch('backend.mavlink.connection.time.time', side_effect=[0, 0, 100]), \
             patch('backend.mavlink.connection.time.sleep'):
            assert conn.recv_match_protected('HEARTBEAT', timeout=1) is None


class TestWaitAck:
    def test_true_on_accepted(self, conn):
        conn._pending_acks[400] = ack(400, 0)
        assert conn.wait_ack(command_id=400) is True

    def test_false_on_rejected(self, conn):
        conn._pending_acks[400] = ack(400, 2)
        assert conn.wait_ack(command_id=400) is False

    def test_extends_on_in_progress_then_accepts(self, conn):
        conn._pending_acks[400] = ack(400, 5)
        call_state = {'n': 0}

        def fake_sleep(s):
            call_state['n'] += 1
            if call_state['n'] == 1:
                conn._pending_acks[400] = ack(400, 0)

        with patch('backend.mavlink.connection.time.sleep', side_effect=fake_sleep):
            assert conn.wait_ack(command_id=400, timeout=1) is True

    def test_timeout_returns_false(self, conn):
        with patch('backend.mavlink.connection.time.sleep'):
            assert conn.wait_ack(command_id=999, timeout=0.01) is False

    def test_any_command_accepted_when_no_id_given(self, conn):
        conn._pending_acks[123] = ack(123, 0)
        assert conn.wait_ack(command_id=None) is True


class TestPauseRead:
    def test_sets_and_clears_pause_flag(self, conn):
        with patch('backend.mavlink.connection.time.sleep'):
            with conn.pause_read():
                assert conn._pause_read.is_set()
        assert not conn._pause_read.is_set()


class TestDisconnectReconnect:
    def test_disconnect_closes_master(self, conn):
        conn.disconnect()
        assert conn.connected is False
        assert conn.master is None

    def test_close_socket_keeps_connected_flag(self, conn):
        conn.connected = True
        conn._close_socket()
        assert conn.connected is True
        assert conn.master is None


class TestStartStopAutoReconnect:
    def test_start_creates_thread(self, conn):
        conn.start_auto_reconnect(initial_interval=100, max_interval=100)
        try:
            assert conn._auto_reconnect_thread.is_alive()
        finally:
            conn.stop_auto_reconnect()

    def test_start_is_idempotent(self, conn):
        conn.start_auto_reconnect(initial_interval=100)
        first = conn._auto_reconnect_thread
        conn.start_auto_reconnect(initial_interval=100)
        assert conn._auto_reconnect_thread is first
        conn.stop_auto_reconnect()

    def test_stop_joins_thread(self, conn):
        conn.start_auto_reconnect(initial_interval=100)
        conn.stop_auto_reconnect()
        assert conn._auto_reconnect_thread is None
