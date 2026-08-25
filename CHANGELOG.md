# CHANGELOG — Ojo de dios GCS

## [24-08-2026] — Sesión de desarrollo

### Nueva funcionalidad — Vuelo autónomo dual-mode (indoor / GPS)
**Archivo:** `mobile/src/screens/WaypointScreen.tsx`
- Agregado toggle de modo de ruta: **🏠 CERRADO** (F/R/U metros relativos) y **🛰 GPS** (LAT/LON absoluto)
- Cada waypoint guarda su propio modo (`indoor` | `outdoor`)
- Al cambiar de modo con waypoints existentes, se solicita confirmación
- Campos de entrada adaptativos según el modo seleccionado

### Bug fix — Comando incorrecto al ir a waypoint individual
**Archivo:** `mobile/src/screens/WaypointScreen.tsx`
- **Antes:** `doGotoWaypoint` enviaba `GOTO` con `{forward, right, up}` — el handler esperaba lat/lon
- **Ahora:** envía `GOTO_RELATIVE` para modo indoor y `GOTO` para modo outdoor

### Bug fix — Misión no se subía antes de ejecutarse
**Archivo:** `mobile/src/screens/WaypointScreen.tsx`
- **Antes:** `doStartMission` llamaba `START_MISSION` sin subir primero los waypoints al Pixhawk
- **Ahora:** ejecuta `MISSION_UPLOAD_RELATIVE` (indoor) o `MISSION_UPLOAD` (outdoor) primero; si falla, aborta con error

### Bug fix — Motor test fallaba en modo simulador
**Archivo:** `backend/mavlink/controller.py`
- En modo SIM el proxy no exponía `test_motor` del `_SimulatedController`
- Agregado: `self.test_motor = self._sim.test_motor` en bloque SIM (~línea 54)

### Mejora — PWM real de motores en telemetría WebSocket
**Archivos:** `backend/api/websocket.py`, `mobile/src/context/DroneContext.tsx`, `mobile/src/screens/DroneControlScreen.tsx`
- La telemetría WebSocket (10 Hz) ahora incluye `rc_throttle_pwm`, `rc_roll_pwm`, `rc_pitch_pwm`, `rc_yaw_pwm`
- Los chips THR/YAW/PITCH/RLL en la pantalla de control muestran valores reales del backend (fallback a estimación local si no hay dato)
- Tipo `TelemetryData` extendido con campos PWM opcionales

### Nueva funcionalidad — Evasión de obstáculos + recalculo de ruta en vuelo autónomo
**Archivos:** `backend/api/websocket.py`, `mobile/src/context/DroneContext.tsx`, `mobile/src/screens/WaypointScreen.tsx`

**Problema anterior:** `START_MISSION` usaba el modo AUTO de ArduPilot (firmware), que ejecuta waypoints de forma independiente sin que el LiDAR/RealSense de Python pueda intervenir.

**Solución implementada:**
- `MISSION_UPLOAD` y `MISSION_UPLOAD_RELATIVE` ahora guardan los waypoints GPS en `_pending_mission_waypoints`
- `START_MISSION` pone el Pixhawk en modo GUIDED y delega al `NavigationController` de Python, que:
  - Envía `GOTO` uno a uno mientras monitorea sensores (LiDAR YDLiDAR X4 + MTF-01)
  - Si obstáculo detectado a **< 2 m** → modo AVOIDING: calcula heading seguro y desvía el dron
  - Si obstáculo a **< 1 m** → BRAKE de emergencia inmediato
  - Tras **3 s sin obstáculo** → recalcula ruta desde posición actual usando `PathPlanner` y retoma el siguiente waypoint
- `CLEAR_MISSION` detiene el `NavigationController` y limpia los waypoints pendientes
- Fallback automático al modo AUTO de ArduPilot si `nav_controller` no está disponible

**Telemetría nueva (10 Hz):**
- `nav_mode`: `IDLE` | `NAVIGATING` | `MISSION` | `AVOIDING`
- `nav_waypoint_index`: índice del waypoint actual
- `nav_total_waypoints`: total de waypoints en la misión
- `nav_avoidance_active`: si la evasión está activada

**Banner visual en WaypointScreen:**
- 🚁 Verde: "MISIÓN EN CURSO — Waypoint X/N" durante vuelo normal
- ⚠️ Naranja: "ESQUIVANDO OBSTÁCULO — LiDAR detectó obstáculo — recalculando ruta..." durante evasión

### Identidad visual — Ícono y nombre de la app
**Archivos:** `mobile/app.json`, `mobile/android/app/src/main/res/values/strings.xml`, `mobile/android/app/src/main/res/mipmap-*/`
- Nombre de la app: **"Ojo de dios"** (antes: "mobile")
- Ícono personalizado reemplazado en los 5 tamaños Android:
  - `mipmap-mdpi` → 48×48 px
  - `mipmap-hdpi` → 72×72 px
  - `mipmap-xhdpi` → 96×96 px
  - `mipmap-xxhdpi` → 144×144 px
  - `mipmap-xxxhdpi` → 192×192 px

---

## Configuración requerida para build del APK

### 1. Archivo `mobile/android/local.properties` (no versionado)
```
sdk.dir=C\:\\Users\\USER\\AppData\\Local\\Android\\Sdk
```

### 2. Exclusión de Windows Defender (requerida para compilación NDK)
Ejecutar en PowerShell como Administrador:
```powershell
Add-MpPreference -ExclusionPath "C:\Users\USER\AppData\Local\Android\Sdk\ndk"
Add-MpPreference -ExclusionPath "E:\Alejandro bustos\SEMILLERO\DRON-2\mobile\android\app\.cxx"
```

### 3. Compilar APK release
```powershell
cd "E:\Alejandro bustos\SEMILLERO\DRON-2\mobile\android"
.\gradlew.bat assembleRelease
```
APK generado en: `mobile/android/app/build/outputs/apk/release/app-release.apk`

---

## Configuración para prueba con dron físico (Raspberry Pi + Pixhawk)

### Backend
```bash
# Pixhawk por USB
MAVLINK_DEVICE=/dev/ttyACM0 MAVLINK_BAUD=115200 python backend/run_with_device.py

# Radio telemetría SiK
MAVLINK_DEVICE=/dev/ttyUSB0 MAVLINK_BAUD=57600 python backend/run_with_device.py
```

### Permisos puerto serial (Linux/Raspberry Pi)
```bash
sudo usermod -aG dialout $USER
```

### Red
- Activar hotspot en el teléfono Android
- Conectar Raspberry Pi al hotspot
- IP por defecto en la app: `172.20.10.2` (configurable desde ⚙ en la app)

---

## Ramas en GitHub
- `ruta` — rama principal de trabajo con todos los cambios
- `vuelo-autonomo` — rama de desarrollo de esta sesión (mergeada en `ruta`)
- Repositorio: https://github.com/Jbustos1941/DRON-2
