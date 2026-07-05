# Backend — Documentación Completa del Código

## Estructura del Backend

```
backend/
├── api/              # Capa de transporte: REST + WebSocket + Cámara
│   ├── rest.py           # 20+ endpoints REST para control y telemetría
│   ├── websocket.py      # Tiempo real: telemetría 10Hz + comandos
│   └── camera_stream.py  # Streaming MJPEG/WS + YOLO/ArUco
├── config.py         # Configuración central (env vars, auto-detect MAVLink)
├── main.py           # Punto de entrada: FastAPI, lifecycle startup/shutdown
├── db/               # Persistencia (PostgreSQL)
│   ├── database.py       # Engine SQLAlchemy
│   ├── models.py         # Modelo Telemetry
│   └── repository.py     # save_telemetry()
├── mavlink/          # Capa MAVLink: comunicación con Pixhawk
│   ├── connection.py     # Conexión serie/USB, auto-reconnect, ACKs
│   ├── commands.py       # ARM/DISARM/TAKEOFF/LAND/GOTO/EMERGENCY
│   ├── telemetry.py      # Lectura continua de sensores vía MAVLink
│   ├── controller.py     # Orquestador: unifica conn + commands + telemetry
│   ├── rc_override.py    # Joystick: mapea -1..1 → PWM 1000-2000
│   ├── geo_utils.py      # Coordenadas relativas → GPS absoluto
│   └── sim_test.py       # Script de prueba en modo SIM
├── navigation/       # Navegación autónoma
│   ├── avoidance.py      # Evaluación de obstáculos (BRAKE/AVOID/NONE)
│   ├── planner.py        # Planificación de rutas y patrones de búsqueda
│   └── controller.py     # Loop de navegación 5Hz, ejecuta misiones
├── schemas/           # (placeholder) — Schemas definidos inline en rest.py
├── sensors/          # Drivers de sensores físicos
│   ├── base.py           # Clase abstracta BaseSensor + dataclasses
│   ├── manager.py        # Orquestador: loop 20Hz, MTF01 + LIDAR + mapa
│   ├── mtf01.py          # Sensor ultrasónico MTF01 (I2C 0x57)
│   ├── ydlidar_x4.py     # LIDAR YDLIDAR X4 (serial 115200 baud)
│   └── obstacle_map.py   # Grid 2D 20×20m (0.2m resolución)
├── tests/            # Tests (config + endpoints)
└── vision/           # Visión por computadora
    └── detector.py       # YOLOv8n + ArUco + estimación de distancia
```

---

## 1. Flujo de Datos General

```
                         ┌──────────────────────────────────┐
                         │         main.py                  │
                         │  (FastAPI app, startup/shutdown) │
                         └──────┬─────────────────────┬─────┘
                                │                     │
              ┌─────────────────┤                     ├─────────────────┐
              ▼                 ▼                     ▼                 ▼
      api/rest.py        api/websocket.py      api/camera_stream   (db/)
      (REST HTTP)        (WebSocket 10Hz)      (MJPEG/WS vision)   (histórico)
              │                 │                     │
              └─────────┬───────┴──────────┬──────────┘
                        ▼                  ▼
               mavlink/controller     sensors/manager
                        │                  │
              ┌─────────┼──────────┐       ├── mtf01.py (I2C)
              ▼         ▼          ▼       ├── ydlidar_x4.py (serial)
        connection  commands  telemetry    └── obstacle_map.py (grid 20×20m)
        (serial)   (MAVLink)  (MAVLink)
                        │                  │
                        └──────┬───────────┘
                               ▼
                    Pixhawk / Autopiloto
                    (ArduPilot / PX4)

  Raspberry Pi Bridge → POST /api/sensors → cache con TTL 30s
  (alternativa sin conexión directa)
```

### Flujo por capa

