"""Arranca la API con `MAVLINK_DEVICE=SIM` para pruebas locales (SITL/sim).

Uso:
    python backend/start_api_sim.py
"""
import os
import sys
import uvicorn

os.environ['MAVLINK_DEVICE'] = 'SIM'

# Asegura que el directorio raíz del proyecto está en sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if __name__ == '__main__':
    uvicorn.run(
        'backend.main:app',
        host='0.0.0.0',
        port=8000,
        reload=False,
        ws_ping_interval=20,
        ws_ping_timeout=10,
    )
