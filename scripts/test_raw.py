import socket
s = socket.socket()
s.settimeout(3)
try:
    s.connect(("127.0.0.1", 5760))
    print("RAW TCP OK")
    s.close()
except Exception as e:
    print(f"FAIL: {e}")
