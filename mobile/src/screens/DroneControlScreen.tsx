import React, { useState, useEffect, useRef } from 'react';
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
  PanResponder,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Joystick } from '../components/Joystick';
import { TacticalButton } from '../components/TacticalButton';
import { StatusBar as AppStatusBar } from '../components/StatusBar';
import { useDrone } from '../context/DroneContext';
import { API_URL } from '../config';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const PANEL_WIDTH = SCREEN_WIDTH * 0.72;
const JOYSTICK_SIZE = SCREEN_WIDTH * 0.18;

const MODE_META: Record<string, { color: string; icon: string; desc: string; requiresGPS?: boolean }> = {
  STABILIZE: { color: '#00ff88', icon: '◈', desc: 'Control manual' },
  ALT_HOLD:  { color: '#00d4ff', icon: '⇳', desc: 'Altura automática' },
  LOITER:    { color: '#00aaff', icon: '⊙', desc: 'Posición fija GPS', requiresGPS: true },
  POSHOLD:   { color: '#00ccaa', icon: '⊕', desc: 'Posición + altitud', requiresGPS: true },
  AUTO:      { color: '#aa88ff', icon: '⟳', desc: 'Misión automática', requiresGPS: true },
  GUIDED:    { color: '#cc88ff', icon: '➤', desc: 'Control GCS', requiresGPS: true },
  RTL:       { color: '#ff8800', icon: '⌂', desc: 'Retorno a casa', requiresGPS: true },
  LAND:      { color: '#ffaa00', icon: '↓', desc: 'Aterrizaje automático' },
  CIRCLE:    { color: '#88aaff', icon: '○', desc: 'Círculo', requiresGPS: true },
  BRAKE:     { color: '#ff4400', icon: '⊗', desc: 'Freno GPS', requiresGPS: true },
  SPORT:     { color: '#ffcc00', icon: '⚡', desc: 'Velocidad mejorada' },
  ACRO:      { color: '#ff6688', icon: '✦', desc: 'Acrobático' },
  DRIFT:     { color: '#ff99aa', icon: '〜', desc: 'Vuelo tipo avión' },
  FLIP:      { color: '#ff66cc', icon: '↺', desc: 'Flips' },
  THROW:     { color: '#ffdd88', icon: '⤴', desc: 'Lanzamiento' },
  SMARTRTL:  { color: '#ff9944', icon: '⟲', desc: 'RTL inteligente', requiresGPS: true },
};

const getMeta = (mode: string) => MODE_META[mode] ?? { color: '#555', icon: '?', desc: '?' };

const MODE_GROUPS = [
  { label: 'MANUAL',              modes: ['STABILIZE', 'ACRO', 'SPORT', 'DRIFT'] },
  { label: 'ASISTIDO',            modes: ['ALT_HOLD', 'POSHOLD', 'LOITER', 'BRAKE'] },
  { label: 'AUTOMÁTICO',          modes: ['AUTO', 'GUIDED', 'CIRCLE', 'FLIP', 'THROW'] },
  { label: 'EMERGENCIA / RETORNO',modes: ['RTL', 'SMARTRTL', 'LAND'] },
];

