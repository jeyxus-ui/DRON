"""
Autenticación de la API del dron.

Diseñado para pasar pruebas de seguridad tipo "caja negra" y "caja blanca":

Caja negra (desde fuera, sin acceso al código):
- Rate limiting por usuario: bloqueo temporal tras N intentos fallidos de login.
- Mensaje de error genérico (no revela si el usuario existe o no).
- Tokens de sesión aleatorios e impredecibles (secrets.token_urlsafe).
- El token viaja en el header Authorization y expira automáticamente.

Caja blanca (revisión de código):
- Contraseñas con hash PBKDF2-HMAC-SHA256 (stdlib hashlib), salt aleatorio.
- Comparación de hash con hmac.compare_digest (resistente a timing attacks).
- Expiración de token verificada en cada request.
- Validación de longitud mínima de contraseña al crear usuarios.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.config import (
    AUTH_LOCKOUT_SECONDS,
    AUTH_MAX_FAILED_LOGINS,
    AUTH_MIN_PASSWORD_LENGTH,
    AUTH_TOKEN_EXPIRY,
    USERS_FILE,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Constantes de seguridad ───────────────────────────────────────────────────
PBKDF2_ITERATIONS = 600_000
PBKDF2_HASH_ALGO = "sha256"
DEFAULT_ROLE = "operator"


# ── Almacenamiento de usuarios ────────────────────────────────────────────────
class AuthStore:
    """Persistencia de usuarios en JSON. Thread-safe."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error("Error leyendo usuarios: %s", e)
            return {}

    def _save(self, data: Dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def get_user(self, username: str) -> Optional[dict]:
        with self._lock:
            return self._load().get(username)

    def create_user(
        self,
        username: str,
        password: str,
        role: str = DEFAULT_ROLE,
        overwrite: bool = False,
    ) -> dict:
        if len(password) < AUTH_MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"La contraseña debe tener al menos {AUTH_MIN_PASSWORD_LENGTH} caracteres"
            )
        with self._lock:
            users = self._load()
            if username in users and not overwrite:
                raise ValueError(f"El usuario '{username}' ya existe")
            hash_info = hash_password(password)
            users[username] = {
                "password_hash": hash_info["hash"],
                "salt": hash_info["salt"],
                "iterations": hash_info["iterations"],
                "role": role,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save(users)
            return users[username]

    def set_password(self, username: str, password: str) -> bool:
        if len(password) < AUTH_MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"La contraseña debe tener al menos {AUTH_MIN_PASSWORD_LENGTH} caracteres"
            )
        with self._lock:
            users = self._load()
            if username not in users:
                return False
            hash_info = hash_password(password)
            users[username]["password_hash"] = hash_info["hash"]
            users[username]["salt"] = hash_info["salt"]
            users[username]["iterations"] = hash_info["iterations"]
            users[username]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(users)
            return True

    def list_users(self) -> list:
        with self._lock:
            return sorted(self._load().keys())


# ── Hash de contraseñas ───────────────────────────────────────────────────────
def hash_password(password: str, salt: Optional[str] = None) -> dict:
    """Genera hash PBKDF2-HMAC-SHA256 con salt aleatorio."""
    salt_bytes = (
        bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    )
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_HASH_ALGO,
        password.encode("utf-8"),
        salt_bytes,
        PBKDF2_ITERATIONS,
    )
    return {
        "hash": digest.hex(),
        "salt": salt_bytes.hex(),
        "iterations": PBKDF2_ITERATIONS,
    }


def verify_password(password: str, salt: str, expected_hash: str, iterations: int) -> bool:
    """Verifica la contraseña usando comparación constante de tiempo."""
    if not salt or not expected_hash:
        return False
    try:
        computed = hashlib.pbkdf2_hmac(
            PBKDF2_HASH_ALGO,
            password.encode("utf-8"),
            bytes.fromhex(salt),
            iterations,
        )
        return hmac.compare_digest(computed.hex(), expected_hash)
    except Exception:
        return False


