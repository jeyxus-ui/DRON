# Guía de Instalación y Despliegue
## Sistema de Control y Telemetría para Drones

**Versión:** 1.0.0  
**Fecha:** Mayo 2026

---

## 1. Requisitos del Sistema

### 1.1 Hardware Mínimo

| Componente | Especificación |
|------------|----------------|
| **Servidor** | Raspberry Pi 4/5 (4GB+ RAM) o PC/Laptop |
| **Dron** | Vehículo con autopiloto ArduPilot (Pixhawk, Cube, etc.) |
| **Cámara (opcional)** | Intel RealSense D435i o cámara USB |
| **Dispositivo móvil** | Android 8.0+ con Wi-Fi |
| **Red** | Wi-Fi local (misma red para servidor y app) |

### 1.2 Software Requerido

| Software | Versión Mínima | Propósito |
|----------|----------------|-----------|
| Python | 3.10 | Backend |
| Node.js | 20 | Compilación app móvil |
| PostgreSQL (opcional) | 15 | Base de datos |
| Docker (opcional) | 24 | Contenedores |
| Git | Cualquiera | Control de versiones |

### 1.3 Puertos de Red

| Puerto | Servicio | Descripción |
|--------|----------|-------------|
| 8000 | Backend API | REST + WebSocket |
| 5432 | PostgreSQL | Base de datos |
| 14550 | UDP | QGroundControl (simulación) |
| 14551 | TCP | Conexión sim_drone |

---

## 2. Instalación del Servidor

### 2.1 Linux (Recomendado)

#### Ubuntu/Debian / Raspberry Pi OS

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Python y dependencias del sistema
sudo apt install -y python3 python3-pip python3-venv git

# Opcional: PostgreSQL
sudo apt install -y postgresql postgresql-client

# Opcional: Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 2.2 Windows

```bash
# Requisitos:
# 1. Python 3.10+ desde python.org (agregar a PATH)
# 2. Git desde git-scm.com
# 3. Opcional: Docker Desktop

# Verificar instalación
python --version
pip --version
git --version
```

### 2.3 macOS

```bash
# Usando Homebrew
brew install python@3.10 git

# Opcional: PostgreSQL
brew install postgresql@15
brew services start postgresql@15
```

---

## 3. Clonar y Configurar el Repositorio

```bash
# Clonar
git clone <url-del-repositorio>
cd back-mavlink

# Crear y activar entorno virtual (recomendado)
python -m venv venv

# Linux/Mac:
source venv/bin/activate

# Windows:
# .\venv\Scripts\activate

# Instalar dependencias Python
pip install -r backend/requirements.txt
```

### 3.1 Configurar Variables de Entorno

Editar `.env` en la raíz del proyecto:

```env
# PostgreSQL (opcional - si no tienes BD, el sistema funciona igual)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=drones
DB_USER=dronix_user
DB_PASSWORD=DronixSecure2024!
DB_URL=postgresql://dronix_user:DronixSecure2024!@localhost:5432/drones

# MAVLink - Configura según tu caso:
#   /dev/ttyACM0    → Pixhawk por USB
#   tcp:127.0.0.1:14551 → sim_drone.py
#   udpin:0.0.0.0:14550 → SITL
#   SIM             → Simulador interno
MAVLINK_DEVICE=SIM
MAVLINK_BAUD=115200

# Backend API
API_HOST=0.0.0.0
API_PORT=8000

# Logging
LOG_LEVEL=INFO
```

---

## 4. Iniciar el Sistema

### 4.1 Inicio Rápido (Simulación)

```bash
# Opción A: Solo backend con simulador interno
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Opción B: Backend + sim_drone.py (ventanas separadas)
# Terminal 1:
python scripts/sim_drone.py

# Terminal 2:
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Opción C: Windows (powershell)
.\scripts\start_all.ps1

# Opción D: Linux/Mac
./scripts/start_all.sh
```

### 4.2 Verificar que funciona

```bash
# La API debe responder:
curl http://localhost:8000/
# → {"message":"Drone Control API","version":"1.0.0","status":"running"}

# Health check:
curl http://localhost:8000/health
# → {"status":"healthy"}

# Estado del dron:
curl http://localhost:8000/api/status
# → {"connected":true,"armed":false,"mode":"STABILIZE","system_status":4}
```

---

## 5. Instalación de la App Móvil

### 5.1 Compilar APK

```bash
# Instalar dependencias Node.js
cd mobile
npm install

# Configurar IP del servidor
# Editar: mobile/src/config.ts
# Cambiar HOST_IP a la IP de tu servidor

# Compilar APK release
npx react-native build-android --mode=release

# El APK se genera en:
# mobile/android/app/build/outputs/apk/release/app-release.apk
```

### 5.2 Instalar en Dispositivo

1. Transfiere el APK al dispositivo Android
2. Habilita "Instalar apps de orígenes desconocidos" en Ajustes
3. Abre el archivo APK y sigue las instrucciones
4. Asegúrate de que el dispositivo esté en la misma red Wi-Fi que el servidor

### 5.3 Despliegue Rápido (sin compilar)

