"""
Bidirectional MAVLink simulated drone.
Sends telemetry to QGC (UDP 14550) and backend (TCP 14551).
Processes incoming commands: ARM, DISARM, TAKEOFF, LAND, RTL, GOTO, mission protocol.
"""
import socket, time, threading
from pymavlink.dialects.v20 import ardupilotmega as mavlink2
from pymavlink import mavutil

HOST = "127.0.0.1"
QGC_PORT = 14550
BACKEND_PORT = 14551
TX_PORT = 14552  # sim_drone sends FROM here, listens here for QGC replies

# Bogotá, Colombia: 4.7110° N, -74.0721° W, ~2600m
BOGOTA_LAT = 47110000
BOGOTA_LON = -740721000
BOGOTA_ALT = 2600000

state = dict(
    armed=False, mode="STABILIZE", custom_mode=0,
    lat=BOGOTA_LAT, lon=BOGOTA_LON, alt=BOGOTA_ALT, relative_alt=0,
    vx=0, vy=0, vz=0, hdg=0,
    roll=0.0, pitch=0.0, yaw=0.0,
    rollspeed=0.0, pitchspeed=0.0, yawspeed=0.0,
    groundspeed=0.0, airspeed=0.0, throttle=0, climb=0.0,
    battery_remaining=85, voltage_battery=12600, current_battery=-1,
    satellites_visible=12, fix_type=3, eph=100, epv=100,
)

missions = []
mission_count = 0
home_position = None
seq_counter = 0
goto_target = None  # (lat_int, lon_int, alt_mm) — navegación suave hacia waypoint
lock = threading.Lock()
running = True
t_start = time.time()

# UDP socket for QGC communication
qgc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
qgc_sock.bind((HOST, TX_PORT))
qgc_sock.settimeout(0.05)

# TCP server for backend communication (replaces UDP to avoid socket competition)
be_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
be_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
be_server.bind((HOST, BACKEND_PORT))
be_server.listen(1)
be_server.settimeout(1.0)

be_client = None
be_client_lock = threading.Lock()

mav = mavlink2.MAVLink(None)
mav.srcSystem = 1
mav.srcComponent = 1


import os as _os
_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
_LOG_DIR = _os.path.join(_SCRIPT_DIR, '..', 'logs')
_os.makedirs(_LOG_DIR, exist_ok=True)

def pack_msg(msg):
    mav.seq = seq_counter & 0xFF
    return bytes(msg.pack(mav))


def send_to_all(buf):
    """Send to QGC (UDP:14550) and Backend (TCP:14551)."""
    try:
        qgc_sock.sendto(buf, (HOST, QGC_PORT))
    except Exception as e:
        with open(_os.path.join(_LOG_DIR, "sim_udp_errors.txt"),"a") as _f:
            _f.write(f"UDP sendto error: {e}\n")
    with be_client_lock:
        if be_client:
            try: be_client.send(buf)
            except: pass