# ── Sesiones (tokens) ─────────────────────────────────────────────────────────
class SessionStore:
    """Tokens de sesión persistidos en disco. Thread-safe.

    Los tokens sobreviven reinicios del backend: el mismo token que la app
    guardó sigue siendo válido hasta su expiración natural.
    """

    def __init__(self, expiry_seconds: int, persist_file: Optional[str] = None):
        self.expiry = expiry_seconds
        self._sessions: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._file = persist_file
        if self._file:
            self._load()

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            path = Path(self._file)
            if not path.exists():
                return
            with path.open() as f:
                data = json.load(f)
            now = time.time()
            self._sessions = {
                t: s for t, s in data.items() if s.get("expires_at", 0) > now
            }
            logger.info("Sesiones cargadas desde disco: %d activas", len(self._sessions))
        except Exception as e:
            logger.warning("No se pudo cargar sesiones: %s", e)

    def _save(self) -> None:
        if not self._file:
            return
        try:
            path = Path(self._file)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(path) + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._sessions, f)
            os.replace(tmp, str(path))
        except Exception as e:
            logger.warning("No se pudo guardar sesiones: %s", e)

    # ── Operaciones ───────────────────────────────────────────────────────────

    def create(self, username: str) -> tuple:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self.expiry
        with self._lock:
            self._sessions[token] = {
                "username": username,
                "expires_at": expires_at,
            }
            self._save()
        return token, expires_at

    def get(self, token: str) -> Optional[dict]:
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if time.time() > session["expires_at"]:
                del self._sessions[token]
                self._save()
                return None
            return dict(session)

    def revoke(self, token: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(token, None) is not None
            if removed:
                self._save()
            return removed

    def revoke_all_for_user(self, username: str) -> int:
        with self._lock:
            to_del = [
                t for t, s in self._sessions.items() if s["username"] == username
            ]
            for t in to_del:
                del self._sessions[t]
            if to_del:
                self._save()
            return len(to_del)


# ── Rate limiting de login ────────────────────────────────────────────────────
class LoginRateLimiter:
    """Bloquea temporalmente un usuario tras demasiados intentos fallidos."""

    def __init__(self, max_failures: int, lockout_seconds: int):
        self.max_failures = max_failures
        self.lockout = lockout_seconds
        self._records: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def _cleanup(self, now: float) -> None:
        for user in list(self._records.keys()):
            rec = self._records[user]
            locked = rec.get("locked_until", 0)
            if locked and locked < now:
                del self._records[user]

    def check_locked(self, username: str) -> Optional[float]:
        """Devuelve segundos restantes de bloqueo, o None si no está bloqueado."""
        now = time.time()
        with self._lock:
            self._cleanup(now)
            rec = self._records.get(username)
            if rec and rec.get("locked_until", 0) > now:
                return int(rec["locked_until"] - now) + 1
        return None

    def record_failure(self, username: str) -> Optional[float]:
        """Registra un intento fallido. Devuelve bloqueo en segundos si se activó."""
        now = time.time()
        with self._lock:
            self._cleanup(now)
            rec = self._records.setdefault(
                username, {"failures": 0, "locked_until": 0}
            )
            rec["failures"] = rec.get("failures", 0) + 1
            if rec["failures"] >= self.max_failures:
                rec["locked_until"] = now + self.lockout
                rec["failures"] = 0
                logger.warning(
                    "🔒 Login bloqueado temporalmente para '%s' (%ds) por %d intentos fallidos",
                    username, self.lockout, self.max_failures,
                )
                return self.lockout
        return None

    def record_success(self, username: str) -> None:
        with self._lock:
            self._records.pop(username, None)


# ── Instancias globales ───────────────────────────────────────────────────────
store = AuthStore(USERS_FILE)
_SESSIONS_FILE = os.path.join(os.path.dirname(USERS_FILE), "sessions.json")
sessions = SessionStore(AUTH_TOKEN_EXPIRY, persist_file=_SESSIONS_FILE)
rate_limiter = LoginRateLimiter(AUTH_MAX_FAILED_LOGINS, AUTH_LOCKOUT_SECONDS)


def get_user_from_token(token: Optional[str]) -> Optional[dict]:
    """Devuelve el usuario asociado a un token válido, o None."""
    session = sessions.get(token)
    if session is None:
        return None
    user = store.get_user(session["username"])
    if user is None:
        return None
    return {
        "username": session["username"],
        "role": user.get("role", DEFAULT_ROLE),
    }


# ── Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    token: str
    user: dict
    expires_at: float


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    username = request.username.strip()
    password = request.password

    locked_for = rate_limiter.check_locked(username)
    if locked_for:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {locked_for}s",
        )

    user = store.get_user(username)
    valid = (
        user is not None
        and verify_password(
            password,
            user.get("salt", ""),
            user.get("password_hash", ""),
            int(user.get("iterations", PBKDF2_ITERATIONS)),
        )
    )

    if not valid:
        rate_limiter.record_failure(username)
        # Mensaje genérico: no revela si el usuario existe
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas",
        )

    rate_limiter.record_success(username)
    token, expires_at = sessions.create(username)
    logger.info("✅ Login exitoso: '%s'", username)
    return TokenResponse(
        token=token,
        user={"username": username, "role": user.get("role", DEFAULT_ROLE)},
        expires_at=expires_at,
    )


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    token = _extract_bearer(authorization)
    if token and sessions.revoke(token):
        logger.info("Sesión cerrada")
        return {"success": True, "message": "Sesión cerrada"}
    return {"success": False, "message": "Token inválido o ya expirado"}


@router.get("/me")
def me(authorization: Optional[str] = Header(None)):
    user = require_auth(authorization)
    return {"success": True, "user": user}


# ── Dependencia FastAPI ───────────────────────────────────────────────────────
def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency que exige un bearer token válido. Códigos 401/403 estándar."""
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Autenticación requerida",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user_from_token(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def websocket_token_user(query_params: Dict[str, str]) -> Optional[dict]:
    """Valida el token para conexiones WebSocket (enviado como query param)."""
    token = query_params.get("token")
    if not token:
        return None
    return get_user_from_token(token)


def ensure_admin_user(username: str, password: str) -> dict:
    """Crea o actualiza un usuario administrador (usado en seed)."""
    if store.get_user(username) is None:
        return store.create_user(username, password, role="admin")
    return store.set_password(username, password) and store.get_user(username)
