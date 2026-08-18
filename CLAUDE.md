# Reglas del Proyecto - Dron R App

## Identidad del Proyecto
- App Android de control de dron con interfaz tactil (joysticks, waypoints, telemetry)
- Backend Python (FastAPI + WebSocket) que se comunica con ArduPilot via MAVLink
- Dead-reckoning local NED para vuelo sin GPS

## Stack
- **Backend**: Python 3.11+, FastAPI, Uvicorn, SQLAlchemy (async), MAVLink (pymavlink)
- **Mobile**: React Native 0.83, Expo (bare), TypeScript
- **Sensors**: MTF01 (flow + LIDAR X4) - fallback a simulacion
- **Vision**: YOLOv8n (ArUco detection), RealSense D435i (VIO) - futuras fases

## Reglas de Codigo
- No comentarios innecesarios
- No subir a GitHub sin instruccion explicita
- Ruta del repo: `C:\Users\USUARIO\Desktop\Drones\dron r\Dron` (espacios en ruta -> usar `git -C "..."`)
- PowerShell no soporta `&&` ni heredocs - usar scripts en archivo + `bash`
- Android SDK: `C:\Users\USUARIO\AppData\Local\Android\Sdk`

## Verificacion Anti-Regresion
- `py_compile` para cada archivo Python antes de commit
- `tsc --noEmit` en mobile antes de commit
- Probar backend SIM: `python main.py` -> verificar startup + WebSocket connection
- Test de navegacion local SIM: `python test_nav_sim_local.py`

## Fases del Proyecto

### Fase 0 - Auditoria (completada)
- Auditoria completa backend + mobile realizada

### Fase 1 - Estabilizar Nucleo
- [ ] Fix `websocket.py` indentacion/get_telemetry_data
- [ ] Fix `config.ts` DEFAULT_MAX_ALT mismatch (100 vs 3)
- [ ] Fix `IpConfigModal` side effect FENCE_ENABLE
- [ ] Evaluar dead code: Joystick.tsx, TacticalButton.tsx, StatusBar.tsx
- [ ] Fix `arm()` inconsistente en commands.py
- [ ] Fix `main.py` warning SQLAlchemy siempre se loggea
- [ ] Agregar `ultralytics` a `requirements.txt`

### Fase 2 - Control
- [ ] ArUco detection con YOLOv8n (detector.py ya existe)
- [ ] VISION_POSITION_ESTIMATE con ArUco
- [ ] ArduPilot EKF2 posicion externa

### Fase 3 - Funciones Avanzadas
- [ ] RealSense D435i VIO (realsense.py placeholder existe)

### Fase 4 - Pulido UI
- [ ] Unificar pantallas grandes (DroneControlScreen 1248 lin, WaypointScreen 1155 lin)
- [ ] Refactorizar camara duplicada portrait/landscape en DroneControlScreen
