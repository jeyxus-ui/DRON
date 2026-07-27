from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('tcp:172.28.252.91:5760', source_system=255)
time.sleep(1)

sock = getattr(m, 'socket', None)
print(f"socket attr: {sock}")
print(f"sock type: {type(sock)}")

attrs = [x for x in dir(m) if "sock" in x.lower()]
print(f"socket attrs: {attrs}")

m.close()
