# AGENTS.md - Instrucciones persistentes del proyecto

## Descripción del Proyecto

Sistema integral de control y telemetría para drones (UAV) basado en ArduPilot. Permite operar un dron desde una app móvil React Native, con backend FastAPI, comunicación MAVLink, visión artificial YOLOv8 y simulación integrada.

**Repositorio:** https://github.com/jeyxus-ui/DRON
**Rama principal:** ruta

## Arquitectura

```
App Móvil (React Native) ←→ Backend (FastAPI) ←→ Pixhawk/SITL (MAVLink)
                                    ↓
                            VisionDetector (YOLOv8n)
                                    ↓
                            Cámara RealSense/USB
```

- **Backend:** Python 3.11+ / FastAPI / pymavlink / PostgreSQL
- **Mobile:** React Native 0.83.1 / TypeScript
- **Frontend Web:** Next.js 16 / Dashboard de telemetría
- **Visión:** YOLOv8nano (Ultralytics) / OpenCV
- **Hardware:** Raspberry Pi 4/5 + Pixhawk + Cámara RealSense D435i

## Estructura del Proyecto

| Directorio | Contenido |
|---|---|
| `backend/` | FastAPI: API REST, WebSocket, MAVLink, visión artificial |
| `backend/api/` | rest.py, websocket.py, camera_stream.py |
| `backend/mavlink/` | connection.py, controller.py, commands.py, telemetry.py, rc_override.py, geo_utils.py |
| `backend/vision/` | detector.py (YOLOv8n) |
| `backend/db/` | database.py, models.py, repository.py |
| `mobile/src/` | App React Native: context, screens, components |
| `mobile/src/screens/` | DroneControlScreen, TelemetryScreen, GPSScreen, WaypointScreen |
| `mobile/src/context/` | DroneContext.tsx (estado global WebSocket) |
| `frontend/` | Next.js dashboard web |
| `raspberry/` | Versión standalone para Raspberry Pi |
| `scripts/` | sim_drone.py, test_*.py, deploy, utilidades |
| `docs/` | Documentación técnica en Markdown |
| `documentacion/` | Manuales en DOCX |

## Convenciones de Código

### Python (Backend)
- Clases: `PascalCase` (`MAVController`, `DroneCommands`)
- Funciones/variables: `snake_case` (`send_command`, `_read_loop`)
- Constantes: `UPPER_SNAKE_CASE` (`VALID_MODES`, `PWM_MIN`)
- Métodos privados: prefijo `_` (`_do_upload_mission`)
- Type hints obligatorios en funciones públicas
- Logging: `logging.getLogger(__name__)`

### TypeScript (Mobile)
- Componentes: `PascalCase` (`DroneControlScreen`)
- Archivos: `PascalCase.tsx` para componentes
- Interfaces: `PascalCase` (`CommandResult`, `Telemetry`)
- Funciones: `camelCase` (`sendCommand`)
- Constantes: `UPPER_SNAKE_CASE` (`API_URL`, `WS_URL`)

## Comandos Útiles

```bash
# Backend (RECOMENDADO — incluye WebSocket ping/pong)
python -m backend.run
# O alternativa:
MAVLINK_DEVICE='tcp:127.0.0.1:5760' python -m backend.run

# Backend (uvicorn directo — NO configura ws_ping, usar solo para desarrollo)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Mobile
cd mobile && npm install && npx react-native start

# Simulación
.\scripts\start_all.ps1          # Windows
./scripts/start_all.sh           # Linux/Mac

# Tests
python scripts/test_all_in_one.py
python scripts/test_websocket.py

# Docker
docker-compose up --build -d
```

## Puertos

| Puerto | Servicio |
|---|---|
| 8000 | Backend FastAPI (REST + WebSocket) |
| 4545 | Frontend Next.js |
| 5432 | PostgreSQL |
| 14550 | UDP - QGroundControl / sim_drone |
| 14551 | TCP - sim_drone → Backend |

## WebSocket Ping/Pong

El backend envía pings WebSocket cada 15s (configurable: `WS_PING_INTERVAL`).
Si el cliente no responde en 10s (`WS_PING_TIMEOUT`), uvicorn cierra la conexión.