| Capa | Archivos | Qué hace | Frecuencia |
|------|----------|----------|------------|
| Transporte | `rest.py` | Endpoints HTTP (control, telemetría, waypoints, sensores) | Bajo demanda |
| Transporte | `websocket.py` | Broadcast de telemetría + recepción de comandos | 10 Hz |
| Transporte | `camera_stream.py` | Streaming MJPEG/WebSocket, detección YOLO/ArUco | 25-30 fps |
| Orquestación | `controller.py` | MAVController: unifica conexión, comandos, telemetría, RC | — |
| Sensores | `manager.py` | Loop de lectura MTF01 + LIDAR + actualización mapa | 20 Hz |
| Navegación | `navigation/controller.py` | Loop de navegación autónoma con evitación | 5 Hz |
| Visión | `detector.py` | YOLOv8 inference + ArUco markers + distancia | Cada frame |
| DB | `repository.py` | Persistencia de snapshots de telemetría | Cada 5s (opcional) |

---

## 2. config.py — Configuración Central

**Propósito:** Carga variables de entorno y auto-detecta el dispositivo MAVLink.

**Variables principales:**

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MAVLINK_DEVICE` | `"udpin:0.0.0.0:14550"` | String de conexión: `SIM`, `tcp:...`, `udpin:...`, o ruta serie (`/dev/ttyUSB0`) |
| `MAVLINK_BAUD` | `115200` | Baud rate (115200 USB directo, 57600 radio telemetría) |
| `API_HOST` | `"0.0.0.0"` | IP de bind del servidor |
| `API_PORT` | `8000` | Puerto del servidor |
| `LOG_LEVEL` | `"INFO"` | Nivel de logging |
| `DB_URL` | `postgresql://...` | URL de base de datos PostgreSQL |

**Auto-detección:** `detect_mavlink_device()` prioriza: (1) env var `MAVLINK_DEVICE`, (2) sondeo de puertos serie (`/dev/ttyACM*`, `/dev/ttyUSB*`), (3) fallback `"SIM"`.

---

## 3. main.py — Punto de Entrada

**Propósito:** Crea la app FastAPI, registra routers CORS, y orquesta el lifecycle.

**Startup (`startup_event`):** orden de inicialización:
1. `init_mav(device, baud)` → crea MAVController
2. Inicia cámara (`RealSenseCamera`)
3. `start_telemetry_broadcast()` → WebSocket 10Hz
4. Registra callback de emergencia (visión → BRAKE)
5. `init_sensors(mav)` → SensorManager
6. `init_navigation(mav, sensors)` → NavigationController

**Shutdown:** Detiene navegación, sensores, cámara, desconecta MAVLink.

**Endpoints propios:**
| Ruta | Método | Descripción |
|------|--------|-------------|
| `/` | GET | Metadata de la API |
| `/health` | GET | `{"status": "healthy"}` |
| `/drones`, `/missions`, `/users`, `/flight-routes` | GET | Datos estáticos placeholder |

---

## 4. api/rest.py — REST API

**Propósito:** 20+ endpoints para control del dron, telemetría, waypoints, sensores, navegación, y recepción de datos externos (bridge Raspberry Pi).

**Variables globales:** `mav` (MAVController), `sensor_manager`, `nav_controller`, `_external_sensor_data` (caché bridge).

