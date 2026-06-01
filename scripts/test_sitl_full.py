#!/usr/bin/env python3
"""
Full sequence test: GUIDED mode, ARM, upload circular mission, start mission.
Diagnoses the immediate-disarm issue from full_circular.py.
"""
import subprocess, time, os, signal, math
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
time.sleep(8)

master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=10)
print(f'Connected! sys={master.target_system}')
modes = master.mode_mapping()

print('ARMING_SKIPCHK =', end=' ')
master.mav.param_request_read_send(master.target_system, master.target_component, b'ARMING_SKIPCHK', -1)
msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
print(msg.param_value if msg else 'no response')

print('DISARM_DELAY =', end=' ')
master.mav.param_request_read_send(master.target_system, master.target_component, b'DISARM_DELAY', -1)
msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
print(msg.param_value if msg else 'no response')

# Upload circular mission
print('\nUploading circular mission...')
lat0, lon0 = -35.363262, 149.165237
alt, radius = 30.0, 100

wps = []
wps.append({'lat': int(lat0 * 1e7), 'lon': int(lon0 * 1e7), 'alt': alt,
            'cmd': mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})
for i in range(8):
    angle = i * 2 * math.pi / 8
    dlat = radius * math.cos(angle) / 111111
    dlon = radius * math.sin(angle) / (111111 * math.cos(math.radians(lat0)))
    wps.append({'lat': int((lat0 + dlat) * 1e7), 'lon': int((lon0 + dlon) * 1e7), 'alt': alt,
                'cmd': mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})

master.mav.mission_count_send(master.target_system, master.target_component, len(wps))
start = time.time()
seq = 0
while seq < len(wps):
    msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST'], blocking=True, timeout=5)
    if not msg:
        if time.time() - start > 15:
            print('  Timeout!')
            break
        continue
    print(f'  WP{msg.seq} ({wps[msg.seq]["cmd"]})...')
    wp = wps[msg.seq]
    master.mav.mission_item_int_send(master.target_system, master.target_component, msg.seq,
        wp['frame'], wp['cmd'], 0, 1, 0, 0, 0, 0, wp['lat'], wp['lon'], wp['alt'])
    seq = msg.seq + 1

ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
print(f'  Mission: {"OK" if ack and ack.type == 0 else "FAIL (type="+str(ack.type if ack else None)+")"}')

# Set GUIDED
print('\nSetting GUIDED...')
master.mav.set_mode_send(master.target_system, modes['GUIDED'], 0, 0)
time.sleep(2)

msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
ms = mavutil.mode_string_v10(msg) if msg else '?'
print(f'  Mode: {ms}')

# ARM
print('ARMING (force, param2=21196)...')
master.mav.command_long_send(master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)

# Monitor for 5s
print('\nMonitoring for 10s...')
start = time.time()
while time.time() - start < 10:
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

# If armed, start mission
msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
if msg and (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
    print('\nStarting mission (AUTO)...')
    master.mav.set_mode_send(master.target_system, modes['AUTO'], 0, 0)
    time.sleep(3)
    msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
    if msg:
        ms = mavutil.mode_string_v10(msg)
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        print(f'  Mode: {ms}, Armed: {armed}')
else:
    print('\nNot armed, skipping mission start')

master.close()
print('\nKilling SITL...')
os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
proc.wait(timeout=5)
print('Done')
