"""
Endpoints REST para control del dron.

CORRECCIONES:
- Lista de modos válidos ampliada a todos los que muestra el frontend
- /telemetry ahora incluye vertical_speed y hdop (faltaban)
- Emergencia STOP: intenta BRAKE primero, cae a LOITER si no hay GPS
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio
import logging
import threading
import time

logger = logging.getLogger(__name__)

router = APIRouter(tags=["drone"])

mav = None
sensor_manager = None
nav_controller = None
_monitor_thread = None

# Datos recibidos desde raspberry/ bridge (cuando el backend no tiene acceso directo al hardware)
_external_sensor_data = {}
_external_mavlink_data = {}
_external_update_time = 0.0

# ── Todos los modos que muestra el frontend ────────────────────────────────────
VALID_MODES = [
    "STABILIZE", "ACRO", "SPORT", "DRIFT",
    "ALT_HOLD",  "POSHOLD", "LOITER", "BRAKE",
    "AUTO",      "GUIDED",  "CIRCLE", "FLIP", "THROW",
    "RTL",       "SMARTRTL","LAND",
]

# ── Inicialización MAVLink ─────────────────────────────────────────────────────

def init_mav(device: str, baud: int) -> bool:
    global mav
    try:
        from backend.mavlink.controller import MAVController
        mav = MAVController(device, baud)
        logger.info("MAVLink controller initialized: device=%s baud=%s", device, baud)
        return True
    except Exception as e:
        logger.exception("Error initializing MAV controller: %s", e)
        mav = None
        return False


def start_monitoring(baud: int, interval: int = 5) -> None:
    global _monitor_thread
    def _loop():
        import time
        while _monitor_thread and getattr(_monitor_thread, "_running", True):
            if mav and getattr(mav, "conn", None) and not mav.conn.is_connected():
                logger.warning("MAVLink connection lost")
            time.sleep(interval)
    _monitor_thread = threading.Thread(target=_loop, daemon=True)
    _monitor_thread._running = True
    _monitor_thread.start()
    logger.info("MAVLink monitoring started (interval=%ss)", interval)

# ── Schemas ────────────────────────────────────────────────────────────────────

class ArmRequest(BaseModel):
    force: bool = False

class TakeoffRequest(BaseModel):
    altitude: float = 10.0

class ModeRequest(BaseModel):
    mode: str

class GotoRequest(BaseModel):
    latitude:  float
    longitude: float
    altitude:  float = 10.0

class RCControlRequest(BaseModel):
    throttle: Optional[float] = None  # 0.0 – 1.0
    yaw:      Optional[float] = None  # -1.0 – 1.0
    pitch:    Optional[float] = None  # -1.0 – 1.0
    roll:     Optional[float] = None  # -1.0 – 1.0

class EmergencyRequest(BaseModel):
    action: str  # "STOP", "RTL", "LAND", "KILL"

# ── Helper ─────────────────────────────────────────────────────────────────────

def get_mav_controller():
    if mav is None:
        raise HTTPException(status_code=503, detail="MAVLink no conectado")
    return mav

# ── Estado y Telemetría ────────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    try:
        ctrl = get_mav_controller()
        return {
            "connected":     ctrl.is_connected(),
            "armed":         ctrl.is_armed(),
            "mode":          ctrl.get_mode(),
            "system_status": ctrl.get_system_status(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telemetry")
async def get_telemetry():
    try:
        # Si hay datos MAVLink externos recientes (< 30s), usarlos
        if _external_update_time > 0 and time.time() - _external_update_time < 30 and _external_mavlink_data:
            tel = dict(_external_mavlink_data)
            tel["_source"] = "external"
            return tel
        ctrl = get_mav_controller()
        if ctrl.telemetry is None:
            tel = ctrl.get_telemetry()
            return {
                "armed":             ctrl.is_armed(),
                "mode":              ctrl.get_mode(),
                "altitude":          tel.get("altitude", 0),
                "latitude":          tel.get("gps", {}).get("lat", 0),
                "longitude":         tel.get("gps", {}).get("lon", 0),
                "roll":              tel.get("attitude", {}).get("roll", 0),
                "pitch":             tel.get("attitude", {}).get("pitch", 0),
                "yaw":               tel.get("attitude", {}).get("yaw", 0),
                "battery_voltage":   tel.get("battery", {}).get("voltage", 0),
                "battery_remaining": tel.get("battery", {}).get("remaining", 0),
                "ground_speed":      0.0,
                "vertical_speed":    0.0,
                "satellites":        tel.get("gps", {}).get("satellites", 0),
                "hdop":              tel.get("gps", {}).get("hdop", 0),
            }
        attitude = ctrl.telemetry.get_attitude() or {}
        gps      = ctrl.telemetry.get_gps()      or {}
        battery  = ctrl.telemetry.get_battery()  or {}
        velocity = ctrl.telemetry.get_velocity() or {}

        hdop_raw = gps.get("hdop", 0)

        return {
            "armed":             ctrl.is_armed(),
            "mode":              ctrl.get_mode(),
            "altitude":          ctrl.telemetry.data.get("altitude", 0),
            "latitude":          gps.get("lat", 0),
            "longitude":         gps.get("lon", 0),
            "roll":              attitude.get("roll", 0),
            "pitch":             attitude.get("pitch", 0),
            "yaw":               attitude.get("yaw", 0),
            "battery_voltage":   battery.get("voltage", 0),
            "battery_remaining": battery.get("remaining", 0),
            "ground_speed":      velocity.get("ground_speed", 0),
            "vertical_speed":    velocity.get("vertical_speed", 0),
            "satellites":        gps.get("satellites", 0),
            "hdop":              hdop_raw if hdop_raw < 100 else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Diagnóstico ───────────────────────────────────────────────────────────────

@router.get("/diag/params")
async def diag_params():
    """Lee parámetros críticos del Pixhawk para diagnóstico."""
    try:
        ctrl = get_mav_controller()
        params = ctrl.get_critical_params()
        return {"success": True, "params": params}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/diag/param/set")
async def diag_param_set(name: str, value: float):
    """Establece un parámetro en el Pixhawk."""
    try:
        ctrl = get_mav_controller()
        result = ctrl.set_param(name, value)
        return {"success": True, "param": name, "value": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/diag/motor-test")
async def diag_motor_test(motor: int = 0, throttle: float = 10.0, duration: float = 1.5, armed: bool = False):
    """Test individual motor. motor=0-3, throttle=0-100, duration=seconds."""
    try:
        ctrl = get_mav_controller()
        await asyncio.to_thread(ctrl.cmd.test_motor, motor, throttle, duration, even_if_armed=armed)
        return {"success": True, "message": f"Motor {motor} tested @ {throttle}% for {duration}s"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/diag/rc")
async def diag_rc():
    """Diagnóstico del estado actual de RC Override."""
    try:
        ctrl = get_mav_controller()
        rc = getattr(ctrl, "rc", None)
        if not rc:
            return {"success": False, "message": "RC no disponible"}
        values = rc.get_current_values()
        values["_send_failures"] = rc._send_failures
        values["_send_count"] = rc._send_count
        values["armed"] = rc._armed
        return {"success": True, "rc": values}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/diag/servo_raw")
async def diag_servo_raw():
    """Lee SERVO_OUTPUT_RAW del Pixhawk (PWM real que está emitiendo)."""
    try:
        ctrl = get_mav_controller()
        data = ctrl.get_servo_output_raw()
        return {"success": "error" not in data, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/diag/rc_channels")
async def diag_rc_channels():
    """Lee RC_CHANNELS del Pixhawk (lo que ve como entrada)."""
    try:
        ctrl = get_mav_controller()
        data = ctrl.get_rc_channels()
        return {"success": "error" not in data, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Control Básico ─────────────────────────────────────────────────────────────

@router.post("/arm")
async def arm_drone(request: ArmRequest):
    try:
        ctrl = get_mav_controller()
        if ctrl.is_armed() and not request.force:
            return {"success": False, "message": "Dron ya está armado"}
        success = await asyncio.to_thread(ctrl.arm, request.force)
        rc = getattr(ctrl, "rc", None)
        if success and rc:
            rc.set_armed(True)
        return {"success": success, "message": "Dron armado" if success else "Error armando", "armed": ctrl.is_armed()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disarm")
async def disarm_drone():
    try:
        ctrl = get_mav_controller()
        if not ctrl.is_armed():
            return {"success": False, "message": "Dron ya está desarmado"}
        success = await asyncio.to_thread(ctrl.disarm)
        rc = getattr(ctrl, "rc", None)
        if success and rc:
            rc.set_armed(False)
        return {"success": success, "message": "Dron desarmado" if success else "Error desarmando", "armed": ctrl.is_armed()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/takeoff")
async def takeoff(request: TakeoffRequest):
    try:
        ctrl = get_mav_controller()
        if not ctrl.is_armed():
            return {"success": False, "message": "Dron no está armado"}
        if not (2 <= request.altitude <= 100):
            return {"success": False, "message": "Altitud debe estar entre 2 y 100 metros"}
        success = await asyncio.to_thread(ctrl.takeoff, request.altitude)
        return {"success": success, "message": f"Despegando a {request.altitude}m" if success else "Error despegando"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/land")
async def land():
    try:
        ctrl    = get_mav_controller()
        success = await asyncio.to_thread(ctrl.land)
        return {"success": success, "message": "Aterrizando" if success else "Error aterrizando"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rtl")
async def return_to_launch():
    try:
        ctrl    = get_mav_controller()
        success = await asyncio.to_thread(ctrl.return_to_launch)
        return {"success": success, "message": "Regresando a home" if success else "Error en RTL"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Control RC ─────────────────────────────────────────────────────────────────

@router.post("/rc/control")
async def rc_control(request: RCControlRequest):
    try:
        ctrl = get_mav_controller()
        if not getattr(ctrl, "rc", None):
            return {"success": False, "message": "RC Controller no inicializado"}
        ctrl.rc.set_controls(
            throttle=request.throttle,
            yaw=request.yaw,
            pitch=request.pitch,
            roll=request.roll,
        )
        return {"success": True, "message": "Controles RC actualizados", "values": ctrl.rc.get_current_values()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rc/reset")
async def rc_reset():
    try:
        ctrl = get_mav_controller()
        if getattr(ctrl, "rc", None):
            ctrl.rc.reset_controls()
            return {"success": True, "message": "Controles RC reseteados"}
        return {"success": False, "message": "RC Controller no disponible"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rc/values")
async def get_rc_values():
    try:
        ctrl = get_mav_controller()
        if getattr(ctrl, "rc", None):
            return {"success": True, "values": ctrl.rc.get_current_values()}
        return {"success": False, "message": "RC Controller no disponible"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Emergencias ────────────────────────────────────────────────────────────────

@router.post("/emergency")
async def emergency_action(request: EmergencyRequest):
    """
    Acciones de emergencia.
    CORRECCIÓN: STOP intenta BRAKE primero (más seguro que LOITER sin GPS).
    Si BRAKE falla, cae a LOITER.
    """
    try:
        ctrl   = get_mav_controller()
        action = request.action.upper()

        if action == "STOP":
            # BRAKE es más seguro que LOITER cuando no hay GPS
            success = await asyncio.to_thread(ctrl.set_mode, "BRAKE")
            if not success:
                logger.warning("BRAKE falló, intentando LOITER...")
                success = await asyncio.to_thread(ctrl.set_mode, "LOITER")
            if getattr(ctrl, "rc", None):
                ctrl.rc.reset_controls()
            message = "STOP: modo BRAKE/LOITER activado" if success else "Error en STOP"

        elif action == "RTL":
            success = await asyncio.to_thread(ctrl.return_to_launch)
            message = "RTL activado" if success else "Error activando RTL"

        elif action == "LAND":
            success = await asyncio.to_thread(ctrl.land)
            message = "Aterrizaje de emergencia activado" if success else "Error aterrizando"

        elif action == "KILL":
            logger.warning("⚠️ MOTOR KILL ACTIVADO")
            success = await asyncio.to_thread(ctrl.kill_motors)
            message = "MOTORES DETENIDOS" if success else "Error en MOTOR KILL"

        else:
            return {"success": False, "message": f"Acción desconocida: {action}"}

        return {"success": success, "action": action, "message": message}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Cambio de Modo ─────────────────────────────────────────────────────────────

@router.post("/mode")
async def set_mode(request: ModeRequest):
    """
    CORRECCIÓN: Lista de modos válidos ampliada para cubrir todos los que
    muestra el frontend (antes faltaban POSHOLD, CIRCLE, SPORT, ACRO, DRIFT,
    FLIP, THROW, SMARTRTL).
    """
    try:
        ctrl = get_mav_controller()
        mode = request.mode.upper()

        if mode not in VALID_MODES:
            return {"success": False, "message": f"Modo inválido. Válidos: {', '.join(VALID_MODES)}"}

        success = await asyncio.to_thread(ctrl.set_mode, mode)
        return {
            "success": success,
            "message": f"Modo cambiado a {mode}" if success else "Error cambiando modo",
            "mode":    ctrl.get_mode(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Waypoints persistencia ──────────────────────────────────────────────────────

import os, json
_WAYPOINTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'waypoints')

class SaveWaypointsRequest(BaseModel):
    name: str = "default"
    waypoints: list

class LoadWaypointsRequest(BaseModel):
    name: str = "default"

@router.post("/waypoints/save")
async def save_waypoints(request: SaveWaypointsRequest):
    try:
        os.makedirs(_WAYPOINTS_DIR, exist_ok=True)
        path = os.path.join(_WAYPOINTS_DIR, f"{request.name}.json")
        with open(path, 'w') as f:
            json.dump(request.waypoints, f, indent=2)
        return {"success": True, "message": f"Waypoints guardados como '{request.name}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/waypoints/load")
async def load_waypoints(request: LoadWaypointsRequest):
    try:
        path = os.path.join(_WAYPOINTS_DIR, f"{request.name}.json")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"No se encontró '{request.name}'")
        with open(path) as f:
            waypoints = json.load(f)
        return {"success": True, "waypoints": waypoints}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/waypoints/list")
async def list_waypoints():
    try:
        os.makedirs(_WAYPOINTS_DIR, exist_ok=True)
        files = [f for f in os.listdir(_WAYPOINTS_DIR) if f.endswith('.json')]
        names = sorted([os.path.splitext(f)[0] for f in files])
        return {"success": True, "names": names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/waypoints/{name}")
async def delete_waypoint(name: str):
    try:
        path = os.path.join(_WAYPOINTS_DIR, f"{name}.json")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"No se encontró '{name}'")
        os.remove(path)
        return {"success": True, "message": f"'{name}' eliminado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Navegación ─────────────────────────────────────────────────────────────────

@router.post("/goto")
async def goto_location(request: GotoRequest):
    try:
        ctrl = get_mav_controller()
        if not ctrl.is_armed():
            return {"success": False, "message": "Dron debe estar armado"}
        success = await asyncio.to_thread(ctrl.goto, request.latitude, request.longitude, request.altitude)
        return {
            "success": success,
            "message": f"Navegando a ({request.latitude}, {request.longitude})" if success else "Error navegando",
            "target": {"latitude": request.latitude, "longitude": request.longitude, "altitude": request.altitude},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Inicialización sensores ──────────────────────────────────────────────────

def init_sensors(mav_controller):
    global sensor_manager
    try:
        from backend.sensors.manager import SensorManager
        sim_mode = hasattr(mav_controller, '_sim')
        sensor_manager = SensorManager(sim_mode=sim_mode)
        sensor_manager.start()
        logger.info("SensorManager iniciado (sim=%s)", sim_mode)
        return True
    except Exception as e:
        logger.exception("Error iniciando sensores: %s", e)
        sensor_manager = None
        return False

def init_navigation(mav_controller):
    global nav_controller
    try:
        if sensor_manager is None:
            logger.warning("Sensores no disponibles, navegación no iniciada")
            return False
        from backend.navigation.avoidance import ObstacleAvoidance
        from backend.navigation.planner import PathPlanner
        from backend.navigation.controller import NavigationController
        avoidance = ObstacleAvoidance()
        planner = PathPlanner()
        nav_controller = NavigationController(mav_controller, sensor_manager, avoidance, planner)
        def nav_emergency(action, data):
            try:
                mav_controller.set_mode("BRAKE")
                logger.warning("🛑 NAV auto-avoid: BRAKE mode set")
            except Exception as e:
                logger.error(f"Nav emergency failed: {e}")
        nav_controller.set_emergency_callback(nav_emergency)
        nav_controller.start()
        logger.info("NavigationController iniciado")
        return True
    except Exception as e:
        logger.exception("Error iniciando navegación: %s", e)
        nav_controller = None
        return False

def shutdown_sensors_and_nav():
    global sensor_manager, nav_controller
    if nav_controller:
        try:
            nav_controller.stop()
            logger.info("Navegación detenida")
        except Exception as e:
            logger.error("Error deteniendo navegación: %s", e)
        nav_controller = None
    if sensor_manager:
        try:
            sensor_manager.stop()
            logger.info("Sensores detenidos")
        except Exception as e:
            logger.error("Error deteniendo sensores: %s", e)
        sensor_manager = None

# ── Endpoint para recibir datos del bridge raspberry/ ────────────────────────

class SensorExternalRequest(BaseModel):
    mtf01: Optional[dict] = None
    lidar: Optional[dict] = None
    obstacle_map: Optional[dict] = None
    telemetry: Optional[dict] = None

class MavlinkExternalRequest(BaseModel):
    armed: Optional[bool] = None
    mode: Optional[str] = None
    altitude: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    roll: Optional[float] = None
    pitch: Optional[float] = None
    yaw: Optional[float] = None
    battery_voltage: Optional[float] = None
    battery_remaining: Optional[int] = None
    ground_speed: Optional[float] = None
    vertical_speed: Optional[float] = None
    satellites: Optional[int] = None
    hdop: Optional[float] = None

class BridgeDataRequest(BaseModel):
    """Datos completos enviados por raspberry/bridge.py"""
    sensors: Optional[SensorExternalRequest] = None
    mavlink: Optional[MavlinkExternalRequest] = None

@router.post("/sensors")
async def post_sensor_data(data: BridgeDataRequest):
    """Recibe datos de sensores desde raspberry/bridge.py"""
    global _external_sensor_data, _external_mavlink_data, _external_update_time
    if data.sensors:
        _external_sensor_data = data.sensors.model_dump(exclude_none=True)
    if data.mavlink:
        _external_mavlink_data = data.mavlink.model_dump(exclude_none=True)
    _external_update_time = time.time()
    return {"success": True, "updated_at": _external_update_time}

@router.get("/sensors/source")
async def get_sensor_source():
    """Indica de dónde vienen los datos de sensores actualmente."""
    source = "sim"
    if _external_update_time > 0 and time.time() - _external_update_time < 30:
        source = "external"
    elif sensor_manager and not sensor_manager.sim_mode:
        source = "local"
    return {
        "source": source,
        "sim_mode": sensor_manager.sim_mode if sensor_manager else True,
        "external_age_s": round(time.time() - _external_update_time, 1) if _external_update_time else None,
        "external_present": _external_update_time > 0,
    }

# ── Endpoints sensores ───────────────────────────────────────────────────────

@router.get("/sensors")
async def get_sensor_data():
    # Si hay datos externos recientes (< 30s), usarlos
    if _external_update_time > 0 and time.time() - _external_update_time < 30:
        data = dict(_external_sensor_data)
        data["_source"] = "external"
        data["_updated_at"] = _external_update_time
        return {"success": True, "data": data}
    if sensor_manager is not None:
        return {"success": True, "data": sensor_manager.get_data(), "_source": "local"}
    return {"success": False, "message": "Sensores no disponibles"}

@router.get("/sensors/status")
async def get_sensor_status():
    if sensor_manager is None:
        return {"success": False, "message": "Sensores no disponibles"}
    return {"success": True, "data": sensor_manager.get_status()}

# ── Endpoints navegación ─────────────────────────────────────────────────────

@router.get("/nav/status")
async def get_nav_status():
    if nav_controller is None:
        return {"success": False, "message": "Navegación no disponible"}
    return {"success": True, "data": nav_controller.get_status()}

class NavGotoRequest(BaseModel):
    latitude: float
    longitude: float
    altitude: float = 10.0

@router.post("/nav/goto")
async def nav_goto(request: NavGotoRequest):
    try:
        if nav_controller is None:
            return {"success": False, "message": "Navegación no disponible"}
        nav_controller.navigate_to(request.latitude, request.longitude, request.altitude)
        return {
            "success": True,
            "message": f"Navegando a ({request.latitude}, {request.longitude})",
            "target": {"lat": request.latitude, "lon": request.longitude, "alt": request.altitude},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class NavMissionRequest(BaseModel):
    waypoints: list

@router.post("/nav/mission")
async def nav_mission(request: NavMissionRequest):
    try:
        if nav_controller is None:
            return {"success": False, "message": "Navegación no disponible"}
        nav_controller.start_mission(request.waypoints)
        return {"success": True, "message": f"Misión con {len(request.waypoints)} waypoints iniciada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nav/stop")
async def nav_stop():
    if nav_controller is None:
        return {"success": False, "message": "Navegación no disponible"}
    nav_controller.stop_navigation()
    return {"success": True, "message": "Navegación detenida"}

@router.post("/nav/avoidance")
async def toggle_avoidance(active: bool = True):
    if nav_controller is None:
        return {"success": False, "message": "Navegación no disponible"}
    nav_controller.avoidance.set_active(active)
    return {"success": True, "message": f"Avoidance {'activado' if active else 'desactivado'}"}

# ── Endpoints mapa de obstáculos ─────────────────────────────────────────────

@router.get("/obstacle-map")
async def get_obstacle_map():
    if sensor_manager is None:
        return {"success": False, "message": "Sensores no disponibles"}
    return {"success": True, "data": sensor_manager.obstacle_map.to_dict()}

@router.post("/obstacle-map/reset")
async def reset_obstacle_map():
    if sensor_manager is None:
        return {"success": False, "message": "Sensores no disponibles"}
    sensor_manager.obstacle_map.reset()
    return {"success": True, "message": "Mapa de obstáculos reiniciado"}