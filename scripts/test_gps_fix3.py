#!/usr/bin/env python3
"""Force SIM_GPS1_FIXTYPE=3 and check GPS fix."""
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

# Set SIM_GPS1_FIXTYPE = 3
print('Setting SIM_GPS1_FIXTYPE=3...')
master.mav.param_set_send(1, 1, b'SIM_GPS1_FIXTYPE', 3.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)

# Verify
master.mav.param_request_read_send(1, 1, b'SIM_GPS1_FIXTYPE', -1)
msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
if msg:
    print(f'SIM_GPS1_FIXTYPE = {msg.param_value}')

# Request GPS_RAW_INT
print('Requesting GPS_RAW_INT...')
master.mav.command_long_send(1, 1,
    mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT, 0, 0, 0, 0, 0, 0)

for _ in range(20):
    msg = master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=0.5)
    if msg:
        print(f'GPS_RAW_INT: fix={msg.fix_type} sats={msg.satellites_visible} lat={msg.lat}')
        break
else:
    print('No GPS_RAW_INT')

# Try setting GUIDED
print('Setting GUIDED...')
modes = master.mode_mapping()
master.mav.set_mode_send(1, modes['GUIDED'], 0, 0)
time.sleep(2)
msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
ms = mavutil.mode_string_v10(msg) if msg else '?'
print(f'Mode: {ms}')

# ARM in GUIDED
if ms == 'GUIDED':
    print('ARMING...')
    master.mav.command_long_send(1, 1,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
    time.sleep(3)
    msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
    if msg:
        armed = bool(msg.base_mode & 128)
        print(f'Armed: {armed}')
else:
    print('GUIDED rejected')

master.close()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
proc.wait(timeout=5)
print('Done')
