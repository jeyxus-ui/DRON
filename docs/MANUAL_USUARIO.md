# Manual de Usuario
## Sistema de Control y Telemetría para Drones

**Versión:** 1.0.0  
**Fecha:** Mayo 2026

---

## 1. Introducción

Este manual describe cómo operar el sistema de control de drones desde la aplicación móvil y el panel web. El sistema permite controlar un dron compatible con ArduPilot (Pixhawk, Cube, etc.) desde un dispositivo Android.

---

## 2. Requisitos del Sistema

### 2.1 Hardware

- **Dron:** Cualquier vehículo con autopiloto ArduPilot (Copter, Plane, Rover)
- **Computador:** Servidor con Python 3.10+ (Raspberry Pi, laptop, PC)
- **Cámara (opcional):** Intel RealSense D435i u otra cámara USB
- **Dispositivo móvil:** Android 8.0+ con Wi-Fi

### 2.2 Software

- Python 3.10 o superior
- Node.js 20+ (solo para compilar la app)
- PostgreSQL 15 (opcional)

---

## 3. Instalación

### 3.1 En el servidor

```bash
# Clonar el repositorio
git clone <repo-url>
cd back-mavlink

# Instalar dependencias Python
pip install -r backend/requirements.txt

# Configurar conexión
# Editar .env con el dispositivo MAVLink
```

### 3.2 En el dispositivo Android

La app se distribuye como APK:

```bash
# Compilar desde el código fuente
cd mobile
npm install
npx react-native build-android --mode=release
# APK: mobile/android/app/build/outputs/apk/release/app-release.apk
```

Alternativa: solicitar al equipo de desarrollo el APK precompilado.

---

## 4. Configuración Inicial

### 4.1 Conectar al servidor

1. Asegúrate de que el servidor y el dispositivo móvil estén en la misma red Wi-Fi
2. Encuentra la IP del servidor:
   - Windows: `ipconfig` (buscar IPv4)
   - Linux/Mac: `ip addr` o `ifconfig`
3. La app se conecta automáticamente a la IP configurada en `mobile/src/config.ts`

### 4.2 Configurar conexión del dron

Edita el archivo `.env` en el servidor:

```env
# Para dron físico (Pixhawk por USB):
MAVLINK_DEVICE=/dev/ttyACM0
MAVLINK_BAUD=115200

# Para simulación:
MAVLINK_DEVICE=SIM
```

### 4.3 Iniciar el servidor

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Verás en la consola:
```
✅ MAVLink controller initialized
✅ Telemetry WebSocket iniciado
✅ Cámara RealSense iniciada  (si hay cámara conectada)
```

---

## 5. Pantalla Principal (DroneControl)

### 5.1 Vista General

La pantalla principal se compone de:

```
┌─────────────────────────────────┐
│  [● CONECTADO]  STABILIZE  ⚡   │ ← Barra de estado
├─────────────────────────────────┤
│                                 │
│      ┌─── VIDEO EN VIVO ───┐    │
│      │                      │    │
│      │    [crosshair]       │    │ ← Stream de cámara
│      │              [ALT]   │    │   con HUD superpuesto
│      │              ┌──┐    │    │
│      │              │10│    │    │
│      │              └──┘    │    │
│      └──────────────────────┘    │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐   │
│  │CAM │ │SPD │ │ALT │ │BAT │   │ ← Tarjetas HUD
│  │ OK │ │8.2 │ │10.2│ │85% │   │
│  └────┘ └────┘ └────┘ └────┘   │
│  ┌────┐ ┌────┐ ┌────┐          │
│  │SAT │ │YAW │ │V/S │          │
│  │ 12 │ │ 45 │ │+0.3│          │
│  └────┘ └────┘ └────┘          │
├─────────────────────────────────┤
│ [ARMAR] [DESPEGUE] [ATERR] [SOS]│ ← Botones tácticos
├─────────────────────────────────┤
│    ┌─────────┐ ┌─────────┐     │
│    │ THR/YAW │ │PITCH/ROL│     │ ← Joysticks virtuales
│    │   [joystick] │ [joystick]│ │
│    │ THR:1500 │ │PIT:1500 │     │
│    │ YAW:1500 │ │RLL:1500 │     │
│    └─────────┘ └─────────┘     │
└─────────────────────────────────┘
```

