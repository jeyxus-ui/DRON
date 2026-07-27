#!/usr/bin/env python3
"""Quick debug: ver si _read_loop recibe COMMAND_ACK"""
import subprocess, time, os, sys, signal, urllib.request, json, threading

SITL = '/home/usuario/ardupilot/build/sitl/bin/arducopter'
HOME = '-35.363262,149.165237,584,270'

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
     '--host', '0.0.0.0', '--port', '8000', '--log-level', 'debug'],
    cwd=os.path.join(os.path.dirname(__file__), '..'),
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)

start = time.time()
armed_sent = False
for line in bp.stdout:
    l = line.strip()
    t = time.time() - start
    if t > 40:
        break
    if t > 10 and not armed_sent:
        # Send ARM via API
        import urllib.request
        try:
            req = urllib.request.Request(
                'http://127.0.0.1:8000/api/arm',
                data=json.dumps({"force": True}).encode(),
                method='POST'
            )
            req.add_header('Content-Type', 'application/json')
            resp = urllib.request.urlopen(req, timeout=10)
            print(f'[{t:.1f}s] ARM response: {resp.read().decode()}')
            armed_sent = True
        except Exception as e:
            print(f'[{t:.1f}s] ARM error: {e}')
            armed_sent = True

    if 'COMMAND_ACK' in l or 'stored' in l or 'wait_ack' in l or 'timeout' in l or 'Error' in l or 'telemetry' in l.lower() or 'Thread' in l:
        print(f'[{t:.1f}s] {l[:200]}')

bp.terminate()
os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, 'killpg') else proc.kill()
