"""
Prueba integrada: arranca el backend SIM, conecta WebSocket,
envía RC_CONTROL a 10Hz por 30s, verifica estabilidad.
"""
import sys
import os
import subprocess
import time
import json
import logging
import asyncio
import signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('RC_TEST')

WS_URL = 'ws://127.0.0.1:8000/ws/telemetry'

async def run_test(duration=30):
    import websockets

    logger.info(f"Conectando a {WS_URL} ...")
    for attempt in range(10):
        try:
            async with websockets.connect(WS_URL) as ws:
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
                            logger.error(f"❌ Error enviando RC_CONTROL: {e}")
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
                            logger.warning("⚠️ Timeout (5s sin datos)")
                        except Exception as e:
                            logger.error(f"❌ Error listener: {e}")
                            break

                hb_task = asyncio.create_task(heartbeat())
                ls_task = asyncio.create_task(listener())

                try:
                    while time.time() - start < duration:
                        await asyncio.sleep(1)
                        elapsed = time.time() - start
                        since_tel = time.time() - last_telemetry

                        if since_tel > 10:
                            logger.error(f"❌ FALLÓ: {since_tel:.0f}s sin telemetría")
                            return False

                        if int(elapsed) % 10 == 0 and elapsed > 0:
                            logger.info(f"⏱ {elapsed:.0f}s — RC: {rc_count} — tel: hace {since_tel:.1f}s")

                    total = time.time() - start
                    logger.info(f"\n✅ PRUEBA SUPERADA: {total:.0f}s — {rc_count} RC_CONTROL sin perder conexión")
                    return True

                finally:
                    hb_task.cancel()
                    ls_task.cancel()

        except (OSError, websockets.exceptions.WebSocketException) as e:
            logger.info(f"  Intento {attempt+1}: {e}")
            await asyncio.sleep(1)

    logger.error("❌ No se pudo conectar tras 10 intentos")
    return False

async def main():
    logger.info("=" * 60)
    logger.info("PRUEBA DE ESTABILIDAD RC — Heartbeat 10Hz")
    logger.info("=" * 60)
    logger.info(f"Duración: 30 segundos")
    logger.info("")

    result = await run_test(30)
    logger.info(f"\nResultado: {'✅ ESTABLE' if result else '❌ INESTABLE'}")
    return result

if __name__ == '__main__':
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
