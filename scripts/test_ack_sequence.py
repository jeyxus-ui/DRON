#!/usr/bin/env python3
"""
Diagnostic test: Send ARM via API and observe ALL COMMAND_ACKs and HEARTBEAT armed state.
Does NOT open a second pymavlink connection — everything goes through the backend API.
"""
import subprocess, time, os, sys, signal, urllib.request, json, threading

SITL = '/home/usuario/ardupilot/build/sitl/bin/arducopter'
HOME = '-35.363262,149.165237,584,270'
PORT = 8000

proc = subprocess.Popen(
    [SITL, '--model', 'quad', '--speedup', '1', '--home', HOME, '-I0',
     '--synthetic-clock', '--defaults', '/home/usuario/ardupilot/Tools/autotest/default_params/copter.parm'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid
)
time.sleep(8)

env = os.environ.copy()
env['MAVLINK_DEVICE'] = 'tcp:127.0.0.1:5760'
env['LOG_LEVEL'] = 'DEBUG'
bp = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'backend.main:app',
     '--host', '0.0.0.0', '--port', str(PORT), '--log-level', 'debug'],
    cwd=os.path.join(os.path.dirname(__file__), '..'),
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)

start = time.time()
armed_sent = False
arm_result = None
log_lines = []

def read_backend():
    global armed_sent, arm_result
    for line in bp.stdout:
        l = line.strip()
        t = time.time() - start
        if t > 60:
            break
        if l:
            log_lines.append((t, l))

        if t > 12 and not armed_sent:
            try:
                req = urllib.request.Request(
                    f'http://127.0.0.1:{PORT}/api/arm',
                    data=json.dumps({"force": True}).encode(),
                    method='POST'
                )
                req.add_header('Content-Type', 'application/json')
                resp = urllib.request.urlopen(req, timeout=15)
                arm_result = json.loads(resp.read().decode())
                print(f'\n[{t:.1f}s] ARM API response: {json.dumps(arm_result)}')
                armed_sent = True
            except Exception as e:
                print(f'\n[{t:.1f}s] ARM API error: {e}')
                arm_result = {"error": str(e)}
                armed_sent = True

t_log = threading.Thread(target=read_backend, daemon=True)
t_log.start()

# Poll status every 1s after ARM
time.sleep(18)
print('\n--- Polling armed state after ARM ---')
for i in range(15):
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{PORT}/api/status', method='GET')
        resp = urllib.request.urlopen(req, timeout=5)
        s = json.loads(resp.read().decode())
        t = time.time() - start
        print(f'[{t:.1f}s] status: armed={s.get("armed")} mode={s.get("mode")} connected={s.get("connected")}')
    except Exception as e:
        print(f'[{time.time()-start:.1f}s] status error: {e}')
    time.sleep(1)

# Print relevant log lines
print('\n--- Backend logs (COMMAND_ACK / wait_ack / timeout / ARM / IN_PROGRESS) ---')
for t, l in log_lines:
    low = l.lower()
    if any(kw in low for kw in ['command_ack', 'wait_ack', 'timeout', 'arm', 'in_progress', 'result=', 'stored', 'accepted']):
        print(f'[{t:.1f}s] {l[:250]}')

print(f'\n--- ARM result: {json.dumps(arm_result)} ---')

bp.terminate()
try:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
except:
    proc.kill()
print('Done.')
