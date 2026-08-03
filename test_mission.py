#!/usr/bin/env python3
"""Test mission via WebSocket: forward 3m, right 3m, right 3m, land/disarm"""
import asyncio
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

WS_URL = "ws://localhost:8000/ws/telemetry"

class Mission:
    def __init__(self):
        self.ws = None
        self._last_armed = None

    async def connect(self):
        import websockets
        self.ws = await websockets.connect(WS_URL)
        logger.info("Connected to WebSocket")

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def cmd(self, cmd_type, params=None, wait_ack=True, timeout=15):
        msg = {"type": cmd_type, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        logger.info(f"→ {cmd_type} {params or ''}")
        if not wait_ack:
            return True
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = await asyncio.wait_for(self.ws.recv(), timeout=1)
                data = json.loads(resp)
                if data.get("type") == "command_ack" and data.get("command") == cmd_type:
                    result = data.get("result", {})
                    if result.get("success"):
                        logger.info(f"✓ {cmd_type} OK")
                        return True
                    logger.error(f"✗ {cmd_type}: {result.get('message')}")
                    return False
            except asyncio.TimeoutError:
                continue
        logger.error(f"✗ {cmd_type} timeout")
        return False

    async def wait(self, seconds):
        logger.info(f"⏳ waiting {seconds}s...")
        await asyncio.sleep(1.5)
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                resp = await asyncio.wait_for(self.ws.recv(), timeout=0.5)
                data = json.loads(resp)
                if data.get("type") == "telemetry":
                    armed = data.get("data", {}).get("armed")
                    if armed is False and self._last_armed is True:
                        logger.warning(f"⚠ drone disarmed!")
                        return False
                    elif armed is True:
                        self._last_armed = True
            except asyncio.TimeoutError:
                continue
        return True

    async def arm(self):
        return await self.cmd("ARM")

    async def disarm(self):
        return await self.cmd("DISARM")

    async def land(self):
        return await self.cmd("LAND")

    async def goto_relative(self, forward=0, right=0, up=0):
        return await self.cmd("GOTO_RELATIVE", {"forward": forward, "right": right, "up": up})

    async def run(self):
        try:
            await self.connect()

            # 1. ARM
            logger.info("=== STEP 1: ARM ===")
            if not await self.arm():
                logger.error("ARM failed, aborting")
                return

            start = time.time()
            await self.wait(5)

            # 2. Forward 3m
            logger.info("=== STEP 2: GOTO forward 3m ===")
            if not await self.goto_relative(forward=3):
                logger.error("GOTO forward failed")
                return

            await self.wait(10)

            # 3. Right 3m
            logger.info("=== STEP 3: GOTO right 3m ===")
            if not await self.goto_relative(right=3):
                logger.error("GOTO right (1) failed")
                return

            await self.wait(10)

            # 4. Right 3m again
            logger.info("=== STEP 4: GOTO right 3m ===")
            if not await self.goto_relative(right=3):
                logger.error("GOTO right (2) failed")
                return

            await self.wait(10)

            # 5. LAND
            logger.info("=== STEP 5: LAND ===")
            await self.land()
            await self.wait(8)

            # 6. DISARM
            logger.info("=== STEP 6: DISARM ===")
            await self.disarm()

            elapsed = time.time() - start
            logger.info(f"=== MISSION COMPLETE in {elapsed:.0f}s ===")

        except Exception as e:
            logger.error(f"Mission error: {e}")
            raise
        finally:
            await self.close()

if __name__ == "__main__":
    asyncio.run(Mission().run())