def handle_message(msg, _sender):
    global state, missions, mission_count, home_position
    t = msg.get_type()

    if t == "HEARTBEAT":
        return

    if t == "COMMAND_LONG":
        cmd = msg.command
        if cmd == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
            cm = int(msg.param2)
            with open(_os.path.join(_LOG_DIR, "sim_debug.txt"),"a") as f:
                f.write(f"SET_MODE from {_sender}: custom_mode={cm} (p1={msg.param1} p2={msg.param2})\n")
        print(f"[SIM {_sender}] COMMAND_LONG cmd={cmd}")
        p = [msg.param1, msg.param2, msg.param3, msg.param4, msg.param5, msg.param6, msg.param7]
        res = mavutil.mavlink.MAV_RESULT_ACCEPTED

        if cmd == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
            with lock:
                state["armed"] = p[0] == 1
                state["mode"] = "GUIDED" if state["armed"] else "STABILIZE"
                state["custom_mode"] = 4 if state["armed"] else 0
            print(f"[SIM] {'ARM' if state['armed'] else 'DISARM'}")

        elif cmd == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
            alt = p[6] if p[6] else 10
            with lock:
                state["armed"] = True; state["mode"] = "GUIDED"; state["custom_mode"] = 4
                state["alt"] = int(alt * 1000); state["relative_alt"] = int(alt * 1000)
                state["climb"] = 2.0
            print(f"[SIM] TAKEOFF {alt}m")

        elif cmd == mavutil.mavlink.MAV_CMD_NAV_LAND:
            with lock:
                state["mode"] = "LAND"; state["custom_mode"] = 9
                state["armed"] = False; state["alt"] = 0
                state["relative_alt"] = 0; state["climb"] = -0.5
            print("[SIM] LAND")

        elif cmd == mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH:
            with lock:
                state["mode"] = "RTL"; state["custom_mode"] = 11
                if home_position:
                    state["lat"] = home_position[0]; state["lon"] = home_position[1]
            print("[SIM] RTL")

        elif cmd == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
            cm = int(p[1])
            if cm == 17:
                print(f"[SIM] SET_MODE BRAKE ignored from {_sender}")
            else:
                mm = {0: "STABILIZE", 4: "GUIDED", 3: "AUTO", 11: "RTL", 9: "LAND", 1: "ACRO"}
                with lock:
                    state["custom_mode"] = cm; state["mode"] = mm.get(cm, f"C{cm}")
                print(f"[SIM] SET_MODE {state['mode']}")

        elif cmd == mavutil.mavlink.MAV_CMD_DO_SET_HOME:
            with lock:
                home_position = (
                    int(p[4] * 1e7) if p[4] else state["lat"],
                    int(p[5] * 1e7) if p[5] else state["lon"],
                    int(p[6] * 1000) if p[6] else state["alt"],
                )
            print(f"[SIM] HOME {home_position}")

        elif cmd == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT:
            with lock:
                state["lat"] = int(p[4] * 1e7); state["lon"] = int(p[5] * 1e7); state["alt"] = int(p[6] * 1000)
            print(f"[SIM] GOTO {p[4]}, {p[5]}")

        elif cmd == mavutil.mavlink.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES:
            cap = mavutil.mavlink.MAV_PROTOCOL_CAPABILITY_MISSION_FLOAT
            resp = mav.autopilot_version_encode(
                capabilities=cap, flight_sw_version=0x01000000,
                middleware_sw_version=0, os_sw_version=0, board_version=0,
                flight_custom_version=b'\x00'*8, middleware_custom_version=b'\x00'*8,
                os_custom_version=b'\x00'*8, vendor_id=0, product_id=0,
                uid=0xDEADBEEF, uid2=b'\x00'*18,
            )
            send_to_all(pack_msg(resp))
        else:
            res = mavutil.mavlink.MAV_RESULT_UNSUPPORTED
            print(f"[SIM] Unsupported CMD {cmd}")

        ack = mav.command_ack_encode(cmd, res, progress=255, result_param2=0,
                                      target_system=1, target_component=1)
        send_to_all(pack_msg(ack))
        return

    if t == "COMMAND_INT":
        cmd = msg.command
        if cmd == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT:
            with lock:
                state["lat"] = msg.x; state["lon"] = msg.y; state["alt"] = msg.z
            ack = mav.command_ack_encode(cmd, mavutil.mavlink.MAV_RESULT_ACCEPTED,
                                          progress=255, target_system=1, target_component=1)
            send_to_all(pack_msg(ack))

    if t == "MISSION_COUNT":
        with lock:
            missions.clear()
            mission_count = msg.count
        print(f"[SIM] Mission upload: {msg.count} WPs")
        send_to_all(pack_msg(mav.mission_request_int_encode(msg.target_system, msg.target_component, 0)))

    if t == "MISSION_REQUEST_INT":
        with lock:
            if msg.seq < len(missions):
                lat_i, lon_i, alt_f = missions[msg.seq]
                item = mav.mission_item_int_encode(
                    msg.target_system, msg.target_component, msg.seq,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0, 1, 0, 0, 0, 0, lat_i, lon_i, alt_f,
                )
                send_to_all(pack_msg(item))
                if msg.seq == len(missions) - 1:
                    print(f"[SIM] Mission uploaded: {len(missions)} WPs")
                    send_to_all(pack_msg(mav.mission_ack_encode(
                        msg.target_system, msg.target_component, mavutil.mavlink.MAV_MISSION_ACCEPTED)))
            else:
                print(f"[SIM] MISSION_REQUEST_INT seq {msg.seq} OOR")

    if t == "MISSION_ITEM_INT":
        with lock:
            while len(missions) <= msg.seq: missions.append(None)
            missions[msg.seq] = (msg.x, msg.y, msg.z)
            count = mission_count
        if count > 0 and msg.seq >= count - 1:
            print(f"[SIM] Mission uploaded: {count} WPs (via MISSION_ITEM_INT)")
            send_to_all(pack_msg(mav.mission_ack_encode(
                msg.target_system, msg.target_component, mavutil.mavlink.MAV_MISSION_ACCEPTED)))
        else:
            send_to_all(pack_msg(mav.mission_request_int_encode(
                msg.target_system, msg.target_component, msg.seq + 1)))

    if t == "MISSION_SET_CURRENT":
        with lock: state["mode"] = "AUTO"; state["custom_mode"] = 3
        print(f"[SIM] MISSION_SET_CURRENT {msg.seq}")

    if t == "MISSION_CLEAR_ALL":
        with lock: missions.clear()
        print("[SIM] Mission cleared")
        send_to_all(pack_msg(mav.mission_ack_encode(
            msg.target_system, msg.target_component, mavutil.mavlink.MAV_MISSION_ACCEPTED)))

    if t == "PARAM_REQUEST_LIST":
        send_to_all(pack_msg(mav.param_value_encode(
            b"", 0.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32, 0, 65535)))

    if t == "SET_POSITION_TARGET_GLOBAL_INT":
        with lock:
            if int(msg.type_mask) & 0b0000111111111000 != 0b0000111111111000:
                global goto_target
                goto_target = (msg.lat_int, msg.lon_int, int(msg.alt * 1000))
                state["vx"] = msg.vx; state["vy"] = msg.vy
                state["vz"] = msg.vz; state["hdg"] = msg.yaw

    if t == "RC_CHANNELS_OVERRIDE":
        with lock:
            import math as _math
            _pwm_to_norm = lambda pwm: max(-1.0, min(1.0, (pwm - 1500) / 500.0)) if pwm else 0.0
            roll_n   = _pwm_to_norm(msg.chan1_raw)
            pitch_n  = _pwm_to_norm(msg.chan2_raw)
            thr_n    = max(0.0, min(1.0, (msg.chan3_raw - 1000) / 1000.0)) if msg.chan3_raw else 0.0
            yaw_n    = _pwm_to_norm(msg.chan4_raw)

            state["roll"] = roll_n * 45.0
            state["pitch"] = pitch_n * 30.0
            state["yaw"] = (state["yaw"] + yaw_n * 5.0) % 360.0
            state["hdg"] = int(state["yaw"])
            state["throttle"] = int(thr_n * 100)

            state["groundspeed"] = abs(pitch_n) * 15.0 + thr_n * 10.0
            state["airspeed"] = state["groundspeed"]
            state["climb"] = (thr_n - 0.5) * 5.0
            state["relative_alt"] = max(0, state["relative_alt"] + int(state["climb"] * 50))
            state["alt"] = BOGOTA_ALT + state["relative_alt"]

            fwd_cms = pitch_n * 10 * 100
            right_cms = roll_n * 10 * 100
            state["vx"] = int(fwd_cms)
            state["vy"] = int(right_cms)
            state["vz"] = int(-state["climb"] * 100)

            hdg_rad = _math.radians(state["yaw"])
            north_cms = fwd_cms * _math.cos(hdg_rad) - right_cms * _math.sin(hdg_rad)
            east_cms  = fwd_cms * _math.sin(hdg_rad) + right_cms * _math.cos(hdg_rad)
            d_north = north_cms * 0.1 / 100.0
            d_east  = east_cms  * 0.1 / 100.0
            lat_rad = _math.radians(state["lat"] / 1e7)
            d_lat = d_north / 111320.0
            d_lon = d_east / (111320.0 * _math.cos(lat_rad))
            state["lat"] += int(d_lat * 1e7)
            state["lon"] += int(d_lon * 1e7)


