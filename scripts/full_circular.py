"""
Circular mission via direct TCP to MAVProxy.
Uses correct params for ArduCopter 4.8.0-dev.
"""
from pymavlink import mavutil
import math, time

WSL_IP = '172.28.252.91'
MAV_TCP_PORT = 14650

master = mavutil.mavlink_connection(f'tcp:{WSL_IP}:{MAV_TCP_PORT}', source_system=255)
master.wait_heartbeat(timeout=10)
print(f'Connected! Sys={master.target_system}')

modes = master.mode_mapping()
print(f'Modes available: {list(modes.keys())}')

# Wait for EKF init
print('\nWaiting for EKF init (10s)...')
time.sleep(10)

# Step 1: Verify ARMING_SKIPCHK
print('1. ARMING_SKIPCHK:', end=' ')
master.mav.param_request_read_send(master.target_system, master.target_component,
    b'ARMING_SKIPCHK', -1)
msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
print(msg.param_value if msg else '?')

# Step 2: Clear mission
print('2. Clearing mission...')
master.mav.mission_clear_all_send(master.target_system, master.target_component)
time.sleep(1)

# Step 3: Upload circular mission
print('3. Uploading circular mission...')
lat0, lon0 = -35.363262, 149.165237
alt, radius = 30.0, 100

wps = []
wps.append({'lat': int(lat0*1e7), 'lon': int(lon0*1e7), 'alt': alt,
            'cmd': mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})
for i in range(8):
    angle = i * 2 * math.pi / 8
    dlat = radius * math.cos(angle) / 111111
    dlon = radius * math.sin(angle) / (111111 * math.cos(math.radians(lat0)))
    wps.append({'lat': int((lat0+dlat)*1e7), 'lon': int((lon0+dlon)*1e7),
                'alt': alt, 'cmd': mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})

master.mav.mission_count_send(master.target_system, master.target_component, len(wps))
seq = 0
start = time.time()
while seq < len(wps):
    msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST'],
                            blocking=True, timeout=5)
    if not msg:
        if time.time() - start > 15:
            print('   Timeout!')
            break
        continue
    print(f'   WP{msg.seq}...')
    wp = wps[msg.seq]
    master.mav.mission_item_int_send(
        master.target_system, master.target_component, msg.seq,
        wp['frame'], wp['cmd'], 0, 1, 0, 0, 0, 0,
        wp['lat'], wp['lon'], wp['alt'])
    seq = msg.seq + 1

ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
print(f'   Mission: {"OK" if ack and ack.type == 0 else "FAIL"}')

# Step 4: Set GUIDED (may not work without GPS fix, try anyway)
print('4. Setting GUIDED...')
master.mav.set_mode_send(master.target_system, modes['GUIDED'], 0, 0)
time.sleep(2)
msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
mode_str = mavutil.mode_string_v10(msg) if msg else '?'
print(f'   Mode: {mode_str}')

# Step 5: ARM with force
print('5. Arming (force)...')
master.mav.command_long_send(master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
time.sleep(3)

msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
if msg:
    armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    mode_str = mavutil.mode_string_v10(msg)
    print(f'   Mode={mode_str}, Armed={armed}')
else:
    print('   No heartbeat')
    armed = False

# Step 6: Start mission (AUTO) if armed
if armed:
    print('6. Starting mission (AUTO)...')
    master.mav.set_mode_send(master.target_system, modes['AUTO'], 0, 0)
    time.sleep(3)
    msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
    if msg:
        mode_str = mavutil.mode_string_v10(msg)
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        print(f'   Mode={mode_str}, Armed={armed}')
else:
    print('6. Cannot start mission: not armed')

print('\nDone!')