### 5.2 Barra de Estado

| Indicador | Significado |
|-----------|-------------|
| ● CONECTADO | Conexión con el servidor activa |
| ○ DESCONECTADO | Sin conexión (modo demo activo) |
| STABILIZE | Modo de vuelo actual |
| ⚡ ARMADO | Motores armados |
| ● STANDBY | Motores desarmados |
| 🎮 DEMO | Modo de demostración sin dron |

### 5.3 Video en Vivo

- Muestra el stream de la cámara frontal del dron
- HUD superpuesto con altitud, velocidad, batería
- Crosshair central para referencia
- Si la cámara no está disponible, muestra "SEÑAL DE VIDEO NO DISPONIBLE"

### 5.4 Botones Tácticos

| Botón | Acción |
|-------|--------|
| **ARMAR** (⚡) | Armar motores (preparar para vuelo) |
| **DESARMAR** (🔒) | Desarmar motores (solo en tierra) |
| **DESPEGUE** (▲) | Despegar a 10 metros (pide confirmación) |
| **ATERRIZAJE** (▼) | Iniciar aterrizaje automático |
| **SOS** (☢) | Abre panel de emergencia |

### 5.5 Joysticks Virtuales

**Joystick izquierdo (THR/YAW):**
- Arriba/Abajo: Control de throttle (aceleración)
- Izquierda/Derecha: Control de yaw (giro)

**Joystick derecho (PITCH/ROLL):**
- Arriba/Abajo: Control de pitch (inclinación adelante/atrás)
- Izquierda/Derecha: Control de roll (inclinación lateral)

Los valores PWM se muestran debajo de cada joystick (1000-2000, centro 1500).

### 5.6 Panel Lateral

Desliza desde el borde izquierdo o presiona el ícono de menú para abrir:

**Acciones Rápidas:**
- ARMAR/DESARMAR
- DESPEGUE, ATERRIZAR, RTL, FRENO, HOLD POS, REBOOT FC

**Modos de Vuelo (agrupados):**
- MANUAL: STABILIZE, ACRO, SPORT, DRIFT
- ASISTIDO: ALT_HOLD, POSHOLD, LOITER, BRAKE
- AUTOMÁTICO: AUTO, GUIDED, CIRCLE, FLIP, THROW
- EMERGENCIA/RETORNO: RTL, SMARTRTL, LAND

### 5.7 Emergencias

Presiona **SOS** para abrir el panel de emergencia:

| Botón | Acción |
|-------|--------|
| **DETENER** (■) | Activa BRAKE (freno) o LOITER si no hay GPS |
| **RTL** (⌂) | Return to Launch (retorno a casa) |
| **ATERRIZAJE** (↓) | Aterrizaje inmediato |

Todas las emergencias requieren confirmación antes de ejecutarse.

---

## 6. Pantalla de Telemetría (Telemetry)

Accede deslizando o navegando desde el menú.

### 6.1 Horizonte Artificial

Indicador visual de actitud del dron:
- **Roll:** Rotación del horizonte (ala izquierda/derecha)
- **Pitch:** Desplazamiento vertical del horizonte
- **Yaw:** Valor numérico en grados
- Cielo (azul) y tierra (marrón) separados por la línea de horizonte

### 6.2 Velocidad

- **Horizontal:** Velocidad sobre el suelo en m/s con barra de progreso
- **Vertical:** Velocidad de ascenso/descenso (verde/rojo)

### 6.3 Posición y GPS

| Dato | Descripción |
|------|-------------|
| Altitud | Altura sobre el nivel del mar (m) |
| Latitud | Coordenada en grados decimales |
| Longitud | Coordenada en grados decimales |
| Satélites | Número de satélites GPS visibles |
| HDOP | Precisión horizontal (menor = mejor) |

