#!/usr/bin/env python3
"""Request GPS data explicitly and set stream rates."""
import subprocess, time, os, signal, sys
from pymavlink import mavutil

sys.stdout.reconfigure(line_buffering=True)

print('Starting SITL...')
proc = subprocess.Popen(
    ['/home/usuario/ardupilot/build/sitl/bin/arducopter', '--model', 'quad',
     '--speedup', '1', '--home', '-35.363262,149.165237,584,270', '-I0'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
time.sleep(10)

master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=15)
print('Connected!')

# Check stream rate params
for p in ['SR0_EXTRA1', 'SR0_EXTRA2', 'SR0_EXTRA3', 'SR0_POSITION', 'SR0_RAW_SENS']:
    master.mav.param_request_read_send(1, 1, p.encode(), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
    print(f'{p}: {msg.param_value if msg else "no response"}')

# Request GPS data explicitly
print('\nRequesting GPS_RAW_INT...')
master.mav.command_long_send(1, 1,
    mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT, 0, 0, 0, 0, 0, 0)
time.sleep(0.5)

# Drain messages for 5s looking for GPS
print('Listening for GPS data (5s)...')
for _ in range(50):
    msg = master.recv_match(blocking=True, timeout=0.1)
    if msg is None:
        continue
    t = msg.get_type()
    if t == 'GPS_RAW_INT':
        print(f'GPS_RAW_INT: fix={msg.fix_type} sats={msg.satellites_visible} lat={msg.lat}')
        break
    elif t == 'GLOBAL_POSITION_INT':
        print(f'GLOBAL_POS: lat={msg.lat} lon={msg.lon} alt={msg.relative_alt/1000}m')
    elif t == 'STATUSTEXT':
        print(f'STATUS: {msg.text}')
    elif t == 'COMMAND_ACK':
        print(f'ACK: cmd={msg.command} result={msg.result}')
else:
    print('No GPS data received')

# Try setting stream rate
print('\nSetting SERIAL0 stream rates to 10Hz...')
for sr in ['SR0_EXTRA1', 'SR0_EXTRA2', 'SR0_EXTRA3', 'SR0_POSITION']:
    master.mav.param_set_send(1, 1, sr.encode(), 10.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)

print('Listening again (5s)...')
for _ in range(50):
    msg = master.recv_match(blocking=True, timeout=0.1)
    if msg is None:
        continue
    t = msg.get_type()
    if t in ('GPS_RAW_INT', 'GLOBAL_POSITION_INT', 'SYS_STATUS', 'VFR_HUD'):
        if t == 'GPS_RAW_INT':
            print(f'GPS_RAW_INT: fix={msg.fix_type} sats={msg.satellites_visible}')
            break
        elif t == 'GLOBAL_POSITION_INT':
            print(f'GLOBAL_POS: lat={msg.lat} lon={msg.lon}')
        elif t == 'SYS_STATUS':
            print(f'SYS_STATUS: GPS_health={bool(msg.onboard_control_sensors_health & (1<<5))} load={msg.load}')
        elif t == 'VFR_HUD':
            print(f'VFR_HUD: alt={msg.alt}m')
    elif t == 'STATUSTEXT':
        print(f'STATUS: {msg.text}')
else:
    print('No streaming data after setting rates')

# Try requesting GPS report
print('\nSending MAV_CMD_REQUEST_MESSAGE for GPS_STATUS...')
master.mav.command_long_send(1, 1,
    mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
    234, 0, 0, 0, 0, 0, 0)  # GPS_STATUS = 234 (deprecated, but worth trying)
time.sleep(1)
for _ in range(10):
    msg = master.recv_match(blocking=True, timeout=0.3)
    if msg and msg.get_type() not in ('HEARTBEAT', 'TIMESYNC', 'BAD_DATA'):
        print(f'{msg.get_type()}')

master.close()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
proc.wait(timeout=5)
print('\nDone')
