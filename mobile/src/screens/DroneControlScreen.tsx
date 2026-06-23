import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  StyleSheet,
  Dimensions,
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
import { Joystick } from '../components/Joystick';
import { useDrone } from '../context/DroneContext';
import { useDeviceLocation } from '../hooks/useDeviceLocation';
import { getApiUrl, setHostIp } from '../config';
import { getStoredIp } from '../utils/ipConfig';
import { IpConfigModal } from '../components/IpConfigModal';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const JOYSTICK_SIZE = SCREEN_WIDTH * 0.18;
const PANEL_WIDTH = SCREEN_WIDTH * 0.72;

const BG = '#0A0D12';
const AMBER = '#FF8800';
const YELLOW = '#F0B429';
const RED = '#E53E3E';
const LABEL = '#8A95A3';
const BORDER = 'rgba(255,255,255,0.08)';
const GLASS = 'rgba(20,30,48,0.3)';
const GLASS_BORDER = 'rgba(255,255,255,0.18)';

const MODE_META: Record<string, { color: string; icon: string; desc: string; requiresGPS?: boolean }> = {
  STABILIZE: { color: AMBER, icon: '◈', desc: 'Control manual' },
  ALT_HOLD: { color: '#00d4ff', icon: '⇳', desc: 'Altura automática' },
  LOITER: { color: '#00aaff', icon: '⊙', desc: 'Posición fija GPS', requiresGPS: true },
  POSHOLD: { color: '#00ccaa', icon: '⊕', desc: 'Posición + altitud', requiresGPS: true },
  AUTO: { color: '#aa88ff', icon: '⟳', desc: 'Misión automática', requiresGPS: true },
  GUIDED: { color: '#cc88ff', icon: '➤', desc: 'Control GCS', requiresGPS: true },
  RTL: { color: '#ff8800', icon: '⌂', desc: 'Retorno a casa', requiresGPS: true },
  LAND: { color: '#ffaa00', icon: '↓', desc: 'Aterrizaje automático' },
  CIRCLE: { color: '#88aaff', icon: '○', desc: 'Círculo', requiresGPS: true },
  BRAKE: { color: '#ff4400', icon: '⊗', desc: 'Freno GPS', requiresGPS: true },
  SPORT: { color: '#ffcc00', icon: '⚡', desc: 'Velocidad mejorada' },
  ACRO: { color: '#ff6688', icon: '✦', desc: 'Acrobático' },
  DRIFT: { color: '#ff99aa', icon: '〜', desc: 'Vuelo tipo avión' },
  FLIP: { color: '#ff66cc', icon: '↺', desc: 'Flips' },
  THROW: { color: '#ffdd88', icon: '⤴', desc: 'Lanzamiento' },
  SMARTRTL: { color: '#ff9944', icon: '⟲', desc: 'RTL inteligente', requiresGPS: true },
};

const getMeta = (mode: string) => MODE_META[mode] ?? { color: '#555', icon: '?', desc: '?' };

const MODE_GROUPS = [
  { label: 'MANUAL', modes: ['STABILIZE', 'ACRO', 'SPORT', 'DRIFT'] },
  { label: 'ASISTIDO', modes: ['ALT_HOLD', 'POSHOLD', 'LOITER', 'BRAKE'] },
  { label: 'AUTOMÁTICO', modes: ['AUTO', 'GUIDED', 'CIRCLE', 'FLIP', 'THROW'] },
  { label: 'EMERGENCIA / RETORNO', modes: ['RTL', 'SMARTRTL', 'LAND'] },
];