def recv_udp_thread(sock, label):
    buf = b""
    while running:
        try:
            data, _ = sock.recvfrom(65535)
            buf += data
            while True:
                msg = mav.parse_char(buf)
                if msg:
                    buf = buf[mav.buf_index:]
                    handle_message(msg, label)
                else:
                    break
        except socket.timeout:
            continue
        except Exception as e:
            if running: print(f"[SIM] {label} recv: {e}")


def recv_tcp_thread():
    """TCP server: accept backend client and read MAVLink messages."""
    global be_client
    while running:
        try:
            client, addr = be_server.accept()
            print(f"[SIM] Backend TCP client connected: {addr}")
            with be_client_lock:
                if be_client:
                    try: be_client.close()
                    except: pass
                be_client = client
                be_client.settimeout(0.05)
            buf = b""
            while running:
                try:
                    data = client.recv(65535)
                    if not data:
                        print("[SIM] Backend client disconnected")
                        break
                    buf += data
                    while True:
                        msg = mav.parse_char(buf)
                        if msg:
                            buf = buf[mav.buf_index:]
                            handle_message(msg, "BKEND")
                        else:
                            break
                except socket.timeout:
                    continue
                except Exception as e:
                    if running: print(f"[SIM] BKEND recv: {e}")
                    break
            with be_client_lock:
                if be_client is client:
                    be_client = None
            try: client.close()
            except: pass
        except socket.timeout:
            continue
        except Exception as e:
            if running: print(f"[SIM] BKEND server: {e}")


