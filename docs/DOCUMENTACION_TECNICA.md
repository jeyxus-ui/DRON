# Documentación Técnica — Sistema de Control de Dron

## Versión: 1.0.0
## Fecha: Mayo 2026

---

# Índice

1. [Resumen del Proyecto](#1-resumen-del-proyecto)
2. [Arquitectura General](#2-arquitectura-general)
3. [Backend (FastAPI + MAVLink)](#3-backend-fastapi--mavlink)
   - 3.1 Estructura del Backend
   - 3.2 Configuración (`config.py`)
   - 3.3 Punto de Entrada (`main.py`)
   - 3.4 API REST (`api/rest.py`)
   - 3.5 WebSocket (`api/websocket.py`)
   - 3.6 Cámara Streaming (`api/camera_stream.py`)
   - 3.7 Conexión MAVLink (`mavlink/connection.py`)
   - 3.8 Controlador MAVLink (`mavlink/controller.py`)
   - 3.9 Comandos (`mavlink/commands.py`)
   - 3.10 Override RC (`mavlink/rc_override.py`)
   - 3.11 Telemetría (`mavlink/telemetry.py`)
   - 3.12 Base de Datos (`db/`)
4. [App Móvil (React Native)](#4-app-móvil-react-native)
   - 4.1 Estructura del Móvil
   - 4.2 Configuración de Red (`config.ts`)
   - 4.3 Contexto de Estado (`DroneContext.tsx`)
   - 4.4 Pantalla de Control (`DroneControlScreen.tsx`)
   - 4.5 Pantalla GPS/Mapa (`GPSScreen.tsx`)
   - 4.6 Pantalla Waypoints (`WaypointScreen.tsx`)
   - 4.7 Pantalla Telemetría (`TelemetryScreen.tsx`)
   - 4.8 Componentes UI
5. [Simulación ArduPilot SITL](#5-simulación-ardupilot-sitl)
6. [Frontend Web (Next.js)](#6-frontend-web-nextjs)
7. [Raspberry Pi Companion](#7-raspberry-pi-companion)
8. [Dockerización](#8-dockerización)
9. [Protocolo de Comunicación WebSocket](#9-protocolo-de-comunicación-websocket)
10. [Guía de Despliegue](#10-guía-de-despliegue)
11. [Solución de Problemas](#11-solución-de-problemas)
12. [Referencia de API Completa](#12-referencia-de-api-completa)

---

# 1. Resumen del Proyecto

Sistema integral de control de drones que permite operar un vehículo aéreo no tripulado (UAV) mediante:

- **App móvil React Native** con interfaz estilo militar/futurista tipo DJI
- **Backend FastAPI** en Python que sirve como puente entre la app y el dron
- **MAVLink** como protocolo de comunicación con el autopiloto (Pixhawk/ArduPilot)
- **Simulación ArduPilot SITL** para desarrollo sin hardware físico
- **WebSocket** para telemetría en tiempo real y envío de comandos
- **Transmisión de video** desde cámara a bordo (RealSense / cámara USB)
- **Gestión de waypoints** con categorías y navegación autónoma

## Propósito

El sistema permite:

- Control manual del dron mediante joysticks virtuales (modo 2: THR/YAW izq, PITCH/ROLL der)
- Visualización de telemetría en tiempo real (altitud, velocidad, batería, GPS, actitud)
- Navegación autónoma por waypoints (GOTO, MISSION_UPLOAD, START_MISSION)
- Visualización de mapa satelital con posición del dron y waypoints
- Transmisión de video en vivo desde la cámara del dron
- Modo demo offline para pruebas sin conexión al backend
- Visualización de horizonte artificial (actitud 3D)
- Emergencias: STOP (BRAKE/LOITER), RTL (Return to Launch), LAND, KILL (motores)

---

# 2. Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ARQUITECTURA DEL SISTEMA                      │
└─────────────────────────────────────────────────────────────────────┘

                            ┌──────────────────┐
                            │   App Móvil       │
                            │   React Native    │
                            │   (Android APK)   │
                            └────────┬─────────┘
                                     │ WS + HTTP
                                     │
                            ┌────────▼─────────┐
                            │   Backend         │
                            │   FastAPI         │
                            │   0.0.0.0:8000    │
                            │                   │
                   ┌────────┴─────────┬────────┴────────┐
                   │                  │                  │
            ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
            │  MAVLink     │   │  Cámara     │   │  DB         │
            │  Controller  │   │  Streaming  │   │  PostgreSQL │
            │  (SIM/Real)  │   │  (MJPEG/WS) │   │  (Historial)│
            └──────┬───────┘   └─────────────┘   └─────────────┘
                   │ MAVLink (TCP/UDP/Serial)
                   │
            ┌──────▼───────┐
            │  Autopiloto   │
            │  ┌─────────┐ │
            │  │ Pixhawk  │ │  (Hardware real)
            │  │  o       │ │
            │  │ ArduPilot│ │  (SITL simulado)
            │  │  SITL    │ │
            │  └─────────┘ │
            └──────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                        FLUJO DE DATOS                                │
└─────────────────────────────────────────────────────────────────────┘

  SITL/Pixhawk                  Backend                       App Móvil
  ────────────                  ───────                       ────────
       │                          │                              │
       │── MAVLink (TCP/UDP) ──▶  │                              │
       │   HEARTBEAT              │                              │
       │   VFR_HUD               │                              │
       │   GPS_RAW_INT           │                              │
       │   ATTITUDE              │                              │
       │   BATTERY_STATUS        │                              │
       │   SYS_STATUS            │                              │
       │                          │                              │
       │                          │── WebSocket (JSON) ──────▶  │
       │                          │   telemetry @ 10Hz          │
       │                          │                              │
       │                          │◀── WebSocket (JSON) ─────── │
       │                          │   ARM, TAKEOFF, GOTO,       │
       │◀── MAVLink Cmd ──────── │   MISSION_UPLOAD, etc.      │
       │   COMMAND_LONG          │                              │
       │   MISSION_ITEM          │                              │
```

---

# 3. Backend (FastAPI + MAVLink)

## 3.1 Estructura del Backend

```
backend/
├── __init__.py
├── .env                          # Variables de entorno locales
├── config.py                     # Configuración central (MAVLink, API, DB)
├── main.py                       # Punto de entrada FastAPI
├── requirements.txt              # Dependencias Python
├── requirements_camera.txt       # Dependencias de cámara
├── create_tables.py              # Creación de tablas DB
├── run_with_device.py            # Runner con device personalizado
├── start_api_sim.py              # Runner modo simulado
├── Dockerfile                    # Build imagen Docker
├── api/
│   ├── __init__.py
│   ├── rest.py                   # Endpoints REST
│   ├── websocket.py              # Endpoint WebSocket
│   └── camera_stream.py          # Streaming de cámara (RealSense/USB)
├── mavlink/
│   ├── __init__.py
│   ├── connection.py             # Conexión MAVLink (serial/UDP/TCP)
│   ├── controller.py             # Controlador de alto nivel
│   ├── commands.py               # Comandos específicos MAVLink
│   ├── rc_override.py            # Override de canales RC
│   ├── telemetry.py              # Procesamiento de telemetría
│   └── sim_test.py               # Test del simulador
├── db/
│   ├── __init__.py
│   ├── database.py               # Conexión SQLAlchemy
│   ├── models.py                 # Modelos ORM
│   └── repository.py             # Operaciones de base de datos
├── schemas/
│   ├── __init__.py
│   └── telemetry.py              # Schemas Pydantic (vacío / pendiente)
└── tests/
    ├── run_config_tests.py       # Tests de detección MAVLink
    ├── test_config.py            # Tests pytest de configuración
    └── test_endpoints.py         # Tests de endpoints
```

## 3.2 Configuración (`config.py`)

El archivo `backend/config.py` centraliza toda la configuración del backend.

### Variables de Entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MAVLINK_DEVICE` | `tcp:172.28.252.91:5760` | Dispositivo MAVLink: `SIM`, `tcp:<ip>:<port>`, `udp:<ip>:<port>`, o ruta serial (`/dev/ttyACM0`) |
| `MAVLINK_BAUD` | `115200` | Baud rate para conexión serial |
| `API_HOST` | `0.0.0.0` | Host del servidor API |
| `API_PORT` | `8000` | Puerto del servidor API |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `DB_URL` | `postgresql://dronix_user:DronixSecure2024!@postgres:5432/drones` | Conexión PostgreSQL |

### Auto-detección de MAVLink

La función `detect_mavlink_device()` sigue esta prioridad:

1. **Variable de entorno** `MAVLINK_DEVICE`:
   - `SIM` → simulador interno
   - `tcp:ip:puerto` o `udp:ip:puerto` → conexión remota
   - Ruta absoluta → dispositivo serial
2. **Auto-detección**: prueba candidatos (`/dev/ttyACM0`, `/dev/ttyUSB0`, nombres persistentes en `/dev/serial/by-id/`)
3. **Fallback**: modo `SIM`

```python
# Ejemplos de configuración MAVLINK_DEVICE:
# Hardware real:   /dev/ttyACM0
# Radio telemetría: /dev/ttyUSB0
# SITL local:      tcp:127.0.0.1:5760
# SITL WSL2:       tcp:172.28.252.91:5760
# Simulado:        SIM
```

## 3.3 Punto de Entrada (`main.py`)

El archivo `backend/main.py` crea la aplicación FastAPI y gestiona el ciclo de vida.

### Inicialización (Startup)

```python
# Orden de inicialización en startup:
1. Detectar dispositivo MAVLink (detect_mavlink_device)
2. Inicializar MAVController (rest.init_mav)
3. Iniciar monitoreo de conexión (rest.start_monitoring)
4. Iniciar cámara RealSense/USB (camera_stream.camera.start)
5. Iniciar broadcast WebSocket (websocket.start_telemetry_broadcast)
```

### Endpoints del sistema

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Información de la API |
| GET | `/health` | Health check |
| GET | `/drones` | Lista de drones (mock) |
| GET | `/missions` | Lista de misiones (mock) |
| GET | `/users` | Lista de usuarios (mock) |
| GET | `/flight-routes` | Rutas de vuelo (mock) |

## 3.4 API REST (`api/rest.py`)

Endpoints RESTful para control del dron.

### Estados y Telemetría

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/status` | Estado general: connected, armed, mode, system_status |
| GET | `/api/telemetry` | Telemetría completa: altitud, GPS, actitud, batería, velocidad, satélites, HDOP |

**Respuesta de `/api/status`:**
```json
{
  "connected": true,
  "armed": false,
  "mode": "STABILIZE",
  "system_status": "STANDBY"
}
```

**Respuesta de `/api/telemetry`:**
```json
{
  "armed": false,
  "mode": "STABILIZE",
  "altitude": 0.0,
  "latitude": -33.4489,
  "longitude": -70.6693,
  "roll": 0.0,
  "pitch": 0.0,
  "yaw": 0.0,
  "battery_voltage": 12.6,
  "battery_remaining": 100,
  "ground_speed": 0.0,
  "vertical_speed": 0.0,
  "satellites": 10,
  "hdop": 0.8
}
```

### Control Básico

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| POST | `/api/arm` | `{ "force": false }` | Armar motores |
| POST | `/api/disarm` | - | Desarmar motores |
| POST | `/api/takeoff` | `{ "altitude": 10 }` | Despegue (2-100m) |
| POST | `/api/land` | - | Aterrizar |
| POST | `/api/rtl` | - | Return to Launch |

### Control RC

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| POST | `/api/rc/control` | `{ throttle, yaw, pitch, roll }` | Enviar valores RC normalizados |
| POST | `/api/rc/reset` | - | Resetear controles RC |
| GET | `/api/rc/values` | - | Valores actuales RC |

Todos los valores RC se esperan **normalizados**:
- `throttle`: 0.0 a 1.0
- `yaw`: -1.0 a 1.0
- `pitch`: -1.0 a 1.0
- `roll`: -1.0 a 1.0

### Emergencias

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| POST | `/api/emergency` | `{ "action": "STOP" }` | Acciones: STOP, RTL, LAND, KILL |

- **STOP**: Intenta BRAKE primero; si falla (sin GPS), cae a LOITER. Resetea RC.
- **RTL**: Return to Launch.
- **LAND**: Aterrizaje de emergencia.
- **KILL**: Detención inmediata de motores (peligroso, solo emergencia real).

### Modos de Vuelo

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| POST | `/api/mode` | `{ "mode": "GUIDED" }` | Cambiar modo de vuelo |

**Modos válidos:** STABILIZE, ACRO, SPORT, DRIFT, ALT_HOLD, POSHOLD, LOITER, BRAKE, AUTO, GUIDED, CIRCLE, FLIP, THROW, RTL, SMARTRTL, LAND.

### Navegación

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| POST | `/api/goto` | `{ latitude, longitude, altitude }` | Navegar a coordenada |

## 3.5 WebSocket (`api/websocket.py`)

Endpoint WebSocket en `/ws/telemetry` para comunicación bidireccional en tiempo real.

### ConnectionManager

Gestiona múltiples conexiones WebSocket concurrentes:

```python
class ConnectionManager:
    - active_connections: Set[WebSocket]
    - _locks: dict[websocket_id, asyncio.Lock]  # Previene escrituras concurrentes
    - telemetry_task: reference a tarea de broadcast
    - connect(websocket): Acepta conexión
    - disconnect(websocket): Elimina conexión
    - send(websocket, message): Envío thread-safe por conexión
    - broadcast(message): Envía a todas las conexiones activas
```

### Broadcast de Telemetría

- Frecuencia: **10 Hz** (cada 100ms)
- Tarea asíncrona en background iniciada en startup
- Extrae datos del MAVController (real o simulado)
- Broadcast en formato JSON a todos los clientes conectados

### Procesamiento de Comandos

La función `process_command()` maneja todos los comandos entrantes:

```python
# Comandos soportados:
CMD_ARM             → mav_controller.arm()
CMD_DISARM          → mav_controller.disarm()
CMD_TAKEOFF         → mav_controller.takeoff(altitude)
CMD_LAND            → mav_controller.land()
CMD_RTL             → mav_controller.return_to_launch()
CMD_SET_MODE        → mav_controller.set_mode(mode)
CMD_REBOOT          → mav_controller.cmd.reboot_autopilot()
CMD_RC_CONTROL      → mav_controller.rc.set_controls(throttle, yaw, pitch, roll)
CMD_RC_RESET        → mav_controller.rc.reset_controls()
CMD_EMERGENCY       → STOP/RTL/LAND/KILL
CMD_GOTO            → mav_controller.goto(lat, lon, alt)
CMD_MISSION_UPLOAD  → mav_controller.upload_mission(waypoints)
CMD_START_MISSION   → mav_controller.start_mission()
CMD_CLEAR_MISSION   → mav_controller.clear_mission()
```

Los comandos `RC_CONTROL` y `RC_RESET` **no generan ACK** (se envían a 10Hz y saturarían el canal). Todos los demás reciben un `command_ack`.

### Flujo de Mensajes WebSocket

```
Cliente → Servidor:
{
  "type": "ARM",                    # Tipo de comando
  "params": { "force": false }      # Parámetros (opcional)
}

Servidor → Cliente (telemetría):
{
  "type": "telemetry",
  "data": { ... },                  # Objeto Telemetry completo
  "timestamp": "2026-05-09T22:49:50"
}

Servidor → Cliente (ACK):
{
  "type": "command_ack",
  "command": "ARM",
  "result": { "success": true, "message": "Drone armado" },
  "timestamp": "2026-05-09T22:49:50"
}
```

## 3.6 Cámara Streaming (`api/camera_stream.py`)

Transmisión de video desde cámara a bordo del dron.

### Clase RealSenseCamera

- Soporta cámaras Intel RealSense y cámaras USB genéricas
- Auto-detección de dispositivos de video (`/dev/video4,2,0,1,3,5`)
- Captura en resolución configurable (default: 640x480 @ 30fps)

### Endpoints de Cámara

| Método | Ruta | Descripción |
|--------|------|-------------|
| WS | `/api/camera/ws` | Frames base64 JPEG a 25fps por WebSocket |
| GET | `/api/camera/stream` | Streaming MJPEG |
| GET | `/api/camera/view` | Visor HTML simple |
| GET | `/api/camera/snapshot` | Captura instantánea JPEG |
| POST | `/api/camera/start` | Iniciar cámara |
| POST | `/api/camera/stop` | Detener cámara |
| GET | `/api/camera/status` | Estado de la cámara |

### HUD Overlay

La transmisión de video incluye un HUD superpuesto con:
- Altitud (escala vertical izquierda)
- Velocidad horizontal
- Batería (porcentaje + ícono)
- Modo de vuelo
- Estado de armado
- Crosshair central

## 3.7 Conexión MAVLink (`mavlink/connection.py`)

Clase `MAVLinkConnection` — maneja la conexión de bajo nivel con el autopiloto.

### Tipos de Conexión Soportados

| Tipo | Formato | Ejemplo |
|------|---------|---------|
| Serial | Ruta de dispositivo | `/dev/ttyACM0` |
| TCP | `tcp:<ip>:<puerto>` | `tcp:172.28.252.91:5760` |
| UDP | `udp:<ip>:<puerto>` | `udp:127.0.0.1:14550` |

### Características

- **Conexión con reintento**: exponential backoff (1s, 2s, 4s, 8s... hasta 30s máx)
- **Envío thread-safe**: `send_command()` con Lock
- **Lectura sin lock**: `recv_match()` para evitar deadlock con `wait_ack()`
- **Espera de ACK**: `wait_ack()` verifica COMMAND_ACK después de comandos
- **Auto-reconexión**: thread background que monitorea y reconecta con backoff configurable

```python
class MAVLinkConnection:
    def connect(self, device: str, baud: int) -> bool
    def disconnect(self)
    def is_connected(self) -> bool
    def send_command(self, msg) -> bool       # Thread-safe
    def recv_match(self, **kwargs) -> Message  # Sin lock
    def wait_ack(self, command, timeout=5) -> bool
```

## 3.8 Controlador MAVLink (`mavlink/controller.py`)

Clase `MAVController` — capa de abstracción de alto nivel.

### Constructor

```python
MAVController(device: str = "SIM", baud: int = 115200)
```

- `device = "SIM"` → usa `_SimulatedController` (simulador interno)
- Otros valores → delega en `MAVLinkConnection`, `DroneCommands`, `DroneTelemetry`, `RCOverrideController`

### Métodos Públicos

| Método | Descripción |
|--------|-------------|
| `arm()` | Armar motores |
| `disarm(force=False)` | Desarmar motores |
| `set_mode(mode)` | Cambiar modo de vuelo |
| `takeoff(altitude)` | Despegar a altitud especificada |
| `land()` | Aterrizar |
| `return_to_launch()` | RTL |
| `goto_position(lat, lon, alt)` | Navegar a coordenadas |
| `kill_motors()` | Detener motores inmediatamente (KILL) |
| `set_param(name, value)` | Cambiar parámetro del autopiloto |
| `get_param(name)` | Leer parámetro del autopiloto |
| `upload_mission(waypoints)` | Subir misión de waypoints |
| `start_mission()` | Iniciar misión (cambia a modo AUTO) |
| `clear_mission()` | Limpiar misión actual |
| `get_flight_logs()` | Obtener logs de vuelo |
| `is_armed()` | Estado de armado |
| `is_connected()` | Estado de conexión |
| `get_mode()` | Modo actual |
| `get_system_status()` | Estado del sistema |

### Simulador Interno (`_SimulatedController`)

Cuando `device = "SIM"`, se utiliza un simulador básico que:
- Simula armado/desarmado
- Aumenta/reduce altitud cuando armado + modo GUIDED
- Drena batería lentamente
- Simula coordenadas GPS (Santiago de Chile: -33.4489, -70.6693)
- Responde a todos los comandos con datos simulados

## 3.9 Comandos (`mavlink/commands.py`)

Clase `DroneCommands` — implementación de comandos MAVLink específicos.

### Comandos Implementados

| Método | MAV_CMD | Descripción |
|--------|---------|-------------|
| `arm(force=False)` | `MAV_CMD_COMPONENT_ARM_DISARM` | Armar (force=true omite chequeos de seguridad) |
| `disarm(force=False)` | `MAV_CMD_COMPONENT_ARM_DISARM` | Desarmar |
| `set_mode(mode_name)` | `MAV_CMD_DO_SET_MODE` | lookup en `mode_mapping` |
| `takeoff(altitude)` | `MAV_CMD_NAV_TAKEOFF` | Set GUIDED + arm + takeoff |
| `land()` | `MAV_CMD_NAV_LAND` | Aterrizar |
| `rtl()` | `MAV_CMD_NAV_RETURN_TO_LAUNCH` | Regresar a home (set_mode RTL) |
| `loiter()` | `MAV_CMD_NAV_LOITER_UNLIM` | set_mode LOITER |
| `goto_position(lat, lon, alt)` | `SET_POSITION_TARGET_GLOBAL_INT` | Navegación a coordenada |
| `set_velocity(vx, vy, vz, yaw_rate)` | `SET_POSITION_TARGET_LOCAL_NED` | Control por velocidad |
| `emergency_stop()` | - | RTL → LAND → force disarm |
| `kill_motors()` | `MAV_CMD_COMPONENT_ARM_DISARM` | Force disarm (KILL) |
| `reboot_autopilot()` | `MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN` | Reboot autopiloto |
| `get_current_mode()` | - | Desde HEARTBEAT |

### Mode Mapping

ArduPilot soporta múltiples modos. El mapeo numérico sigue la convención estándar de ArduPilot:

| Modo | ID | Descripción |
|------|----|-------------|
| STABILIZE | 0 | Estabilización básica |
| ACRO | 1 | Acrobático |
| ALT_HOLD | 2 | Mantener altitud |
| AUTO | 3 | Misión autónoma |
| GUIDED | 4 | Guiado externo |
| LOITER | 5 | Vuelo estacionario |
| RTL | 6 | Return to Launch |
| CIRCLE | 7 | Orbitar |
| LAND | 9 | Aterrizar |
| DRIFT | 11 | Drift |
| SPORT | 13 | Sport |
| FLIP | 14 | Flip |
| POSHOLD | 16 | Posición fija |
| BRAKE | 17 | Frenado |
| THROW | 18 | Lanzamiento |
| SMARTRTL | 21 | Smart RTL |

## 3.10 Override RC (`mavlink/rc_override.py`)

Clase `RCOverrideController` — permite control manual del dron overrideando canales RC.

### Canales RC

| Canal | Eje | Rango Normalizado | Rango PWM |
|-------|-----|-------------------|-----------|
| 0 | Roll | -1.0 a 1.0 | 1000-2000 |
| 1 | Pitch | -1.0 a 1.0 | 1000-2000 |
| 2 | Throttle | 0.0 a 1.0 | 1000-2000 |
| 3 | Yaw | -1.0 a 1.0 | 1000-2000 |

### Mecanismo

- Hilo background que envía `RC_CHANNELS_OVERRIDE` a **10 Hz**
- `set_controls(throttle, yaw, pitch, roll)`: actualiza valores normalizados
- `reset_controls()`: envía PWM=0 en todos los canales (cede control al piloto RC real)

## 3.11 Telemetría (`mavlink/telemetry.py`)

Clase `DroneTelemetry` — procesa mensajes MAVLink entrantes y extrae datos de telemetría.

### Flujo de Procesamiento

1. Hilo background de lectura a **100 Hz**
2. Solicita streams de datos al Pixhawk en startup (`MAV_CMD_SET_MESSAGE_INTERVAL`)
3. Procesa mensajes:

| Mensaje MAVLink | Datos Extraídos |
|-----------------|-----------------|
| `VFR_HUD` | Altitud, velocidad horizontal, climb rate, throttle |
| `GPS_RAW_INT` | Latitud, longitud, altitud MSL, satélites, HDOP |
| `BATTERY_STATUS` | Voltaje, corriente, porcentaje restante |
| `SYS_STATUS` | Estado del sistema, sensores |
| `ATTITUDE` | Roll, pitch, yaw (grados) |
| `HEARTBEAT` | Armado, modo, system_status |
| `HOME_POSITION` | Posición de home |

### Persistencia

- Hilo separado guarda snapshots en PostgreSQL a intervalo configurable (default: 5s)
- Tabla `telemetry`: id, altitude, speed, pitch, roll, yaw, battery, timestamp

### Preflight Checks

```python
def preflight_checks() -> list[str]:
    - GPS fix (satélites >= 6)
    - Batería (voltaje > 11.0V)
    - EKF (estimador Kalman)
    - Home position definida
    - Sensores OK
```

## 3.12 Base de Datos (`db/`)

### Esquema

**Tabla `telemetry`:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | Integer (PK) | Auto-increment |
| altitude | Float | Altitud actual (m) |
| speed | Float | Velocidad horizontal (m/s) |
| pitch | Float | Pitch (grados) |
| roll | Float | Roll (grados) |
| yaw | Float | Yaw (grados) |
| battery | Float | Voltaje batería (V) |
| timestamp | TIMESTAMP | Marca de tiempo |

### Configuración por Defecto

```yaml
Base de datos: drones
Usuario: dronix_user
Contraseña: DronixSecure2024!
Puerto: 5432
Host (Docker): postgres
Host (local): localhost
```

---

# 4. App Móvil (React Native)

## 4.1 Estructura del Móvil

```
mobile/
├── App.tsx                          # Componente raíz con navegación
├── index.js                         # Punto de entrada
├── app.json                         # Configuración de la app
├── package.json                     # Dependencias
├── tsconfig.json                    # Configuración TypeScript
├── babel.config.js                  # Babel
├── metro.config.js                  # Metro bundler
├── jest.config.js                   # Jest testing
├── .eslintrc.js                     # ESLint
├── .prettierrc.js                   # Prettier
├── Gemfile                          # Ruby gems (iOS)
├── src/
│   ├── config.ts                    # Configuración de red
│   ├── context/
│   │   └── DroneContext.tsx          # Contexto global de estado
│   ├── screens/
│   │   ├── DroneControlScreen.tsx   # Pantalla principal de control
│   │   ├── GPSScreen.tsx            # Pantalla de mapa GPS
│   │   ├── WaypointScreen.tsx       # Gestión de waypoints
│   │   └── TelemetryScreen.tsx      # Telemetría detallada
│   └── components/
│       ├── Joystick.tsx             # Joystick virtual animado
│       ├── StatusBar.tsx            # Barra de estado superior
│       └── TacticalButton.tsx       # Botón táctico reutilizable
├── __tests__/
│   └── App.test.tsx                 # Test de snapshot
├── android/                         # Proyecto Android nativo
└── ios/                             # Proyecto iOS nativo
```

## 4.2 Configuración de Red (`config.ts`)

```typescript
// mobile/src/config.ts
const HOST_IP = '192.168.20.38';

export const API_URL = `http://${HOST_IP}:8000`;
export const WS_URL = `ws://${HOST_IP}:8000/ws/telemetry`;
```

**Estrategia de conexión según entorno:**

| Entorno | HOST_IP | Método |
|---------|---------|--------|
| BlueStacks (misma PC) | IP LAN del host (ej: 192.168.20.38) | WiFi directo |
| Emulador Android estándar | `localhost` | ADB reverse |
| Dispositivo físico misma red | IP LAN del servidor | WiFi |

**ADB Reverse** (para emulador estándar):
```bash
adb reverse tcp:8000 tcp:8000
```

## 4.3 Contexto de Estado (`DroneContext.tsx`)

Provider de React Context que maneja todo el estado global de la aplicación.

### Estados

| Estado | Tipo | Default | Descripción |
|--------|------|---------|-------------|
| `telemetry` | `Telemetry` | DEFAULT_TELEMETRY | Datos de telemetría del dron |
| `connected` | `boolean` | `false` | Conexión WebSocket activa |
| `demoMode` | `boolean` | `false` | Modo demo offline activo |

### Interfaz Telemetry

```typescript
interface Telemetry {
  armed:              boolean;   // Motores armados
  mode:               string;    // Modo de vuelo (GUIDED, AUTO, etc.)
  altitude:           number;    // Altitud en metros
  latitude:           number;    // Latitud GPS
  longitude:          number;    // Longitud GPS
  roll:               number;    // Roll en grados
  pitch:              number;    // Pitch en grados
  yaw:                number;    // Yaw en grados
  battery_voltage:    number;    // Voltaje de batería
  battery_remaining:  number;    // Porcentaje de batería restante
  ground_speed:       number;    // Velocidad horizontal (m/s)
  vertical_speed:     number;    // Velocidad vertical (m/s)
  satellites:         number;    // Satélites GPS visibles
  hdop:               number;    // Precisión GPS (HDOP)
}
```

### Funciones Expuestas

| Función | Descripción |
|---------|-------------|
| `sendCommand(type, params)` | Enviar comando al backend, retorna `Promise<CommandResult>` |
| `armDrone()` | Armar motores |
| `disarmDrone()` | Desarmar motores |
| `takeoff(altitude)` | Despegar (altitud en metros) |
| `land()` | Aterrizar |
| `emergency(action)` | Emergencia: 'STOP', 'RTL', 'LAND' |
| `setJoystick(throttle, yaw, pitch, roll)` | Valores RC normalizados |

### Manejo de Conexión WebSocket

```typescript
// Flujo de conexión:
1. useEffect en mount → connectWebSocket()
2. fallbackTimer de 5s → si no hay conexión, activa modo demo
3. onopen → setConnected(true), stopDemo()
4. onmessage → actualiza telemetría o procesa command_ack
5. onerror → setConnected(false), startDemo()
6. onclose → setConnected(false), reconecta en 3s
7. RC Heartbeat → envía RC_CONTROL cada 100ms si conectado
```

### Modo Demo (Offline)

- Se activa automáticamente si no hay conexión WebSocket después de 5s
- También se activa en `onerror` y `onclose`
- Simula telemetría realista usando funciones senoidales:
  - Altitud: `10 + 5 * sin(t * 0.1)` cuando armado
  - Velocidad: `8 + 4 * sin(t * 0.05)` cuando armado
  - Posición GPS: órbita alrededor del origen (Santiago, Chile)
  - Actitud: variaciones senoidales de roll/pitch/yaw
  - Batería: descarga lineal cuando armado
  - Satélites: 10-15, aleatorio
- Maneja todos los comandos localmente (ARM, TAKEOFF, GOTO, MISSION_UPLOAD, etc.)

### Sistema de Comandos con Timeout

```typescript
sendCommand(type, params) → Promise<CommandResult>
  - Timeout: 5 segundos
  - Sin ACK para RC_CONTROL y RC_RESET
  - Mapa de comandos pendientes para correlacionar ACKs
```

## 4.4 Pantalla de Control (`DroneControlScreen.tsx`)

Pantalla principal con interfaz de piloto estilo DJI militar.

### Layout

```
┌──────────────────────────────────────┐
│  StatusBar: [ON●LINE] [GUIDED] [ARM] │  ← Componente StatusBar
├──────────────────────────────────────┤
│                                      │
│  ┌─ Panel ─┐        ┌──── HUD ────┐ │
│  │ Conect.  │        │ CAM         │ │
│  │ Modo     │        │ SPD  12.4   │ │
│  │ Acciones │        │ ALT  15.0   │ │
│  │ Batería  │        │ BAT%  87    │ │
│  └──────────┘        │ SAT  12     │ │
│                      │ YAW  045°   │ │
│                      │ V/S  +1.2   │ │
│                      └─────────────┘ │
│                                      │
│  ┌── Video Feed (WebView MJPEG) ──┐  │
│  │  ┌─────────── HUD ───────────┐ │  │
│  │  │ Alt: 15.2m  SPD: 12.4    │ │  │
│  │  │ Bat: 87%   MODE: GUIDED  │ │  │
│  │  │        ✛                  │ │  │
│  │  │    [Barra de altitud]     │ │  │
│  │  └───────────────────────────┘ │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌─── Joystick Izq ──┐ ┌─── Joy Der┐│
│  │   THR (arriba)     │ │ PITCH     ││
│  │   YAW (abajo)      │ │ ROLL      ││
│  │    [THR: ++++]     │ │           ││
│  └────────────────────┘ └───────────┘│
│                                      │
│  [ARM] [TAKEOFF] [LAND]    [SOS]    │  ← Botones tácticos
└──────────────────────────────────────┘
```

### Componentes Internos

**Video Feed (WebView):**
- URL: `{API_URL}/api/camera/view`
- HUD superpuesto con valores de telemetría
- Barra de altitud vertical animada
- Crosshair central

**Joysticks:**
- Izquierdo: THR (eje vertical, modo 2: persiste al soltar) + YAW (eje horizontal)
- Derecho: PITCH (eje vertical) + ROLL (eje horizontal)
- Valores PWM en tiempo real
- Modo 2: el throttle se mantiene en su última posición al soltar

**Botones Tácticos:**
- ARM: Armar motores (verde)
- TAKEOFF: Despegar (azul)
- LAND: Aterrizar (rojo/anaranjado)
- SOS: Emergencia (rojo intenso)

**Panel de Emergencia (SOS):**
- STOP: BRAKE/LOITER
- RTL: Return to Launch
- LAND: Aterrizaje inmediato

**Panel Lateral (gesto de arrastre):**
- Estado de conexión
- Selector de modo de vuelo (16 modos en 4 grupos)
- Acciones rápidas
- Estado de batería

**Animaciones:**
- Parpadeo de batería cuando < 20%
- Transiciones suaves en paneles
- Feedback háptico visual en botones

## 4.5 Pantalla GPS/Mapa (`GPSScreen.tsx`)

Pantalla de mapa con posición del dron y gestión visual de waypoints.

### Características

- **MapView** (react-native-maps) con modo satelital/standard
- **Marcador del dron** con animación de pulso
- **Círculo de precisión GPS** basado en HDOP
- **Polilínea de ruta** desde el dron hasta los waypoints
- **Toque en mapa** → crea waypoint con opciones: "Solo marcar" o "Ir ahora"
- **Selector de altitud** para GOTO: 5m, 10m, 20m, 30m, 50m
- **Indicador de calidad GPS**: EXCELENTE (≥8 sat, HDOP<1.5), BUENO, REGULAR, MALO
- **Overlay "Sin GPS"** cuando no hay coordenadas
- **Botón seguir dron**: centra el mapa en la posición del dron
- **Lista horizontal de waypoints** con opciones Ir/Eliminar

### Interacción

```typescript
- Tap en mapa → Alert con opciones: Cancelar / Solo marcar / Ir ahora
- Tap en waypoint en mapa → Ir a ese waypoint
- Long press en waypoint en lista → Eliminar
- Botón ✕ → Limpiar todos los waypoints
- Botón ⌖ → Centrar en dron
- Botón 🗺/🛰 → Alternar satelital/standard
```

## 4.6 Pantalla Waypoints (`WaypointScreen.tsx`)

Gestión avanzada de waypoints con entrada directa de coordenadas.

### Características

- **Formulario de entrada directa**: latitud, longitud, altitud, nombre
- **Selector de 6 categorías**:
  - 🌳 Parque
  - 🏛️ Edificio
  - 🌿 Zona Verde
  - ⚽ Cancha
  - 🅿️ Estacionamiento
  - 📍 Personalizado
- **Botón GPS**: completa lat/lon con la posición actual del dron
- **Lista de waypoints**: muestra nombre, categoría, coordenadas, altitud
  - Botón `IR`: envía GOTO al backend
  - Botón `X`: elimina waypoint
- **Footer con 3 botones de acción**:
  - `GOTO`: navegar al waypoint seleccionado
  - `MISSION`: sube todos los waypoints como misión y la inicia
  - `LIMPIAR`: limpia todos los waypoints

### Estructura del Waypoint

```typescript
interface Waypoint {
  id: string;
  name: string;
  category: string;
  latitude: number;
  longitude: number;
  altitude: number;
}
```

### Flujo Mission Upload

```
1. Usuario ingresa waypoints (directo o desde GPS)
2. Presiona MISSION
3. App envía MISSION_UPLOAD con array de waypoints
4. Backend recibe y formatea: {lat, lon, alt}
5. Llama a mav_controller.upload_mission()
6. Envía START_MISSION
7. Backend llama a mav_controller.start_mission()
8. Dron cambia a modo AUTO y ejecuta misión
```

## 4.7 Pantalla Telemetría (`TelemetryScreen.tsx`)

Visualización detallada de todos los parámetros del dron.

### Secciones

**Estado General:**
- Modo de vuelo actual
- Estado de armado (ARMED/STANDBY)

**Horizonte Artificial:**
- Representación visual de roll/pitch
- Cielo (azul) y tierra (marrón) separados por línea de horizonte
- Líneas de pitch cada 10°
- Indicador de yaw en la parte superior

**Actitud:**
- Roll: grados + barra visual
- Pitch: grados + barra visual
- Yaw: grados + brújula

**Velocidad:**
- Velocidad horizontal (m/s) + barra
- Velocidad vertical (m/s) + barra con indicación subida/bajada

**Posición y GPS:**
- Tabla con latitud, longitud, altitud, satélites, HDOP

**Batería:**
- Porcentaje grande
- Voltaje actual
- Barra de batería con marcadores de 25%, 50%, 75%

## 4.8 Componentes UI

### Joystick (`Joystick.tsx`)

```typescript
interface JoystickProps {
  mode: 'both' | 'vertical' | 'horizontal' | 'mode2';
  onMove: (x: number, y: number) => void;
  onRelease: () => void;
  disabled?: boolean;
  armed?: boolean;  // mode2: si false, throttle vuelve a 0
}
```

- Animado con `PanResponder` y `Animated.View`
- Clipping circular
- Deadzone configurable
- Modo 2: throttle persiste al soltar (barra lateral)
- Reset a 0 en evento de armado

### StatusBar (`StatusBar.tsx`)

```typescript
interface StatusBarProps {
  demoMode: boolean;
  connected: boolean;
  mode: string;
  armed: boolean;
  onMenuPress: () => void;
}
```

- Píldora de conexión: ONLINE (verde) / OFFLINE (rojo) con punto animado
- Badge de modo según tipo (GUIDED=azul, RTL=naranja, LAND=rojo, etc.)
- Badge DEMO con animación de pulso
- Badge ARM/STANDBY con pulso cuando armado
- Botón menú (3 líneas)

### TacticalButton (`TacticalButton.tsx`)

```typescript
interface TacticalButtonProps {
  icon: string;
  label: string;
  color: string;
  size?: 'normal' | 'compact' | 'large';
  onPress: () => void;
  disabled?: boolean;
  active?: boolean;
}
```

- Escala animada al presionar (0.95x)
- Efectos de sombra y brillo
- Estados disabled y active con colores atenuados/brillantes
- 3 tamaños predefinidos

### Navegación (App.tsx)

```typescript
// FlatList horizontal con 4 pantallas
Páginas:
1. DroneControlScreen  (icono: 🎮)
2. GPSScreen           (icono: 🛰)
3. WaypointScreen      (icono: 📍)
4. TelemetryScreen     (icono: 📊)

// Tab bar personalizada:
- Indicador de página activa (barra inferior)
- Iconos y etiquetas
```

---

# 5. Simulación ArduPilot SITL

## Descripción

ArduPilot SITL (Software In The Loop) permite ejecutar el autopiloto ArduPilot directamente en una PC sin hardware físico. Se utiliza para desarrollo y pruebas.

## Configuración en WSL2

### Requisitos

- WSL2 con Ubuntu 22.04+
- Compilador C++ (g++)
- Python 3 con pip
- MAVProxy
- ArduPilot source code

### Instalación

```bash
# En WSL2 Ubuntu:
sudo apt update
sudo apt install git build-essential python3 python3-pip

# Clonar ArduPilot
git clone https://github.com/ArduPilot/ardupilot.git
cd ardupilot

# Instalar dependencias
git submodule update --init --recursive
./Tools/environment_install/install-prereqs-ubuntu.sh -y

# Compilar Copter SITL
./waf configure --board sitl
./waf copter
```

### Ejecución

```bash
# Terminal 1: Iniciar SITL
cd ardupilot
sim_vehicle.py -v ArduCopter -L Santiago --out udp:172.28.240.1:14550

# Esto:
# 1. Inicia el simulador Copter en modo SITL
# 2. Escucha en TCP 127.0.0.1:5760
# 3. Inicia MAVProxy como GCS
# 4. Reenvía UDP a la IP especificada
```

### Parámetros del Script

```bash
# En launch_sitl_and_backend.sh:
./ardupilot/Tools/autotest/sim_vehicle.py \
  -v ArduCopter \                # Vehículo: Copter
  --map \                         # Mostrar mapa MAVProxy
  --console \                     # Mostrar consola MAVProxy
  -L Santiago \                   # Localización (-35.363262, -71.590447)
  --out udp:127.0.0.1:14550      # Salida UDP al backend local
```

### Topología de Red WSL2

```
┌─────────────────────────────────────────┐
│                WSL2 Ubuntu                │
│  ┌──────────────────────────────────────┐│
│  │  ArduPilot SITL                     ││
│  │  (arducopter)                       ││
│  │  TCP :5760                          ││
│  └──────────┬───────────────────────────┘│
│             │ MAVLink TCP              │
│  ┌──────────▼───────────────────────────┐│
│  │  MAVProxy                           ││
│  │  UDP → 172.28.240.1:14550           ││
│  │  UDP → 127.0.0.1:14550              ││
│  └──────────────────────────────────────┘│
│  IP: 172.28.252.91                       │
└─────────────────────────────────────────┘
                    │
                    │ UDP :14550
                    ▼
┌─────────────────────────────────────────┐
│              Windows Host                 │
│  Backend conecta a tcp:172.28.252.91:5760│
│  (Windows reenvía localhost:5760 a WSL)  │
└─────────────────────────────────────────┘
```

### Conexión del Backend

```python
# backend/config.py
MAVLINK_DEVICE = 'tcp:172.28.252.91:5760'
# Alternativa si Windows reenvía a localhost:
# MAVLINK_DEVICE = 'tcp:127.0.0.1:5760'
```

---

# 6. Frontend Web (Next.js)

## Estructura

```
frontend/
├── package.json           # Next.js 16, React 19, Tailwind v4
├── next.config.ts         # Config Next.js
├── tsconfig.json          # TypeScript
├── eslint.config.mjs      # ESLint
├── postcss.config.mjs     # PostCSS
├── Dockerfile             # Build Docker
├── app/
│   ├── layout.tsx         # Layout raíz
│   ├── page.tsx           # Página principal
│   └── globals.css        # Estilos globales
└── public/                # Assets estáticos
```

## Funcionalidad

- Dashboard web para monitoreo de telemetría
- Consume WebSocket en `ws://<BACKEND>:8000/ws/telemetry`
- Endpoints REST consumidos: `/api/device`, `/api/status`, `/api/battery`
- Acciones rápidas: ARM, DISARM, TAKEOFF, LAND

---

# 7. Raspberry Pi Companion

## Propósito

El módulo `raspberry/` es una versión standalone y minimalista para ejecutar en una Raspberry Pi conectada directamente al Pixhawk vía USB.

## Archivos

```
raspberry/
├── main.py              # Punto de entrada
├── connection.py        # Conexión MAVLink standalone
├── requirements.txt     # pymavlink, pyserial
└── README.md            # Documentación específica
```

## Diferencias con el Backend Completo

| Característica | Backend Completo | Raspberry Companion |
|---------------|------------------|---------------------|
| Framework | FastAPI | Script directo |
| Conexión | Serial/UDP/TCP | Serial |
| API REST | Sí | No |
| WebSocket | Sí | No |
| Cámara | Sí | No |
| DB | PostgreSQL | No |
| Ideal para | Desarrollo, pruebas | Producción embebida |

---

# 8. Dockerización

## Estructura Docker

```yaml
# docker-compose.yml
Servicios:
  - postgres:   postgres:15 (ARM64), puerto 5432
  - backend:    python:3.11-slim, puerto 8000, privilegiado
  - frontend:   node:20-alpine, puerto 3000
  Red: drone_network (bridge)
  Volumen: postgres_data
```

## Dockerfile del Backend

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim
# Instala dependencias del sistema (libgl1, libglib2.0-0 para OpenCV)
# Instala librealsense+Python bindings (compila desde fuente)
# pip install -r requirements.txt
# EXPOSE 8000
# CMD uvicorn backend.main:app
```

## Dockerfile del Frontend

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine
# npm install
# npm run build
# EXPOSE 3000
# npm start
```

## Variables de Entorno Docker

```yaml
backend:
  environment:
    - MAVLINK_DEVICE=/dev/ttyACM0
    - MAVLINK_BAUD=115200
    - API_HOST=0.0.0.0
    - API_PORT=8000
    - DB_URL=postgresql://dronix_user:DronixSecure2024!@postgres:5432/drones
  devices:
    - /dev/ttyACM0:/dev/ttyACM0  # Pixhawk USB
    - /dev/video0:/dev/video0    # Cámara USB
```

---

# 9. Protocolo de Comunicación WebSocket

## Formato General

### Mensajes Cliente → Servidor

```json
{
  "type": "<COMMAND_TYPE>",
  "params": { ... }
}
```

### Mensajes Servidor → Cliente (Telemetría)

```json
{
  "type": "telemetry",
  "data": {
    "armed": false,
    "mode": "STABILIZE",
    "altitude": 0.0,
    "latitude": -33.4489,
    "longitude": -70.6693,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
    "battery_voltage": 12.6,
    "battery_current": 0.0,
    "battery_remaining": 100,
    "ground_speed": 0.0,
    "vertical_speed": 0.0,
    "satellites": 10,
    "hdop": 0.8
  },
  "timestamp": "2026-05-09T22:49:50.123456"
}
```

### Mensajes Servidor → Cliente (ACK)

```json
{
  "type": "command_ack",
  "command": "ARM",
  "result": {
    "success": true,
    "message": "Drone armado"
  },
  "timestamp": "2026-05-09T22:49:50.123456"
}
```

## Referencia Completa de Comandos

### Comandos de Control

| type | params | Descripción |
|------|--------|-------------|
| `ARM` | `{}` | Armar motores |
| `DISARM` | `{}` | Desarmar motores |
| `TAKEOFF` | `{ "altitude": 10 }` | Despegar a altitud especificada |
| `LAND` | `{}` | Aterrizar |
| `RTL` | `{}` | Return to Launch |
| `REBOOT` | `{}` | Reiniciar autopiloto (solo real, no SIM) |
| `SET_MODE` | `{ "mode": "GUIDED" }` | Cambiar modo de vuelo |

### Comandos RC

| type | params | ACK | Descripción |
|------|--------|-----|-------------|
| `RC_CONTROL` | `{ throttle, yaw, pitch, roll }` | No | Valores RC normalizados |
| `RC_RESET` | `{}` | No | Resetear RC |

**Valores normalizados:**
- `throttle`: 0.0 (mín) a 1.0 (máx)
- `yaw`: -1.0 (izquierda) a 1.0 (derecha)
- `pitch`: -1.0 (adelante/abajo) a 1.0 (atrás/arriba)
- `roll`: -1.0 (izquierda) a 1.0 (derecha)

### Comandos de Emergencia

| type | params | Descripción |
|------|--------|-------------|
| `EMERGENCY` | `{ "action": "STOP" }` | STOP: BRAKE/LOITER + reset RC |
| `EMERGENCY` | `{ "action": "RTL" }` | Return to Launch |
| `EMERGENCY` | `{ "action": "LAND" }` | Aterrizaje inmediato |
| `EMERGENCY` | `{ "action": "KILL" }` | **PELIGROSO**: motores off inmediato |

### Comandos de Navegación

| type | params | Descripción |
|------|--------|-------------|
| `GOTO` | `{ latitude, longitude, altitude }` | Navegar a coordenada |
| `MISSION_UPLOAD` | `{ waypoints: [{ lat, lon, alt }, ...] }` | Subir misión |
| `START_MISSION` | `{}` | Iniciar misión |
| `CLEAR_MISSION` | `{}` | Limpiar misión |

## Códigos de Cierre WebSocket

| Código | Significado | Causa común |
|--------|-------------|-------------|
| 1000 | Normal closure | Cliente desconectado intencionalmente |
| 1001 | Going away | Backend deteniéndose |
| 1006 | Abnormal closure | Red caída, backend crash |
| 1011 | Internal error | Error en backend |

---

# 10. Guía de Despliegue

## 10.1 Desarrollo Local (Windows + WSL2 + SITL)

### Requisitos

- Python 3.11+
- Node.js 22+
- WSL2 con Ubuntu 22.04+
- ArduPilot SITL compilado en WSL
- ADB + BlueStacks (opcional, para app móvil)

### Paso 1: Iniciar SITL (WSL)

```bash
# En WSL2 Ubuntu:
cd ~/ardupilot
sim_vehicle.py -v ArduCopter -L Santiago --out udp:172.28.240.1:14550
```

### Paso 2: Iniciar Backend (Windows)

```bash
cd C:\Users\USUARIO\Downloads\back-mavlink
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cd backend
# Configurar .env con MAVLINK_DEVICE=tcp:172.28.252.91:5760
python -m backend.main
```

### Paso 3: Iniciar App Móvil (BlueStacks)

```bash
# Configurar HOST_IP en mobile/src/config.ts con IP LAN
cd mobile
npm install

# Debug:
npx react-native start
npx react-native run-android

# Release:
cd android
.\gradlew.bat assembleRelease
adb connect 127.0.0.1:5556
adb install -r .\app\build\outputs\apk\release\app-release.apk
adb reverse tcp:8000 tcp:8000  # Si se necesita
```

## 10.2 Producción (Raspberry Pi + Pixhawk)

### Hardware

- Raspberry Pi 4/5 (2GB+ RAM)
- Pixhawk (CUBE, Pixhawk 4, etc.)
- Cámara USB o RealSense D435
- Módulo de telemetría (3DR/SiK) — opcional

### Paso 1: Preparar Raspberry Pi

```bash
# Instalar Raspberry Pi OS 64-bit
sudo apt update && sudo apt upgrade
sudo apt install docker.io docker-compose
sudo usermod -aG docker $USER
# Reiniciar sesión
```

### Paso 2: Desplegar con Docker

```bash
git clone <repo-url>
cd back-mavlink

# Verificar puerto Pixhawk
ls /dev/ttyACM0

# Iniciar todo
docker-compose up --build -d

# Verificar logs
docker-compose logs -f
```

### Paso 3: Exponer sin Docker (más simple)

```bash
cd back-mavlink/raspberry
pip install -r requirements.txt

# Configurar puerto en main.py
python main.py
```

## 10.3 Configuración de Red

### BlueStacks (Wifi Directo)

```
App móvil → http://192.168.20.38:8000 (IP LAN del host)
Backend → arranca en 0.0.0.0:8000
Firewall → Puerto 8000 abierto
```

### Emulador Android (ADB Reverse)

```bash
adb reverse tcp:8000 tcp:8000
# App usa HOST_IP = 'localhost'
```

### Dispositivo Físico (Misma Red WiFi)

```bash
# App usa HOST_IP = '192.168.x.x' (IP LAN del servidor)
# Verificar firewall: puerto 8000 accesible
```

---

# 11. Solución de Problemas

## 11.1 WebSocket

### Síntoma: Reconexión infinita

**Causa:** Dependencia cíclica en useEffect de DroneContext.

**Solución:** Eliminar `connected` de las dependencias del useEffect de conexión WebSocket. El estado `connected` cambia dentro del handler `onclose`, que a su vez reconecta, causando loop infinito si está en la lista de dependencias.

### Síntoma: WebSocket no conecta en release APK

**Causa:** `usesCleartextTraffic="false"` (default en React Native 0.83+ para release).

**Solución:** Forzar `android:usesCleartextTraffic="true"` en `AndroidManifest.xml`:
```xml
<application
  android:usesCleartextTraffic="true"
  ...>
```

### Síntoma: WebSocket se cierra con code=1000 al conectar

**Causa:** Normalmente es cierre normal. Puede deberse a:
1. Reconexión: la conexión anterior se cerró para abrir una nueva
2. Backend reiniciado: broadcast de telemetría se detuvo y reinició
3. Timeout de inactividad

**Solución:** Verificar que el broadcaster de telemetría esté activo en backend.

### Síntoma: Error "Device offline" en ADB

**Causa:** BlueStacks perdió la conexión ADB.

**Solución:**
```bash
adb kill-server
adb connect 127.0.0.1:5556  # Puerto BlueStacks
adb devices  # Verificar estado "device"
```

## 11.2 MAVLink

### Síntoma: MAVController no conecta a SITL

**Causa:** IP incorrecta de WSL2.

**Solución:**
```bash
# Desde PowerShell, obtener IP de WSL2:
wsl -- hostname -I
# → 172.28.252.91
# Actualizar backend/config.py con esa IP
```

### Síntoma: SITL no arranca en WSL

**Causa:** Dependencias de compilación faltantes o puerto ocupado.

**Solución:**
```bash
# Verificar puerto:
netstat -ano | findstr :5760
# Matar proceso si es necesario:
# kill -9 <PID_en_WSL>
```

### Síntoma: MAVLink connection lost en monitoring

**Causa:** SITL se cayó o red WSL2 inestable.

**Solución:** Verificar proceso SITL en WSL: `ps aux | grep arducopter`. Si no corre, reiniciar.

## 11.3 App Móvil

### Síntoma: Modo demo siempre activo

**Causa:** WebSocket no puede conectar al backend.

**Verificar:**
1. Backend corriendo: `http://192.168.20.38:8000/health`
2. Firewall permitiendo puerto 8000
3. HOST_IP correcto en `config.ts`

### Síntoma: Joystick no responde

**Causa:** RC_CONTROL no enviado o heartbeat no activo.

**Solución:** Verificar que `ws.current.readyState === WebSocket.OPEN` en el heartbeat de 10Hz. Revisar que `setJoystick` en DroneControlScreen recibe datos.

### Síntoma: MapView no muestra mapa

**Causa:** API key de Google Maps faltante o inválida.

**Solución:** Verificar `com.google.android.geo.API_KEY` en `AndroidManifest.xml`. Si no hay, generar clave en Google Cloud Console.

## 11.4 Base de Datos

### Síntoma: Error de conexión PostgreSQL

**Causa:** DB_URL incorrecta o Postgres no iniciado.

**Solución:**
```bash
# Verificar que Postgres corre:
docker ps | grep postgres
# Verificar DB_URL en .env o config.py
# Si no se necesita BD, ignorar warning — backend funciona igual
```

---

# 12. Referencia de API Completa

## REST API

### GET /

**Descripción:** Información de la API.

**Respuesta:**
```json
{
  "message": "Drone Control API",
  "version": "1.0.0",
  "status": "running"
}
```

### GET /health

**Respuesta:** `{ "status": "healthy" }`

### GET /api/status

**Respuesta:**
```json
{
  "connected": true,
  "armed": false,
  "mode": "STABILIZE",
  "system_status": "STANDBY"
}
```

### GET /api/telemetry

**Respuesta:** Objeto Telemetry completo (ver sección 9).

### POST /api/arm

**Body:** `{ "force": false }`

**Respuesta:**
```json
{
  "success": true,
  "message": "Dron armado",
  "armed": true
}
```

### POST /api/arm (force)

**Body:** `{ "force": true }` — Omite chequeos de seguridad. Útil para forzar armado.

### POST /api/disarm

**Respuesta:**
```json
{
  "success": true,
  "message": "Dron desarmado",
  "armed": false
}
```

### POST /api/takeoff

**Body:** `{ "altitude": 10 }` — Altitud entre 2 y 100 metros.

### POST /api/land

### POST /api/rtl

### POST /api/goto

**Body:**
```json
{
  "latitude": -33.4489,
  "longitude": -70.6693,
  "altitude": 20
}
```

**Respuesta:**
```json
{
  "success": true,
  "message": "Navegando a (-33.4489, -70.6693)",
  "target": {
    "latitude": -33.4489,
    "longitude": -70.6693,
    "altitude": 20
  }
}
```

### POST /api/mode

**Body:** `{ "mode": "GUIDED" }`

**Modos válidos:** STABILIZE, ACRO, SPORT, DRIFT, ALT_HOLD, POSHOLD, LOITER, BRAKE, AUTO, GUIDED, CIRCLE, FLIP, THROW, RTL, SMARTRTL, LAND.

### POST /api/emergency

**Body:** `{ "action": "STOP" | "RTL" | "LAND" | "KILL" }`

### POST /api/rc/control

**Body:**
```json
{
  "throttle": 0.5,
  "yaw": 0.0,
  "pitch": 0.3,
  "roll": -0.1
}
```

### GET /api/rc/values

### POST /api/rc/reset

## WebSocket

### ws://<host>:8000/ws/telemetry

Protocolo completo documentado en [sección 9](#9-protocolo-de-comunicación-websocket).

## Cámara Endpoints

### GET /api/camera/stream — MJPEG stream
### WS /api/camera/ws — WebSocket con frames base64
### GET /api/camera/view — Visor HTML
### GET /api/camera/snapshot — JPEG snapshot
### POST /api/camera/start — Iniciar
### POST /api/camera/stop — Detener
### GET /api/camera/status — Estado

---

# Apéndice A: Glosario

| Término | Significado |
|---------|-------------|
| **MAVLink** | Protocolo de comunicación ligero para drones (Message Marshalling) |
| **MAVProxy** | GCS (Ground Control Station) por línea de comandos |
| **SITL** | Software In The Loop — simulador de ArduPilot |
| **GCS** | Ground Control Station — estación de control en tierra |
| **Pixhawk** | Autopiloto hardware para drones |
| **ArduPilot** | Firmware de código abierto para autopilotos |
| **HDOP** | Horizontal Dilution of Precision — precisión GPS horizontal |
| **RTL** | Return To Launch — regresar al punto de despegue |
| **GUIDED** | Modo de vuelo donde el dron recibe comandos externos |
| **BRAKE** | Modo que frena el dron en su posición actual |
| **LOITER** | Modo que mantiene posición y altitud |
| **ACK** | Acknowledgement — confirmación de comando |
| **PWM** | Pulse Width Modulation — modulación usada para controlar servos/ESCs |
| **ESC** | Electronic Speed Controller — controlador de velocidad de motor |
| **FPV** | First Person View — vista en primera persona |
| **HUD** | Heads-Up Display — superposición de datos en pantalla |
| **JSON** | JavaScript Object Notation — formato de intercambio de datos |

# Apéndice B: Archivos Clave del Proyecto

| Archivo | Propósito |
|---------|-----------|
| `backend/config.py` | Configuración central (MAVLink, API, DB) |
| `backend/main.py` | Punto de entrada FastAPI con lifecycle |
| `backend/api/rest.py` | Endpoints REST del dron |
| `backend/api/websocket.py` | WebSocket bidireccional |
| `backend/mavlink/controller.py` | Controlador MAVLink de alto nivel |
| `backend/mavlink/commands.py` | Comandos MAVLink específicos |
| `backend/mavlink/telemetry.py` | Procesamiento de telemetría |
| `mobile/src/config.ts` | Configuración de red de la app |
| `mobile/App.tsx` | Navegación principal de la app |
| `mobile/src/context/DroneContext.tsx` | Estado global y WebSocket |
| `mobile/src/screens/DroneControlScreen.tsx` | Pantalla de control principal |
| `mobile/src/screens/GPSScreen.tsx` | Mapa GPS con waypoints |
| `mobile/src/screens/WaypointScreen.tsx` | Gestión avanzada de waypoints |
| `mobile/src/screens/TelemetryScreen.tsx` | Telemetría detallada |
| `mobile/src/components/Joystick.tsx` | Joystick virtual |
| `docker-compose.yml` | Orquestación Docker completa |
| `scripts/TROUBLESHOOTING_WEBSOCKET.md` | Guía de troubleshooting WebSocket |

# Apéndice C: Dependencias

## Backend (Python)

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| fastapi | 0.104.1 | Framework web |
| uvicorn | 0.24.0 | Servidor ASGI |
| pymavlink | 2.4.41 | Protocolo MAVLink |
| sqlalchemy | 2.0.23 | ORM para BD |
| psycopg2-binary | 2.9.9 | Driver PostgreSQL |
| pyserial | 3.5 | Comunicación serial |
| python-dotenv | 1.0.0 | Variables de entorno |
| pydantic | 2.5.0 | Validación de datos |
| opencv-python-headless | 4.8.1.78 | Procesamiento de video |
| websockets | 11.0.3 | WebSocket server |
| numpy | 1.26.0+ | Cálculos numéricos |
| Pillow | 10.1.0 | Procesamiento de imágenes |

## Mobile (React Native)

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| react-native | 0.83.1 | Framework móvil |
| react | 19.2.0 | UI library |
| react-native-maps | — | MapView nativo |
| react-native-safe-area-context | — | Safe area insets |
| react-native-webview | — | WebView para video |
| axios | — | HTTP client |
| typescript | — | Tipado estático |

## Frontend (Next.js)

| Paquete | Versión |
|---------|---------|
| next | 16.1.4 |
| react | 19.2.3 |
| tailwindcss | 4 |
| typescript | 5 |
