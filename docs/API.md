# Referencia de API
## REST + WebSocket - Sistema de Control de Drones

**Versión:** 1.0.0  
**Base URL:** `http://<host>:8000`  
**WebSocket:** `ws://<host>:8000/ws/telemetry`

---

## 1. API REST

### 1.1 Estado y Telemetría

---

#### `GET /` — Información del servidor

```bash
curl http://localhost:8000/
```

```json
{
  "message": "Drone Control API",
  "version": "1.0.0",
  "status": "running"
}
```

---

#### `GET /health` — Health check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy"
}
```

---

#### `GET /api/status` — Estado del dron

```bash
curl http://localhost:8000/api/status
```

```json
{
  "connected": true,
  "armed": false,
  "mode": "STABILIZE",
  "system_status": 4
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| connected | bool | Conexión MAVLink activa |
| armed | bool | Motores armados |
| mode | string | Modo de vuelo actual |
| system_status | int | Estado del sistema MAVLink |

---

#### `GET /api/telemetry` — Telemetría completa

```bash
curl http://localhost:8000/api/telemetry
```

```json
{
  "armed": false,
  "mode": "STABILIZE",
  "altitude": 0,
  "latitude": 4.711,
  "longitude": -74.0721,
  "roll": 0.0,
  "pitch": 0.0,
  "yaw": 45.2,
  "battery_voltage": 12.6,
  "battery_remaining": 85,
  "ground_speed": 0,
  "vertical_speed": 0,
  "satellites": 10,
  "hdop": 0.8
}
```

| Campo | Tipo | Unidad | Fuente MAVLink |
|-------|------|--------|----------------|
| armed | bool | - | HEARTBEAT.base_mode |
| mode | string | - | HEARTBEAT (custom_mode) |
| altitude | float | m | VFR_HUD.alt |
| latitude | float | ° | GPS_RAW_INT.lat / 1e7 |
| longitude | float | ° | GPS_RAW_INT.lon / 1e7 |
| roll | float | ° | ATTITUDE.roll (convertido) |
| pitch | float | ° | ATTITUDE.pitch (convertido) |
| yaw | float | ° | ATTITUDE.yaw (convertido) |
| battery_voltage | float | V | BATTERY_STATUS.voltages[0] / 1000 |
| battery_remaining | int | % | BATTERY_STATUS.battery_remaining |
| ground_speed | float | m/s | VFR_HUD.airspeed |
| vertical_speed | float | m/s | VFR_HUD.climb |
| satellites | int | - | GPS_RAW_INT.satellites_visible |
| hdop | float | - | GPS_RAW_INT.eph / 100 |

---

### 1.2 Control Básico

---

#### `POST /api/arm` — Armar motores

```bash
curl -X POST http://localhost:8000/api/arm \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

```json
{
  "success": true,
  "message": "Dron armado",
  "armed": true
}
```

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| force | bool | false | Forzar armado (skip safety checks) |

---

#### `POST /api/disarm` — Desarmar motores

```bash
curl -X POST http://localhost:8000/api/disarm
```

```json
{
  "success": true,
  "message": "Dron desarmado",
  "armed": false
}
```

---

#### `POST /api/takeoff` — Despegar

```bash
curl -X POST http://localhost:8000/api/takeoff \
  -H "Content-Type: application/json" \
  -d '{"altitude": 10}'
```

```json
{
  "success": true,
  "message": "Despegando a 10m"
}
```

| Parámetro | Tipo | Default | Validación |
|-----------|------|---------|------------|
| altitude | float | 10.0 | 2m ≤ altitude ≤ 100m |

---

#### `POST /api/land` — Aterrizar

```bash
curl -X POST http://localhost:8000/api/land
```

```json
{
  "success": true,
  "message": "Aterrizando"
}
```

---

#### `POST /api/rtl` — Return to Launch

```bash
curl -X POST http://localhost:8000/api/rtl
```

```json
{
  "success": true,
  "message": "Regresando a home"
}
```

---

#### `POST /api/goto` — Navegar a coordenada

```bash
curl -X POST http://localhost:8000/api/goto \
  -H "Content-Type: application/json" \
  -d '{"latitude": 4.712, "longitude": -74.073, "altitude": 15}'
```

```json
{
  "success": true,
  "message": "Navegando a (4.712, -74.073)",
  "target": {
    "latitude": 4.712,
    "longitude": -74.073,
    "altitude": 15
  }
}
```

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| latitude | float | - | Latitud destino |
| longitude | float | - | Longitud destino |
| altitude | float | 10.0 | Altitud de navegación |

---

### 1.3 Cambio de Modo

---

#### `POST /api/mode` — Cambiar modo de vuelo

```bash
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "GUIDED"}'
```

```json
{
  "success": true,
  "message": "Modo cambiado a GUIDED",
  "mode": "GUIDED"
}
```

**Modos válidos:** `STABILIZE`, `ACRO`, `SPORT`, `DRIFT`, `ALT_HOLD`, `POSHOLD`, `LOITER`, `BRAKE`, `AUTO`, `GUIDED`, `CIRCLE`, `FLIP`, `THROW`, `RTL`, `SMARTRTL`, `LAND`

---

### 1.4 Control RC

---

#### `POST /api/rc/control` — Control manual

```bash
curl -X POST http://localhost:8000/api/rc/control \
  -H "Content-Type: application/json" \
  -d '{"throttle": 0.5, "yaw": 0, "pitch": 0.2, "roll": 0}'
