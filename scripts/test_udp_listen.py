import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(8)
s.bind(('0.0.0.0', 14550))
print(f'Listening on UDP 14550...')
sys.stdout.flush()
try:
    data, addr = s.recvfrom(4096)
    print(f'Got {len(data)} bytes from {addr[0]}:{addr[1]}')
    print(f'First bytes: {data[:20].hex()}')
    sys.stdout.flush()
except socket.timeout:
    print('No data received in 8s')
    sys.stdout.flush()
s.close()
