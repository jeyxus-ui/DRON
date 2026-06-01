from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_drones_endpoint():
    r = client.get("/drones")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any('name' in d for d in data)


def test_api_status():
    r = client.get("/api/status")
    assert r.status_code == 200
    j = r.json()
    assert j.get('success') is True
    assert 'data' in j


def test_device_endpoint():
    r = client.get("/api/device")
    assert r.status_code == 200
    j = r.json()
    assert j.get('success') is True
    data = j.get('data')
    assert 'device' in data and 'connected' in data and 'simulated' in data


def test_telemetry_persistence_called(monkeypatch):
    # Patch save_telemetry to count calls
    called = {'count': 0}

    def fake_save(data):
        called['count'] += 1

    monkeypatch.setattr('backend.db.repository.save_telemetry', fake_save)

    # Minimal dummy connection usable by DroneTelemetry
    class DummyConn:
        def __init__(self):
            self.master = type('M', (), {'recv_match': lambda *a, **k: None})()
        def is_connected(self):
            return False

    from backend.mavlink.telemetry import DroneTelemetry

    dt = DroneTelemetry(DummyConn(), persist_interval=1.0)

    import time
    time.sleep(1.5)  # allow at least one persist cycle
    dt.stop()

    assert called['count'] >= 1