GOTO_SPEED_CMS = 200  # 2 m/s velocidad de navegación a waypoint

_nav_count = 0
def _navigate():
    """Mueve el dron suavemente hacia goto_target cada ciclo de telemetría (5Hz)."""
    global goto_target, _nav_count
    if goto_target is None:
        return
    import math as _nm
    tlat, tlon, talt = goto_target
    with lock:
        dlat = (tlat - state["lat"]) / 1e7
        dlon = (tlon - state["lon"]) / 1e7
        dlat_m = dlat * 111320.0
        lon_scale = 111320.0 * _nm.cos(_nm.radians(state["lat"] / 1e7))
        dlon_m = dlon * lon_scale
        dist = _nm.sqrt(dlat_m**2 + dlon_m**2)
        if dist < 0.5:
            state["lat"] = tlat
            state["lon"] = tlon
            state["alt"] = talt
            goto_target = None
            state["groundspeed"] = 0.0
            state["vx"] = 0; state["vy"] = 0
            return
        step_m = GOTO_SPEED_CMS * 0.2 / 100.0
        if step_m > dist:
            step_m = dist
        ratio = step_m / dist
        dlat_step_m = dlat_m * ratio
        dlon_step_m = dlon_m * ratio
        state["lat"] += int(dlat_step_m / 111320.0 * 1e7)
        state["lon"] += int(dlon_step_m / lon_scale * 1e7)
        _nav_count += 1
        if _nav_count % 25 == 0:
            cur_lat = state["lat"] / 1e7
            cur_lon = state["lon"] / 1e7
            print(f"[NAV] cycle#{_nav_count} dist={dist:.1f}m target=({tlat/1e7:.6f},{tlon/1e7:.6f}) cur=({cur_lat:.6f},{cur_lon:.6f})")
        alt_diff = talt - state["alt"]
        alt_step = int(step_m * 50)
        if abs(alt_diff) < 100:
            state["alt"] = talt
        else:
            state["alt"] += int(alt_step if alt_diff > 0 else -alt_step)
        state["groundspeed"] = GOTO_SPEED_CMS / 100.0

