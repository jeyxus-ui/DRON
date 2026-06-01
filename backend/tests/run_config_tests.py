# run_config_tests.py
"""Simple test runner for detect_mavlink_device to avoid pytest dependency during quick CI.

This script runs a set of deterministic checks and exits with non-zero status on failure.
"""
import sys
import types
import glob
import os

import backend.config as config


def _with_temp_attr(obj, name, value):
    original = getattr(obj, name, None)
    has = hasattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        if has:
            setattr(obj, name, original)
        else:
            delattr(obj, name)


def _run_test(name, fn):
    try:
        fn()
        print(f"PASS: {name}")
    except AssertionError as e:
        print(f"FAIL: {name} - {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"ERROR: {name} - {e}")
        raise SystemExit(2)


def test_env_sim():
    config.MAVLINK_DEVICE = 'SIM'
    assert config.detect_mavlink_device() == 'SIM'


def test_env_invalid_path_falls_back():
    config.MAVLINK_DEVICE = '/dev/doesnotexist'
    old_exists = os.path.exists
    os.path.exists = lambda p: False
    old_glob = glob.glob
    glob.glob = lambda pattern: []
    try:
        assert config.detect_mavlink_device() == 'SIM'
    finally:
        os.path.exists = old_exists
        glob.glob = old_glob


def test_candidate_probe_with_pyserial():
    config.MAVLINK_DEVICE = ''
    old_exists = os.path.exists
    os.path.exists = lambda p: p == '/dev/ttyACM0'

    class FakeSerial:
        def __init__(self, path, baud, timeout=0.5):
            if path != '/dev/ttyACM0':
                raise OSError('not available')
        def close(self):
            pass

    old_serial = sys.modules.get('serial')
    sys.modules['serial'] = types.SimpleNamespace(Serial=FakeSerial)
    try:
        assert config.detect_mavlink_device() == '/dev/ttyACM0'
    finally:
        os.path.exists = old_exists
        if old_serial is None:
            sys.modules.pop('serial', None)
        else:
            sys.modules['serial'] = old_serial


def test_candidate_probe_without_pyserial_uses_os_open():
    config.MAVLINK_DEVICE = ''
    old_exists = os.path.exists
    os.path.exists = lambda p: p == '/dev/ttyUSB0'

    old_serial = sys.modules.get('serial')
    if 'serial' in sys.modules:
        sys.modules.pop('serial', None)

    old_open = os.open
    old_close = os.close
    os.open = lambda path, flags: 3
    os.close = lambda fd: None
    try:
        assert config.detect_mavlink_device() == '/dev/ttyUSB0'
    finally:
        os.path.exists = old_exists
        if old_serial is not None:
            sys.modules['serial'] = old_serial
        os.open = old_open
        os.close = old_close


def test_by_id_probe():
    config.MAVLINK_DEVICE = ''
    old_exists = os.path.exists
    # Make only the by-id path appear to exist
    os.path.exists = lambda p: p == '/dev/serial/by-id/usb-FAKE-1'
    old_glob = glob.glob
    glob.glob = lambda pattern: ['/dev/serial/by-id/usb-FAKE-1']

    old_open = os.open
    old_close = os.close
    os.open = lambda path, flags: 4
    os.close = lambda fd: None
    try:
        detected = config.detect_mavlink_device()
        if detected != '/dev/serial/by-id/usb-FAKE-1':
            print(f"Detected by-id returned: {detected!r}")
        assert detected == '/dev/serial/by-id/usb-FAKE-1'
    finally:
        os.path.exists = old_exists
        glob.glob = old_glob
        os.open = old_open
        os.close = old_close


if __name__ == '__main__':
    tests = [
        test_env_sim,
        test_env_invalid_path_falls_back,
        test_candidate_probe_with_pyserial,
        test_candidate_probe_without_pyserial_uses_os_open,
        test_by_id_probe,
    ]

    for t in tests:
        _run_test(t.__name__, t)

    print('\nAll tests passed!')
    sys.exit(0)
