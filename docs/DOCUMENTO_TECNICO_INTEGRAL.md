# Documento Técnico Integral
## Sistema de Control y Telemetría para Drones

**Versión:** 1.0.0  
**Fecha:** Mayo 2026  
**Plataforma:** ArduPilot / PX4 · MAVLink · FastAPI · React Native

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Introducción](#2-introducción)
3. [Arquitectura General del Sistema](#3-arquitectura-general-del-sistema)
4. [Componentes del Sistema](#4-componentes-del-sistema)
5. [Protocolo MAVLink](#5-protocolo-mavlink)
6. [Backend (FastAPI)](#6-backend-fastapi)
7. [App Móvil (React Native)](#7-app-móvil-react-native)
8. [Visión por Computadora](#8-visión-por-computadora)
9. [Simulación](#9-simulación)
10. [Base de Datos](#10-base-de-datos)
11. [Seguridad](#11-seguridad)
12. [Despliegue](#12-despliegue)
13. [Pruebas](#13-pruebas)
14. [Mantenimiento y Troubleshooting](#14-mantenimiento-y-troubleshooting)
15. [Conclusiones](#15-conclusiones)

---

## 1. Resumen Ejecutivo

El presente documento describe la arquitectura, implementación y operación de un sistema integral de control y telemetría para vehículos aéreos no tripulados (drones) compatible con firmware ArduPilot. El sistema permite la operación remota de un dron mediante una aplicación móvil React Native, un backend FastAPI con comunicación MAVLink, capacidades de visión artificial con YOLOv8, y un módulo de simulación para pruebas offline.

El proyecto está diseñado con una arquitectura modular, desacoplada y escalable, utilizando protocolos estándar de la industria (MAVLink, WebSocket, REST) para garantizar interoperabilidad y facilidad de extensión.

**Palabras clave:** Dron, MAVLink, ArduPilot, FastAPI, React Native, YOLOv8, Telemetría, Visión Artificial, SITL.

---

## 2. Introducción

### 2.1 Contexto

Los vehículos aéreos no tripulados (UAV) han experimentado un crecimiento exponencial en los últimos años, con aplicaciones que abarcan desde la agricultura de precisión hasta la respuesta a emergencias. Sin embargo, muchas soluciones comerciales son cerradas, costosas o difíciles de integrar con sistemas externos.

Este proyecto nace de la necesidad de contar con una plataforma abierta, extensible y multiplataforma para el control de drones basados en ArduPilot, el firmware de autopiloto open-source más utilizado en el ámbito académico y de investigación.

### 2.2 Objetivos

- **General:** Desarrollar un sistema integral de control y telemetría para drones ArduPilot, accesible desde dispositivos móviles.
- **Específicos:**
  - Implementar comunicación bidireccional vía protocolo MAVLink.
  - Desarrollar una API REST y WebSocket para control en tiempo real.
  - Crear una interfaz móvil intuitiva con joysticks virtuales y telemetría en vivo.
  - Integrar detección de objetos con YOLOv8 para evitar colisiones.
  - Proveer un simulador virtual para pruebas sin hardware.
  - Implementar persistencia de waypoints para reutilización de rutas.

### 2.3 Alcance

El sistema abarca:

- Conexión con Pixhawk físico (serial), SITL (TCP/UDP) o simulador interno.
- Transmisión de telemetría en tiempo real (posición, actitud, batería, GPS, velocidad).
- Comandos de control: ARM, DISARM, TAKEOFF, LAND, RTL, GOTO, cambio de modo.
- Control manual mediante joysticks virtuales (override RC).
- Gestión de misiones: subida, inicio y limpieza de waypoints.
- Waypoints relativos: definidos como desplazamiento desde la posición actual.
- Persistencia de waypoints en disco.
- Streaming de video con detección de objetos y frenado automático de emergencia.
- Cuatro modos de simulación para desarrollo y pruebas.
- Dashboard web de telemetría (Next.js).

---

## 3. Arquitectura General del Sistema

### 3.1 Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                        APLICACIÓN MÓVIL                            │
│                     (React Native 0.83.1)                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  ┌────────────┐ │
│  │DroneControl │  │ Telemetry    │  │   GPS    │  │  Waypoint  │ │
│  │   Screen    │  │   Screen     │  │  Screen  │  │   Screen   │ │
│  └──────┬──────┘  └──────┬───────┘  └────┬─────┘  └─────┬──────┘ │
│         └────────────────┼───────────────┼───────────────┘        │
│                          │     DroneContext (WebSocket)            │
│                          │              │                         │
└──────────────────────────┼──────────────┼─────────────────────────┘
                           │              │
                    ┌──────┴──────┐       │ WS /ws/telemetry
                    │   REST API  │       │
                    │  :8000/api  │       │
                    └──────┬──────┘       │
                           │              │
┌──────────────────────────┼──────────────┼─────────────────────────┐
│                     BACKEND (FastAPI)   │                         │
│                                          │                        │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐│                        │
│  │  rest.py │  │websocket │  │camera_   ││                        │
│  │         │  │  .py     │  │stream.py ││                        │
│  └────┬────┘  └────┬─────┘  └────┬─────┘│                        │
│       │            │              │      │                        │
│  ┌────┴────────────┴──────────────┴───┐  │                        │
│  │         MAVController               │  │                        │
│  │  ┌─────────┐┌──────────┐┌────────┐ │  │                        │
│  │  │Commands ││Telemetry ││RC_Over │ │  │                        │
│  │  │         ││          ││ride    │ │  │                        │
│  │  └────┬────┘└────┬─────┘└───┬────┘ │  │                        │
│  │       │          │          │      │  │                        │
│  │  ┌────┴──────────┴──────────┴───┐  │  │                        │
│  │  │   MAVLinkConnection          │  │  │                        │
│  │  │   (Serial / TCP / UDP / SIM) │  │  │                        │
│  │  └───────────────┬──────────────┘  │  │                        │
│  └──────────────────┼─────────────────┘  │                        │
│                     │                     │                        │
│  ┌──────────────────┼─────────────────┐  │                        │
│  │    VisionDetector (YOLOv8n)        │  │                        │
│  └──────────────────┼─────────────────┘  │                        │
│                     │                     │                        │
│  ┌──────────────────┼─────────────────┐  │                        │
│  │  RealSenseCamera / OpenCV          │  │                        │
│  └────────────────────────────────────┘  │                        │
└──────────────────────────────────────────┘                        │
                     │
       ┌─────────────┼──────────────┬──────────────┐
       │             │              │              │
  ┌────┴────┐  ┌────┴────┐  ┌──────┴──────┐ ┌────┴────┐
  │ Pixhawk │  │  SITL   │  │sim_drone.py │ │PostgreSQL│
  │ (Serial)│  │(TCP/UDP)│  │ (Virtual)   │ │   DB     │
  └─────────┘  └─────────┘  └─────────────┘ └─────────┘
```

### 3.2 Flujo de Comunicación

**Conexión de telemetría (unidireccional, 10 Hz):**

```
Pixhawk/SITL ──MAVLink──→ MAVLinkConnection ──→ DroneTelemetry ──→ WebSocket ──→ App Móvil
                          (thread lectura)       (procesamiento)    (broadcast)
```

**Conexión de control (bidireccional, bajo demanda):**

```
App Móvil ──WebSocket──→ process_command() ──→ MAVController ──→ MAVLinkConnection ──→ Pixhawk/SITL
             (JSON)        (switch cmd_type)        (commands.py)      (send_command)
```

### 3.3 Stack Tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Backend Framework | FastAPI (Python) | 0.104.1 |
| Servidor ASGI | Uvicorn | 0.24.0 |
| Protocolo Dron | pymavlink | 2.4.41 |
| Base de Datos | PostgreSQL 15 | - |
| ORM | SQLAlchemy | 2.0.23 |
| Serialización | Pydantic | 2.5.0 |
| Visión | YOLOv8n (Ultralytics) | - |
| Cámara | OpenCV (Intel RealSense D435i) | 4.8.1 |
| App Móvil | React Native | 0.83.1 |
| Lenguaje Móvil | TypeScript | 5.8 |
| Mapas | react-native-maps | 1.27.1 |
| Virtualización | Docker / docker-compose | - |
| Plataforma HW | Raspberry Pi (ARM64) / x86_64 | - |

---

## 4. Componentes del Sistema

### 4.1 Backend (`backend/`)

El backend es el núcleo del sistema. Está desarrollado en Python con FastAPI y expone interfaces REST y WebSocket. Se organiza en los siguientes módulos:

| Módulo | Archivo | Responsabilidad |
|--------|---------|-----------------|
| Configuración | `config.py` | Variables de entorno, detección automática de dispositivo MAVLink |
| Punto de entrada | `main.py` | Inicialización de FastAPI, inclusión de routers, eventos startup/shutdown |
| API REST | `api/rest.py` | Endpoints REST: arm, takeoff, land, goto, emergencias, waypoints |
| API WebSocket | `api/websocket.py` | Canal bidireccional de telemetría y comandos en tiempo real |
| Streaming | `api/camera_stream.py` | Streaming MJPEG, WebSocket, snapshots, detección ArUco/YOLO |
| Controlador | `mavlink/controller.py` | Orquestador de alto nivel, wrapper del simulador interno |
| Conexión | `mavlink/connection.py` | Conexión MAVLink con reconexión automática y protección de raza |
| Comandos | `mavlink/commands.py` | Envío de comandos MAVLink: arm, disarm, takeoff, land, etc. |
| Telemetría | `mavlink/telemetry.py` | Lectura y procesamiento de telemetría en loop |
| RC Override | `mavlink/rc_override.py` | Control manual por override de canales RC |
| Geo Utils | `mavlink/geo_utils.py` | Conversión de coordenadas relativas a GPS absolutas |
| Detector | `vision/detector.py` | Detección YOLOv8n con estimación de distancia |

### 4.2 App Móvil (`mobile/`)

Aplicación React Native con TypeScript que proporciona la interfaz de usuario para operar el dron.

| Pantalla | Archivo | Funcionalidad |
|----------|---------|---------------|
| Control Principal | `DroneControlScreen.tsx` | Joysticks virtuales, HUD, botones tácticos, panel lateral de modos |
| Telemetría | `TelemetryScreen.tsx` | Dashboard detallado: horizonte artificial, velocidades, batería, GPS |
| GPS | `GPSScreen.tsx` | Mapa interactivo, waypoints por geolocalización, seguimiento |
| Waypoints | `WaypointScreen.tsx` | Waypoints relativos, subida de misión, persistencia |

| Contexto/Utilidad | Archivo | Funcionalidad |
|-------------------|---------|---------------|
| Estado Global | `DroneContext.tsx` | WebSocket, telemetría en vivo, cola de comandos, modo demo |
| Configuración | `config.ts` | URL del backend (IP configurable) |
| Joystick | `Joystick.tsx` | Joystick virtual táctil |
| Barra Estado | `StatusBar.tsx` | Conexión, modo, ARM, demo |
| Botón Táctico | `TacticalButton.tsx` | Botón de acción estilizado |

### 4.3 Scripts de Utilidad (`scripts/`)

| Script | Propósito |
|--------|-----------|
| `sim_drone.py` | Dron virtual bidireccional (UDP→QGC, TCP→backend) con respuesta a comandos |
| `virtual_drone.py` | Versión anterior del dron virtual (reemplazado por sim_drone) |
| `start_all.ps1` | Lanza simulación + backend en Windows |
| `start_all.sh` | Lanza simulación + backend en Linux/Mac |
| `deploy_raspberry.sh` | Despliegue automatizado en Raspberry Pi |
| `gen_markers.py` | Genera marcadores ArUco para calibración de visión |
| `test_*.py` | ~20 scripts de prueba: conexión, GPS, SITL, armado, misiones |
| `upload_*.py` | Subida de misiones de prueba (circular, directa, v2) |
| `create_tables.py` | Creación de tablas en PostgreSQL |
| `bridge_*.py` | Puentes de conexión WSL/SITL/QGC |

### 4.4 Frontend Web (`frontend/`)

Dashboard web Next.js para visualización de telemetría y administración. Se ejecuta en el puerto 4545 (mapeado desde 3000 interno).

---

## 5. Protocolo MAVLink

### 5.1 Introducción a MAVLink

MAVLink (Micro Air Vehicle Link) es un protocolo de comunicación ligero diseñado para vehículos aéreos no tripulados. Es el estándar de facto en la industria de drones open-source. El protocolo define:

- **Mensajes** de telemetría (posición, actitud, batería, GPS, velocidad, etc.)
- **Comandos** de control (armar, despegar, aterrizar, navegar a posición, etc.)
- **Misiones** (lista de waypoints que el dron ejecuta secuencialmente)
- **Parámetros** de configuración del autopiloto

### 5.2 Mensajes MAVLink Utilizados

| Mensaje | Dirección | Propósito |
|---------|-----------|-----------|
| `HEARTBEAT` | Dron → Sistema | Estado general: armado, modo, system status |
| `VFR_HUD` | Dron → Sistema | Altitud, velocidad, climb rate, throttle |
| `GPS_RAW_INT` | Dron → Sistema | Latitud, longitud, altitud GPS, satélites, HDOP |
| `ATTITUDE` | Dron → Sistema | Roll, pitch, yaw (ángulos de Euler) |
| `BATTERY_STATUS` | Dron → Sistema | Voltaje, corriente, porcentaje restante |
| `SYS_STATUS` | Dron → Sistema | Estado de sensores, batería (fallback) |
| `HOME_POSITION` | Dron → Sistema | Posición de despegue (home) |
| `COMMAND_ACK` | Dron → Sistema | Confirmación de comando recibido |
| `MISSION_REQUEST_INT` | Sistema → Dron | Solicitud de siguiente waypoint en misión |
| `MISSION_ACK` | Dron → Sistema | Confirmación de misión recibida |

### 5.3 Comandos MAVLink Implementados

| Comando | Código MAVLink | Propósito |
|---------|----------------|-----------|
| `MAV_CMD_COMPONENT_ARM_DISARM` | 400 | Armar/desarmar motores |
| `MAV_CMD_NAV_TAKEOFF` | 22 | Despegue a altitud objetivo |
| `MAV_CMD_NAV_LAND` | 21 | Aterrizaje |
| `MAV_CMD_NAV_WAYPOINT` | 16 | Waypoint en misión |
| `MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN` | 246 | Reiniciar autopiloto |
| `MISSION_COUNT` | 44 | Iniciar subida de misión |
| `MISSION_ITEM_INT` | 73 | Enviar waypoint de misión |
| `SET_MODE` | 11 | Cambiar modo de vuelo |
| `RC_CHANNELS_OVERRIDE` | 70 | Control manual por radio |

### 5.4 Modos de Vuelo Soportados

| Modo | Descripción | Requiere GPS |
|------|-------------|--------------|
| `STABILIZE` | Control manual con auto-nivelación | No |
| `ALT_HOLD` | Altitud automática, control horizontal manual | No |
| `LOITER` | Posición fija con GPS | Sí |
| `POSHOLD` | Posición + altitud fija | Sí |
| `AUTO` | Ejecución de misión | Sí |
| `GUIDED` | Control desde estación en tierra | Sí |
| `RTL` | Retorno a punto de despegue | Sí |
| `LAND` | Aterrizaje automático | No |
| `BRAKE` | Frenado inmediato | Sí |
| `CIRCLE` | Vuelo en círculo | Sí |
| `SPORT` | Modo manual con respuesta mejorada | No |
| `ACRO` | Modo acrobático | No |
| `DRIFT` | Vuelo estilo avión | No |
| `FLIP` | Realiza flips | No |
| `THROW` | Lanzamiento manual | No |
| `SMARTRTL` | RTL inteligente con evitación | Sí |

---

## 6. Backend (FastAPI)

### 6.1 Inicialización y Ciclo de Vida

El archivo `main.py` define el ciclo de vida de la aplicación FastAPI:

**Startup:**
1. Detectar dispositivo MAVLink (`detect_mavlink_device()`)
2. Inicializar `MAVController` con el dispositivo y baudrate
3. Iniciar monitoreo de conexión (thread check cada 5s)
4. Iniciar cámara RealSense (fallback silencioso si no está disponible)
5. Iniciar broadcast de telemetría WebSocket
6. Registrar callback de emergencia para visión → MAVLink (auto-avoid)

**Shutdown:**
1. Detener cámara
2. Desconectar MAVLink

### 6.2 API REST

La API REST está disponible en `http://<host>:8000/api/` y expone los siguientes endpoints:

#### Estado y Telemetría

| Método | Ruta | Respuesta |
|--------|------|-----------|
| `GET` | `/api/status` | Conexión, armado, modo, system status |
| `GET` | `/api/telemetry` | Altitud, GPS, batería, actitud, velocidad |

#### Control Básico

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| `POST` | `/api/arm` | `{"force": false}` | Armar motores |
| `POST` | `/api/disarm` | - | Desarmar motores |
| `POST` | `/api/takeoff` | `{"altitude": 10}` | Despegar a altitud |
| `POST` | `/api/land` | - | Aterrizar |
| `POST` | `/api/rtl` | - | Return to Launch |
| `POST` | `/api/goto` | `{"lat","lon","alt"}` | Navegar a coordenada |

#### Cambio de Modo

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| `POST` | `/api/mode` | `{"mode": "GUIDED"}` | Cambiar modo de vuelo |

#### Control RC

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| `POST` | `/api/rc/control` | `{"throttle","yaw","pitch","roll"}` | Enviar override RC |
| `POST` | `/api/rc/reset` | - | Resetear controles RC |
| `GET` | `/api/rc/values` | - | Valores actuales RC |

#### Emergencias

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| `POST` | `/api/emergency` | `{"action":"STOP"|"RTL"|"LAND"|"KILL"}` | Acción de emergencia |

#### Waypoints (Persistencia)

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| `POST` | `/api/waypoints/save` | `{"name","waypoints"}` | Guardar waypoints en disco |
| `POST` | `/api/waypoints/load` | `{"name"}` | Cargar waypoints del disco |
| `GET` | `/api/waypoints/list` | - | Listar nombres guardados |
| `DELETE` | `/api/waypoints/{name}` | - | Eliminar archivo guardado |

#### Cámara

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/camera/snapshot` | Captura JPEG actual |
| `GET` | `/api/camera/stream` | Streaming MJPEG |
| `GET` | `/api/camera/view` | Página HTML con stream + detecciones |
| `GET` | `/api/camera/status` | Estado de la cámara y visión |
| `GET` | `/api/camera/vision` | Detecciones actuales |
| `POST` | `/api/camera/start` | Iniciar cámara |
| `POST` | `/api/camera/stop` | Detener cámara |
| `GET` | `/api/camera/markers/{id}` | Obtener marcador ArUco |
| `WS` | `/api/camera/ws` | Streaming WebSocket (base64, 25fps) |

### 6.3 WebSocket

El WebSocket principal está en `ws://<host>:8000/ws/telemetry` y maneja dos tipos de mensajes:

**Envío al cliente (broadcast cada 100ms):**
```json
{
  "type": "telemetry",
  "data": {
    "armed": false,
    "mode": "STABILIZE",
    "altitude": 0,
    "latitude": 4.711,
    "longitude": -74.0721,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
    "battery_voltage": 12.6,
    "battery_remaining": 100,
    "ground_speed": 0,
    "vertical_speed": 0,
    "satellites": 10,
    "hdop": 0.8
  },
  "timestamp": "2026-05-17T12:00:00.000000"
}
```

**Recepción desde el cliente (comandos):**
```json
{
  "type": "ARM",
  "params": {}
}
```

**Respuesta a comandos (ACK):**
```json
{
  "type": "command_ack",
  "command": "ARM",
  "result": {
    "success": true,
    "message": "Drone armado"
  },
  "timestamp": "2026-05-17T12:00:00.000000"
}
```

**Comandos WebSocket disponibles:**

| Comando | Parámetros | Descripción |
|---------|-------------|-------------|
| `ARM` | - | Armar motores |
| `DISARM` | - | Desarmar motores |
| `TAKEOFF` | `altitude` (int) | Despegar |
| `LAND` | - | Aterrizar |
| `RTL` | - | Return to Launch |
| `SET_MODE` | `mode` (string) | Cambiar modo |
| `REBOOT` | - | Reiniciar autopiloto |
| `GOTO` | `lat, lon, alt` | Ir a coordenada |
| `GOTO_RELATIVE` | `forward, right, up` | Ir relativo al dron |
| `RC_CONTROL` | `throttle, yaw, pitch, roll` | Control manual continuo |
| `RC_RESET` | - | Resetear controles |
| `EMERGENCY` | `action: STOP/RTL/LAND` | Emergencia |
| `MISSION_UPLOAD` | `waypoints: [{lat, lon, alt}]` | Subir misión |
| `MISSION_UPLOAD_RELATIVE` | `waypoints: [{forward, right, up}]` | Subir misión relativa |
| `START_MISSION` | - | Iniciar misión |
| `CLEAR_MISSION` | - | Limpiar misión |
| `SAVE_WAYPOINTS` | `name, waypoints` | Guardar waypoints |
| `LOAD_WAYPOINTS` | `name` | Cargar waypoints |
| `LIST_WAYPOINTS` | - | Listar waypoints guardados |

### 6.4 Módulo de Conexión MAVLink

El archivo `connection.py` implementa la clase `MAVLinkConnection`, que maneja:

- **Conexión con reintentos:** Hasta 5 intentos con backoff exponencial
- **Reconexión automática:** Thread en background que verifica conectividad cada 5s
- **Protección contra race conditions:** Lock exclusivo para escrituras, recepción sin lock
- **Soporte multi-conexión:** Serial, TCP, UDP, SIM
- **Manejo de ACK:** Almacena `COMMAND_ACK` recibidos en el `_read_loop` para `wait_ack()`

**Tipos de conexión soportados:**

```
MAVLINK_DEVICE=                     # Modo
SIM                                  → Simulador interno
tcp:127.0.0.1:14551                 → TCP (SITL remoto)
udpin:0.0.0.0:14550                 → UDP escucha (MAVProxy)
udpout:127.0.0.1:14550              → UDP envío
/dev/ttyACM0                        → Serial (Pixhawk USB)
/dev/ttyUSB0                        → Serial (radio telemetría)
```

### 6.5 Módulo de Telemetría

El archivo `telemetry.py` implementa `DroneTelemetry`:

- **Thread de lectura:** Loop a 100 Hz procesando mensajes MAVLink
- **Mensajes procesados:** VFR_HUD, GPS_RAW_INT, BATTERY_STATUS, SYS_STATUS, ATTITUDE, HEARTBEAT, HOME_POSITION
- **Mapeo de modos:** Traducción de `custom_mode` numérico a nombre de modo ArduPilot
- **Persistencia opcional:** Guarda snapshots en PostgreSQL cada N segundos
- **Getters:** `get_all()`, `get_status()`, `get_battery()`, `get_gps()`, `get_attitude()`, `get_velocity()`, `get_position()`
- **Pre-flight checks:** Verifica GPS fix ≥ 3, satélites ≥ 6, batería > 30%, EKF ok, home set, sensores ok

### 6.6 Módulo de Comandos

El archivo `commands.py` implementa `DroneCommands`:

- Todos los comandos se envían con lock para evitar race conditions
- `wait_ack()` espera confirmación del autopiloto con timeout de 3s
- `set_mode()` valida contra `master.mode_mapping()` del autopiloto
- `takeoff()` automáticamente cambia a GUIDED y arma si es necesario
- `goto_position()` usa `SET_POSITION_TARGET_GLOBAL_INT` para navegación
- `emergency_stop()` escalada: RTL → LAND → DISARM forzado

### 6.7 Módulo RC Override

El archivo `rc_override.py` implementa `RCOverrideController`:

- Thread independiente que envía `RC_CHANNELS_OVERRIDE` a 10 Hz
- Convierte valores normalizados (-1.0 a 1.0, throttle 0.0 a 1.0) a PWM (1000-2000)
- `reset_controls()` libera todos los canales (envía 0 = release)
- Sincronización con lock para acceso thread-safe a valores

### 6.8 Módulo de Geo Utils

El archivo `geo_utils.py` proporciona:

- `relative_to_gps()`: Convierte desplazamiento (forward, right, up) en coordenadas GPS absolutas usando latitud, longitud y yaw actuales
- `waypoints_relative_to_gps()`: Convierte lista de waypoints relativos acumulativos a absolutos

**Fórmula de transformación:**
```
dx = forward * cos(yaw) - right * sin(yaw)
dy = forward * sin(yaw) + right * cos(yaw)
new_lat = lat + (dx / 111320.0)
new_lon = lon + (dy / (111320.0 * cos(lat_rad)))
```

---

## 7. App Móvil (React Native)

### 7.1 Arquitectura de la App

La app sigue el patrón de Context API de React para el estado global. El `DroneProvider` envuelve toda la aplicación y proporciona:

- **Telemetría en vivo:** Actualizada vía WebSocket a 10 Hz
- **Cola de comandos:** Promesas que se resuelven cuando llega el ACK del servidor
- **Modo Demo:** Simulación local cuando no hay conexión WebSocket
- **RC Heartbeat:** Envío continuo de valores de joystick a 10 Hz

### 7.2 Manejo de Conexión

El `DroneContext.tsx` implementa:

1. Intento de conexión WebSocket al montar el componente
2. Si falla tras 5s, activa modo demo automático
3. Reconexión automática cada 3s tras desconexión
4. Timeout de 5s para comandos sin respuesta
5. Fallback a demo handler para todos los comandos

### 7.3 Pantallas

#### DroneControlScreen
- Video stream en vivo desde la cámara (vía WebView)
- HUD superpuesto: altitud, velocidad, batería, satélites, yaw
- Crosshair central con esquinas
- Barra de altitud vertical animada
- Joysticks virtuales: izquierdo (throttle/yaw), derecho (pitch/roll)
- Botones tácticos: ARMAR, DESPEGUE, ATERRIZAJE, SOS
- Panel lateral deslizante con modos de vuelo agrupados
- Botones de acción rápida: FRENO, HOLD POS, REBOOT
- Panel de emergencia expandible: DETENER, RTL, ATERRIZAJE

#### TelemetryScreen
- Horizonte artificial con indicación de roll/pitch
- Velocidad horizontal y vertical con barras de progreso
- Datos de posición: altitud, latitud, longitud
- Estado GPS: satélites, HDOP con semáforo de calidad
- Batería: porcentaje grande, voltaje, barra con marcadores
- Modo actual y estado de armado

#### GPSScreen
- Mapa satelital/estándar con seguimiento del dron
- Marcador del dron con pulso animado
- Círculo de precisión GPS basado en HDOP
- Creación de waypoints por toque en el mapa
- Línea de ruta desde el dron hasta waypoints
- Selector de altitud para nuevos waypoints
- Calidad GPS: EXCELENTE/BUENO/REGULAR/MALO

#### WaypointScreen
- Entrada de waypoints relativos: adelante, derecha, arriba (metros)
- Lista de waypoints con navegación individual
- Botones: SUBIR misión, INICIAR misión, LIMPIAR
- Persistencia: campo de nombre + GUARDAR/CARGAR
- Carga por selección de lista o nombre directo

### 7.4 Modo Demo

El modo demo permite probar la app sin conexión a un dron real:

- Simula posición GPS cerca de Bogotá (4.7110, -74.0721)
- Genera telemetría realista con variaciones sinusoidales
- Todos los comandos responden con éxito simulado
- Cambios de modo y estado se reflejan en la UI
- Se activa automáticamente si no hay WebSocket tras 5s

### 7.5 Compilación APK

```bash
cd mobile
npm install
npx react-native build-android --mode=release
# APK en: mobile/android/app/build/outputs/apk/release/app-release.apk
```

---

## 8. Visión por Computadora

### 8.1 Detección de Objetos (YOLOv8)

El módulo `vision/detector.py` implementa la clase `VisionDetector`:

- **Modelo:** YOLOv8nano (ultralytics) - el modelo más rápido de la familia YOLOv8
- **Pesos:** `assets/models/yolov8n.pt`
- **Confianza mínima:** 0.4 (configurable)
- **80 clases COCO** con alturas conocidas para estimación de distancia

**Estimación de distancia:**
```
distance = (known_height * FOCAL_LENGTH) / bounding_box_height
```
Donde `FOCAL_LENGTH_ESTIMATE = 600.0` basado en una cámara con FOV típico.

**Zonas de seguridad:**
| Zona | Distancia | Acción |
|------|-----------|--------|
| Safe | > 5m | Monitoreo |
| Warning | 2m - 5m | Alerta visual |
| Critical | < 2m | Freno automático (BRAKE) |

### 8.2 Auto-Avoid (Frenado Automático)

El sistema de auto-avoid conecta visión con control de vuelo:

1. `VisionDetector.detect()` procesa cada frame
2. Si detecta objetos en zona `critical` (< 2m)
3. `_check_auto_avoid()` verifica si pasaron 3s desde la última emergencia
4. Ejecuta callback que cambia el dron a modo `BRAKE`
5. Sistema configurado en `main.py` startup

### 8.3 Cámara RealSense

La clase `RealSenseCamera` en `camera_stream.py`:

- Auto-detección de dispositivo (prueba índices 4, 2, 0, 1, 3, 5)
- Resolución: 640×480 @ 30fps
- Thread de captura continuo
- Detección en cada frame con overlay
- HUD superpuesto: altitud, velocidad, batería, modo, estado ARM
- Crosshair central

**Endpoints de cámara:**
- Streaming MJPEG: `GET /api/camera/stream`
- WebSocket base64: `ws://host:8000/api/camera/ws` (25fps)
- Snapshot: `GET /api/camera/snapshot`
- Página de visión: `GET /api/camera/view`

### 8.4 Marcadores ArUco

Los marcadores ArUco se generan con `scripts/gen_markers.py` y se almacenan en `assets/markers/`. Se utilizan para:

- Calibración de cámara
- Puntos de referencia visuales
- Aterrizaje en plataforma (futuro)

---

## 9. Simulación

### 9.1 Modos de Simulación

El sistema soporta cuatro modos de simulación:

| Modo | Configuración MAVLINK_DEVICE | Descripción |
|------|------------------------------|-------------|
| **Simulador Interno** | `SIM` | Simulador Python ligero sin dependencias externas |
| **Dron Virtual** | `tcp:127.0.0.1:14551` | `sim_drone.py` - bidireccional, realista |
| **SITL Completo** | `udpin:0.0.0.0:14550` | ArduPilot SITL + QGroundControl |
| **SITL + Bridge** | `tcp:127.0.0.1:14551` | SITL con puente WSL |

### 9.2 Simulador Interno (`_SimulatedController`)

Implementado en `controller.py`, simula un dron sin MAVLink real:

- Estado simulado: GPS, batería, actitud, altitud
- Loop de tick que varía altitud en GUIDED
- Descarga de batería durante armado
- Responde a todos los comandos: ARM, DISARM, TAKEOFF, LAND, RTL, GOTO, misiones
- Ideal para pruebas de API y frontend sin hardware

### 9.3 Dron Virtual Bidireccional (`sim_drone.py`)

Script Python independiente que emula un dron ArduPilot:

- **Comunicación:** UDP con QGC (14550), TCP con backend (14551)
- **Protocolo:** pymavlink dial v20 ardupilotmega
- **Mensajes enviados:** HEARTBEAT, VFR_HUD, GPS_RAW_INT, ATTITUDE, BATTERY_STATUS, SYS_STATUS, HOME_POSITION
- **Comandos soportados:** ARM/DISARM, TAKEOFF, LAND, RTL, GOTO, misiones, SET_MODE
- **Origen:** Bogotá, Colombia (4.7110°N, -74.0721°W, 2600m)
- **Navegación suave:** Transición gradual hacia waypoints (velocidad 5 m/s)
- **Logs:** Escribe `sim_debug.txt` en `logs/`

### 9.4 ArduPilot SITL

Simulación completa con el simulador oficial de ArduPilot:

```bash
sim_vehicle.py -v ArduCopter --console --map
```

- Modelo dinámico realista
- Parámetros completos del autopiloto
- Logs de vuelo descargables
- Requiere WSL en Windows o Linux nativo

### 9.5 Scripts de Inicio

**Windows (PowerShell):**
```powershell
.\scripts\start_all.ps1
```
Lanza:
1. `sim_drone.py` en ventana separada
2. Backend FastAPI en `http://localhost:8000`

**Linux/Mac:**
```bash
./scripts/start_all.sh
```

**SITL + Backend (Linux/WSL):**
```bash
./scripts/launch_sitl_and_backend.sh
```

---

## 10. Base de Datos

### 10.1 Esquema

El sistema utiliza PostgreSQL 15 con una tabla principal `telemetry`:

```sql
CREATE TABLE telemetry (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    altitude FLOAT,
    speed FLOAT,
    pitch FLOAT,
    roll FLOAT,
    yaw FLOAT,
    battery FLOAT
);
```

### 10.2 Configuración

Variables en `.env`:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=drones
DB_USER=dronix_user
DB_PASSWORD=DronixSecure2024!
DB_URL=postgresql://dronix_user:DronixSecure2024!@localhost:5432/drones
```

### 10.3 Persistencia de Telemetría

Opcional: `DroneTelemetry` guarda snapshots periódicamente (configurable con `persist_interval`). Si la BD no está disponible, el sistema continúa funcionando sin ella.

### 10.4 Persistencia de Waypoints

Los waypoints se guardan como archivos JSON en `data/waypoints/`:
```
data/waypoints/
├── default.json        # {"forward": 10, "right": 5, "up": 3}
├── mision_circular.json
└── ruta_segura.json
```

Cada archivo contiene un array de objetos `{forward, right, up}` que representan desplazamientos relativos.

---

## 11. Seguridad

### 11.1 Consideraciones de Seguridad

El sistema está diseñado para entornos controlados (investigación, desarrollo). Las siguientes consideraciones aplican:

- **CORS abierto:** `allow_origins=["*"]` - para facilitar desarrollo, debe restringirse en producción
- **Sin autenticación:** No hay mecanismo de login/token implementado
- **Emergencia por visión:** El auto-avoid puede activar BRAKE automáticamente
- **Timeout de comandos:** 5s timeout en comandos WebSocket, 3s en wait_ack MAVLink
- **KILL switch:** Endpoint `POST /api/emergency {"action": "KILL"}` detiene motores inmediatamente
- **Protección de altitud:** Takeoff limitado entre 2m y 100m
- **Validación de modos:** Solo modos en `VALID_MODES` son aceptados

### 11.2 Buenas Prácticas

- No exponer el puerto 8000 a internet sin autenticación
- Usar Docker con redes internas para aislar servicios
- En Raspberry Pi, restringir acceso por firewall
- No compartir `.env` con contraseñas en repositorios públicos

---

## 12. Despliegue

### 12.1 Local (Desarrollo)

**Backend:**
```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**App Móvil:**
```bash
cd mobile
npm install
npx react-native start
npx react-native run-android
```

**Simulación:**
```powershell
.\scripts\start_all.ps1     # Windows
./scripts/start_all.sh      # Linux/Mac
```

### 12.2 Docker

```bash
docker-compose up --build -d
```

Servicios:
- **postgres:** base de datos
- **backend:** FastAPI en puerto 8000
- **frontend:** Next.js en puerto 4545

Para Raspberry Pi:
- Backend compilado para `linux/amd64`
- Frontend y PostgreSQL para `linux/arm64/v8`

### 12.3 Raspberry Pi

```bash
chmod +x scripts/deploy_raspberry.sh
./scripts/deploy_raspberry.sh
```

Script de despliegue automatizado que:
1. Instala dependencias del sistema
2. Configura VirtualEnv de Python
3. Instala requirements
4. Configura PostgreSQL
5. Crea tablas
6. Inicia el backend como servicio systemd

### 12.4 Dispositivo Real (Pixhawk)

1. Conectar Pixhawk vía USB
2. Configurar `.env`:
   ```env
   MAVLINK_DEVICE=/dev/ttyACM0
   MAVLINK_BAUD=115200
   ```
3. Iniciar backend
4. Conectar app móvil a la IP del servidor

---

## 13. Pruebas

### 13.1 Scripts de Prueba

El directorio `scripts/` contiene numerosos scripts de prueba:

| Script | Propósito |
|--------|-----------|
| `test_connection.py` | Verificar conexión MAVLink básica |
| `test_arm_direct.py` | Probar comando ARM |
| `test_gps_fix.py` | Verificar calidad de fix GPS |
| `test_gps_debug.py` | Depuración de datos GPS |
| `test_sitl_arm.py` | ARM/DISARM en SITL |
| `test_sitl_full.py` | Prueba completa SITL |
| `test_sitl_guided.py` | Navegación GUIDED en SITL |
| `test_websocket.py` | Prueba de comunicación WebSocket |
| `test_pymav_udp.py` | Conexión UDP con pymavlink |
| `test_all_in_one.py` | Suite de pruebas integral |
| `test_aruco.py` | Detección de marcadores ArUco |
| `test_simple_mission.py` | Misión simple con waypoints GPS |

### 13.2 Uso de Pruebas

```bash
# Probar conexión básica
python scripts/test_connection.py

# Probar SITL completo (requiere SITL corriendo)
python scripts/test_sitl_full.py

# Probar WebSocket
python scripts/test_websocket.py
```

---

## 14. Mantenimiento y Troubleshooting

### 14.1 Problemas Comunes

| Problema | Causa | Solución |
|----------|-------|----------|
| "No se puede conectar" | MAVLINK_DEVICE incorrecto | Verificar `.env` y conexión USB |
| WebSocket no conecta | IP incorrecta en config.ts | Actualizar `HOST_IP` en `mobile/src/config.ts` |
| Modo "UNKNOWN" | Mapeo de custom_mode falla | Verificar que SITL esté enviando heartbeats |
| Cámara no inicia | RealSense no conectada | El backend continúa sin cámara |
| Errores BD | PostgreSQL no disponible | No crítico para vuelo |
| Joystick sin respuesta | RC Override no iniciado | Verificar `rc.start()` en controller.py |
| Misión no sube | Race en _read_loop | Usa `pause_read()` que ya está implementado |

### 14.2 Logs

Los logs se escriben en `logs/`:

| Archivo | Origen | Descripción |
|---------|--------|-------------|
| `backend.log` | Backend | Log principal del servidor |
| `sim_debug.txt` | sim_drone.py | Comandos SET_MODE recibidos |
| `sim_udp_errors.txt` | sim_drone.py | Errores UDP |
| `rc_cmd.json` | Backend | Últimos valores RC |
| `err*.txt` | Pruebas | Stderr capturado |
| `out*.txt` | Pruebas | Stdout capturado |

### 14.3 Docker Troubleshooting

```bash
# Ver logs del backend
docker-compose logs -f backend

# Verificar conectividad de red
docker-compose exec backend ping postgres

# Resetear base de datos
docker-compose down -v
docker-compose up -d
```

---

## 15. Conclusiones

### 15.1 Logros Técnicos

1. **Protocolo MAVLink completo:** Implementación bidireccional con soporte para comandos, telemetría y misiones
2. **Arquitectura desacoplada:** Backend independiente del cliente, múltiples opciones de conexión
3. **Tiempo real:** WebSocket a 10 Hz para telemetría, RC override a 10 Hz
4. **Visión artificial:** YOLOv8n con detección en tiempo real y auto-avoid
5. **Simulación versátil:** Cuatro modos de simulación para diferentes necesidades
6. **Multiplataforma:** Windows, Linux, Raspberry Pi, Docker
7. **Persistencia:** Waypoints guardados en disco para reutilización

### 15.2 Trabajo Futuro

- Implementar autenticación y autorización
- Agregar encriptación WebSocket (WSS)
- Soporte para múltiples drones simultáneos
- Integración con seguimiento GPS en tiempo real (telemetría push)
- Algoritmos de evitación de obstáculos más sofisticados
- Modo follow-me con geocerca
- Grabación y reproducción de misiones
- Integración con ROS 2
- Soporte para cámara térmica/multiespectral

### 15.3 Referencias

- [MAVLink Protocol](https://mavlink.io/en/)
- [ArduPilot Documentation](https://ardupilot.org/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [React Native](https://reactnative.dev/)
- [YOLOv8 by Ultralytics](https://github.com/ultralytics/ultralytics)
- [pymavlink](https://github.com/ArduPilot/pymavlink)
- [Intel RealSense](https://www.intelrealsense.com/)
