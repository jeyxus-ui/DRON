import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Dimensions,
  SafeAreaView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone } from '../context/DroneContext';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

const MODE_COLORS: Record<string, string> = {
  STABILIZE: '#14B8A6',
  ALT_HOLD: '#00d4ff',
  LOITER: '#00aaff',
  AUTO: '#aa88ff',
  GUIDED: '#cc88ff',
  RTL: '#ff8800',
  LAND: '#ffaa00',
  POSHOLD: '#00ccaa',
  BRAKE: '#ff4400',
  CIRCLE: '#88aaff',
  SPORT: '#ffcc00',
  ACRO: '#ff6688',
  UNKNOWN: '#555',
};

const getModeColor = (mode: string) => MODE_COLORS[mode] ?? '#888';

export const TelemetryScreen: React.FC = () => {
  const { telemetry, connected } = useDrone();

  const alt = Number(telemetry?.altitude ?? 0);
  const lat = Number(telemetry?.latitude ?? 0);
  const lon = Number(telemetry?.longitude ?? 0);
  const sat = Number(telemetry?.satellites ?? 0);
  const hdop = Number(telemetry?.hdop ?? 0);
  const roll = Number(telemetry?.roll ?? 0);
  const pitch = Number(telemetry?.pitch ?? 0);
  const yaw = Number(telemetry?.yaw ?? 0);
  const gs = Number(telemetry?.ground_speed ?? 0);
  const vs = Number(telemetry?.vertical_speed ?? 0);
  const batV = Number(telemetry?.battery_voltage ?? 0);
  const batPct = Number(telemetry?.battery_remaining ?? 0);
  const mode = String(telemetry?.mode ?? 'UNKNOWN');
  const armed = Boolean(telemetry?.armed);

  const batColor = batPct > 50 ? '#14B8A6' : batPct > 20 ? '#ffaa00' : '#ff0044';
  const satColor = sat >= 8 ? '#14B8A6' : sat >= 5 ? '#ffaa00' : '#ff4444';
  const modeColor = getModeColor(mode);
  const insets = useSafeAreaInsets();

  // Horizon indicator (simple roll/pitch visual)
  const horizonRollDeg = Math.max(-45, Math.min(45, roll));
  const horizonPitchOffset = Math.max(-30, Math.min(30, pitch * 1.5));

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <View>
          <Text style={styles.title}>TELEMETRÍA</Text>
          <Text style={styles.subtitle}>Datos en tiempo real</Text>
        </View>
        <View style={[styles.connBadge, { borderColor: connected ? '#14B8A640' : '#ff004440', backgroundColor: connected ? '#14B8A612' : '#ff004412' }]}>
          <View style={[styles.connDot, { backgroundColor: connected ? '#14B8A6' : '#ff0044' }]} />
          <Text style={[styles.connText, { color: connected ? '#14B8A6' : '#ff4444' }]}>
            {connected ? 'ONLINE' : 'OFFLINE'}
          </Text>
        </View>
      </View>

      <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>

        {/* ── ESTADO GENERAL ── */}
        <Text style={styles.sectionLabel}>ESTADO GENERAL</Text>
        <View style={styles.statusRow}>
          {/* Modo */}
          <View style={[styles.statusCard, { borderColor: modeColor + '50', flex: 1.2 }]}>
            <Text style={styles.statusCardLabel}>MODO</Text>
            <View style={[styles.modePill, { backgroundColor: modeColor + '20', borderColor: modeColor + '60' }]}>
              <View style={[styles.modeDot, { backgroundColor: modeColor }]} />
              <Text style={[styles.modePillText, { color: modeColor, textShadowColor: modeColor }]}>{mode}</Text>
            </View>
          </View>

          {/* Estado ARM */}
          <View style={[styles.statusCard, {
            borderColor: armed ? '#ff004450' : '#33333360',
            flex: 1,
            backgroundColor: armed ? '#ff000010' : '#0a0a14',
          }]}>
            <Text style={styles.statusCardLabel}>ESTADO</Text>
            <Text style={[styles.statusCardValue, { color: armed ? '#ff4466' : '#555', textShadowColor: armed ? '#ff4466' : 'transparent', textShadowOffset: { width: 0, height: 0 }, textShadowRadius: armed ? 8 : 0 }]}>
              {armed ? '⚡ ARMADO' : '● STANDBY'}
            </Text>
          </View>
        </View>

        {/* ── HORIZON INDICATOR ── */}
        <Text style={styles.sectionLabel}>ACTITUD</Text>
        <View style={styles.attitudeContainer}>
          {/* Artificial Horizon */}
          <View style={styles.horizonWrap}>
            <View style={styles.horizonMask}>
              <View style={[styles.horizonInner, {
                transform: [
                  { rotate: `${-horizonRollDeg}deg` },
                  { translateY: horizonPitchOffset },
                ],
              }]}>
                {/* Sky */}
                <View style={styles.horizonSky} />
                {/* Ground */}
                <View style={styles.horizonGround} />
                {/* Horizon line */}
                <View style={styles.horizonLine} />
                {/* Pitch lines */}
                {[-10, -5, 5, 10].map((deg) => (
                  <View key={deg} style={[styles.pitchLine, { top: '50%', marginTop: deg * 2.5 }]}>
                    <Text style={styles.pitchLineText}>{deg > 0 ? '+' : ''}{deg}</Text>
                  </View>
                ))}
              </View>
              {/* Center reticle - fixed */}
              <View style={styles.horizonReticle}>
                <View style={styles.reticleLeft} />
                <View style={styles.reticleDot} />
                <View style={styles.reticleRight} />
              </View>
            </View>
          </View>

          {/* Valores numéricos actitud */}
          <View style={styles.attitudeValues}>
            {[
              { label: 'ROLL', value: roll.toFixed(1), unit: '°', color: '#00aaff' },
              { label: 'PITCH', value: pitch.toFixed(1), unit: '°', color: '#14B8A6' },
              { label: 'YAW', value: yaw.toFixed(1), unit: '°', color: '#ffaa00' },
            ].map((item) => (
              <View key={item.label} style={styles.attValCard}>
                <Text style={styles.attValLabel}>{item.label}</Text>
                <Text style={[styles.attValNumber, { color: item.color, textShadowColor: item.color }]}>{item.value}</Text>
                <Text style={styles.attValUnit}>{item.unit}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ── VELOCIDAD ── */}
        <Text style={styles.sectionLabel}>VELOCIDAD</Text>
        <View style={styles.speedRow}>
          <View style={styles.speedCard}>
            <Text style={styles.speedLabel}>HORIZONTAL</Text>
            <Text style={styles.speedValue}>{gs.toFixed(2)}</Text>
            <Text style={styles.speedUnit}>m/s</Text>
            {/* Barra de velocidad */}
            <View style={styles.speedBar}>
              <View style={[styles.speedFill, { width: `${Math.min(gs / 15 * 100, 100)}%`, backgroundColor: '#14B8A6' }]} />
            </View>
          </View>

          <View style={styles.speedCard}>
            <Text style={styles.speedLabel}>VERTICAL</Text>
            <Text style={[styles.speedValue, { color: vs >= 0 ? '#14B8A6' : '#ff6644', textShadowColor: vs >= 0 ? '#14B8A6' : '#ff6644' }]}>
              {vs >= 0 ? '+' : ''}{vs.toFixed(2)}
            </Text>
            <Text style={styles.speedUnit}>m/s</Text>
            <View style={styles.speedBar}>
              <View style={[styles.speedFill, {
                width: `${Math.min(Math.abs(vs) / 5 * 100, 100)}%`,
                backgroundColor: vs >= 0 ? '#14B8A6' : '#ff6644',
              }]} />
            </View>
          </View>
        </View>

        {/* ── POSICIÓN ── */}
        <Text style={styles.sectionLabel}>POSICIÓN & GPS</Text>
        <View style={styles.dataContainer}>
          {[
            { label: 'Altitud', value: alt.toFixed(2), unit: 'm', color: '#14B8A6' },
            { label: 'Latitud', value: lat.toFixed(6), unit: '°', color: '#aaa' },
            { label: 'Longitud', value: lon.toFixed(6), unit: '°', color: '#aaa' },
            { label: 'Satélites', value: String(sat), unit: '', color: satColor },
            { label: 'HDOP', value: hdop.toFixed(2), unit: '', color: hdop < 2 ? '#14B8A6' : hdop < 5 ? '#ffaa00' : '#ff4444' },
          ].map((row, i, arr) => (
            <View key={row.label} style={[styles.dataRow, i === arr.length - 1 && { borderBottomWidth: 0 }]}>
              <Text style={styles.rowLabel}>{row.label}</Text>
              <Text style={[styles.rowValue, { color: row.color, textShadowColor: row.color, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 3 }]}>
                {row.value} <Text style={styles.rowUnit}>{row.unit}</Text>
              </Text>
            </View>
          ))}
        </View>

        {/* ── BATERÍA ── */}
        <Text style={styles.sectionLabel}>BATERÍA</Text>
        <View style={styles.batteryCard}>
          {/* Porcentaje grande */}
          <View style={styles.batteryTopRow}>
            <Text style={[styles.batteryPct, { color: batColor, textShadowColor: batColor }]}>{batPct.toFixed(0)}%</Text>
            <Text style={[styles.batteryVoltage, { color: batColor, textShadowColor: batColor, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 4 }]}>{batV.toFixed(2)} V</Text>
          </View>

          {/* Barra */}
          <View style={styles.batteryBarWrap}>
            <View style={[styles.batteryBarFill, {
              width: `${batPct}%`,
              backgroundColor: batColor,
            }]} />
            {/* Marcadores */}
            {[25, 50, 75].map((mark) => (
              <View key={mark} style={[styles.batteryMark, { left: `${mark}%` }]} />
            ))}
          </View>

          <View style={styles.batteryLabels}>
            <Text style={styles.batteryMarkLabel}>0%</Text>
            <Text style={styles.batteryMarkLabel}>25%</Text>
            <Text style={styles.batteryMarkLabel}>50%</Text>
            <Text style={styles.batteryMarkLabel}>75%</Text>
            <Text style={styles.batteryMarkLabel}>100%</Text>
          </View>
        </View>

        <View style={{ height: 24 }} />
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#050508',
  },

  // ── HEADER ──
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingBottom: 15,
    borderBottomWidth: 1.5,
    borderBottomColor: 'rgba(255,255,255,0.15)',
    backgroundColor: 'rgba(15,25,40,0.3)',
  },
  title: {
    fontSize: 22,
    fontWeight: '900',
    color: '#fff',
    letterSpacing: 3,
    textShadowColor: '#14B8A6',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 6,
  },
  subtitle: {
    fontSize: 10,
    color: '#444',
    fontWeight: '600',
    letterSpacing: 1,
    marginTop: 2,
  },
  connBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1.5,
    gap: 6,
    backgroundColor: 'rgba(15,25,40,0.3)',
  },
  connDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    shadowColor: '#14B8A6',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 6,
    elevation: 6,
  },
  connText: {
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1,
  },

  scrollView: {
    flex: 1,
    paddingHorizontal: 16,
  },
  sectionLabel: {
    fontSize: 10,
    fontWeight: '800',
    color: '#333',
    letterSpacing: 2,
    marginTop: 18,
    marginBottom: 10,
  },

  // ── STATUS ──
  statusRow: {
    flexDirection: 'row',
    gap: 10,
  },
  statusCard: {
    backgroundColor: 'rgba(20,30,50,0.25)',
    borderRadius: 16,
    padding: 14,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.1)',
    gap: 8,
  },
  statusCardLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: '#444',
    letterSpacing: 1,
  },
  statusCardValue: {
    fontSize: 16,
    fontWeight: '900',
    letterSpacing: 1,
  },
  modePill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    borderWidth: 1.5,
    gap: 6,
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(15,25,40,0.3)',
  },
  modeDot: { width: 6, height: 6, borderRadius: 3, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 1, shadowRadius: 6, elevation: 6 },
  modePillText: {
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 1,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 4,
  },

  // ── HORIZON ──
  attitudeContainer: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
  },
  horizonWrap: {
    width: 140,
    height: 110,
  },
  horizonMask: {
    width: 140,
    height: 110,
    borderRadius: 16,
    overflow: 'hidden',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.15)',
    position: 'relative',
    backgroundColor: 'rgba(15,25,40,0.3)',
  },
  horizonInner: {
    position: 'absolute',
    width: 280,
    height: 280,
    left: -70,
    top: -85,
  },
  horizonSky: {
    width: '100%',
    height: '50%',
    backgroundColor: '#001833',
  },
  horizonGround: {
    width: '100%',
    height: '50%',
    backgroundColor: '#1a0f00',
  },
  horizonLine: {
    position: 'absolute',
    top: '50%',
    left: 0,
    right: 0,
    height: 2,
    backgroundColor: '#14B8A6',
    marginTop: -1,
    shadowColor: '#14B8A6',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.9,
    shadowRadius: 4,
    elevation: 4,
  },
  pitchLine: {
    position: 'absolute',
    left: '30%',
    right: '30%',
    height: 1,
    backgroundColor: 'rgba(255,255,255,0.3)',
    flexDirection: 'row',
    justifyContent: 'center',
  },
  pitchLineText: {
    position: 'absolute',
    right: -20,
    top: -5,
    color: 'rgba(255,255,255,0.4)',
    fontSize: 7,
  },
  horizonReticle: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    flexDirection: 'row',
    alignItems: 'center',
    transform: [{ translateX: -40 }, { translateY: -4 }],
  },
  reticleLeft: {
    width: 30,
    height: 2,
    backgroundColor: '#ffcc00',
    marginRight: 4,
  },
  reticleDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#ffcc00',
    shadowColor: '#ffcc00',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 6,
    elevation: 6,
  },
  reticleRight: {
    width: 30,
    height: 2,
    backgroundColor: '#ffcc00',
    marginLeft: 4,
  },
  attitudeValues: {
    flex: 1,
    gap: 8,
  },
  attValCard: {
    backgroundColor: 'rgba(20,30,50,0.25)',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.1)',
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
  },
  attValLabel: {
    color: '#444',
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1,
    width: 36,
  },
  attValNumber: {
    fontSize: 18,
    fontWeight: '900',
    flex: 1,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 4,
  },
  attValUnit: {
    color: '#555',
    fontSize: 11,
    fontWeight: '600',
  },

  // ── VELOCIDAD ──
  speedRow: {
    flexDirection: 'row',
    gap: 10,
  },
  speedCard: {
    flex: 1,
    backgroundColor: 'rgba(20,30,50,0.25)',
    borderRadius: 16,
    padding: 14,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.1)',
    gap: 4,
  },
  speedLabel: {
    color: '#444',
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1,
  },
  speedValue: {
    color: '#14B8A6',
    fontSize: 26,
    fontWeight: '900',
    textShadowColor: '#14B8A6',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 4,
  },
  speedUnit: {
    color: '#444',
    fontSize: 10,
    fontWeight: '600',
    marginBottom: 6,
  },
  speedBar: {
    height: 4,
    backgroundColor: 'rgba(13,13,26,0.6)',
    borderRadius: 2,
    overflow: 'hidden',
  },
  speedFill: {
    height: '100%',
    borderRadius: 2,
  },

  // ── POSICIÓN ──
  dataContainer: {
    backgroundColor: 'rgba(20,30,50,0.25)',
    borderRadius: 16,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.1)',
    overflow: 'hidden',
  },
  dataRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1.5,
    borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  rowLabel: {
    color: '#555',
    fontSize: 13,
    fontWeight: '600',
  },
  rowValue: {
    fontSize: 14,
    fontWeight: '800',
    color: '#14B8A6',
  },
  rowUnit: {
    fontSize: 10,
    color: '#444',
    fontWeight: '600',
  },

  // ── BATERÍA ──
  batteryCard: {
    backgroundColor: 'rgba(20,30,50,0.25)',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  batteryTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 14,
  },
  batteryPct: {
    fontSize: 40,
    fontWeight: '900',
    letterSpacing: -1,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 6,
  },
  batteryVoltage: {
    fontSize: 18,
    fontWeight: '800',
  },
  batteryBarWrap: {
    height: 10,
    backgroundColor: '#0d0d1a',
    borderRadius: 5,
    overflow: 'visible',
    marginBottom: 6,
    position: 'relative',
  },
  batteryBarFill: {
    height: '100%',
    borderRadius: 5,
  },
  batteryMark: {
    position: 'absolute',
    top: -2,
    width: 1,
    height: 14,
    backgroundColor: '#050508',
  },
  batteryLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  batteryMarkLabel: {
    color: '#333',
    fontSize: 8,
    fontWeight: '600',
  },
});