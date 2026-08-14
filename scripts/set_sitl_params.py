#!/usr/bin/env python3
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('tcp:127.0.0.1:5760')
m.wait_heartbeat()
print('Connected')

m.mav.param_set_send(m.target_system, m.target_component, b'ARMING_CHECK', 0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)
m.mav.param_set_send(m.target_system, m.target_component, b'DISARM_DELAY', 0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)
# RC_OVERRIDE_TIME=-1: nunca expira — los overrides del joystick siguen activos
# indefinidamente (0 desactivaría los overrides RC por completo).
m.mav.param_set_send(m.target_system, m.target_component, b'RC_OVERRIDE_TIME', -1, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
time.sleep(1)
print('Params set')
m.close()
