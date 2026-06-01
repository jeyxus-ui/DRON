#!/usr/bin/env python3
"""
Test ARM after waiting for full system initialization.
Diagnoses: 1) ARMING_CHECK param, 2) force ARM after EKF/GPS ready.
"""
import subprocess, time, os, signal
from pymavlink import mavutil

ardupilot_dir = '/home/usuario/ardupilot'
sitl_bin = f'{ardupilot_dir}/build/sitl/bin/arducopter'

print('Starting SITL...')
proc = subprocess.Popen(
    [sitl_bin, '--model', 'quad', '--speedup', '1',
     '--home', '-35.363262,149.165237,584,270',
     '-I0', '--synthetic-clock'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
)
time.sleep(5)

master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=10)
print(f'Connected! target_sys={master.target_system}')
modes = master.mode_mapping()

# Wait for EKF/GPS init
print('Waiting for system init (10s)...')
start = time.time()
while time.time() - start < 10:
    msg = master.recv_match(type='STATUSTEXT', blocking=True, timeout=0.5)
    if msg:
        t = time.time() - start
        if any(kw in msg.text for kw in ['GPS', 'EKF', 'Ready', 'init', 'Arm']):
            print(f'  t={t:.1f}s {msg.text}')

# Read params
for pname in ['ARMING_CHECK', 'ARMING_SKIPCHK']:
    master.mav.param_request_read_send(master.target_system, master.target_component, pname.encode(), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
    if msg:
        print(f'{pname} = {msg.param_value} (type={msg.param_type})')
    else:
        print(f'{pname}: no response')

# Also try listing all params to find the right name
print('\nSearching for arming-related params...')
master.mav.param_request_list_send(master.target_system, master.target_component)
for _ in range(200):
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
    if msg is None:
        break
    pid = msg.param_id.decode() if hasattr(msg.param_id, 'decode') else msg.param_id
    if 'ARM' in pid.upper() or 'SKIP' in pid.upper():
        print(f'  {pid} = {msg.param_value}')

# Set STABILIZE (doesn't need GPS)
print('\nSetting STABILIZE mode...')
master.mav.set_mode_send(master.target_system, modes['STABILIZE'], 0, 0)
time.sleep(2)

# Check heartbeat
msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
if msg:
    print(f'Mode: {mavutil.mode_string_v10(msg)}, Armed={bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)}')

# ARM with force
print('\nARMING (param2=21196)...')
master.mav.command_long_send(master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)

# Monitor for 20s
print('\nMonitoring for 20s...')
start = time.time()
while time.time() - start < 20:
    msg = master.recv_match(blocking=True, timeout=0.5)
    if msg is None:
        continue
    t = time.time() - start
    if msg.get_type() == 'HEARTBEAT':
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        ms = mavutil.mode_string_v10(msg) or str(msg.custom_mode)
        print(f'  t={t:.1f}s mode={ms} armed={armed}')
    elif msg.get_type() == 'STATUSTEXT':
        print(f'  t={t:.1f}s STATUS: {msg.text}')
    elif msg.get_type() == 'COMMAND_ACK':
        print(f'  t={t:.1f}s ACK cmd={msg.command} result={msg.result}')
    elif msg.get_type() == 'SYS_STATUS':
        pass  # noisy
    elif msg.get_type() == 'GPS_RAW_INT':
        print(f'  t={t:.1f}s GPS: fix={msg.fix_type} sats={msg.satellites_visible}')
    elif msg.get_type() in ['VFR_HUD', 'ATTITUDE', 'LOCAL_POSITION_NED', 'GLOBAL_POSITION_INT']:
        pass  # noisy

master.close()
print('\nKilling SITL...')
os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
proc.wait(timeout=5)
print('Done')
