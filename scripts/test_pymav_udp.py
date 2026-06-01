from pymavlink import mavutil
import time, sys

master = mavutil.mavlink_connection('udpin:0.0.0.0:14550', source_system=255)
print('Created connection, waiting for heartbeat...')
sys.stdout.flush()

start = time.time()
hb = master.wait_heartbeat(timeout=5)
elapsed = time.time() - start

if hb:
    print(f'Heartbeat OK after {elapsed:.1f}s: sys={master.target_system}')
else:
    print(f'No heartbeat after {elapsed:.1f}s')
sys.stdout.flush()

msg = master.recv_match(blocking=True, timeout=3)
if msg:
    print(f'Got message: {msg.get_type()}')
else:
    print('No message in 3s')
sys.stdout.flush()

print('Done')
