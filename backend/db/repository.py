from backend.db.database import SessionLocal
from backend.db.models import Telemetry
import logging

logger = logging.getLogger(__name__)

def save_telemetry(data):
    try:
        with SessionLocal() as db:
            t = Telemetry(**data)
            db.add(t)
            db.commit()
            logger.info("Telemetry saved to database")
    except Exception as e:
        logger.error(f"Error saving telemetry: {e}")
        raise
