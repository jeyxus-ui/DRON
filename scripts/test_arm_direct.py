#!/usr/bin/env python3
"""
Minimal test to diagnose SITL immediate disarm after arming.
Connects via TCP to MAVProxy, tests ARMING_CHECK vs ARMING_SKIPCHK.
"""
from pymavlink import mavutil
import time, sys

WSL_IP = '172.28.252.91'
PORT = 14650

master = mavutil.mavlink_connection(f'tcp:{WSL_IP}:{PORT}', source_system=255)
master.wait_heartbeat(timeout=10)
print(f'Connected! target_sys={master.target_system}, target_comp={master.target_component}')

modes = master.mode_mapping()
print(f'Modes: {list(modes.keys())}')

# Read current ARMING_CHECK and ARMING_SKIPCHK params
for pname in ['ARMING_CHECK', 'ARMING_SKIPCHK']:
    master.mav.param_request_read_send(master.target_system, master.target_component, pname.encode(), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
    if msg:
        print(f'{pname} = {msg.param_value} (id={msg.param_id})')
    else:
        print(f'{pname}: no response')

# Try ARMING_CHECK=0 first
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

# Set GUIDED
print('Setting GUIDED...')
master.mav.set_mode_send(master.target_system, modes['GUIDED'], 0, 0)
time.sleep(2)

# ARM with force
print('ARMING (force, param2=21196)...')
master.mav.command_long_send(master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)

# Monitor for 10 seconds
print('\nMonitoring heartbeat for 10s...')
start = time.time()
while time.time() - start < 10:
    msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
    if msg:
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        mode_str = mavutil.mode_string_v10(msg) or str(msg.custom_mode)
        print(f'  t={time.time()-start:.1f}s mode={mode_str} armed={armed}')
    # Also catch STATUSTEXT for disarm reasons
    st = master.recv_match(type='STATUSTEXT', blocking=False)
    if st:
        print(f'  >> STATUS: {st.text}')

master.close()
