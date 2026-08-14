import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

ADMIN_USER = "test_admin"
ADMIN_PASS = "TestPass1234"


@pytest.fixture(autouse=True)
def _isolated_users(tmp_path, monkeypatch):
    """Aísla el almacén de usuarios en un archivo temporal por test."""
    from backend.api import auth
    monkeypatch.setattr(auth.store, "path", tmp_path / "users.json")
    auth.rate_limiter._records.clear()
    auth.sessions._sessions.clear()
    auth.ensure_admin_user(ADMIN_USER, ADMIN_PASS)


def test_drones_endpoint():
    r = client.get("/drones")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any('name' in d for d in data)


def test_api_status_requires_auth():
    r = client.get("/api/status")
    assert r.status_code == 401


def test_api_status_with_auth():
    r = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Sin MAVLink conectado → 500/503 (pero NO 401/403, el token sí es válido)
    r = client.get("/api/status", headers=headers)
    assert r.status_code in (200, 500, 503)


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
