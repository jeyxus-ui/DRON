"""
Punto de entrada recomendado para el backend.
Configura uvicorn con WebSocket ping/pong para detectar conexiones muertas.

Uso: python -m backend.run
"""
import uvicorn
import os
import sys

HOST = os.getenv('API_HOST', '0.0.0.0')
PORT = int(os.getenv('API_PORT', '8000'))
WS_PING_INTERVAL = int(os.getenv('WS_PING_INTERVAL', '30'))
WS_PING_TIMEOUT = int(os.getenv('WS_PING_TIMEOUT', '25'))

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        reload=os.getenv('RELOAD', '0') == '1',
        ws_ping_interval=WS_PING_INTERVAL,
        ws_ping_timeout=WS_PING_TIMEOUT,
    )
else:
    # Also support: from backend.run import run; run()
    def run():
        uvicorn.run(
            "backend.main:app",
            host=HOST,
            port=PORT,
            ws_ping_interval=WS_PING_INTERVAL,
            ws_ping_timeout=WS_PING_TIMEOUT,
        )
