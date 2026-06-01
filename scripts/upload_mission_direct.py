"""
Subir mision circular directamente via TCP a MAVProxy en WSL.
Evita el race condition del backend usando una conexion separada.
"""
from pymavlink import mavutil
import math, time

WSL_IP = '172.28.252.91'
MAVPROXY_TCP_PORT = 14650

master = mavutil.mavlink_connection(
    f'tcp:{WSL_IP}:{MAVPROXY_TCP_PORT}',
    source_system=255,
    wait_heartbeat=False
)

print(f'Connecting to tcp:{WSL_IP}:{MAVPROXY_TCP_PORT}...')
master.wait_heartbeat(timeout=5)
print(f'Connected! System: {master.target_system}, Component: {master.target_component}')

master.mav.param_set_send(
    master.target_system, master.target_component,
    b'ARMING_SKIPCHK', 1.0, mavutil.mavlink.MAV_PARAM_TYPE_REAL32
)
time.sleep(1)

lat0 = -35.363262
lon0 = 149.165237
alt = 30

radius = 100
waypoints = []
for i in range(8):
    angle = i * 2 * math.pi / 8
    dlat = radius * math.cos(angle) / 111111
    dlon = radius * math.sin(angle) / (111111 * math.cos(math.radians(lat0)))
    waypoints.append({
        'lat': int((lat0 + dlat) * 1e7),
        'lon': int((lon0 + dlon) * 1e7),
        'alt': float(alt)
    })

print('\nCircular mission (8 WPs):')
for i, wp in enumerate(waypoints):
    print(f'  WP{i}: ({wp["lat"]/1e7:.7f}, {wp["lon"]/1e7:.7f}) @ {alt}m')

master.mav.mission_clear_all_send(master.target_system, master.target_component)
time.sleep(1)

count = len(waypoints)
master.mav.mission_count_send(master.target_system, master.target_component, count)

start = time.time()
seq = 0
while seq < count:
    msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST'], blocking=True, timeout=5)
    if not msg:
        if time.time() - start > 15:
            print('Timeout waiting for mission request')
            break
        continue
    req_seq = msg.seq
    print(f'  Sending WP{req_seq}...')
    wp = waypoints[req_seq]
    master.mav.mission_item_int_send(
        master.target_system, master.target_component,
        req_seq,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
        0, 1, 0, 0, 0, 0,
        wp['lat'], wp['lon'], wp['alt']
    )
    seq = req_seq + 1

ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
if ack:
    print(f'Mission accepted! type={ack.type}')
else:
    print('No MISSION_ACK received')

print('Done!')
