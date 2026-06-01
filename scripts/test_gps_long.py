#!/usr/bin/env python3
"""Monitor GPS for 60s with synthetic-clock."""
import subprocess, time, os, signal
from pymavlink import mavutil

print('Starting SITL...')
proc = subprocess.Popen(
    ['/home/usuario/ardupilot/build/sitl/bin/arducopter', '--model', 'quad',
     '--speedup', '1', '--home', '-35.363262,149.165237,584,270', '-I0',
     '--synthetic-clock'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
time.sleep(10)

master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=15)
print('Connected!')

# Check SIM_GPS params properly
for pname in ['SIM_GPS1_ENABLE', 'SIM_GPS1_TYPE', 'SIM_GPS1_DISABLE']:
    master.mav.param_request_read_send(1, 1, pname.encode(), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
    if msg:
        print(f'{pname} = {msg.param_value}')

# Long monitor
print('Monitoring 40s for GPS...')
start = time.time()
while time.time() - start < 40:
    msg = master.recv_match(blocking=True, timeout=0.5)
    if msg is None:
        continue
    t = msg.get_type()
    if t in ('GPS_RAW_INT', 'GLOBAL_POSITION_INT', 'SYS_STATUS', 'VFR_HUD', 'HEARTBEAT'):
        print(f'{t}: ', end='')
        if t == 'GPS_RAW_INT':
            print(f'fix={msg.fix_type} sats={msg.satellites_visible}')
        elif t == 'GLOBAL_POSITION_INT':
            print(f'lat={msg.lat} lon={msg.lon} alt={msg.relative_alt/1000}m')
        elif t == 'SYS_STATUS':
            gps_h = bool(msg.onboard_control_sensors_health & (1<<5))
            gps_p = bool(msg.onboard_control_sensors_present & (1<<5))
            print(f'GPS_present={gps_p} GPS_health={gps_h}', end='')
            print(f' load={msg.load} battery={msg.voltage_battery/1000}V')
        elif t == 'VFR_HUD':
            print(f'alt={msg.alt}m groundspeed={msg.groundspeed}')
        elif t == 'HEARTBEAT':
            armed = bool(msg.base_mode & 0b10000000)
            print(f'armed={armed}')
    elif t == 'STATUSTEXT':
        print(f'STATUS: {msg.text}')
    elif t != 'PARAM_VALUE':
        print(f'OTHER: {t}')

master.close()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
proc.wait(timeout=5)
print('Done')
