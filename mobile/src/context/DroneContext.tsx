import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { getWsUrl, getApiUrl, setHostIp } from '../config';
import { getStoredIp, getMaxAltitude, saveMaxAltitude, getMaxSpeed, saveMaxSpeed } from '../utils/ipConfig';

// ── Tipos ──────────────────────────────────────────────────────────────────────

export type ErrorSeverity = 'info' | 'warn' | 'error' | 'critical';

export interface AppError {
  id: string;
  code: string;
  message: string;
  detail?: string;
  timestamp: number;
  severity: ErrorSeverity;
  count: number;
  acknowledged: boolean;  // true si ya fue descartado del banner (sigue en historial)
}

interface ConnectionHealth {
  connected:              boolean;
  healthy:                boolean;
  heartbeat_age_s:        number | null;
  last_msg_age_s:         number | null;
  socket_alive:           boolean;
  reconnecting:           boolean;
  needs_reconnect:        boolean;
  probe_failures:         number;
  device:                 string;
}

interface Telemetry {
  armed:              boolean;
  mode:               string;
  altitude:           number;
  latitude:           number;
  longitude:          number;
  roll:               number;
  pitch:              number;
  yaw:                number;
  battery_voltage:    number;
  battery_remaining:  number;
  ground_speed:       number;
  vertical_speed:     number;
  satellites:         number;
  hdop:               number;
  // Sensores MTF01 y YDLIDAR
  mtf01_distance?:           number;
  lidar_closest_distance?:   number;
  lidar_closest_angle?:      number;
  lidar_points?:             number;
  obstacle_ahead?:           boolean;
  // Salud de conexión MAVLink
  connection_health?:        ConnectionHealth;
}

export interface CommandResult {
  success: boolean;
  message: string;
}

interface DroneContextType {
  telemetry:       Telemetry;
  connected:       boolean;
  demoMode:        boolean;
  connectionHealth: ConnectionHealth | null;
  mavlinkOnline:   boolean;
  sendCommand:     (type: string, params?: any) => Promise<CommandResult>;
  armDrone:        () => Promise<CommandResult>;
  disarmDrone:     () => Promise<CommandResult>;
  takeoff:         (altitude: number) => Promise<CommandResult>;
  land:            () => Promise<CommandResult>;
  emergency:       (action: 'STOP' | 'RTL' | 'LAND') => Promise<CommandResult>;
  setJoystick:     (throttle?: number, yaw?: number, pitch?: number, roll?: number) => void;
  // Navegación autónoma
  navGoto:         (lat: number, lon: number, alt?: number) => Promise<CommandResult>;
  navMission:      (waypoints: any[]) => Promise<CommandResult>;
  navStop:         () => Promise<CommandResult>;
  setAvoidance:    (active: boolean) => Promise<CommandResult>;
  // IP dinámica
  forceReconnect:  () => void;
  // Error handling
  errors:            AppError[];
  lastError:         AppError | null;
  pushError:         (code: string, message: string, severity?: ErrorSeverity, detail?: string) => void;
  clearErrors:       () => void;
  dismissError:      (id: string) => void;
  errorHistory:      AppError[];
  clearErrorHistory: () => void;
  // Límites
  maxAltitude:       number;
  setMaxAltitude:    (alt: number) => void;
  maxSpeed:          number;
  setMaxSpeed:       (spd: number) => void;
}

const DroneContext = createContext<DroneContextType | undefined>(undefined);

export const useDrone = () => {
  const ctx = useContext(DroneContext);
  if (!ctx) throw new Error('useDrone debe usarse dentro de DroneProvider');
  return ctx;
};

// ── Telemetría por defecto ─────────────────────────────────────────────────────

const DEFAULT_TELEMETRY: Telemetry = {
  armed:             false,
  mode:              'STANDBY',
  altitude:          0,
  latitude:          0,
  longitude:         0,
  roll:              0,
  pitch:             0,
  yaw:               0,
  battery_voltage:   0,
  battery_remaining: 0,
  ground_speed:      0,
  vertical_speed:    0,
  satellites:        0,
  hdop:              0,
  mtf01_distance:          undefined,
  lidar_closest_distance:  undefined,
  lidar_closest_angle:     undefined,
  lidar_points:            undefined,
  obstacle_ahead:          undefined,
};

