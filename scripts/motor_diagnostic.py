"""
Script de diagnóstico para investigar por qué los motores dejaron de girar.
Conecta directo al Pixhawk vía MAVLink e imprime todo el estado relevante.

Uso:
  python scripts/motor_diagnostic.py [device]
  Ejemplo: python scripts/motor_diagnostic.py /dev/ttyACM0
"""

import sys
import time
import struct

from pymavlink import mavutil, mavwp


def connect(device: str, baud: int = 115200):
    print(f"\n{'='*60}")
    print(f"🔌 Conectando a {device} @ {baud} baud...")
    print('='*60)
    master = mavutil.mavlink_connection(device, baud=baud, source_system=255)
    master.wait_heartbeat(timeout=10)
    print(f"✅ Heartbeat recibido (sys={master.target_system}, comp={master.target_component})")
    return master


def read_param(master, name: str, timeout: float = 3.0):
    """Lee un parámetro del Pixhawk y devuelve su valor."""
    master.mav.param_request_read_send(
        master.target_system, master.target_component,
        name.encode('utf-8'), -1
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=timeout)
        if msg:
            try:
                pid = msg.param_id.decode('utf-8').strip('\x00')
            except Exception:
                pid = str(msg.param_id)
            if pid == name:
                return msg.param_value
    return None


def request_message(master, msg_id: int, interval_us: int = 500_000):
    """Solicitar un mensaje MAVLink específico."""
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0, msg_id, interval_us, 0, 0, 0, 0, 0,
    )
    time.sleep(0.3)


def check_heartbeat(master):
    print(f"\n{'─'*60}")
    print("💓 HEARTBEAT")
    print('─'*60)
    msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
    if msg:
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        mode = mavutil.mode_string_v10(msg)
        print(f"  Armed:     {armed}")
        print(f"  Mode:      {mode}")
        print(f"  Type:      {msg.type}")
        print(f"  System:    {msg.system_status}")
        return armed, mode
    else:
        print("  ⚠️  No heartbeat received!")
        return None, None


def check_battery(master):
    print(f"\n{'─'*60}")
    print("🔋 BATTERY_STATUS")
    print('─'*60)
    msg = master.recv_match(type='BATTERY_STATUS', blocking=True, timeout=3)
    if msg:
        volts = [v for v in msg.voltages if v != 65535]
        print(f"  Voltages:     {[f'{v/1000:.2f}V' for v in volts]}")
        print(f"  Current:      {msg.current_battery / 100.0:.2f} A")
        print(f"  Remaining:    {msg.battery_remaining}%")
        print(f"  Cell count:   {len(volts)}S")
        print(f"  Total:        {sum(volts)/1000:.2f}V" if volts else "  No voltage data")
    else:
        print("  ⚠️  No BATTERY_STATUS received")


def check_servo_output_raw(master):
    print(f"\n{'─'*60}")
    print("⚙️  SERVO_OUTPUT_RAW (PWM real saliendo del Pixhawk)")
    print('─'*60)
    request_message(master, mavutil.mavlink.MAVLINK_MSG_ID_SERVO_OUTPUT_RAW, 200_000)
    msg = master.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=2)
    if msg:
        for i in range(1, 9):
            pwm = getattr(msg, f'servo{i}_raw', 0)
            marker = ' ⬅️' if i <= 4 else ''
            print(f"  CH{i}: {pwm:>5} us{marker}")
        print(f"  Port: {msg.port}")
    else:
        print("  ⚠️  No SERVO_OUTPUT_RAW received")


def check_rc_channels(master):
    print(f"\n{'─'*60}")
    print("📻 RC_CHANNELS (lo que el Pixhawk ve como entrada)")
    print('─'*60)
    request_message(master, mavutil.mavlink.MAVLINK_MSG_ID_RC_CHANNELS, 200_000)
    msg = master.recv_match(type='RC_CHANNELS', blocking=True, timeout=2)
    if msg:
        for i in range(1, 9):
            chan = getattr(msg, f'chan{i}_raw', 0)
            rssi = getattr(msg, 'rssi', 0)
            marker = ' ⬅️ (override activo)' if chan != 65535 and i <= 4 else ''
            if chan != 65535:
                print(f"  CH{i}: {chan:>5}{marker}")
        print(f"  RSSI: {rssi}")
    else:
        print("  ⚠️  No RC_CHANNELS received")


def check_ekf(master):
    print(f"\n{'─'*60}")
    print("🧭 EKF_STATUS_REPORT")
    print('─'*60)
    request_message(master, mavutil.mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 200_000)
    msg = master.recv_match(type='EKF_STATUS_REPORT', blocking=True, timeout=2)
    if msg:
        flags = msg.flags
        print(f"  Flags:      0x{flags:04x}")
        print(f"  Velocity:   {bool(flags & 0x01)}")
        print(f"  Pos Horz:   {bool(flags & 0x02)}")
        print(f"  Pos Vert:   {bool(flags & 0x04)}")
        print(f"  Compass:    {bool(flags & 0x08)}")
        print(f"  TerrainAlt: {bool(flags & 0x10)}")
        print(f"  ConstPos:   {bool(flags & 0x20)}")
        print(f"  OptFlow:    {bool(flags & 0x40)}")
        aligned = bool(flags & 0x07)
        print(f"  ✅ EKF aligned: {aligned}")
    else:
        print("  ⚠️  No EKF_STATUS_REPORT received")


