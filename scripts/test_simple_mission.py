from pymavlink import mavutil
import time

master = mavutil.mavlink_connection('tcp:172.28.252.91:14650', source_system=255, wait_heartbeat=False)
master.wait_heartbeat(timeout=5)
print('Connected')

master.mav.mission_clear_all_send(master.target_system, master.target_component)
time.sleep(1)

lat0 = int(-35.363262 * 1e7)
lon0 = int(149.165237 * 1e7)
alt = 30.0

wps = [
    (mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, lat0, lon0, alt),
    (mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, int((-35.363262 + 0.001) * 1e7), int((149.165237 + 0.001) * 1e7), alt),
]

master.mav.mission_count_send(master.target_system, master.target_component, len(wps))
seq = 0
start = time.time()
while seq < len(wps):
    msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST'], blocking=True, timeout=5)
    if not msg:
        if time.time() - start > 15:
            break
        continue
    cmd, lat, lon, al = wps[msg.seq]
    print(f'Sending WP{msg.seq}...')
    master.mav.mission_item_int_send(
        master.target_system, master.target_component, msg.seq,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, cmd,
        0, 1, 0, 0, 0, 0, lat, lon, al
    )
    seq = msg.seq + 1

ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
print(f'Mission OK: {ack is not None}, type={ack.type if ack else "?"}')