```bash
# Instalación directa desde el código
npx react-native run-android
# Requiere: dispositivo conectado por USB con depuración USB activada
```

---

## 6. Configuración con Dron Real (Pixhawk)

### 6.1 Conexión por USB

```bash
# 1. Conectar Pixhawk al servidor por USB
# 2. Identificar el puerto:
#    Linux: ls /dev/ttyACM*  o  ls /dev/ttyUSB*
#    Windows: Revisar Administrador de Dispositivos → Puertos COM

# 3. Configurar .env:
MAVLINK_DEVICE=/dev/ttyACM0
MAVLINK_BAUD=115200

# 4. Iniciar backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 6.2 Conexión por Radio Telemetría

```bash
# La radio telemetría (3DR, SiK) usa 57600 baud
MAVLINK_DEVICE=/dev/ttyUSB0
MAVLINK_BAUD=57600
```

### 6.3 Permisos en Linux

```bash
# Agregar usuario al grupo dialout para acceso a puertos seriales
sudo usermod -a -G dialout $USER

# Alternativa temporal:
sudo chmod 666 /dev/ttyACM0
```

---

## 7. Despliegue con Docker

### 7.1 Docker Compose (Todos los Servicios)

```yaml
# docker-compose.yml ya incluido en el proyecto
# Incluye: postgres, backend, frontend
```

```bash
# Iniciar todos los servicios
docker-compose up --build -d

# Ver logs
docker-compose logs -f backend

# Detener servicios
docker-compose down

# Detener y eliminar volúmenes
docker-compose down -v
```

### 7.2 Docker Solo Backend

```bash
# Construir imagen
docker build -t drone-backend -f backend/Dockerfile .

# Ejecutar
docker run -d \
  --name drone-backend \
  -p 8000:8000 \
  -e MAVLINK_DEVICE=SIM \
  -e API_HOST=0.0.0.0 \
  -e API_PORT=8000 \
  drone-backend
```

### 7.3 Docker en Raspberry Pi

```bash
# El docker-compose.yml ya tiene platform configurado:
# backend: linux/amd64
# frontend: linux/arm64/v8
# postgres: linux/arm64/v8

docker-compose up --build -d
```

---

## 8. Despliegue en Raspberry Pi

### 8.1 Script Automatizado

```bash
chmod +x scripts/deploy_raspberry.sh
./scripts/deploy_raspberry.sh
```

### 8.2 Instalación Manual

```bash
# 1. Instalar sistema operativo (Raspberry Pi OS Lite 64-bit)
# 2. Conectar por SSH
ssh pi@<raspberry-pi-ip>

# 3. Clonar repositorio
git clone <url-del-repositorio>
cd back-mavlink

# 4. Ejecutar script de despliegue
./scripts/deploy_raspberry.sh

# 5. El script:
#    - Instala dependencias del sistema
#    - Crea entorno virtual Python
#    - Instala dependencias Python
#    - Configura PostgreSQL
#    - Crea tablas
#    - Configura servicio systemd para inicio automático
#    - Inicia el backend

# 6. Verificar estado
sudo systemctl status drone-backend
```

### 8.3 Servicio Systemd

El script crea un servicio systemd:

```bash
# Ver estado
sudo systemctl status drone-backend

# Ver logs
sudo journalctl -u drone-backend -f

# Reiniciar
sudo systemctl restart drone-backend

# Detener
sudo systemctl stop drone-backend
```

---

## 9. Configuración de Red

### 9.1 Red Local

```
Servidor (IP: 192.168.1.100)    Dispositivo Móvil (IP: 192.168.1.50)
         │                                    │
         └─────────── Wi-Fi Router ───────────┘
                     (192.168.1.1)
```

- El servidor y el móvil deben estar en la misma red
- La app se conecta a la IP del servidor (puerto 8000)
- Si usas emulador BlueStacks, usa la IP LAN del host

### 9.2 Firewall

```bash
# Linux (ufw)
sudo ufw allow 8000/tcp   # Backend API
sudo ufw allow 22/tcp      # SSH
sudo ufw enable

# Windows (PowerShell como Admin)
New-NetFirewallRule -DisplayName "Drone Backend" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

### 9.3 IP Fija (Recomendado)

**Raspberry Pi / Linux:**
```bash
# Editar /etc/dhcpcd.conf
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=8.8.8.8
```

**Windows:**
```
Configuración de Red → Wi-Fi → Administrar redes conocidas
→ Propiedades → Editar asignación de IP → Manual → IPv4
```

---

## 10. Simulación SITL (ArduPilot)

### 10.1 Instalar SITL

```bash
# En Linux/WSL
pip install mavproxy
sudo apt install -y simgear

# Descargar ArduPilot
git clone https://github.com/ArduPilot/ardupilot.git
cd ardupilot
git submodule update --init --recursive

# Instalar herramientas SITL
Tools/environment_install/install-prereqs-ubuntu.sh -y
```

### 10.2 Ejecutar SITL