export const DroneControlScreen: React.FC = () => {
  const { telemetry, connected, demoMode, armDrone, disarmDrone, setJoystick, sendCommand, forceReconnect } =
    useDrone();
  const insets = useSafeAreaInsets();

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

  useEffect(() => {
    const isArmed = telemetry?.armed ?? false;
    if (isArmed && !prevArmed.current) {
      setLeftJoystickReset(true);
      setTimeout(() => setLeftJoystickReset(false), 150);
    }
    prevArmed.current = isArmed;
  }, [telemetry?.armed]);

  const [normalizedValues, setNormalizedValues] = useState({ thrNorm: 0, yaw: 0, pitch: 0, roll: 0 });
  const toPWM = (v: number): number => Math.round(1500 + v * 500);
  const toThrottlePWM = (v: number): number => Math.round(1000 + v * 1000);
  const pwmDisplay = {
    thr: toThrottlePWM(normalizedValues.thrNorm),
    yaw: toPWM(normalizedValues.yaw),
    pitch: toPWM(normalizedValues.pitch),
    roll: toPWM(normalizedValues.roll),
  };

  // animations
  const batteryBlink = useRef(new Animated.Value(1)).current;
  const panelX = useRef(new Animated.Value(-PANEL_WIDTH)).current;
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

  const batColor = bat > 50 ? AMBER : bat > 20 ? YELLOW : RED;
  const altColor = alt > 0 ? AMBER : LABEL;

  const openPanel = () => {
    setPanelOpen(true);
    Animated.parallel([
      Animated.spring(panelX, { toValue: 0, useNativeDriver: true, tension: 65, friction: 11 }),
      Animated.timing(backdropOp, { toValue: 1, duration: 250, useNativeDriver: true }),
    ]).start();
  };

  const closePanel = () => {
    Animated.parallel([
      Animated.spring(panelX, { toValue: -PANEL_WIDTH, useNativeDriver: true, tension: 65, friction: 11 }),
      Animated.timing(backdropOp, { toValue: 0, duration: 200, useNativeDriver: true }),
    ]).start(() => setPanelOpen(false));
  };

  const handleLeftJoystick = (x: number, y: number) => {
    setNormalizedValues(prev => ({ ...prev, thrNorm: y, yaw: x }));
    setJoystick(y, x, undefined, undefined);
  };

  const handleRightJoystick = (x: number, y: number) => {
    setNormalizedValues(prev => ({ ...prev, pitch: y, roll: x }));
    setJoystick(undefined, undefined, y, x);
  };

  const runCommand = async (fn: () => Promise<{ success: boolean; message: string }>) => {
    const result = await fn();
    if (!result.success) Alert.alert('Error', result.message);
    return result;
  };

  const handleModeChange = (mode: string) => {
    const meta = getMeta(mode);
    const gpsOk = droneSat ? droneSat >= 6 : true;
    const gpsWarning =
      meta.requiresGPS && !gpsOk ? '\n⚠️ GPS insuficiente' : '';
    Alert.alert('Cambiar modo', `¿Cambiar a ${mode}?\n${meta.desc}${gpsWarning}`, [
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
            await runCommand(armDrone);
          },
        },
      ]);
    }
  };

  const handleAction = (id: string) => {
    const map: Record<string, () => void> = {
      BRAKE: () => { closePanel(); runCommand(() => sendCommand('SET_MODE', { mode: 'BRAKE' })); },
      HOLD_POS: () => {
        closePanel();
        runCommand(() => sendCommand('SET_MODE', { mode: 'LOITER' }));
      },
      REBOOT: () =>
        Alert.alert('Reboot', '¿Reiniciar autopiloto?', [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Reiniciar', style: 'destructive', onPress: () => runCommand(() => sendCommand('REBOOT', {})) },
        ]),
    };
    map[id]?.();
  };

  const meta = getMeta(telemetry?.mode ?? 'UNKNOWN');

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={BG} />

      {/* ── HEADER ── */}
      <View style={[styles.header, { paddingTop: insets.top + 4 }]}>
        <View style={styles.headerLeft}>
          <Text style={styles.logo}>GCS</Text>
          <Text style={styles.logoSub}>v1.0</Text>
        </View>
        <View style={styles.headerRight}>
          <TouchableOpacity onPress={() => setIpModalVisible(true)} activeOpacity={0.6} style={styles.ipBtn}>
            <Text style={styles.ipBtnIcon}>⚙</Text>
          </TouchableOpacity>
          <Text style={styles.headerTime}>{new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</Text>
          <TouchableOpacity
            style={[styles.headerArmBtn, telemetry?.armed ? styles.headerArmBtnArmed : { borderColor: AMBER + '60' }]}
            onPress={handleArmToggle}
            activeOpacity={0.7}
          >
            <View style={[styles.headerArmDot, { backgroundColor: telemetry?.armed ? RED : AMBER }]} />
            <Text style={[styles.headerArmText, { color: telemetry?.armed ? RED : AMBER, textShadowColor: telemetry?.armed ? RED : AMBER, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: telemetry?.armed ? 10 : 4 }]}>
              {telemetry?.armed ? 'ARM' : 'STBY'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* ── CAMERA + METRICS OVERLAY ── */}
      <View style={styles.cameraSection}>
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
              onError={() => setCameraState('failed')}
              onHttpError={() => setCameraState('failed')}
              onLoad={() => {}}
              renderError={() => null}
            />
          ) : (
            <View style={styles.cameraOff}>
              <Text style={styles.cameraOffIcon}>CAM</Text>
              <TouchableOpacity
                style={styles.retryBtn}
                onPress={() => {
                  setCameraState('loading');
                  fetch(`${getApiUrl()}/api/camera/view`, { method: 'HEAD', cache: 'no-store' })
                    .then(r => {
                      if (r.ok) { setCameraState('connected'); cameraKeyRef.current++; }
                      else setCameraState('failed');
                    })
                    .catch(() => setCameraState('failed'));
                }}
                activeOpacity={0.7}
              >
                <Text style={styles.retryBtnText}>REINTENTAR</Text>
              </TouchableOpacity>
            </View>
          )}
          {cameraState === 'connected' && (
            <>
              {/* Single row of essential chips */}
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
                  <Text style={styles.chipValue}>{alt.toFixed(1)}</Text>
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
            </>
          )}
        </View>
      </View>

      {/* ── JOYSTICKS ── */}
      <View style={styles.joystickSection}>
        <View style={styles.joystickCol}>
          <Text style={styles.joystickLabel}>THR / YAW</Text>
          <Joystick
            onMove={handleLeftJoystick}
            size={JOYSTICK_SIZE}
            mode="mode2"
            color={AMBER}
            resetToBottom={leftJoystickReset}
          />
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
        <View style={styles.joystickCol}>
          <Text style={styles.joystickLabel}>PITCH / ROLL</Text>
          <Joystick
            onMove={handleRightJoystick}
            size={JOYSTICK_SIZE}
            mode="both"
            color="#3B82F6"
          />
          <View style={styles.pwmRow}>
            <View style={[styles.pwmChip, { borderColor: BORDER }]}>
              <Text style={styles.pwmLabel}>PIT</Text>
              <Text style={[styles.pwmValue, { color: pwmDisplay.pitch !== 1500 ? '#3B82F6' : LABEL }]}>
                {pwmDisplay.pitch}
              </Text>
            </View>
            <View style={[styles.pwmChip, { borderColor: BORDER }]}>
              <Text style={styles.pwmLabel}>RLL</Text>
              <Text style={[styles.pwmValue, { color: pwmDisplay.roll !== 1500 ? '#3B82F6' : LABEL }]}>
                {pwmDisplay.roll}
              </Text>
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
        <Text style={[styles.modeText, { color: meta.color, textShadowColor: meta.color, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 6 }]}>
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

      {/* ── SIDE PANEL ── */}
      {panelOpen && (
        <Animated.View style={[styles.backdrop, { opacity: backdropOp }]}>
          <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={closePanel} />
        </Animated.View>
      )}

      <Animated.View style={[styles.sidePanel, { transform: [{ translateX: panelX }] }]}>
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
              ? { backgroundColor: '#ff000018', borderColor: '#ff0044AA', shadowColor: RED, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.6, shadowRadius: 14, elevation: 14 }
              : { backgroundColor: '#00ff8818', borderColor: '#00ff88AA', shadowColor: AMBER, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.4, shadowRadius: 10, elevation: 8 }]}
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
              { id: 'BRAKE', label: 'FRENO', icon: '⊗', color: '#ff4400' },
              { id: 'HOLD_POS', label: 'HOLD POS', icon: '⊙', color: '#00ccaa' },
              { id: 'REBOOT', label: 'REBOOT FC', icon: '↺', color: '#777' },
            ].map(a => (
              <TouchableOpacity
                key={a.id}
                style={[styles.quickBtn, { borderColor: a.color + '88', backgroundColor: a.color + '12', shadowColor: a.color, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.4, shadowRadius: 8, elevation: 6 }]}
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
                      }, isActive && { shadowColor: m.color, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.5, shadowRadius: 10, elevation: 8 }]}
                      onPress={() => handleModeChange(modeName)}
                      activeOpacity={0.75}
                    >
                      <View style={styles.modeBtnLeft}>
                        <Text style={[styles.modeBtnIcon, { color: m.color }]}>{m.icon}</Text>
                        <View>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                            <Text style={[styles.modeBtnName, { color: isActive ? m.color : '#ccc' }]}>
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
    borderBottomColor: GLASS_BORDER,
    backgroundColor: GLASS,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  logo: { color: AMBER, fontSize: 20, fontWeight: '900', letterSpacing: 3, textShadowColor: AMBER, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 8 },
  logoSub: { color: LABEL, fontSize: 10, fontWeight: '600' },
  headerTime: { color: AMBER, fontSize: 14, fontWeight: '700', fontFamily: 'monospace', textShadowColor: AMBER, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 4 },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ipBtn: { padding: 4 },
  ipBtnIcon: { fontSize: 16, color: LABEL },
  headerArmBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    borderWidth: 1.5, borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 4,
    backgroundColor: GLASS,
  },
  headerArmBtnArmed: {
    borderColor: RED + 'AA',
    shadowColor: RED,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 10,
    elevation: 10,
  },
  headerArmDot: { width: 5, height: 5, borderRadius: 3 },
  headerArmText: { fontSize: 8, fontWeight: '900', letterSpacing: 1, fontFamily: 'monospace' },

  // ── CAMERA ──
  cameraSection: { height: SCREEN_HEIGHT * 0.35, borderWidth: 1.5, borderColor: GLASS_BORDER, borderRadius: 14, marginHorizontal: 2, overflow: 'hidden' },
  cameraContainer: { flex: 1, backgroundColor: '#000', position: 'relative' },
  cameraFeed: { width: '100%', height: '100%', backgroundColor: 'transparent' },
  cameraOff: {
    flex: 1, justifyContent: 'center', alignItems: 'center',
    backgroundColor: '#050508', gap: 12,
  },
  cameraOffIcon: { fontSize: 28, color: '#333', fontWeight: '900', letterSpacing: 2 },
  cameraConnecting: { color: '#555', fontSize: 9, fontWeight: '700', letterSpacing: 1.5 },
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
    backgroundColor: GLASS,
    borderWidth: 1, borderRadius: 8,
    paddingHorizontal: 6, paddingVertical: 3,
  },
  chipLabel: { color: LABEL, fontSize: 6, fontWeight: '700', letterSpacing: 0.6 },
  chipValue: { color: AMBER, fontSize: 8, fontWeight: '900', fontFamily: 'monospace' },

  // ── JOYSTICKS ──
  joystickSection: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 4,
    flex: 1,
  },
  joystickCol: { alignItems: 'center', gap: 3 },
  joystickLabel: { color: LABEL, fontSize: 7, fontWeight: '700', letterSpacing: 1.2 },
  pwmRow: { flexDirection: 'row', gap: 4 },
  pwmChip: {
    alignItems: 'center',
    backgroundColor: GLASS,
    borderRadius: 10, paddingHorizontal: 8, paddingVertical: 4,
    borderWidth: 1, borderColor: AMBER + '55',
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
    backgroundColor: GLASS,
  },
  bottomLeft: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  statusDot: { width: 5, height: 5, borderRadius: 3 },
  bottomText: { color: LABEL, fontSize: 8, fontWeight: '700', letterSpacing: 0.8 },
  modeText: { fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  bottomRight: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  armDot: { width: 5, height: 5, borderRadius: 3 },
  demoBadge: {
    backgroundColor: GLASS, borderWidth: 1, borderColor: 'rgba(255,170,0,0.3)',
    borderRadius: 6, paddingHorizontal: 5, paddingVertical: 2,
  },
  demoBadgeText: { color: YELLOW, fontSize: 6, fontWeight: '900', letterSpacing: 1 },

  // ── Side panel ──
  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 20 },
  sidePanel: {
    position: 'absolute', top: 0, bottom: 0, left: 0,
    width: PANEL_WIDTH, backgroundColor: 'rgba(10,15,25,0.92)',
    borderRightWidth: 1.5, borderRightColor: 'rgba(255,136,0,0.6)', shadowColor: AMBER, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.3, shadowRadius: 20, elevation: 0, zIndex: 30,
  },
  panelHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 18, paddingTop: 18, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: GLASS_BORDER },
  panelTitle: { color: '#fff', fontSize: 16, fontWeight: '900', letterSpacing: 2 },
  panelSubtitle: { color: LABEL, fontSize: 9, fontWeight: '600', letterSpacing: 1, marginTop: 2 },
  closeBtn: { width: 30, height: 30, borderRadius: 15, backgroundColor: GLASS, justifyContent: 'center', alignItems: 'center', borderWidth: 1.5, borderColor: GLASS_BORDER },
  closeBtnText: { color: '#888', fontSize: 12, fontWeight: '700' },
  panelScroll: { flex: 1, paddingHorizontal: 14 },
  sectionLabel: { color: '#4a4a5a', fontSize: 9, fontWeight: '800', letterSpacing: 2, marginTop: 18, marginBottom: 8 },
  armBigBtn: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 14, borderWidth: 1, marginBottom: 10, gap: 12, backgroundColor: GLASS },
  armBigIcon: { fontSize: 26 },
  armBigLabel: { fontSize: 14, fontWeight: '900', letterSpacing: 1 },
  armBigDesc: { color: LABEL, fontSize: 9, fontWeight: '600', marginTop: 2 },
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  quickBtn: { width: '30.5%', aspectRatio: 1.2, borderRadius: 14, borderWidth: 1, justifyContent: 'center', alignItems: 'center', gap: 4, backgroundColor: GLASS },
  quickBtnIcon: { fontSize: 18 },
  quickBtnLabel: { fontSize: 8, fontWeight: '800', letterSpacing: 0.5, textAlign: 'center' },
  modeGroup: { gap: 6, marginBottom: 4 },
  modeBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 10, borderRadius: 14, borderWidth: 1, backgroundColor: GLASS },
  modeBtnLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  modeBtnIcon: { fontSize: 18, width: 24, textAlign: 'center' },
  modeBtnName: { fontSize: 12, fontWeight: '800', letterSpacing: 0.5 },
  modeBtnDesc: { color: LABEL, fontSize: 9, fontWeight: '600', marginTop: 2 },
  gpsBadge: { backgroundColor: GLASS, borderWidth: 1, borderColor: 'rgba(0,170,255,0.4)', borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2 },
  gpsBadgeText: { color: '#00aaff', fontSize: 7, fontWeight: '800', letterSpacing: 0.5 },
  activeModeDot: { width: 8, height: 8, borderRadius: 4, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 1, shadowRadius: 6, elevation: 6 },
  batteryPanel: { backgroundColor: GLASS, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: GLASS_BORDER },
  batteryTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 },
  batteryPct: { fontSize: 28, fontWeight: '900', fontFamily: 'monospace' },
  batteryV: { fontSize: 14, fontWeight: '700' },
  batteryBar: { height: 8, backgroundColor: '#0d0d1a', borderRadius: 4, overflow: 'hidden' },
  batteryFill: { height: '100%', borderRadius: 4 },

  // ── TOAST ──
  toast: {
    position: 'absolute', bottom: 60, left: 20, right: 20,
    backgroundColor: 'rgba(10,15,25,0.95)',
    borderWidth: 1, borderColor: AMBER + '66',
    borderRadius: 12, paddingVertical: 8, paddingHorizontal: 16,
    alignItems: 'center', zIndex: 100,
    shadowColor: AMBER, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.3, shadowRadius: 10, elevation: 8,
  },
  toastText: { color: '#fff', fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
});
