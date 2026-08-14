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
    yield


def _login(username: str = ADMIN_USER, password: str = ADMIN_PASS) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Endpoints públicos ─────────────────────────────────────────────────────────

def test_drones_endpoint():
    r = client.get("/drones")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any('name' in d for d in data)


# ── Autenticación requerida ───────────────────────────────────────────────────

def test_protected_endpoint_rejects_without_token():
    r = client.get("/api/status")
    assert r.status_code == 401


def test_protected_endpoint_rejects_with_invalid_token():
    r = client.get("/api/status", headers=_auth_headers("token-inexistente"))
    assert r.status_code == 401


def test_protected_endpoint_accepts_valid_token():
    token = _login()
    # Sin MAVLink conectado el endpoint devuelve 500/503, pero NO 401 → token aceptado
    r = client.get("/api/status", headers=_auth_headers(token))
    assert r.status_code in (200, 500, 503)


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_success():
    r = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["user"]["username"] == ADMIN_USER
    assert body["expires_at"] > 0


def test_login_wrong_password_is_generic():
    r = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": "incorrecta"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Credenciales inválidas"


def test_login_unknown_user_is_generic():
    r = client.post("/api/auth/login", json={"username": "no_existe", "password": "cualquiera"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Credenciales inválidas"


# ── Rate limiting (caja negra) ────────────────────────────────────────────────

def test_rate_limit_locks_user_after_failures():
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": "mala"})
        assert r.status_code == 401

    r = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 429
    assert "Intenta de nuevo" in r.json()["detail"]


# ── Caja blanca: hash de contraseñas ──────────────────────────────────────────

def test_password_not_stored_in_plaintext():
    from backend.api import auth
    user = auth.store.get_user(ADMIN_USER)
    assert user["password_hash"] != ADMIN_PASS
    assert user["salt"]
    assert not auth.verify_password("wrong-pass", user["salt"], user["password_hash"], user["iterations"])
    assert auth.verify_password(ADMIN_PASS, user["salt"], user["password_hash"], user["iterations"])


# ── Sesión: /me y /logout ─────────────────────────────────────────────────────

def test_me_returns_current_user():
    token = _login()
    r = client.get("/api/auth/me", headers=_auth_headers(token))
    assert r.status_code == 200
    assert r.json()["user"]["username"] == ADMIN_USER


def test_logout_revokes_token():
    token = _login()
    r = client.post("/api/auth/logout", headers=_auth_headers(token))
    assert r.status_code == 200
    assert r.json()["success"] is True
    r2 = client.get("/api/status", headers=_auth_headers(token))
    assert r2.status_code == 401


def test_token_can_expire():
    from backend.api import auth
    token = _login()
    auth.sessions._sessions[token]["expires_at"] = 0  # forzar expiración
    r = client.get("/api/auth/me", headers=_auth_headers(token))
    assert r.status_code == 401


# ── WebSocket ─────────────────────────────────────────────────────────────────

def test_ws_rejects_without_token():
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/telemetry"):
            pass
    assert exc_info.value.code == 1008


def test_ws_rejects_with_invalid_token():
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/telemetry?token=token-malo"):
            pass
    assert exc_info.value.code == 1008


def test_ws_accepts_valid_token():
    token = _login()
    with client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
        first = ws.receive_json()
        assert first["type"] in ("connection_alert", "telemetry")
