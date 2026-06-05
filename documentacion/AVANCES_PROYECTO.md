# Avances del Proyecto — Dron Ground Control Station (GCS)

## Base del Desarrollo

Este proyecto se desarrolló sobre avances realizados previamente por estudiantes de la **Universitaria de Colombia**. La base original consistía en una aplicación con cuatro módulos accesibles desde un menú de opciones. Se reestructuró por completo la interfaz y la lógica de control para lograr un sistema de vuelo autónomo con capacidad de seguir rutas y evadir obstáculos mediante sensores.

---

## Arquitectura General

```
App Móvil (React Native) ←── WebSocket / REST ──→ Backend (FastAPI / Python)
                                                        │
                                                   MAVLink
                                                        │
                                                   Pixhawk / ArduPilot
                                                        │
                                              Sensores (MTF01, YDLIDAR)
```

- **App móvil**: Ground Control Station (GCS) con 4 pantallas deslizables.
- **Backend**: API REST + WebSocket en Python que se comunica con el dron vía MAVLink.
- **Comunicación**: WebSocket para telemetría en tiempo real (10 Hz) y comandos; REST para operaciones no críticas; cámara vía MJPEG stream.

---

## Cambios y Mejoras Realizadas

### 1. Interfaz de Usuario — De Menú a Pestañas

| Original | Actual |
|---|---|
| Menú de opciones con navegación por botones | Navegación horizontal por pestañas (FlatList + pagingEnabled) |
| Estilo genérico | Glassmorphism v2 con identidad de color por pestaña |
| Sin efectos visuales | Efectos neón (neon glow) en todos los elementos |

**Pestañas actuales**:
- **CONTROL** (ámbar `#FF8800`) — Panel de vuelo principal con cámaras, joysticks y modo de vuelo.
- **GPS** (cian `#00B4D8`) — Mapa con posicionamiento, waypoints en mapa y calidad GPS.
- **RUTA** (violeta `#8B5CF6`) — Planificación de rutas relativas (F = adelante, R = derecha, U = arriba).
- **DATA** (teal `#14B8A6`) — Telemetría detallada con horizonte artificial.

### 2. Sistema de Navegación Autónoma

Se implementó un sistema completo de navegación autónoma en el backend:

- **NavigationController** — Bucle en segundo plano a 5 Hz que ejecuta waypoints de forma autónoma.
- **PathPlanner** — Genera rutas punto a punto con interpolación y desvíos por obstáculos.
- **Modos de operación**: IDLE, NAVIGATING, MISSION, AVOIDING.
- Comandos desde la app: `NAV_GOTO`, `NAV_MISSION`, `NAV_STOP`, `NAV_AVOIDANCE`.

### 3. Sensores y Evitación de Obstáculos

- **MTF01** — Sensor ultrasónico (2 cm – 400 cm) por I2C. En simulación genera distancias senoidales.
- **YDLIDAR X4** — Escáner láser 360° (0.12 m – 10 m, 720 puntos/barrido) por USB serial. En simulación genera 4 obstáculos virtuales con ruido.
- **ObstacleMap** — Mapa de ocupación 20 m × 20 m con resolución de 0.2 m. Se actualiza con datos de LiDAR y ultrasonido. Decaimiento temporal (0.995).
- **ObstacleAvoidance** — Evalúa obstáculos y ejecuta acciones:
  - Distancia < 1 m → BRAKE (freno).
  - Distancia < 2 m → AVOID (giro hacia dirección segura).
  - Distancia > 2 m → NONE (continúa normal).

### 4. Control del Dron

- **Joysticks virtuales**: Izquierdo = Throttle/Yaw (modo 2, throttle permanente), Derecho = Pitch/Roll (auto-centrado).
- **Selector de modos de vuelo** en panel lateral: MANUAL, ASISTIDO, AUTOMÁTICO, EMERGENCIA.
- **Botones de acción rápida**: BRAKE, HOLD POS, REBOOT.
- **ARM/DISARM** desde el header o panel lateral.
- **Comandos autónomos**: iniciar misión, navegar a punto, detener navegación.

### 5. Gestión de Rutas (Waypoints)

- **Rutas relativas**: El usuario ingresa desplazamientos en metros (Forward, Right, Up) desde la posición actual del dron.
- **Persistencia local**: Las rutas se guardan como archivos JSON en el sistema de archivos del dispositivo (`GCS/waypoints/*.json`) mediante `react-native-fs`.
- **Edición**: Cada waypoint puede editarse (modal con F/R/U) o eliminarse.
- **Carga/Descarga**: Las rutas guardadas se listan con opciones para cargar, eliminar o sobreescribir.
- **Indicador de ruta activa**: Banner en la parte superior de la pantalla RUTA.

### 6. Configuración Dinámica de IP

- El usuario puede cambiar la IP del servidor desde la app (ícono ⚙ en la pantalla CONTROL).
- La IP se persiste en el dispositivo (`GCS/config.json`) y se carga al iniciar la app.
- Al guardar una nueva IP, la app reconecta automáticamente el WebSocket.
- Se muestra retroalimentación visual (toast) indicando "Conectado" o "Error de conexión".

### 7. Sistema de Cámara

- **RealSense Camera** (Intel D415/D435) conectada al backend.
- Stream MJPEG visible en la pantalla CONTROL dentro de un WebView.
- Superposición de retícula, crosshair y chips de telemetría sobre la vista de cámara.
- Detección de marcadores ArUco con estimación de distancia.
- Zonas de seguridad: crítica (< 2 m), advertencia (< 5 m), segura.
- Visión por computadora integrada con el sistema de evitación (emergency callback → BRAKE).

