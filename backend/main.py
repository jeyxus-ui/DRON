# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from backend.api import rest, websocket, camera_stream
from backend.config import API_HOST, API_PORT, LOG_LEVEL, MAVLINK_BAUD, detect_mavlink_device
from sqlalchemy import text 

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Drone Control API",
    description="API REST para control de dron vía MAVLink",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir rutas
app.include_router(rest.router, prefix="/api", tags=["drone"])
app.include_router(websocket.router)  # WebSocket no lleva prefix
app.include_router(camera_stream.router)  # Ya tiene su propio prefix

# Inicialización en eventos de ciclo de vida
@app.on_event("startup")
def startup_event():
    try:
        device = detect_mavlink_device()
        logger.info(f"Selected MAVLink device: {device}")
        rest.init_mav(device, MAVLINK_BAUD)
        rest.start_monitoring(MAVLINK_BAUD, interval=5)
        try:
            camera_stream.camera.start(width=640, height=480, fps=30)
            logger.info("✅ Cámara RealSense iniciada")
        except Exception as e:
            logger.warning(f"⚠️ Error iniciando cámara (continuando sin ella): {e}")
        if getattr(rest, 'mav', None):
            websocket.start_telemetry_broadcast(rest.mav)
            logger.info("✅ Telemetry WebSocket iniciado")
            def vision_emergency():
                try:
                    rest.mav.set_mode("BRAKE")
                    logger.warning("🛑 Vision auto-avoid: BRAKE mode set")
                except Exception as e:
                    logger.error(f"Vision emergency failed: {e}")
            camera_stream.set_emergency_callback(vision_emergency)
            logger.info("✅ Vision → MAVLink emergency callback registrado")

            rest.init_sensors(rest.mav)
            rest.init_navigation(rest.mav)
            logger.info("✅ Sensores y navegación autónoma iniciados")
        else:
            logger.warning("⚠️ MAV controller no disponible, WebSocket no iniciado")
    except Exception as e:
        logger.error(f"Failed to initialize on startup: {e}")

@app.on_event("shutdown")
def shutdown_event():
    try:
        rest.shutdown_sensors_and_nav()
        try:
            camera_stream.camera.stop()
            logger.info("✅ Cámara detenida")
        except Exception as e:
            logger.error(f"Error deteniendo cámara: {e}")
        if getattr(rest, 'mav', None):
            try:
                rest.mav.conn.disconnect()
                logger.info("✅ MAVLink desconectado")
            except Exception as e:
                logger.error(f"Error disconnecting MAV: {e}")
    except Exception as e:
        logger.error(f"Error during shutdown cleanup: {e}")

@app.get("/")
def root():
    return {
        "message": "Drone Control API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

# Rutas adicionales para el frontend
@app.get("/drones")
def list_drones():
    return [
        {"id": 1, "name": "Test Drone", "status": "idle", "model": "PX4"}
    ]

@app.get("/missions")
def list_missions():
    return [
        {"id": 1, "name": "Mission Alpha", "status": "paused", "progress_percent": 0}
    ]

@app.get("/users")
def list_users():
    return [
        {"id": 1, "username": "operator", "role": "pilot"}
    ]

@app.get("/flight-routes")
def list_routes():
    return [
        {"id": 1, "name": "Route 1", "total_distance": 1.2}
    ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)