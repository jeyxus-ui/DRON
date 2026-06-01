#!/usr/bin/env python3
"""Check GPS status in SITL."""
import subprocess, time, os, signal
from pymavlink import mavutil

print('Starting SITL...')
proc = subprocess.Popen(
    ['/home/usuario/ardupilot/build/sitl/bin/arducopter', '--model', 'quad', '--speedup', '1',
     '--home', '-35.363262,149.165237,584,270', '-I0', '--synthetic-clock'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(8)

master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=10)
modes = master.mode_mapping()

print('Monitoring GPS for 15s...')
for _ in range(30):
    msg = master.recv_match(blocking=True, timeout=0.5)
    if msg is None:
        continue
    t = msg.get_type()
    if t == 'GPS_RAW_INT':
        print(f'  GPS: fix={msg.fix_type} sats={msg.satellites_visible} lat={msg.lat} lon={msg.lon} alt={msg.alt} eph={msg.eph} epv={msg.epv}')
    elif t == 'GLOBAL_POSITION_INT':
        print(f'  GLOBAL_POS: lat={msg.lat} lon={msg.lon} alt={msg.relative_alt/1000}m')
    elif t == 'STATUSTEXT':
        if 'GPS' in msg.text:
            print(f'  STATUS: {msg.text}')
    elif t == 'SYS_STATUS':
        print(f'  SYS_STATUS: gps_fix={msg.onboard_control_sensors_present & 0x20} sensors={msg.onboard_control_sensors_present:08x}')
    elif t == 'HEARTBEAT':
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        ms = mavutil.mode_string_v10(msg) or str(msg.custom_mode)
        print(f'  HB: mode={ms} armed={armed}')
    elif t == 'COMMAND_ACK':
        print(f'  ACK: cmd={msg.command} result={msg.result}')

master.close()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
proc.wait(timeout=5)
print('Done')