**Calidad GPS:**
| HDOP | Satélites | Calidad |
|------|-----------|---------|
| < 1.5 | ≥ 8 | EXCELENTE |
| < 2.5 | ≥ 6 | BUENO |
| < 5.0 | ≥ 5 | REGULAR |
| ≥ 5.0 | < 5 | MALO |

### 6.4 Batería

- Porcentaje grande con código de colores
- Voltaje actual
- Barra de progreso con marcadores en 0%, 25%, 50%, 75%, 100%
- Rojo < 20%, Naranja 20-50%, Verde > 50%

---

## 7. Pantalla GPS (Mapa)

### 7.1 Navegación del Mapa

- **Tocar el mapa:** Crear un waypoint en esa ubicación
- **Arrastrar:** Mover el mapa libremente
- **Botón 🛰/🗺:** Alternar entre satelital y estándar
- **Botón ⌖:** Centrar y seguir al dron

### 7.2 Crear Waypoints

1. Toca cualquier punto en el mapa
2. Selecciona:
   - **Solo marcar:** Agrega el waypoint a la lista sin navegar
   - **Ir ahora:** Agrega y envía el dron inmediatamente
3. Selecciona la altitud del waypoint (5, 10, 20, 30, 50m)

### 7.3 Gestión de Waypoints

- Los waypoints aparecen como chips numerados abajo
- **Tocar un chip:** Enviar el dron a ese waypoint
- **Mantener presionado:** Eliminar el waypoint
- **Botón ✕:** Limpiar todos los waypoints
- **Línea punteada:** Ruta desde el dron hasta los waypoints

### 7.4 Indicadores GPS

- **Anillo verde:** Círculo de precisión basado en HDOP
- **Pulso del marcador:** Indicación visual de conexión
- **Overlay sin GPS:** Se muestra cuando no hay señal

---

## 8. Pantalla de Waypoints Relativos

### 8.1 ¿Qué son los waypoints relativos?

Son desplazamientos desde la posición actual del dron, no coordenadas GPS absolutas. Útil para:
- Patrones de búsqueda
- Inspección de estructuras
- Vuelo en formación
- Rutas predecibles

### 8.2 Crear Waypoints Relativos

1. Ingresa valores en metros:
   - **Adelante (m):** Distancia hacia adelante
   - **Derecha (m):** Distancia hacia la derecha
   - **Arriba (m):** Distancia hacia arriba
2. Presiona **+ AÑADIR WAYPOINT**
3. Repite para cada punto de la ruta

### 8.3 Gestionar Waypoints

- Cada waypoint se muestra con su desplazamiento acumulado
- Presiona **▶** para navegar a ese waypoint individualmente
- Presiona **×** para eliminar un waypoint
- Presiona **LIMPIAR** para borrar todos

### 8.4 Acciones de Misión

| Botón | Acción |
|-------|--------|
| **📤 SUBIR** | Sube los waypoints como misión al dron |
| **▶ INICIAR** | Inicia la ejecución de la misión (cambia a AUTO) |
| **🗑 LIMPIAR** | Limpia la misión del dron |

### 8.5 Guardar/Cargar Waypoints

Los waypoints se pueden guardar para reutilizar:

1. Escribe un nombre en el campo de texto
2. Presiona **💾 GUARDAR** para guardar la lista actual
3. Presiona **📂 CARGAR** para cargar waypoints guardados
4. Si hay varios guardados, se muestra lista para seleccionar

Los archivos se almacenan en el servidor en `data/waypoints/`.

---

## 9. Modo Demo (Sin Dron)

Cuando no hay conexión con el servidor, la app activa automáticamente el modo demo:

- **Indicador:** 🎮 DEMO en la barra de estado
- **Simulación:** Posición GPS cerca de Bogotá con movimiento sinusoidal
- **Comandos:** Todos los comandos responden con éxito simulado
- **Propósito:** Familiarizarse con la interfaz sin riesgo