```

```json
{
  "success": true,
  "message": "Controles RC actualizados",
  "values": {
    "throttle": 0.5,
    "yaw": 0,
    "pitch": 0.2,
    "roll": 0,
    "throttle_pwm": 1500,
    "yaw_pwm": 1500,
    "pitch_pwm": 1600,
    "roll_pwm": 1500
  }
}
```

| Parámetro | Tipo | Rango | Descripción |
|-----------|------|-------|-------------|
| throttle | float | 0.0 - 1.0 | Aceleración (0 = mínimo, 1 = máximo) |
| yaw | float | -1.0 - 1.0 | Giro (negativo = izquierda, positivo = derecha) |
| pitch | float | -1.0 - 1.0 | Inclinación (negativo = atrás, positivo = adelante) |
| roll | float | -1.0 - 1.0 | Rolido (negativo = izquierda, positivo = derecha) |

---

#### `POST /api/rc/reset` — Resetear controles

```bash
curl -X POST http://localhost:8000/api/rc/reset
```

```json
{
  "success": true,
  "message": "Controles RC reseteados"
}
```

---

#### `GET /api/rc/values` — Valores actuales RC

```bash
curl http://localhost:8000/api/rc/values
```

```json
{
  "success": true,
  "values": {
    "throttle": 0,
    "yaw": 0,
    "pitch": 0,
    "roll": 0,
    "throttle_pwm": 1000,
    "yaw_pwm": 1500,
    "pitch_pwm": 1500,
    "roll_pwm": 1500
  }
}
```

---

### 1.5 Emergencias

---

#### `POST /api/emergency` — Acción de emergencia

```bash
# STOP (BRAKE/LOITER)
curl -X POST http://localhost:8000/api/emergency \
  -H "Content-Type: application/json" \
  -d '{"action": "STOP"}'

# Return to Launch
curl -X POST http://localhost:8000/api/emergency \
  -H "Content-Type: application/json" \
  -d '{"action": "RTL"}'

# Aterrizaje de emergencia
curl -X POST http://localhost:8000/api/emergency \
  -H "Content-Type: application/json" \
  -d '{"action": "LAND"}'

# Muerte de motores (PELIGROSO)
curl -X POST http://localhost:8000/api/emergency \
  -H "Content-Type: application/json" \
  -d '{"action": "KILL"}'
```

```json
{
  "success": true,
  "action": "STOP",
  "message": "STOP: modo BRAKE/LOITER activado"
}
```

| Acción | Comportamiento |
|--------|----------------|
| `STOP` | Intenta BRAKE, fallback a LOITER, resetea RC |
| `RTL` | Return to Launch |
| `LAND` | Aterrizaje inmediato |
| `KILL` | Desarma motores forzadamente (CAÍDA LIBRE) |

---

### 1.6 Waypoints (Persistencia)

---

#### `POST /api/waypoints/save` — Guardar waypoints

```bash
curl -X POST http://localhost:8000/api/waypoints/save \
  -H "Content-Type: application/json" \
  -d '{"name": "mision_circular", "waypoints": [{"forward": 10, "right": 0, "up": 0}, {"forward": 0, "right": 10, "up": 0}]}'
```

```json
{
  "success": true,
  "message": "Waypoints guardados como 'mision_circular'"
}
```

Los archivos se guardan en `data/waypoints/<name>.json`.

---

#### `POST /api/waypoints/load` — Cargar waypoints

```bash
curl -X POST http://localhost:8000/api/waypoints/load \
  -H "Content-Type: application/json" \
  -d '{"name": "mision_circular"}'
