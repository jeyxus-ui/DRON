#!/usr/bin/env python3
"""
MAVLink UDP Bridge — Raspberry Pi
Lee MAVLink del Pixhawk (serial) y lo reenvía al backend (UDP), y viceversa.
Ejecutar en la Raspberry con:
    python3 mavlink_udp_bridge.py
Variables de entorno:
    MAVLINK_DEVICE   — puerto serial (default: /dev/ttyUSB0)
    MAVLINK_BAUD     — baudrate    (default: 57600)
    BACKEND_HOST     — IP del PC   (default: 10.252.200.181)
    BACKEND_PORT     — puerto UDP  (default: 14550)
    LOCAL_PORT       — puerto UDP local donde escucha (default: 14550)
"""
import os
import socket
import threading
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

MAVLINK_DEVICE = os.getenv('MAVLINK_DEVICE', '/dev/ttyUSB0')
MAVLINK_BAUD   = int(os.getenv('MAVLINK_BAUD', '57600'))
BACKEND_HOST   = os.getenv('BACKEND_HOST', '10.252.200.181')
BACKEND_PORT   = int(os.getenv('BACKEND_PORT', '14550'))
LOCAL_PORT     = int(os.getenv('LOCAL_PORT', '14550'))
BUFFER_SIZE    = 1024


def open_serial():
    import serial
    port = serial.Serial(MAVLINK_DEVICE, baudrate=MAVLINK_BAUD, timeout=0.1)
    logger.info('Serial abierto: %s @ %d', MAVLINK_DEVICE, MAVLINK_BAUD)
    return port


def serial_to_udp(ser, sock, backend_addr, stop_event):
    """Lee bytes del Pixhawk y los envía al backend por UDP."""
    logger.info('serial→UDP iniciado (destino %s:%d)', *backend_addr)
    while not stop_event.is_set():
        try:
            data = ser.read(BUFFER_SIZE)
            if data:
                sock.sendto(data, backend_addr)
        except Exception as e:
            logger.error('serial→UDP error: %s', e)
            time.sleep(0.5)


def udp_to_serial(ser, sock, stop_event):
    """Recibe bytes del backend por UDP y los escribe al Pixhawk por serial."""
    logger.info('UDP→serial iniciado (escuchando :%d)', LOCAL_PORT)
    while not stop_event.is_set():
        try:
            sock.settimeout(1.0)
            data, addr = sock.recvfrom(BUFFER_SIZE)
            if data:
                ser.write(data)
        except socket.timeout:
            pass
        except Exception as e:
            logger.error('UDP→serial error: %s', e)
            time.sleep(0.5)


def run():
    stop_event = threading.Event()

    try:
        ser = open_serial()
    except Exception as e:
        logger.error('No se pudo abrir serial %s: %s', MAVLINK_DEVICE, e)
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('0.0.0.0', LOCAL_PORT))
    except OSError as e:
        logger.warning('No se pudo bind :%d (%s) — solo envío', LOCAL_PORT, e)

    backend_addr = (BACKEND_HOST, BACKEND_PORT)
    logger.info('Bridge iniciado: %s → udp://%s:%d', MAVLINK_DEVICE, BACKEND_HOST, BACKEND_PORT)

    t1 = threading.Thread(target=serial_to_udp, args=(ser, sock, backend_addr, stop_event), daemon=True)
    t2 = threading.Thread(target=udp_to_serial, args=(ser, sock, stop_event), daemon=True)
    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info('Deteniendo bridge...')
    finally:
        stop_event.set()
        t1.join(timeout=2)
        t2.join(timeout=2)
        ser.close()
        sock.close()
        logger.info('Bridge detenido.')


if __name__ == '__main__':
    run()
