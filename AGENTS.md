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
# Backend
pip install -r backend/requirements.txt
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

- **Última sesión:** Fusión de manuales técnicos (Diego Cheo + App Dron)
- **Manual fusionado:** `documentacion/MANUAL_TECNICO_FUSIONADO.docx`
- **Estilo de redacción:** Formal académico
- **Archivos pendientes de revisión:** Secciones 5.4, 6.3-6.8, 7-16 del manual

## Reglas para el Asistente

1. **Leer este archivo** al inicio de cada sesión para contexto rápido
2. **No agregar comentarios** en código a menos que el usuario los pida
3. **Usar tablas** en lugar de árbol ASCII para directorios en documentos
4. **Estilo formal académico** para documentos técnicos
5. **Preferir ediciones** sobre reescrituras completas
6. **Verificar con lint/typecheck** después de modificar código
7. **No commitear** a menos que el usuario lo pida explícitamente