```

```json
{
  "success": true,
  "waypoints": [
    {"forward": 10, "right": 0, "up": 0},
    {"forward": 0, "right": 10, "up": 0}
  ]
}
```

---

#### `GET /api/waypoints/list` — Listar waypoints guardados

```bash
curl http://localhost:8000/api/waypoints/list
```

```json
{
  "success": true,
  "names": ["default", "mision_circular", "ruta_segura"]
}
```

---

#### `DELETE /api/waypoints/{name}` — Eliminar waypoints

```bash
curl -X DELETE http://localhost:8000/api/waypoints/mision_circular
```

```json
{
  "success": true,
  "message": "'mision_circular' eliminado"
}
```

---

### 1.7 Cámara y Visión

---

#### `GET /api/camera/snapshot` — Captura JPEG

```bash
curl http://localhost:8000/api/camera/snapshot -o frame.jpg
```

Retorna una imagen JPEG con el frame actual (con overlays de detección).

---

#### `GET /api/camera/stream` — Streaming MJPEG

```
http://localhost:8000/api/camera/stream
```

Streaming MJPEG para navegadores y reproductores compatibles.

---

#### `GET /api/camera/view` — Página HTML de visión

```
http://localhost:8000/api/camera/view
```

Página web completa con:
- Stream de video (polling cada 100ms)
- Detecciones en tiempo real
- Lista de objetos detectados
- Indicadores de zona (safe/warning/critical)

---

#### `GET /api/camera/status` — Estado de cámara

```bash
curl http://localhost:8000/api/camera/status
```

```json
{
  "running": true,
  "has_frame": true,
  "device": "/dev/video4",
  "resolution": "640x480",
  "fps": 30,
  "ws_clients": 1,
  "vision": {
    "detections": [
      {"class_id": 0, "label": "person", "confidence": 0.85, "distance": 3.2, "zone": "warning"}
    ],
    "count": 1,
    "critical_count": 0,
    "warning_count": 1
  }
}
```

---

#### `GET /api/camera/vision` — Detecciones actuales

```bash
curl http://localhost:8000/api/camera/vision
```

```json
{
  "detections": [
    {"class_id": 0, "label": "person", "confidence": 0.85, "bbox": {"x1": 100, "y1": 200, "x2": 150, "y2": 350}, "distance": 3.2, "zone": "warning"}
  ],
  "count": 1,
  "critical_count": 0,
  "warning_count": 1
}
```

---

#### `POST /api/camera/start` — Iniciar cámara

```bash
curl -X POST "http://localhost:8000/api/camera/start?width=640&height=480&fps=30"
```

```json
{
  "success": true,
  "message": "Cámara iniciada en /dev/video4"
}
```

---

#### `POST /api/camera/stop` — Detener cámara

```bash
curl -X POST http://localhost:8000/api/camera/stop
```

```json
{
  "success": true,
  "message": "Cámara detenida"
}
```

---

#### `GET /api/camera/markers/{marker_id}` — Obtener marcador ArUco

```bash
curl http://localhost:8000/api/camera/markers/42 -o marker.png
```

Retorna la imagen PNG del marcador ArUco con el ID especificado.

---

### 1.8 Rutas Adicionales (Frontend)

---

#### `GET /drones` — Listar drones

```bash
curl http://localhost:8000/drones
```

```json
[{"id": 1, "name": "Test Drone", "status": "idle", "model": "PX4"}]
```

#### `GET /missions` — Listar misiones

```bash
curl http://localhost:8000/missions
```

```json
[{"id": 1, "name": "Mission Alpha", "status": "paused", "progress_percent": 0}]
```

#### `GET /users` — Listar usuarios

```bash
curl http://localhost:8000/users
```

```json
[{"id": 1, "username": "operator", "role": "pilot"}]
```

#### `GET /flight-routes` — Listar rutas

```bash
curl http://localhost:8000/flight-routes
```

```json
[{"id": 1, "name": "Route 1", "total_distance": 1.2}]
```

---

## 2. WebSocket

### 2.1 Conexión

```
ws://<host>:8000/ws/telemetry
```

### 2.2 Mensajes Recibidos (Servidor → Cliente)

#### Telemetría (cada 100ms)

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
    "battery_current": 0.0,
    "battery_remaining": 100,
    "ground_speed": 0,
    "vertical_speed": 0,
    "satellites": 10,
    "hdop": 0.8
  },
  "timestamp": "2026-05-17T12:00:00.000000"
}
```

#### ACK de Comando

