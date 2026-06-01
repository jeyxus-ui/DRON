"""Runner minimal para iniciar el backend usando una cadena MAVLink

Este script permite usar dispositivos tipo `udp:127.0.0.1:14550` sin pasar
por `detect_mavlink_device()` del proyecto. No modifica la lógica del proyecto;
solo inicializa el controlador antes de arrancar Uvicorn y ejecuta el servidor
sin ejecutar los eventos de `startup` (lifespan desactivado) para evitar
re-inicializaciones que dependan de la detección automática.

Uso:
  MAVLINK_DEVICE=udp:127.0.0.1:14550 MAVLINK_BAUD=57600 python3 backend/run_with_device.py
"""
import os
import logging
import sys

logger = logging.getLogger("run_with_device")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    device = os.getenv('MAVLINK_DEVICE')
    if not device:
        logger.error('MAVLINK_DEVICE not set. Example: MAVLINK_DEVICE=udp:127.0.0.1:14550')
        sys.exit(2)

    try:
        baud = int(os.getenv('MAVLINK_BAUD', os.getenv('BAUD', '57600')))
    except Exception:
        logger.warning('Invalid MAVLINK_BAUD, falling back to 57600')
        baud = 57600

    logger.info(f"Initializing MAV controller on device={device} baud={baud}")

    # Import rest lazily (project code) and initialize MAVController directly
    try:
        from backend.api import rest
    except Exception as e:
        logger.exception(f"Failed to import backend.api.rest: {e}")
        sys.exit(3)

    try:
        success = rest.init_mav(device, baud)
        if not success:
            logger.error('rest.init_mav returned False')
        else:
            # Start monitoring thread so behavior matches original startup
            try:
                rest.start_monitoring(baud, interval=5)
            except Exception:
                logger.debug('Could not start rest monitoring thread')
    except Exception as e:
        logger.exception(f"rest.init_mav raised exception: {e}")
        # Continue to start the server so the API is available (as in original design)

    # Run uvicorn but disable lifespan so backend.main startup handlers that perform
    # device detection do not override our manual initialization.
    try:
        import uvicorn

        logger.info('Starting uvicorn (lifespan=off) backend.main:app on 0.0.0.0:8000')
        uvicorn.run('backend.main:app', host='0.0.0.0', port=8000, lifespan='off')
    except Exception as e:
        logger.exception(f"Failed to start uvicorn: {e}")
        sys.exit(4)


if __name__ == '__main__':
    main()
