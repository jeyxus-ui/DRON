"""End-to-end test: verifies that RC_CHANNELS_OVERRIDE with roll/pitch produces
attitude response from ArduPilot SITL (same code path as the app's right joystick).

Uso: python scripts/sitl_rc_test.py [tcp:127.0.0.1:5760]
"""
import sys
import time

from pymavlink import mavutil


def connect(device: str):
    print(f"🔌 Conectando a {device} ...")
    master = mavutil.mavlink_connection(device, source_system=255, autoreconnect=True)
    master.wait_heartbeat(timeout=10)
    print(f"✅ Heartbeat (sys={master.target_system})")
    return master


def request_message(master, msg_id: int, interval_us: int = 100_000):
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0, msg_id, interval_us, 0, 0, 0, 0, 0,
    )


def set_param(master, name: str, value: float):
    master.mav.param_set_send(
        master.target_system, master.target_component,
        name.encode('utf-8'), float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
    )


def read_param(master, name: str, timeout: float = 3.0):
    master.mav.param_request_read_send(
        master.target_system, master.target_component,
        name.encode('utf-8'), -1,
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


MODE_BY_NAME = {v: k for k, v in mavutil.mode_mapping_acm.items()}
MODE_BY_NAME.setdefault('STABILIZE', 0)


def set_mode(master, mode: str):
    mode_id = MODE_BY_NAME[mode]
    master.set_mode_apm(mode_id)
    time.sleep(0.5)


def read_ack(master, command, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type='COMMAND_ACK', blocking=True, timeout=timeout)
        if msg and msg.command == command:
            return msg.result
    return None


def wait_arm(master, timeout: float = 12.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
        if msg and msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
            return True
    return False


def arm(master, force: bool = True):
    force_val = 21196 if force else 0
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, force_val, 0, 0, 0, 0, 0,
    )
    result = read_ack(master, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
    print(f"ARM ACK result={result} ({mavutil.mavlink.enums['MAV_RESULT'].get(result).name if result is not None else 'none'})")


def disarm(master):
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 0, 21196, 0, 0, 0, 0, 0,
    )
    read_ack(master, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
    time.sleep(1.0)


def get_mode(master, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=timeout)
        if msg:
            return msg.custom_mode, mavutil.mode_string_v10(msg)
    return None, None


def drain_statustext(master, timeout: float = 1.0):
    msgs = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type='STATUSTEXT', blocking=True, timeout=timeout)
        if msg:
            try:
                msgs.append(msg.text.decode('utf-8', 'replace'))
            except Exception:
                msgs.append(str(msg.text))
    return msgs


def latest(master, msg_type: str, timeout: float = 1.0):
    msg = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        m = master.recv_match(type=msg_type, blocking=True, timeout=timeout)
        if m:
            msg = m
    return msg


def get_attitude(master, timeout: float = 1.0):
    msg = latest(master, 'ATTITUDE', timeout)
    if not msg:
        return None
    import math
    return {
        'roll_deg': round(math.degrees(msg.roll), 2),
        'pitch_deg': round(math.degrees(msg.pitch), 2),
        'yaw_deg': round(math.degrees(msg.yaw), 2),
    }


def get_alt(master, timeout: float = 1.0):
    msg = latest(master, 'VFR_HUD', timeout)
    return round(msg.alt, 2) if msg else None


def override(master, ch1=1500, ch2=1500, ch3=1500, ch4=1500):
    master.mav.rc_channels_override_send(
        master.target_system, master.target_component,
        ch1, ch2, ch3, ch4, 65535, 65535, 65535, 65535,
    )


def hold_override(master, ch1, ch2, ch3, ch4, duration: float):
    end = time.time() + duration
    while time.time() < end:
        override(master, ch1, ch2, ch3, ch4)
        time.sleep(0.5)


def main():
    device = sys.argv[1] if len(sys.argv) > 1 else 'tcp:127.0.0.1:5760'
    master = connect(device)

    # ── Preparar SITL ──
    set_param(master, 'ARMING_CHECK', 0)
    set_param(master, 'MOT_SPIN_ARM', 0.15)
    set_param(master, 'DISARM_DELAY', 0)
    time.sleep(1.5)
    set_mode(master, 'STABILIZE')
    time.sleep(1.0)
    mode_id, mode_name = get_mode(master)
    print(f"Modo actual: id={mode_id} name={mode_name}")
    print(f"ARMING_CHECK={read_param(master, 'ARMING_CHECK')}, MOT_SPIN_ARM={read_param(master, 'MOT_SPIN_ARM')}")

    # Streams para leer actitud
    request_message(master, mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE, 100_000)
    request_message(master, mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 500_000)
    request_message(master, mavutil.mavlink.MAVLINK_MSG_ID_VFR_HUD, 200_000)
    time.sleep(1.0)

    print("Esperando 10s para GPS/EKF (SITL)...")
    time.sleep(10)

    pre = drain_statustext(master, 1.5)
    if pre:
        print("STATUSTEXT previos:")
        for t in pre:
            print(f"  • {t}")

    arm(master)
    armed = wait_arm(master)
    print(f"Armed: {armed}")
    post = drain_statustext(master, 1.5)
    if post:
        print("STATUSTEXT tras armar:")
        for t in post:
            print(f"  • {t}")
    if not armed:
        print("❌ No se pudo armar; revisar ACK/log de SITL. Abortando.")
        master.close()
        return

    # ── Despegar (override continuo, throttle > hover) ──
    hold_override(master, 1500, 1500, 1650, 1500, 5.0)
    # Hover
    hold_override(master, 1500, 1500, 1580, 1500, 3.0)
    alt0 = get_alt(master)
    base = get_attitude(master)
    print(f"Baseline attitude (aire, alt={alt0}m): {base}")

    # ── PITCH forward (CH2=1800, hover throttle) ──
    hold_override(master, 1500, 1800, 1580, 1500, 2.0)
    pitch_att = get_attitude(master)
    print(f"Tras PITCH CH2=1800: {pitch_att}  (Δpitch={pitch_att['pitch_deg'] - base['pitch_deg']}°)")

    # ── ROLL right (CH1=1800, hover throttle) ──
    hold_override(master, 1800, 1500, 1580, 1500, 2.0)
    roll_att = get_attitude(master)
    print(f"Tras ROLL CH1=1800: {roll_att}  (Δroll={roll_att['roll_deg'] - base['roll_deg']}°)")

    # ── ROLL+PITCH full ──
    hold_override(master, 1800, 1800, 1580, 1500, 2.0)
    full_att = get_attitude(master)
    print(f"Tras ROLL+PITCH CH=1800: {full_att}  (Δroll={full_att['roll_deg'] - base['roll_deg']}°, Δpitch={full_att['pitch_deg'] - base['pitch_deg']}°)")

    # ── YAW (CH4=1700) — sanity: left joystick path ──
    hold_override(master, 1500, 1500, 1580, 1700, 2.0)
    yaw_att = get_attitude(master)
    print(f"Tras YAW CH4=1700: {yaw_att}  (Δyaw={yaw_att['yaw_deg'] - base['yaw_deg']}°)")

    # ── Aterrizar y liberar ──
    hold_override(master, 1500, 1500, 1400, 1500, 3.0)
    override(master, 0, 0, 0, 0)
    time.sleep(0.5)
    disarm(master)
    print("✅ Test completo. Control liberado y desarmado.")
    master.close()


if __name__ == '__main__':
    main()
