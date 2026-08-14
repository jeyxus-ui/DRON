import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, StyleSheet, TouchableOpacity,
  Alert, KeyboardAvoidingView, Platform, ScrollView, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone } from '../context/DroneContext';
import { getApiUrl } from '../config';
import { authFetch } from '../utils/authFetch';
import { theme } from '../theme';
import RNFS from 'react-native-fs';

const WAYPOINTS_DIR = `${RNFS.DocumentDirectoryPath}/GCS/waypoints`;

interface WaypointItem {
  id: string;
  forward: number;
  right: number;
  up: number;
}

let wpCounter = 0;

const C = theme.colors;
const VIOLET = C.primary;
const VIOLET_LIGHT = C.primaryLight;

export const WaypointScreen: React.FC = () => {
  const insets = useSafeAreaInsets();
  const { telemetry, connected, demoMode, sendCommand, pushError } = useDrone();

  const [waypoints, setWaypoints] = useState<WaypointItem[]>([]);
  const [fwd, setFwd] = useState('');
  const [right, setRight] = useState('');
  const [up, setUp] = useState('');
  const [loading, setLoading] = useState('');

  const [routeName, setRouteName] = useState('');
  const [currentRouteName, setCurrentRouteName] = useState<string | null>(null);
  const [savedRoutes, setSavedRoutes] = useState<string[]>([]);

  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingWp, setEditingWp] = useState<WaypointItem | null>(null);
  const [editIndex, setEditIndex] = useState(-1);
  const [editFwd, setEditFwd] = useState('');
  const [editRight, setEditRight] = useState('');
  const [editUp, setUpEdit] = useState('');

  const fwdRef = useRef<TextInput>(null);
  const rightRef = useRef<TextInput>(null);
  const upRef = useRef<TextInput>(null);

  const refreshSavedRoutes = useCallback(async () => {
    try {
      const exists = await RNFS.exists(WAYPOINTS_DIR);
      if (!exists) { setSavedRoutes([]); return; }
      const files = await RNFS.readDir(WAYPOINTS_DIR);
      const names = files
        .filter(f => f.name.endsWith('.json'))
        .map(f => f.name.replace('.json', ''))
        .sort();
      setSavedRoutes(names);
    } catch { setSavedRoutes([]); }
  }, []);

  useEffect(() => { refreshSavedRoutes(); }, [refreshSavedRoutes]);

  useEffect(() => {
    if (!connected || demoMode) return;
    let cancelled = false;
    const check = () => {
      authFetch(`${getApiUrl()}/api/sensors/status`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (cancelled || !data) return;
          if (!data.success || !data.data?.running) {
            pushError('SENSOR_NO_DATA', 'Sensores no disponibles — verifica bridge raspberry o conexión I2C/USB', 'warn');
          } else {
            const mtf = data.data.mtf01;
            const lid = data.data.lidar;
            if (mtf && !mtf.running) pushError('SENSOR_MTF01_ERROR', 'Ultrasonido MTF01 no conectado — revisa cable I2C', 'warn');
            if (lid && !lid.running) pushError('SENSOR_LIDAR_ERROR', 'LIDAR YDLIDAR no conectado — revisa cable USB', 'warn');
          }
        })
        .catch(() => {});
    };
    check();
    const iv = setInterval(check, 15000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [connected, demoMode, pushError]);

  const addWaypoint = () => {
    const f = parseFloat(fwd);
    const r = parseFloat(right);
    const u = parseFloat(up);
    if (isNaN(f) && isNaN(r) && isNaN(u)) {
      Alert.alert('Error', 'Ingresa al menos un valor');
      return;
    }
    const wp: WaypointItem = {
      id: `wp_${++wpCounter}`,
      forward: isNaN(f) ? 0 : f,
      right: isNaN(r) ? 0 : r,
      up: isNaN(u) ? 0 : u,
    };
    setWaypoints(prev => [...prev, wp]);
    setFwd(''); setRight(''); setUp('');
    fwdRef.current?.focus();
  };

  const removeWaypoint = (id: string) => {
    setWaypoints(prev => prev.filter(w => w.id !== id));
  };

  const clearWaypoints = () => {
    setWaypoints([]);
    setCurrentRouteName(null);
    setRouteName('');
  };

  const formatNum = (v: number) => (v >= 0 ? `+${v.toFixed(1)}` : `${v.toFixed(1)}`);

  const doStartMission = async () => {
    if (waypoints.length === 0) { Alert.alert('Sin waypoints', 'Agrega al menos un waypoint'); return; }
    setLoading('start');
    const res = await sendCommand('START_MISSION');
    setLoading('');
    Alert.alert(res.success ? 'Misión iniciada' : 'Error', res.message);
  };

  const doClearMission = async () => {
    setLoading('clear');
    await sendCommand('CLEAR_MISSION');
    setLoading('');
    clearWaypoints();
    Alert.alert('Misión limpiada', 'Waypoints y misión eliminados');
  };

  const doGotoWaypoint = (wp: WaypointItem) => {
    setLoading(`goto_${wp.id}`);
    sendCommand('GOTO', { forward: wp.forward, right: wp.right, up: wp.up })
      .then(res => {
        setLoading('');
        Alert.alert(res.success ? 'Navegando' : 'Error', res.message);
      })
      .catch(() => { setLoading(''); Alert.alert('Error', 'No se pudo enviar GOTO'); });
  };

  const doSaveRoute = async () => {
    const name = routeName.trim();
    if (!name) { Alert.alert('Error', 'Ingresa un nombre para la ruta'); return; }
    if (waypoints.length === 0) { Alert.alert('Error', 'No hay waypoints para guardar'); return; }
    try {
      await RNFS.mkdir(WAYPOINTS_DIR);
      const data = JSON.stringify({ name, waypoints }, null, 2);
      await RNFS.writeFile(`${WAYPOINTS_DIR}/${name}.json`, data, 'utf8');
      setCurrentRouteName(name);
      await refreshSavedRoutes();
      Alert.alert('Guardado', `Ruta "${name}" guardada (${waypoints.length} WP)`);
    } catch (e: any) {
      Alert.alert('Error', `No se pudo guardar: ${e.message}`);
    }
  };

  const doLoadRoute = async (name: string) => {
    try {
      const data = await RNFS.readFile(`${WAYPOINTS_DIR}/${name}.json`, 'utf8');
      const parsed = JSON.parse(data);
      if (!parsed.waypoints || !Array.isArray(parsed.waypoints)) {
        Alert.alert('Error', 'Archivo de ruta inválido');
        return;
      }
      setWaypoints(parsed.waypoints);
      setCurrentRouteName(name);
      setRouteName(name);
      wpCounter = parsed.waypoints.reduce((m: number, w: WaypointItem) => {
        const n = parseInt(w.id.replace('wp_', ''), 10);
        return isNaN(n) ? m : Math.max(m, n);
      }, 0);
      Alert.alert('Cargado', `Ruta "${name}" cargada (${parsed.waypoints.length} WP)`);
    } catch (e: any) {
      Alert.alert('Error', `No se pudo cargar: ${e.message}`);
    }
  };

  const doDeleteRoute = (name: string) => {
    Alert.alert(
      'Eliminar ruta',
      `¿Eliminar "${name}" permanentemente?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Eliminar', style: 'destructive',
          onPress: async () => {
            try {
              await RNFS.unlink(`${WAYPOINTS_DIR}/${name}.json`);
              if (currentRouteName === name) {
                setCurrentRouteName(null);
                setRouteName('');
              }
              await refreshSavedRoutes();
            } catch (e: any) {
              Alert.alert('Error', `No se pudo eliminar: ${e.message}`);
            }
          },
        },
      ],
    );
  };

  const openEditModal = (wp: WaypointItem, index: number) => {
    setEditingWp(wp);
    setEditIndex(index);
    setEditFwd(String(wp.forward));
    setEditRight(String(wp.right));
    setUpEdit(String(wp.up));
    setEditModalVisible(true);
  };

  const saveEditModal = () => {
    if (!editingWp) return;
    const f = parseFloat(editFwd);
    const r = parseFloat(editRight);
    const u = parseFloat(editUp);
    if (isNaN(f) && isNaN(r) && isNaN(u)) {
      Alert.alert('Error', 'Ingresa al menos un valor');
      return;
    }
    const updated: WaypointItem = {
      ...editingWp,
      forward: isNaN(f) ? 0 : f,
      right: isNaN(r) ? 0 : r,
      up: isNaN(u) ? 0 : u,
    };
    setWaypoints(prev => prev.map((w, i) => (i === editIndex ? updated : w)));
    closeEditModal();
  };

  const closeEditModal = () => {
    setEditModalVisible(false);
    setEditingWp(null);
    setEditIndex(-1);
  };

  const renderWaypoint = ({ item, index }: { item: WaypointItem; index: number }) => {
    const isNavigating = loading === `goto_${item.id}`;
    return (
      <View style={styles.wpCard}>
        <View style={styles.wpCardLeft}>
          <View style={[styles.wpBadge, { borderColor: VIOLET + 'AA' }]}>
            <Text style={styles.wpBadgeText}>{index + 1}</Text>
          </View>
          <View style={styles.wpCoords}>
            <View style={styles.wpCoordRow}>
              <Text style={styles.wpCoordLabel}>F</Text>
              <Text style={[styles.wpCoordValue, { color: item.forward > 0 ? VIOLET : C.textMuted }]}>{formatNum(item.forward)}</Text>
            </View>
            <View style={styles.wpCoordRow}>
              <Text style={styles.wpCoordLabel}>R</Text>
              <Text style={[styles.wpCoordValue, { color: item.right > 0 ? VIOLET : C.textMuted }]}>{formatNum(item.right)}</Text>
            </View>
            <View style={styles.wpCoordRow}>
              <Text style={styles.wpCoordLabel}>U</Text>
              <Text style={[styles.wpCoordValue, { color: item.up > 0 ? VIOLET : C.textMuted }]}>{formatNum(item.up)}</Text>
            </View>
          </View>
        </View>
        <View style={styles.wpCardActions}>
          <TouchableOpacity
            style={[styles.wpCardBtn, styles.wpEditBtn]}
            onPress={() => openEditModal(item, index)}
          >
            <Text style={styles.wpCardBtnText}>✎</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.wpCardBtn, styles.wpGotoBtn]}
            onPress={() => doGotoWaypoint(item)}
            disabled={!!loading}
          >
            <Text style={styles.wpCardBtnText}>{isNavigating ? '…' : '▶'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.wpCardBtn, styles.wpDelBtn]}
            onPress={() => removeWaypoint(item.id)}
          >
            <Text style={styles.wpCardBtnText}>✕</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  const editModalRef = useRef<TextInput>(null);
  const editModalRightRef = useRef<TextInput>(null);
  const editModalUpRef = useRef<TextInput>(null);

  const isEditingRoute = currentRouteName !== null && waypoints.length > 0;
  const isSaveDisabled = !routeName.trim() || waypoints.length === 0;

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* ── HEADER ── */}
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Text style={styles.headerTitle}>RUTA</Text>
        <View style={styles.headerBadges}>
          <View style={[styles.hdrBadge, { borderColor: connected ? VIOLET_LIGHT + '66' : '#F87171' + '66' }]}>
            <View style={[styles.hdrDot, { backgroundColor: connected ? VIOLET_LIGHT : '#F87171' }]} />
            <Text style={[styles.hdrBadgeText, { color: connected ? VIOLET_LIGHT : '#F87171' }]}>
              {connected ? 'ON' : 'OFF'}
            </Text>
          </View>
          {telemetry.armed && (
            <View style={[styles.hdrBadge, { borderColor: '#F87171' + '66' }]}>
              <Text style={[styles.hdrBadgeText, { color: '#F87171' }]}>ARM</Text>
            </View>
          )}
          <View style={[styles.hdrBadge, { borderColor: VIOLET_LIGHT + '66' }]}>
            <Text style={[styles.hdrBadgeText, { color: VIOLET_LIGHT }]}>{waypoints.length} WP</Text>
          </View>
        </View>
      </View>

      {/* ── SENSORES DETECTADOS ── */}
      {connected && !demoMode && (
        <View style={styles.sensorBar}>
          <Text style={styles.sensorBarTitle}>SENSORES</Text>
          <View style={styles.sensorChips}>
            <View style={[styles.sensorChip, { borderColor: telemetry.mtf01_distance != null ? C.cyan + '66' : C.hairline }]}>
              <Text style={[styles.sensorChipText, { color: telemetry.mtf01_distance != null ? C.cyan : C.textDim }]}>MTF01</Text>
            </View>
            <View style={[styles.sensorChip, { borderColor: (telemetry.lidar_points ?? 0) > 0 ? C.cyan + '66' : C.hairline }]}>
              <Text style={[styles.sensorChipText, { color: (telemetry.lidar_points ?? 0) > 0 ? C.cyan : C.textDim }]}>LIDAR</Text>
            </View>
            <View style={[styles.sensorChip, { borderColor: telemetry.obstacle_ahead != null ? VIOLET + '66' : C.hairline }]}>
              <Text style={[styles.sensorChipText, { color: telemetry.obstacle_ahead != null ? VIOLET : C.textDim }]}>OBSTÁCULOS</Text>
            </View>
          </View>
        </View>
      )}

      <ScrollView style={styles.body} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

        {/* ── INPUT PANEL ── */}
        <View style={styles.inputPanel}>
          <View style={styles.inputRow}>
            <View style={styles.inputGroup}>
              <TextInput
                ref={fwdRef}
                style={styles.input}
                value={fwd}
                onChangeText={setFwd}
                keyboardType="numeric"
                placeholder="F"
                placeholderTextColor={C.textDim}
                returnKeyType="next"
                onSubmitEditing={() => rightRef.current?.focus()}
              />
              <Text style={styles.inputSuffix}>m</Text>
            </View>
            <View style={styles.inputGroup}>
              <TextInput
                ref={rightRef}
                style={styles.input}
                value={right}
                onChangeText={setRight}
                keyboardType="numeric"
                placeholder="R"
                placeholderTextColor={C.textDim}
                returnKeyType="next"
                onSubmitEditing={() => upRef.current?.focus()}
              />
              <Text style={styles.inputSuffix}>m</Text>
            </View>
            <View style={styles.inputGroup}>
              <TextInput
                ref={upRef}
                style={styles.input}
                value={up}
                onChangeText={setUp}
                keyboardType="numeric"
                placeholder="U"
                placeholderTextColor={C.textDim}
                returnKeyType="done"
              />
              <Text style={styles.inputSuffix}>m</Text>
            </View>
            <TouchableOpacity style={styles.addBtn} onPress={addWaypoint} activeOpacity={0.75}>
              <Text style={styles.addBtnText}>+</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* ── CURRENT ROUTE BANNER ── */}
        {currentRouteName && waypoints.length > 0 && (
          <View style={styles.routeBanner}>
            <Text style={styles.routeBannerLabel}>RUTA ACTUAL</Text>
            <Text style={styles.routeBannerName}>{currentRouteName}</Text>
            <TouchableOpacity
              onPress={() => { setCurrentRouteName(null); setRouteName(''); }}
              activeOpacity={0.7}
            >
              <Text style={styles.routeBannerClose}>✕</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── SAVE / UPDATE ROUTE ── */}
        <View style={styles.persistCard}>
          <View style={styles.persistRow}>
            <TextInput
              style={styles.persistInput}
              value={routeName}
              onChangeText={setRouteName}
              placeholder="Nombre de ruta"
              placeholderTextColor={C.textDim}
              returnKeyType="done"
              onSubmitEditing={doSaveRoute}
            />
            <TouchableOpacity
              style={[
                styles.persistBtn,
                isEditingRoute ? styles.updateBtn : styles.saveBtn,
                isSaveDisabled && { opacity: 0.4 },
              ]}
              onPress={doSaveRoute}
              activeOpacity={0.7}
              disabled={isSaveDisabled}
            >
              <Text style={styles.persistBtnText}>
                {isEditingRoute ? '⟳' : '💾'}
              </Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.persistHint}>
            {isEditingRoute
              ? `Actualizará la ruta "${currentRouteName}"`
              : 'Guardar como nueva ruta'}
          </Text>
        </View>

        {/* ── SAVED ROUTES LIST ── */}
        {savedRoutes.length > 0 && (
          <View style={styles.persistCard}>
            <Text style={styles.savedSectionTitle}>RUTAS GUARDADAS</Text>
            <View style={styles.savedList}>
              {savedRoutes.map(name => {
                const isActive = currentRouteName === name;
                return (
                  <View key={name} style={[styles.savedRow, isActive && styles.savedRowActive]}>
                    <View style={styles.savedNameWrap}>
                      {isActive && <View style={styles.savedActiveDot} />}
                      <Text style={[styles.savedName, isActive && { color: VIOLET }]}>{name}</Text>
                    </View>
                    <View style={styles.savedActions}>
                      <TouchableOpacity
                        style={[styles.savedActionBtn, isActive ? styles.savedEditBtn : styles.savedLoadBtn]}
                        onPress={() => doLoadRoute(name)}
                        activeOpacity={0.7}
                      >
                        <Text style={styles.savedActionText}>{isActive ? '✎' : '▶'}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.savedActionBtn, styles.savedDelBtn]}
                        onPress={() => doDeleteRoute(name)}
                        activeOpacity={0.7}
                      >
                        <Text style={styles.savedActionText}>✕</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })}
            </View>
          </View>
        )}

        {/* ── WAYPOINT LIST ── */}
        <View style={styles.listSection}>
          <View style={styles.listHeader}>
            <Text style={styles.listTitle}>WAYPOINTS</Text>
            {waypoints.length > 0 && (
              <TouchableOpacity onPress={clearWaypoints} activeOpacity={0.7}>
                <Text style={styles.clearBtn}>LIMPIAR TODO</Text>
              </TouchableOpacity>
            )}
          </View>

          {waypoints.length === 0 ? (
            <View style={styles.emptyBox}>
              <Text style={styles.emptyIcon}>🎯</Text>
              <Text style={styles.emptyTitle}>Sin waypoints</Text>
              <Text style={styles.emptySub}>Define F/R/U y presiona +</Text>
              {savedRoutes.length > 0 && (
                <Text style={styles.emptySub2}>O carga una ruta guardada</Text>
              )}
            </View>
          ) : (
            waypoints.map((wp, i) => (
              <View key={wp.id}>{renderWaypoint({ item: wp, index: i })}</View>
            ))
          )}
        </View>

        {/* ── ACTION BUTTONS ── */}
        <View style={styles.actionBar}>
          <TouchableOpacity
            style={[styles.actionBtn, styles.actionStart]}
            onPress={doStartMission}
            disabled={!!loading || waypoints.length === 0}
          >
            <Text style={styles.actionIcon}>▶</Text>
            <Text style={styles.actionLabel}>{loading === 'start' ? '⟳' : 'INICIAR'}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, styles.actionClear]}
            onPress={doClearMission}
            disabled={!!loading}
          >
            <Text style={styles.actionIcon}>🗑</Text>
            <Text style={styles.actionLabel}>{loading === 'clear' ? '⟳' : 'LIMPIAR'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: 24 }} />
      </ScrollView>

      {/* ── EDIT MODAL ── */}
      <Modal
        visible={editModalVisible}
        transparent
        animationType="fade"
        onRequestClose={closeEditModal}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>EDITAR WAYPOINT #{editIndex + 1}</Text>

            <View style={styles.modalInputRow}>
              <View style={styles.modalInputGroup}>
                <Text style={styles.modalInputLabel}>F</Text>
                <TextInput
                  ref={editModalRef}
                  style={styles.modalInput}
                  value={editFwd}
                  onChangeText={setEditFwd}
                  keyboardType="numeric"
                  placeholder="0"
                  placeholderTextColor={C.textDim}
                  returnKeyType="next"
                  onSubmitEditing={() => editModalRightRef.current?.focus()}
                />
                <Text style={styles.modalInputUnit}>m</Text>
              </View>
              <View style={styles.modalInputGroup}>
                <Text style={styles.modalInputLabel}>R</Text>
                <TextInput
                  ref={editModalRightRef}
                  style={styles.modalInput}
                  value={editRight}
                  onChangeText={setEditRight}
                  keyboardType="numeric"
                  placeholder="0"
                  placeholderTextColor={C.textDim}
                  returnKeyType="next"
                  onSubmitEditing={() => editModalUpRef.current?.focus()}
                />
                <Text style={styles.modalInputUnit}>m</Text>
              </View>
              <View style={styles.modalInputGroup}>
                <Text style={styles.modalInputLabel}>U</Text>
                <TextInput
                  ref={editModalUpRef}
                  style={styles.modalInput}
                  value={editUp}
                  onChangeText={setUpEdit}
                  keyboardType="numeric"
                  placeholder="0"
                  placeholderTextColor={C.textDim}
                  returnKeyType="done"
                  onSubmitEditing={saveEditModal}
                />
                <Text style={styles.modalInputUnit}>m</Text>
              </View>
            </View>

            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={closeEditModal} activeOpacity={0.7}>
                <Text style={styles.modalCancelText}>CANCELAR</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSaveBtn} onPress={saveEditModal} activeOpacity={0.7}>
                <Text style={styles.modalSaveText}>GUARDAR</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: C.bg,
  },
  body: {
    flex: 1,
    paddingHorizontal: 12,
    paddingTop: 8,
  },

  // ── SENSOR BAR ──
  sensorBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: C.surface,
    borderBottomWidth: 1,
    borderBottomColor: C.hairline,
    gap: 8,
  },
  sensorBarTitle: {
    fontSize: 9,
    fontWeight: '700',
    color: C.textDim,
    letterSpacing: 1,
  },
  sensorChips: {
    flexDirection: 'row',
    gap: 6,
  },
  sensorChip: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    borderWidth: 1,
    backgroundColor: C.bgElevated,
  },
  sensorChipText: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
  },

  // ── HEADER ──
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingBottom: 10,
    backgroundColor: C.navy,
    borderBottomWidth: 1.5,
    borderBottomColor: C.navyElevated,
  },
  headerTitle: {
    color: C.surface,
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: 4,
  },
  headerBadges: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
  },
  hdrBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderWidth: 1.5,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  hdrDot: {
    width: 5,
    height: 5,
    borderRadius: 3,
  },
  hdrBadgeText: {
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.8,
  },

  // ── INPUT PANEL ──
  inputPanel: {
    backgroundColor: C.surface,
    borderWidth: 1.5,
    borderColor: C.hairline,
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 6,
  },
  inputRow: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
  },
  inputGroup: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: C.bgElevated,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: VIOLET + '55',
  },
  input: {
    flex: 1,
    color: C.text,
    fontSize: 16,
    fontWeight: '900',
    textAlign: 'center',
    paddingVertical: 8,
    paddingHorizontal: 4,
    fontFamily: 'monospace',
  },
  inputSuffix: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '700',
    marginRight: 6,
  },
  addBtn: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: C.primaryDim,
    borderWidth: 1.5,
    borderColor: VIOLET + '88',
    justifyContent: 'center',
    alignItems: 'center',
  },
  addBtnText: {
    color: VIOLET,
    fontSize: 22,
    fontWeight: '900',
    lineHeight: 24,
  },

  // ── CURRENT ROUTE BANNER ──
  routeBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: VIOLET + '1A',
    borderWidth: 1.5,
    borderColor: VIOLET + '55',
    borderRadius: 10,
    paddingVertical: 6,
    paddingHorizontal: 12,
    marginBottom: 6,
    gap: 8,
  },
  routeBannerLabel: {
    color: C.textMuted,
    fontSize: 7,
    fontWeight: '800',
    letterSpacing: 1,
  },
  routeBannerName: {
    color: VIOLET,
    fontSize: 12,
    fontWeight: '900',
    flex: 1,
    fontFamily: 'monospace',
  },
  routeBannerClose: {
    color: C.danger,
    fontSize: 12,
    fontWeight: '900',
  },

  // ── PERSIST (SAVE/UPDATE) ──
  persistCard: {
    backgroundColor: C.surface,
    borderWidth: 1.5,
    borderColor: C.hairline,
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 6,
  },
  persistRow: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
  },
  persistInput: {
    flex: 1,
    backgroundColor: C.bgElevated,
    borderWidth: 1.5,
    borderColor: VIOLET + '55',
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 10,
    color: C.text,
    fontSize: 12,
    fontWeight: '700',
    fontFamily: 'monospace',
  },
  persistBtn: {
    width: 38,
    height: 38,
    borderRadius: 10,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
  },
  saveBtn: {
    borderColor: VIOLET + '66',
  },
  updateBtn: {
    borderColor: VIOLET_LIGHT + '88',
    backgroundColor: VIOLET_LIGHT + '20',
  },
  persistBtnText: {
    color: C.text,
    fontSize: 14,
    fontWeight: '800',
  },
  persistHint: {
    color: C.textMuted,
    fontSize: 7,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginTop: 4,
  },
  savedSectionTitle: {
    color: C.textMuted,
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 1.5,
    marginBottom: 6,
  },
  savedList: {
    gap: 4,
  },
  savedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: C.bgElevated,
    borderRadius: 10,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: VIOLET + '33',
  },
  savedRowActive: {
    borderColor: VIOLET + '55',
    backgroundColor: VIOLET + '10',
  },
  savedNameWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flex: 1,
  },
  savedActiveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: VIOLET,
  },
  savedName: {
    color: C.textMuted,
    fontSize: 11,
    fontWeight: '700',
    fontFamily: 'monospace',
  },
  savedActions: {
    flexDirection: 'row',
    gap: 4,
  },
  savedActionBtn: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
  },
  savedLoadBtn: {
    borderColor: VIOLET + '66',
    backgroundColor: VIOLET + '15',
  },
  savedEditBtn: {
    borderColor: VIOLET_LIGHT + '88',
    backgroundColor: VIOLET_LIGHT + '20',
  },
  savedDelBtn: {
    borderColor: C.danger + '80',
    backgroundColor: C.danger + '1F',
  },
  savedActionText: {
    color: C.text,
    fontSize: 11,
    fontWeight: '800',
  },

  // ── LIST ──
  listSection: {
    marginBottom: 6,
  },
  listHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  listTitle: {
    color: C.textMuted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  clearBtn: {
    color: C.danger,
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 1,
  },
  emptyBox: {
    alignItems: 'center',
    paddingVertical: 24,
    gap: 4,
  },
  emptyIcon: { fontSize: 28 },
  emptyTitle: { color: C.textMuted, fontSize: 12, fontWeight: '700' },
  emptySub: { color: C.textDim, fontSize: 10, fontWeight: '600' },
  emptySub2: { color: C.textDim, fontSize: 10, fontWeight: '600', marginTop: 2 },

  // ── WAYPOINT CARD ──
  wpCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: C.surface,
    borderWidth: 1.5,
    borderColor: VIOLET + '40',
    borderRadius: 14,
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginBottom: 5,
  },
  wpCardLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
  },
  wpBadge: {
    width: 28,
    height: 28,
    borderRadius: 10,
    borderWidth: 1.5,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: VIOLET + '15',
  },
  wpBadgeText: {
    color: VIOLET,
    fontSize: 11,
    fontWeight: '900',
  },
  wpCoords: {
    flex: 1,
    gap: 1,
  },
  wpCoordRow: {
    flexDirection: 'row',
    gap: 4,
    alignItems: 'center',
  },
  wpCoordLabel: {
    color: C.textMuted,
    fontSize: 8,
    fontWeight: '800',
    width: 12,
    letterSpacing: 0.5,
  },
  wpCoordValue: {
    fontSize: 11,
    fontWeight: '700',
    fontFamily: 'monospace',
    letterSpacing: 0.5,
  },
  wpCardActions: {
    flexDirection: 'row',
    gap: 4,
    marginLeft: 6,
  },
  wpCardBtn: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
  },
  wpEditBtn: {
    borderColor: VIOLET_LIGHT + '66',
    backgroundColor: VIOLET_LIGHT + '15',
  },
  wpGotoBtn: {
    borderColor: VIOLET + '66',
    backgroundColor: VIOLET + '15',
  },
  wpDelBtn: {
    borderColor: C.danger + '80',
    backgroundColor: C.danger + '1F',
  },
  wpCardBtnText: {
    color: C.text,
    fontSize: 11,
    fontWeight: '800',
  },

  // ── ACTION BAR ──
  actionBar: {
    flexDirection: 'row',
    gap: 6,
    paddingVertical: 4,
    marginBottom: 8,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    backgroundColor: C.surface,
    gap: 4,
  },
  actionStart: {
    borderColor: VIOLET_LIGHT + '55',
  },
  actionClear: {
    borderColor: C.danger + '80',
  },
  actionIcon: {
    fontSize: 16,
  },
  actionLabel: {
    color: C.text,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1.5,
  },

  // ── EDIT MODAL ──
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  modalContent: {
    width: '100%',
    backgroundColor: C.surface,
    borderWidth: 1.5,
    borderColor: VIOLET + '66',
    borderRadius: 18,
    padding: 20,
  },
  modalTitle: {
    color: C.text,
    fontSize: 14,
    fontWeight: '900',
    letterSpacing: 2,
    textAlign: 'center',
    marginBottom: 16,
  },
  modalInputRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 20,
  },
  modalInputGroup: {
    flex: 1,
    alignItems: 'center',
    gap: 4,
  },
  modalInputLabel: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1,
  },
  modalInput: {
    width: '100%',
    backgroundColor: C.bgElevated,
    borderWidth: 1.5,
    borderColor: VIOLET + '44',
    borderRadius: 10,
    color: C.text,
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
    paddingVertical: 10,
    paddingHorizontal: 8,
    fontFamily: 'monospace',
  },
  modalInputUnit: {
    color: C.textMuted,
    fontSize: 8,
    fontWeight: '700',
  },
  modalActions: {
    flexDirection: 'row',
    gap: 8,
  },
  modalCancelBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    alignItems: 'center',
    backgroundColor: C.glass,
  },
  modalCancelText: {
    color: C.textMuted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  modalSaveBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: VIOLET + '88',
    alignItems: 'center',
    backgroundColor: C.primaryDim,
  },
  modalSaveText: {
    color: VIOLET,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
});
