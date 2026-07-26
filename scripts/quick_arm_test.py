import json, urllib.request, time

def api(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f'http://localhost:8000{path}', data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

print('GUIDED:', api('POST', '/api/mode', {'mode': 'GUIDED'}))
time.sleep(2)
try:
    print('ARM:', api('POST', '/api/arm', {'force': True}, timeout=60))
except Exception as e:
    print('ARM ERROR:', e)
time.sleep(3)
print('STATUS:', api('GET', '/api/status'))
