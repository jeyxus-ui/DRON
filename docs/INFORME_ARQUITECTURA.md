# Informe de Arquitectura
## Sistema de Control y Telemetría para Drones

**Versión:** 1.0.0  
**Fecha:** Mayo 2026

---

## 1. Resumen

Este informe detalla la arquitectura de software del sistema de control y telemetría para drones. Describe las decisiones de diseño, la estructura de componentes, los patrones arquitectónicos utilizados y los flujos de datos entre módulos.

---

## 2. Decisiones de Diseño

### 2.1 Arquitectura Cliente-Servidor con Comunicación en Tiempo Real

**Decisión:** Se optó por una arquitectura cliente-servidor donde el backend actúa como intermediario entre el dron (hardware/simulación) y los clientes (app móvil, frontend web).

**Justificación:**
- El dron no puede exponer directamente servicios HTTP/WebSocket
- MAVLink es un protocolo de baja potencia diseñado para enlaces de radio
- El backend puede gestionar múltiples clientes simultáneamente
- Permite agregar procesamiento (visión, persistencia) sin modificar el dron

### 2.2 API REST + WebSocket

**Decisión:** Se implementaron dos canales de comunicación: REST para consultas/acciones puntuales y WebSocket para telemetría continua y comandos en tiempo real.

**Justificación:**
- REST: ideal para consultas de estado, configuraciones y operaciones CRUD
- WebSocket: necesario para telemetría a 10 Hz sin overhead HTTP
- Los comandos importantes (ARM, TAKEOFF) usan WebSocket con ACK confirmado
- Los comandos continuos (RC_CONTROL) no requieren ACK para evitar saturación

### 2.3 Simulador Interno vs Externo

**Decisión:** Se implementaron cuatro niveles de simulación: interno (SIM), virtual (sim_drone.py), SITL completo y SITL con bridge.

**Justificación:**
- SIM: pruebas de API y frontend sin dependencias (no requiere pymavlink real)
- sim_drone.py: pruebas más realistas con comunicación MAVLink real
- SITL: pruebas de vuelo realistas con modelo dinámico ArduPilot
- SITL + bridge: integración con QGroundControl para depuración visual

### 2.4 Persistencia de Waypoints en JSON

**Decisión:** Los waypoints se guardan como archivos JSON en lugar de base de datos.

**Justificación:**
- Simplicidad: no requiere conexión a BD
- Portabilidad: los archivos se pueden copiar entre servidores
- Legibilidad: formato JSON plano fácil de inspeccionar y editar
- Suficiente: los waypoints son datos pequeños (< 100KB típicamente)

### 2.5 Mapeo de Modos ArduPilot

**Decisión:** Se implementó un mapeo manual de `custom_mode` numérico a nombre de modo, junto con validación contra `master.mode_mapping()`.

**Justificación:**
- `mode_string_v10()` de pymavlink no siempre traduce correctamente
- El mapeo numérico es estable entre versiones de ArduPilot
- La validación contra `mode_mapping()` evita modos inválidos
- Soporta todos los modos de Copter (0-23)

### 2.6 Threading y Protección contra Race Conditions

**Decisión:** Se utilizó un modelo de threading con locks específicos para lectura/escritura, y un mecanismo de pausa para operaciones de misión.

**Justificación:**
- MAVLink requiere un thread de lectura continuo para no perder heartbeats
- Los comandos necesitan acceso exclusivo al canal de envío
- `pause_read()` evita que el thread de lectura consuma mensajes de misión
- `recv_match()` sin lock previene deadlocks con `wait_ack()`
- `_pending_msgs` almacena mensajes capturados durante pausa

---

## 3. Diagrama de Componentes

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTES                                      │
│                                                                            │
│  ┌───────────────────┐  ┌──────────────────┐  ┌────────────────────────┐ │
│  │   App React Native│  │  Frontend Next.js│  │   QGroundControl       │ │
│  │   (Android, iOS)  │  │  (Web Dashboard) │  │   (Estación Tierra)    │ │
│  └────────┬──────────┘  └────────┬─────────┘  └───────────┬────────────┘ │
│           │                      │                        │              │
│      WS JSON                HTTP REST                  MAVLink UDP       │
└───────────┼──────────────────────┼────────────────────────┼──────────────┘
            │                      │                        │
