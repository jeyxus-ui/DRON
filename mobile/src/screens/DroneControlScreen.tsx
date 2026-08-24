import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  StyleSheet,
  useWindowDimensions,
  TouchableOpacity,
  Text,
  StatusBar,
  Alert,
  SafeAreaView,
  Animated,
  ScrollView,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { DualJoystick } from '../components/DualJoystick';
import { FlightController, DEFAULT_FLIGHT_CONFIG, toRcOverride, StickInput } from '../utils/flightControls';
import { useDrone } from '../context/DroneContext';
import { useDeviceLocation } from '../hooks/useDeviceLocation';
import { getApiUrl, setHostIp } from '../config';
import { authFetch } from '../utils/authFetch';
import { getStoredIp } from '../utils/ipConfig';
import { IpConfigModal } from '../components/IpConfigModal';
import { theme } from '../theme';

const C = theme.colors;
const BG = C.bg;
const AMBER = C.primary;
const YELLOW = C.warning;
const RED = C.danger;
const LABEL = C.textMuted;
const BORDER = C.hairline;
const GLASS_BORDER = C.hairlineStrong;

const MODE_META: Record<string, { color: string; icon: string; desc: string; requiresGPS?: boolean }> = {
  STABILIZE: { color: AMBER, icon: '◈', desc: 'Control manual' },
  ALT_HOLD: { color: '#0EA5E9', icon: '⇳', desc: 'Altura automática' },
  LOITER: { color: '#0891B2', icon: '⊙', desc: 'Posición fija GPS', requiresGPS: true },
  POSHOLD: { color: '#0D9488', icon: '⊕', desc: 'Posición + altitud', requiresGPS: true },
  AUTO: { color: '#7C3AED', icon: '⟳', desc: 'Misión automática', requiresGPS: true },
  GUIDED: { color: '#9333EA', icon: '➤', desc: 'Control GCS', requiresGPS: true },
  RTL: { color: '#EA580C', icon: '⌂', desc: 'Retorno a casa', requiresGPS: true },
  LAND: { color: '#D97706', icon: '↓', desc: 'Aterrizaje automático' },
  CIRCLE: { color: '#4F46E5', icon: '○', desc: 'Círculo', requiresGPS: true },
  BRAKE: { color: '#DC2626', icon: '⊗', desc: 'Freno GPS', requiresGPS: true },
  SPORT: { color: '#CA8A04', icon: '⚡', desc: 'Velocidad mejorada' },
  ACRO: { color: '#E11D48', icon: '✦', desc: 'Acrobático' },
  DRIFT: { color: '#DB2777', icon: '〜', desc: 'Vuelo tipo avión' },
  FLIP: { color: '#C026D3', icon: '↺', desc: 'Flips' },
  THROW: { color: '#F59E0B', icon: '⤴', desc: 'Lanzamiento' },
  SMARTRTL: { color: '#F97316', icon: '⟲', desc: 'RTL inteligente', requiresGPS: true },
};

const getMeta = (mode: string) => MODE_META[mode] ?? { color: C.textMuted, icon: '?', desc: '?' };

const MODE_GROUPS = [
  { label: 'MANUAL', modes: ['STABILIZE', 'ACRO', 'SPORT', 'DRIFT'] },
  { label: 'ASISTIDO', modes: ['ALT_HOLD', 'POSHOLD', 'LOITER', 'BRAKE'] },
  { label: 'AUTOMÁTICO', modes: ['AUTO', 'GUIDED', 'CIRCLE', 'FLIP', 'THROW'] },
  { label: 'EMERGENCIA / RETORNO', modes: ['RTL', 'SMARTRTL', 'LAND'] },
];

