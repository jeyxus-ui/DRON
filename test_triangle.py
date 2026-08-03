#!/usr/bin/env python3
"""Mission: triangular route returning to origin. Arm → Takeoff → Triangle → RTL → Disarm"""
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

    async def cmd(self, cmd_type, params=None, wait_ack=True, timeout=30):
        msg = {"type": cmd_type, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        logger.info(f"  → {cmd_type} {params or ''}")
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
                        logger.info(f"  ✓ {cmd_type} OK")
                        return True
                    logger.error(f"  ✗ {cmd_type}: {result.get('message')}")
                    return False
            except asyncio.TimeoutError:
                continue
        logger.error(f"  ✗ {cmd_type} timeout")
        return False

    async def wait(self, seconds, check_disarm=True):
        logger.info(f"  ⏳ {seconds}s...")
        await asyncio.sleep(1.5)
        deadline = time.time() + seconds
        while time.time() < deadline:
            if check_disarm:
                try:
                    resp = await asyncio.wait_for(self.ws.recv(), timeout=0.5)
                    data = json.loads(resp)
                    if data.get("type") == "telemetry":
                        armed = data.get("data", {}).get("armed")
                        if armed is False and self._last_armed is True:
                            logger.warning("⚠ drone disarmed!")
                            return False
                        elif armed is True:
                            self._last_armed = True
                except asyncio.TimeoutError:
                    continue
            else:
                await asyncio.sleep(0.5)
        return True

    async def goto_relative(self, forward=0, right=0, up=0):
        return await self.cmd("GOTO_RELATIVE", {"forward": forward, "right": right, "up": up})

    async def run(self):
        try:
            await self.connect()
            start = time.time()

            # 1. Set STABILIZE + ARM
            logger.info("STEP 1: SET STABILIZE + ARM")
            await self.cmd("SET_MODE", {"mode": "STABILIZE"})
            await asyncio.sleep(1)

            if not await self.cmd("ARM"):
                logger.error("ARM failed, aborting")
                return
            await asyncio.sleep(2)

            # 2. GUIDED + TAKEOFF
            logger.info("STEP 2: TAKEOFF to 5m")
            await self.cmd("SET_MODE", {"mode": "GUIDED"})
            await asyncio.sleep(1)

            if not await self.cmd("TAKEOFF", {"altitude": 5}):
                logger.warning("TAKEOFF wait_ack timeout, continuing anyway")
            await self.wait(10)  # wait to reach altitude

            # 3. TRIANGLE (returns to origin)
            logger.info("STEP 3: TRIANGLE ROUTE")
            legs = [
                (5, 0),    # forward 5m
                (-5, 5),   # right 5m + back 5m
                (0, -5),   # left 5m → back to origin
            ]
            for i, (fwd, right) in enumerate(legs, 1):
                logger.info(f"  Leg {i}/3: forward={fwd}m, right={right}m")
                if not await self.goto_relative(forward=fwd, right=right):
                    logger.error(f"Leg {i} failed")
                    return
                await self.wait(8)

            # 4. RTL (land and return)
            logger.info("STEP 4: RTL")
            await self.cmd("RTL")
            await self.wait(15)

            # 5. DISARM (force via emergency KILL if needed)
            logger.info("STEP 5: DISARM")
            if not await self.cmd("DISARM", timeout=15):
                logger.warning("DISARM via CMD failed, trying EMERGENCY KILL")
                await self.cmd("EMERGENCY", {"action": "KILL"}, wait_ack=False)
                await asyncio.sleep(2)

            elapsed = time.time() - start
            logger.info(f"=== MISSION COMPLETE in {elapsed:.0f}s ===")

        except Exception as e:
            logger.error(f"Mission error: {e}")
            raise
        finally:
            await self.close()

if __name__ == "__main__":
    asyncio.run(Mission().run())
