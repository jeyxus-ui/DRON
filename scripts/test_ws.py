import asyncio, websockets, json
async def test():
    async with websockets.connect("ws://192.168.20.38:8000/ws/telemetry") as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print("WS OK:", json.loads(msg))
asyncio.run(test())
