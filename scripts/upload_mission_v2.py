"""
Subir mision circular con TAKEOFF como primer WP.
"""
from pymavlink import mavutil
import math, time

WSL_IP = '172.28.252.91'

master = mavutil.mavlink_connection(f'tcp:{WSL_IP}:14650', source_system=255, wait_heartbeat=False)
master.wait_heartbeat(timeout=5)
print(f'Connected! Sys={master.target_system}')

lat0 = -35.363262
lon0 = 149.165237
alt = 30.0
radius = 100

# Build waypoints: TAKEOFF + 8 NAV_WAYPOINT in a circle
waypoints = []
# WP0: TAKEOFF to 30m
waypoints.append({'lat': int(lat0 * 1e7), 'lon': int(lon0 * 1e7), 'alt': alt,
                  'cmd': mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT})

# WP1-WP8: Circle
for i in range(8):
    angle = i * 2 * math.pi / 8
    dlat = radius * math.cos(angle) / 111111
    dlon = radius * math.sin(angle) / (111111 * math.cos(math.radians(lat0)))
    waypoints.append({
        'lat': int((lat0 + dlat) * 1e7),
        'lon': int((lon0 + dlon) * 1e7),
        'alt': alt,
        'cmd': mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
        'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    })

print(f'Circular mission ({len(waypoints)} WPs):')
for i, wp in enumerate(waypoints):
    name = 'TAKEOFF' if wp['cmd'] == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF else f'NAV_WP {i}'
    print(f'  WP{i}: ({wp["lat"]/1e7:.7f}, {wp["lon"]/1e7:.7f}) @ {wp["alt"]}m [{name}]')

# Clear
master.mav.mission_clear_all_send(master.target_system, master.target_component)
time.sleep(1)

# Upload
count = len(waypoints)
master.mav.mission_count_send(master.target_system, master.target_component, count)
start = time.time()
seq = 0
while seq < count:
    msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST'], blocking=True, timeout=5)
    if not msg:
        if time.time() - start > 15:
            print('Timeout!')
            break
        continue
    req = msg.seq
    wp = waypoints[req]
    print(f'  Sending WP{req}...')
    master.mav.mission_item_int_send(
        master.target_system, master.target_component, req,
        wp['frame'], wp['cmd'],
        0, 1, 0, 0, 0, 0,
        wp['lat'], wp['lon'], wp['alt']
    )
    seq = req + 1

ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
if ack:
    print(f'Mission accepted! type={ack.type}')
else:
    print('No MISSION_ACK')

print('Done!')
