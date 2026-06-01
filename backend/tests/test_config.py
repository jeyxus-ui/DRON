# tests/test_config.py
import importlib
import sys
import types
import os
import glob

import backend.config as config


def test_env_sim(monkeypatch):
    """If MAVLINK_DEVICE is explicitly set to SIM, return SIM."""
    monkeypatch.setattr(config, 'MAVLINK_DEVICE', 'SIM')
    assert config.detect_mavlink_device() == 'SIM'


def test_env_invalid_path_falls_back(monkeypatch):
    """If MAVLINK_DEVICE points to a non-existing path, fall back to detection (SIM)."""
    monkeypatch.setattr(config, 'MAVLINK_DEVICE', '/dev/doesnotexist')
    monkeypatch.setattr(os.path, 'exists', lambda p: False)
    # Ensure glob yields nothing
    monkeypatch.setattr(glob, 'glob', lambda pattern: [])
    assert config.detect_mavlink_device() == 'SIM'


def test_candidate_probe_with_pyserial(monkeypatch):
    """When a candidate exists and pyserial is available, it should be returned."""
    monkeypatch.setattr(config, 'MAVLINK_DEVICE', '')

    # Make /dev/ttyACM0 exist
    monkeypatch.setattr(os.path, 'exists', lambda p: p == '/dev/ttyACM0')

    # Provide a fake serial module with Serial that can open/close
    class FakeSerial:
        def __init__(self, path, baud, timeout=0.5):
            if path != '/dev/ttyACM0':
                raise OSError('not available')
        def close(self):
            pass

    fake_serial_mod = types.SimpleNamespace(Serial=FakeSerial)
    monkeypatch.setitem(sys.modules, 'serial', fake_serial_mod)

    assert config.detect_mavlink_device() == '/dev/ttyACM0'


def test_candidate_probe_without_pyserial_uses_os_open(monkeypatch):
    """If pyserial is not available, fallback to os.open probe should work."""
    monkeypatch.setattr(config, 'MAVLINK_DEVICE', '')

    # No serial module
    monkeypatch.setitem(sys.modules, 'serial', None)
    if 'serial' in sys.modules:
        sys.modules.pop('serial', None)

    # Make /dev/ttyUSB0 exist
    monkeypatch.setattr(os.path, 'exists', lambda p: p == '/dev/ttyUSB0')

    # Make os.open succeed for the test path and os.close be a no-op
    monkeypatch.setattr(os, 'open', lambda path, flags: 3)
    monkeypatch.setattr(os, 'close', lambda fd: None)

    assert config.detect_mavlink_device() == '/dev/ttyUSB0'


def test_by_id_probe(monkeypatch):
    """If /dev/serial/by-id contains an accessible device, it should be returned."""
    monkeypatch.setattr(config, 'MAVLINK_DEVICE', '')

    # No candidate files
    monkeypatch.setattr(os.path, 'exists', lambda p: False)

    # Simulate a by-id entry
    monkeypatch.setattr(glob, 'glob', lambda pattern: ['/dev/serial/by-id/usb-FAKE-1'])

    # os.open works on that path
    monkeypatch.setattr(os, 'open', lambda path, flags: 4)
    monkeypatch.setattr(os, 'close', lambda fd: None)

    assert config.detect_mavlink_device() == '/dev/serial/by-id/usb-FAKE-1'