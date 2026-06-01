#!/usr/bin/env python3
"""Monitor ALL messages from SITL to debug GPS."""
import subprocess, time, os, signal, sys
from pymavlink import mavutil

sys.stdout.reconfigure(line_buffering=True)

print('=== Starting SITL ===')
proc = subprocess.Popen(
    ['/home/usuario/ardupilot/build/sitl/bin/arducopter', '--model', 'quad',
     '--speedup', '1', '--home', '-35.363262,149.165237,584,270', '-I0'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid)
time.sleep(10)

print('=== Connecting ===')
master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=15)
print(f'Connected!')

# Check SIM_GPS params
for p in ['SIM_GPS_ENABLE', 'SIM_GPS_DISABLE', 'SIM_GPS_TYPE', 'SIM_GPS1_DISABLE', 'SIM_GPS1_ENABLE']:
    master.mav.param_request_read_send(1, 1, p.encode(), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
    if msg:
        print(f'{p} = {msg.param_value}')

# Raw monitoring
print('\n=== RAW MONITORING (20s) ===')
counts = {}
for _ in range(40):
    msg = master.recv_match(blocking=True, timeout=0.5)
    if msg is None:
        continue
    t = msg.get_type()
    counts[t] = counts.get(t, 0) + 1
    if t == 'GPS_RAW_INT':
        print(f'GPS_RAW_INT: fix={msg.fix_type} sats={msg.satellites_visible} lat={msg.lat}')
    elif t == 'GLOBAL_POSITION_INT':
        print(f'GLOBAL_POS_INT: lat={msg.lat} lon={msg.lon} alt={msg.relative_alt/1000}m')
    elif t == 'STATUSTEXT':
        if any(kw in msg.text.upper() for kw in ['GPS', 'EKF', 'ARM', 'HOME']):
            print(f'STATUS: {msg.text}')
    elif t == 'SYS_STATUS':
        sensors = msg.onboard_control_sensors_present
        gps_present = bool(sensors & (1 << 5))
        gps_healthy = bool(msg.onboard_control_sensors_health & (1 << 5))
        print(f'SYS_STATUS: GPS_present={gps_present} GPS_healthy={gps_healthy}')

print(f'\nMessage counts: {dict(sorted(counts.items()))}')

master.close()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
proc.wait(timeout=5)
print('Done')