def check_sys_status(master):
    print(f"\n{'─'*60}")
    print("📊 SYS_STATUS")
    print('─'*60)
    msg = master.recv_match(type='SYS_STATUS', blocking=True, timeout=3)
    if msg:
        print(f"  Voltage:       {msg.voltage_battery / 1000:.2f}V" if msg.voltage_battery != 65535 else "  Voltage: N/A")
        print(f"  Current:       {msg.current_battery / 100.0:.2f}A" if msg.current_battery != -1 else "  Current: N/A")
        print(f"  Battery rem:   {msg.battery_remaining}%")
        print(f"  Errors comm:   {msg.errors_count1}")
        print(f"  Errors count:  {msg.errors_count2}")
        print(f"  Sensors en:    0x{msg.onboard_control_sensors_enabled:08x}")
        print(f"  Sensors health: 0x{msg.onboard_control_sensors_health:08x}")
    else:
        print("  ⚠️  No SYS_STATUS received")


def check_gps(master):
    print(f"\n{'─'*60}")
    print("🛰️  GPS_RAW_INT")
    print('─'*60)
    msg = master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=3)
    if msg:
        print(f"  Fix type:     {msg.fix_type} (3=3D fix)")
        print(f"  Satellites:   {msg.satellites_visible}")
        print(f"  Lat/Lon:      {msg.lat / 1e7:.6f}, {msg.lon / 1e7:.6f}")
        print(f"  Alt:          {msg.alt / 1000:.1f}m")
        print(f"  HDOP:         {msg.eph / 100:.1f}" if msg.eph != 65535 else "  HDOP: N/A")
    else:
        print("  ⚠️  No GPS_RAW_INT received")


def check_statustext(master):
    """Lee STATUSTEXT recientes del buffer."""
    print(f"\n{'─'*60}")
    print("📝 STATUSTEXT (mensajes recientes del Pixhawk)")
    print('─'*60)
    found = 0
    for _ in range(20):
        msg = master.recv_match(type='STATUSTEXT', blocking=False)
        if msg:
            text = msg.text.decode('utf-8', errors='replace') if isinstance(msg.text, bytes) else str(msg.text)
            print(f"  [{msg.severity}] {text}")
            found += 1
        else:
            break
    if found == 0:
        print("  (no status messages in buffer)")


def main():
    device = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
    baud = 115200

    master = connect(device, baud)

    # ── 1. Heartbeat / estado básico ──
    armed, mode = check_heartbeat(master)
    check_battery(master)

    # ── 2. Parámetros críticos ──
    print(f"\n{'─'*60}")
    print("⚙️  PARÁMETROS CRÍTICOS")
    print('─'*60)
    critical_params = [
        'MOT_SPIN_ARM', 'DISARM_DELAY', 'ARMING_CHECK',
        'RC_OVERRIDE_TIME', 'BRD_SAFETY_DEFLT',
        'MOT_PWM_MIN', 'MOT_PWM_MAX',
        'BATT_MONITOR', 'BATT_N_CELLS',
        'SERVO_BLH_*',  # Not real, just placeholder
    ]
    for name in critical_params:
        if '*' in name:
            continue
        val = read_param(master, name)
        if val is not None:
            print(f"  {name:>20} = {val}")
        else:
            print(f"  {name:>20} = ⚠️  no response / not found")

    # ── 3. PWM output ──
    check_servo_output_raw(master)

    # ── 4. RC input ──
    check_rc_channels(master)

    # ── 5. EKF ──
    check_ekf(master)

    # ── 6. SYS_STATUS ──
    check_sys_status(master)

    # ── 7. GPS ──
    check_gps(master)

    # ── 8. STATUSTEXT ──
    check_statustext(master)

    # ── 9. Resumen y diagnóstico ──
    print(f"\n{'='*60}")
    print("📋 RESUMEN DE DIAGNÓSTICO")
    print('='*60)

    if armed is False:
        print("\n❌ EL DRON NO ESTÁ ARMADO — esta es la causa más probable")
        print("   Razones posibles:")
        print("   - Pre-arm checks fallando (GPS, EKF, battery)")
        print("   - Safety switch activado (ver BRD_SAFETY_DEFLT)")
        print("   - ARMING_CHECK bloqueando")
        print("   - EKF no alineado (sin GPS en interiores)")
        print("   Solución: enviar ARM con force=True desde el backend")
    elif armed is True:
        print("\n✅ El dron SÍ está armado")
        print("   Pero los motores no giran. Posibles causas:")
        print("   1. MOT_SPIN_ARM = 0 → motores no giran en idle (debe ser >0)")
        print("   2. SERVO_OUTPUT_RAW muestra 1000 en todos → sin PWM")
        print("      → RC_OVERRIDE no está llegando al Pixhawk")
        print("      → O el throttle está en 0 en rc_override.py")
        print("   3. Revisar RC_CHANNELS: si CH3=1000, el throttle está en mínimo")
        print("   4. El failsafe de rc_override.py pudo haber desarmado")

    print(f"\n💡 Próximos pasos:")
    print(f"   - Ejecutar: python scripts/motor_diagnostic.py")
    print(f"   - Verificar SERVO_OUTPUT_RAW vs RC_CHANNELS")
    print(f"   - Ver parámetro MOT_SPIN_ARM")
    print(f"   - Probar motor test: curl -X POST 'http://localhost:8000/api/diag/motor-test?motor=0&throttle=15&duration=2'")
    print(f"   - Revisar logs del backend por mensajes de failsafe o disarm")

    master.close()
    print("\n🔌 Conexión cerrada.")


if __name__ == '__main__':
    main()