export const DroneControlScreen: React.FC = () => {
  const { telemetry, connected, demoMode, armDrone, disarmDrone, takeoff, land, emergency, setJoystick, sendCommand } =
    useDrone();
  const insets = useSafeAreaInsets();

  const [cameraOk, setCameraOk] = useState(true);
  const [showEmergency, setShowEmergency] = useState(false);
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
    thr:   toThrottlePWM(normalizedValues.thrNorm),
    yaw:   toPWM(normalizedValues.yaw),
    pitch: toPWM(normalizedValues.pitch),
    roll:  toPWM(normalizedValues.roll),
  };

  const batteryBlink = useRef(new Animated.Value(1)).current;
  const panelX = useRef(new Animated.Value(-PANEL_WIDTH)).current;
  const backdropOp = useRef(new Animated.Value(0)).current;
  const hudFade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const pct = Number(telemetry?.battery_remaining ?? 100);
    if (pct < 20) {
      Animated.loop(Animated.sequence([
        Animated.timing(batteryBlink, { toValue: 0.2, duration: 400, useNativeDriver: true }),
        Animated.timing(batteryBlink, { toValue: 1, duration: 400, useNativeDriver: true }),
      ])).start();
    } else {
      batteryBlink.setValue(1);
    }
  }, [telemetry?.battery_remaining]);

  useEffect(() => {
    Animated.timing(hudFade, { toValue: 1, duration: 800, useNativeDriver: true }).start();
  }, []);

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

  const edgePanResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => g.dx > 8 && Math.abs(g.dy) < 40,
      onPanResponderRelease: (_, g) => { if (g.dx > 30) openPanel(); },
    })
  ).current;

  const panelPanResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => g.dx < -8 && Math.abs(g.dy) < 40,
      onPanResponderRelease: (_, g) => { if (g.dx < -30) closePanel(); },
    })
  ).current;

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

  const handleTakeoff = () =>
    Alert.alert('Despegue', '¿Despegar a 10 metros?', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Despegar', onPress: () => runCommand(() => takeoff(10)) },
    ]);

  const handleEmergency = (action: 'STOP' | 'RTL' | 'LAND') =>
    Alert.alert('⚠️ EMERGENCIA', `¿Ejecutar ${action}?`, [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'CONFIRMAR', style: 'destructive',
        onPress: async () => {
          setShowEmergency(false);
          await runCommand(() => emergency(action));
        },
      },
    ]);

  const handleModeChange = (mode: string) => {
    const meta = getMeta(mode);
    const gpsWarning = meta.requiresGPS && Number(telemetry?.satellites ?? 0) < 6
      ? '\n⚠️ GPS insuficiente (< 6 satélites)' : '';
    Alert.alert(`Cambiar modo`, `¿Cambiar a ${mode}?\n${meta.desc}${gpsWarning}`, [
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
        { text: 'Desarmar', style: 'destructive', onPress: async () => { closePanel(); await runCommand(disarmDrone); } },
      ]);
    } else {
      Alert.alert('Armar', '¿Armar el dron?', [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Armar', onPress: async () => { closePanel(); await runCommand(armDrone); } },
      ]);
    }
  };

  const handleAction = (id: string) => {
    const map: Record<string, () => void> = {
      TAKEOFF: () => { handleTakeoff(); closePanel(); },
      LAND: () => Alert.alert('Aterrizar', '¿Iniciar aterrizaje?', [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Aterrizar', onPress: async () => { closePanel(); await runCommand(land); } },
      ]),
      RTL: () => Alert.alert('RTL', '¿Retornar a casa?', [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'RTL', onPress: async () => { closePanel(); await runCommand(() => sendCommand('SET_MODE', { mode: 'RTL' })); } },
      ]),
      BRAKE: () => { closePanel(); runCommand(() => sendCommand('SET_MODE', { mode: 'BRAKE' })); },
      HOLD_POS: () => {
        const sat = Number(telemetry?.satellites ?? 0);
        if (sat < 6) { Alert.alert('Sin GPS', `Solo ${sat} satélites. LOITER requiere mínimo 6.`); return; }
        closePanel();
        runCommand(() => sendCommand('SET_MODE', { mode: 'LOITER' }));
      },
      REBOOT: () => Alert.alert('Reboot', '¿Reiniciar autopiloto?', [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Reiniciar', style: 'destructive', onPress: () => runCommand(() => sendCommand('REBOOT', {})) },
      ]),
    };
    map[id]?.();
  };

  const batPct = Number(telemetry?.battery_remaining ?? 0);
  const batColor = batPct > 50 ? '#00ff88' : batPct > 20 ? '#ffaa00' : '#ff0044';
  const sat = Number(telemetry?.satellites ?? 0);
  const satColor = sat >= 8 ? '#00ff88' : sat >= 5 ? '#ffaa00' : '#ff4444';
  const meta = getMeta(telemetry?.mode ?? 'UNKNOWN');
  const vs = Number(telemetry?.vertical_speed ?? 0);
  const alt = Number(telemetry?.altitude ?? 0);
  const spd = Number(telemetry?.ground_speed ?? 0);
  const yaw = Number(telemetry?.yaw ?? 0);

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#050508" />

      <View style={styles.edgeZone} {...edgePanResponder.panHandlers} />

      {/* ══ STATUS BAR ══ */}
      <AppStatusBar
        connected={connected}
        mode={telemetry?.mode ?? 'UNKNOWN'}
        modeColor={meta.color}
        modeIcon={meta.icon}
        armed={telemetry?.armed ?? false}
        demoMode={demoMode}
        onMenuPress={openPanel}
        insetsTop={insets.top}
      />

      {/* ══ VIDEO + HUD ══ */}
      <View style={styles.hudSection}>
        <View style={styles.videoContainer}>
          <WebView
            source={{ uri: `${API_URL}/api/camera/view` }}
            style={styles.video}
            scrollEnabled={false}
            bounces={false}
            javaScriptEnabled={true}
            mediaPlaybackRequiresUserAction={false}
            allowsInlineMediaPlayback={true}
            onError={() => setCameraOk(false)}
            onHttpError={() => setCameraOk(false)}
            onLoad={() => setCameraOk(true)}
          />

          {!cameraOk && (
            <View style={styles.cameraOverlay}>
              <Text style={styles.cameraOverlayIcon}>�</Text>
              <Text style={styles.cameraOverlayText}>SEÑAL DE VIDEO NO DISPONIBLE</Text>
              <Text style={styles.cameraOverlaySub}>Verificando conexión de cámara...</Text>
            </View>
          )}

          <View style={styles.vignette} />

          {/* ── HUD OVERLAY ── */}
          <View style={styles.hudOverlay}>
            <View style={styles.crosshairWrap}>
              <View style={styles.crosshairH} />
              <View style={styles.crosshairV} />
              <View style={styles.crosshairCenter} />
              <View style={[styles.corner, styles.cornerTL]} />
              <View style={[styles.corner, styles.cornerTR]} />
              <View style={[styles.corner, styles.cornerBL]} />
              <View style={[styles.corner, styles.cornerBR]} />
            </View>

            {/* ── Altitude bar ── */}
            <View style={styles.altBar}>
              <View style={[styles.altFill, { height: `${Math.min((alt / 100) * 100, 100)}%` }]} />
              <Text style={styles.altText}>{alt.toFixed(1)}</Text>
              <Text style={styles.altUnit}>m</Text>
            </View>
          </View>
        </View>

        {/* ── CENTRAL HUD PANEL ── */}
        <Animated.View style={[styles.centralHudPanel, { opacity: hudFade }]}>
          <View style={styles.hudGrid}>
            <View style={styles.hudCard}>
              <Text style={styles.hudCardLabel}>CAM</Text>
              <Text style={[styles.hudCardValue, { color: cameraOk ? '#00ff88' : '#ff4444' }]}>
                {cameraOk ? 'OK' : 'OFF'}
              </Text>
            </View>
            <View style={styles.hudCard}>
              <Text style={styles.hudCardLabel}>SPD</Text>
              <Text style={styles.hudCardValue}>{spd.toFixed(1)}</Text>
              <Text style={styles.hudCardUnit}>m/s</Text>
            </View>
            <View style={styles.hudCard}>
              <Text style={styles.hudCardLabel}>ALT</Text>
              <Text style={styles.hudCardValue}>{alt.toFixed(1)}</Text>
              <Text style={styles.hudCardUnit}>m</Text>
            </View>
            <View style={styles.hudCard}>
              <Text style={styles.hudCardLabel}>BAT</Text>
              <Animated.Text style={[styles.hudCardValue, { color: batColor, opacity: batteryBlink }]}>
                {batPct.toFixed(0)}
              </Animated.Text>
              <Animated.Text style={[styles.hudCardUnit, { color: batColor, opacity: batteryBlink }]}>
                %
              </Animated.Text>
            </View>
            <View style={styles.hudCard}>
              <Text style={styles.hudCardLabel}>SAT</Text>
              <Text style={[styles.hudCardValue, { color: satColor }]}>{sat}</Text>
              <Text style={styles.hudCardUnit}>🛰</Text>
            </View>
            <View style={styles.hudCard}>
              <Text style={styles.hudCardLabel}>YAW</Text>
              <Text style={styles.hudCardValue}>{yaw.toFixed(0)}</Text>
              <Text style={styles.hudCardUnit}>°</Text>
            </View>
            <View style={styles.hudCard}>
              <Text style={styles.hudCardLabel}>V/S</Text>
              <Text style={[styles.hudCardValue, { color: vs >= 0 ? '#00ff88' : '#ff6644' }]}>
                {vs.toFixed(1)}
              </Text>
              <Text style={styles.hudCardUnit}>m/s</Text>
            </View>
          </View>
        </Animated.View>
      </View>

      {/* ══ CONTROLS ══ */}
      <View style={styles.controlsSection}>
        {/* ── Tactical buttons ── */}
        <View style={styles.tacticalRow}>
          {!telemetry?.armed ? (
            <TacticalButton label="ARMAR" icon="⚡" color="#00ff88" onPress={handleArmToggle} size="large" />
          ) : (
            <TacticalButton label="DESARMAR" icon="🔒" color="#ff4466" onPress={handleArmToggle} active size="large" />
          )}
          <TacticalButton label="DESPEGUE" icon="▲" color="#00aaff" onPress={handleTakeoff} size="large" />
          <TacticalButton label="ATERRIZAJE" icon="▼" color="#ffaa00" onPress={() =>
            Alert.alert('Aterrizar', '¿Iniciar aterrizaje?', [
              { text: 'Cancelar', style: 'cancel' },
              { text: 'Aterrizar', onPress: () => runCommand(land) },
            ])
          } size="large" />
          <TacticalButton
            label="SOS"
            icon="☢"
            color="#ff0044"
            onPress={() => setShowEmergency(!showEmergency)}
            active={showEmergency}
            size="large"
          />
        </View>

        {/* ── Emergency panel ── */}
        {showEmergency && (
          <View style={styles.emergencyPanel}>
            <View style={styles.emergencyButtons}>
              {[
                { label: 'DETENER', icon: '■', color: '#ff6600', action: 'STOP' as const },
                { label: 'RTL', icon: '⌂', color: '#ffaa00', action: 'RTL' as const },
                { label: 'ATERRIZAJE', icon: '↓', color: '#ff0044', action: 'LAND' as const },
              ].map(e => (
                <TouchableOpacity
                  key={e.action}
                  style={[styles.emergencyBtn, { borderColor: e.color, backgroundColor: e.color + '18' }]}
                  onPress={() => handleEmergency(e.action)}
                  activeOpacity={0.75}
                >
                  <Text style={[styles.emergencyIcon, { color: e.color }]}>{e.icon}</Text>
                  <Text style={[styles.emergencyLabel, { color: e.color }]}>{e.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* ── Joysticks ── */}
        <View style={styles.joystickArea}>
          <View style={styles.joystickCol}>
            <Text style={styles.joystickLabel}>THR / YAW</Text>
            <Joystick
              onMove={handleLeftJoystick}
              size={JOYSTICK_SIZE}
              mode="mode2"
              color="#00ff88"
              resetToBottom={leftJoystickReset}
            />
            <View style={styles.pwmRow}>
              <View style={styles.pwmChip}>
                <Text style={styles.pwmLabel}>THR</Text>
                <Text style={[styles.pwmValue, {
                  color: pwmDisplay.thr >= 1800 ? '#ff4444' : pwmDisplay.thr >= 1500 ? '#00ff88' : pwmDisplay.thr >= 1200 ? '#ffaa00' : '#555'
                }]}>
                  {pwmDisplay.thr}
                </Text>
              </View>
              <View style={styles.pwmChip}>
                <Text style={styles.pwmLabel}>YAW</Text>
                <Text style={[styles.pwmValue, { color: pwmDisplay.yaw !== 1500 ? '#ffcc00' : '#555' }]}>
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
              color="#00aaff"
            />
            <View style={styles.pwmRow}>
              <View style={styles.pwmChip}>
                <Text style={styles.pwmLabel}>PIT</Text>
                <Text style={[styles.pwmValue, { color: pwmDisplay.pitch !== 1500 ? '#00aaff' : '#555' }]}>
                  {pwmDisplay.pitch}
                </Text>
              </View>
              <View style={styles.pwmChip}>
                <Text style={styles.pwmLabel}>RLL</Text>
                <Text style={[styles.pwmValue, { color: pwmDisplay.roll !== 1500 ? '#00aaff' : '#555' }]}>
                  {pwmDisplay.roll}
                </Text>
              </View>
            </View>
          </View>
        </View>
      </View>

      {/* ══ BACKDROP ══ */}
      {panelOpen && (
        <Animated.View style={[styles.backdrop, { opacity: backdropOp }]}>
          <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={closePanel} />
        </Animated.View>
      )}

      {/* ══ SIDE PANEL ══ */}
      <Animated.View
        style={[styles.sidePanel, { transform: [{ translateX: panelX }] }]}
        {...panelPanResponder.panHandlers}
      >
        <View style={[styles.panelHeader, { paddingTop: insets.top + 12 }]}>
          <View>
            <Text style={styles.panelTitle}>CONTROL</Text>
            <Text style={styles.panelSubtitle}>ArduPilot · {telemetry?.mode ?? '—'}</Text>
          </View>
          <TouchableOpacity onPress={closePanel} style={styles.closeBtn} activeOpacity={0.75}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
        </View>

        <View style={[styles.connBar, {
          backgroundColor: connected ? '#00ff8815' : '#ff004415',
          borderColor: connected ? '#00ff8830' : '#ff004430',
        }]}>
          <View style={[styles.connDot, { backgroundColor: connected ? '#00ff88' : '#ff0044' }]} />
          <Text style={[styles.connText, { color: connected ? '#00ff88' : '#ff4444' }]}>
            {connected ? 'Conectado al dron' : 'Sin conexión'}
          </Text>
        </View>

        <ScrollView style={styles.panelScroll} showsVerticalScrollIndicator={false}>
          <Text style={styles.sectionLabel}>ACCIONES RÁPIDAS</Text>

          <TouchableOpacity
            style={[styles.armBigBtn, telemetry?.armed
              ? { backgroundColor: '#ff000018', borderColor: '#ff004460' }
              : { backgroundColor: '#00ff8818', borderColor: '#00ff8860' }]}
            onPress={handleArmToggle}
            activeOpacity={0.75}
          >
            <Text style={[styles.armBigIcon, { color: telemetry?.armed ? '#ff4466' : '#00ff88' }]}>
              {telemetry?.armed ? '🔒' : '⚡'}
            </Text>
            <View style={{ flex: 1 }}>
              <Text style={[styles.armBigLabel, { color: telemetry?.armed ? '#ff4466' : '#00ff88' }]}>
                {telemetry?.armed ? 'DESARMAR DRON' : 'ARMAR DRON'}
              </Text>
              <Text style={styles.armBigDesc}>
                {telemetry?.armed ? 'Armado — toca para desarmar' : 'Stand-by — toca para armar'}
              </Text>
            </View>
          </TouchableOpacity>

          <View style={styles.quickGrid}>
            {[
              { id: 'TAKEOFF',  label: 'DESPEGUE', icon: '▲', color: '#00aaff' },
              { id: 'LAND',     label: 'ATERRIZAR', icon: '▼', color: '#ffaa00' },
              { id: 'RTL',      label: 'RTL',       icon: '⌂', color: '#ff8800' },
              { id: 'BRAKE',    label: 'FRENO',     icon: '⊗', color: '#ff4400' },
              { id: 'HOLD_POS', label: 'HOLD POS',  icon: '⊙', color: '#00ccaa' },
              { id: 'REBOOT',   label: 'REBOOT FC', icon: '↺', color: '#777' },
            ].map(a => (
              <TouchableOpacity
                key={a.id}
                style={[styles.quickBtn, { borderColor: a.color + '40', backgroundColor: a.color + '12' }]}
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
                        borderColor: isActive ? m.color : m.color + '25',
                        backgroundColor: isActive ? m.color + '22' : m.color + '08',
                      }]}
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
              <Text style={[styles.batteryPct, { color: batColor }]}>{batPct.toFixed(0)}%</Text>
              <Text style={[styles.batteryV, { color: batColor + 'aa' }]}>
                {(Number(telemetry?.battery_voltage ?? 0)).toFixed(2)} V
              </Text>
            </View>
            <View style={styles.batteryBar}>
              <View style={[styles.batteryFill, { width: `${batPct}%`, backgroundColor: batColor }]} />
            </View>
          </View>

          <View style={{ height: 32 }} />
        </ScrollView>
      </Animated.View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#050508' },
  edgeZone: { position: 'absolute', left: 0, top: 60, bottom: 0, width: 18, zIndex: 10 },

  /* ── HUD SECTION ── */
  hudSection: { flex: 1.5 },
  videoContainer: { flex: 0.7, backgroundColor: '#000' },
  centralHudPanel: {
    flex: 0.3,
    backgroundColor: 'rgba(5,5,8,0.95)',
    borderTopWidth: 1,
    borderTopColor: '#0d0d1a',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  hudGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: 6,
  },
  hudCard: {
    width: '23%',
    backgroundColor: 'rgba(15,15,25,0.9)',
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 6,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(0,255,136,0.3)',
    minHeight: 55,
    justifyContent: 'center',
    shadowColor: '#00ff88',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 3,
  },
  hudCardLabel: { color: '#888', fontSize: 9, fontWeight: '700', letterSpacing: 1, marginBottom: 3 },
  hudCardValue: { color: '#00ff88', fontSize: 16, fontWeight: '900', textAlign: 'center' },
  hudCardUnit: { color: '#aaa', fontSize: 8, fontWeight: '600', textAlign: 'center' },
  video: { width: '100%', height: '100%', backgroundColor: 'transparent' },
  vignette: {
    position: 'absolute', width: '100%', height: '100%',
    borderWidth: 30, borderColor: 'rgba(0,0,0,0.5)',
  },
  cameraOverlay: {
    position: 'absolute', width: '100%', height: '100%',
    justifyContent: 'center', alignItems: 'center',
    backgroundColor: '#050508', gap: 4,
  },
  cameraOverlayIcon: { fontSize: 28 },
  cameraOverlayText: { color: '#444', fontSize: 11, fontWeight: '800', letterSpacing: 2 },
  cameraOverlaySub: { color: '#333', fontSize: 9, fontWeight: '600', letterSpacing: 1 },

  hudOverlay: { position: 'absolute', width: '100%', height: '100%' },

  /* ── Crosshair ── */
  crosshairWrap: {
    position: 'absolute', top: '50%', left: '50%',
    width: 56, height: 56, marginLeft: -28, marginTop: -28,
    justifyContent: 'center', alignItems: 'center',
  },
  crosshairH: { position: 'absolute', width: 56, height: 1, backgroundColor: 'rgba(0,255,136,0.45)' },
  crosshairV: { position: 'absolute', width: 1, height: 56, backgroundColor: 'rgba(0,255,136,0.45)' },
  crosshairCenter: { width: 5, height: 5, borderRadius: 3, backgroundColor: '#00ff88' },
  corner: { position: 'absolute', width: 10, height: 10, borderColor: 'rgba(0,255,136,0.7)' },
  cornerTL: { top: 0, left: 0, borderTopWidth: 2, borderLeftWidth: 2 },
  cornerTR: { top: 0, right: 0, borderTopWidth: 2, borderRightWidth: 2 },
  cornerBL: { bottom: 0, left: 0, borderBottomWidth: 2, borderLeftWidth: 2 },
  cornerBR: { bottom: 0, right: 0, borderBottomWidth: 2, borderRightWidth: 2 },

  /* ── Altitude bar ── */
  altBar: {
    position: 'absolute', left: 8, top: '12%', bottom: '12%',
    width: 28, alignItems: 'center', justifyContent: 'flex-end',
  },
  altFill: {
    position: 'absolute', bottom: 0, width: 3,
    backgroundColor: '#00ff88', borderRadius: 2, minHeight: 3,
  },
  altText: { color: '#00ff88', fontSize: 11, fontWeight: '900', marginBottom: 1 },
  altUnit: { color: '#00ff8866', fontSize: 7, fontWeight: '700' },

  /* ── Telemetry column ── */
  telemetryColumn: {
    position: 'absolute', right: 6, top: 6,
    gap: 3,
  },
  tCard: {
    backgroundColor: 'rgba(5,5,10,0.75)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(0,255,136,0.1)',
    minWidth: 52,
  },
  tLabel: { color: '#555', fontSize: 7, fontWeight: '700', letterSpacing: 1 },
  tValue: { color: '#00ff88', fontSize: 14, fontWeight: '900' },
  tUnit: { color: '#446', fontSize: 7, fontWeight: '600' },

  /* ── CONTROLS SECTION ── */
  controlsSection: { flex: 0.9, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 12 },

  tacticalRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },

  /* ── Emergency ── */
  emergencyPanel: {
    marginBottom: 12,
    padding: 8,
    backgroundColor: '#0d0005',
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: '#ff004440',
    shadowColor: '#ff0044',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 5,
  },
  emergencyButtons: { flexDirection: 'row', gap: 8 },
  emergencyBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: 'center',
    borderWidth: 1.5,
    gap: 3,
    shadowColor: '#ff0044',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 3,
  },
  emergencyIcon: { fontSize: 16, lineHeight: 20 },
  emergencyLabel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },

  /* ── Joysticks ── */
  joystickArea: { flex: 1, flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center', paddingHorizontal: 30 },
  joystickCol: { alignItems: 'center', gap: 4 },
  joystickLabel: { color: '#444', fontSize: 8, fontWeight: '700', letterSpacing: 1.2 },

  pwmRow: { flexDirection: 'row', gap: 4, marginTop: 3 },
  pwmChip: {
    alignItems: 'center',
    backgroundColor: '#0a0a14',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderWidth: 1,
    borderColor: '#1a1a2a',
  },
  pwmLabel: { color: '#333', fontSize: 6, fontWeight: '800', letterSpacing: 0.8 },
  pwmValue: { fontSize: 10, fontWeight: '900', letterSpacing: 0.3 },

  /* ── Center info ── */
  centerCol: { alignItems: 'center', justifyContent: 'center' },
  centerCard: {
    alignItems: 'center',
    backgroundColor: 'rgba(10,10,20,0.8)',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#1a1a2a',
    gap: 1,
  },
  centerLabel: { color: '#444', fontSize: 8, fontWeight: '700', letterSpacing: 1 },
  centerValue: { color: '#00ff88', fontSize: 15, fontWeight: '900' },
  centerValueSmall: { color: '#888', fontSize: 12, fontWeight: '800' },
  centerUnit: { color: '#333', fontSize: 7, fontWeight: '600' },
  centerDivider: { width: 20, height: 1, backgroundColor: '#222', marginVertical: 2 },

  /* ── Backdrop & Side panel ── */
  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 20 },

  sidePanel: {
    position: 'absolute', top: 0, bottom: 0, left: 0,
    width: PANEL_WIDTH,
    backgroundColor: '#07070d',
    borderRightWidth: 1, borderRightColor: '#00ff8820',
    zIndex: 30,
  },
  panelHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 18, paddingTop: 18, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#0d0d1a' },
  panelTitle: { color: '#fff', fontSize: 18, fontWeight: '900', letterSpacing: 2 },
  panelSubtitle: { color: '#444', fontSize: 10, fontWeight: '600', letterSpacing: 1, marginTop: 2 },
  closeBtn: { width: 30, height: 30, borderRadius: 15, backgroundColor: '#1a1a2a', justifyContent: 'center', alignItems: 'center' },
  closeBtnText: { color: '#666', fontSize: 14, fontWeight: '700' },

  connBar: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 14, marginTop: 10, marginBottom: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, gap: 8 },
  connDot: { width: 6, height: 6, borderRadius: 3 },
  connText: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },

  panelScroll: { flex: 1, paddingHorizontal: 14 },
  sectionLabel: { color: '#2a2a3a', fontSize: 9, fontWeight: '800', letterSpacing: 2, marginTop: 18, marginBottom: 8 },

  armBigBtn: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 12, borderWidth: 1.5, marginBottom: 10, gap: 12 },
  armBigIcon: { fontSize: 26 },
  armBigLabel: { fontSize: 15, fontWeight: '900', letterSpacing: 1 },
  armBigDesc: { color: '#555', fontSize: 10, fontWeight: '600', marginTop: 2 },

  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  quickBtn: { width: '30.5%', aspectRatio: 1.2, borderRadius: 10, borderWidth: 1, justifyContent: 'center', alignItems: 'center', gap: 4 },
  quickBtnIcon: { fontSize: 20 },
  quickBtnLabel: { fontSize: 8, fontWeight: '800', letterSpacing: 0.5, textAlign: 'center' },

  modeGroup: { gap: 6, marginBottom: 4 },
  modeBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1 },
  modeBtnLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  modeBtnIcon: { fontSize: 18, width: 24, textAlign: 'center' },
  modeBtnName: { fontSize: 13, fontWeight: '800', letterSpacing: 0.5 },
  modeBtnDesc: { color: '#444', fontSize: 9, fontWeight: '600', marginTop: 2 },
  gpsBadge: { backgroundColor: '#00aaff20', borderWidth: 1, borderColor: '#00aaff40', borderRadius: 4, paddingHorizontal: 4, paddingVertical: 1 },
  gpsBadgeText: { color: '#00aaff', fontSize: 7, fontWeight: '800', letterSpacing: 0.5 },
  activeModeDot: { width: 8, height: 8, borderRadius: 4 },

  batteryPanel: { backgroundColor: '#0a0a14', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#1a1a2a' },
  batteryTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 },
  batteryPct: { fontSize: 32, fontWeight: '900' },
  batteryV: { fontSize: 16, fontWeight: '700' },
  batteryBar: { height: 8, backgroundColor: '#0d0d1a', borderRadius: 4, overflow: 'hidden' },
  batteryFill: { height: '100%', borderRadius: 4 },
});
