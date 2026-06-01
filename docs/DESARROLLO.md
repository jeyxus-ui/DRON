# Guía de Desarrollo

## Entorno Local

### Requisitos

- Python 3.11+
- Node.js 20+
- Android SDK (para compilar APK)
- Git

### Clonar e instalar

```bash
git clone <repo>
cd back-mavlink

# Backend
python -m venv venv
.\venv\Scripts\activate   # Windows
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# Mobile
cd mobile
npm install
cd ..
```

## Backend

### Estructura

```
backend/
├── main.py            # Punto de entrada FastAPI
├── config.py          # Configuración central
├── api/
│   ├── rest.py        # Endpoints REST
│   ├── websocket.py   # WebSocket /ws/telemetry
│   └── camera_stream.py  # Streaming de cámara
└── mavlink/
    ├── controller.py  # Orquestador
    ├── connection.py  # Conexión MAVLink
    ├── telemetry.py   # Loop de telemetría
    ├── commands.py    # Comandos
    └── geo_utils.py   # Conversión coordenadas
```

### Ejecutar

```bash
# Modo simulado (sin dron real)
$Env:MAVLINK_DEVICE="SIM"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Con dron virtual bidireccional
.\scripts\start_all.ps1
```

### Agregar un endpoint REST

1. Abre `backend/api/rest.py`
2. Agrega el schema Pydantic si tiene body
3. Agrega la función con el decorador `@router`
4. Usa `get_mav_controller()` para acceder al dron

```python
class MyRequest(BaseModel):
    value: float

@router.post("/mi-accion")
async def mi_accion(request: MyRequest):
    ctrl = get_mav_controller()
    success = await asyncio.to_thread(ctrl.mi_comando, request.value)
    return {"success": success}
```

### Agregar un comando WebSocket

En `backend/api/websocket.py`, agrega un `elif` en `process_command()`:

```python
elif cmd_type == "MI_COMANDO":
    valor = params.get("valor")
    resultado = await asyncio.to_thread(mav_controller.mi_comando, valor)
    return {"success": True, "resultado": resultado}
```

## Mobile (React Native)

### Estructura

```
mobile/
├── App.tsx                    # Navegación entre pantallas
├── src/
│   ├── config.ts              # IP del backend
│   ├── context/
│   │   └── DroneContext.tsx   # Estado global + WebSocket
│   ├── screens/
│   │   ├── DroneControlScreen.tsx  # Control principal
│   │   ├── TelemetryScreen.tsx     # Telemetría
│   │   ├── GPSScreen.tsx          # Mapa GPS
│   │   └── WaypointScreen.tsx     # Waypoints
│   └── components/
│       ├── Joystick.tsx
│       ├── StatusBar.tsx
│       └── TacticalButton.tsx
└── android/                   # Proyecto Android nativo
```

### Ejecutar en BlueStacks

1. Obtén IP LAN: `ipconfig` → `192.168.x.x`
2. Edita `mobile/src/config.ts` → `HOST_IP = '192.168.x.x'`
3. Conecta ADB: `adb connect 127.0.0.1:5556`
4. `npx react-native run-android`

### Compilar APK Release

```bash
cd mobile
npm install
npx react-native build-android --mode=release
# APK: mobile/android/app/build/outputs/apk/release/app-release.apk
```

### Agregar una pantalla

1. Crea `mobile/src/screens/MiScreen.tsx`
2. En `App.tsx`, importa y agrega al array `SCREENS`
3. Usa `useDrone()` para telemetría y comandos:

```tsx
const { telemetry, connected, sendCommand } = useDrone();
const res = await sendCommand('MI_COMANDO', { valor: 123 });
```

### Estilo y convenciones

- Tema oscuro: `backgroundColor: '#050508'`
- Colores: verde `#00ff88`, azul `#00ccff`, rojo `#ff4466`
- Estilo militar/futurista (tipo DJI)
- Sin librerías UI externas (componentes propios)

## Scripts de simulación

| Script | Propósito |
|--------|-----------|
| `scripts/sim_drone.py` | Dron virtual bidireccional (UDP→QGC, TCP→backend) |
| `scripts/start_all.ps1` | Lanza simulación + backend en Windows |
| `scripts/gen_markers.py` | Genera marcadores ArUco en `assets/markers/` |
| `scripts/bridges/bridge_wsl.py` | Puente WSL↔Windows MAVLink |
| `scripts/create_tables.py` | Crea tablas PostgreSQL |

## Docker

```bash
# Construir y ejecutar todo
docker-compose up --build -d

# Solo servicios específicos
docker-compose up -d postgres
docker-compose up backend
```

## Base de datos

No es obligatoria para volar. Crea las tablas:

```bash
python scripts/create_tables.py
```

Configura en `.env`:
```
DB_URL=postgresql://dronix_user:DronixSecure2024!@localhost:5432/drones
```

## Consejos

- **Logs**: backend escribe a `logs/` (gitignored). Usa `LOG_LEVEL=DEBUG` para más info.
- **WebSocket**: usa `websocket/` en Postman o `scripts/test_websocket.py`.
- **Demo**: si no hay backend, la app activa modo demo automáticamente.
- **Simulación**: `.\scripts\start_all.ps1` es la forma más rápida de probar.
- **Cámara**: el backend arranca aunque no haya cámara conectada.
