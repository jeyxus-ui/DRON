# 🚁 Raspberry Pi Companion - MAVLink Module

Módulo minimalista para Raspberry Pi que se conecta a Pixhawk vía USB/UART.

## 📋 Requisitos

- Raspberry Pi 3B+ o superior
- Pixhawk/ArduCopter
- Cable USB (Pixhawk-to-RPi) o conexión UART

### Permisos de puerto serial (importante)

En Raspberry Linux el dispositivo serial (ej. `/dev/ttyUSB0`) requiere permisos de grupo `dialout`. Ejecuta:

```bash
sudo usermod -aG dialout $(whoami)
# Cierra sesión o reinicia para aplicar
```

Alternativamente puedes ejecutar `main.py` con `sudo` (no recomendado). Para acceso persistente sin sudo considera una regla `udev`.

## 🚀 Instalación rápida

```bash
# Clonar/descargar este módulo en la Pi
cd /home/pi/drone/
git clone <repo> .

# Instalar dependencias (recomendado dentro de un virtualenv)
pip install -r requirements.txt

# Ejecutar prueba (puedes configurar puerto/baud con variables de entorno)
MAVLINK_DEVICE=/dev/ttyUSB0 MAVLINK_BAUD=57600 python3 main.py
```

## 📁 Estructura

```
raspberry/
├── connection.py      # Clase MAVLinkConnection (núcleo)
├── main.py           # Script de prueba
├── requirements.txt   # Dependencias
└── README.md         # Este archivo
```

## ⚙️ Configurar puerto y baudrate

Edita `main.py` o usa variables de entorno:

```python
# Por defecto usa /dev/ttyUSB0 y 57600, pero puedes exportar env vars:
# MAVLINK_DEVICE and MAVLINK_BAUD
```

### Detectar puerto en Raspberry

```bash
ls /dev/tty*
```

Busca `/dev/ttyUSB*` o `/dev/ttyAMA*`

## 💻 Uso en código

```python
from connection import MAVLinkConnection

# Conectar (mejor usar env vars para no editar el script)
drone = MAVLinkConnection("/dev/ttyUSB0", 57600)

# Verificar conexión
if drone.is_connected():
    print("✅ Conectado")
    
    # Iniciar lectura de telemetría
    drone.start_telemetry_loop()
    
    # Enviar comando
    drone.send_arm()
    drone.send_mode("GUIDED")
    
    # Limpiar
    drone.stop_telemetry_loop()
    drone.disconnect()
```

## 📡 Métodos disponibles

### Conexión

- `connect()` - Conectar (se llama automático en __init__)
- `disconnect()` - Desconectar
- `is_connected()` - Verificar estado

### Telemetría

- `recv_match(msg_type, blocking=False, timeout=None)` - Recibir mensaje específico
- `start_telemetry_loop()` - Iniciar thread de lectura (no bloqueante)
- `stop_telemetry_loop()` - Detener thread

### Comandos

- `send_arm()` - Armar motores
- `send_disarm()` - Desarmar motores
- `send_mode(mode_name)` - Cambiar modo (GUIDED, RTL, LOITER, etc)
- `wait_ack(command_id, timeout=3)` - Esperar confirmación de comando

## 🔧 Logs

El módulo usa logging estándar de Python:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Niveles disponibles: DEBUG, INFO, WARNING, ERROR, CRITICAL

## ⚠️ Notas importantes

- El heartbeat se espera con timeout=10s
- Los reintentos de conexión son automáticos (exponential backoff)
- El telemetry loop es **no bloqueante** (corre en thread separado)
- Los mensajes se procesan cada 0.01s por defecto

## 🚀 Próximos pasos

Después puedes agregar:
- Guardado de logs en archivo
- API REST simple en puerto local
- Sincronización con backend PC
- Grabación de misiones

## 📝 Licencia

Parte del proyecto `back-mavlink`
