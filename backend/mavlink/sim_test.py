"""Pequeño script para probar `MAVController` en modo SIM.

Ejecútalo para verificar que los métodos básicos funcionan sin hardware.
"""
import time
from backend.mavlink.controller import MAVController


def run():
    mc = MAVController('SIM', 0)

    print('Estado inicial:', mc.get_status())

    print('Preflight checks:', mc.preflight_checks())

    print('Armando...')
    mc.arm()
    time.sleep(0.2)
    print('Estado:', mc.get_status())

    print('Takeoff a 5m...')
    mc.takeoff(5)
    time.sleep(0.5)
    print('Telemetry:', mc.get_telemetry())

    print('Goto posición (1.0, 1.0, 10)')
    mc.goto_position(1.0, 1.0, 10)
    print('Telemetry:', mc.get_telemetry())

    print('Cambiando parámetro TEST_PARAM=3.14')
    mc.set_param('TEST_PARAM', 3.14)
    print('Get param:', mc.get_param('TEST_PARAM'))

    print('Subiendo misión de prueba...')
    wp = [{'lat': 1.0, 'lon': 1.0, 'alt': 10}, {'lat': 1.1, 'lon': 1.1, 'alt': 12}]
    mc.upload_mission(wp)
    mc.start_mission()
    print('Modo:', mc.get_status())

    print('Limpiando misión...')
    mc.clear_mission()
    print('OK')


if __name__ == '__main__':
    run()