**IMPORTANTE**: Solo funciona cuando se inicia con `python -m backend.run`.
Si se usa `uvicorn backend.main:app` directamente, NO se configuran los pings.

## Raspberry Pi (despliegue de campo)

| Dato | Valor |
|---|---|
| Host / hostname | DRONE-2 |
| IP de campo | `10.252.200.235` |
| Service systemd | `dron-backend.service` |
| Puerto | `8000` |
| Repo de referencia | https://github.com/jeyxus-ui/DRON (rama `ruta`) |

### systemd recomendado

- `ExecStart` debe usar `python3 -m backend.run` (no `uvicorn backend.main:app` directo).
- Obligatorio en Pi 4 (Cortex-A72): `Environment=DRON_VISION_ENABLED=0` — evita crash-loop SIGILL de PyTorch/YOLO.
- Reinicio: `sudo systemctl restart dron-backend.service`

### App móvil (IP)

El default de código es `172.20.10.2` (hotspot de desarrollo). En campo configurar manualmente: ⚙️ → Host IP = `10.252.200.235` → guardar → reiniciar app.

### Remotes

Puede haber varios remotes (`jeyxus-ui/DRON`, forks locales, remoto de la Pi). Al sincronizar, usar explícitamente el remote correcto; un checkout limpio puede sobrescribir IP/config locales.

### Checklist post-despliegue

1. Actualizar código en la Pi y reiniciar `dron-backend.service`.
2. `systemctl status dron-backend` → activo, `NRestarts=0`, `:8000` escuchando.
3. `curl` login `/api/auth/login` → HTTP 200 + token.
4. `curl` `/api/telemetry` → batería, mode, etc.
5. WebSocket `/ws/telemetry?token=...` → frames `type:telemetry` ~10 Hz (no solo `connection_alert`).
6. App con IP `10.252.200.235` → telemetría en vivo.
7. Armado solo con GPS fix (exterior). Indoor (`satellites:0`) bloquea prearm; no es bug de backend.

## Documentación del Proyecto

| Archivo | Contenido |
|---|---|
| `docs/DOCUMENTO_TECNICO_INTEGRAL.md` | Documento técnico completo del sistema |
| `docs/DOCUMENTACION_TECNICA.md` | Documentación técnica detallada |
| `docs/INFORME_ARQUITECTURA.md` | Informe de arquitectura y decisiones de diseño |
| `docs/GUIA_INSTALACION.md` | Guía de instalación |
| `docs/MANUAL_USUARIO.md` | Manual de usuario |
| `docs/API.md` | Referencia de API |
| `documentacion/MANUAL_TECNICO_FUSIONADO.docx` | Manual técnico fusionado (estilo Diego + contenido dron) |

## Estado Actual

- **Última sesión:** Fix informe Pi — telemetría WS + kill-switch YOLO (2026-08-20)
- **Merge local:** `nueva-interfaz` → `ruta` (fast-forward, commit `a9e5355`)
- **Fix WS:** `get_telemetry_data()` en `websocket.py` — lógica sacada del `except` (bug que retornaba `None` y mataba el broadcaster)
- **Visión en Pi:** `DRON_VISION_ENABLED=0` vía config/`VisionDetector` para evitar SIGILL
- **Comando backend recomendado:** `python -m backend.run` (incluye ws_ping)
- **RPi:** desplegar estos fixes y verificar checklist de la sección Raspberry Pi
- **Manual fusionado:** `documentacion/MANUAL_TECNICO_FUSIONADO.docx`
- **Estilo de redacción:** Formal académico

## Reglas para el Asistente

1. **Leer este archivo** al inicio de cada sesión para contexto rápido
2. **No agregar comentarios** en código a menos que el usuario los pida
3. **Usar tablas** en lugar de árbol ASCII para directorios en documentos
4. **Estilo formal académico** para documentos técnicos
5. **Preferir ediciones** sobre reescrituras completas
6. **Verificar con lint/typecheck** después de modificar código
7. **No commitear** a menos que el usuario lo pida explícitamente
