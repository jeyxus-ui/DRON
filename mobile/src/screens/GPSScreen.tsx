import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  Animated,
  ScrollView,
} from 'react-native';
import MapView, { Marker, Polyline, Circle, MapPressEvent } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone } from '../context/DroneContext';
import { theme } from '../theme';

const C = theme.colors;

interface Waypoint {
  id:        string;
  latitude:  number;
  longitude: number;
  altitude:  number;
  label:     number;
}

const GPS_QUALITY = (hdop: number, sat: number) => {
  if (sat >= 8 && hdop < 1.5) return { label: 'EXCELENTE', color: C.cyan };
  if (sat >= 6 && hdop < 2.5) return { label: 'BUENO',     color: C.success };
  if (sat >= 5 && hdop < 5)   return { label: 'REGULAR',   color: C.warning };
  return                               { label: 'MALO',      color: C.danger };
};

export const GPSScreen: React.FC = () => {
  const { telemetry, connected, sendCommand } = useDrone();
  const insets = useSafeAreaInsets();

  const lat  = Number(telemetry?.latitude  ?? 0);
  const lon  = Number(telemetry?.longitude ?? 0);
  const alt  = Number(telemetry?.altitude  ?? 0);
  const sat  = Number(telemetry?.satellites ?? 0);
  const hdop = Number(telemetry?.hdop ?? 0);
  const hasGPS = lat !== 0 || lon !== 0;

  const [waypoints, setWaypoints]     = useState<Waypoint[]>([]);
  const [targetWp, setTargetWp]       = useState<Waypoint | null>(null);
  const [mapType, setMapType]         = useState<'satellite' | 'standard'>('satellite');
  const [followDrone, setFollowDrone] = useState(true);
  const [gotoAlt, setGotoAlt]         = useState(10);

  const mapRef    = useRef<MapView>(null);
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const fadeAnim  = useRef(new Animated.Value(0)).current;

  const gpsQuality = GPS_QUALITY(hdop, sat);

  // ── Pulso del marcador del dron ──────────────────────────────────────────
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.6, duration: 900, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1,   duration: 900, useNativeDriver: true }),
      ])
    ).start();
  }, []);

  // ── Fade in al montar ─────────────────────────────────────────────────────
  useEffect(() => {
    Animated.timing(fadeAnim, { toValue: 1, duration: 400, useNativeDriver: true }).start();
  }, []);

  // ── Seguir al dron ────────────────────────────────────────────────────────
  useEffect(() => {
    if (followDrone && hasGPS && mapRef.current) {
      mapRef.current.animateToRegion({
        latitude:       lat,
        longitude:      lon,
        latitudeDelta:  0.001,
        longitudeDelta: 0.001,
      }, 800);
    }
  }, [lat, lon, followDrone]);

  // ── Toque en el mapa → waypoint ───────────────────────────────────────────
  const handleMapPress = (e: MapPressEvent) => {
    const { latitude, longitude } = e.nativeEvent.coordinate;

    Alert.alert(
      '📍 Nuevo waypoint',
      `¿Enviar el dron a esta posición?\n\nLat: ${latitude.toFixed(6)}\nLon: ${longitude.toFixed(6)}\nAltitud: ${gotoAlt}m`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Solo marcar',
          onPress: () => {
            const wp: Waypoint = {
              id:        Date.now().toString(),
              latitude,
              longitude,
              altitude:  gotoAlt,
              label:     waypoints.length + 1,
            };
            setWaypoints(prev => [...prev, wp]);
          },
        },
        {
          text: 'Ir ahora',
          onPress: () => {
            const wp: Waypoint = {
              id:        Date.now().toString(),
              latitude,
              longitude,
              altitude:  gotoAlt,
              label:     waypoints.length + 1,
            };
            setWaypoints(prev => [...prev, wp]);
            setTargetWp(wp);
            sendCommand('GOTO', { latitude, longitude, altitude: gotoAlt });
          },
        },
      ]
    );
  };

  const handleGotoWaypoint = (wp: Waypoint) => {
    Alert.alert(
      `Waypoint ${wp.label}`,
      `¿Enviar el dron al waypoint ${wp.label}?\n\nLat: ${wp.latitude.toFixed(6)}\nLon: ${wp.longitude.toFixed(6)}\nAlt: ${wp.altitude}m`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Ir',
          onPress: () => {
            setTargetWp(wp);
            sendCommand('GOTO', { latitude: wp.latitude, longitude: wp.longitude, altitude: wp.altitude });
          },
        },
      ]
    );
  };

  const handleDeleteWaypoint = (id: string) => {
    setWaypoints(prev => prev.filter(w => w.id !== id));
    if (targetWp?.id === id) setTargetWp(null);
  };

  const clearWaypoints = () => {
    Alert.alert('Limpiar', '¿Eliminar todos los waypoints?', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Limpiar', style: 'destructive', onPress: () => { setWaypoints([]); setTargetWp(null); } },
    ]);
  };

  // ── Línea de ruta: dron → waypoints ──────────────────────────────────────
  const routeCoords = hasGPS
    ? [{ latitude: lat, longitude: lon }, ...waypoints.map(w => ({ latitude: w.latitude, longitude: w.longitude }))]
    : waypoints.map(w => ({ latitude: w.latitude, longitude: w.longitude }));

  // ── Región inicial ────────────────────────────────────────────────────────
  const initialRegion = {
    latitude:       hasGPS ? lat : 4.711,   // Bogotá por defecto
    longitude:      hasGPS ? lon : -74.0721,
    latitudeDelta:  0.005,
    longitudeDelta: 0.005,
  };

  return (
    <Animated.View style={[styles.container, { opacity: fadeAnim }]}>

      {/* ══ MAPA ══ */}
      <MapView
        ref={mapRef}
        style={styles.map}
        mapType={mapType}
        initialRegion={initialRegion}
        onPress={handleMapPress}
        onTouchStart={() => setFollowDrone(false)}
        showsUserLocation={false}
        showsCompass={false}
        showsScale={false}
        rotateEnabled={false}
      >
        {/* Línea de ruta */}
        {routeCoords.length >= 2 && (
          <Polyline
            coordinates={routeCoords}
            strokeColor="#00B4D888"
            strokeWidth={1.5}
            lineDashPattern={[6, 4]}
          />
        )}

        {/* Marcador dron */}
        {hasGPS && (
          <Marker coordinate={{ latitude: lat, longitude: lon }} anchor={{ x: 0.5, y: 0.5 }}>
            <View style={styles.droneMarkerWrap}>
              <Animated.View style={[styles.dronePulse, {
                transform: [{ scale: pulseAnim }],
                backgroundColor: connected ? C.cyan + '22' : C.danger + '22',
                borderColor:     connected ? C.cyan + '66' : C.danger + '66',
              }]} />
              <View style={[styles.droneDot, { backgroundColor: connected ? C.cyan : C.danger }]}>
                <Text style={styles.droneIcon}>✈</Text>
              </View>
            </View>
          </Marker>
        )}

        {/* Waypoints */}
        {waypoints.map(wp => (
          <Marker
            key={wp.id}
            coordinate={{ latitude: wp.latitude, longitude: wp.longitude }}
            anchor={{ x: 0.5, y: 0.5 }}
            onPress={() => handleGotoWaypoint(wp)}
          >
            <View style={[
              styles.wpMarker,
              targetWp?.id === wp.id && styles.wpMarkerActive,
            ]}>
              <Text style={styles.wpMarkerText}>{wp.label}</Text>
            </View>
          </Marker>
        ))}

        {/* Círculo de precisión GPS */}
        {hasGPS && hdop > 0 && (
          <Circle
            center={{ latitude: lat, longitude: lon }}
            radius={hdop * 3}
            fillColor="rgba(0,180,216,0.06)"
            strokeColor="rgba(0,180,216,0.25)"
            strokeWidth={1}
          />
        )}
      </MapView>

      {/* ══ HUD SUPERIOR ══ */}
      <View style={[styles.topHud, { paddingTop: insets.top + 8 }]}>
        {/* Calidad GPS */}
        <View style={[styles.gpsPill, { borderColor: gpsQuality.color + '60', backgroundColor: gpsQuality.color + '15' }]}>
          <View style={[styles.gpsDot, { backgroundColor: gpsQuality.color }]} />
          <Text style={[styles.gpsPillText, { color: gpsQuality.color }]}>
            GPS {gpsQuality.label}
          </Text>
        </View>

        {/* Chips SAT / HDOP */}
        <View style={styles.hudChips}>
          <View style={styles.hudChip}>
            <Text style={styles.hudChipLabel}>SAT</Text>
            <Text style={[styles.hudChipValue, { color: sat >= 6 ? C.cyan : C.danger }]}>{sat}</Text>
          </View>
          <View style={styles.hudChip}>
            <Text style={styles.hudChipLabel}>HDOP</Text>
            <Text style={[styles.hudChipValue, { color: hdop < 2 ? C.cyan : hdop < 5 ? C.warning : C.danger }]}>
              {hdop.toFixed(1)}
            </Text>
          </View>
          <View style={styles.hudChip}>
            <Text style={styles.hudChipLabel}>ALT</Text>
            <Text style={styles.hudChipValue}>{alt.toFixed(1)}<Text style={styles.hudChipUnit}>m</Text></Text>
          </View>
        </View>
      </View>

      {/* ══ BOTONES DERECHA ══ */}
      <View style={[styles.rightButtons, { top: insets.top + 70 }]}>
        {/* Tipo de mapa */}
        <TouchableOpacity
          style={styles.mapBtn}
          onPress={() => setMapType(t => t === 'satellite' ? 'standard' : 'satellite')}
          activeOpacity={0.8}
        >
          <Text style={styles.mapBtnText}>{mapType === 'satellite' ? '🗺' : '🛰'}</Text>
        </TouchableOpacity>

        {/* Seguir dron */}
        <TouchableOpacity
          style={[styles.mapBtn, followDrone && styles.mapBtnActive]}
          onPress={() => {
            setFollowDrone(true);
            if (hasGPS && mapRef.current) {
              mapRef.current.animateToRegion({
                latitude: lat, longitude: lon,
                latitudeDelta: 0.001, longitudeDelta: 0.001,
              }, 600);
            }
          }}
          activeOpacity={0.8}
        >
          <Text style={styles.mapBtnText}>⌖</Text>
        </TouchableOpacity>

        {/* Limpiar waypoints */}
        {waypoints.length > 0 && (
          <TouchableOpacity style={styles.mapBtn} onPress={clearWaypoints} activeOpacity={0.8}>
            <Text style={styles.mapBtnText}>✕</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* ══ PANEL INFERIOR ══ */}
      <View style={[styles.bottomPanel, { paddingBottom: insets.bottom + 8 }]}>

        {/* Coordenadas del dron */}
        <View style={styles.coordRow}>
          <View style={styles.coordItem}>
            <Text style={styles.coordLabel}>LATITUD</Text>
            <Text style={styles.coordValue}>{hasGPS ? lat.toFixed(6) : '—'}</Text>
          </View>
          <View style={styles.coordDivider} />
          <View style={styles.coordItem}>
            <Text style={styles.coordLabel}>LONGITUD</Text>
            <Text style={styles.coordValue}>{hasGPS ? lon.toFixed(6) : '—'}</Text>
          </View>
        </View>

        {/* Altitud del goto + selector */}
        <View style={styles.altRow}>
          <Text style={styles.altLabel}>ALT. WAYPOINT</Text>
          <View style={styles.altControls}>
            {[5, 10, 20, 30, 50].map(a => (
              <TouchableOpacity
                key={a}
                style={[styles.altBtn, gotoAlt === a && styles.altBtnActive]}
                onPress={() => setGotoAlt(a)}
                activeOpacity={0.8}
              >
                <Text style={[styles.altBtnText, gotoAlt === a && styles.altBtnTextActive]}>
                  {a}m
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Lista waypoints */}
        {waypoints.length > 0 && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.wpList}
            contentContainerStyle={styles.wpListContent}
          >
            {waypoints.map(wp => (
              <TouchableOpacity
                key={wp.id}
                style={[styles.wpChip, targetWp?.id === wp.id && styles.wpChipActive]}
                onPress={() => handleGotoWaypoint(wp)}
                onLongPress={() => handleDeleteWaypoint(wp.id)}
                activeOpacity={0.8}
              >
                <Text style={[styles.wpChipNum, targetWp?.id === wp.id && { color: C.cyan }]}>
                  WP{wp.label}
                </Text>
                <Text style={styles.wpChipCoord}>
                  {wp.latitude.toFixed(4)}, {wp.longitude.toFixed(4)}
                </Text>
                <Text style={styles.wpChipAlt}>{wp.altitude}m</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}

        {/* Hint */}
        {waypoints.length === 0 && (
          <Text style={styles.hint}>
            Toca el mapa para agregar un waypoint · Mantén para eliminar
          </Text>
        )}
      </View>

      {/* Sin GPS overlay */}
      {!hasGPS && (
        <View style={styles.noGpsOverlay}>
          <Text style={styles.noGpsIcon}>🛰</Text>
          <Text style={styles.noGpsTitle}>Esperando señal GPS</Text>
          <Text style={styles.noGpsDesc}>{sat} satélites detectados</Text>
        </View>
      )}
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  map:       { flex: 1 },

  // ── HUD SUPERIOR ──
  topHud: {
    position:       'absolute',
    top:            0,
    left:           0,
    right:          0,
    flexDirection:  'row',
    justifyContent: 'space-between',
    alignItems:     'center',
    paddingHorizontal: 12,
    paddingBottom:  8,
  },
  gpsPill: {
    flexDirection:  'row',
    alignItems:     'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius:   20,
    borderWidth:    1.5,
    gap:            6,
    backgroundColor: C.glass,
  },
  gpsDot:      { width: 6, height: 6, borderRadius: 3 },
  gpsPillText: { fontSize: 10, fontWeight: '800', letterSpacing: 1 },

  hudChips:    { flexDirection: 'row', gap: 6 },
  hudChip: {
    alignItems:      'center',
    backgroundColor: C.glass,
    borderRadius:    12,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderWidth:     1.5,
    borderColor:     C.cyan + '88',
    minWidth:        44,
  },
  hudChipLabel: { color: C.textMuted, fontSize: 7, fontWeight: '800', letterSpacing: 1 },
  hudChipValue: { color: C.cyan, fontSize: 13, fontWeight: '900' },
  hudChipUnit:  { color: C.textMuted, fontSize: 8 },

  // ── BOTONES DERECHA ──
  rightButtons: {
    position: 'absolute',
    right:    12,
    gap:      8,
  },
  mapBtn: {
    width:           42,
    height:          42,
    borderRadius:    14,
    backgroundColor: C.glass,
    borderWidth:     1.5,
    borderColor:     C.hairlineStrong,
    justifyContent:  'center',
    alignItems:      'center',
  },
  mapBtnActive: { borderColor: C.cyan, backgroundColor: C.cyan + '1A' },
  mapBtnText:   { fontSize: 16 },

  // ── MARCADOR DRON ──
  droneMarkerWrap: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  dronePulse: {
    position:     'absolute',
    width:        40,
    height:       40,
    borderRadius: 20,
    borderWidth:  1.5,
    borderColor:  'rgba(0,180,216,0.4)',
  },
  droneDot: {
    width:          26,
    height:         26,
    borderRadius:   13,
    justifyContent: 'center',
    alignItems:     'center',
    borderWidth:    2,
    borderColor:    C.cyan + '66',
  },
  droneIcon: { fontSize: 13, color: C.bg },

  // ── WAYPOINT MARKER ──
  wpMarker: {
    width:           28,
    height:          28,
    borderRadius:    14,
    backgroundColor: 'rgba(255,170,0,0.3)',
    borderWidth:     2,
    borderColor:     'rgba(255,170,0,0.7)',
    justifyContent:  'center',
    alignItems:      'center',
  },
  wpMarkerActive: {
    backgroundColor: 'rgba(0,180,216,0.3)',
    borderColor:     C.cyan,
  },
  wpMarkerText: { color: C.text, fontSize: 10, fontWeight: '900' },

  // ── PANEL INFERIOR ──
  bottomPanel: {
    position:        'absolute',
    bottom:          0,
    left:            0,
    right:           0,
    backgroundColor: C.surface,
    borderTopWidth:  1.5,
    borderTopColor:  C.hairlineStrong,
    paddingHorizontal: 14,
    paddingTop:      12,
  },

  coordRow:     { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  coordItem:    { flex: 1, alignItems: 'center' },
  coordDivider: { width: 1, height: 28, backgroundColor: C.hairline },
  coordLabel:   { color: C.textDim, fontSize: 8, fontWeight: '800', letterSpacing: 1.5, marginBottom: 2 },
  coordValue:   { color: C.cyan, fontSize: 13, fontWeight: '800', letterSpacing: 0.5 },

  altRow: {
    flexDirection:  'row',
    alignItems:     'center',
    marginBottom:   10,
    gap:            10,
  },
  altLabel:    { color: C.textDim, fontSize: 8, fontWeight: '800', letterSpacing: 1 },
  altControls: { flexDirection: 'row', gap: 6, flex: 1 },
  altBtn: {
    flex:            1,
    paddingVertical: 5,
    borderRadius:    10,
    backgroundColor: C.glass,
    borderWidth:     1.5,
    borderColor:     C.hairlineStrong,
    alignItems:      'center',
  },
  altBtnActive:     { backgroundColor: C.cyan + '1A', borderColor: C.cyan },
  altBtnText:       { color: C.textMuted, fontSize: 10, fontWeight: '700' },
  altBtnTextActive: { color: C.cyan },

  // ── LISTA WAYPOINTS ──
  wpList:        { maxHeight: 60, marginBottom: 4 },
  wpListContent: { gap: 8, paddingRight: 4 },
  wpChip: {
    backgroundColor: C.glass,
    borderRadius:    12,
    borderWidth:     1.5,
    borderColor:     C.hairlineStrong,
    paddingHorizontal: 10,
    paddingVertical: 6,
    minWidth:        110,
  },
  wpChipActive:  { borderColor: C.cyan, backgroundColor: C.cyan + '18' },
  wpChipNum:     { color: C.warning, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  wpChipCoord:   { color: C.textMuted, fontSize: 8, fontWeight: '600', marginTop: 1 },
  wpChipAlt:     { color: C.textMuted, fontSize: 8, fontWeight: '600' },

  hint: {
    color:      C.textDim,
    fontSize:   10,
    fontWeight: '600',
    textAlign:  'center',
    marginBottom: 4,
  },

  // ── SIN GPS ──
  noGpsOverlay: {
    position:       'absolute',
    top:            '35%',
    left:           '50%',
    transform:      [{ translateX: -90 }],
    width:          180,
    backgroundColor: C.surface,
    borderRadius:   18,
    borderWidth:    1.5,
    borderColor:    C.hairlineStrong,
    padding:        20,
    alignItems:     'center',
    gap:            6,
  },
  noGpsIcon:  { fontSize: 32 },
  noGpsTitle: { color: C.textMuted, fontSize: 13, fontWeight: '800', letterSpacing: 1 },
  noGpsDesc:  { color: C.textMuted, fontSize: 10, fontWeight: '600' },
});