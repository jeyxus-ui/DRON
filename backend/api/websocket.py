"""
WebSocket API para comunicación en tiempo real con clientes (Mobile/Frontend)
Envía telemetría y recibe comandos de control.

CORRECCIONES:
- Añadido comando REBOOT (faltaba en process_command)
- Eliminado deadlock: recv_match ya no adquiere el lock de conexión dentro de wait_ack
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import asyncio
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._locks: dict = {}
        self.telemetry_task = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self._locks[id(websocket)] = asyncio.Lock()
        logger.info(f"Cliente conectado. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self._locks.pop(id(websocket), None)
        logger.info(f"Cliente desconectado. Total: {len(self.active_connections)}")

    async def send(self, websocket: WebSocket, message: dict):
        lock = self._locks.get(id(websocket))
        if lock is None:
            return
        async with lock:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error enviando a cliente: {e}")
                raise

    async def broadcast(self, message: dict):
        disconnected = set()
        for connection in list(self.active_connections):
            try:
                await self.send(connection, message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


async def telemetry_broadcaster(mav_controller):
    """Tarea en background que transmite telemetría a 10 Hz + connection health."""
    logger.info("Iniciando broadcaster de telemetría...")
    _last_healthy = True  # track state changes for alerts
    _debug_counter = 0
    while True:
        try:
            if manager.active_connections:
                telemetry = await get_telemetry_data(mav_controller)

                # Connection health
                conn = getattr(mav_controller, "conn", None)
                if conn and hasattr(conn, "get_connection_health"):
                    health = conn.get_connection_health()
                    telemetry["connection_health"] = health
                    # Send alert when MAVLink drops
                    healthy = health.get("healthy", True)

                    _debug_counter += 1
                    if _debug_counter % 50 == 1 or _last_healthy != healthy:
                        logger.warning(
                            "[BROADCASTER] healthy=%s (last=%s) | socket=%s probe_fails=%s "
                            "connected=%s hb_age=%s msg_age=%s reconnecting=%s needs_reconnect=%s",
                            healthy, _last_healthy,
                            health.get("socket_alive"), health.get("probe_failures"),
                            health.get("connected"), health.get("heartbeat_age_s"),
                            health.get("last_msg_age_s"),
                            health.get("reconnecting"), health.get("needs_reconnect"),
                        )

                    if _last_healthy and not healthy:
                        await manager.broadcast({
                            "type": "connection_alert",
                            "alert": "mavlink_lost",
                            "message": "Conexión MAVLink perdida — reconectando...",
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                        logger.warning("⚠️ WebSocket: alerta mavlink_lost ENVIADA a clientes")
                    elif not _last_healthy and healthy:
                        await manager.broadcast({
                            "type": "connection_alert",
                            "alert": "mavlink_restored",
                            "message": "Conexión MAVLink restaurada",
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                        logger.info("✅ WebSocket: conexión MAVLink restaurada, alerta enviada")
                    _last_healthy = healthy

                await manager.broadcast({
                    "type": "telemetry",
                    "data": telemetry,
                    "timestamp": datetime.utcnow().isoformat(),
                })
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error en telemetry_broadcaster: {e}")
            await asyncio.sleep(1)


def _get_sensor_data():
    try:
        from backend.api.rest import sensor_manager, _external_sensor_data, _external_update_time
        import time
        # Priorizar datos externos del bridge raspberry/ (si hay y son recientes)
        now = time.time()
        if _external_update_time > 0 and now - _external_update_time < 30 and _external_sensor_data:
            mtf = _external_sensor_data.get('mtf01', {})
            lid = _external_sensor_data.get('lidar', {})
            front_dist = mtf.get('distance_m') if mtf.get('valid') else None
            return {
                'mtf01_distance': mtf.get('distance_m'),
                'lidar_closest_distance': lid.get('closest_distance'),
                'lidar_closest_angle': lid.get('closest_angle'),
                'lidar_points': lid.get('points', 0),
                'obstacle_ahead': front_dist is not None and front_dist < 2.0,
            }
        if sensor_manager and sensor_manager._running:
            data = sensor_manager.get_data()
            return {
                'mtf01_distance': data.get('mtf01', {}).get('distance_m'),
                'lidar_closest_distance': data.get('lidar', {}).get('closest_distance'),
                'lidar_closest_angle': data.get('lidar', {}).get('closest_angle'),
                'lidar_points': data.get('lidar', {}).get('points', 0),
                'obstacle_ahead': sensor_manager.has_obstacle_ahead(),
            }
    except Exception as e:
        logger.debug("Error obteniendo datos de sensores: %s", e)
    return {}


async def get_telemetry_data(mav_controller) -> dict:
    """Extrae telemetría del controlador MAVLink + sensores."""
    try:
        # Priorizar datos externos del bridge raspberry/
        from backend.api.rest import _external_mavlink_data, _external_update_time
        now = time.time()
        if _external_update_time > 0 and now - _external_update_time < 30 and _external_mavlink_data:
            tel = dict(_external_mavlink_data)
            tel.update(_get_sensor_data())
            return tel
    except Exception as e:
        logger.debug("Error obteniendo datos de sensores: %s", e)

        telemetry = getattr(mav_controller, "telemetry", None)
        sensors = _get_sensor_data()

        # Soporte simulador
        if telemetry is None and hasattr(mav_controller, "get_telemetry"):
            sim = mav_controller.get_telemetry()
            return {
                "armed":             mav_controller.is_armed(),
                "mode":              mav_controller.get_mode(),
                "altitude":          sim.get("altitude", 0),
                "latitude":          sim.get("gps", {}).get("lat", 0),
                "longitude":         sim.get("gps", {}).get("lon", 0),
                "roll":              sim.get("attitude", {}).get("roll", 0),
                "pitch":             sim.get("attitude", {}).get("pitch", 0),
                "yaw":               sim.get("attitude", {}).get("yaw", 0),
                "battery_voltage":   sim.get("battery", {}).get("voltage", 0),
                "battery_current":   sim.get("battery", {}).get("current", 0),
                "battery_remaining": sim.get("battery", {}).get("remaining", 0),
                "ground_speed":      sim.get("speed", 0),
                "vertical_speed":    sim.get("climb_rate", 0),
                "satellites":        sim.get("gps", {}).get("satellites", 0),
                "hdop":              sim.get("gps", {}).get("hdop", 0),
                **sensors,
            }

        if telemetry is None:
            if not getattr(get_telemetry_data, "_error_shown", False):
                logger.error("Telemetría no disponible")
                get_telemetry_data._error_shown = True
            return {"error": "Telemetría no disponible"}

        attitude = telemetry.get_attitude() or {}
        gps      = telemetry.get_gps()      or {}
        battery  = telemetry.get_battery()  or {}
        velocity = telemetry.get_velocity() or {}

        return {
            "armed":             mav_controller.is_armed(),
            "mode":              mav_controller.get_mode(),
            "altitude":          gps.get("alt", 0),
            "latitude":          gps.get("lat", 0),
            "longitude":         gps.get("lon", 0),
            "roll":              attitude.get("roll", 0),
            "pitch":             attitude.get("pitch", 0),
            "yaw":               attitude.get("yaw", 0),
            "battery_voltage":   battery.get("voltage", 0),
            "battery_current":   battery.get("current", 0),
            "battery_remaining": battery.get("remaining", 0),
            "ground_speed":      velocity.get("ground_speed", 0),
            "vertical_speed":    velocity.get("vertical_speed", 0),
            "satellites":        gps.get("satellites", gps.get("satellites_visible", 0)),
            "hdop":              gps.get("hdop", 0),
            **sensors,
        }

    except Exception as e:
        logger.error(f"Error obteniendo telemetría: {e}")
        return {"error": str(e)}


async def process_command(command: dict, mav_controller) -> dict:
    """
    Procesa comandos recibidos desde el cliente WebSocket.
    Todos los valores RC se esperan NORMALIZADOS (-1.0 a 1.0 / 0.0 a 1.0 para throttle).
    """
    cmd_type = command.get("type", "")
    params   = command.get("params", {})

    if cmd_type != "RC_CONTROL":
        logger.info(f"Procesando comando: {cmd_type} | params: {params}")
    else:
        logger.debug(f"Procesando comando: {cmd_type} | params: {params}")

    if not mav_controller:
        return {"success": False, "message": "No hay dron conectado — el backend no pudo conectar con el Pixhawk"}

    if not mav_controller.is_connected():
        return {"success": False, "message": "Dron no conectado — verifica cable USB del Pixhawk y heartbeat MAVLink"}

    try:
        # ── Comandos de estado ────────────────────────────────────────────────
        if cmd_type == "ARM":
            force = params.get("force", True)
            # Throttle a mínimo antes de armar (precondición de ArduPilot)
            rc = getattr(mav_controller, "rc", None)
            if rc:
                rc.reset_controls()
            if not force:
                preflight = mav_controller.preflight_checks()
                failed = [k for k, v in preflight.items() if not v]
                if failed:
                    return {"success": False, "message": f"Pre-flight checks fallidos: {', '.join(failed)} — usa force=true para bypass"}
            success = await asyncio.to_thread(mav_controller.arm, force)
            if success:
                rc = getattr(mav_controller, "rc", None)
                if rc:
                    rc.set_armed(True)
            return {"success": success, "message": "Drone armado" if success else "Error armando"}

        elif cmd_type == "DISARM":
            success = await asyncio.to_thread(mav_controller.disarm)
            if success:
                rc = getattr(mav_controller, "rc", None)
                if rc:
                    rc.set_armed(False)
            return {"success": success, "message": "Drone desarmado" if success else "Error desarmando"}

        elif cmd_type == "TAKEOFF":
            altitude = params.get("altitude", 10)
            if not (1 <= altitude <= 10):
                return {"success": False, "message": "Altitud debe estar entre 1 y 10 metros"}
            success  = await asyncio.to_thread(mav_controller.takeoff, altitude)
            return {"success": success, "message": f"Despegando a {altitude}m" if success else "Error despegando"}

        elif cmd_type == "LAND":
            success = await asyncio.to_thread(mav_controller.land)
            return {"success": success, "message": "Aterrizando" if success else "Error aterrizando"}

        elif cmd_type == "RTL":
            success = await asyncio.to_thread(mav_controller.return_to_launch)
            return {"success": success, "message": "Regresando a home" if success else "Error en RTL"}

        elif cmd_type == "SET_MODE":
            mode    = params.get("mode", "STABILIZE")
            success = await asyncio.to_thread(mav_controller.set_mode, mode)
            return {"success": success, "message": f"Modo cambiado a {mode}" if success else f"Error cambiando a {mode}"}

        # ── REBOOT — CORRECCIÓN: faltaba este handler ─────────────────────────
        elif cmd_type == "REBOOT":
            try:
                if hasattr(mav_controller, "cmd") and mav_controller.cmd:
                    await asyncio.to_thread(mav_controller.cmd.reboot_autopilot)
                    return {"success": True, "message": "Autopiloto reiniciando..."}
                else:
                    return {"success": False, "message": "REBOOT no disponible en modo simulador"}
            except Exception as e:
                return {"success": False, "message": f"Error en REBOOT: {e}"}

        # ── Control RC — valores normalizados ─────────────────────────────────
        elif cmd_type == "RC_CONTROL":
            rc = getattr(mav_controller, "rc", None)
            if not rc:
                return {"success": False, "message": "RC no disponible"}

            # Valores ya normalizados: throttle 0..1, yaw/pitch/roll -1..1
            rc.set_controls(
                throttle=params.get("throttle"),
                yaw=params.get("yaw"),
                pitch=params.get("pitch"),
                roll=params.get("roll"),
            )
            return {"success": True, "message": "RC actualizado", "values": rc.get_current_values()}

        elif cmd_type == "RC_RESET":
            rc = getattr(mav_controller, "rc", None)
            if rc:
                rc.reset_controls()
            return {"success": True, "message": "RC reseteado"}

        # ── Emergencia ────────────────────────────────────────────────────────
        elif cmd_type == "EMERGENCY":
            action = params.get("action", "").upper()
            if action == "STOP":
                success = await asyncio.to_thread(mav_controller.set_mode, "BRAKE")
                if not success:
                    success = await asyncio.to_thread(mav_controller.set_mode, "LOITER")
                rc = getattr(mav_controller, "rc", None)
                if rc:
                    rc.reset_controls()
                    rc.set_armed(False)
                return {"success": success, "message": "STOP activado" if success else "Error en STOP"}
            elif action == "RTL":
                success = await asyncio.to_thread(mav_controller.return_to_launch)
                return {"success": success, "message": "RTL activado" if success else "Error en RTL"}
            elif action == "LAND":
                success = await asyncio.to_thread(mav_controller.land)
                return {"success": success, "message": "Aterrizaje de emergencia" if success else "Error aterrizando"}
            else:
                return {"success": False, "message": f"Acción desconocida: {action}"}

        # ── Velocidad de navegación ────────────────────────────────────────────
        elif cmd_type == "SET_NAV_SPEED":
            speed = params.get("speed", 2.0)
            try:
                cmd = getattr(mav_controller, "cmd", None)
                if cmd and hasattr(cmd, "set_nav_speed"):
                    await asyncio.to_thread(cmd.set_nav_speed, speed)
                    return {"success": True, "message": f"Velocidad de navegación → {speed:.1f} m/s"}
                return {"success": False, "message": "set_nav_speed no disponible"}
            except Exception as e:
                return {"success": False, "message": f"Error: {e}"}

        # ── Navegación ────────────────────────────────────────────────────────
        elif cmd_type == "GOTO":
            lat     = params.get("latitude")
            lon     = params.get("longitude")
            alt     = params.get("altitude", 10)
            # Aplicar velocidad de navegación si está configurada
            cmd = getattr(mav_controller, "cmd", None)
            if cmd and hasattr(cmd, "_nav_speed") and cmd._nav_speed is not None:
                await asyncio.to_thread(cmd.set_nav_speed, cmd._nav_speed)
            success = await asyncio.to_thread(mav_controller.goto, lat, lon, alt)
            return {"success": success, "message": f"Navegando a ({lat}, {lon})" if success else "Error navegando"}

        elif cmd_type == "GOTO_RELATIVE":
            from backend.mavlink.geo_utils import relative_to_gps
            fwd = params.get("forward", 0)
            right = params.get("right", 0)
            up = params.get("up", 0)
            tel = mav_controller.get_telemetry() if hasattr(mav_controller, 'get_telemetry') else {}
            gps_data = tel.get('gps', {})
            att_data = tel.get('attitude', {})
            cur_lat = gps_data.get('lat', 0)
            cur_lon = gps_data.get('lon', 0)
            if not cur_lat and not cur_lon:
                return {"success": False, "message": "Posición del dron no disponible"}
            cur_alt = tel.get('altitude', 0)
            yaw = att_data.get('yaw', 0)
            new_lat, new_lon, new_alt = relative_to_gps(cur_lat, cur_lon, cur_alt, yaw, fwd, right, up)
            success = await asyncio.to_thread(mav_controller.goto, new_lat, new_lon, new_alt)
            return {"success": success,
                    "message": f"Navegando {fwd}m adelante, {right}m derecha, {up}m arriba" if success else "Error navegando"}

        # ── Misión (waypoints) ────────────────────────────────────────────────
        elif cmd_type == "MISSION_UPLOAD":
            waypoints = params.get("waypoints", [])
            if not waypoints:
                return {"success": False, "message": "Lista de waypoints vacía"}
            try:
                formatted = []
                for wp in waypoints:
                    formatted.append({
                        'lat': wp.get('latitude') or wp.get('lat', 0),
                        'lon': wp.get('longitude') or wp.get('lon', 0),
                        'alt': wp.get('altitude') or wp.get('alt', 10),
                    })
                success = await asyncio.to_thread(mav_controller.upload_mission, formatted)
                return {"success": success, "message": f"Misión con {len(formatted)} waypoints subida" if success else "Error subiendo misión"}
            except Exception as e:
                return {"success": False, "message": f"Error en misión: {e}"}

        elif cmd_type == "MISSION_UPLOAD_RELATIVE":
            from backend.mavlink.geo_utils import waypoints_relative_to_gps
            rel_wps = params.get("waypoints", [])
            if not rel_wps:
                return {"success": False, "message": "Lista de waypoints vacía"}
            tel = mav_controller.get_telemetry() if hasattr(mav_controller, 'get_telemetry') else {}
            gps_data = tel.get('gps', {})
            att_data = tel.get('attitude', {})
            cur_lat = gps_data.get('lat', 0)
            cur_lon = gps_data.get('lon', 0)
            if not cur_lat and not cur_lon:
                return {"success": False, "message": "Posición del dron no disponible"}
            cur_alt = tel.get('altitude', 0)
            yaw = att_data.get('yaw', 0)
            try:
                abs_wps = waypoints_relative_to_gps(cur_lat, cur_lon, cur_alt, yaw, rel_wps)
                success = await asyncio.to_thread(mav_controller.upload_mission, abs_wps)
                return {"success": success, "message": f"Misión con {len(abs_wps)} waypoints subida" if success else "Error subiendo misión"}
            except Exception as e:
                return {"success": False, "message": f"Error en misión relativa: {e}"}

        elif cmd_type == "START_MISSION":
            try:
                success = await asyncio.to_thread(mav_controller.start_mission)
                return {"success": success, "message": "Misión iniciada" if success else "Error iniciando misión"}
            except Exception as e:
                return {"success": False, "message": f"Error: {e}"}

        elif cmd_type == "CLEAR_MISSION":
            try:
                success = await asyncio.to_thread(mav_controller.clear_mission)
                return {"success": success, "message": "Misión limpiada" if success else "Error limpiando misión"}
            except Exception as e:
                return {"success": False, "message": f"Error: {e}"}

        # ── Persistencia waypoints ────────────────────────────────────────────
        elif cmd_type == "SAVE_WAYPOINTS":
            name = params.get("name", "default")
            wps = params.get("waypoints", [])
            import os, json
            save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'data', 'waypoints')
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, f"{name}.json"), 'w') as f:
                json.dump(wps, f, indent=2)
            return {"success": True, "message": f"Waypoints guardados como '{name}'"}

        elif cmd_type == "LOAD_WAYPOINTS":
            name = params.get("name", "default")
            import os, json
            save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'data', 'waypoints')
            path = os.path.join(save_dir, f"{name}.json")
            if not os.path.exists(path):
                return {"success": False, "message": f"No se encontró '{name}'"}
            with open(path) as f:
                wps = json.load(f)
            return {"success": True, "message": f"Waypoints '{name}' cargados", "waypoints": wps}

        elif cmd_type == "LIST_WAYPOINTS":
            import os, glob
            save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'data', 'waypoints')
            os.makedirs(save_dir, exist_ok=True)
            files = glob.glob(os.path.join(save_dir, '*.json'))
            names = sorted([os.path.splitext(os.path.basename(f))[0] for f in files])
            return {"success": True, "names": names}

        # ── Navegación autónoma ──────────────────────────────────────────────
        elif cmd_type == "NAV_GOTO":
            from backend.api.rest import nav_controller as nc
            if nc is None:
                return {"success": False, "message": "Navegación no disponible"}
            nc.navigate_to(params.get("latitude"), params.get("longitude"), params.get("altitude", 10))
            return {"success": True, "message": "Navegación autónoma iniciada"}

        elif cmd_type == "NAV_MISSION":
            from backend.api.rest import nav_controller as nc
            if nc is None:
                return {"success": False, "message": "Navegación no disponible"}
            nc.start_mission(params.get("waypoints", []))
            return {"success": True, "message": "Misión autónoma iniciada"}

        elif cmd_type == "NAV_STOP":
            from backend.api.rest import nav_controller as nc
            if nc is None:
                return {"success": False, "message": "Navegación no disponible"}
            nc.stop_navigation()
            return {"success": True, "message": "Navegación detenida"}

        elif cmd_type == "NAV_AVOIDANCE":
            from backend.api.rest import nav_controller as nc
            if nc is None:
                return {"success": False, "message": "Navegación no disponible"}
            nc.avoidance.set_active(params.get("active", True))
            return {"success": True, "message": f"Evitación {'activada' if params.get('active', True) else 'desactivada'}"}

        elif cmd_type == "GET_SENSORS":
            from backend.api.rest import sensor_manager as sm
            if sm is None:
                return {"success": False, "message": "Sensores no disponibles"}
            return {"success": True, "data": sm.get_data()}

        elif cmd_type == "GET_OBSTACLE_MAP":
            from backend.api.rest import sensor_manager as sm
            if sm is None:
                return {"success": False, "message": "Sensores no disponibles"}
            return {"success": True, "data": sm.obstacle_map.to_dict()}

        else:
            logger.warning(f"Comando desconocido recibido: {cmd_type}")
            return {"success": False, "message": f"Comando desconocido: {cmd_type}"}

    except Exception as e:
        logger.error(f"Error procesando {cmd_type}: {e}")
        return {"success": False, "message": f"Error: {e}"}


@router.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket principal.
    - Requiere token de sesión vía query param (?token=...) — se valida ANTES de aceptar.
    - Envía telemetría cada 100ms (via telemetry_broadcaster)
    - Recibe comandos y responde con ACK
    """
    client_id = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"

    from backend.api.auth import websocket_token_user
    user = websocket_token_user(websocket.query_params)
    if user is None:
        logger.warning(f"[WS] {client_id} — conexión rechazada: token inválido o ausente")
        await websocket.close(code=1008, reason="Autenticación requerida: token inválido o expirado")
        return
    logger.info(f"[WS] {client_id} — conexión autorizada (usuario: {user.get('username')})")

    await manager.connect(websocket)

    from backend.api import rest
    mav_controller = rest.mav

    if not mav_controller:
        logger.warning(f"[WS] {client_id} — No hay dron conectado")
    elif not mav_controller.is_connected():
        logger.warning(f"[WS] {client_id} — Dron conectado pero sin heartbeat")

    # Notificar reconexión al RC (cancela failsafe si estaba activo)
    rc = getattr(mav_controller, "rc", None) if mav_controller else None
    if rc:
        rc.on_reconnect()

    # Enviar estado inicial de conexión MAVLink al cliente
    try:
        conn = getattr(mav_controller, "conn", None) if mav_controller else None
        health = conn.get_connection_health() if conn and hasattr(conn, "get_connection_health") else None
        await manager.send(websocket, {
            "type": "connection_alert",
            "alert": "connected",
            "message": "Conexión WebSocket establecida",
            "mavlink": health,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.debug("Error enviando welcome message: %s", e)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError as e:
                logger.warning(f"[WS] JSON inválido de {client_id}: {e}")
                continue

            cmd_type = message.get("type", "<sin tipo>")
            if cmd_type != "RC_CONTROL":
                logger.info(f"[WS] {client_id} → {cmd_type}")
            else:
                logger.debug(f"[WS] {client_id} → {cmd_type}")

            result = await process_command(message, mav_controller)

            # RC_CONTROL y RC_RESET son continuos — no necesitan ACK
            # para evitar saturar el canal WebSocket a 10Hz
            if cmd_type not in ("RC_CONTROL", "RC_RESET"):
                await manager.send(websocket, {
                    "type":      "command_ack",
                    "command":   cmd_type,
                    "result":    result,
                    "timestamp": datetime.utcnow().isoformat(),
                })

    except WebSocketDisconnect as e:
        manager.disconnect(websocket)
        logger.info(f"[WS] {client_id} desconectado (code={e.code})")
        # Failsafe: NO resetea controles — el dron mantiene velocidad actual
        # Si no reconecta en 10s, rc_override desarma automáticamente
        rc = getattr(mav_controller, "rc", None) if mav_controller else None
        if rc:
            rc.on_disconnect()
    except Exception as e:
        logger.error(f"[WS] {client_id} ERROR: {type(e).__name__}: {e}", exc_info=True)
        manager.disconnect(websocket)
        rc = getattr(mav_controller, "rc", None) if mav_controller else None
        if rc:
            rc.on_disconnect()


def start_telemetry_broadcast(mav_controller):
    loop = asyncio.get_event_loop()
    manager.telemetry_task = loop.create_task(telemetry_broadcaster(mav_controller))
    logger.info("Telemetry broadcaster iniciado")