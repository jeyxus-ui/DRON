"""
Simulación de navegación con evitación de obstáculos.
Punto A → Punto B con un objeto intermedio detectado por sensores.

Uso:
    cd Dron
    python backend/test_nav_sim.py
"""
import sys, os, time, math, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Punto A y B ──────────────────────────────────────────────────────────────
A_LAT, A_LON = -34.6037, -58.3816
B_LAT, B_LON = -34.5980, -58.3700
# Obstáculo al 30% del camino (~370m de A)
OBSTACLE_LAT = A_LAT + (B_LAT - A_LAT) * 0.30
OBSTACLE_LON = A_LON + (B_LON - A_LON) * 0.30
ALT = 15.0


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def offset_position(lat, lon, dist_m, heading_deg):
    """Retorna (lat, lon) a dist_m en dirección heading_deg desde (lat, lon)."""
    R = 6371000
    rad = math.radians(heading_deg)
    dlat = dist_m * math.cos(rad) / R
    dlon = dist_m * math.sin(rad) / (R * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


# ── ObstacleInjector ─────────────────────────────────────────────────────────
class ObstacleInjector:
    """Inyecta datos de obstáculo cuando el dron está cerca."""
    def __init__(self, o_lat, o_lon, danger_radius=40.0):
        self.o_lat, self.o_lon = o_lat, o_lon
        self.danger_radius = danger_radius
        self.active = False
        self.last_safe_heading = None

    def get_sensor_data(self, pos):
        dist = haversine(pos['lat'], pos['lon'], self.o_lat, self.o_lon)

        angle_to_obs = math.degrees(math.atan2(
            self.o_lon - pos['lon'], self.o_lat - pos['lat']))
        rel_angle = (angle_to_obs - pos['yaw']) % 360

        if dist > self.danger_radius:
            was = self.active
            self.active = False
            if was:
                print(f"      [inyector] obstáculo superado ({dist:.0f}m)")
            return None  # sin obstáculo

        apparent = max(0.5, dist - 2)
        self.active = True
        # Desvío de ~40° respecto al rumbo original A→B para rodear el obstáculo
        route_heading = math.degrees(math.atan2(
            B_LON - A_LON, B_LAT - A_LAT))
        self.last_safe_heading = (route_heading - 40) % 360  # viraje a la izquierda

        if not getattr(self, '_warned', False):
            self._warned = True
            print(f"      [inyector] obstáculo activo — dist={dist:.0f}m "
                  f"safe_heading={self.last_safe_heading:.0f}°")

        return {
            'mtf01': {'distance_m': round(apparent, 2), 'valid': True},
            'lidar': {'points': 8, 'valid': True,
                      'closest_distance': round(max(0.3, apparent - 1), 2),
                      'closest_angle': round(rel_angle, 1)},
            'drone_yaw': pos['yaw'],
            'safe_direction': round(self.last_safe_heading, 1),
        }


# ── Mock SensorManager ───────────────────────────────────────────────────────
class MockObstacleMap:
    def to_dict(self): return {}
    def is_blocked(self, x, y, threshold=0.5): return False
    def find_free_direction(self, yaw, min_clearance_m=2.0): return yaw
    def reset(self): pass

class MockSensorManager:
    def __init__(self, injector):
        self.injector = injector
        self.obstacle_map = MockObstacleMap()
        self._running = False
        self.sim_mode = True
        self._sensor_data = {'mtf01': {'distance_m': None, 'valid': False},
                              'lidar': {'points': 0, 'valid': True,
                                        'closest_distance': None, 'closest_angle': None},
                              'drone_yaw': 0, 'safe_direction': None}
    def start(self): self._running = True
    def stop(self): self._running = False
    def set_drone_yaw(self, yaw): pass
    def get_data(self): return self._sensor_data
    def get_status(self): return {'running': True, 'sim_mode': True}


# ── Drone Simulator (movimiento a velocidad constante) ───────────────────────
class SimDrone:
    def __init__(self):
        self._lat, self._lon = A_LAT, A_LON
        self._alt = 5.0
        self._armed = False
        self._mode = 'STANDBY'
        self._yaw = 45.0
        self._target_lat = None
        self._target_lon = None
        self._target_alt = None
        self._lock = threading.Lock()
        self._goto_calls = []
        self._speed_mps = 15.0  # m/s constante
        self._thread = threading.Thread(target=self._move_loop, daemon=True)
        self._thread.start()

    def _move_loop(self):
        while True:
            with self._lock:
                if self._target_lat is not None and self._armed:
                    dlat = self._target_lat - self._lat
                    dlon = self._target_lon - self._lon
                    dist_m = haversine(self._lat, self._lon,
                                       self._target_lat, self._target_lon)
                    if dist_m < 1.0:
                        self._target_lat = None
                    else:
                        # Movimiento constante a self._speed_mps
                        step_m = self._speed_mps * 0.1  # 10 Hz → 1.5m por tick
                        fraction = min(step_m / max(dist_m, 0.1), 1.0)
                        self._lat += dlat * fraction
                        self._lon += dlon * fraction
                        if self._target_alt is not None:
                            alt_diff = self._target_alt - self._alt
                            self._alt += alt_diff * min(fraction * 5, 1.0)
            time.sleep(0.1)

    def is_connected(self): return True
    def is_armed(self): return self._armed
    def get_mode(self): return self._mode
    def get_system_status(self): return 4

    def arm(self, force=True): self._armed = True; self._mode = 'GUIDED'; return True
    def disarm(self, force=False): self._armed = False; return True
    def set_mode(self, mode): self._mode = mode; return True
    def takeoff(self, alt): self._armed = True; self._mode = 'GUIDED'; self._alt = alt; return True
    def land(self): self._mode = 'LAND'; return True
    def return_to_launch(self): self._mode = 'RTL'; return True
    def kill_motors(self): return False

    def goto(self, lat, lon, alt):
        with self._lock:
            self._target_lat = float(lat)
            self._target_lon = float(lon)
            self._target_alt = float(alt)
            self._goto_calls.append({'lat': lat, 'lon': lon, 'alt': alt, 'time': time.time()})
        return True
    def goto_position(self, lat, lon, alt): return self.goto(lat, lon, alt)
    def upload_mission(self, wps): return True
    def start_mission(self): return True
    def clear_mission(self): return True
    def get_flight_logs(self): return []

    def get_telemetry(self):
        with self._lock:
            return {'gps': {'lat': self._lat, 'lon': self._lon, 'alt': self._alt,
                            'satellites': 12, 'hdop': 0.7},
                    'attitude': {'roll': 0.0, 'pitch': 0.0, 'yaw': self._yaw},
                    'altitude': self._alt,
                    'battery': {'voltage': 12.5, 'remaining': 95},
                    'velocity': {'ground_speed': self._speed_mps, 'vertical_speed': 0.0},
                    'armed': self._armed, 'mode': self._mode}

    def get_status(self):
        return {'connected': True, 'armed': self._armed,
                'mode': self._mode, 'system_status': 4}


# ── Test ─────────────────────────────────────────────────────────────────────
def test():
    print("=" * 70)
    print("SIMULACIÓN: Navegación A→B con obstáculo intermedio")
    print("=" * 70)
    print(f"  A: ({A_LAT:.4f}, {A_LON:.4f})")
    print(f"  B: ({B_LAT:.4f}, {B_LON:.4f})  ({haversine(A_LAT,A_LON,B_LAT,B_LON):.0f}m)")
    print(f"  Obstáculo: ({OBSTACLE_LAT:.4f}, {OBSTACLE_LON:.4f})  "
          f"({haversine(A_LAT,A_LON,OBSTACLE_LAT,OBSTACLE_LON):.0f}m de A)")
    print()

    drone = SimDrone()
    drone.arm()

    injector = ObstacleInjector(OBSTACLE_LAT, OBSTACLE_LON, danger_radius=35.0)
    sensors = MockSensorManager(injector)

    from backend.navigation.avoidance import ObstacleAvoidance
    from backend.navigation.planner import PathPlanner
    from backend.navigation.controller import NavigationController

    avoidance = ObstacleAvoidance(safety_distance_m=4.0, brake_distance_m=1.5)
    planner = PathPlanner(step_size_m=5.0, clearance_m=2.0)
    nav = NavigationController(drone, sensors, avoidance, planner)
    nav._goto_interval = 0.3
    nav.start()

    nav.navigate_to(B_LAT, B_LON, ALT)

    # Hilo que inyecta datos de sensor ANTES de cada ciclo del nav_loop
    stop_patch = threading.Event()
    def sensor_patcher():
        while not stop_patch.is_set():
            raw = drone.get_telemetry()
            pos = {'lat': raw['gps']['lat'], 'lon': raw['gps']['lon'],
                   'yaw': raw['attitude']['yaw']}
            data = injector.get_sensor_data(pos)
            if data is None:
                # Sin obstáculo → datos limpios
                data = {'mtf01': {'distance_m': None, 'valid': False},
                        'lidar': {'points': 0, 'valid': True,
                                  'closest_distance': None, 'closest_angle': None},
                        'drone_yaw': pos['yaw'], 'safe_direction': None}
            sensors._sensor_data = data
            time.sleep(0.1)

    threading.Thread(target=sensor_patcher, daemon=True).start()

    # Monitoreo
    start = time.time()
    max_time = 150
    reached = triggered = evaded = False
    last_mode = ""
    log_entries = []

    while time.time() - start < max_time:
        time.sleep(0.3)
        elapsed = time.time() - start
        status = nav.get_status()
        mode = status['mode']
        gps = drone.get_telemetry()['gps']
        dist_b = haversine(gps['lat'], gps['lon'], B_LAT, B_LON)
        dist_o = haversine(gps['lat'], gps['lon'], OBSTACLE_LAT, OBSTACLE_LON)
        obs_active = injector.active

        log_entries.append((elapsed, gps['lat'], gps['lon'], mode, dist_b, dist_o, obs_active))

        if mode == 'AVOIDING':
            if not triggered:
                triggered = True
                print(f"\n  ⚠️  [{elapsed:5.1f}s] AVOIDING — obstáculo a {dist_o:.0f}m")
            if not evaded and dist_o < 15:
                evaded = True
                print(f"  🚁 [{elapsed:5.1f}s] Maniobra evasiva — obstáculo a {dist_o:.0f}m")

        if dist_b < 5.0:
            reached = True
            print(f"\n  ✅ [{elapsed:5.1f}s] PUNTO B (d={dist_b:.1f}m)")
            break

        if mode != last_mode:
            last_mode = mode
            marker = '⚠️' if mode == 'AVOIDING' else '▷'
            print(f"  {marker} [{elapsed:5.1f}s] {mode:11s}  "
                  f"({gps['lat']:.4f},{gps['lon']:.4f})  "
                  f"B={dist_b:.0f}m  O={dist_o:.0f}m  "
                  + ("⚠️" if obs_active else ""))

    print()
    print("=" * 70)
    print("RESULTADOS")
    print("=" * 70)
    print(f"  Tiempo:       {time.time()-start:.1f}s")
    print(f"  Punto B:      {'✅' if reached else '❌'}")
    print(f"  Avoidance:    {'✅' if triggered else '❌'}")
    print(f"  Maniobra:     {'✅' if evaded else '❌'}")
    print(f"  Gotos:        {len(drone._goto_calls)}")
    print(f"  Modo final:   {nav.mode}")

    nav.stop()
    stop_patch.set()
    time.sleep(0.2)

    # Resumen ruta
    print("\n  Trayectoria:")
    for e, lat, lon, mode, db, do, oa in log_entries[::10]:
        m = '⚠️' if mode == 'AVOIDING' else ('✅' if oa else '·')
        print(f"    {m} {e:5.1f}s  ({lat:.4f},{lon:.4f})  B={db:.0f}m  O={do:.0f}m")

    if reached and triggered:
        print("\n  🟢 SIMULACIÓN EXITOSA")
        return True
    print("\n  🔴 FALLÓ")
    return False


if __name__ == '__main__':
    sys.exit(0 if test() else 1)
