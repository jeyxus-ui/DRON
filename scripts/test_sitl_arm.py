#!/usr/bin/env python3
"""
Self-contained SITL test: starts arducopter, connects directly via TCP,
tests ARM sequence. Bypasses MAVProxy entirely.
"""
import subprocess, time, os, signal, sys
from pymavlink import mavutil

# Start SITL
ardupilot_dir = '/home/usuario/ardupilot'
sitl_bin = f'{ardupilot_dir}/build/sitl/bin/arducopter'
copter_parm = f'{ardupilot_dir}/Tools/autotest/default_params/copter.parm'

print('Starting SITL...')
proc = subprocess.Popen(
    [sitl_bin, '--model', 'quad', '--speedup', '1',
     '--home', '-35.363262,149.165237,584,270',
     '-I0', '--synthetic-clock'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
)
time.sleep(5)  # Wait for startup

# Connect directly to SITL's TCP port 5760
print('Connecting to tcp:127.0.0.1:5760...')
master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=10)
print(f'Connected! target_sys={master.target_system}')

modes = master.mode_mapping()
print(f'Modes: {list(modes.keys())}')

# Read ARMING_CHECK
master.mav.param_request_read_send(master.target_system, master.target_component, b'ARMING_CHECK', -1)
msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
if msg:
    print(f'ARMING_CHECK = {msg.param_value}')
else:
    print('ARMING_CHECK: no response')

# Set ARMING_CHECK=0 (skip all checks)
print('\nSetting ARMING_CHECK=0...')
master.mav.param_set_send(master.target_system, master.target_component,
    b'ARMING_CHECK', 0.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)

# Verify
master.mav.param_request_read_send(master.target_system, master.target_component, b'ARMING_CHECK', -1)
msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
if msg:
    print(f'ARMING_CHECK now = {msg.param_value}')
else:
    print('ARMING_CHECK: verify failed')

# Set STABILIZE first (doesn't need GPS)
print('Setting STABILIZE...')
master.mav.set_mode_send(master.target_system, modes['STABILIZE'], 0, 0)
time.sleep(2)

msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
if msg:
    print(f'Mode: {mavutil.mode_string_v10(msg)}, Armed={bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)}')

# ARM with force
print('\nARMING (param2=21196)...')
master.mav.command_long_send(master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)

# Monitor for 15s
print('\nMonitoring for 15s...')
start = time.time()
while time.time() - start < 15:
    msg = master.recv_match(blocking=True, timeout=1)
    if msg is None:
        continue
    t = time.time() - start
    if msg.get_type() == 'HEARTBEAT':
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        ms = mavutil.mode_string_v10(msg) or str(msg.custom_mode)
        print(f'  t={t:.1f}s HEARTBEAT mode={ms} armed={armed}')
    elif msg.get_type() == 'STATUSTEXT':
        print(f'  t={t:.1f}s STATUS: {msg.text}')
    elif msg.get_type() == 'COMMAND_ACK':
        print(f'  t={t:.1f}s COMMAND_ACK cmd={msg.command} result={msg.result}')
    elif msg.get_type() in ['SYS_STATUS', 'GPS_RAW_INT', 'ATTITUDE']:
        pass  # too noisy
    else:
        print(f'  t={t:.1f}s {msg.get_type()}')

# Clean up
master.close()
print('\nKilling SITL...')
os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
proc.wait(timeout=5)
print('Done')
