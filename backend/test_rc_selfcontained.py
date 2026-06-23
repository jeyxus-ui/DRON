"""
Prueba autónoma: arranca backend SIM como subproceso, conecta WebSocket,
envía RC_CONTROL a 10Hz por 30s, reporta estabilidad.
"""
import subprocess
import sys
import os
import time
import json
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('RC_TEST')

WS_URL = 'ws://127.0.0.1:8000/ws/telemetry'

BACKEND_SCRIPT = os.path.join(os.path.dirname(__file__), 'start_api_sim.py')

async def test_ws(duration=30):
    import websockets

    for attempt in range(15):
        try:
            async with websockets.connect(WS_URL, timeout=5) as ws:
                logger.info("✅ Conectado al backend")
                start = time.time()
                last_telemetry = time.time()
                rc_count = 0

                async def heartbeat():
                    nonlocal rc_count
                    while True:
                        try:
                            await ws.send(json.dumps({
                                "type": "RC_CONTROL",
                                "params": {"throttle": 0.0, "yaw": 0.0, "pitch": 0.0, "roll": 0.0}
                            }))
                            rc_count += 1
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            logger.error(f"❌ heartbeat error: {e}")
                            break

                async def listener():
                    nonlocal last_telemetry
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=5)
                            data = json.loads(msg)
                            if data.get("type") == "telemetry":
                                last_telemetry = time.time()
                        except asyncio.TimeoutError:
                            logger.warning("⚠️ 5s sin datos")
                        except Exception as e:
                            logger.error(f"❌ listener error: {e}")
                            break

                hb = asyncio.create_task(heartbeat())
                ls = asyncio.create_task(listener())

                try:
                    while time.time() - start < duration:
                        await asyncio.sleep(1)
                        elapsed = time.time() - start
                        since_tel = time.time() - last_telemetry

                        if since_tel > 10:
                            logger.error(f"❌ FALLÓ: {since_tel:.0f}s sin telemetría")
                            return False

                        if int(elapsed) % 10 == 0:
                            logger.info(f"  {elapsed:.0f}s — RC: {rc_count} — tel: hace {since_tel:.1f}s")

                    total = time.time() - start
                    logger.info(f"\n✅ PRUEBA SUPERADA: {total:.0f}s — {rc_count} RC_CONTROL")
                    return True
                finally:
                    hb.cancel()
                    ls.cancel()
        except Exception as e:
            logger.info(f"  Intento {attempt+1}: {e}")
            await asyncio.sleep(1)

    logger.error("❌ No se pudo conectar")
    return False

def main():
    logger.info("=" * 60)
    logger.info("PRUEBA DE ESTABILIDAD RC — Heartbeat 10Hz")
    logger.info("=" * 60)

    # Kill any existing python on port 8000
    proc = subprocess.Popen(
        [sys.executable, BACKEND_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(5)
        logger.info(f"Backend PID: {proc.pid}")

        result = asyncio.run(test_ws(30))
        logger.info(f"\nResultado: {'✅ ESTABLE' if result else '❌ INESTABLE'}")
        return result
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()
        logger.info("Backend detenido")

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
