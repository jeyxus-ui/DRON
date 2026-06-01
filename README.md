# Drone Telemetry System

Sistema de control y telemetría para drones compatible con ArduPilot. Backend FastAPI + MAVLink, app móvil React Native, visión YOLOv8 y simulación SITL.

```
                            ╔══════════════════╗
                            ║  FASTRAPI +      ║
          ┌─────────────────║  PYTHON + MAVLINK ║─────────────────┐
          │                 ╚══════════════════╝                 │
          │                                                      │
    ┌─────┴──────┐                                    ┌─────────┴────────┐
    │  APP MÓVIL  │    REST + WebSocket                │   DRON / SITL    │
    │  React      │◄══════════════════════════════════►│   MAVLink        │
    │  Native     │                                    │   ArduPilot      │
    │  Android    │                                    │   Pixhawk        │
    └─────────────┘                                    └──────────────────┘
```

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [`docs/DOCUMENTO_TECNICO_INTEGRAL.md`](docs/DOCUMENTO_TECNICO_INTEGRAL.md) | Documento técnico completo (arquitectura, componentes, protocolos, decisiones de diseño) |
| [`docs/INFORME_ARQUITECTURA.md`](docs/INFORME_ARQUITECTURA.md) | Arquitectura detallada: diagramas, patrones, flujos, estructura de datos |
| [`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md) | Manual de operación: cómo usar la app, cada pantalla, emergencias |
| [`docs/GUIA_INSTALACION.md`](docs/GUIA_INSTALACION.md) | Instalación y despliegue en distintos entornos (local, Docker, Raspberry Pi) |
| [`docs/API.md`](docs/API.md) | Referencia completa de API REST + WebSocket con ejemplos |
| [`docs/DOCUMENTACION_TECNICA.md`](docs/DOCUMENTACION_TECNICA.md) | Documentación técnica general del proyecto |
| [`docs/README_SITL.md`](docs/README_SITL.md) | Guía de simulación SITL |
| [`docs/TROUBLESHOOTING_WEBSOCKET.md`](docs/TROUBLESHOOTING_WEBSOCKET.md) | Solución de problemas de WebSocket |

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI (Python 3.10+), Uvicorn |
| Protocolo dron | MAVLink (pymavlink 2.4.41) |
| Base de datos | PostgreSQL 15 (opcional) |
| Visión | YOLOv8n + OpenCV + Intel RealSense |
| App móvil | React Native 0.83.1 (TypeScript) |
| Contenedores | Docker / docker-compose |

## Inicio rápido

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
# → http://localhost:8000
```

## Estructura

```
back-mavlink/
├── backend/          # API REST + WebSocket + MAVLink
├── mobile/           # App React Native Android
├── frontend/         # Dashboard web Next.js
├── scripts/          # Simulación, pruebas, bridges
├── assets/           # Modelos ML, marcadores ArUco
├── logs/             # Logs de ejecución (gitignored)
├── data/             # Persistencia de waypoints
├── docs/             # Documentación
└── raspberry/        # Despliegue Raspberry Pi
```

## Contacto

Proyecto universitario - Mayo 2026