```bash
# Terminal 1: SITL
cd ardupilot
sim_vehicle.py -v ArduCopter --console --map

# Terminal 2: Backend
cd back-mavlink
MAVLINK_DEVICE=udpin:0.0.0.0:14550 uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Opcional: QGroundControl (conectar a udp:127.0.0.1:14550)
```

### 10.3 SITL en WSL (Windows)

```bash
# Usar los scripts bridge incluidos
python scripts/bridges/sitl_bridge_wsl.py
# o
python scripts/bridges/bridge_wsl.py
```

---

## 11. Base de Datos PostgreSQL

### 11.1 Instalación

```bash
# Linux
sudo apt install -y postgresql postgresql-client

# Iniciar servicio
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 11.2 Configuración

```bash
# Acceder a PostgreSQL
sudo -u postgres psql

# Crear usuario y base de datos
CREATE USER dronix_user WITH PASSWORD 'DronixSecure2024!';
CREATE DATABASE drones OWNER dronix_user;
GRANT ALL PRIVILEGES ON DATABASE drones TO dronix_user;
\q
```

### 11.3 Crear Tablas

```bash
# Opción A: Script dedicado
python scripts/create_tables.py

# Opción B: El backend crea las tablas automáticamente al iniciar
# (si la BD está configurada y accesible)
```

---

## 12. Configuración de Cámara

### 12.1 Intel RealSense D435i

```bash
# Linux: instalar SDK
sudo apt install -y librealsense2-dev librealsense2-dkms

# Verificar conexión
rs-enumerate-devices

# La cámara se detecta automáticamente al iniciar el backend
```

### 12.2 Cámara USB Genérica

```bash
# El backend prueba automáticamente los índices: 4, 2, 0, 1, 3, 5
# Verificar dispositivo:
ls /dev/video*
v4l2-ctl --list-devices
```

### 12.3 Sin Cámara

El backend funciona sin cámara. La detección de objetos y el auto-avoid simplemente no estarán disponibles.

---

## 13. Verificación Post-Instalación

### 13.1 Checklist

- [ ] Servidor iniciado: `curl http://localhost:8000/` responde
- [ ] MAVLink conectado: `curl http://localhost:8000/api/status` muestra connected=true
- [ ] App móvil instalada y conectada (barra de estado verde)
- [ ] Joysticks responden
- [ ] Comandos ARM/DISARM funcionan (en simulación)
- [ ] TAKEOFF/LAND funcionan
- [ ] Waypoints se suben correctamente
- [ ] Cámara (si aplica) muestra video en vivo

### 13.2 Prueba Rápida

```bash
# 1. Iniciar simulación
python scripts/sim_drone.py &
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

# 2. Probar armado
curl -X POST http://localhost:8000/api/arm -H "Content-Type: application/json" -d '{"force": true}'

# 3. Probar takeoff
curl -X POST http://localhost:8000/api/takeoff -H "Content-Type: application/json" -d '{"altitude": 10}'

# 4. Ver telemetría
curl http://localhost:8000/api/telemetry

# 5. Probar goto
curl -X POST http://localhost:8000/api/goto -H "Content-Type: application/json" -d '{"latitude": 4.712, "longitude": -74.073, "altitude": 15}'
```

---

## 14. Troubleshooting de Instalación

### 14.1 "pymavlink" no se instala

```bash
# En Windows puede requerir C++ Build Tools
# Descargar: https://visualstudio.microsoft.com/visual-cpp-build-tools/

# En Linux:
sudo apt install -y python3-dev libxml2-dev libxslt1-dev
```

### 14.2 "No module named 'backend'"

```bash
# Ejecutar desde la raíz del proyecto (back-mavlink/)
# Verificar que el PYTHONPATH incluya el directorio actual
export PYTHONPATH="${PYTHONPATH}:."  # Linux/Mac
$env:PYTHONPATH = "${PYTHONPATH};."  # Windows PowerShell
```

### 14.3 Permiso denegado al puerto serial

```bash
# Linux:
sudo usermod -a -G dialout $USER
# Cerrar sesión y volver a entrar
# O temporalmente:
sudo chmod 666 /dev/ttyACM0
```

### 14.4 PostgreSQL no conecta

```bash
# Verificar que el servicio está corriendo
sudo systemctl status postgresql

# Verificar configuración pg_hba.conf
# Debe permitir conexiones locales con md5
sudo nano /etc/postgresql/15/main/pg_hba.conf
# local   all   all   md5
```

### 14.5 Docker no encuentra platform linux/arm64/v8

```bash
# En Raspberry Pi de 64 bits:
docker run --privileged --rm tonistiigi/binfmt --install all
```

---

## 15. Resumen de Comandos Rápidos

```bash
# Iniciar backend (simulación)
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Iniciar sim_drone (ventana separada)
python scripts/sim_drone.py

# Iniciar todo (Windows)
.\scripts\start_all.ps1

# Iniciar todo (Linux/Mac)
./scripts/start_all.sh

# Compilar APK
cd mobile && npx react-native build-android --mode=release

# Docker
docker-compose up --build -d

# Ver logs del backend
docker-compose logs -f backend

# Despliegue Raspberry Pi
./scripts/deploy_raspberry.sh
```
