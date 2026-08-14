# backend/config.py
import os
import logging
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / '.env')

logger = logging.getLogger(__name__)

# MAVLink
# - 'SIM' → simulador interno básico (sin MAVLink real)
# - 'tcp:<ip>:<port>' → ArduPilot SITL en WSL/remoto
# - 'udpin:0.0.0.0:14550' → escucha UDP (MAVProxy en WSL)
# - 'udpout:127.0.0.1:14551' → envía UDP a backend
# - '/dev/ttyACM0' → Pixhawk físico
MAVLINK_DEVICE = os.getenv('MAVLINK_DEVICE', 'udpin:0.0.0.0:14550')

# CORREGIDO: baudrates correctos según tipo de conexión
# USB directo Pixhawk → 115200
# Radio telemetría (3DR, SiK) → 57600
MAVLINK_BAUD = int(os.getenv('MAVLINK_BAUD', 115200))  # ← era 57600

# API
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 8000))

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Autenticación
AUTH_TOKEN_EXPIRY = int(os.getenv('AUTH_TOKEN_EXPIRY', 86400))          # 24h
AUTH_MAX_FAILED_LOGINS = int(os.getenv('AUTH_MAX_FAILED_LOGINS', 5))    # intentos antes de bloquear
AUTH_LOCKOUT_SECONDS = int(os.getenv('AUTH_LOCKOUT_SECONDS', 300))      # bloqueo 5 min
AUTH_MIN_PASSWORD_LENGTH = int(os.getenv('AUTH_MIN_PASSWORD_LENGTH', 8))
USERS_FILE = os.getenv('USERS_FILE', os.path.join(os.path.dirname(__file__), 'data', 'users.json'))

# Database
DEFAULT_DB = 'postgresql://dronix_user:DronixSecure2024!@postgres:5432/drones'
DB_URL = os.getenv('DB_URL', DEFAULT_DB)

if not DB_URL.startswith('postgres'):
    logger.warning("DB_URL no apunta a PostgreSQL.")


def detect_mavlink_device() -> str:
    """
    Auto-detecta el dispositivo MAVLink.
    
    Prioridad:
    1. Variable de entorno MAVLINK_DEVICE
    2. Detección automática de puertos comunes
    3. Fallback a SIM
    """

    # 1. Respetar variable de entorno explícita
    if MAVLINK_DEVICE:
        if MAVLINK_DEVICE.upper() == 'SIM':
            logger.info("Modo simulador activado por variable de entorno.")
            return 'SIM'

        # TCP/UDP connections (e.g. 'tcp:192.168.1.5:5760') — no son archivos
        if ':' in MAVLINK_DEVICE and not MAVLINK_DEVICE.startswith('/'):
            logger.info(f"Usando conexión remota MAVLink: {MAVLINK_DEVICE}")
            return MAVLINK_DEVICE

        if not os.path.exists(MAVLINK_DEVICE):
            logger.warning(
                f"MAVLINK_DEVICE='{MAVLINK_DEVICE}' no existe en el sistema. "
                f"Fallback a SIM. ¿Está conectado el Pixhawk?"
            )
            return 'SIM'

        logger.info(f"Usando dispositivo MAVLink configurado: {MAVLINK_DEVICE} @ {MAVLINK_BAUD} baud")
        return MAVLINK_DEVICE

    # 2. Auto-detección
    candidates = [
        '/dev/ttyACM0',  # Pixhawk USB directo
        '/dev/ttyACM1',
        '/dev/ttyUSB0',  # Radio telemetría (SiK, 3DR)
        '/dev/ttyUSB1',
    ]

    # Agregar entradas de /dev/serial/by-id (nombres persistentes)
    try:
        import glob
        by_id = glob.glob('/dev/serial/by-id/*')
        candidates.extend(by_id)
    except Exception:
        pass

    for path in candidates:
        if _probe_device(path):
            logger.info(f"Dispositivo MAVLink detectado automáticamente: {path}")
            return path

    logger.warning(
        "No se encontró ningún dispositivo MAVLink accesible. "
        "Usando modo SIM. Verifica conexión USB y permisos."
    )
    return 'SIM'


def _probe_device(path: str) -> bool:
    """Verifica si un puerto serial existe y puede abrirse."""
    if not os.path.exists(path):
        return False
    try:
        import serial
        # CRÍTICO: usar el baudrate real configurado
        s = serial.Serial(path, MAVLINK_BAUD, timeout=0.5)
        s.close()
        logger.debug(f"Probe exitoso: {path}")
        return True
    except ImportError:
        # pyserial no disponible, usar os.open como último recurso
        try:
            fd = os.open(path, os.O_RDWR | getattr(os, 'O_NONBLOCK', 0))
            os.close(fd)
            return True
        except OSError:
            return False
    except Exception as e:
        logger.debug(f"Probe fallido en {path}: {e}")
        return False