### Endpoints

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/api/status` | GET | Estado: connected, armed, mode, system_status |
| `/api/telemetry` | GET | Telemetría completa (altitude, GPS, battery, attitude, speeds, satélites) |
| `/api/arm` | POST | Armar motores |
| `/api/disarm` | POST | Desarmar motores |
| `/api/takeoff` | POST | Despegar (altitud 2-100m) |
| `/api/land` | POST | Aterrizar |
| `/api/rtl` | POST | Regreso a casa |
| `/api/rc/control` | POST | Control RC (throttle 0-1, yaw/pitch/roll -1 a 1) |
| `/api/rc/reset` | POST | Resetear controles RC |
| `/api/rc/values` | GET | Valores actuales de RC |
| `/api/emergency` | POST | STOP / RTL / LAND / KILL |
| `/api/mode` | POST | Cambiar modo de vuelo (15 modos) |
| `/api/waypoints/save` | POST | Guardar waypoints a JSON |
| `/api/waypoints/load` | POST | Cargar waypoints de JSON |
| `/api/waypoints/list` | GET | Listar waypoints guardados |
| `/api/waypoints/{name}` | DELETE | Eliminar waypoint |
| `/api/goto` | POST | Volar a coordenada GPS |
| `/api/sensors` | POST | Recibir datos de bridge externo (RPi) |
| `/api/sensors/source` | GET | Fuente de datos (sim/local/external) |
| `/api/sensors` | GET | Datos actuales de sensores |
| `/api/sensors/status` | GET | Estado de los sensores (running/stopped) |
| `/api/nav/status` | GET | Estado del NavigationController |
| `/api/nav/goto` | POST | Navegación autónoma a coordenada |
| `/api/nav/mission` | POST | Iniciar misión con lista de waypoints |
| `/api/nav/stop` | POST | Detener navegación autónoma |
| `/api/nav/avoidance` | POST | Activar/desactivar evitación |
| `/api/obstacle-map` | GET | Mapa de obstáculos (grid) |
| `/api/obstacle-map/reset` | POST | Limpiar mapa de obstáculos |

**Bridge externo:** `POST /api/sensors` recibe datos json desde la Raspberry Pi. Se cachean en `_external_sensor_data` con TTL de 30s. Todos los GET de telemetría y sensores verifican esta caché primero.

---

## 5. api/websocket.py — Tiempo Real

**Propósito:** Conexión bidireccional WebSocket. Broadcast de telemetría a 10 Hz y procesamiento de comandos.

### Conexión WebSocket

| Ruta | Descripción |
|------|-------------|
| `/ws/telemetry` | WS bidireccional. Recibe comandos JSON, envía telemetry 10Hz + command_ack |

**Manager de conexiones:** `ConnectionManager` mantiene set de websockets activos con locks por conexión.

### Comandos soportados (campo `type` en JSON)

| Comando | Acción |
|---------|--------|
| `ARM` / `DISARM` | Armar/desarmar motores + actualiza RC armed state |
| `TAKEOFF` | Despegar a altitud (m) |
| `LAND` | Aterrizar |
| `RTL` | Regreso a casa |
| `SET_MODE` | Cambiar modo de vuelo |
| `REBOOT` | Reiniciar autopiloto |
| `RC_CONTROL` | Control manual (throttle, yaw, pitch, roll normalizados) |
| `RC_RESET` | Resetear controles |
| `EMERGENCY` | STOP / RTL / LAND |
| `GOTO` | Navegar a coordenadas GPS absolutas |
| `GOTO_RELATIVE` | Navegar relativo a posición actual (forward/right/up) |
| `MISSION_UPLOAD` | Subir misión (waypoints absolutos) |
| `MISSION_UPLOAD_RELATIVE` | Subir misión relativa a posición actual |
| `START_MISSION` / `CLEAR_MISSION` | Iniciar/limpiar misión |
| `SAVE_WAYPOINTS` / `LOAD_WAYPOINTS` / `LIST_WAYPOINTS` | Persistencia de waypoints |
| `NAV_GOTO` / `NAV_MISSION` / `NAV_STOP` / `NAV_AVOIDANCE` | Navegación autónoma |
| `GET_SENSORS` | Datos de sensores |
| `GET_OBSTACLE_MAP` | Mapa de obstáculos |

**Failsafe:** Al desconectarse un cliente WS, se resetean los controles RC (seguridad).

---

## 6. api/camera_stream.py — Cámara y Visión

**Propósito:** Streaming de video, detección YOLOv8 + ArUco, y auto-evitación por visión.

### Clase `RealSenseCamera`

| Método | Descripción |
|--------|-------------|
| `start(width, height, fps)` | Abre dispositivo de video (prueba /dev/video{4,2,0,1,3,5}) |
| `stop()` | Cierra cámara y libera recursos |
| `get_frame()` | Último frame capturado (OpenCV) |
| `get_frame_with_overlay(telemetry)` | Frame con HUD: altitud, velocidad, batería, modo, crosshair |
| `_capture_loop()` | Thread daemon: captura frames → detect YOLO → draw overlay → auto-avoid |

**Streaming:**
| Ruta | Método | Descripción |
|------|--------|-------------|
| `/api/camera/ws` | WS | Frames JPEG base64 a 25 fps |
| `/api/camera/stream` | GET | MJPEG multipart a 30 fps (navegador) |
| `/api/camera/snapshot` | GET | JPEG individual |
| `/api/camera/start` | POST | Iniciar cámara |
| `/api/camera/stop` | POST | Detener cámara |
| `/api/camera/status` | GET | Estado (running, device, fps, detecciones) |
| `/api/camera/vision` | GET | Últimas detecciones YOLO/ArUco |
| `/api/camera/markers/{id}` | GET | Imagen de marcador ArUco |

**Auto-avoid:** Si visión detecta objeto en zona `"critical"` (distancia < 2m), llama callback de emergencia (BRAKE) con rate-limit de 3s.

---

## 7. sensors/ — Sensores Físicos

### base.py — Tipos Base

| Clase/Dataclass | Descripción |
|-----------------|-------------|
| `BaseSensor` (ABC) | Interfaz: `start()`, `stop()`, `read()`. Propiedades: `is_running`, `status` |
| `SensorReading` | `timestamp`, `valid` |
| `DistanceReading(SensorReading)` | + `distance_m` |
| `LidarPoint` | `angle_deg`, `distance_m`, `quality` |
| `LidarScan(SensorReading)` | + `points: list[LidarPoint]`, `min_angle`, `max_angle` |

### mtf01.py — Ultrasonido MTF01

- **I2C:** dirección `0x57`, rango 2-400 cm, precisión ±1 cm, tasa 20 Hz
- **Modo real:** lectura raw 2 bytes → `raw / 58.0` → centímetros → metros
- **Modo sim:** distancia sinusoidal (1.5 m ± 1.0 m, 0.3 rad/s)

### ydlidar_x4.py — LIDAR YDLIDAR X4

- **Serial:** 115200 baud, 720 puntos/scan, 360°
- **Modo real:** lee 2000 bytes, parsea 5-byte packets (angle/64, distance mm, quality)
- **Circuit breaker:** 10 errores consecutivos → `_is_dead`, reintenta cada 5s
- **Modo sim:** 720 puntos sinusoidales + 4 obstáculos simulados

### obstacle_map.py — Mapa de Obstáculos 2D

- Grid 20×20 metros, resolución 0.2 m (100×100 celdas), dron en el centro
- `update_from_lidar()`: transforma puntos LIDAR según yaw, incrementa ocupación (+0.3), limpia rayo (-0.1)
- `update_from_ultrasonic()`: actualiza desde MTF01 frontal
- `find_free_direction()`: prueba ángulos [0, ±30, ±60, ±90, ±120, 180]° desde heading actual
- `decay(0.99)`: reduce ocupación cada tick para olvidar obstáculos viejos

### manager.py — Orquestador de Sensores

- Loop a 20 Hz (0.05s sleep): lee MTF01 + LIDAR → actualiza obstacle map → decay
- `set_drone_yaw()`: registra heading actual (llamado desde navigation)
- `has_obstacle_ahead`: MTF01 < 2m OR LIDAR front zone (45° FOV, 2m max)

---

## 8. vision/detector.py — Detector YOLOv8 + ArUco

**Propósito:** Detección de objetos con YOLOv8n, estimación de distancia monocular, clasificación en zonas de seguridad.

**Constantes importantes:**
- `FOCAL_LENGTH_ESTIMATE = 184.0` — para estimación de distancia
- `SAFE_DISTANCE > 5m`, `WARNING 2-5m`, `CRITICAL < 2m`
- `KNOWN_HEIGHTS`: 80 clases COCO con altura promedio en metros

**Clase `VisionDetector`:**
- Carga `yolov8n.pt` en thread background (no bloquea startup)
- `detect(frame)`: inference a 640px, confidence 0.4, devuelve lista de `Detection`
- `draw_overlay(frame, detections)`: bounding boxes color-coded (verde/naranja/rojo) + label + distancia + zona
- `get_status()`: detecciones actuales, count, critical_count

---

## 9. navigation/ — Navegación Autónoma

### avoidance.py — Evaluación de Obstáculos

- `evaluate(sensor_data)`: usa datos de sensor (MTF01, LIDAR, safe_direction)
- Si distancia ≤ `brake_distance` (1m) + cooldown 3s → `BRAKE`
- Si distancia ≤ `safety_distance` (2m) → `AVOID` con ángulo de giro
- Si no → `NONE`

### planner.py — Planificador de Rutas

- `plan_to_waypoint(start, target, obstacle_map)`: interpola waypoints cada 2m, evita obstáculos desviando 2m en dirección libre
- `plan_search_pattern(center, radius, spacing)`: patrón espiral concéntrico (máx 50 waypoints)

### controller.py — Controlador de Navegación

- `_nav_loop()` a 5 Hz (0.2s): lee sensores → evalúa obstáculos → ejecuta paso de navegación/misión
- Modos: `IDLE`, `NAVIGATING`, `MISSION`, `AVOIDING`
- `_execute_navigation_step()`: calcula distancia haversine, envía `mav.goto()`
- `_execute_mission_step()`: itera waypoints, verifica llegada (radio 2m)

---

## 10. db/ — Base de Datos

| Archivo | Propósito |
|---------|-----------|
| `database.py` | Engine SQLAlchemy con `pool_pre_ping=True`, SessionLocal |
| `models.py` | Modelo `Telemetry`: id, altitude, speed, pitch, roll, yaw, battery, timestamp |
| `repository.py` | `save_telemetry(data)`: inserta snapshot en BD |

**Nota:** La persistencia a BD es opcional — el sistema funciona sin PostgreSQL.

---

## 11. Notas de Revisión Técnica

### Problemas conocidos con wait_ack

`wait_ack` (conn.wait_ack) usado en arm/disarm/takeoff:
- Si el read loop no procesó el COMMAND_ACK, `wait_ack` espera hasta timeout → el comando se bloquea

### get_current_mode con blocking

`get_current_mode` usa `recv_match(blocking=True, timeout=2)` — bloquea hasta 2s.

### Cadena de esperas en takeoff

`takeoff()` → llama `arm()` → `wait_ack(ARM)` → `wait_ack(TAKEOFF)` — cadena de esperas si algo falla.

### Causas de fallo en wait_ack / recv_match (aun con conexión)

1. `_read_loop` no corre o está pausado (`_pause_read` seteado)
2. HEARTBEAT/ACKs no llegan al buffer (sysid/compid incorrecto)
3. `save_telemetry()` pesado retrasa el procesamiento
4. Reasignación accidental de `conn` o `telemetry`

### Por qué el sistema "reconecta" estando conectado

Si `telemetry.data['armed']` queda en `False` (read loop no procesó HEARTBEAT a tiempo), código que depende de `is_armed()` puede reiniciar conexiones o mostrar reconexión en UI.

### Diagnóstico recomendado

- Logs DEBUG: "COMMAND_ACK stored", "wait_ack timeout", HEARTBEAT procesado
- Verificar `_read_loop` vivo: dump de hilos con `faulthandler`
- Añadir logger.debug en `_process_message` bloque HEARTBEAT para armed/mode
- Inspeccionar `conn._pending_ack` en runtime

### Cambios recomendados

1. `_is_armed`: usar `recv_match_protected` como fallback en vez de `recv_match` non-blocking
2. Evitar `blocking=True` innecesario en caminos críticos
3. `_is_armed` más robusto: (1) cache telemetry → (2) recv_match_protected(HEARTBEAT, 0.2s) → (3) False