### 8. Telemetría y Monitoreo

- **WebSocket** transmite telemetría completa a 10 Hz: actitud, GPS, batería, velocidad, HDOP, satélites.
- **Modo demo**: Si no hay conexión con el backend, la app genera telemetría simulada localmente y permite probar toda la interfaz sin hardware.
- **Pantalla DATA**: horizonte artificial, valores numéricos de actitud, velocidad, posición y batería con barras de progreso.
- **Pantalla GPS**: Mapa con marcador del dron, círculo de precisión GPS, waypoints en mapa, calidad GPS (EXCELENTE/BUENO/REGULAR/MALO).

### 9. Estilo Visual

- **Glassmorphism v2**: Fondos semi-transparentes con bordes brillantes (1.5 px, blanco 10-18% opacidad), bordes redondeados de 12-16 px. Sin `backdrop-filter` (no soportado en Android React Native).
- **Identidad por pestaña**: Cada pantalla tiene su propio color de acento (ámbar, cian, violeta, teal) aplicado a bordes, sombras y brillos.
- **Neon glow**: Sombras de color (`shadowColor` + `shadowRadius` hasta 14 px) en contenedores; `textShadowRadius` hasta 10 px en textos.
- **Tipografía**: Monospace para valores numéricos; sistema monospace. Se eliminó `@fontsource/roboto-mono`.

### 10. Estructura del Backend

```
backend/
├── main.py                 # FastAPI app entry point
├── start_api_sim.py        # Lanzador en modo simulación
├── config.py               # Configuración (MAVLink, puertos, DB)
├── api/
│   ├── rest.py             # Endpoints REST de control
│   ├── websocket.py        # WebSocket de telemetría/ comandos
│   └── camera_stream.py    # Stream MJPEG y visión
├── mavlink/
│   ├── connection.py       # Conexión MAVLink (Pixhawk)
│   ├── controller.py       # Controlador de alto nivel
│   ├── commands.py         # Comandos del dron
│   ├── telemetry.py        # Parseo de telemetría MAVLink
│   └── rc_override.py      # Override de canales RC
├── sensors/
│   ├── mtf01.py            # Sensor ultrasónico MTF01
│   ├── ydlidar_x4.py       # Láser YDLIDAR X4
│   ├── obstacle_map.py     # Mapa de obstáculos 20×20 m
│   └── manager.py          # Orquestador de sensores
├── navigation/
│   ├── avoidance.py        # Evitación de obstáculos
│   ├── planner.py          # Planificador de rutas
│   └── controller.py       # Controlador de navegación
└── vision/
    └── detector.py         # Detección ArUco
```

### 11. Estructura de la App Móvil

```
mobile/src/
├── App.tsx                         # Navegación por pestañas + providers
├── config.ts                       # Configuración dinámica de IP
├── context/DroneContext.tsx        # Estado central (WebSocket + demo)
├── screens/
│   ├── DroneControlScreen.tsx      # CONTROL — HUD, joysticks, cámara
│   ├── GPSScreen.tsx               # GPS — mapa, waypoints, calidad
│   ├── WaypointScreen.tsx          # RUTA — planificación de rutas
│   └── TelemetryScreen.tsx         # DATA — telemetría, horizonte
├── components/
│   ├── Joystick.tsx                # Joystick virtual
│   ├── StatusBar.tsx               # Barra de estado superior
│   ├── TacticalButton.tsx          # Botón reutilizable
│   └── IpConfigModal.tsx           # Modal de configuración IP
├── hooks/
│   └── useDeviceLocation.ts        # GPS del dispositivo
└── utils/
    └── ipConfig.ts                 # Persistencia de IP en disco
```

---

## Resumen de Funcionalidades Actuales

| Funcionalidad | Estado |
|---|---|
| Control manual (joysticks) | ✅ |
| Cambio de modos de vuelo | ✅ |
| ARM / DISARM | ✅ |
| Navegación autónoma punto a punto | ✅ |
| Misión autónoma con waypoints | ✅ |
| Evitación de obstáculos ultrasónico + láser | ✅ |
| Mapa de obstáculos 20×20 m | ✅ |
| Planificación de rutas relativas (F/R/U) | ✅ |
| Persistencia de rutas en dispositivo | ✅ |
| Stream de cámara (RealSense + MJPEG) | ✅ |
| Detección ArUco con distancia | ✅ |
| Telemetría en tiempo real (WebSocket 10 Hz) | ✅ |
| Horizonte artificial | ✅ |
| Mapa GPS con waypoints | ✅ |
| Calidad GPS (HDOP + satélites) | ✅ |
| Configuración dinámica de IP del servidor | ✅ |
| Modo demo sin hardware | ✅ |
| Glassmorphism + neon glow | ✅ |
| Diseño por pestañas con identidad de color | ✅ |

---

## Próximos Pasos Potenciales

- Integración con base de datos PostgreSQL para telemetría histórica.
- Autenticación de usuarios y sesiones múltiples.
- Soporte para múltiples drones simultáneamente.
- Algoritmos de búsqueda y rescate automáticos (patrones de búsqueda).
- Transmisión de video con latencia ultrabaja (WebRTC en lugar de MJPEG).
- Despliegue del backend en un companion computer (Raspberry Pi / Jetson) a bordo del dron.
