/**
 * VUELO AUTÓNOMO — misión simple y estricta:
 *   ARM → ELEVAR X → RUTA (puntos) → DESCENDER X → DESARMAR (opcional)
 *
 * Dos modos, cada uno con su propio mecanismo de confirmación (nunca se
 * mezclan ni se fabrica telemetría):
 *
 *   AUTONOMOUS TEST — banco, sin hélices. Los puntos de ruta son direcciones
 *   cardinales (relativas al dron, no brújula real) enviadas como pulsos RC
 *   reales (`setJoystick`, mismo canal que el joystick manual) para poder
 *   escuchar la respuesta de los motores. Como el dron no se desplaza, cada
 *   confirmación de progreso es explícitamente SIMULATED/TEST.
 *
 *   AUTONOMOUS GPS — vuelo real. Los puntos se tocan en un mapa y se navegan
 *   con el comando autónomo real (`navGoto` → NavigationController). Cada
 *   "punto alcanzado" y la altitud se confirman con telemetría real, nunca
 *   con un temporizador (el timeout solo detecta bloqueo → ERROR).
 *
 * Todo reutiliza mecanismos ya existentes (ARM/DISARM/TAKEOFF/GOTO_RELATIVE/
 * NAV_GOTO/RC_CONTROL) — no se modifica el backend ni ningún otro modo de
 * vuelo.
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, ScrollView, FlatList,
} from 'react-native';
import MapView, { Marker, Polyline, MapPressEvent } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone } from '../context/DroneContext';
import { theme } from '../theme';

const C = theme.colors;

// ── Tipos ────────────────────────────────────────────────────────────────

type Mode = 'TEST' | 'GPS';

type MissionState =
  | 'IDLE' | 'ARMING' | 'ARMED' | 'ASCENDING' | 'ALTITUDE_READY'
  | 'EXECUTING_ROUTE' | 'POINT_REACHED' | 'NEXT_POINT'
  | 'DESCENDING' | 'DESCENT_COMPLETE' | 'DISARMING' | 'FINAL' | 'ERROR';

type Cardinal = 'N' | 'NE' | 'E' | 'SE' | 'S' | 'SW' | 'W' | 'NW';

interface TestPoint { kind: 'TEST'; id: string; dir: Cardinal; }
interface GpsPoint { kind: 'GPS'; id: string; lat: number; lon: number; label: number; }
type RoutePoint = TestPoint | GpsPoint;

interface LogEntry { id: string; time: number; text: string; kind: 'real' | 'sim' | 'error'; }

const TIME_OPTS: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit' };

// Direcciones cardinales = dirección RELATIVA al dron (no brújula real).
// Solo se usan en modo TEST, como pulso RC pitch/roll (mismo mecanismo que el joystick manual).
const CARDINAL_VECTORS: Record<Cardinal, { pitch: number; roll: number }> = {
  N:  { pitch: 1, roll: 0 },
  S:  { pitch: -1, roll: 0 },
  E:  { pitch: 0, roll: 1 },
  W:  { pitch: 0, roll: -1 },
  NE: { pitch: 0.75, roll: 0.75 },
  NW: { pitch: 0.75, roll: -0.75 },
  SE: { pitch: -0.75, roll: 0.75 },
  SW: { pitch: -0.75, roll: -0.75 },
};
const CARDINAL_ORDER: Cardinal[] = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
const CARDINAL_LABEL: Record<Cardinal, string> = {
  N: 'NORTE', S: 'SUR', E: 'ESTE', W: 'OESTE',
  NE: 'NORESTE', NW: 'NOROESTE', SE: 'SURESTE', SW: 'SUROESTE',
};

const describePoint = (p: RoutePoint): string =>
  p.kind === 'TEST' ? CARDINAL_LABEL[p.dir] : `P${p.label} (${p.lat.toFixed(6)}, ${p.lon.toFixed(6)})`;

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));
const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(() => resolve(), ms));

export const BenchTestScreen: React.FC = () => {
  const {
    telemetry, connected, demoMode,
    armDrone, disarmDrone, takeoff, navGoto, navStop, sendCommand, setJoystick,
  } = useDrone();
  const insets = useSafeAreaInsets();

  // ── Configuración de la misión ────────────────────────────────────────
  const [mode, setMode] = useState<Mode>('TEST');
  const [propsConfirmed, setPropsConfirmed] = useState(false);
  const [elevateM, setElevateM] = useState('3');
  const [descendM, setDescendM] = useState('3');
  const [disarmAtEnd, setDisarmAtEnd] = useState(true);
  const [points, setPoints] = useState<RoutePoint[]>([]);

  // Parámetros de confirmación
  const [timeoutS, setTimeoutS] = useState('8');          // TEST: timeout SIMULATED/TEST
  const [gpsStallS, setGpsStallS] = useState('30');        // GPS: timeout de bloqueo (nunca de éxito)
  const [pulseSeconds, setPulseSeconds] = useState('2');   // TEST: duración del pulso RC
  const [pulseStrength, setPulseStrength] = useState('0.4'); // TEST: deflexión pitch/roll (0..1)
  const ALT_TOLERANCE_M = 0.5;

  // ── Estado de ejecución ───────────────────────────────────────────────
  const [state, setState] = useState<MissionState>('IDLE');
  const [currentPointIdx, setCurrentPointIdx] = useState(-1);
  const [commandLabel, setCommandLabel] = useState('');
  const [commandStatus, setCommandStatus] = useState<'SENT' | 'ACTIVE' | 'COMPLETED' | 'ERROR' | ''>('');
  const [waitSecondsLeft, setWaitSecondsLeft] = useState<number | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [altitudeReady, setAltitudeReady] = useState(false);
  const [startPos, setStartPos] = useState<{ lat: number; lon: number; alt: number } | null>(null);
  const [cruiseAlt, setCruiseAlt] = useState<number | null>(null);

  const telemetryRef = useRef(telemetry);
  useEffect(() => { telemetryRef.current = telemetry; }, [telemetry]);

  const cancelledRef = useRef(false);
  const runningRef = useRef(false);
  const confirmResolverRef = useRef<(() => void) | null>(null);
  const armedResolverRef = useRef<{ want: boolean; resolve: () => void } | null>(null);

  useEffect(() => {
    const pending = armedResolverRef.current;
    if (pending && telemetry.armed === pending.want) {
      armedResolverRef.current = null;
      pending.resolve();
    }
  }, [telemetry.armed]);

  const logCounter = useRef(0);
  const addLog = useCallback((text: string, kind: LogEntry['kind'] = 'real') => {
    logCounter.current += 1;
    const entry: LogEntry = { id: `l${logCounter.current}`, time: Date.now(), text, kind };
    setLog(prev => [entry, ...prev].slice(0, 300));
  }, []);

  // ── Helpers de espera ─────────────────────────────────────────────────

  /** Confirmación REAL de armado/desarmado vía telemetría (armed === want). */
  const waitForArmedState = (want: boolean, timeoutMs = 5000): Promise<boolean> => {
    if (telemetryRef.current.armed === want) return Promise.resolve(true);
    return new Promise(resolve => {
      let done = false;
      const timer = setTimeout(() => {
        if (done) return; done = true; armedResolverRef.current = null; resolve(false);
      }, timeoutMs);
      armedResolverRef.current = {
        want, resolve: () => { if (done) return; done = true; clearTimeout(timer); resolve(true); },
      };
    });
  };

  /** Confirmación REAL de altitud: telemetry.altitude dentro de tolerancia del objetivo. */
  const waitForRealAltitude = (target: number, timeoutMs: number): Promise<'reached' | 'timeout'> =>
    new Promise(resolve => {
      let done = false;
      const start = Date.now();
      const tick = setInterval(() => {
        if (done) return;
        if (Math.abs(telemetryRef.current.altitude - target) <= ALT_TOLERANCE_M) {
          done = true; clearInterval(tick); resolve('reached'); return;
        }
        if (Date.now() - start > timeoutMs) { done = true; clearInterval(tick); resolve('timeout'); }
      }, 200);
    });

  /** Confirmación REAL de punto GPS: nav_mode pasa de NAVIGATING a IDLE. */
  const waitForNavReached = (timeoutMs: number): Promise<'reached' | 'timeout'> =>
    new Promise(resolve => {
      let done = false;
      let sawNavigating = telemetryRef.current.nav_mode === 'NAVIGATING';
      const start = Date.now();
      const tick = setInterval(() => {
        if (done) return;
        const nm = telemetryRef.current.nav_mode;
        if (nm === 'NAVIGATING') sawNavigating = true;
        if (sawNavigating && nm === 'IDLE') { done = true; clearInterval(tick); resolve('reached'); return; }
        if (Date.now() - start > timeoutMs) { done = true; clearInterval(tick); resolve('timeout'); }
      }, 200);
    });

  /** Confirmación SIMULATED/TEST: timeout configurable o botón "Confirmar ahora". */
  const waitForTestConfirmation = (): Promise<'timeout' | 'manual'> => {
    const seconds = Math.max(1, Number(timeoutS) || 8);
    return new Promise(resolve => {
      let done = false;
      let remaining = seconds;
      setWaitSecondsLeft(remaining);
      const tick = setInterval(() => {
        remaining -= 1;
        setWaitSecondsLeft(Math.max(0, remaining));
        if (remaining <= 0 && !done) {
          done = true; clearInterval(tick); confirmResolverRef.current = null;
          setWaitSecondsLeft(null); resolve('timeout');
        }
      }, 1000);
      confirmResolverRef.current = () => {
        if (done) return; done = true; clearInterval(tick); setWaitSecondsLeft(null); resolve('manual');
      };
    });
  };
  const confirmNow = () => { confirmResolverRef.current?.(); };

  /** Pulso RC direccional (modo TEST) — mismo canal que el joystick manual, sin GPS. */
  const sendCardinalPulse = async (dir: Cardinal) => {
    const v = clamp(Number(pulseStrength) || 0.4, 0.1, 0.8);
    const vec = CARDINAL_VECTORS[dir];
    const pitch = +(vec.pitch * v).toFixed(2);
    const roll = +(vec.roll * v).toFixed(2);
    setJoystick(0.5, 0, pitch, roll);
    addLog(`COMMAND: ${CARDINAL_LABEL[dir]} — RC pitch=${pitch} roll=${roll} — SENT`, 'real');
    setCommandStatus('ACTIVE');
    const seconds = Math.max(1, Number(pulseSeconds) || 2);
    await sleep(seconds * 1000);
    setJoystick(0.5, 0, 0, 0);
    addLog('RC pulse: retorno a neutral (throttle en hover)', 'real');
  };

  // ── Agregar / quitar puntos ───────────────────────────────────────────

  const addCardinalPoint = (dir: Cardinal) =>
    setPoints(prev => [...prev, { kind: 'TEST', id: `t${Date.now()}_${prev.length}`, dir }]);

  const handleMapPress = (e: MapPressEvent) => {
    const { latitude, longitude } = e.nativeEvent.coordinate;
    setPoints(prev => [...prev, {
      kind: 'GPS', id: `g${Date.now()}_${prev.length}`,
      lat: latitude, lon: longitude, label: prev.filter(p => p.kind === 'GPS').length + 1,
    }]);
  };

  const removePoint = (id: string) => setPoints(prev => prev.filter(p => p.id !== id));
  const clearRoute = () => setPoints([]);

  // ── Motor de la misión ────────────────────────────────────────────────

  const canStart = connected && !demoMode && points.length > 0 &&
    (mode === 'GPS' || propsConfirmed) &&
    (state === 'IDLE' || state === 'FINAL' || state === 'ERROR');

  const stopActivePulse = () => setJoystick(0.5, 0, 0, 0);

  const abort = useCallback(async () => {
    cancelledRef.current = true;
    confirmResolverRef.current?.();
    armedResolverRef.current?.resolve();
    addLog('DETENER — abortando misión', 'error');
    try { stopActivePulse(); } catch { /* best effort */ }
    try { await navStop(); } catch { /* best effort */ }
    try { if (telemetryRef.current.armed) await disarmDrone(); } catch { /* best effort */ }
    setState('IDLE');
    setCommandStatus(''); setCommandLabel(''); setCurrentPointIdx(-1);
    setAltitudeReady(false); setWaitSecondsLeft(null);
    runningRef.current = false;
  }, [navStop, disarmDrone, addLog]);

  const returnToStart = useCallback(async () => {
    if (mode !== 'GPS' || !startPos || runningRef.current) return;
    addLog(`VOLVER AL INICIO — navegando a (${startPos.lat.toFixed(6)}, ${startPos.lon.toFixed(6)})`, 'real');
    const r = await navGoto(startPos.lat, startPos.lon, startPos.alt);
    if (!r.success) { addLog(`VOLVER AL INICIO: ERROR — ${r.message}`, 'error'); return; }
    const res = await waitForNavReached(Number(gpsStallS) * 1000 || 30000);
    addLog(res === 'reached' ? 'VOLVER AL INICIO: llegada confirmada (real)' : 'VOLVER AL INICIO: TIMEOUT', res === 'reached' ? 'real' : 'error');
  }, [mode, startPos, navGoto, gpsStallS, addLog]);

  const runMission = useCallback(async () => {
    if (!canStart || runningRef.current) return;
    runningRef.current = true;
    cancelledRef.current = false;
    setLog([]);
    addLog(`MISIÓN INICIADA — modo ${mode}, ${points.length} punto(s)`, 'sim');

    // 1) ARM
    setState('ARMING');
    addLog('ARM COMMAND: SENT', 'real');
    const armResult = await armDrone();
    if (cancelledRef.current) return;
    if (!armResult.success) {
      addLog(`ARM: ERROR — ${armResult.message}`, 'error'); setState('ERROR'); runningRef.current = false; return;
    }
    const armedOk = await waitForArmedState(true, 5000);
    if (cancelledRef.current) return;
    if (!armedOk) {
      addLog('ARM STATE: TIMEOUT — telemetría no confirmó armado en 5s', 'error');
      setState('ERROR'); runningRef.current = false; return;
    }
    addLog('ARM STATE: ARMED (confirmado por telemetría real)', 'real');
    setState('ARMED');
    setStartPos({ lat: telemetryRef.current.latitude, lon: telemetryRef.current.longitude, alt: telemetryRef.current.altitude });

    // 2) ASCEND (elevar X metros desde la altitud actual)
    setState('ASCENDING');
    const baseAlt = telemetryRef.current.altitude;
    const elevate = Math.max(0, Number(elevateM) || 0);
    const targetAlt = clamp(baseAlt + elevate, 1, 10); // TAKEOFF exige 1..10 en el backend
    addLog(`ELEVATE REQUEST: SENT (+${elevate}m desde ${baseAlt.toFixed(1)}m → objetivo ${targetAlt.toFixed(1)}m)`, 'real');
    const ascendResult = await takeoff(targetAlt);
    if (cancelledRef.current) return;
    if (!ascendResult.success) {
      addLog(`ELEVATE: ERROR — ${ascendResult.message}`, 'error'); setState('ERROR'); runningRef.current = false; return;
    }
    if (mode === 'GPS') {
      const r = await waitForRealAltitude(targetAlt, Number(gpsStallS) * 1000 || 30000);
      if (cancelledRef.current) return;
      if (r === 'timeout') {
        addLog('ALTITUDE TARGET: TIMEOUT — la altitud real no llegó al objetivo', 'error');
        setState('ERROR'); runningRef.current = false; return;
      }
      addLog(`ALTITUDE TARGET REACHED (real, ${telemetryRef.current.altitude.toFixed(1)}m)`, 'real');
    } else {
      addLog('AUTONOMOUS ALTITUDE TEST — esperando confirmación de prueba', 'sim');
      const c = await waitForTestConfirmation();
      if (cancelledRef.current) return;
      addLog(`ALTITUDE TARGET: SIMULATED / TEST (${c === 'manual' ? 'confirmación manual' : `timeout ${timeoutS}s`}) — TEST ALTITUDE ${targetAlt.toFixed(1)}m`, 'sim');
    }
    setCruiseAlt(targetAlt);
    setAltitudeReady(true);
    setState('ALTITUDE_READY');

    // 3) RUTA — puntos en el orden en que se agregaron
    for (let i = 0; i < points.length; i++) {
      if (cancelledRef.current) return;
      const p = points[i];
      setCurrentPointIdx(i);
      setState('EXECUTING_ROUTE');
      setCommandLabel(describePoint(p));
      setCommandStatus('SENT');

      if (p.kind === 'TEST') {
        await sendCardinalPulse(p.dir);
        if (cancelledRef.current) return;
        addLog('COMMAND STATUS: ACTIVE — esperando confirmación de prueba', 'sim');
        const c = await waitForTestConfirmation();
        if (cancelledRef.current) return;
        setCommandStatus('COMPLETED');
        addLog(`TEST TARGET REACHED (SIMULATED) — ${c === 'manual' ? 'confirmación manual' : `timeout ${timeoutS}s`}`, 'sim');
      } else {
        addLog(`COMMAND: NAVIGATE_TO_WAYPOINT P${p.label} (${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}, ${(cruiseAlt ?? targetAltFallback(telemetryRef.current.altitude)).toFixed(1)}m) — SENT`, 'real');
        const alt = cruiseAlt ?? telemetryRef.current.altitude;
        const r = await navGoto(p.lat, p.lon, alt);
        if (cancelledRef.current) return;
        if (!r.success) {
          addLog(`COMMAND: ERROR — ${r.message}`, 'error');
          setCommandStatus('ERROR'); setState('ERROR'); runningRef.current = false; return;
        }
        setCommandStatus('ACTIVE');
        addLog('COMMAND STATUS: ACTIVE — esperando confirmación real (nav_mode)', 'real');
        const res = await waitForNavReached(Number(gpsStallS) * 1000 || 30000);
        if (cancelledRef.current) return;
        if (res === 'timeout') {
          addLog('POINT: TIMEOUT — no se confirmó llegada real (posible bloqueo)', 'error');
          setCommandStatus('ERROR'); setState('ERROR'); runningRef.current = false; return;
        }
        setCommandStatus('COMPLETED');
        addLog(`POINT REACHED (real, nav_mode → IDLE) — P${p.label}`, 'real');
      }

      setState('POINT_REACHED');
      if (i < points.length - 1) { setState('NEXT_POINT'); addLog('NEXT COMMAND', 'sim'); }
    }

    // 4) DESCEND (bajar X metros desde la altitud actual)
    setCurrentPointIdx(-1); setCommandStatus(''); setCommandLabel('');
    setState('DESCENDING');
    const beforeDescAlt = telemetryRef.current.altitude;
    const requestedDescend = Math.max(0, Number(descendM) || 0);
    const effectiveDescend = mode === 'GPS' ? Math.min(requestedDescend, beforeDescAlt) : requestedDescend;
    const descendTarget = Math.max(0, beforeDescAlt - effectiveDescend);
    addLog(`DESCEND REQUEST: SENT (-${effectiveDescend.toFixed(1)}m desde ${beforeDescAlt.toFixed(1)}m → objetivo ${descendTarget.toFixed(1)}m)`, 'real');
    const descResult = await sendCommand('GOTO_RELATIVE', { forward: 0, right: 0, up: -effectiveDescend });
    if (cancelledRef.current) return;
    if (!descResult.success) {
      addLog(`DESCEND: ERROR — ${descResult.message}`, 'error'); setState('ERROR'); runningRef.current = false; return;
    }
    if (mode === 'GPS') {
      const r = await waitForRealAltitude(descendTarget, Number(gpsStallS) * 1000 || 30000);
      if (cancelledRef.current) return;
      if (r === 'timeout') {
        addLog('DESCENT: TIMEOUT — la altitud real no bajó al objetivo', 'error');
        setState('ERROR'); runningRef.current = false; return;
      }
      addLog(`DESCENT COMPLETE (real, ${telemetryRef.current.altitude.toFixed(1)}m)`, 'real');
    } else {
      addLog('AUTONOMOUS DESCENT TEST — esperando confirmación de prueba', 'sim');
      const c = await waitForTestConfirmation();
      if (cancelledRef.current) return;
      addLog(`DESCENT: SIMULATED / TEST (${c === 'manual' ? 'confirmación manual' : `timeout ${timeoutS}s`}) — TEST ALTITUDE ${descendTarget.toFixed(1)}m`, 'sim');
    }
    setState('DESCENT_COMPLETE');

    // 5) DISARM (opcional)
    if (disarmAtEnd) {
      setState('DISARMING');
      addLog('DISARM COMMAND: SENT', 'real');
      const disarmResult = await disarmDrone();
      if (cancelledRef.current) return;
      if (!disarmResult.success) {
        addLog(`DISARM: ERROR — ${disarmResult.message}`, 'error'); setState('ERROR'); runningRef.current = false; return;
      }
      const disarmedOk = await waitForArmedState(false, 5000);
      if (cancelledRef.current) return;
      if (!disarmedOk) {
        addLog('DISARM STATE: TIMEOUT — telemetría no confirmó desarmado en 5s', 'error');
        setState('ERROR'); runningRef.current = false; return;
      }
      addLog('DISARM STATE: DISARMED (confirmado por telemetría real)', 'real');
    } else {
      addLog('DISARM: NO solicitado por el usuario — el dron permanece armado', 'sim');
    }
    addLog('MISSION COMPLETE', 'sim');
    setState('FINAL');
    runningRef.current = false;
  }, [canStart, mode, points, elevateM, descendM, disarmAtEnd, timeoutS, gpsStallS, cruiseAlt,
      armDrone, takeoff, navGoto, sendCommand, disarmDrone, addLog]);

  // Salvaguarda: si el operador navega a otra pestaña con la misión corriendo.
  useEffect(() => {
    return () => {
      if (runningRef.current) {
        cancelledRef.current = true;
        confirmResolverRef.current?.();
        armedResolverRef.current?.resolve();
        try { setJoystick(0.5, 0, 0, 0); } catch { /* best effort */ }
        navStop().catch(() => {});
        disarmDrone().catch(() => {});
      }
    };
  }, [navStop, disarmDrone, setJoystick]);

  const showAbort = state !== 'IDLE' && state !== 'FINAL';
  const currentPoint = currentPointIdx >= 0 ? points[currentPointIdx] : null;
  const nextPoint = currentPointIdx >= 0 && currentPointIdx + 1 < points.length ? points[currentPointIdx + 1] : null;
  const realTelemetryAvailable = connected && !demoMode;
  const gpsPoints = points.filter((p): p is GpsPoint => p.kind === 'GPS');
  const routeCoords = gpsPoints.map(p => ({ latitude: p.lat, longitude: p.lon }));

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}>
      <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
        <Text style={styles.title}>🧭 VUELO AUTÓNOMO</Text>
        <Text style={styles.subtitle}>ARM → ELEVAR → RUTA → DESCENDER → DESARMAR</Text>
      </View>

      {demoMode && (
        <View style={styles.warnBanner}>
          <Text style={styles.warnText}>⚠ Modo DEMO activo — conectate al dron real para iniciar la misión.</Text>
        </View>
      )}

      {/* ── MISSION STATUS ───────────────────────────────────────────── */}
      <View style={styles.panel}>
        <Text style={styles.panelTitle}>MISSION STATUS</Text>
        <StatusRow label="Mode" value={mode === 'TEST' ? 'AUTONOMOUS TEST' : 'AUTONOMOUS GPS'} />
        <StatusRow label="State" value={state} highlight={state === 'ERROR' ? C.danger : undefined} />
        <StatusRow label="ARMED" value={telemetry.armed ? '✓' : '—'} highlight={telemetry.armed ? C.success : undefined} />
        <StatusRow label="ALTITUDE" value={altitudeReady ? '✓' : '—'} highlight={altitudeReady ? C.success : undefined} />
        <StatusRow label="CURRENT" value={currentPoint ? `${describePoint(currentPoint)} (${currentPointIdx + 1}/${points.length})` : '—'} />
        <StatusRow label="NEXT" value={nextPoint ? describePoint(nextPoint) : '—'} />
        <StatusRow label="COMMAND" value={commandLabel || '—'} />
        <StatusRow label="COMMAND STATUS" value={commandStatus || '—'} />
        {mode === 'TEST' && (
          <>
            <StatusRow label="POSITION" value="TEST / NOT REAL" />
            <StatusRow label="MOTOR OUTPUT" value={commandStatus === 'ACTIVE' ? 'ACTIVE (comando RC real enviado)' : 'IDLE'} />
          </>
        )}
        {waitSecondsLeft !== null && (
          <View style={styles.confirmBox}>
            <Text style={styles.confirmText}>Confirmación de prueba en {waitSecondsLeft}s…</Text>
            <TouchableOpacity style={styles.confirmBtn} onPress={confirmNow}>
              <Text style={styles.confirmBtnText}>✅ Confirmar ahora</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* ── Telemetría real de referencia ────────────────────────────── */}
      <View style={styles.panel}>
        <Text style={styles.panelTitle}>TELEMETRÍA REAL</Text>
        <StatusRow label="ARM STATE" value={telemetry.armed ? 'ARMED' : 'DISARMED'} highlight={telemetry.armed ? C.success : C.textDim} />
        <StatusRow label="REAL ALTITUDE" value={realTelemetryAvailable ? `${telemetry.altitude.toFixed(2)} m` : 'NOT AVAILABLE'} />
        <StatusRow label="REAL POSITION" value={realTelemetryAvailable && (telemetry.latitude || telemetry.longitude) ? `${telemetry.latitude.toFixed(6)}, ${telemetry.longitude.toFixed(6)}` : 'NOT AVAILABLE'} />
        <StatusRow label="REAL DISTANCE" value="NOT AVAILABLE" />
      </View>

      {/* ── Configuración ─────────────────────────────────────────────── */}
      {!showAbort && (
        <View style={styles.panel}>
          <Text style={styles.panelTitle}>CONFIGURACIÓN</Text>

          <View style={styles.modeToggle}>
            <TouchableOpacity style={[styles.modeBtn, mode === 'TEST' && styles.modeBtnActive]} onPress={() => setMode('TEST')}>
              <Text style={[styles.modeBtnText, mode === 'TEST' && styles.modeBtnTextActive]}>TEST</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.modeBtn, mode === 'GPS' && styles.modeBtnActive]} onPress={() => setMode('GPS')}>
              <Text style={[styles.modeBtnText, mode === 'GPS' && styles.modeBtnTextActive]}>GPS</Text>
            </TouchableOpacity>
          </View>

          {mode === 'TEST' && (
            <TouchableOpacity style={styles.checkboxRow} onPress={() => setPropsConfirmed(v => !v)} activeOpacity={0.7}>
              <View style={[styles.checkbox, propsConfirmed && styles.checkboxChecked]}>
                {propsConfirmed && <Text style={styles.checkboxMark}>✓</Text>}
              </View>
              <Text style={styles.checkboxLabel}>Confirmo que las hélices están retiradas</Text>
            </TouchableOpacity>
          )}

          <View style={styles.rowPair}>
            <View style={styles.rowHalf}>
              <Text style={styles.fieldLabel}>Elevar (m)</Text>
              <TextInput style={styles.input} keyboardType="numeric" value={elevateM} onChangeText={setElevateM} />
            </View>
            <View style={styles.rowHalf}>
              <Text style={styles.fieldLabel}>Descender (m)</Text>
              <TextInput style={styles.input} keyboardType="numeric" value={descendM} onChangeText={setDescendM} />
            </View>
          </View>

          {mode === 'TEST' ? (
            <>
              <View style={styles.rowPair}>
                <View style={styles.rowHalf}>
                  <Text style={styles.fieldLabel}>Timeout confirmación (s)</Text>
                  <TextInput style={styles.input} keyboardType="numeric" value={timeoutS} onChangeText={setTimeoutS} />
                </View>
                <View style={styles.rowHalf}>
                  <Text style={styles.fieldLabel}>Duración pulso RC (s)</Text>
                  <TextInput style={styles.input} keyboardType="numeric" value={pulseSeconds} onChangeText={setPulseSeconds} />
                </View>
              </View>
              <View style={styles.row}>
                <Text style={styles.fieldLabel}>Deflexión del pulso RC (0.1–0.8)</Text>
                <TextInput style={styles.input} keyboardType="numeric" value={pulseStrength} onChangeText={setPulseStrength} />
              </View>
            </>
          ) : (
            <View style={styles.row}>
              <Text style={styles.fieldLabel}>Timeout de bloqueo GPS (s) — nunca marca éxito, solo detecta que algo se trabó</Text>
              <TextInput style={styles.input} keyboardType="numeric" value={gpsStallS} onChangeText={setGpsStallS} />
            </View>
          )}

          <TouchableOpacity style={styles.checkboxRow} onPress={() => setDisarmAtEnd(v => !v)} activeOpacity={0.7}>
            <View style={[styles.checkbox, disarmAtEnd && styles.checkboxChecked]}>
              {disarmAtEnd && <Text style={styles.checkboxMark}>✓</Text>}
            </View>
            <Text style={styles.checkboxLabel}>Desarmar al finalizar</Text>
          </TouchableOpacity>

          {/* ── Ruta ── */}
          <Text style={[styles.panelTitle, { marginTop: 6 }]}>RUTA — {points.length} punto(s)</Text>

          {mode === 'TEST' ? (
            <View style={styles.cardinalGrid}>
              {CARDINAL_ORDER.map(dir => (
                <TouchableOpacity key={dir} style={styles.cardinalBtn} onPress={() => addCardinalPoint(dir)}>
                  <Text style={styles.cardinalBtnText}>{dir}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : (
            <View style={styles.mapWrap}>
              <MapView
                style={styles.map}
                initialRegion={{
                  latitude: telemetry.latitude || 4.711,
                  longitude: telemetry.longitude || -74.0721,
                  latitudeDelta: 0.005, longitudeDelta: 0.005,
                }}
                onPress={handleMapPress}
              >
                {telemetry.latitude !== 0 && telemetry.longitude !== 0 && (
                  <Marker coordinate={{ latitude: telemetry.latitude, longitude: telemetry.longitude }} pinColor={C.cyan} title="Dron" />
                )}
                {gpsPoints.map(p => (
                  <Marker key={p.id} coordinate={{ latitude: p.lat, longitude: p.lon }} title={`P${p.label}`} />
                ))}
                {routeCoords.length >= 2 && <Polyline coordinates={routeCoords} strokeColor={C.primary} strokeWidth={2} />}
              </MapView>
              <Text style={styles.mapHint}>Tocá el mapa para agregar puntos en orden</Text>
            </View>
          )}

          {points.map((p, i) => (
            <View key={p.id} style={styles.cmdRow}>
              <Text style={styles.cmdRowText}>{i + 1}. {describePoint(p)}</Text>
              <TouchableOpacity onPress={() => removePoint(p.id)}>
                <Text style={styles.cmdRowRemove}>✕</Text>
              </TouchableOpacity>
            </View>
          ))}

          <View style={styles.actionsRow}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={clearRoute} disabled={points.length === 0}>
              <Text style={styles.secondaryBtnText}>🧹 LIMPIAR RUTA</Text>
            </TouchableOpacity>
            {mode === 'GPS' && startPos && (
              <TouchableOpacity style={styles.secondaryBtn} onPress={returnToStart}>
                <Text style={styles.secondaryBtnText}>⤺ VOLVER AL INICIO</Text>
              </TouchableOpacity>
            )}
          </View>

          <TouchableOpacity style={[styles.startBtn, !canStart && styles.startBtnDisabled]} disabled={!canStart} onPress={runMission}>
            <Text style={styles.startBtnText}>▶ INICIAR MISIÓN</Text>
          </TouchableOpacity>
        </View>
      )}

      {showAbort && (
        <TouchableOpacity style={styles.abortBtn} onPress={abort}>
          <Text style={styles.abortBtnText}>⛔ DETENER</Text>
        </TouchableOpacity>
      )}

      {/* ── Log ──────────────────────────────────────────────────────── */}
      <View style={styles.panel}>
        <Text style={styles.panelTitle}>REGISTRO DE COMANDOS</Text>
        {log.length === 0 ? (
          <Text style={styles.emptyLog}>Sin actividad — iniciá una misión para ver el registro.</Text>
        ) : (
          <FlatList
            data={log}
            keyExtractor={item => item.id}
            scrollEnabled={false}
            renderItem={({ item }) => (
              <View style={styles.logRow}>
                <Text style={styles.logTime}>{new Date(item.time).toLocaleTimeString('es-CO', TIME_OPTS)}</Text>
                <Text style={[styles.logText, item.kind === 'sim' && { color: C.warning }, item.kind === 'error' && { color: C.danger }]}>
                  {item.text}
                </Text>
              </View>
            )}
          />
        )}
      </View>
    </ScrollView>
  );
};

/** Fallback de altitud de crucero si aún no se registró (no debería usarse en la práctica). */
const targetAltFallback = (current: number) => current;

const StatusRow: React.FC<{ label: string; value: string; highlight?: string }> = ({ label, value, highlight }) => (
  <View style={styles.statusRow}>
    <Text style={styles.statusLabel}>{label}</Text>
    <Text style={[styles.statusValue, highlight ? { color: highlight } : null]}>{value}</Text>
  </View>
);

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 18, paddingBottom: 10 },
  title: { fontSize: 18, fontWeight: '900', color: C.text, letterSpacing: 1 },
  subtitle: { fontSize: 11, color: C.textMuted, marginTop: 2, fontWeight: '700' },

  warnBanner: {
    marginHorizontal: 14, marginBottom: 10, padding: 10,
    backgroundColor: 'rgba(217,119,6,0.12)', borderRadius: 10,
    borderLeftWidth: 3, borderLeftColor: C.warning,
  },
  warnText: { color: C.warning, fontSize: 12, fontWeight: '700' },

  panel: {
    marginHorizontal: 14, marginBottom: 12, padding: 14,
    backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.hairline,
  },
  panelTitle: { fontSize: 10, fontWeight: '800', letterSpacing: 1.5, color: C.textDim, marginBottom: 8 },

  statusRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: C.hairline,
  },
  statusLabel: { fontSize: 11, color: C.textMuted, fontWeight: '700' },
  statusValue: { fontSize: 12, color: C.text, fontWeight: '800', fontFamily: 'monospace', flexShrink: 1, textAlign: 'right' },

  confirmBox: {
    marginTop: 10, padding: 10, backgroundColor: C.primaryDim, borderRadius: 10,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
  },
  confirmText: { fontSize: 12, color: C.navy, fontWeight: '700', flexShrink: 1 },
  confirmBtn: { backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  confirmBtnText: { color: '#fff', fontSize: 11, fontWeight: '800' },

  modeToggle: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  modeBtn: { flex: 1, paddingVertical: 8, borderRadius: 8, borderWidth: 1.5, borderColor: C.hairlineStrong, alignItems: 'center' },
  modeBtnActive: { backgroundColor: C.primaryDim, borderColor: C.primary },
  modeBtnText: { fontSize: 11, fontWeight: '800', color: C.textMuted },
  modeBtnTextActive: { color: C.primary },

  checkboxRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  checkbox: { width: 22, height: 22, borderRadius: 6, borderWidth: 2, borderColor: C.hairlineStrong, alignItems: 'center', justifyContent: 'center' },
  checkboxChecked: { backgroundColor: C.success, borderColor: C.success },
  checkboxMark: { color: '#fff', fontWeight: '900', fontSize: 13 },
  checkboxLabel: { fontSize: 12, color: C.text, fontWeight: '700', flexShrink: 1 },

  row: { marginBottom: 10 },
  rowPair: { flexDirection: 'row', gap: 10, marginBottom: 10 },
  rowHalf: { flex: 1 },
  fieldLabel: { fontSize: 10, color: C.textDim, fontWeight: '700', marginBottom: 4 },
  input: {
    borderWidth: 1, borderColor: C.hairline, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8,
    fontSize: 13, color: C.text, backgroundColor: C.bg,
  },

  cardinalGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  cardinalBtn: {
    width: '22%', paddingVertical: 12, borderRadius: 10, borderWidth: 1.5, borderColor: C.primary,
    backgroundColor: C.primaryDim, alignItems: 'center',
  },
  cardinalBtnText: { fontSize: 12, fontWeight: '900', color: C.primary },

  mapWrap: { marginBottom: 10 },
  map: { width: '100%', height: 220, borderRadius: 12 },
  mapHint: { fontSize: 10, color: C.textDim, marginTop: 4, textAlign: 'center' },

  cmdRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.hairline,
  },
  cmdRowText: { fontSize: 11, color: C.text, flexShrink: 1 },
  cmdRowRemove: { color: C.danger, fontWeight: '900', fontSize: 14, paddingHorizontal: 6 },

  actionsRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  secondaryBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, borderWidth: 1.5, borderColor: C.hairlineStrong, alignItems: 'center' },
  secondaryBtnText: { fontSize: 10, fontWeight: '800', color: C.textMuted },

  startBtn: { marginTop: 12, backgroundColor: C.success, paddingVertical: 14, borderRadius: 10, alignItems: 'center' },
  startBtnDisabled: { backgroundColor: C.hairlineStrong },
  startBtnText: { color: '#fff', fontSize: 13, fontWeight: '900', letterSpacing: 1 },

  abortBtn: { marginHorizontal: 14, marginBottom: 12, backgroundColor: C.danger, paddingVertical: 14, borderRadius: 10, alignItems: 'center' },
  abortBtnText: { color: '#fff', fontSize: 13, fontWeight: '900', letterSpacing: 1 },

  emptyLog: { fontSize: 12, color: C.textDim, fontStyle: 'italic' },
  logRow: { flexDirection: 'row', gap: 8, paddingVertical: 4, borderBottomWidth: 1, borderBottomColor: C.hairline },
  logTime: { fontSize: 10, color: C.textDim, fontFamily: 'monospace', width: 62 },
  logText: { fontSize: 11, color: C.text, flexShrink: 1, fontFamily: 'monospace' },
});
