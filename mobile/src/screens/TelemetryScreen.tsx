import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone } from '../context/DroneContext';
import { theme } from '../theme';

const C = theme.colors;

const MODE_COLORS: Record<string, string> = {
  STABILIZE: C.primary,
  ALT_HOLD: '#0EA5E9',
  LOITER: '#0891B2',
  AUTO: '#7C3AED',
  GUIDED: '#9333EA',
  RTL: '#EA580C',
  LAND: C.warning,
  POSHOLD: '#0D9488',
  BRAKE: C.danger,
  CIRCLE: '#4F46E5',
  SPORT: '#CA8A04',
  ACRO: '#E11D48',
  UNKNOWN: C.textMuted,
};

const getModeColor = (mode: string) => MODE_COLORS[mode] ?? C.textMuted;

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

  // Sensores
  const mtf01Dist = telemetry?.mtf01_distance;
  const lidarDist = telemetry?.lidar_closest_distance;
  const lidarAngle = telemetry?.lidar_closest_angle;
  const lidarPts = Number(telemetry?.lidar_points ?? 0);
  const obstacleAhead = Boolean(telemetry?.obstacle_ahead);

  const hasSensors = mtf01Dist != null || lidarDist != null;

  const batColor = batPct > 50 ? C.cyan : batPct > 20 ? C.warning : C.danger;
  const satColor = sat >= 8 ? C.cyan : sat >= 5 ? C.warning : C.danger;
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
        <View style={[styles.connBadge, { borderColor: connected ? '#38BDF8' + '66' : C.danger + '66' }]}>
          <View style={[styles.connDot, { backgroundColor: connected ? '#38BDF8' : '#F87171' }]} />
          <Text style={[styles.connText, { color: connected ? '#38BDF8' : '#F87171' }]}>
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
              <Text style={[styles.modePillText, { color: modeColor }]}>{mode}</Text>
            </View>
          </View>

          {/* Estado ARM */}
          <View style={[styles.statusCard, {
            borderColor: armed ? C.danger + '50' : C.textDim + '60',
            flex: 1,
            backgroundColor: armed ? C.danger + '10' : C.bgElevated,
          }]}>
            <Text style={styles.statusCardLabel}>ESTADO</Text>
            <Text style={[styles.statusCardValue, { color: armed ? C.danger : C.textMuted }]}>
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
              { label: 'ROLL', value: roll.toFixed(1), unit: '°', color: C.cyan },
              { label: 'PITCH', value: pitch.toFixed(1), unit: '°', color: C.primary },
              { label: 'YAW', value: yaw.toFixed(1), unit: '°', color: C.warning },
            ].map((item) => (
              <View key={item.label} style={styles.attValCard}>
                <Text style={styles.attValLabel}>{item.label}</Text>
                <Text style={[styles.attValNumber, { color: item.color }]}>{item.value}</Text>
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
              <View style={[styles.speedFill, { width: `${Math.min(gs / 15 * 100, 100)}%`, backgroundColor: C.cyan }]} />
            </View>
          </View>

          <View style={styles.speedCard}>
            <Text style={styles.speedLabel}>VERTICAL</Text>
            <Text style={[styles.speedValue, { color: vs >= 0 ? C.cyan : C.danger }]}>
              {vs >= 0 ? '+' : ''}{vs.toFixed(2)}
            </Text>
            <Text style={styles.speedUnit}>m/s</Text>
            <View style={styles.speedBar}>
              <View style={[styles.speedFill, {
                width: `${Math.min(Math.abs(vs) / 5 * 100, 100)}%`,
                backgroundColor: vs >= 0 ? C.cyan : C.danger,
              }]} />
            </View>
          </View>
        </View>

        {/* ── POSICIÓN ── */}
        <Text style={styles.sectionLabel}>POSICIÓN & GPS</Text>
        <View style={styles.dataContainer}>
          {[
            { label: 'Altitud', value: alt.toFixed(2), unit: 'm', color: C.cyan },
            { label: 'Latitud', value: lat.toFixed(6), unit: '°', color: C.textMuted },
            { label: 'Longitud', value: lon.toFixed(6), unit: '°', color: C.textMuted },
            { label: 'Satélites', value: String(sat), unit: '', color: satColor },
            { label: 'HDOP', value: hdop.toFixed(2), unit: '', color: hdop < 2 ? C.cyan : hdop < 5 ? C.warning : C.danger },
          ].map((row, i, arr) => (
            <View key={row.label} style={[styles.dataRow, i === arr.length - 1 && { borderBottomWidth: 0 }]}>
              <Text style={styles.rowLabel}>{row.label}</Text>
              <Text style={[styles.rowValue, { color: row.color }]}>
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
            <Text style={[styles.batteryPct, { color: batColor }]}>{batPct.toFixed(0)}%</Text>
            <Text style={[styles.batteryVoltage, { color: batColor }]}>{batV.toFixed(2)} V</Text>
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

        {/* ── SENSORES ── */}
        {hasSensors && (
          <>
            <Text style={styles.sectionLabel}>SENSORES</Text>
            <View style={styles.dataContainer}>
              {mtf01Dist != null && (
                <View style={[styles.dataRow, { borderBottomWidth: 1.5, borderBottomColor: C.hairline }]}>
                  <Text style={styles.rowLabel}>MTF01</Text>
                  <Text style={[styles.rowValue, { color: mtf01Dist < 2 ? C.danger : C.cyan }]}>
                    {mtf01Dist.toFixed(2)} <Text style={styles.rowUnit}>m</Text>
                  </Text>
                </View>
              )}
              {lidarDist != null && (
                <View style={[styles.dataRow, { borderBottomWidth: 1.5, borderBottomColor: C.hairline }]}>
                  <Text style={styles.rowLabel}>LIDAR close</Text>
                  <Text style={[styles.rowValue, { color: lidarDist < 2 ? C.danger : C.cyan }]}>
                    {lidarDist.toFixed(2)} <Text style={styles.rowUnit}>m</Text>
                  </Text>
                </View>
              )}
              {lidarAngle != null && (
                <View style={[styles.dataRow, { borderBottomWidth: 1.5, borderBottomColor: C.hairline }]}>
                  <Text style={styles.rowLabel}>LIDAR angle</Text>
                  <Text style={[styles.rowValue, { color: C.textMuted }]}>
                    {lidarAngle.toFixed(1)}°
                  </Text>
                </View>
              )}
              <View style={[styles.dataRow, { borderBottomWidth: 1.5, borderBottomColor: C.hairline }]}>
                <Text style={styles.rowLabel}>LIDAR points</Text>
                <Text style={[styles.rowValue, { color: C.textMuted }]}>{lidarPts}</Text>
              </View>
              <View style={[styles.dataRow, { borderBottomWidth: 0 }]}>
                <Text style={styles.rowLabel}>Obstáculo</Text>
                <Text style={[styles.rowValue, { color: obstacleAhead ? C.danger : C.cyan }]}>
                  {obstacleAhead ? '⚠ ADELANTE' : 'DESPEJADO'}
                </Text>
              </View>
            </View>
          </>
        )}

        <View style={{ height: 24 }} />
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: C.bg,
  },

  // ── HEADER ──
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingBottom: 15,
    borderBottomWidth: 1.5,
    borderBottomColor: C.navyElevated,
    backgroundColor: C.navy,
  },
  title: {
    fontSize: 22,
    fontWeight: '900',
    color: C.surface,
    letterSpacing: 3,
  },
  subtitle: {
    fontSize: 10,
    color: 'rgba(255,255,255,0.65)',
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
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  connDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
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
    color: C.textDim,
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
    backgroundColor: C.surface,
    borderRadius: 16,
    padding: 14,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    gap: 8,
  },
  statusCardLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: C.textMuted,
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
    backgroundColor: C.glass,
  },
  modeDot: { width: 6, height: 6, borderRadius: 3 },
  modePillText: {
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 1,
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
    borderColor: C.hairlineStrong,
    position: 'relative',
    backgroundColor: C.glass,
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
    backgroundColor: '#7EC8E3',
  },
  horizonGround: {
    width: '100%',
    height: '50%',
    backgroundColor: '#C9A05C',
  },
  horizonLine: {
    position: 'absolute',
    top: '50%',
    left: 0,
    right: 0,
    height: 2,
    backgroundColor: C.navy,
    marginTop: -1,
  },
  pitchLine: {
    position: 'absolute',
    left: '30%',
    right: '30%',
    height: 1,
    backgroundColor: 'rgba(15,42,74,0.5)',
    flexDirection: 'row',
    justifyContent: 'center',
  },
  pitchLineText: {
    position: 'absolute',
    right: -20,
    top: -5,
    color: 'rgba(15,42,74,0.6)',
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
    backgroundColor: C.navy,
    marginRight: 4,
  },
  reticleDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: C.navy,
  },
  reticleRight: {
    width: 30,
    height: 2,
    backgroundColor: C.navy,
    marginLeft: 4,
  },
  attitudeValues: {
    flex: 1,
    gap: 8,
  },
  attValCard: {
    backgroundColor: C.surface,
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
  },
  attValLabel: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1,
    width: 36,
  },
  attValNumber: {
    fontSize: 18,
    fontWeight: '900',
    flex: 1,
  },
  attValUnit: {
    color: C.textMuted,
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
    backgroundColor: C.surface,
    borderRadius: 16,
    padding: 14,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    gap: 4,
  },
  speedLabel: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1,
  },
  speedValue: {
    color: C.cyan,
    fontSize: 26,
    fontWeight: '900',
  },
  speedUnit: {
    color: C.textMuted,
    fontSize: 10,
    fontWeight: '600',
    marginBottom: 6,
  },
  speedBar: {
    height: 4,
    backgroundColor: C.bgElevated,
    borderRadius: 2,
    overflow: 'hidden',
  },
  speedFill: {
    height: '100%',
    borderRadius: 2,
  },

  // ── POSICIÓN ──
  dataContainer: {
    backgroundColor: C.surface,
    borderRadius: 16,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    overflow: 'hidden',
  },
  dataRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1.5,
    borderBottomColor: C.hairline,
  },
  rowLabel: {
    color: C.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  rowValue: {
    fontSize: 14,
    fontWeight: '800',
    color: C.cyan,
  },
  rowUnit: {
    fontSize: 10,
    color: C.textMuted,
    fontWeight: '600',
  },

  // ── BATERÍA ──
  batteryCard: {
    backgroundColor: C.surface,
    borderRadius: 16,
    padding: 16,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
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
  },
  batteryVoltage: {
    fontSize: 18,
    fontWeight: '800',
  },
  batteryBarWrap: {
    height: 10,
    backgroundColor: C.bgElevated,
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
    backgroundColor: C.textDim,
  },
  batteryLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  batteryMarkLabel: {
    color: C.textDim,
    fontSize: 8,
    fontWeight: '600',
  },
});