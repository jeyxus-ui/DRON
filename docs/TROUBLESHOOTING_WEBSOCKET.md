# WebSocket Troubleshooting Guide
## Problema: WebSocket se desconecta al enviar un comando desde la app móvil

---

## Diagnóstico rápido

### Paso 1 — Ejecutar el script de test

Desde cualquier máquina en la misma red que la Raspberry Pi:

```bash
pip install websockets requests
python scripts/test_websocket.py --host <IP_RASPBERRY_PI>
```

Ejemplo:
```bash
python scripts/test_websocket.py --host 192.168.137.22
```

El script ejecuta 4 tests:
1. **HTTP Health** — verifica que el backend responde en el puerto 8000
2. **WS Telemetría** — conecta y recibe telemetría durante 5 segundos
3. **WS Comando sin desconexión** — envía `RC_CONTROL` y verifica que la conexión sigue activa
4. **WS Stress** — envía 10 comandos rápidos consecutivos

---

## Causas conocidas y soluciones

### ❌ Causa 1: Escrituras concurrentes al WebSocket (YA CORREGIDO)

**Síntoma:** El WebSocket se cierra con código `1006` (cierre anormal) exactamente cuando se envía un comando.

**Causa:** El `telemetry_broadcaster` y el `websocket_endpoint` escribían al mismo WebSocket simultáneamente sin sincronización. FastAPI/Starlette no permite escrituras concurrentes en el mismo WebSocket.

**Solución aplicada:** Se añadió un `asyncio.Lock` por conexión en `ConnectionManager`. Tanto el broadcaster como el ACK de comandos usan `manager.send()` que adquiere el lock antes de escribir.

**Archivo:** [`backend/api/websocket.py`](../backend/api/websocket.py)

---

### ❌ Causa 2: `connectWebSocket` llamado antes de ser definido

**Síntoma:** La app no conecta en absoluto, o conecta pero no reconecta.

**Causa:** `connectWebSocket` era una `const` arrow function definida DESPUÉS del `useEffect` que la llamaba. Las `const` no se elevan (hoisting), causando un error de referencia.

**Solución aplicada:** Se envolvió en `useCallback` y se movió ANTES del `useEffect`.

**Archivo:** [`mobile/src/context/DroneContext.tsx`](../mobile/src/context/DroneContext.tsx)

---

### ❌ Causa 3: Error de TypeScript `NodeJS.Timeout`

**Síntoma:** Error de compilación `Cannot find namespace 'NodeJS'.ts(2503)`.

**Causa:** `NodeJS.Timeout` requiere `@types/node`, que no está disponible en React Native (el `tsconfig.json` solo incluye `"types": ["jest"]`).

**Solución aplicada:** Cambiado a `ReturnType<typeof setTimeout>`.

**Archivo:** [`mobile/src/context/DroneContext.tsx`](../mobile/src/context/DroneContext.tsx:64)

---

### ❌ Causa 4: RC_CONTROL falla porque no hay MAVLink conectado

**Síntoma:** El WebSocket se cierra con código `1011` (error interno del servidor) al enviar `RC_CONTROL`.

**Causa:** El backend está en modo SIM (sin dron físico conectado). El comando `RC_CONTROL` intenta acceder a `mav_controller.rc` que es `None` en modo SIM.

**Verificación:**
```bash
docker-compose logs backend | grep "RC no disponible"
```

**Solución:** El backend ya maneja este caso y devuelve `{"success": false, "message": "RC no disponible (ej. modo SIM)"}` sin cerrar la conexión. Si aún se cierra, revisar los logs del backend.

---

### ❌ Causa 5: IP incorrecta en la app móvil

**Síntoma:** La app no conecta en absoluto. El log muestra `[WS] Error de WebSocket`.

**Verificación:** En la Raspberry Pi:
```bash
hostname -I
```

**Solución:** Actualizar `RASPBERRY_IP` en [`mobile/src/config.ts`](../mobile/src/config.ts):
```ts
const RASPBERRY_IP = '192.168.X.X';  // IP real de la Raspberry Pi
```

Luego reconstruir la app:
```bash
cd mobile && npm run android
```

---

### ❌ Causa 6: Firewall bloqueando el puerto 8000

**Síntoma:** El test HTTP falla pero el ping a la Raspberry Pi funciona.

**Verificación en Raspberry Pi:**
```bash
sudo ufw status
sudo iptables -L -n | grep 8000
```

**Solución:**
```bash
sudo ufw allow 8000/tcp
```

---

## Cómo leer los logs del backend

```bash
# Ver logs en tiempo real
docker-compose logs -f backend

# Buscar errores de WebSocket
docker-compose logs backend | grep "\[WS\]"

# Buscar desconexiones
docker-compose logs backend | grep "desconectado\|ERROR\|cerrado"
```

### Interpretación de códigos de cierre WebSocket

| Código | Significado | Causa probable |
|--------|-------------|----------------|
| `1000` | Cierre normal | El cliente cerró la app |
| `1001` | Going away | El servidor se reinició |
| `1006` | Cierre anormal | Error de red o excepción no capturada en el servidor |
| `1011` | Error interno | Excepción en el handler del servidor |

---

## Mapa de puertos (sin solapamientos)

| Servicio | Puerto interno | Puerto en Raspberry Pi | URL |
|----------|---------------|------------------------|-----|
| PostgreSQL | 5432 | **5432** | Solo interno |
| Backend API | 8000 | **8000** | `http://<PI_IP>:8000` |
| WebSocket | 8000 | **8000** | `ws://<PI_IP>:8000/ws/telemetry` |
| Frontend | 3000 | **4545** | `http://<PI_IP>:4545` |

---

## Flujo de datos completo

```
App Móvil (Android)
    │
    │  ws://192.168.X.X:8000/ws/telemetry
    │
    ▼
Raspberry Pi — Docker Container (backend:8000)
    │
    ├── telemetry_broadcaster (loop cada 100ms)
    │       └── manager.broadcast() → asyncio.Lock → ws.send_json(telemetry)
    │
    └── websocket_endpoint (loop esperando comandos)
            ├── ws.receive_text() → process_command()
            └── manager.send() → asyncio.Lock → ws.send_json(ack)
                                    ↑
                          MISMO LOCK que el broadcaster
                          → evita escrituras concurrentes
```

---

## Verificación final

Después de aplicar todos los fixes, el comportamiento esperado es:

1. La app conecta al WebSocket ✅
2. La app recibe telemetría cada ~100ms ✅
3. Al mover el joystick, se envía `RC_CONTROL` ✅
4. El backend responde con `command_ack` ✅
5. La conexión **NO** se cierra después del comando ✅
6. La telemetría continúa llegando después del comando ✅
