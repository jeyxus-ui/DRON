#!/usr/bin/env python3
"""Check ALL SIM_GPS and GPS params."""
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
print(f'Connected!')

# Request all params
print('Reading all params...')
master.mav.param_request_list_send(1, 1)

gps_params = {}
start = time.time()
while time.time() - start < 15:
    msg = master.recv_match(blocking=True, timeout=0.3)
    if msg is None:
        continue
    if msg.get_type() == 'PARAM_VALUE':
        pid = msg.param_id.decode() if hasattr(msg.param_id, 'decode') else str(msg.param_id)
        val = msg.param_value
        if 'GPS' in pid.upper() or 'SIM_' in pid.upper() or 'SR0' in pid or 'SERIAL' in pid or 'HOME' in pid.upper() or 'ARM' in pid.upper():
            gps_params[pid] = val
    elif msg.get_type() == 'GPS_RAW_INT':
        print(f'GPS_RAW_INT: fix={msg.fix_type} sats={msg.satellites_visible} lat={msg.lat} lon={msg.lon}')
    elif msg.get_type() == 'STATUSTEXT':
        if 'GPS' in msg.text or 'ARM' in msg.text:
            print(f'STATUS: {msg.text}')

print(f'\nGPS/SIM params ({len(gps_params)}):')
for k, v in sorted(gps_params.items()):
    print(f'  {k} = {v}')

# Check version
print('\nFirmware version:')
master.mav.command_long_send(1, 1,
    mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
    148, 0, 0, 0, 0, 0, 0)  # AUTOPILOT_VERSION = 148
time.sleep(0.5)
msg = master.recv_match(type='AUTOPILOT_VERSION', blocking=True, timeout=3)
if msg:
    print(f'  flight_sw_version: {msg.flight_sw_version}')
    print(f'  flight_custom_version: {bytes(msg.flight_custom_version).hex()}')

master.close()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
proc.wait(timeout=5)
print('Done')
