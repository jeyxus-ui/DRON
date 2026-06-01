import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { API_URL, WS_URL } from '../config';

// ── Tipos ──────────────────────────────────────────────────────────────────────

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
}

export interface CommandResult {
  success: boolean;
  message: string;
}

interface DroneContextType {
  telemetry:    Telemetry;
  connected:    boolean;
  demoMode:     boolean;
  sendCommand:  (type: string, params?: any) => Promise<CommandResult>;
  armDrone:     () => Promise<CommandResult>;
  disarmDrone:  () => Promise<CommandResult>;
  takeoff:      (altitude: number) => Promise<CommandResult>;
  land:         () => Promise<CommandResult>;
  emergency:    (action: 'STOP' | 'RTL' | 'LAND') => Promise<CommandResult>;
  setJoystick:  (throttle?: number, yaw?: number, pitch?: number, roll?: number) => void;
  // Navegación autónoma
  navGoto:      (lat: number, lon: number, alt?: number) => Promise<CommandResult>;
  navMission:   (waypoints: any[]) => Promise<CommandResult>;
  navStop:      () => Promise<CommandResult>;
  setAvoidance: (active: boolean) => Promise<CommandResult>;
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

export const DroneProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [telemetry, setTelemetry] = useState<Telemetry>(DEFAULT_TELEMETRY);
  const [connected, setConnected] = useState(false);
  const [demoMode, setDemoMode] = useState(false);

  const ws               = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingCommands  = useRef<Map<string, (result: CommandResult) => void>>(new Map());
  const demoStartTime    = useRef<number>(0);
  const demoTick         = useRef<ReturnType<typeof setInterval> | null>(null);
  const demoArmed        = useRef(false);
  const mountedRef       = useRef(true);

  // ── Estado RC persistente ─────────────────────────────────────────────────
  const rcValues = useRef({ throttle: 0, yaw: 0, pitch: 0, roll: 0 });

  // ── Iniciar/Detener demo ──────────────────────────────────────────────────

  const startDemo = useCallback(() => {
    if (demoTick.current) return;
    console.log('[DEMO] 📱 Modo demo activado — datos simulados');
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

  // ── WebSocket ────────────────────────────────────────────────────────────

  const connectWebSocket = useCallback(() => {
    try {
      console.log(`[WS] Conectando a ${WS_URL}...`);
      const newWs = new WebSocket(WS_URL);

      newWs.onopen = () => {
        console.log('[WS] ✅ Conexión establecida');
        setConnected(true);
        stopDemo();
      };

      newWs.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          if (message.type === 'telemetry') {
            setTelemetry(message.data);

          } else if (message.type === 'command_ack') {
            const cmdType = message.command as string;
            const result: CommandResult = {
              success: message.result?.success ?? false,
              message: message.result?.message ?? '',
            };
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
          console.error('[WS] Error parseando mensaje:', err);
        }
      };

      newWs.onerror = () => {
        console.error('[WS] ❌ Error de WebSocket');
        setConnected(false);
        startDemo();
      };

      newWs.onclose = (event) => {
        console.warn(`[WS] ⚠️ Cerrado — code=${event.code}`);
        setConnected(false);

        pendingCommands.current.forEach((resolve) => {
          resolve({ success: false, message: 'Conexión perdida' });
        });
        pendingCommands.current.clear();

        if (mountedRef.current) {
          reconnectTimeout.current = setTimeout(() => {
            console.log('[WS] 🔄 Reconectando...');
            connectWebSocket();
            startDemo();
          }, 3000);
        }
      };

      ws.current = newWs;
    } catch (err) {
      console.error('[WS] Error creando WebSocket:', err);
    }
  }, [startDemo, stopDemo]);

  useEffect(() => {
    mountedRef.current = true;
    connectWebSocket();
    const fallbackTimer = setTimeout(() => {
      if (ws.current?.readyState !== WebSocket.OPEN) startDemo();
    }, 5000);
    return () => {
      mountedRef.current = false;
      ws.current?.close();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      clearTimeout(fallbackTimer);
      stopDemo();
    };
  }, []);

  // ── RC Heartbeat a 10 Hz ──────────────────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({
          type:   'RC_CONTROL',
          params: { ...rcValues.current },
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
        resolve({ success: false, message: 'Sin conexión con el dron' });
        return;
      }

      const NO_ACK_COMMANDS = ['RC_CONTROL', 'RC_RESET'];
      if (NO_ACK_COMMANDS.includes(type)) {
        ws.current.send(JSON.stringify({ type, params }));
        resolve({ success: true, message: 'RC enviado' });
        return;
      }

      const timer = setTimeout(() => {
        if (pendingCommands.current.has(type)) {
          pendingCommands.current.delete(type);
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
      sendCommand,
      armDrone,
      takeoff,
      land,
      emergency,
      setJoystick,
      navGoto,
      navMission,
      navStop,
      setAvoidance,
    }}>
      {children}
    </DroneContext.Provider>
  );
};