export const DroneControlScreen: React.FC = () => {
  const { telemetry, connected, demoMode, armDrone, disarmDrone, setJoystick, sendCommand, forceReconnect, pushError, maxAltitude, setMaxAltitude, maxSpeed, setMaxSpeed } =
    useDrone();
  const insets = useSafeAreaInsets();
  const { width: winW, height: winH } = useWindowDimensions();
  const isLandscape = winW > winH;
  const refDim = Math.min(winW, winH);
  const joySize = isLandscape ? refDim * 0.36 : refDim * 0.18;
  const panelWidth = winW * 0.72;

  const deviceLoc = useDeviceLocation();

  type CameraState = 'idle' | 'loading' | 'connected' | 'failed';
  const [cameraState, setCameraState] = useState<CameraState>('idle');
  const cameraKeyRef = useRef(0);
  const webViewRef = useRef<WebView>(null);
  const [ipModalVisible, setIpModalVisible] = useState(false);
  const [toastMsg, setToastMsg] = useState('');
  const toastTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectedRef = useRef(connected);
  connectedRef.current = connected;

  // simulated telemetry for fallback / smooth display
  const [sim, setSim] = useState({ spd: 0, alt: 0, bat: 100, yaw: 0, vs: 0 });
  const simRef = useRef(sim);

  useEffect(() => {
    const t = setInterval(() => {
      simRef.current = {
        spd: Math.max(0, simRef.current.spd + (Math.random() - 0.5) * 0.8),
        alt: Math.max(0, simRef.current.alt + (Math.random() - 0.45) * 0.3),
        bat: Math.max(0, simRef.current.bat - 0.1),
        yaw: (simRef.current.yaw + (Math.random() - 0.5) * 10 + 360) % 360,
        vs: Math.max(-0.5, Math.min(0.5, simRef.current.vs + (Math.random() - 0.5) * 0.2)),
      };
      setSim({ ...simRef.current });
    }, 1000);
    return () => {
      clearInterval(t);
      if (toastTimeout.current) clearTimeout(toastTimeout.current);
    };
  }, []);

  const getSpd = () => telemetry?.ground_speed ?? sim.spd;
  const getAlt = () => telemetry?.altitude ?? sim.alt;
  const getBat = () => telemetry?.battery_remaining ?? sim.bat;
  const getYaw = () => telemetry?.yaw ?? sim.yaw;
  const getVs = () => telemetry?.vertical_speed ?? sim.vs;

  const [panelOpen, setPanelOpen] = useState(false);
  const [leftJoystickReset, setLeftJoystickReset] = useState(false);
  const prevArmed = useRef<boolean>(false);

  const HOLD_ARM_SECONDS = 3;
  const [holdProgress, setHoldProgress] = useState(0);
  const lastLeftRef = useRef({ x: 0, y: -1 });
  const leftTouchActiveRef = useRef(false);
  const armTriggeredRef = useRef(false);
  const holdStartRef = useRef<number | null>(null);
  const holdTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const armedRef = useRef(false);

  useEffect(() => {
    const isArmed = telemetry?.armed ?? false;
    armedRef.current = isArmed;
    if (isArmed && !prevArmed.current) {
      setLeftJoystickReset(true);
      setTimeout(() => setLeftJoystickReset(false), 150);
    }
    if (isArmed) {
      if (holdTimerRef.current) {
        clearInterval(holdTimerRef.current);
        holdTimerRef.current = null;
      }
      holdStartRef.current = null;
      setHoldProgress(0);
    } else {
      armTriggeredRef.current = false;
    }
    prevArmed.current = isArmed;
  }, [telemetry?.armed]);

  const [normalizedValues, setNormalizedValues] = useState({ thrNorm: -1, yaw: 0, pitch: 0, roll: 0 });
  const toPWM = (v: number): number => Math.round(1500 + v * 500);
  const toThrottlePWM = (v: number): number => Math.round(1000 + v * 1000);
  // Usa PWM real del backend cuando está disponible; fallback a estimación local del joystick
  const pwmDisplay = {
    thr:   telemetry?.rc_throttle_pwm ?? toThrottlePWM((normalizedValues.thrNorm + 1) / 2),
    yaw:   telemetry?.rc_yaw_pwm      ?? toPWM(normalizedValues.yaw),
    pitch: telemetry?.rc_pitch_pwm    ?? toPWM(normalizedValues.pitch),
    roll:  telemetry?.rc_roll_pwm     ?? toPWM(normalizedValues.roll),
  };

  const fcRef = useRef<FlightController | null>(null);
  if (!fcRef.current) {
    fcRef.current = new FlightController(DEFAULT_FLIGHT_CONFIG);
    fcRef.current.onCommand = (cmd) => {
      const rc = toRcOverride(cmd);
      setJoystick(rc.throttle, rc.yaw, rc.pitch, rc.roll);
    };
  }
  const leftStickRef = useRef<StickInput>({ x: 0, y: -1 });
  const rightStickRef = useRef<StickInput>({ x: 0, y: 0 });
  fcRef.current?.setTargetSticks(leftStickRef.current, rightStickRef.current);
  useEffect(() => () => fcRef.current?.stop(), []);

  // animations
  const batteryBlink = useRef(new Animated.Value(1)).current;
  const panelX = useRef(new Animated.Value(-winW * 0.72)).current;
  const backdropOp = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const pct = getBat();
    if (pct < 20) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(batteryBlink, { toValue: 0.2, duration: 400, useNativeDriver: true }),
          Animated.timing(batteryBlink, { toValue: 1, duration: 400, useNativeDriver: true }),
        ]),
      ).start();
    } else {
      batteryBlink.setValue(1);
    }
  }, [telemetry?.battery_remaining, sim.bat]);

  const spd = getSpd();
  const alt = getAlt();
  const bat = getBat();
  const yaw = getYaw();
  const vs = getVs();
  const droneSat = telemetry?.satellites;
  const droneHdop = telemetry?.hdop;
  const gpsOk = (droneSat ?? 0) >= 6 && (droneHdop ?? 0) > 0 && (droneHdop ?? 0) < 2.0;

  const batColor = bat > 50 ? AMBER : bat > 20 ? YELLOW : RED;
  const altLimitReached = alt >= maxAltitude && maxAltitude > 0;
  const altColor = altLimitReached ? RED : alt > 0 ? AMBER : LABEL;

  const openPanel = () => {
    setPanelOpen(true);
    Animated.parallel([
      Animated.spring(panelX, { toValue: 0, useNativeDriver: true, tension: 65, friction: 11 }),
      Animated.timing(backdropOp, { toValue: 1, duration: 250, useNativeDriver: true }),
    ]).start();
  };

  const closePanel = () => {
    Animated.parallel([
      Animated.spring(panelX, { toValue: -panelWidth, useNativeDriver: true, tension: 65, friction: 11 }),
      Animated.timing(backdropOp, { toValue: 0, duration: 200, useNativeDriver: true }),
    ]).start(() => setPanelOpen(false));
  };

  const isHoldCondition = () =>
    leftTouchActiveRef.current &&
    !armedRef.current &&
    !armTriggeredRef.current &&
    connectedRef.current &&
    lastLeftRef.current.x >= -0.1 && lastLeftRef.current.x <= 0.1 &&
    lastLeftRef.current.y <= -0.85;

  const cancelHold = () => {
    holdStartRef.current = null;
    if (holdTimerRef.current) {
      clearInterval(holdTimerRef.current);
      holdTimerRef.current = null;
    }
    setHoldProgress(0);
  };

  const tickHold = () => {
    if (!isHoldCondition()) {
      cancelHold();
      return;
    }
    const started = holdStartRef.current ?? Date.now();
    holdStartRef.current = started;
    const pct = Math.min(1, (Date.now() - started) / (HOLD_ARM_SECONDS * 1000));
    setHoldProgress(pct);
    if (pct >= 1) {
      cancelHold();
      armTriggeredRef.current = true;
      fcRef.current?.resetToMin();
      armDrone().then(res => {
        if (!res.success) {
          armTriggeredRef.current = false;
          Alert.alert('Error', res.message);
        }
      });
    }
  };

  const evalHold = () => {
    if (isHoldCondition()) {
      if (!holdTimerRef.current) {
        holdStartRef.current = Date.now();
        setHoldProgress(0);
        holdTimerRef.current = setInterval(tickHold, 100);
      }
    } else {
      cancelHold();
    }
  };

  const handleLeftTouchActive = (active: boolean) => {
    leftTouchActiveRef.current = active;
    if (!active) cancelHold();
  };

  const handleLeftJoystick = (x: number, y: number) => {
    let thr = y;
    // Si se alcanzó el límite de altura, no permitir subir más (throttle > neutro)
    if (altLimitReached && thr > 0) {
      thr = 0;
    }
    leftStickRef.current = { x, y: thr };
    fcRef.current?.setTargetSticks(leftStickRef.current, rightStickRef.current);
    fcRef.current?.start();
    lastLeftRef.current = { x, y: thr };
    setNormalizedValues(prev => ({ ...prev, thrNorm: thr, roll: x }));
    evalHold();
  };

  const handleRightJoystick = (x: number, y: number) => {
    rightStickRef.current = { x, y };
    fcRef.current?.setTargetSticks(leftStickRef.current, rightStickRef.current);
    fcRef.current?.start();
    setNormalizedValues(prev => ({ ...prev, pitch: y, yaw: x }));
  };

  const runCommand = async (fn: () => Promise<{ success: boolean; message: string }>) => {
    const result = await fn();
    if (!result.success) Alert.alert('Error', result.message);
    return result;
  };

  const handleModeChange = (mode: string) => {
    const meta = getMeta(mode);
    if (meta.requiresGPS && !gpsOk) {
      Alert.alert('GPS insuficiente', `No se puede cambiar a ${mode}.\nSe requieren ≥6 satélites y HDOP < 2.0.`, [
        { text: 'OK', style: 'cancel' },
      ]);
      return;
    }
    Alert.alert('Cambiar modo', `¿Cambiar a ${mode}?\n${meta.desc}`, [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'Confirmar',
        onPress: async () => {
          closePanel();
          await runCommand(() => sendCommand('SET_MODE', { mode }));
        },
      },
    ]);
  };

  const handleKillAll = () => {
    Alert.alert('APAGAR TODO', '¿Detener motores, soltar controles y apagar cámara?', [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'KILL',
        style: 'destructive',
        onPress: async () => {
          fcRef.current?.resetToMin();
          leftStickRef.current = { x: 0, y: -1 };
          rightStickRef.current = { x: 0, y: 0 };
          try { await sendCommand('EMERGENCY', { action: 'STOP' }); } catch { /* ignore */ }
          try { await disarmDrone(); } catch { /* ignore */ }
          setCameraState('idle');
          cameraKeyRef.current += 1;
        },
      },
    ]);
  };

  const handleArmToggle = () => {
    if (telemetry?.armed) {
      Alert.alert('Desarmar', '¿Desarmar el dron?', [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Desarmar',
          style: 'destructive',
          onPress: async () => {
            closePanel();
            await runCommand(disarmDrone);
          },
        },
      ]);
    } else {
      Alert.alert('Armar', '¿Armar el dron?', [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Armar',
          onPress: async () => {
            closePanel();
            setJoystick(0, 0, 0, 0);
            await runCommand(armDrone);
          },
        },
      ]);
    }
  };

  const handleAction = (id: string) => {
    const gpsActions: Record<string, string> = { BRAKE: 'BRAKE', HOLD_POS: 'LOITER' };
    if (gpsActions[id]) {
      if (!gpsOk) {
        Alert.alert('GPS insuficiente', `No se puede activar ${id === 'BRAKE' ? 'FRENO' : 'HOLD POS'}.\nSe requieren ≥6 satélites y HDOP < 2.0.`, [
          { text: 'OK', style: 'cancel' },
        ]);
        return;
      }
      closePanel();
      runCommand(() => sendCommand('SET_MODE', { mode: gpsActions[id] }));
      return;
    }
    const map: Record<string, () => void> = {
      REBOOT: () =>
        Alert.alert('Reboot', '¿Reiniciar autopiloto?', [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Reiniciar', style: 'destructive', onPress: () => runCommand(() => sendCommand('REBOOT', {})) },
        ]),
    };
    map[id]?.();
  };

  const meta = getMeta(telemetry?.mode ?? 'UNKNOWN');

  const holdIndicator = holdProgress > 0 ? (
    <View style={styles.holdOverlay} pointerEvents="none">
      <View style={styles.holdTrack}>
        <View style={[styles.holdFill, { width: `${Math.round(holdProgress * 100)}%` }]} />
      </View>
      <Text style={styles.holdText}>
        MANTENER {Math.max(1, HOLD_ARM_SECONDS - Math.floor(holdProgress * HOLD_ARM_SECONDS))}s
      </Text>
    </View>
  ) : null;

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor={BG} />

      {!isLandscape && (
        <>
          {/* ── HEADER ── */}
          <View style={[styles.header, { paddingTop: insets.top + 4 }]}>
            <TouchableOpacity style={styles.headerLeft} onPress={openPanel} activeOpacity={0.7}>
              <Text style={styles.logo}>GCS</Text>
              <Text style={styles.logoSub}>v1.0</Text>
            </TouchableOpacity>
            <View style={styles.headerRight}>
              <TouchableOpacity onPress={() => setIpModalVisible(true)} activeOpacity={0.6} style={styles.ipBtn}>
                <Text style={styles.ipBtnIcon}>⚙</Text>
              </TouchableOpacity>
              <Text style={styles.headerTime}>{new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</Text>
              <TouchableOpacity
                style={[styles.headerArmBtn, telemetry?.armed ? styles.headerArmBtnArmed : { borderColor: 'rgba(255,255,255,0.45)' }]}
                onPress={handleArmToggle}
                activeOpacity={0.7}
              >
                <View style={[styles.headerArmDot, { backgroundColor: telemetry?.armed ? RED : C.surface }]} />
                <Text style={[styles.headerArmText, { color: telemetry?.armed ? RED : C.surface }]}>
                  {telemetry?.armed ? 'ARM' : 'STBY'}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.headerKillBtn}
                onPress={handleKillAll}
                activeOpacity={0.7}
              >
                <Text style={styles.headerKillText}>KILL</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* ── CAMERA + METRICS OVERLAY ── */}
          <View style={[styles.cameraSection, { height: winH * 0.35 }]}>
            <View style={styles.cameraContainer}>
              {cameraState === 'loading' ? (
                <View style={styles.cameraOff}>
                  <Text style={styles.cameraOffIcon}>CAM</Text>
                  <Text style={styles.cameraConnecting}>CONECTANDO…</Text>
                </View>
              ) : cameraState === 'connected' ? (
                <WebView
                  ref={webViewRef}
                  key={cameraKeyRef.current}
                  source={{ uri: `${getApiUrl()}/api/camera/view` }}
                  style={styles.cameraFeed}
                  scrollEnabled={false}
                  bounces={false}
                  javaScriptEnabled={true}
                  mediaPlaybackRequiresUserAction={false}
                  allowsInlineMediaPlayback={true}
                  onError={() => { setCameraState('failed'); pushError('CAM_ERROR', 'Error cargando feed de cámara', 'error'); }}
                  onHttpError={() => { setCameraState('failed'); pushError('CAM_HTTP_ERROR', 'Error HTTP en feed de cámara', 'error'); }}
                  onLoad={() => {}}
                  renderError={() => <View style={styles.cameraOff} />}
                />
              ) : (
                <View style={styles.cameraOff}>
                  <Text style={styles.cameraOffIcon}>CAM</Text>
                  <TouchableOpacity
                    style={styles.retryBtn}
                    onPress={() => {
                      setCameraState('loading');
                      authFetch(`${getApiUrl()}/api/camera/status`)
                        .then(r => r.ok ? r.json() : Promise.reject('HTTP ' + r.status))
                        .then(data => {
                          if (data.running && data.has_frame) {
                            setCameraState('connected');
                            cameraKeyRef.current++;
                            pushError('CAM_OK', 'Cámara conectada', 'info');
                          } else {
                            setCameraState('failed');
                            pushError('CAM_NOT_CONNECTED', 'No hay cámara conectada — verifica cable USB y drivers', 'error');
                          }
                        })
                        .catch(() => { setCameraState('failed'); pushError('CAM_NETWORK', 'Red no disponible para cámara', 'error'); });
                    }}
                    activeOpacity={0.7}
                  >
                    <Text style={styles.retryBtnText}>REINTENTAR</Text>
                  </TouchableOpacity>
                </View>
              )}
              {cameraState === 'connected' && (
                <View style={styles.metricChips}>
                  <View style={[styles.chip, { borderColor: AMBER + 'AA' }]}>
                    <Text style={styles.chipLabel}>CAM</Text>
                    <Text style={styles.chipValue}>OK</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: AMBER + 'AA' }]}>
                    <Text style={styles.chipLabel}>SPD</Text>
                    <Text style={styles.chipValue}>{spd.toFixed(1)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: altColor + 'AA' }]}>
                    <Text style={styles.chipLabel}>ALT</Text>
                    <Text style={[styles.chipValue, altLimitReached && { color: RED }]}>
                      {alt.toFixed(1)}{altLimitReached ? ' MAX' : ''}
                    </Text>
                  </View>
                  <View style={[styles.chip, { borderColor: batColor + 'AA' }]}>
                    <Text style={styles.chipLabel}>BAT</Text>
                    <Text style={styles.chipValue}>{bat.toFixed(0)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: AMBER + 'AA' }]}>
                    <Text style={styles.chipLabel}>YAW</Text>
                    <Text style={styles.chipValue}>{yaw.toFixed(0)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: (vs >= 0 ? AMBER : RED) + 'AA' }]}>
                    <Text style={styles.chipLabel}>V/S</Text>
                    <Text style={styles.chipValue}>{vs.toFixed(1)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: connected ? AMBER + 'AA' : RED + 'AA' }]}>
                    <Text style={styles.chipLabel}>LINK</Text>
                    <Text style={styles.chipValue}>{connected ? 'OK' : 'NO'}</Text>
                  </View>
                </View>
              )}
            </View>
          </View>
        </>
      )}

      {isLandscape && (
        <View style={styles.landscapeBody}>
          {/* ── CAMARA FULL SCREEN ── */}
          <View style={StyleSheet.absoluteFill} pointerEvents="none">
            <View style={styles.cameraContainer}>
              {cameraState === 'loading' ? (
                <View style={styles.cameraOff}>
                  <Text style={styles.cameraOffIcon}>CAM</Text>
                  <Text style={styles.cameraConnecting}>CONECTANDO…</Text>
                </View>
              ) : cameraState === 'connected' ? (
                <WebView
                  ref={webViewRef}
                  key={cameraKeyRef.current}
                  source={{ uri: `${getApiUrl()}/api/camera/view` }}
                  style={styles.cameraFeed}
                  scrollEnabled={false}
                  bounces={false}
                  javaScriptEnabled={true}
                  mediaPlaybackRequiresUserAction={false}
                  allowsInlineMediaPlayback={true}
                  onError={() => { setCameraState('failed'); pushError('CAM_ERROR', 'Error cargando feed de cámara', 'error'); }}
                  onHttpError={() => { setCameraState('failed'); pushError('CAM_HTTP_ERROR', 'Error HTTP en feed de cámara', 'error'); }}
                  onLoad={() => {}}
                  renderError={() => <View style={styles.cameraOff} />}
                />
              ) : (
                <View style={styles.cameraOff}>
                  <Text style={styles.cameraOffIcon}>CAM</Text>
                  <TouchableOpacity
                    style={styles.retryBtn}
                    onPress={() => {
                      setCameraState('loading');
                      authFetch(`${getApiUrl()}/api/camera/status`)
                        .then(r => r.ok ? r.json() : Promise.reject('HTTP ' + r.status))
                        .then(data => {
                          if (data.running && data.has_frame) {
                            setCameraState('connected');
                            cameraKeyRef.current++;
                            pushError('CAM_OK', 'Cámara conectada', 'info');
                          } else {
                            setCameraState('failed');
                            pushError('CAM_NOT_CONNECTED', 'No hay cámara conectada — verifica cable USB y drivers', 'error');
                          }
                        })
                        .catch(() => { setCameraState('failed'); pushError('CAM_NETWORK', 'Red no disponible para cámara', 'error'); });
                    }}
                    activeOpacity={0.7}
                  >
                    <Text style={styles.retryBtnText}>REINTENTAR</Text>
                  </TouchableOpacity>
                </View>
              )}
              {cameraState === 'connected' && (
                <View style={[styles.metricChipsLandscape]}>
                  <View style={[styles.chip, { borderColor: AMBER + 'AA' }]}>
                    <Text style={styles.chipLabel}>CAM</Text>
                    <Text style={styles.chipValue}>OK</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: AMBER + 'AA' }]}>
                    <Text style={styles.chipLabel}>SPD</Text>
                    <Text style={styles.chipValue}>{spd.toFixed(1)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: altColor + 'AA' }]}>
                    <Text style={styles.chipLabel}>ALT</Text>
                    <Text style={[styles.chipValue, altLimitReached && { color: RED }]}>
                      {alt.toFixed(1)}{altLimitReached ? ' MAX' : ''}
                    </Text>
                  </View>
                  <View style={[styles.chip, { borderColor: batColor + 'AA' }]}>
                    <Text style={styles.chipLabel}>BAT</Text>
                    <Text style={styles.chipValue}>{bat.toFixed(0)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: AMBER + 'AA' }]}>
                    <Text style={styles.chipLabel}>YAW</Text>
                    <Text style={styles.chipValue}>{yaw.toFixed(0)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: (vs >= 0 ? AMBER : RED) + 'AA' }]}>
                    <Text style={styles.chipLabel}>V/S</Text>
                    <Text style={styles.chipValue}>{vs.toFixed(1)}</Text>
                  </View>
                  <View style={[styles.chip, { borderColor: connected ? AMBER + 'AA' : RED + 'AA' }]}>
                    <Text style={styles.chipLabel}>LINK</Text>
                    <Text style={styles.chipValue}>{connected ? 'OK' : 'NO'}</Text>
                  </View>
                </View>
              )}
            </View>
          </View>

          {/* ── HEADER OVERLAY ── */}
          <View style={[styles.headerLandscape, { paddingTop: insets.top + 2 }]}>
            <TouchableOpacity onPress={openPanel} activeOpacity={0.7}>
              <Text style={styles.logo}>GCS</Text>
            </TouchableOpacity>
            <Text style={styles.headerTime}>{new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}</Text>
            <TouchableOpacity
              style={[styles.headerArmBtn, telemetry?.armed ? styles.headerArmBtnArmed : { borderColor: 'rgba(255,255,255,0.45)' }]}
              onPress={handleArmToggle}
              activeOpacity={0.7}
            >
              <View style={[styles.headerArmDot, { backgroundColor: telemetry?.armed ? RED : C.surface }]} />
              <Text style={[styles.headerArmText, { color: telemetry?.armed ? RED : C.surface }]}>
                {telemetry?.armed ? 'ARM' : 'STBY'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.headerKillBtn}
              onPress={handleKillAll}
              activeOpacity={0.7}
            >
              <Text style={styles.headerKillText}>KILL</Text>
            </TouchableOpacity>
          </View>

          {/* ── JOYSTICKS LANDSCAPE ── */}
          <View style={styles.joystickSectionLandscape}>
            <DualJoystick
              onLeftMove={handleLeftJoystick}
              onRightMove={handleRightJoystick}
              onLeftTouchActive={handleLeftTouchActive}
              leftSize={joySize}
              rightSize={joySize}
              leftColor={AMBER}
              rightColor={C.cyan}
              leftResetToBottom={leftJoystickReset}
            />
            {holdIndicator}
          </View>

          {/* ── BOTTOM LANDSCAPE ── */}
          <View style={styles.bottomBarLandscape}>
            <View style={styles.bottomLeft}>
              <View style={[styles.statusDot, { backgroundColor: connected ? AMBER : RED }]} />
              <Text style={[styles.bottomText, { color: C.surface }]}>{connected ? 'CTD' : 'OFF'}</Text>
            </View>
            <Text style={[styles.modeText, { color: meta.color }]}>
              {meta.icon} {telemetry?.mode ?? '—'}
            </Text>
            <View style={styles.bottomRight}>
              <View style={[styles.armDot, { backgroundColor: telemetry?.armed ? RED : C.surface }]} />
              <Text style={[styles.bottomText, { color: telemetry?.armed ? RED : C.surface }]}>{telemetry?.armed ? 'ARM' : 'SBY'}</Text>
            </View>
          </View>
        </View>
      )}

      {!isLandscape && (
        <>
          {/* ── JOYSTICKS ── */}
          <View style={styles.joystickSection}>
            <DualJoystick
              onLeftMove={handleLeftJoystick}
              onRightMove={handleRightJoystick}
              onLeftTouchActive={handleLeftTouchActive}
              leftSize={joySize}
              rightSize={joySize}
              leftColor={AMBER}
              rightColor={C.cyan}
              leftResetToBottom={leftJoystickReset}
            />
            {holdIndicator}
            <View style={styles.pwmContainer}>
              <View style={styles.pwmCol}>
                <Text style={styles.joystickLabel}>THR / YAW</Text>
                <View style={styles.pwmRow}>
                  <View style={[styles.pwmChip, { borderColor: BORDER }]}>
                    <Text style={styles.pwmLabel}>THR</Text>
                    <Text style={[styles.pwmValue, {
                      color: pwmDisplay.thr >= 1800 ? RED : pwmDisplay.thr >= 1500 ? AMBER : pwmDisplay.thr >= 1200 ? YELLOW : LABEL,
                    }]}>
                      {pwmDisplay.thr}
                    </Text>
                  </View>
                  <View style={[styles.pwmChip, { borderColor: BORDER }]}>
                    <Text style={styles.pwmLabel}>YAW</Text>
                    <Text style={[styles.pwmValue, { color: pwmDisplay.yaw !== 1500 ? YELLOW : LABEL }]}>
                      {pwmDisplay.yaw}
                    </Text>
                  </View>
                </View>
              </View>
              <View style={styles.pwmCol}>
                <Text style={styles.joystickLabel}>PITCH / ROLL</Text>
                <View style={styles.pwmRow}>
                  <View style={[styles.pwmChip, { borderColor: BORDER }]}>
                    <Text style={styles.pwmLabel}>PIT</Text>
                    <Text style={[styles.pwmValue, { color: pwmDisplay.pitch !== 1500 ? C.cyan : LABEL }]}>
                      {pwmDisplay.pitch}
                    </Text>
                  </View>
                  <View style={[styles.pwmChip, { borderColor: BORDER }]}>
                    <Text style={styles.pwmLabel}>RLL</Text>
                    <Text style={[styles.pwmValue, { color: pwmDisplay.roll !== 1500 ? C.cyan : LABEL }]}>
                      {pwmDisplay.roll}
                    </Text>
                  </View>
                </View>
              </View>
            </View>
          </View>

          {/* ── BOTTOM STATUS ── */}
          <View style={styles.bottomBar}>
            <View style={styles.bottomLeft}>
              <View style={[styles.statusDot, { backgroundColor: connected ? AMBER : RED }]} />
              <Text style={styles.bottomText}>
                {connected ? 'CONECTADO' : 'DESCONECTADO'}
              </Text>
            </View>
            <Text style={[styles.modeText, { color: meta.color }]}>
              {meta.icon} {telemetry?.mode ?? '—'}
            </Text>
            <View style={styles.bottomRight}>
              <View style={[styles.armDot, { backgroundColor: telemetry?.armed ? RED : LABEL }]} />
              <Text style={[styles.bottomText, { color: telemetry?.armed ? RED : LABEL }]}>
                {telemetry?.armed ? 'ARMADO' : 'STAND-BY'}
              </Text>
            </View>
            {demoMode && (
              <View style={styles.demoBadge}>
                <Text style={styles.demoBadgeText}>DEMO</Text>
              </View>
            )}
          </View>
        </>
      )}

      {/* ── SIDE PANEL ── */}
      {panelOpen && (
        <Animated.View style={[styles.backdrop, { opacity: backdropOp }]}>
          <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={closePanel} />
        </Animated.View>
      )}

      <Animated.View style={[styles.sidePanel, { width: panelWidth, transform: [{ translateX: panelX }] }]}>
        <View style={[styles.panelHeader, { paddingTop: insets.top + 12 }]}>
          <View>
            <Text style={styles.panelTitle}>GCS CONTROL</Text>
            <Text style={styles.panelSubtitle}>ArduPilot · {telemetry?.mode ?? '—'}</Text>
          </View>
          <TouchableOpacity onPress={closePanel} style={styles.closeBtn} activeOpacity={0.75}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.panelScroll} showsVerticalScrollIndicator={false}>
          <Text style={styles.sectionLabel}>ACCIONES RÁPIDAS</Text>

          <TouchableOpacity
            style={[styles.armBigBtn, telemetry?.armed
              ? { backgroundColor: RED + '1A', borderColor: RED + 'AA' }
              : { backgroundColor: C.success + '1A', borderColor: C.success + 'AA' }]}
            onPress={handleArmToggle}
            activeOpacity={0.75}
          >
            <Text style={[styles.armBigIcon, { color: telemetry?.armed ? RED : AMBER }]}>
              {telemetry?.armed ? '🔒' : '⚡'}
            </Text>
            <View style={{ flex: 1 }}>
              <Text style={[styles.armBigLabel, { color: telemetry?.armed ? RED : AMBER }]}>
                {telemetry?.armed ? 'DESARMAR DRON' : 'ARMAR DRON'}
              </Text>
              <Text style={styles.armBigDesc}>
                {telemetry?.armed ? 'Armado — toca para desarmar' : 'Stand-by — toca para armar'}
              </Text>
            </View>
          </TouchableOpacity>

          <View style={styles.quickGrid}>
            {[
              { id: 'BRAKE', label: 'FRENO', icon: '⊗', color: C.danger },
              { id: 'HOLD_POS', label: 'HOLD POS', icon: '⊙', color: C.teal },
              { id: 'REBOOT', label: 'REBOOT FC', icon: '↺', color: C.textMuted },
            ].map(a => (
              <TouchableOpacity
                key={a.id}
                style={[styles.quickBtn, { borderColor: a.color + '88', backgroundColor: a.color + '12' }]}
                onPress={() => handleAction(a.id)}
                activeOpacity={0.75}
              >
                <Text style={[styles.quickBtnIcon, { color: a.color }]}>{a.icon}</Text>
                <Text style={[styles.quickBtnLabel, { color: a.color }]}>{a.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {MODE_GROUPS.map(group => (
            <View key={group.label}>
              <Text style={styles.sectionLabel}>{group.label}</Text>
              <View style={styles.modeGroup}>
                {group.modes.map(modeName => {
                  const m = getMeta(modeName);
                  const isActive = (telemetry?.mode ?? '') === modeName;
                  return (
                    <TouchableOpacity
                      key={modeName}
                      style={[styles.modeBtn, {
                        borderColor: isActive ? m.color : m.color + '55',
                        backgroundColor: isActive ? m.color + '22' : m.color + '08',
                      }]}
                      onPress={() => handleModeChange(modeName)}
                      activeOpacity={0.75}
                    >
                      <View style={styles.modeBtnLeft}>
                        <Text style={[styles.modeBtnIcon, { color: m.color }]}>{m.icon}</Text>
                        <View>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                            <Text style={[styles.modeBtnName, { color: isActive ? m.color : C.text }]}>
                              {modeName}
                            </Text>
                            {m.requiresGPS && (
                              <View style={styles.gpsBadge}>
                                <Text style={styles.gpsBadgeText}>GPS</Text>
                              </View>
                            )}
                          </View>
                          <Text style={styles.modeBtnDesc}>{m.desc}</Text>
                        </View>
                      </View>
                      {isActive && <View style={[styles.activeModeDot, { backgroundColor: m.color }]} />}
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          ))}

          <Text style={styles.sectionLabel}>BATERÍA</Text>
          <View style={styles.batteryPanel}>
            <View style={styles.batteryTop}>
              <Text style={[styles.batteryPct, { color: batColor }]}>{bat.toFixed(0)}%</Text>
              <Text style={[styles.batteryV, { color: batColor + 'aa' }]}>
                {(telemetry?.battery_voltage ?? 0).toFixed(2)} V
              </Text>
            </View>
            <View style={styles.batteryBar}>
              <View style={[styles.batteryFill, { width: `${bat}%`, backgroundColor: batColor }]} />
            </View>
          </View>

          <Text style={styles.sectionLabel}>LÍMITES</Text>
          <View style={styles.limitsPanel}>
            <View style={styles.limitRow}>
              <Text style={styles.limitLabel}>ALTURA MÁX</Text>
              <View style={styles.limitControls}>
                <TouchableOpacity
                  style={styles.limitBtn}
                  onPress={() => setMaxAltitude(Math.max(1, maxAltitude - 1))}
                  activeOpacity={0.6}
                >
                  <Text style={styles.limitBtnText}>−</Text>
                </TouchableOpacity>
                <Text style={[styles.limitValue, altLimitReached && { color: RED }]}>
                  {maxAltitude} m
                </Text>
                <TouchableOpacity
                  style={styles.limitBtn}
                  onPress={() => setMaxAltitude(Math.min(500, maxAltitude + 1))}
                  activeOpacity={0.6}
                >
                  <Text style={styles.limitBtnText}>+</Text>
                </TouchableOpacity>
              </View>
            </View>
            <View style={styles.limitPresets}>
              {[3, 5, 10, 20].map(v => (
                <TouchableOpacity
                  key={v}
                  style={[styles.limitPreset, maxAltitude === v && { borderColor: AMBER, backgroundColor: AMBER + '22' }]}
                  onPress={() => setMaxAltitude(v)}
                  activeOpacity={0.6}
                >
                  <Text style={[styles.limitPresetText, maxAltitude === v && { color: AMBER }]}>
                    {v}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            {altLimitReached && (
              <View style={styles.limitWarning}>
                <Text style={styles.limitWarningText}>⚠ DRON EN ALTURA MÁXIMA</Text>
              </View>
            )}
          </View>

          <View style={{ height: 8 }} />

          <View style={styles.limitsPanel}>
            <View style={styles.limitRow}>
              <Text style={styles.limitLabel}>VELOCIDAD MÁX</Text>
              <View style={styles.limitControls}>
                <TouchableOpacity
                  style={styles.limitBtn}
                  onPress={() => setMaxSpeed(Math.max(0.05, +(maxSpeed - 0.05).toFixed(2)))}
                  activeOpacity={0.6}
                >
                  <Text style={styles.limitBtnText}>−</Text>
                </TouchableOpacity>
                <Text style={styles.limitValue}>
                  {Math.round(maxSpeed * 100)}%
                </Text>
                <TouchableOpacity
                  style={styles.limitBtn}
                  onPress={() => setMaxSpeed(Math.min(1, +(maxSpeed + 0.05).toFixed(2)))}
                  activeOpacity={0.6}
                >
                  <Text style={styles.limitBtnText}>+</Text>
                </TouchableOpacity>
              </View>
            </View>
            <View style={styles.limitPresets}>
              {[0.1, 0.2, 0.3, 0.5].map(v => (
                <TouchableOpacity
                  key={v}
                  style={[styles.limitPreset, maxSpeed === v && { borderColor: AMBER, backgroundColor: AMBER + '22' }]}
                  onPress={() => setMaxSpeed(v)}
                  activeOpacity={0.6}
                >
                  <Text style={[styles.limitPresetText, maxSpeed === v && { color: AMBER }]}>
                    {Math.round(v * 100)}%
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View style={{ height: 32 }} />
        </ScrollView>
      </Animated.View>

      {/* ── TOAST ── */}
      {toastMsg !== '' && (
        <View style={styles.toast}>
          <Text style={styles.toastText}>{toastMsg}</Text>
        </View>
      )}

      <IpConfigModal
        visible={ipModalVisible}
        onClose={async (changed) => {
          setIpModalVisible(false);
          if (changed) {
            const savedIp = await getStoredIp();
            setHostIp(savedIp);
            forceReconnect();
            setToastMsg(`🔄 Reconectando a ${savedIp}:8000…`);
            if (toastTimeout.current) clearTimeout(toastTimeout.current);
            toastTimeout.current = setTimeout(() => {
              const ok = connectedRef.current;
              setToastMsg(ok
                ? `✓ Conectado a ${savedIp}`
                : `✕ Error — no hay servidor en ${savedIp}:8000`);
              setTimeout(() => setToastMsg(''), 4000);
            }, 5000);
          }
        }}
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },

  // ── HEADER ──
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 8,
    borderBottomWidth: 1.5,
    borderBottomColor: C.navyElevated,
    backgroundColor: C.navy,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  logo: { color: C.surface, fontSize: 20, fontWeight: '900', letterSpacing: 3 },
  logoSub: { color: 'rgba(255,255,255,0.6)', fontSize: 10, fontWeight: '600' },
  headerTime: { color: C.surface, fontSize: 14, fontWeight: '700', fontFamily: 'monospace' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ipBtn: { padding: 4 },
  ipBtnIcon: { fontSize: 16, color: 'rgba(255,255,255,0.8)' },
  headerArmBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    borderWidth: 1.5, borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 4,
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderColor: 'rgba(255,255,255,0.35)',
  },
  headerArmBtnArmed: {
    borderColor: RED + 'AA',
    backgroundColor: RED + '1A',
  },
  headerArmDot: { width: 5, height: 5, borderRadius: 3 },
  headerArmText: { fontSize: 8, fontWeight: '900', letterSpacing: 1, fontFamily: 'monospace' },
  headerKillBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    borderWidth: 1.5, borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 4,
    backgroundColor: RED + '1A',
    borderColor: RED + 'AA',
  },
  headerKillText: { fontSize: 8, fontWeight: '900', letterSpacing: 1, fontFamily: 'monospace', color: RED },

  // ── CAMERA ──
  cameraSection: { borderWidth: 1.5, borderColor: GLASS_BORDER, borderRadius: 14, marginHorizontal: 2, overflow: 'hidden' },
  cameraContainer: { flex: 1, backgroundColor: '#000', position: 'relative' },
  cameraFeed: { width: '100%', height: '100%', backgroundColor: 'transparent' },
  cameraOff: {
    flex: 1, justifyContent: 'center', alignItems: 'center',
    backgroundColor: C.bg, gap: 12,
  },
  cameraOffIcon: { fontSize: 28, color: C.textDim, fontWeight: '900', letterSpacing: 2 },
  cameraConnecting: { color: C.textMuted, fontSize: 9, fontWeight: '700', letterSpacing: 1.5 },
  retryBtn: {
    borderWidth: 1.5, borderColor: AMBER + '66',
    borderRadius: 10, paddingHorizontal: 20, paddingVertical: 8,
    backgroundColor: AMBER + '15',
  },
  retryBtnText: { color: AMBER, fontSize: 9, fontWeight: '800', letterSpacing: 1.5 },

  // ── METRIC CHIPS ──
  metricChips: {
    position: 'absolute', bottom: 4, left: 4, right: 4,
    flexDirection: 'row', justifyContent: 'center', gap: 3,
  },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    backgroundColor: 'rgba(15,42,74,0.85)',
    borderWidth: 1, borderRadius: 8,
    paddingHorizontal: 6, paddingVertical: 3,
  },
  chipLabel: { color: 'rgba(255,255,255,0.7)', fontSize: 6, fontWeight: '700', letterSpacing: 0.6 },
  chipValue: { color: C.surface, fontSize: 8, fontWeight: '900', fontFamily: 'monospace' },

  // ── JOYSTICKS ──
  joystickSection: {
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 4,
    flex: 1,
  },
  holdOverlay: {
    position: 'absolute',
    left: '15%',
    top: '42%',
    width: 110,
    alignItems: 'center',
    gap: 4,
  },
  holdTrack: {
    width: '100%',
    height: 5,
    borderRadius: 3,
    backgroundColor: 'rgba(255,255,255,0.25)',
    overflow: 'hidden',
  },
  holdFill: {
    height: '100%',
    backgroundColor: C.primary,
  },
  holdText: {
    color: C.surface,
    fontSize: 7,
    fontWeight: '800',
    letterSpacing: 1,
  },
  joystickCol: { alignItems: 'center', gap: 3 },
  joystickLabel: { color: LABEL, fontSize: 7, fontWeight: '700', letterSpacing: 1.2 },
  pwmContainer: { flexDirection: 'row', marginTop: 4, gap: 20 },
  pwmCol: { alignItems: 'center', gap: 2 },
  pwmRow: { flexDirection: 'row', gap: 4 },
  pwmChip: {
    alignItems: 'center',
    backgroundColor: C.surface,
    borderRadius: 10, paddingHorizontal: 8, paddingVertical: 4,
    borderWidth: 1, borderColor: C.primary + '55',
  },
  pwmLabel: { color: LABEL, fontSize: 6, fontWeight: '800', letterSpacing: 0.8 },
  pwmValue: { fontSize: 9, fontWeight: '900', fontFamily: 'monospace' },

  // ── BOTTOM BAR ──
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderTopWidth: 1.5,
    borderTopColor: GLASS_BORDER,
    backgroundColor: C.surface,
  },
  bottomLeft: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  statusDot: { width: 5, height: 5, borderRadius: 3 },
  bottomText: { color: LABEL, fontSize: 8, fontWeight: '700', letterSpacing: 0.8 },
  modeText: { fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  bottomRight: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  armDot: { width: 5, height: 5, borderRadius: 3 },
  demoBadge: {
    backgroundColor: C.bgElevated, borderWidth: 1, borderColor: C.warning + '55',
    borderRadius: 6, paddingHorizontal: 5, paddingVertical: 2,
  },
  demoBadgeText: { color: YELLOW, fontSize: 6, fontWeight: '900', letterSpacing: 1 },

  // ── Side panel ──
  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 20 },
  sidePanel: {
    position: 'absolute', top: 0, bottom: 0, left: 0,
    backgroundColor: C.surface,
    borderRightWidth: 1.5, borderRightColor: C.hairlineStrong, zIndex: 30,
  },
  panelHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 18, paddingTop: 18, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: GLASS_BORDER },
  panelTitle: { color: C.text, fontSize: 16, fontWeight: '900', letterSpacing: 2 },
  panelSubtitle: { color: LABEL, fontSize: 9, fontWeight: '600', letterSpacing: 1, marginTop: 2 },
  closeBtn: { width: 30, height: 30, borderRadius: 15, backgroundColor: C.bgElevated, justifyContent: 'center', alignItems: 'center', borderWidth: 1.5, borderColor: GLASS_BORDER },
  closeBtnText: { color: C.textMuted, fontSize: 12, fontWeight: '700' },
  panelScroll: { flex: 1, paddingHorizontal: 14 },
  sectionLabel: { color: C.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 2, marginTop: 18, marginBottom: 8 },
  armBigBtn: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 14, borderWidth: 1, marginBottom: 10, gap: 12, backgroundColor: C.bgElevated },
  armBigIcon: { fontSize: 26 },
  armBigLabel: { fontSize: 14, fontWeight: '900', letterSpacing: 1 },
  armBigDesc: { color: LABEL, fontSize: 9, fontWeight: '600', marginTop: 2 },
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  quickBtn: { width: '30.5%', aspectRatio: 1.2, borderRadius: 14, borderWidth: 1, justifyContent: 'center', alignItems: 'center', gap: 4, backgroundColor: C.bgElevated },
  quickBtnIcon: { fontSize: 18 },
  quickBtnLabel: { fontSize: 8, fontWeight: '800', letterSpacing: 0.5, textAlign: 'center' },
  modeGroup: { gap: 6, marginBottom: 4 },
  modeBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 10, borderRadius: 14, borderWidth: 1, backgroundColor: C.bgElevated },
  modeBtnLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  modeBtnIcon: { fontSize: 18, width: 24, textAlign: 'center' },
  modeBtnName: { fontSize: 12, fontWeight: '800', letterSpacing: 0.5 },
  modeBtnDesc: { color: LABEL, fontSize: 9, fontWeight: '600', marginTop: 2 },
  gpsBadge: { backgroundColor: C.bgElevated, borderWidth: 1, borderColor: C.cyan + '66', borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2 },
  gpsBadgeText: { color: C.cyan, fontSize: 7, fontWeight: '800', letterSpacing: 0.5 },
  activeModeDot: { width: 8, height: 8, borderRadius: 4 },
  batteryPanel: { backgroundColor: C.bgElevated, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: GLASS_BORDER },
  batteryTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 },
  batteryPct: { fontSize: 28, fontWeight: '900', fontFamily: 'monospace' },
  batteryV: { fontSize: 14, fontWeight: '700' },
  batteryBar: { height: 8, backgroundColor: C.hairline, borderRadius: 4, overflow: 'hidden' },
  batteryFill: { height: '100%', borderRadius: 4 },

  // ── LÍMITES ──
  limitsPanel: {
    backgroundColor: C.bgElevated, borderRadius: 16, padding: 14,
    borderWidth: 1, borderColor: GLASS_BORDER,
  },
  limitRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center',
  },
  limitLabel: { color: LABEL, fontSize: 9, fontWeight: '800', letterSpacing: 1.5 },
  limitControls: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  limitBtn: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: C.glass,
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: GLASS_BORDER,
  },
  limitBtnText: { color: AMBER, fontSize: 16, fontWeight: '700', lineHeight: 18 },

  limitValue: { color: AMBER, fontSize: 16, fontWeight: '900', fontFamily: 'monospace', minWidth: 50, textAlign: 'center' },
  limitPresets: { flexDirection: 'row', gap: 8, marginTop: 10 },
  limitPreset: {
    flex: 1, paddingVertical: 6, borderRadius: 8,
    borderWidth: 1, borderColor: C.hairline,
    alignItems: 'center', backgroundColor: C.glass,
  },
  limitPresetText: { color: LABEL, fontSize: 10, fontWeight: '700' },
  limitWarning: {
    marginTop: 8, paddingVertical: 6, paddingHorizontal: 10,
    borderRadius: 8, backgroundColor: RED + '18',
    borderWidth: 1, borderColor: RED + '55',
    alignItems: 'center',
  },
  limitWarningText: { color: RED, fontSize: 8, fontWeight: '900', letterSpacing: 1 },

  // ── TOAST ──
  toast: {
    position: 'absolute', bottom: 60, left: 20, right: 20,
    backgroundColor: C.navy,
    borderWidth: 1, borderColor: AMBER + '66',
    borderRadius: 12, paddingVertical: 8, paddingHorizontal: 16,
    alignItems: 'center', zIndex: 100,
    elevation: 6,
  },
  toastText: { color: C.surface, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },

  // ── Landscape-specific ──
  metricChipsLandscape: {
    position: 'absolute', top: 30, left: 4, right: 4,
    flexDirection: 'row', justifyContent: 'center', gap: 3,
  },
  landscapeBody: {
    flex: 1,
    position: 'relative',
  },
  headerLandscape: {
    position: 'absolute', top: 0, left: 0, right: 0,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 12, paddingBottom: 4,
    backgroundColor: 'rgba(15,42,74,0.55)',
    zIndex: 10,
  },
  joystickSectionLandscape: {
    position: 'absolute', bottom: 28, left: 0, right: 0,
    flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center',
    paddingVertical: 0,
    zIndex: 10,
  },
  bottomBarLandscape: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(15,42,74,0.55)',
    borderTopColor: 'rgba(255,255,255,0.2)',
    paddingVertical: 3,
    zIndex: 10,
  },
});
