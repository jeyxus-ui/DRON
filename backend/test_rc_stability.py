"""
Prueba de estabilidad: simula el heartbeat de RC_CONTROL del frontend.
Conecta al backend por WebSocket, envía RC_CONTROL a 10Hz por 60s,
y reporta si la conexión se mantiene o se pierde.
"""
import asyncio
import json
import logging
import time
import signal
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('RC_TEST')

WS_URL = 'ws://127.0.0.1:8000/ws/telemetry'

async def test_rc_stability(duration=60):
    import websockets

    logger.info(f"Conectando a {WS_URL} ...")
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
                        logger.warning("⚠️ Timeout esperando mensaje (5s sin datos)")
                    except Exception as e:
                        logger.error(f"❌ Error en listener: {e}")
                        break

            hb_task = asyncio.create_task(heartbeat())
            ls_task = asyncio.create_task(listener())

            try:
                while time.time() - start < duration:
                    await asyncio.sleep(1)
                    elapsed = time.time() - start
                    since_tel = time.time() - last_telemetry

                    if since_tel > 10:
                        logger.error(f"❌ FALLÓ: {since_tel:.0f}s sin telemetría (el backend dejó de enviar)")
                        break

                    if elapsed % 10 == 0:
                        logger.info(f"⏱ {elapsed:.0f}s — RC enviados: {rc_count} — última telemetría hace {since_tel:.1f}s")

            except asyncio.CancelledError:
                pass
            finally:
                hb_task.cancel()
                ls_task.cancel()
                total_time = time.time() - start
                success = total_time >= duration - 1

                if success:
                    logger.info(f"\n✅ PRUEBA SUPERADA: {total_time:.0f}s — {rc_count} RC_CONTROL enviados sin perder conexión")
                else:
                    logger.error(f"\n❌ PRUEBA FALLÓ: solo duró {total_time:.0f}s — se perdió la conexión")

                return success

    except Exception as e:
        logger.error(f"❌ No se pudo conectar al backend: {e}")
        return False

async def main():
    logger.info("=" * 60)
    logger.info("PRUEBA DE ESTABILIDAD RC — Heartbeat 10Hz")
    logger.info("=" * 60)
    logger.info(f"Duración: 60 segundos")
    logger.info(f"URL: {WS_URL}")
    logger.info("")

    result = await test_rc_stability(60)

    logger.info("")
    logger.info(f"Resultado: {'✅ ESTABLE' if result else '❌ INESTABLE'}")
    return result

if __name__ == '__main__':
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
