#!/usr/bin/env python3
"""Single script: starts SITL, connects, runs full mission test."""
import subprocess, time, os, signal, math, sys
from pymavlink import mavutil

sys.stdout = open(sys.stdout.fileno(), 'w', buffering=1)  # line buffered

print('=== Starting SITL ===')
proc = subprocess.Popen(
    ['/home/usuario/ardupilot/build/sitl/bin/arducopter', '--model', 'quad',
     '--speedup', '1', '--home', '-35.363262,149.165237,584,270', '-I0'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid)
time.sleep(10)

print('=== Connecting ===')
master = mavutil.mavlink_connection('tcp:127.0.0.1:5760', source_system=255)
master.wait_heartbeat(timeout=10)
print(f'Connected! sys={master.target_system}')

modes = master.mode_mapping()
print(f'Modes: {list(modes.keys())}')

# Check params
for p in ['ARMING_SKIPCHK', 'DISARM_DELAY', 'ARMING_CHECK']:
    master.mav.param_request_read_send(master.target_system, master.target_component, p.encode(), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
    if msg:
        print(f'{p} = {msg.param_value}')

# Wait for GPS
print('Waiting for GPS...')
start = time.time()
while time.time() - start < 15:
    msg = master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=0.5)
    if msg:
        print(f'GPS: fix={msg.fix_type} sats={msg.satellites_visible}')
        if msg.fix_type >= 3:
            break

# Set GUIDED
print('Setting GUIDED...')
master.mav.set_mode_send(master.target_system, modes['GUIDED'], 0, 0)
time.sleep(2)
msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
ms = mavutil.mode_string_v10(msg) if msg else '?'
print(f'Mode after set: {ms}')

if ms == 'GUIDED':
    # Upload mission
    print('Uploading mission...')
    lat0, lon0 = -35.363262, 149.165237
    wps = []
    wps.append({'lat': int(lat0*1e7), 'lon': int(lon0*1e7), 'alt': 30,
                'cmd': mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})
    for i in range(4):
        angle = i * 2 * math.pi / 4
        dlat = 50 * math.cos(angle) / 111111
        dlon = 50 * math.sin(angle) / (111111 * math.cos(math.radians(lat0)))
        wps.append({'lat': int((lat0+dlat)*1e7), 'lon': int((lon0+dlon)*1e7), 'alt': 30,
                    'cmd': mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})

    master.mav.mission_count_send(master.target_system, master.target_component, len(wps))
    start_t = time.time()
    seq = 0
    while seq < len(wps):
        msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST'], blocking=True, timeout=5)
        if not msg:
            if time.time() - start_t > 20:
                print('Mission upload timeout!')
                break
            continue
        print(f'  WP{msg.seq}...')
        wp = wps[msg.seq]
        master.mav.mission_item_int_send(master.target_system, master.target_component, msg.seq,
            wp['frame'], wp['cmd'], 0, 1, 0, 0, 0, 0, wp['lat'], wp['lon'], wp['alt'])
        seq = msg.seq + 1

    ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
    print(f'Mission: {"OK" if ack and ack.type == 0 else "FAIL"}')

    # ARM
    print('ARMING...')
    master.mav.command_long_send(master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
    time.sleep(2)

    msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
    armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) if msg else False
    print(f'Armed: {armed}')

    if armed:
        print('Starting AUTO...')
        master.mav.set_mode_send(master.target_system, modes['AUTO'], 0, 0)
        time.sleep(3)
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
        if msg:
            print(f'Mode: {mavutil.mode_string_v10(msg)}, Armed: {bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)}')
else:
    print('Cannot proceed: not in GUIDED')

master.close()
print('Killing SITL...')
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
proc.wait(timeout=5)
print('Done')
