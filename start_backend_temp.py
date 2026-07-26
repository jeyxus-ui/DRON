import os
os.environ['MAVLINK_DEVICE'] = 'udpin:0.0.0.0:14551'
os.environ['MAVLINK_BAUD'] = '115200'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

import uvicorn
uvicorn.run(
    "backend.main:app",
    host="0.0.0.0",
    port=8000,
    ws_ping_interval=15,
    ws_ping_timeout=10,
)
