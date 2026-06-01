import importlib, traceback

modules = [
    'backend.api.rest',
    'backend.mavlink.telemetry',
    'backend.db.repository'
]

for m in modules:
    try:
        mod = importlib.import_module(m)
        print(f"Imported {m}: OK")
        if m == 'backend.api.rest':
            print('  has get_device =', hasattr(mod, 'get_device'))
        if m == 'backend.mavlink.telemetry':
            print('  DroneTelemetry __init__ =', mod.DroneTelemetry.__init__)
        if m == 'backend.db.repository':
            print('  has save_telemetry =', hasattr(mod, 'save_telemetry'))
    except Exception:
        print(f"Error importing {m}")
        traceback.print_exc()
