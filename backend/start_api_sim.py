"""Arranca la API con `MAVLINK_DEVICE=SIM` para pruebas locales (SITL/sim).

Uso:
    python backend/start_api_sim.py
"""
import os
import uvicorn

os.environ['MAVLINK_DEVICE'] = 'SIM'

if __name__ == '__main__':
    # Lanza la app FastAPI (backend.main:app)
    uvicorn.run('backend.main:app', host='0.0.0.0', port=8000, reload=True)