┌───────────┼──────────────────────┼────────────────────────┼──────────────┐
│           │                      │                        │              │
│  ┌────────┴──────────────────────┴────────────────────────┴──────────┐   │
│  │                       FASTAPI BACKEND                              │   │
│  │                                                                    │   │
│  │  ┌────────────────────────────────────────────────────────────┐   │   │
│  │  │                     REST Router (/api)                     │   │   │
│  │  │  /status, /telemetry, /arm, /disarm, /takeoff, /land,     │   │   │
│  │  │  /rtl, /goto, /mode, /emergency, /rc/*, /waypoints/*      │   │   │
│  │  └───────────────────────────┬────────────────────────────────┘   │   │
│  │                              │                                    │   │
│  │  ┌───────────────────────────┴────────────────────────────────┐   │   │
│  │  │                    WebSocket Router                        │   │   │
│  │  │  /ws/telemetry: telemetry broadcast + command processing   │   │   │
│  │  │  /api/camera/ws: video streaming (base64, 25fps)           │   │   │
│  │  └───────────────────────────┬────────────────────────────────┘   │   │
│  │                              │                                    │   │
│  │  ┌───────────────────────────┴────────────────────────────────┐   │   │
│  │  │                   MAVController                             │   │   │
│  │  │  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐    │   │   │
│  │  │  │DroneCommands│ │DroneTelemetry│ │RCOverrideController│   │   │   │
│  │  │  │ - arm       │ │ - read_loop  │ │ - send_loop 10Hz  │   │   │   │
│  │  │  │ - takeoff   │ │ - getters    │ │ - normalize→PWM   │   │   │   │
│  │  │  │ - goto      │ │ - persist    │ │ - release control │   │   │   │
│  │  │  │ - mission   │ │ - preflight  │ │                   │   │   │   │
│  │  │  └──────┬──────┘ └──────┬───────┘ └────────┬─────────┘   │   │   │
│  │  │         │               │                   │             │   │   │
│  │  │  ┌──────┴───────────────┴───────────────────┴──────────┐  │   │   │
│  │  │  │              MAVLinkConnection                       │  │   │   │
│  │  │  │  connect/reconnect/disconnect                        │  │   │   │
│  │  │  │  send_command (with lock)                            │  │   │   │
│  │  │  │  recv_match (without lock)                           │  │   │   │
│  │  │  │  wait_ack / recv_match_protected                     │  │   │   │
│  │  │  │  pause_read context manager                          │  │   │   │
│  │  │  └──────────────────────┬───────────────────────────────┘  │   │   │
│  │  └─────────────────────────┼─────────────────────────────────┘   │   │
│  │                            │                                      │   │
│  │  ┌─────────────────────────┴─────────────────────────────────┐   │   │
│  │  │  VisionDetector + RealSenseCamera                        │   │   │
│  │  │  - YOLOv8n detection                                     │   │   │
│  │  │  - Auto-avoid (BRAKE on critical)                        │   │   │
│  │  │  - ArUco markers                                         │   │   │
│  │  └─────────────────────────────────────────────────────────┘   │   │
│  │                                                                    │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                    Simulador Interno                        │   │   │
│  │  │  _SimulatedController: estado virtual, tick loop,           │   │   │
│  │  │  responde a todos los comandos sin MAVLink real             │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┬─────────────────┐
          │                │                │                 │
     ┌────┴────┐     ┌────┴────┐     ┌─────┴──────┐    ┌────┴────┐
     │ Pixhawk │     │  SITL   │     │sim_drone.py│    │PostgreSQL│
     │ Serial  │     │ TCP/UDP │     │  TCP+UDP   │    │   BD     │
     └─────────┘     └─────────┘     └────────────┘    └─────────┘
```

---

## 4. Patrones Arquitectónicos

### 4.1 Patrón Observador (Observer)

**Implementación:** WebSocket broadcast de telemetría

El `ConnectionManager` en `websocket.py` implementa el patrón observador:
- **Sujeto:** `telemetry_broadcaster()` genera datos cada 100ms
- **Observadores:** Todos los clientes WebSocket conectados
- **Actualización:** `manager.broadcast()` envía a todos los clientes simultáneamente

### 4.2 Patrón Fachada (Facade)

**Implementación:** `MAVController`

`MAVController` actúa como fachada que unifica:
- `MAVLinkConnection` (conexión)
- `DroneCommands` (comandos)
- `DroneTelemetry` (telemetría)
- `RCOverrideController` (control manual)
- `_SimulatedController` (simulación)

La API REST y WebSocket solo interactúan con `MAVController`, sin conocer los detalles internos.

### 4.3 Patrón Estrategia (Strategy)

**Implementación:** Múltiples modos de conexión MAVLink

La estrategia de conexión se selecciona según `MAVLINK_DEVICE`:
- `SIM` → Simulador interno (no usa pymavlink)
- `tcp:*` → Conexión TCP
- `udpin:*` / `udpout:*` → Conexión UDP
- `/dev/tty*` → Conexión serial

### 4.4 Patrón Productor-Consumidor

**Implementación:** Thread de telemetría

- **Productor:** `_read_loop()` en `DroneTelemetry` (100 Hz)
- **Buffer:** `self.data` (diccionario compartido thread-safe)
- **Consumidores:** `get_all()`, `get_status()`, WebSocket broadcast, persistencia BD

### 4.5 Patrón Comando (Command)

**Implementación:** Procesamiento de comandos WebSocket

`process_command()` en `websocket.py` implementa un dispatch table:
```python
if cmd_type == "ARM":     → arm()
elif cmd_type == "TAKEOFF": → takeoff()
elif cmd_type == "LAND":  → land()
# ...
```

Cada comando se encapsula en una función que `MAVController` ejecuta.

---

## 5. Flujos de Datos

### 5.1 Flujo de Telemetría (10 Hz)

```
Pixhawk/SITL
    │
    │ MAVLink messages (VFR_HUD, GPS_RAW_INT, ATTITUDE, etc.)
    ▼
MAVLinkConnection._read_loop (thread, 100 Hz)
    │
    │ msg = master.recv_match()
    ▼
DroneTelemetry._process_message(msg)
    │
    │ Actualiza self.data
    ▼
self.data (diccionario compartido)
    │
    ├──► DroneTelemetry.get_all()
    │       │
    │       ▼
    │   WebSocket broadcast (10 Hz)
    │       │
    │       ▼
    │   App Móvil / Frontend Web
    │
    ├──► DroneTelemetry.preflight_checks() (bajo demanda)
    │
    └──► DroneTelemetry._persist_loop() (cada 5s, opcional)
            │
            ▼
        PostgreSQL (save_telemetry)
```

### 5.2 Flujo de Comando (Bajo Demanda)

```
App Móvil
    │
    │ WebSocket JSON: {"type": "ARM", "params": {}}
    ▼
websocket_endpoint()
    │
    │ process_command(message, mav_controller)
    ▼
process_command()
    │
    │ cmd_type = "ARM"
    ▼
mav_controller.arm()
    │
    │ self.cmd.arm(force=True)
    ▼
DroneCommands.arm()
    │
    │ with self.conn._lock:
    │     master.mav.command_long_send(MAV_CMD_COMPONENT_ARM_DISARM, ...)
    ▼
MAVLinkConnection (envío con lock)
    │
    │ command_long_send → Pixhawk/SITL
    ▼
    │ Espera COMMAND_ACK (wait_ack, timeout 3s)
    │
    ├──► ACK recibido → return True
    │       │
    │       ▼
    │   manager.send({"type": "command_ack", "command": "ARM", "result": {"success": true}})
    │
    └──► Timeout → return False
            │
            ▼
        manager.send({"type": "command_ack", "command": "ARM", "result": {"success": false}})
```

### 5.3 Flujo de Misión (Upload)

```
App Móvil (WaypointScreen)
    │
    │ WebSocket: MISSION_UPLOAD_RELATIVE con waypoints [{forward, right, up}]
    ▼
process_command()
    │
    │ waypoints_relative_to_gps(lat, lon, alt, yaw, rel_wps)
    ▼
    │ waypoints absolutos [{lat, lon, alt}, ...]
    │
    │ mav_controller.upload_mission(abs_wps)
    ▼
MAVController.upload_mission()
    │
    │ with conn.pause_read():  # Pausa _read_loop
    │     _do_upload_mission(waypoints)
    ▼
MAVLinkConnection (envío MISSION_COUNT)
    │
    │ Pixhawk responde MISSION_REQUEST_INT(seq=0)
    ▼
MAVLinkConnection (envío MISSION_ITEM_INT seq=0)
    │
    │ Pixhawk responde MISSION_REQUEST_INT(seq=1)
    ▼
    ... (repite para cada waypoint)
    │
    │ Último waypoint: espera MISSION_ACK
    ▼
✅ Misión subida correctamente
```

### 5.4 Flujo de Visión con Auto-Avoid

```
RealSenseCamera._capture_loop (thread, 30fps)
    │
    │ cap.read() → frame
    ▼
VisionDetector.detect(frame)
    │
    │ YOLOv8n inference
    │ Estimación de distancia por bounding box
    │ Clasificación en safe / warning / critical
    ▼
    │ detections: [Detection, ...]
    │
    ├──► camera_stream._check_auto_avoid(detections)
    │       │
    │       │ ¿Hay objetos en zona "critical"?
    │       │ ¿Pasaron 3s desde última emergencia?
    │       ▼
    │   _emergency_callback() → mav.set_mode("BRAKE")
    │
    └──► detector.draw_overlay(frame, detections)
            │
            ▼
        camera.current_frame = overlay (con bounding boxes)
            │
            ├──► GET /api/camera/snapshot
            ├──► WS /api/camera/ws (base64, 25fps)
            └──► GET /api/camera/stream (MJPEG)
```

---

## 6. Estructura de Datos

### 6.1 Telemetría (WebSocket)

```typescript
interface Telemetry {
  armed:             boolean;   // Motores armados
  mode:              string;    // Modo de vuelo (STABILIZE, GUIDED, etc.)
  altitude:          number;    // Altitud (m)
  latitude:          number;    // Latitud (° decimal)
  longitude:         number;    // Longitud (° decimal)
  roll:              number;    // Roll (°)
  pitch:             number;    // Pitch (°)
  yaw:               number;    // Yaw (°)
  battery_voltage:   number;    // Voltaje de batería (V)
  battery_current:   number;    // Corriente (A)
  battery_remaining: number;    // Batería restante (%)
  ground_speed:      number;    // Velocidad horizontal (m/s)
  vertical_speed:    number;    // Velocidad vertical (m/s)
  satellites:        number;    // Satélites visibles
  hdop:              number;    // Precisión horizontal
}
```

### 6.2 Waypoint Relativo

```typescript
interface RelativeWaypoint {
  forward: number;  // Metros hacia adelante
  right:   number;  // Metros hacia la derecha
  up:      number;  // Metros hacia arriba
}
```

### 6.3 Waypoint Absoluto

```typescript
interface AbsoluteWaypoint {
  lat: number;  // Latitud (° decimal)
  lon: number;  // Longitud (° decimal)
  alt: number;  // Altitud (m)
}
```

### 6.4 Detección de Visión

```typescript
interface Detection {
  class_id:   number;  // ID de clase COCO
  label:      string;  // Nombre de la clase (person, car, etc.)
  confidence: number;  // Confianza (0-1)
  bbox: {              // Bounding box en píxeles
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  };
  distance:   number;  // Distancia estimada (m)
  zone:       string;  // Zona: "safe" | "warning" | "critical"
}
```

### 6.5 Estado del Dron (REST)

```typescript
interface DroneStatus {
  connected:     boolean;  // Conexión MAVLink activa
  armed:         boolean;  // Motores armados
  mode:          string;   // Modo de vuelo
  system_status: number;   // Estado del sistema MAVLink
}
```

---

## 7. Puertos y Conexiones de Red

| Puerto | Protocolo | Servicio | Dirección |
|--------|-----------|----------|-----------|
| 8000 | HTTP/WS | Backend API (REST + WebSocket) | Cliente → Servidor |
| 4545 | HTTP | Frontend Next.js (Dashboard web) | Cliente → Servidor |
| 5432 | PostgreSQL | Base de datos | Backend → BD |
| 14550 | UDP | Telemetría QGroundControl | SIM → QGC |
| 14551 | TCP | Conexión backend con sim_drone | SIM → Backend |
| 14552 | UDP | Puerto origen sim_drone | SIM → QGC |

---

## 8. Consideraciones de Rendimiento

### 8.1 Telemetría a 10 Hz

- El broadcast WebSocket envía ~500 bytes por mensaje a 10 Hz ≈ 5 KB/s por cliente
- Con 10 clientes concurrentes: ~50 KB/s de ancho de banda de salida
- La codificación JSON tiene overhead mínimo

### 8.2 Streaming de Video

- WebSocket base64: ~30-50 KB por frame (JPEG calidad 75, 480×360)
- A 25 fps: ~750-1250 KB/s por cliente
- MJPEG: similar overhead
- Se recomienda limitar a 1-2 clientes de video simultáneos

### 8.3 Threading

| Thread | Frecuencia | Función |
|--------|------------|---------|
| Telemetría read_loop | 100 Hz | Lectura de mensajes MAVLink |
| Telemetría persist | 0.2 Hz (cada 5s) | Guardado en BD |
| RC Override send_loop | 10 Hz | Envío de override RC |
| Monitoreo conexión | 0.2 Hz (cada 5s) | Verificar conectividad |
| Captura cámara | 30 fps | Captura y detección |
| Broadcast WebSocket | 10 Hz | Envío de telemetría |

### 8.4 YOLOv8 Inferencia

- YOLOv8n es el modelo más rápido (~5-10ms por frame en GPU, ~30-50ms en CPU)
- En Raspberry Pi, la inferencia puede tomar 100-200ms por frame
- Se recomienda GPU NVIDIA para despliegue en producción con visión

---

## 9. Escalabilidad

### 9.1 Limitaciones Actuales

- **Cliente único de video:** El WebSocket de cámara envía a todos los conectados, pero el ancho de banda puede saturarse
- **Dron único:** El sistema está diseñado para controlar un dron a la vez
- **Threading:** El modelo actual usa threads de Python (GIL limitante para CPU-bound)
- **Sin caché:** Las consultas REST consultan el estado en vivo cada vez

### 9.2 Mejoras Propuestas

- **Múltiples drones:** Instanciar múltiples `MAVController` con identificadores
- **AsyncIO completo:** Migrar a asyncio para operaciones I/O bound
- **Redis caché:** Cachear último snapshot de telemetría para REST
- **CDN para video:** Usar RTMP/HLS para streaming de video escalable
- **Autenticación JWT:** Para entornos multi-usuario

---

## 10. Dependencias Externas

### 10.1 Backend (Python)

| Dependencia | Versión | Propósito |
|-------------|---------|-----------|
| fastapi | 0.104.1 | Framework web ASGI |
| uvicorn | 0.24.0 | Servidor ASGI |
| pymavlink | 2.4.41 | Protocolo MAVLink |
| sqlalchemy | 2.0.23 | ORM PostgreSQL |
| psycopg2-binary | 2.9.9 | Driver PostgreSQL |
| pyserial | 3.5 | Comunicación serial |
| python-dotenv | 1.0.0 | Variables de entorno |
| pydantic | 2.5.0 | Validación de datos |
| websockets | 11.0.3 | WebSocket nativo |
| opencv-python | 4.8.1 | Procesamiento de video |
| ultralytics | - | YOLOv8 |
| numpy | ≥1.26 | Cómputo numérico |

### 10.2 Mobile (React Native)

| Dependencia | Versión | Propósito |
|-------------|---------|-----------|
| react-native | 0.83.1 | Framework móvil |
| react-native-maps | 1.27.1 | Mapas GPS |
| react-native-safe-area-context | 5.5.2 | Área segura |
| react-native-webview | 13.16.1 | Stream de video |
| axios | 1.13.5 | Peticiones HTTP |
| TypeScript | 5.8 | Tipado estático |

---

## 11. Convenciones de Código

### 11.1 Backend (Python)

- Nombres de clases: `PascalCase` (`MAVController`, `DroneCommands`)
- Nombres de funciones/variables: `snake_case` (`send_command`, `_read_loop`)
- Constantes: `UPPER_SNAKE_CASE` (`VALID_MODES`, `PWM_MIN`)
- Métodos privados: prefijo `_` (`_do_upload_mission`)
- Type hints: obligatorios en funciones públicas
- Logging: módulo `logging` estándar con `getLogger(__name__)`

### 11.2 Mobile (TypeScript)

- Nombres de componentes: `PascalCase` (`DroneControlScreen`)
- Nombres de archivos: `PascalCase` para componentes (`TelemetryScreen.tsx`)
- Interfaces: `PascalCase` (`CommandResult`, `Telemetry`)
- Funciones: `camelCase` (`sendCommand`, `loadNamedWaypoints`)
- Constantes: `UPPER_SNAKE_CASE` (`API_URL`, `WS_URL`)
- Hooks: prefijo `use` (`useDrone`, `useState`)
- Estilos: `StyleSheet.create()` con nombres `camelCase`

---

## 12. Manejo de Errores

### 12.1 Backend

- **Conexión MAVLink:** Reintentos con backoff exponencial (5 intentos)
- **Cámara no disponible:** Fallback silencioso, backend continúa sin cámara
- **Base de datos no disponible:** Desactivar persistencia, loguear warning
- **Comandos fallidos:** Retornar `{"success": false, "message": "..."}` al cliente
- **Timeouts:** `wait_ack()` timeout 3s, comando WebSocket timeout 5s
- **Excepciones no capturadas:** HTTPException 500 con detail del error

### 12.2 Mobile

- **WebSocket cerrado:** Reconexión automática cada 3s
- **Timeout de comando:** 5s, retorna error al usuario
- **Modo demo:** Activación automática si no hay conexión en 5s
- **Alertas:** Todos los errores se muestran al usuario via `Alert.alert()`
- **RC_CONTROL:** No requiere ACK (evita saturación a 10 Hz)
