#!/usr/bin/env python3
"""Test GUIDED mode + mission upload after GPS lock."""
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
modes = master.mode_mapping()

# Wait for GPS 3D fix
print('Waiting for GPS 3D fix...', end=' ')
start = time.time()
while time.time() - start < 20:
    msg = master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=1)
    if msg and msg.fix_type >= 3:
        print(f'FIX {msg.fix_type}, sats={msg.satellites_visible} (t={time.time()-start:.0f}s)')
        break
    elif msg:
        pass  # keep waiting
else:
    print('No GPS fix after 20s')

# Set GUIDED
print('Setting GUIDED...')
master.mav.set_mode_send(master.target_system, modes['GUIDED'], 0, 0)
time.sleep(2)
msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
ms = mavutil.mode_string_v10(msg) if msg else '?'
print(f'  Mode: {ms}')

# Upload mission
if ms == 'GUIDED':
    print('Uploading mission...')
    lat0, lon0 = -35.363262, 149.165237
    alt, radius = 30.0, 100
    wps = []
    wps.append({'lat': int(lat0 * 1e7), 'lon': int(lon0 * 1e7), 'alt': alt,
                'cmd': mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})
    for i in range(8):
        angle = i * 2 * math.pi / 8
        dlat = radius * math.cos(angle) / 111111
        dlon = radius * math.sin(angle) / (111111 * math.cos(math.radians(lat0)))
        wps.append({'lat': int((lat0 + dlat) * 1e7), 'lon': int((lon0 + dlon) * 1e7), 'alt': alt,
                    'cmd': mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})
    master.mav.mission_count_send(master.target_system, master.target_component, len(wps))
    start_t = time.time()
    seq = 0
    while seq < len(wps):
        msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST'], blocking=True, timeout=5)
        if not msg:
            if time.time() - start_t > 15:
                print('  Timeout!')
                break
            continue
        print(f'  WP{msg.seq}...')
        wp = wps[msg.seq]
        master.mav.mission_item_int_send(master.target_system, master.target_component, msg.seq,
            wp['frame'], wp['cmd'], 0, 1, 0, 0, 0, 0, wp['lat'], wp['lon'], wp['alt'])
        seq = msg.seq + 1
    ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
    print(f'  Mission: {"OK" if ack and ack.type == 0 else "FAIL"}')

    # ARM + start mission
    print('ARMING...')
    master.mav.command_long_send(master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
    time.sleep(3)
    msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
    if msg and (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
        print('  Armed! Starting mission...')
        master.mav.set_mode_send(master.target_system, modes['AUTO'], 0, 0)
        time.sleep(3)
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
        if msg:
            print(f'  Mode: {mavutil.mode_string_v10(msg)}, Armed: {bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)}')
    else:
        print('  Not armed')
else:
    print('Cannot proceed: not in GUIDED')

master.close()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.terminate()
proc.wait(timeout=5)
print('Done')
