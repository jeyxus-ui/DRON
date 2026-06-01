import React, { useState, useRef } from 'react';
import {
  View, Text, TextInput, FlatList, StyleSheet, TouchableOpacity,
  Alert, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone } from '../context/DroneContext';
import { StatusBar } from '../components/StatusBar';
import { API_URL } from '../config';

interface WaypointItem {
  id: string;
  forward: number;
  right: number;
  up: number;
}

let wpCounter = 0;

const MODE_COLORS: Record<string, string> = {
  STANDBY: '#888', GUIDED: '#00ccff', AUTO: '#00ff88',
  RTL: '#ff8800', LAND: '#ff4466', BRAKE: '#ff0044',
  STABILIZE: '#ffaa00', ALT_HOLD: '#44aaff', LOITER: '#aa66ff',
};

const MODE_ICONS: Record<string, string> = {
  STANDBY: '⏸', GUIDED: '🎯', AUTO: '▶', RTL: '🏠',
  LAND: '⬇', BRAKE: '🛑', STABILIZE: '⚖', ALT_HOLD: '↕', LOITER: '◎',
};

export const WaypointScreen: React.FC = () => {
  const insets = useSafeAreaInsets();
  const { telemetry, connected, demoMode, sendCommand, armDrone, takeoff, land } = useDrone();

  const [waypoints, setWaypoints] = useState<WaypointItem[]>([]);
  const [fwd, setFwd] = useState('');
  const [right, setRight] = useState('');
  const [up, setUp] = useState('');
  const [loading, setLoading] = useState('');

  const fwdRef = useRef<TextInput>(null);
  const rightRef = useRef<TextInput>(null);
  const upRef = useRef<TextInput>(null);

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
  };

  const formatNum = (v: number) => (v >= 0 ? `+${v.toFixed(1)}` : `${v.toFixed(1)}`);

  const doUploadMission = async () => {
    if (waypoints.length === 0) { Alert.alert('Sin waypoints', 'Agrega al menos un waypoint'); return; }
    setLoading('upload');
    const res = await sendCommand('MISSION_UPLOAD_RELATIVE', {
      waypoints: waypoints.map(w => ({ forward: w.forward, right: w.right, up: w.up })),
    });
    setLoading('');
    Alert.alert(res.success ? 'Misión subida' : 'Error', res.message);
  };

  const doStartMission = async () => {
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

  const [saveName, setSaveName] = useState('');

  const doSaveWaypoints = async () => {
    if (waypoints.length === 0) { Alert.alert('Sin waypoints', 'Agrega al menos un waypoint'); return; }
    const name = saveName.trim() || 'default';
    setLoading('save');
    try {
      const resp = await fetch(`${API_URL}/api/waypoints/save`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, waypoints }),
      });
      const data = await resp.json();
      Alert.alert(data.success ? 'Guardado' : 'Error', data.message);
    } catch { Alert.alert('Error', 'No se pudo conectar al servidor'); }
    setLoading('');
  };

  const doLoadWaypoints = async () => {
    const name = saveName.trim();
    if (name) { await loadNamedWaypoints(name); return; }
    setLoading('list');
    try {
      const resp = await fetch(`${API_URL}/api/waypoints/list`);
      const data = await resp.json();
      if (!data.success || !data.names.length) {
        Alert.alert('Sin datos', 'No hay waypoints guardados.\nEscribe un nombre y presiona GUARDAR.');
        setLoading('');
        return;
      }
      const names = data.names as string[];
      if (names.length === 1) {
        await loadNamedWaypoints(names[0]);
      } else if (names.length <= 3) {
        Alert.alert('Cargar waypoints', 'Selecciona uno:', [
          ...names.map((n: string) => ({ text: n, onPress: () => loadNamedWaypoints(n) })),
          { text: 'Cancelar', style: 'cancel' as const },
        ]);
      } else {
        Alert.alert('Waypoints guardados', names.join('\n') + '\n\nEscribe el nombre y presiona CARGAR.');
      }
    } catch { Alert.alert('Error', 'No se pudo conectar al servidor'); }
    setLoading('');
  };

  const loadNamedWaypoints = async (name: string) => {
    setLoading('load');
    try {
      const resp = await fetch(`${API_URL}/api/waypoints/load`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await resp.json();
      if (data.success && data.waypoints) {
        const loaded: WaypointItem[] = data.waypoints.map((wp: any, i: number) => ({
          id: `wp_${i + 1}`, forward: wp.forward ?? 0, right: wp.right ?? 0, up: wp.up ?? 0,
        }));
        wpCounter = loaded.length;
        setWaypoints(loaded);
        Alert.alert('Cargado', `Waypoints '${name}' cargados (${loaded.length})`);
      } else {
        Alert.alert('Error', data.message || 'No se pudo cargar');
      }
    } catch { Alert.alert('Error', 'No se pudo conectar al servidor'); }
    setLoading('');
  };

  const modeColor = MODE_COLORS[telemetry.mode] || '#888';
  const modeIcon = MODE_ICONS[telemetry.mode] || '◈';

  const renderWaypoint = ({ item, index }: { item: WaypointItem; index: number }) => {
    const isNavigating = loading === `goto_${item.id}`;
    return (
      <View style={styles.wpRow}>
        <Text style={styles.wpIndex}>WP{index + 1}</Text>
        <View style={styles.wpValues}>
          <Text style={styles.wpVal}>F {formatNum(item.forward)}m</Text>
          <Text style={styles.wpVal}>R {formatNum(item.right)}m</Text>
          <Text style={styles.wpVal}>U {formatNum(item.up)}m</Text>
        </View>
        <View style={styles.wpActions}>
          <TouchableOpacity
            style={[styles.wpBtn, styles.gotoBtn]}
            onPress={() => doGotoWaypoint(item)}
            disabled={!!loading}
          >
            <Text style={styles.wpBtnText}>{isNavigating ? '…' : '▶'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.wpBtn, styles.delBtn]}
            onPress={() => removeWaypoint(item.id)}
          >
            <Text style={styles.wpBtnText}>×</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <StatusBar
        connected={connected}
        mode={telemetry.mode}
        modeColor={modeColor}
        modeIcon={modeIcon}
        armed={telemetry.armed}
        demoMode={demoMode}
        onMenuPress={() => {}}
        insetsTop={insets.top}
      />

      <View style={styles.body}>

        {/* ── Inputs ── */}
        <Text style={styles.sectionTitle}>Agregar waypoint relativo</Text>
        <View style={styles.inputRow}>
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Adelante (m)</Text>
            <TextInput
              ref={fwdRef}
              style={styles.input}
              value={fwd}
              onChangeText={setFwd}
              keyboardType="numeric"
              placeholder="0"
              placeholderTextColor="#444"
              returnKeyType="next"
              onSubmitEditing={() => rightRef.current?.focus()}
            />
          </View>
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Derecha (m)</Text>
            <TextInput
              ref={rightRef}
              style={styles.input}
              value={right}
              onChangeText={setRight}
              keyboardType="numeric"
              placeholder="0"
              placeholderTextColor="#444"
              returnKeyType="next"
              onSubmitEditing={() => upRef.current?.focus()}
            />
          </View>
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Arriba (m)</Text>
            <TextInput
              ref={upRef}
              style={styles.input}
              value={up}
              onChangeText={setUp}
              keyboardType="numeric"
              placeholder="0"
              placeholderTextColor="#444"
              returnKeyType="done"
            />
          </View>
        </View>

        <TouchableOpacity style={styles.addBtn} onPress={addWaypoint} activeOpacity={0.7}>
          <Text style={styles.addBtnIcon}>+</Text>
          <Text style={styles.addBtnLabel}>AÑADIR WAYPOINT</Text>
        </TouchableOpacity>

        {/* ── Lista de waypoints ── */}
        <View style={styles.listSection}>
          <View style={styles.listHeader}>
            <Text style={styles.sectionTitle}>
              Waypoints ({waypoints.length})
            </Text>
            {waypoints.length > 0 && (
              <TouchableOpacity onPress={clearWaypoints}>
                <Text style={styles.clearText}>LIMPIAR</Text>
              </TouchableOpacity>
            )}
          </View>

          <FlatList
            data={waypoints}
            renderItem={renderWaypoint}
            keyExtractor={item => item.id}
            style={styles.list}
            contentContainerStyle={waypoints.length === 0 ? styles.emptyContainer : undefined}
            ListEmptyComponent={
              <View style={styles.emptyBox}>
                <Text style={styles.emptyIcon}>📋</Text>
                <Text style={styles.emptyText}>Sin waypoints aún</Text>
                <Text style={styles.emptySub}>Define posición y presiona +</Text>
              </View>
            }
          />
        </View>

        {/* ── Persistencia waypoints ── */}
        <View style={styles.persistRow}>
          <TextInput
            style={styles.persistInput}
            value={saveName}
            onChangeText={setSaveName}
            placeholder="nombre..."
            placeholderTextColor="#444"
            returnKeyType="done"
          />
          <TouchableOpacity style={[styles.persistBtn, styles.saveBtn]} onPress={doSaveWaypoints} disabled={!!loading}>
            <Text style={styles.persistBtnText}>{loading === 'save' ? '⟳' : '💾'} GUARDAR</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.persistBtn, styles.loadBtn]} onPress={doLoadWaypoints} disabled={!!loading}>
            <Text style={styles.persistBtnText}>{loading === 'list' || loading === 'load' ? '⟳' : '📂'} CARGAR</Text>
          </TouchableOpacity>
        </View>

        {/* ── Acciones de misión ── */}
        <View style={styles.actionBar}>
          <TouchableOpacity
            style={[styles.actionBtn, styles.actionUpload]}
            onPress={doUploadMission}
            disabled={!!loading || waypoints.length === 0}
          >
            <Text style={styles.actionBtnText}>
              {loading === 'upload' ? '⟳' : '📤'} SUBIR
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, styles.actionStart]}
            onPress={doStartMission}
            disabled={!!loading}
          >
            <Text style={styles.actionBtnText}>
              {loading === 'start' ? '⟳' : '▶'} INICIAR
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, styles.actionClear]}
            onPress={doClearMission}
            disabled={!!loading}
          >
            <Text style={styles.actionBtnText}>
              {loading === 'clear' ? '⟳' : '🗑'} LIMPIAR
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#050508',
  },
  body: {
    flex: 1,
    paddingHorizontal: 12,
    paddingTop: 8,
  },

  // ── Títulos ──
  sectionTitle: {
    color: '#aaa',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
    marginBottom: 6,
  },

  // ── Inputs ──
  inputRow: {
    flexDirection: 'row',
    gap: 6,
  },
  inputGroup: {
    flex: 1,
  },
  inputLabel: {
    color: '#666',
    fontSize: 8,
    fontWeight: '700',
    letterSpacing: 0.8,
    marginBottom: 3,
  },
  input: {
    backgroundColor: '#0a0a14',
    borderWidth: 1,
    borderColor: '#1a1a2e',
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 10,
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
    textAlign: 'center',
  },

  // ── Añadir botón ──
  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: '#00ff8812',
    borderWidth: 1.5,
    borderColor: '#00ff8840',
    borderRadius: 10,
    paddingVertical: 10,
    marginTop: 8,
  },
  addBtnIcon: {
    color: '#00ff88',
    fontSize: 18,
    fontWeight: '900',
  },
  addBtnLabel: {
    color: '#00ff88',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },

  // ── Lista ──
  listSection: {
    flex: 1,
    marginTop: 12,
  },
  listHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  clearText: {
    color: '#ff4466',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1,
  },
  list: {
    flex: 1,
    marginTop: 4,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyBox: {
    alignItems: 'center',
    gap: 4,
  },
  emptyIcon: { fontSize: 32 },
  emptyText: { color: '#555', fontSize: 12, fontWeight: '700' },
  emptySub: { color: '#333', fontSize: 10, fontWeight: '600' },

  // ── Waypoint row ──
  wpRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0a0a14',
    borderWidth: 1,
    borderColor: '#1a1a2e',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 10,
    marginBottom: 4,
    gap: 8,
  },
  wpIndex: {
    color: '#00ff88',
    fontSize: 11,
    fontWeight: '900',
    width: 32,
  },
  wpValues: {
    flex: 1,
    flexDirection: 'row',
    gap: 8,
  },
  wpVal: {
    color: '#ccc',
    fontSize: 10,
    fontWeight: '700',
  },
  wpActions: {
    flexDirection: 'row',
    gap: 4,
  },
  wpBtn: {
    width: 28,
    height: 28,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  gotoBtn: {
    borderColor: '#00ccff40',
    backgroundColor: '#00ccff15',
  },
  delBtn: {
    borderColor: '#ff446640',
    backgroundColor: '#ff446615',
  },
  wpBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '800',
  },

  // ── Persist row ──
  persistRow: {
    flexDirection: 'row',
    gap: 4,
    paddingVertical: 6,
    alignItems: 'center',
  },
  persistInput: {
    flex: 1,
    backgroundColor: '#0a0a14',
    borderWidth: 1,
    borderColor: '#1a1a2e',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 8,
    color: '#fff',
    fontSize: 11,
    fontWeight: '700',
  },
  persistBtn: {
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveBtn: {
    borderColor: '#00ff8840',
    backgroundColor: '#00ff8812',
  },
  loadBtn: {
    borderColor: '#00ccff40',
    backgroundColor: '#00ccff15',
  },
  persistBtnText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.8,
  },

  // ── Action bar ──
  actionBar: {
    flexDirection: 'row',
    gap: 6,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: '#0d0d1a',
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
  },
  actionUpload: {
    borderColor: '#00ff8840',
    backgroundColor: '#00ff8812',
  },
  actionStart: {
    borderColor: '#00ccff40',
    backgroundColor: '#00ccff15',
  },
  actionClear: {
    borderColor: '#ff446640',
    backgroundColor: '#ff446615',
  },
  actionBtnText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1,
  },
});
