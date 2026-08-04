"""End-to-end: backend real + SITL. Envía ARM y RC_CONTROL vía WebSocket y
verifica que la actitud (roll/pitch) responda — el mismo camino que usa la app móvil.

Uso: python scripts/ws_flow_test.py [ws://127.0.0.1:8000/ws/telemetry]
"""
import asyncio
import json
import sys
import time
import urllib.request

import websockets

WS_URL = sys.argv[1] if len(sys.argv) > 1 else 'ws://127.0.0.1:8000/ws/telemetry'
HEALTH_URL = WS_URL.replace('ws://', 'http://').replace('/ws/telemetry', '/health')

telemetry = {}
acks = asyncio.Queue()


def wait_backend(timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


async def reader(ws):
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        t = msg.get('type')
        if t == 'telemetry':
            telemetry.update(msg.get('data', {}))
        elif t == 'command_ack':
            await acks.put(msg)


async def send(ws, cmd_type, params=None):
    await ws.send(json.dumps({'type': cmd_type, 'params': params or {}}))


async def wait_ack(cmd, timeout: float = 12.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ack = await asyncio.wait_for(acks.get(), timeout=1)
        except asyncio.TimeoutError:
            continue
        if ack.get('command') == cmd:
            return ack
    return None


async def hold_rc(ws, throttle, yaw, pitch, roll, duration):
    end = time.time() + duration
    while time.time() < end:
        await send(ws, 'RC_CONTROL', {'throttle': throttle, 'yaw': yaw, 'pitch': pitch, 'roll': roll})
        await asyncio.sleep(0.2)


def show(label):
    tel = telemetry
    print(f'{label}: armed={tel.get("armed")} mode={tel.get("mode")} '
          f'alt={tel.get("altitude")}m roll={tel.get("roll")}° pitch={tel.get("pitch")}° '
          f'yaw={tel.get("yaw")}°')


async def wait_armed(timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if telemetry.get('armed'):
            return True
        await asyncio.sleep(0.3)
    return False


async def main():
    if not wait_backend():
        print('❌ Backend no respondió en /health')
        sys.exit(1)
    print('✅ Backend listo (/health OK)')

    async with websockets.connect(WS_URL, open_timeout=15) as ws:
        rtask = asyncio.create_task(reader(ws))
        await asyncio.sleep(2.0)
        show('Estado inicial')
        if telemetry.get('armed'):
            print('⚠️ Ya estaba armado')

        ack = await send(ws, 'ARM', {'force': True}) or None
        ack = await wait_ack('ARM')
        print(f'ARM ack: {ack.get("result") if ack else "timeout"}')
        armed = await wait_armed()
        print(f'Armed: {armed}')
        if not armed:
            print('❌ No se armó — abortando')
            rtask.cancel()
            return

        # ── Despegue ──
        await hold_rc(ws, 0.60, 0.0, 0.0, 0.0, 6.0)
        show('Tras throttle 0.60 (despegue)')

        # ── PITCH (maxSpeed del app = 0.3) ──
        await hold_rc(ws, 0.60, 0.0, 0.3, 0.0, 3.0)
        show('Tras pitch=0.3')
        await hold_rc(ws, 0.60, 0.0, 0.0, 0.0, 2.0)
        show('Tras pitch=0.0')

        # ── ROLL ──
        await hold_rc(ws, 0.60, 0.0, 0.0, 0.3, 3.0)
        show('Tras roll=0.3')
        await hold_rc(ws, 0.60, 0.0, 0.0, 0.0, 2.0)
        show('Tras roll=0.0')

        # ── ROLL+PITCH ──
        await hold_rc(ws, 0.60, 0.0, 0.3, 0.3, 3.0)
        show('Tras roll+pitch=0.3')

        # ── YAW (joystick izquierdo) ──
        await hold_rc(ws, 0.60, 0.3, 0.0, 0.0, 3.0)
        show('Tras yaw=0.3')

        # ── Descenso y desarme ──
        await hold_rc(ws, 0.20, 0.0, 0.0, 0.0, 3.0)
        show('Tras throttle 0.20 (descenso)')
        await send(ws, 'DISARM', {})
        ack = await wait_ack('DISARM')
        print(f'DISARM ack: {ack.get("result") if ack else "timeout"}')
        await asyncio.sleep(1.0)
        show('Estado final')

        rtask.cancel()


if __name__ == '__main__':
    asyncio.run(main())
