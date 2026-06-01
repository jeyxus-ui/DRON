import asyncio, json, math, websockets, urllib.request

# Get current position from telemetry
with urllib.request.urlopen('http://localhost:8000/api/telemetry') as resp:
    telem = json.loads(resp.read())
lat0 = telem['latitude']  # current lat
lon0 = telem['longitude']  # current lon
alt = 30  # 30m relative to home
radius_m = 100

waypoints = []
for i in range(8):
    angle = i * 2 * math.pi / 8
    dlat = radius_m * math.cos(angle) / 111111
    dlon = radius_m * math.sin(angle) / (111111 * math.cos(math.radians(lat0)))
    waypoints.append({
        'latitude': round(lat0 + dlat, 7),
        'longitude': round(lon0 + dlon, 7),
        'altitude': alt
    })

print('=== CIRCULAR MISSION ===')
for i, wp in enumerate(waypoints):
    print(f'  WP{i}: ({wp["latitude"]}, {wp["longitude"]}) @ {wp["altitude"]}m')

async def get_ack(ws, expected_command):
    while True:
        resp = json.loads(await ws.recv())
        if resp.get('type') == 'command_ack' and resp.get('command') == expected_command:
            return resp
        # skip telemetry messages

async def send():
    async with websockets.connect('ws://localhost:8000/ws/telemetry') as ws:
        # Clear existing mission first
        await ws.send(json.dumps({'type': 'CLEAR_MISSION'}))
        resp = await get_ack(ws, 'CLEAR_MISSION')
        print(f'Clear response: {json.dumps(resp, indent=2)}')

        # Send mission upload
        msg = json.dumps({
            'type': 'MISSION_UPLOAD',
            'params': {'waypoints': waypoints}
        })
        await ws.send(msg)
        resp = await get_ack(ws, 'MISSION_UPLOAD')
        print(f'Upload response: {json.dumps(resp, indent=2)}')
        success = resp.get('result', {}).get('success', False)

        if success:
            # Start mission
            await ws.send(json.dumps({'type': 'START_MISSION'}))
            resp2 = await get_ack(ws, 'START_MISSION')
            print(f'Start response: {json.dumps(resp2, indent=2)}')

asyncio.run(send())
