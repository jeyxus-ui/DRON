# Instrucciones para ejecutar SITL (Software In The Loop) de Pixhawk

Para simular un Pixhawk, usa ArduPilot SITL.

## Requisitos:
- WSL (Windows Subsystem for Linux) instalado.
- Ubuntu en WSL.

## Pasos:
1. Abre WSL (Ubuntu).
2. Instala dependencias:
   ```
   sudo apt update
   sudo apt install git python3 python3-pip
   ```
3. Clona ArduPilot:
   ```
   git clone https://github.com/ArduPilot/ardupilot.git
   cd ardupilot
   ```
4. Instala prereqs:
   ```
   ./Tools/environment_install/install-prereqs-ubuntu.sh
   ```
5. Construye:
   ```
   ./waf configure --board sitl
   ./waf build --target copter
   ```
6. Ejecuta SITL:
   ```
   cd ArduCopter
   ../Tools/autotest/sim_vehicle.py -w
   ```
   Esto iniciará el simulador en UDP 127.0.0.1:14550.

El backend se conectará automáticamente.

## Para Raspberry Pi con Pixhawk Real
- Conecta la Pixhawk vía USB.
- Ejecuta el script `scripts/deploy_raspberry.sh` para desplegar todo automáticamente.
- El backend se conectará directamente a la Pixhawk.