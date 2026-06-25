#!/usr/bin/env python3
"""
Entry point para Raspberry Pi Companion.
Inicia el puente de datos: lee Pixhawk + sensores y envía al backend.
"""
import logging
import os
import signal
import sys
import time

logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='[%(asctime)s] %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def main():
    logger.info('=' * 60)
    logger.info('Raspberry Pi Companion — Bridge de datos')
    logger.info('=' * 60)
    logger.info('Backend URL: %s', os.getenv('BACKEND_URL', 'http://127.0.0.1:8000'))
    logger.info('MAVLink:    %s @ %s baud',
                os.getenv('MAVLINK_DEVICE', '/dev/ttyUSB0'),
                os.getenv('MAVLINK_BAUD', '57600'))
    logger.info('Intervalo:  %s s', os.getenv('SENSOR_INTERVAL', '0.1'))
    logger.info('=' * 60)

    bridge = None
    shutdown = threading.Event()

    def _signal_handler(signum, frame):
        logger.info('Señal %s recibida, deteniendo...', signum)
        shutdown.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        from bridge import DroneBridge
        bridge = DroneBridge()
        bridge.start()

        logger.info('Bridge corriendo. Ctrl+C para detener.')
        shutdown.wait()

    except ImportError as e:
        logger.error('Error importando bridge: %s', e)
        logger.error('Asegúrate de ejecutar desde el directorio raspberry/')
        sys.exit(1)
    except Exception as e:
        logger.exception('Error fatal: %s', e)
        sys.exit(1)
    finally:
        if bridge:
            bridge.stop()
        logger.info('Bridge detenido. Bye.')


if __name__ == '__main__':
    import threading
    main()
