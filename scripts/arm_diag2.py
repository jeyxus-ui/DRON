"""
Diagnostic: test ARM via REST API and check telemetry to see if it actually arms.
"""
import urllib.request
import json
import time

def api(method, path, body=None, timeout=15):
    url = f"http://localhost:8000{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"error": e.code, "detail": body}

print("=== ARM DIAG 2 ===")
print()

# Check initial state
r = api("GET", "/api/telemetry")
print(f"Before ARM: armed={r.get('armed')}, mode={r.get('mode')}")
print()

# Send GUIDED
print("--- GUIDED ---")
r = api("POST", "/api/mode", {"mode": "GUIDED"})
print(f"  {r}")
time.sleep(1)

# Check state after GUIDED
r = api("GET", "/api/telemetry")
print(f"After GUIDED: armed={r.get('armed')}, mode={r.get('mode')}")
print()

# Send ARM
print("--- ARM (force=True) ---")
t0 = time.time()
r = api("POST", "/api/arm", {"force": True}, timeout=30)
elapsed = time.time() - t0
print(f"  Response ({elapsed:.1f}s): {r}")
print()

# Immediately check telemetry
for i in range(5):
    r = api("GET", "/api/telemetry")
    print(f"  Check {i+1}: armed={r.get('armed')}, mode={r.get('mode')}, alt={r.get('altitude')}")
    time.sleep(1)

print()
print("=== DONE ===")