```json
{
  "type": "command_ack",
  "command": "ARM",
  "result": {
    "success": true,
    "message": "Drone armado"
  },
  "timestamp": "2026-05-17T12:00:01.000000"
}
```

### 2.3 Mensajes Enviados (Cliente → Servidor)

| Comando | Parámetros | Descripción |
|---------|-------------|-------------|
| `ARM` | - | Armar motores |
| `DISARM` | - | Desarmar motores |
| `TAKEOFF` | `{"altitude": 10}` | Despegar |
| `LAND` | - | Aterrizar |
| `RTL` | - | Return to Launch |
| `SET_MODE` | `{"mode": "GUIDED"}` | Cambiar modo |
| `REBOOT` | - | Reiniciar autopiloto |
| `GOTO` | `{"lat": 4.712, "lon": -74.073, "alt": 15}` | Ir a coordenada |
| `GOTO_RELATIVE` | `{"forward": 10, "right": 5, "up": 3}` | Ir relativo al dron |
| `RC_CONTROL` | `{"throttle": 0.5, "yaw": 0, "pitch": 0, "roll": 0}` | Control manual (sin ACK) |
| `RC_RESET` | - | Resetear controles (sin ACK) |
| `EMERGENCY` | `{"action": "STOP"}` | Emergencia |
| `MISSION_UPLOAD` | `{"waypoints": [{"lat": 4.712, "lon": -74.073, "alt": 10}]}` | Subir misión GPS |
| `MISSION_UPLOAD_RELATIVE` | `{"waypoints": [{"forward": 10, "right": 0, "up": 0}]}` | Subir misión relativa |
| `START_MISSION` | - | Iniciar misión |
| `CLEAR_MISSION` | - | Limpiar misión |
| `SAVE_WAYPOINTS` | `{"name": "ruta1", "waypoints": [...]}` | Persistir waypoints |
| `LOAD_WAYPOINTS` | `{"name": "ruta1"}` | Cargar waypoints |
| `LIST_WAYPOINTS` | - | Listar waypoints guardados |

#### Ejemplos de envío WebSocket

```javascript
// Armar motores
ws.send(JSON.stringify({ type: "ARM", params: {} }));

// Despegar a 15m
ws.send(JSON.stringify({ type: "TAKEOFF", params: { altitude: 15 } }));

// Navegación relativa (10m adelante, 5m derecha)
ws.send(JSON.stringify({ type: "GOTO_RELATIVE", params: { forward: 10, right: 5, up: 0 } }));

// Emergencia
ws.send(JSON.stringify({ type: "EMERGENCY", params: { action: "STOP" } }));

// Guardar waypoints
ws.send(JSON.stringify({
  type: "SAVE_WAYPOINTS",
  params: { name: "mision_1", waypoints: [{ forward: 10, right: 0, up: 0 }] }
}));

// Cargar waypoints
ws.send(JSON.stringify({ type: "LOAD_WAYPOINTS", params: { name: "mision_1" } }));
```

### 2.4 WebSocket de Cámara

```
ws://<host>:8000/api/camera/ws
```

El servidor envía frames JPEG codificados en base64 a 25fps:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/camera/ws');
ws.onmessage = (event) => {
  const base64 = event.data;  // string base64 del JPEG
  const imageSrc = `data:image/jpeg;base64,${base64}`;
  // Mostrar en un <img>
};
```

---

## 3. Códigos de Error

| Código HTTP | Significado |
|-------------|-------------|
| 200 | OK |
| 404 | No encontrado (waypoint o recurso) |
| 500 | Error interno del servidor |
| 503 | MAVLink no conectado |

**Respuesta de error estándar:**

```json
{
  "detail": "MAVLink no conectado"
}
```

---

## 4. Esquemas de Datos

### 4.1 Waypoint Relativo

```json
{
  "forward": 10,
  "right": 5,
  "up": 3
}
```

### 4.2 Waypoint Absoluto (GPS)

```json
{
  "latitude": 4.711,
  "longitude": -74.0721,
  "altitude": 10
}
```

### 4.3 Misión

```json
{
  "waypoints": [
    {"lat": 4.711, "lon": -74.0721, "alt": 10},
    {"lat": 4.712, "lon": -74.073, "alt": 15}
  ]
}
```

### 4.4 Control RC

```json
{
  "throttle": 0.5,
  "yaw": 0.0,
  "pitch": 0.2,
  "roll": -0.1
}
```

### 4.5 Emergencia

```json
{
  "action": "STOP"
}
```
