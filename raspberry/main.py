#!/usr/bin/env python3
"""
Main entry point para Raspberry Pi Companion
Ajusta el puerto y baudrate según tu setup
"""

import logging
import sys
import time
import os
from connection import MAVLinkConnection

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Función main para prueba básica de conexión"""
    
    # ========================================
    # PUERTO y BAUDRATE (pueden configurarse vía variables de entorno)
    # ========================================
    PORT = os.getenv('MAVLINK_DEVICE', '/dev/ttyUSB0')
    BAUD = int(os.getenv('MAVLINK_BAUD', os.getenv('BAUD', '57600')))
    
    logger.info("=" * 60)
    logger.info("🚁 Raspberry Pi Companion - MAVLink Test")
    logger.info("=" * 60)
    logger.info(f"Puerto: {PORT}")
    logger.info(f"Baudrate: {BAUD}")
    logger.info("=" * 60)
    
    try:
        # Conectar
        # Intentar detectar problemas de permiso/archivo antes de inicializar
        try:
            # Intento rápido de abrir con pyserial si está disponible
            import serial
            try:
                s = serial.Serial(PORT, BAUD, timeout=0.5)
                s.close()
            except Exception as e:
                logger.warning(f"No se pudo abrir {PORT}: {e} - verifica permisos (sudo usermod -aG dialout $(whoami))")
        except Exception:
            # pyserial no instalado o no disponible; dejamos que la conexión trate el error
            pass

        drone = MAVLinkConnection(PORT, BAUD)
        
        if not drone.is_connected():
            logger.error("❌ No se pudo conectar al Pixhawk")
            sys.exit(1)
        
        logger.info("✅ Conexión establecida")
        
        # Iniciar lectura de telemetría
        drone.start_telemetry_loop(interval=0.1)
        
        logger.info("📡 Leyendo telemetría por 30 segundos...")
        logger.info("Presiona Ctrl+C para detener")
        
        try:
            # Mantener el programa corriendo
            for i in range(300):  # 30 segundos
                time.sleep(0.1)
                if not drone.is_connected():
                    logger.warning("⚠️ Conexión perdida")
                    break
        except KeyboardInterrupt:
            logger.info("\n⏹️ Deteniendo...")
        
        # Limpiar
        drone.stop_telemetry_loop()
        drone.disconnect()
        
        logger.info("✅ Desconectado")
    
    except ConnectionError as e:
        logger.error(f"❌ Error de conexión: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
