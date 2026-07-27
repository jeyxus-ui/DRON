#!/usr/bin/env python3
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
m.wait_heartbeat(timeout=5)
print('Connected')
m.mav.param_set_send(m.target_system, m.target_component, b'ARMING_CHECK', 0.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)
m.mav.param_set_send(m.target_system, m.target_component, b'DISARM_DELAY', 0.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)
print('Params set. Now ARM...')

# Set GUIDED mode
mode_id = m.mode_mapping()['GUIDED']
m.set_mode(mode_id)
time.sleep(1)

# ARM
m.mav.command_long_send(
    m.target_system, m.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    0, 1, 21196, 0, 0, 0, 0, 0,
)
print('ARM sent, waiting for ACK...')
deadline = time.time() + 10
while time.time() < deadline:
    msg = m.recv_match(type='COMMAND_ACK', blocking=True, timeout=2)
    if msg:
        print(f'ACK: cmd={msg.command} result={msg.result}')
        break
else:
    print('ACK timeout')
    hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
    if hb:
        armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        print(f'HEARTBEAT: armed={armed} mode={hb.custom_mode}')
    else:
        print('No heartbeat received!')
m.close()
