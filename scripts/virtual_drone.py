"""
MAVLink virtual drone using pymavlink for proper CRC/encoding.
Sends telemetry to QGC (UDP 14550) and backend (UDP 14551).
Acts as ArduCopter so QGC shows it online.
"""
import socket
import time
import struct
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink2

WINDOWS_HOST = "127.0.0.1"
QGC_PORT = 14550
BACKEND_PORT = 14551

def pack_msg(mav, msg):
    """Pack a MAVLink message into bytes using the dialect's PacketBase."""
    buf = msg.pack(mav)
    return buf

def main():
    mav = mavlink2.MAVLink(None)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = 0
    sysid = 1
    compid = 1
    
    print(f"Sending MAVLink to {WINDOWS_HOST}:{QGC_PORT} and :{BACKEND_PORT}")
    
    t_start = time.time()
    while True:
        now_ms = int((time.time() - t_start) * 1000) & 0xFFFFFFFF
        
        msgs = [
            mav.heartbeat_encode(
                type=mavlink2.MAV_TYPE_QUADROTOR,
                autopilot=mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
                base_mode=0,
                custom_mode=0,
                system_status=mavlink2.MAV_STATE_STANDBY,
            ),
            mav.sys_status_encode(
                onboard_control_sensors_present=0x0F4240,
                onboard_control_sensors_enabled=0x0F4240,
                onboard_control_sensors_health=0x0F4240,
                load=500,
                voltage_battery=12600,
                current_battery=-1,
                battery_remaining=85,
                drop_rate_comm=0,
                errors_comm=0,
                errors_count1=0,
                errors_count2=0,
                errors_count3=0,
                errors_count4=0,
            ),
            mav.gps_raw_int_encode(
                time_usec=int((time.time() - t_start) * 1e6) & 0xFFFFFFFFFFFFFFFF,
                lat=47110000,
                lon=-740721000,
                alt=2600000,
                eph=100,
                epv=100,
                vel=0,
                cog=0,
                fix_type=3,
                satellites_visible=12,
            ),
            mav.attitude_encode(
                time_boot_ms=now_ms,
                roll=0.0,
                pitch=0.0,
                yaw=0.0,
                rollspeed=0.0,
                pitchspeed=0.0,
                yawspeed=0.0,
            ),
            mav.vfr_hud_encode(
                airspeed=0.0,
                groundspeed=0.0,
                heading=0,
                throttle=0,
                alt=2600.0,
                climb=0.0,
            ),
            mav.global_position_int_encode(
                time_boot_ms=now_ms,
                lat=-35363262,
                lon=149165237,
                alt=58400,
                relative_alt=0,
                vx=0,
                vy=0,
                vz=0,
                hdg=0,
            ),
        ]
        
        for msg in msgs:
            buf = msg.pack(mav)
            # Set sysid, compid, seq in the header
            # pymavlink MAVLink_message uses these fields
            try:
                buf = bytearray(buf)
                buf[3] = seq & 0xFF   # seq
                buf[4] = sysid & 0xFF  # sysid
                buf[5] = compid & 0xFF # compid
                buf = bytes(buf)
            except:
                pass
            
            sock.sendto(buf, (WINDOWS_HOST, QGC_PORT))
            sock.sendto(buf, (WINDOWS_HOST, BACKEND_PORT))
        
        seq = (seq + 1) & 0xFF
        time.sleep(0.2)  # 5 Hz

if __name__ == "__main__":
    main()