// ── Generar telemetría demo (simula dron real) ─────────────────────────────────

const DEMO_ORIGIN = {
  lat: 4.7110,
  lon: -74.0721,
};

const DEMO_MODES = ['STABILIZE', 'ALT_HOLD', 'LOITER', 'GUIDED', 'AUTO', 'RTL', 'LAND'];

const createDemoTelemetry = (armed: boolean, seconds: number): Telemetry => {
  const mode = armed 
    ? DEMO_MODES[Math.floor(Math.random() * DEMO_MODES.length)]
    : 'STANDBY';
  
  const altitude = armed 
    ? Math.max(0, 10 + 5 * Math.sin(seconds * 0.1)) 
    : 0;
  
  const groundSpeed = armed 
    ? Math.max(0, 8 + 4 * Math.sin(seconds * 0.05)) 
    : 0;
  
  const verticalSpeed = armed 
    ? 0.3 * Math.cos(seconds * 0.1) 
    : 0;
  
  return {
    armed,
    mode,
    altitude,
    latitude: DEMO_ORIGIN.lat + 0.0005 * Math.sin(seconds * 0.02),
    longitude: DEMO_ORIGIN.lon + 0.0005 * Math.cos(seconds * 0.02),
    roll: 2 * Math.sin(seconds * 0.3),
    pitch: 3 * Math.sin(seconds * 0.2),
    yaw: (seconds * 5) % 360,
    battery_voltage: armed ? 12.6 - (seconds % 300) * 0.01 : 12.6,
    battery_remaining: armed ? Math.max(0, 100 - (seconds % 300) * 0.1) : 100,
    ground_speed: groundSpeed,
    vertical_speed: verticalSpeed,
    satellites: armed ? 12 + Math.floor(Math.random() * 4) : 10,
    hdop: 0.6 + Math.random() * 0.3,
  };
};

// ── Provider ───────────────────────────────────────────────────────────────────

let errorCounter = 0;
const genErrorId = () => `err_${++errorCounter}_${Date.now()}`;

// ── Persistencia de historial de errores ────────────────────────────────────

const ERROR_HISTORY_FILE = 'error_history.json';
let _fs_available = true;

const getFS = () => {
  try {
    return require('react-native-fs');
  } catch {
    _fs_available = false;
    return null;
  }
};

const persistErrorHistory = async (history: AppError[]) => {
  if (!_fs_available) return;
  try {
    const RNFS = getFS();
    if (!RNFS) return;
    const dir = `${RNFS.DocumentDirectoryPath}/GCS`;
    const exists = await RNFS.exists(dir);
    if (!exists) await RNFS.mkdir(dir);
    await RNFS.writeFile(`${dir}/${ERROR_HISTORY_FILE}`, JSON.stringify(history), 'utf8');
  } catch { /* fallback silencioso */ }
};

const loadErrorHistory = async (): Promise<AppError[]> => {
  if (!_fs_available) return [];
  try {
    const RNFS = getFS();
    if (!RNFS) return [];
    const path = `${RNFS.DocumentDirectoryPath}/GCS/${ERROR_HISTORY_FILE}`;
    const exists = await RNFS.exists(path);
    if (!exists) return [];
    const data = await RNFS.readFile(path, 'utf8');
    return JSON.parse(data);
  } catch { return []; }
};