Para salir del modo demo, conecta la app a un servidor con backend funcionando.

---

## 10. Seguridad y Buenas Prácticas

### 10.1 Pre-vuelo

- [ ] Verificar conexión: la barra muestra "● CONECTADO"
- [ ] Verificar GPS: mínimo 6 satélites, HDOP < 2.5
- [ ] Verificar batería: > 50% para vuelo seguro
- [ ] Verificar modo: STABILIZE o ALT_HOLD para despegue manual
- [ ] Verificar que el área de despegue esté despejada

### 10.2 Durante el Vuelo

- Mantener contacto visual con el dron
- Tener el botón RTL accesible en todo momento
- Monitorear batería constantemente
- No realizar cambios bruscos de modo en vuelo

### 10.3 Emergencias

Si algo sale mal:

1. **PÉRDIDA DE CONTROL:** Presiona RTL en emergencias
2. **OBSTÁCULO:** El auto-avoid frena automáticamente (si hay cámara)
3. **BATERÍA BAJA:** Aterriza inmediatamente
4. **FALLA DE GPS:** Usa ALT_HOLD o STABILIZE

### 10.4 Post-vuelo

- [ ] Aterrizar y desarmar motores
- [ ] Guardar waypoints de la misión si es necesario
- [ ] Revisar logs en `logs/` si hubo errores
- [ ] Recargar baterías

---

## 11. Troubleshooting

### 11.1 La app no se conecta al servidor

1. Verifica que el servidor esté corriendo:
   ```bash
   # Deberías ver los logs de inicio
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
2. Verifica la IP en la configuración:
   - La app usa la IP configurada durante la compilación
   - O editar `mobile/src/config.ts` y recompilar
3. Prueba la conexión desde el navegador:
   - `http://<IP>:8000/` → debe mostrar `{"message":"Drone Control API","version":"1.0.0","status":"running"}`
4. Verifica que el firewall permita el puerto 8000

### 11.2 El dron no responde a comandos

1. Verifica que el dron esté conectado (barra de estado)
2. Verifica que el dron tenga GPS fix
3. Algunos modos requieren GPS (GUIDED, AUTO, LOITER, RTL)
4. Verifica los logs del backend para errores MAVLink

### 11.3 El joystick no funciona

1. Verifica que el dron esté armado
2. Algunos modos no permiten override RC (AUTO, LAND, RTL)
3. Cambia a STABILIZE, ALT_HOLD o GUIDED

---

## 12. Mantenimiento del Servidor

### 12.1 Logs

Revisa periódicamente los logs en `logs/`:
- `backend.log` - errores del servidor
- `sim_debug.txt` - actividad del simulador

### 12.2 Base de Datos

Si usas PostgreSQL, monitorea el espacio en disco:
```bash
docker-compose logs postgres
```

### 12.3 Actualizaciones

```bash
git pull
pip install -r backend/requirements.txt --upgrade
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 13. Referencia Rápida

### Atajos y Acciones

| Acción | Cómo hacerlo |
|--------|-------------|
| Armar dron | Botón ARMAR en pantalla principal o panel lateral |
| Despegar | Botón DESPEGUE (confirma en diálogo) |
| Aterrizar | Botón ATERRIZAJE o Emergencia LAND |
| Cambiar modo | Panel lateral → seleccionar modo |
| Emergencia | SOS → DETENER/RTL/ATERRIZAJE |
| Waypoint en mapa | Tocar mapa → Ir ahora |
| Waypoint relativo | Ingresar metros → AÑADIR |
| Guardar ruta | Nombre → GUARDAR en pantalla waypoints |
| Cargar ruta | Nombre → CARGAR |

### Indicadores Visuales

| Color | Significado |
|-------|-------------|
| 🟢 Verde | Normal, seguro |
| 🟡 Naranja | Advertencia |
| 🔴 Rojo | Peligro, emergencia |
| ⚪ Gris | Inactivo, sin datos |