def telemetry_thread():
    global seq_counter
    while running:
        _navigate()
        now_ms = int((time.time() - t_start) * 1000) & 0xFFFFFFFF
        now_us = int((time.time() - t_start) * 1e6) & 0xFFFFFFFFFFFFFFFF
        with lock: s = dict(state)

        # GPS slow orbit (10m radius) para mostrar posición viva en QGC incluso en hover
        import math as _jm
        _jt = time.time() * 0.05
        _orbit_r = 90  # ~10m in lat units (1e7 scale)
        _jlat = int(_jm.sin(_jt) * _orbit_r)
        _jlon = int(_jm.cos(_jt) * _orbit_r)

        bm = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        if s["armed"]:
            bm |= mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        if s["mode"] in ("GUIDED", "RTL", "LAND") or s["custom_mode"] in (4, 11, 9):
            bm |= mavutil.mavlink.MAV_MODE_FLAG_GUIDED_ENABLED
        elif s["mode"] == "AUTO" or s["custom_mode"] == 3:
            bm |= mavutil.mavlink.MAV_MODE_FLAG_AUTO_ENABLED
        else:
            bm |= mavutil.mavlink.MAV_MODE_FLAG_STABILIZE_ENABLED

        msgs = [
            mav.heartbeat_encode(mavutil.mavlink.MAV_TYPE_QUADROTOR,
                                  mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                                  bm, s["custom_mode"],
                                  mavutil.mavlink.MAV_STATE_ACTIVE if s["armed"] else mavutil.mavlink.MAV_STATE_STANDBY),
            mav.sys_status_encode(0x0F4240, 0x0F4240, 0x0F4240, 500,
                                  s["voltage_battery"], s["current_battery"], s["battery_remaining"],
                                  0, 0, 0, 0, 0, 0),
            mav.gps_raw_int_encode(now_us, s["fix_type"], s["lat"] + _jlat, s["lon"] + _jlon, s["alt"],
                                    s["eph"], s["epv"], int(s["groundspeed"] * 100),
                                    int(s["hdg"] * 100), s["satellites_visible"]),
            mav.attitude_encode(now_ms, s["roll"], s["pitch"], s["yaw"],
                                s["rollspeed"], s["pitchspeed"], s["yawspeed"]),
            mav.vfr_hud_encode(s["airspeed"], s["groundspeed"], int(s["hdg"]),
                               s["throttle"], s["alt"] / 1000.0, s["climb"]),
            mav.global_position_int_encode(now_ms, s["lat"] + _jlat, s["lon"] + _jlon, s["alt"],
                                           s["relative_alt"], s["vx"], s["vy"], s["vz"], int(s["hdg"])),
        ]
        if home_position:
            h = home_position
            msgs.append(mav.home_position_encode(h[0], h[1], h[2], 0, 0, 0, [1, 0, 0, 0], 0, 0, 0))

        for msg in msgs:
            send_to_all(pack_msg(msg))
            seq_counter = (seq_counter + 1) & 0xFF
        time.sleep(0.2)


def main():
    global running, home_position
    print("="*50)
    print("SIM: Bidirectional MAVLink Virtual Drone")
    print(f"     Send telemetry to QGC:     UDP {HOST}:{QGC_PORT} (from :{TX_PORT})")
    print(f"     Backend TCP server:         tcp://{HOST}:{BACKEND_PORT}")
    print("="*50)
    home_position = (state["lat"], state["lon"], state["alt"])

    threads = [
        threading.Thread(target=recv_udp_thread, args=(qgc_sock, "QGC"), daemon=True),
        threading.Thread(target=recv_tcp_thread, daemon=True),
        threading.Thread(target=telemetry_thread, daemon=True),
    ]
    for t in threads: t.start()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SIM] Shutdown")
        running = False
        qgc_sock.close()
        with be_client_lock:
            if be_client:
                try: be_client.close()
                except: pass
        be_server.close()


if __name__ == "__main__":
    main()