export const DroneProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [telemetry, setTelemetry] = useState<Telemetry>(DEFAULT_TELEMETRY);
  const [connected, setConnected] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [errors, setErrors] = useState<AppError[]>([]);
  const [errorHistory, setErrorHistory] = useState<AppError[]>([]);
  const [connectionHealth, setConnectionHealth] = useState<ConnectionHealth | null>(null);
  const [mavlinkOnline, setMavlinkOnline] = useState(true);

  const ws               = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingCommands  = useRef<Map<string, (result: CommandResult) => void>>(new Map());
  const demoStartTime    = useRef<number>(0);
  const demoTick         = useRef<ReturnType<typeof setInterval> | null>(null);
  const demoArmed        = useRef(false);
  const mountedRef       = useRef(true);
  const reconnectAttempt = useRef(0);
  const demoDelayTimer   = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Límites ──────────────────────────────────────────────────────────────
  const [maxAltitude, setMaxAltitudeState] = useState<number>(3);
  const [maxSpeed, setMaxSpeedState] = useState<number>(0.3);
  const telemetryRef = useRef<Telemetry>(DEFAULT_TELEMETRY);
  const maxAltitudeRef = useRef<number>(3);
  const maxSpeedRef = useRef<number>(0.3);
  const maxAltWarnedRef = useRef(false);

  // Mantener refs sincronizados con estado
  useEffect(() => { telemetryRef.current = telemetry; }, [telemetry]);
  useEffect(() => { maxAltitudeRef.current = maxAltitude; }, [maxAltitude]);
  useEffect(() => { maxSpeedRef.current = maxSpeed; }, [maxSpeed]);

  // ── Error handling ────────────────────────────────────────────────────────

  const pushError = useCallback((code: string, message: string, severity: ErrorSeverity = 'error', detail?: string) => {
    const now = Date.now();
    const fn = severity === 'critical' ? console.error : severity === 'warn' ? console.warn : console.log;
    fn(`[${severity.toUpperCase()}] ${code}: ${message}`, detail ?? '');

    // Si el mismo código ya está visible, solo actualizar timestamp + count
    setErrors(prev => {
      const existing = prev.find(e => e.code === code);
      if (existing) {
        return prev.map(e =>
          e.code === code
            ? { ...e, count: e.count + 1, timestamp: now, acknowledged: false }
            : e
        );
      }
      const err: AppError = {
        id: genErrorId(),
        code, message, detail,
        timestamp: now, severity, count: 1, acknowledged: false,
      };
      return [err, ...prev].slice(0, 50);
    });

    // Historial: guardar siempre (dedup por código para no saturar)
    setErrorHistory(prev => {
      const existing = prev.find(e => e.code === code);
      if (existing) {
        return prev.map(e =>
          e.code === code
            ? { ...e, count: e.count + 1, timestamp: now, detail: detail ?? e.detail, acknowledged: false }
            : e
        );
      }
      const err: AppError = {
        id: genErrorId(),
        code, message, detail,
        timestamp: now, severity, count: 1, acknowledged: false,
      };
      const updated = [err, ...prev].slice(0, 200);
      // Persistir a archivo en background
      persistErrorHistory(updated);
      return updated;
    });
  }, []);

  const clearErrors = useCallback(() => setErrors([]), []);

  const clearErrorHistory = useCallback(() => {
    setErrorHistory([]);
    persistErrorHistory([]);
  }, []);

  const setMaxAltitude = useCallback((alt: number) => {
    setMaxAltitudeState(alt);
    saveMaxAltitude(alt);
  }, []);

  const setMaxSpeed = useCallback((spd: number) => {
    setMaxSpeedState(spd);
    saveMaxSpeed(spd);
  }, []);

  // Cargar historial al montar
  useEffect(() => {
    loadErrorHistory().then(h => {
      if (h.length > 0) setErrorHistory(h);
    });
  }, []);

  const dismissError = useCallback((id: string) => {
    setErrors(prev => prev.map(e =>
      e.id === id ? { ...e, acknowledged: true } : e
    ));
    setErrorHistory(prev => prev.map(e =>
      e.id === id ? { ...e, acknowledged: true } : e
    ));
  }, []);

  const lastError = errors.length > 0 ? errors[0] : null;

  // ── Estado RC persistente ─────────────────────────────────────────────────
  const rcValues = useRef({ throttle: 0, yaw: 0, pitch: 0, roll: 0 });

  // ── Iniciar/Detener demo ──────────────────────────────────────────────────

  const startDemo = useCallback(() => {
    if (demoTick.current) return;
    console.log('[DEMO] 📱 Modo demo activado — datos simulados');
    pushError('DEMO_MODE', 'Modo demo activado — datos simulados, no del dron real', 'warn');
    setDemoMode(true);
    demoStartTime.current = Date.now();
    demoArmed.current = false;
    setTelemetry(createDemoTelemetry(false, 0));

    demoTick.current = setInterval(() => {
      const elapsed = (Date.now() - demoStartTime.current) / 1000;
      setTelemetry(prev => {
        const armed = prev.armed;
        return createDemoTelemetry(armed, elapsed);
      });
    }, 500);
  }, []);

  const stopDemo = useCallback(() => {
    console.log('[DEMO] 🛑 Modo demo desactivado');
    setDemoMode(false);
    if (demoTick.current) {
      clearInterval(demoTick.current);
      demoTick.current = null;
    }
  }, []);

  // ── Forzar reconexión (al cambiar IP) ────────────────────────────────────

  const forceReconnect = useCallback(() => {
    console.log('[WS] 🔄 Forzando reconexión...');
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
      reconnectTimeout.current = null;
    }
    if (demoDelayTimer.current) {
      clearTimeout(demoDelayTimer.current);
      demoDelayTimer.current = null;
    }
    if (ws.current) {
      ws.current.onclose = null;
      ws.current.close();
      ws.current = null;
    }
    reconnectAttempt.current = 0;
    setConnected(false);
    startDemo();
    setTimeout(() => {
      connectWebSocket();
    }, 1000);
  }, [startDemo]);

  // ── WebSocket ────────────────────────────────────────────────────────────

  const connectWebSocket = useCallback(() => {
    try {
      const url = getWsUrl();
      console.log(`[WS] Conectando a ${url}... (intento ${reconnectAttempt.current + 1})`);
      const newWs = new WebSocket(url);

      newWs.onopen = () => {
        console.log('[WS] ✅ Conexión establecida');
        pushError('WS_CONNECTED', 'Conectado al servidor', 'info');
        setConnected(true);
        reconnectAttempt.current = 0;
        stopDemo();
        if (demoDelayTimer.current) {
          clearTimeout(demoDelayTimer.current);
          demoDelayTimer.current = null;
        }
      };

      newWs.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          if (message.type === 'telemetry') {
            if (message.data?.error) {
              pushError('TELEMETRY_ERROR', `Error en telemetría: ${message.data.error}`, 'warn');
            } else {
              setTelemetry(message.data);
              if (message.data.connection_health) {
                setConnectionHealth(message.data.connection_health);
                setMavlinkOnline(message.data.connection_health.healthy ?? true);
              }
            }

          } else if (message.type === 'connection_alert') {
            const alertType = message.alert as string;
            if (alertType === 'mavlink_lost') {
              setMavlinkOnline(false);
              pushError('MAVLINK_LOST', message.message || 'Conexión MAVLink perdida — reconectando...', 'critical');
              console.warn('[WS] ⚠️ MAVLink lost alert received');
            } else if (alertType === 'mavlink_restored') {
              setMavlinkOnline(true);
              pushError('MAVLINK_RESTORED', message.message || 'Conexión MAVLink restaurada', 'info');
              console.log('[WS] ✅ MAVLink restored alert received');
            } else if (alertType === 'connected') {
              if (message.mavlink) {
                setConnectionHealth(message.mavlink);
                setMavlinkOnline(message.mavlink.healthy ?? true);
              }
            }

          } else if (message.type === 'command_ack') {
            const cmdType = message.command as string;
            const result: CommandResult = {
              success: message.result?.success ?? false,
              message: message.result?.message ?? '',
            };
            if (!result.success) {
              pushError(`${cmdType}_FAILED`, result.message || `Comando ${cmdType} falló`, 'error');
            }
            const resolve = pendingCommands.current.get(cmdType);
            if (resolve) {
              resolve(result);
              pendingCommands.current.delete(cmdType);
            }
            console.log(`[WS] ACK ${cmdType}:`, result);

          } else {
            console.log('[WS] Mensaje desconocido:', message.type);
          }
        } catch (err) {
          const errMsg = err instanceof Error ? err.message : String(err);
          pushError('WS_PARSE', `Error parseando mensaje WebSocket: ${errMsg}`, 'error');
          console.error('[WS] Error parseando mensaje:', err);
        }
      };

      newWs.onerror = () => {
        console.error('[WS] ❌ Error de WebSocket');
        setConnected(false);
        // NO activar demo mode inmediatamente en onerror
        // Esperar a onclose para decidir
      };

      newWs.onclose = (event) => {
        const code = event.code ?? 0;
        const reasons: Record<number, string> = {
          1000: 'Cierre normal',
          1001: 'El servidor se desconectó',
          1006: 'Conexión abortada (timeout / sin respuesta)',
          1011: 'Error interno del servidor',
        };
        const reason = reasons[code] ?? `Código ${code}`;
        pushError('WS_CLOSED', `Conexión perdida: ${reason}`, 'critical');
        console.warn(`[WS] ⚠️ Cerrado — code=${event.code}`);
        setConnected(false);

        pendingCommands.current.forEach((resolve) => {
          resolve({ success: false, message: `Conexión perdida: ${reason}` });
        });
        pendingCommands.current.clear();

        if (mountedRef.current) {
          // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
          reconnectAttempt.current += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempt.current - 1), 30000);
          console.log(`[WS] 🔄 Reconectando en ${delay}ms (intento ${reconnectAttempt.current})...`);

          // Activar demo mode solo después de 3 intentos fallidos (~7s)
          if (reconnectAttempt.current >= 3 && !demoTick.current) {
            startDemo();
          }

          reconnectTimeout.current = setTimeout(() => {
            console.log('[WS] 🔄 Reconectando...');
            pushError('WS_RECONNECT', 'Reconectando al servidor...', 'info');
            connectWebSocket();
          }, delay);
        }
      };

      ws.current = newWs;
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      pushError('WS_CREATE', `Error creando WebSocket: ${errMsg}`, 'critical');
      console.error('[WS] Error creando WebSocket:', err);
    }
  }, [startDemo, stopDemo]);

  useEffect(() => {
    mountedRef.current = true;
    (async () => {
      const [savedIp, savedMaxAlt, savedMaxSpd] = await Promise.all([getStoredIp(), getMaxAltitude(), getMaxSpeed()]);
      setHostIp(savedIp);
      setMaxAltitudeState(savedMaxAlt);
      setMaxSpeedState(savedMaxSpd);
      connectWebSocket();
    })();
    const fallbackTimer = setTimeout(() => {
      if (ws.current?.readyState !== WebSocket.OPEN && !connected) {
        console.log('[WS] ⏱ Timeout de conexión — activando modo demo');
        startDemo();
      }
    }, 8000);
    return () => {
      mountedRef.current = false;
      ws.current?.close();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      if (demoDelayTimer.current) clearTimeout(demoDelayTimer.current);
      clearTimeout(fallbackTimer);
      stopDemo();
    };
  }, []);

  // ── Monitorear límite de altura ───────────────────────────────────────────
  useEffect(() => {
    const armed = telemetry.armed;
    const alt = telemetry.altitude;
    if (alt >= maxAltitude && armed) {
      if (!maxAltWarnedRef.current) {
        maxAltWarnedRef.current = true;
        pushError('MAX_ALT_REACHED', `Altura máxima alcanzada: ${alt.toFixed(1)}m (límite: ${maxAltitude}m)`, 'warn');
      }
    } else {
      maxAltWarnedRef.current = false;
    }
  }, [telemetry.altitude, telemetry.armed, maxAltitude, pushError]);

  // ── Enviar velocidad de navegación al backend cuando cambia ───────────────
  useEffect(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      const speedMps = Math.max(0.5, +(maxSpeed * 6).toFixed(2));
      ws.current.send(JSON.stringify({
        type: 'SET_NAV_SPEED',
        params: { speed: speedMps },
      }));
    }
  }, [maxSpeed]);

  // ── RC Heartbeat a 10 Hz ──────────────────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        const params = { ...rcValues.current };
        // Clamp throttle si se superó el límite de altura
        if (params.throttle > 0.5 && telemetryRef.current.altitude >= maxAltitudeRef.current) {
          params.throttle = 0.5;
        }
        // Clamp velocidad horizontal (pitch/roll)
        const spd = maxSpeedRef.current;
        if (spd < 1) {
          params.pitch = Math.max(-spd, Math.min(spd, params.pitch));
          params.roll  = Math.max(-spd, Math.min(spd, params.roll));
        }
        ws.current.send(JSON.stringify({
          type:   'RC_CONTROL',
          params,
        }));
      }
    }, 100);

    return () => clearInterval(interval);
  }, []);

  // ── sendCommand ───────────────────────────────────────────────────────────

  const sendCommand = useCallback((type: string, params: any = {}): Promise<CommandResult> => {
    if (demoMode) {
      const demoResult = handleDemoCommand(type, params);
      return Promise.resolve(demoResult);
    }

    return new Promise((resolve) => {
      if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
        pushError(`${type}_FAILED`, 'Sin conexión con el servidor — el dron no está disponible', 'error');
        resolve({ success: false, message: 'Sin conexión con el dron' });
        return;
      }

      const NO_ACK_COMMANDS = ['RC_CONTROL', 'RC_RESET', 'SET_NAV_SPEED'];
      if (NO_ACK_COMMANDS.includes(type)) {
        ws.current.send(JSON.stringify({ type, params }));
        resolve({ success: true, message: 'RC enviado' });
        return;
      }

      const timer = setTimeout(() => {
        if (pendingCommands.current.has(type)) {
          pendingCommands.current.delete(type);
          pushError('CMD_TIMEOUT', `Comando ${type} — el dron no respondió en 5s`, 'warn');
          resolve({ success: false, message: 'Timeout — el dron no respondió' });
        }
      }, 5000);

      pendingCommands.current.set(type, (result) => {
        clearTimeout(timer);
        resolve(result);
      });

      ws.current.send(JSON.stringify({ type, params }));
      console.log(`[WS] → ${type}`, params);
    });
  }, [demoMode]);

  const handleDemoCommand = (type: string, params: any): CommandResult => {
    switch (type) {
      case 'ARM':
        demoArmed.current = true;
        setTelemetry(prev => ({ ...prev, armed: true, mode: 'GUIDED' }));
        return { success: true, message: '✅ Motor armado (demo)' };
      case 'DISARM':
        demoArmed.current = false;
        setTelemetry(prev => ({ ...prev, armed: false, mode: 'STANDBY', altitude: 0, ground_speed: 0 }));
        return { success: true, message: '✅ Motor desarmado (demo)' };
      case 'TAKEOFF':
        if (!demoArmed.current) return { success: false, message: 'Arma el dron primero' };
        demoArmed.current = true;
        setTelemetry(prev => ({
          ...prev,
          armed: true,
          mode: 'GUIDED',
          altitude: params.altitude ?? 10,
          ground_speed: 0,
          vertical_speed: 1.5,
        }));
        return { success: true, message: `✅ Despegando a ${params.altitude ?? 10}m (demo)` };
      case 'LAND':
        demoArmed.current = false;
        setTelemetry(prev => ({
          ...prev,
          armed: false,
          mode: 'LAND',
          altitude: 0,
          ground_speed: 0,
          vertical_speed: -0.5,
        }));
        return { success: true, message: '✅ Aterrizando (demo)' };
      case 'EMERGENCY': {
        const action = params?.action ?? 'STOP';
        if (action === 'STOP') {
          demoArmed.current = false;
          setTelemetry(prev => ({ ...prev, armed: false, mode: 'STANDY', altitude: 0 }));
        } else if (action === 'RTL') {
          setTelemetry(prev => ({ ...prev, mode: 'RTL', altitude: 15 }));
        } else if (action === 'LAND') {
          demoArmed.current = false;
          setTelemetry(prev => ({ ...prev, armed: false, mode: 'LAND', altitude: 0 }));
        }
        return { success: true, message: `✅ ${action} ejecutado (demo)` };
      }
      case 'SET_MODE':
        setTelemetry(prev => ({ ...prev, mode: params.mode }));
        return { success: true, message: `✅ Modo cambiado a ${params.mode} (demo)` };
      case 'RC_CONTROL':
        return { success: true, message: 'RC enviado (demo)' };
      case 'GOTO':
        setTelemetry(prev => ({
          ...prev, latitude: params.latitude, longitude: params.longitude,
          altitude: params.altitude ?? prev.altitude, mode: 'GUIDED',
        }));
        return { success: true, message: `✅ Navegando a (${params.latitude}, ${params.longitude}) (demo)` };
      case 'GOTO_RELATIVE':
        return { success: true, message: `✅ Navegando ${params.forward ?? 0}m adelante, ${params.right ?? 0}m derecha (demo)` };
      case 'MISSION_UPLOAD_RELATIVE': {
        const relCount = params.waypoints?.length ?? 0;
        return { success: true, message: `✅ ${relCount} waypoints relativos subidos (demo)` };
      }
      case 'MISSION_UPLOAD': {
        const count = params.waypoints?.length ?? 0;
        return { success: true, message: `✅ ${count} waypoints subidos (demo)` };
      }
      case 'START_MISSION':
        setTelemetry(prev => ({ ...prev, mode: 'AUTO' }));
        return { success: true, message: '✅ Misión iniciada (demo)' };
      case 'CLEAR_MISSION':
        return { success: true, message: '✅ Misión limpiada (demo)' };
      case 'NAV_GOTO':
        setTelemetry(prev => ({ ...prev, mode: 'GUIDED', latitude: params.latitude, longitude: params.longitude }));
        return { success: true, message: `✅ Navegación autónoma a (${params.latitude}, ${params.longitude}) (demo)` };
      case 'NAV_MISSION':
        return { success: true, message: `✅ Misión autónoma con ${params.waypoints?.length ?? 0} waypoints (demo)` };
      case 'NAV_STOP':
        return { success: true, message: '✅ Navegación detenida (demo)' };
      case 'NAV_AVOIDANCE':
        return { success: true, message: `✅ Evitación ${params.active ? 'activada' : 'desactivada'} (demo)` };
      default:
        return { success: true, message: `✅ Comando ${type} OK (demo)` };
    }
  };

  // ── Comandos de alto nivel ────────────────────────────────────────────────

  const armDrone = useCallback(() =>
    sendCommand('ARM'), [sendCommand]);

  const disarmDrone = useCallback(() =>
    sendCommand('DISARM'), [sendCommand]);

  const takeoff = useCallback((altitude: number) =>
    sendCommand('TAKEOFF', { altitude }), [sendCommand]);

  const land = useCallback(() =>
    sendCommand('LAND'), [sendCommand]);

  const emergency = useCallback((action: 'STOP' | 'RTL' | 'LAND') =>
    sendCommand('EMERGENCY', { action }), [sendCommand]);

  // ── setJoystick ───────────────────────────────────────────────────────────
  const setJoystick = useCallback((
    throttle?: number,
    yaw?:      number,
    pitch?:    number,
    roll?:     number,
  ) => {
    if (throttle !== undefined) rcValues.current.throttle = throttle;
    if (yaw      !== undefined) rcValues.current.yaw      = yaw;
    if (pitch    !== undefined) rcValues.current.pitch    = pitch;
    if (roll     !== undefined) rcValues.current.roll     = roll;

    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type:   'RC_CONTROL',
        params: { ...rcValues.current },
      }));
    }
  }, []);

  // ── Navegación autónoma ──────────────────────────────────────────────────
  const navGoto = useCallback((lat: number, lon: number, alt: number = 10) =>
    sendCommand('NAV_GOTO', { latitude: lat, longitude: lon, altitude: alt }),
    [sendCommand]);

  const navMission = useCallback((waypoints: any[]) =>
    sendCommand('NAV_MISSION', { waypoints }),
    [sendCommand]);

  const navStop = useCallback(() =>
    sendCommand('NAV_STOP'),
    [sendCommand]);

  const setAvoidance = useCallback((active: boolean) =>
    sendCommand('NAV_AVOIDANCE', { active }),
    [sendCommand]);

  return (
    <DroneContext.Provider value={{
      telemetry,
      connected,
      demoMode,
      connectionHealth,
      mavlinkOnline,
      sendCommand,
      armDrone,
      disarmDrone,
      takeoff,
      land,
      emergency,
      setJoystick,
      navGoto,
      navMission,
      navStop,
      setAvoidance,
      forceReconnect,
      errors,
      lastError,
      pushError,
      clearErrors,
      dismissError,
      errorHistory,
      clearErrorHistory,
      maxAltitude,
      setMaxAltitude,
      maxSpeed,
      setMaxSpeed,
    }}>
      {children}
    </DroneContext.Provider>
  );
};