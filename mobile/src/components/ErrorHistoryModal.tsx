import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Modal,
  FlatList,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone, AppError } from '../context/DroneContext';
import { getErrorHelp } from '../utils/errorHelp';
import { theme } from '../theme';

const C = theme.colors;

const SEVERITY_COLORS: Record<string, string> = {
  info: C.cyan,
  warn: C.warning,
  error: C.danger,
  critical: '#B91C1C',
};

const SEVERITY_BG: Record<string, string> = {
  info: C.cyanDim,
  warn: 'rgba(217,119,6,0.12)',
  error: C.dangerDim,
  critical: 'rgba(185,28,28,0.12)',
};

const TIME_OPTS: Intl.DateTimeFormatOptions = {
  hour: '2-digit', minute: '2-digit', second: '2-digit',
};

const ErrorRow: React.FC<{ error: AppError }> = ({ error }) => {
  const color = SEVERITY_COLORS[error.severity] ?? C.textMuted;
  const bg = SEVERITY_BG[error.severity] ?? 'rgba(75,90,111,0.10)';
  const time = new Date(error.timestamp).toLocaleTimeString('es-CO', TIME_OPTS);
  const [expanded, setExpanded] = useState(false);
  const help = getErrorHelp(error.code);

  return (
    <TouchableOpacity
      style={[styles.row, { borderLeftColor: color, backgroundColor: bg }]}
      onPress={() => setExpanded(!expanded)}
      activeOpacity={0.7}
    >
      <View style={styles.rowHeader}>
        <Text style={[styles.rowCode, { color }]}>{error.code}</Text>
        <View style={styles.rowHeaderRight}>
          {!error.acknowledged && (
            <View style={[styles.activeDot, { backgroundColor: color }]} />
          )}
          <Text style={styles.rowTime}>{time}</Text>
        </View>
      </View>
      <Text style={styles.rowMessage}>{error.message}</Text>
      {error.detail ? (
        <Text style={styles.rowDetail}>→ {error.detail}</Text>
      ) : null}
      {expanded && help ? (
        <View style={styles.helpBox}>
          <Text style={styles.helpLabel}>POSIBLE MOTIVO:</Text>
          <Text style={styles.helpText}>{help}</Text>
        </View>
      ) : null}
      <View style={styles.rowFooter}>
        <View style={[styles.severityBadge, { backgroundColor: color + '44' }]}>
          <Text style={[styles.severityText, { color }]}>{error.severity.toUpperCase()}</Text>
        </View>
        {error.count > 1 && (
          <View style={styles.countBadge}>
            <Text style={styles.countText}>x{error.count}</Text>
          </View>
        )}
        <Text style={styles.tapHint}>{expanded ? '▲' : '▼'}</Text>
      </View>
    </TouchableOpacity>
  );
};

export const ErrorHistoryModal: React.FC = () => {
  const { errors, errorHistory, clearErrors, clearErrorHistory } = useDrone();
  const [visible, setVisible] = useState(false);
  const insets = useSafeAreaInsets();

  const activeErrors = errors.filter(e => !e.acknowledged);
  const totalActive = activeErrors.length;
  const totalCritical = activeErrors.filter(e => e.severity === 'critical').length;
  // Mostrar activos primero, luego el resto del historial
  const displayList = [...activeErrors, ...errorHistory.filter(e => e.acknowledged)];

  return (
    <>
      {/* Botón flotante de errores */}
      <TouchableOpacity
        style={[styles.fab, { bottom: insets.bottom + 72 }]}
        onPress={() => setVisible(true)}
        activeOpacity={0.8}
      >
        <Text style={styles.fabIcon}>⚠️</Text>
        {totalActive > 0 && (
          <View style={[styles.fabBadge, totalCritical > 0 && { backgroundColor: C.danger }]}>
            <Text style={styles.fabBadgeText}>{totalActive}</Text>
          </View>
        )}
      </TouchableOpacity>

      {/* Modal de historial */}
      <Modal
        visible={visible}
        animationType="slide"
        transparent
        onRequestClose={() => setVisible(false)}
      >
        <View style={styles.overlay}>
          <View style={[styles.modal, { paddingTop: insets.top + 12 }]}>
            {/* Header */}
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>⚠️ Historial de Errores</Text>
              <TouchableOpacity onPress={() => setVisible(false)}>
                <Text style={styles.closeBtn}>✕</Text>
              </TouchableOpacity>
            </View>

            {/* Stats */}
            <View style={styles.stats}>
              <View style={styles.statItem}>
                <Text style={[styles.statValue, totalActive > 0 && { color: C.danger }]}>{totalActive}</Text>
                <Text style={styles.statLabel}>activos</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>{errorHistory.reduce((s, e) => s + e.count, 0)}</Text>
                <Text style={styles.statLabel}>total ocurrencias</Text>
              </View>
              <TouchableOpacity style={styles.clearBtn} onPress={() => { clearErrors(); clearErrorHistory(); }}>
                <Text style={styles.clearBtnText}>Limpiar</Text>
              </TouchableOpacity>
            </View>

            {/* Lista de errores */}
            {displayList.length === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyText}>Sin errores registrados</Text>
              </View>
            ) : (
              <FlatList
                data={displayList}
                keyExtractor={item => item.id}
                renderItem={({ item }) => <ErrorRow error={item} />}
                contentContainerStyle={styles.list}
              />
            )}
          </View>
        </View>
      </Modal>
    </>
  );
};

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 12,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: C.navy,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.3)',
    shadowColor: C.text,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 999,
    zIndex: 999,
  },
  fabIcon: { fontSize: 18 },
  fabBadge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: C.warning,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  fabBadgeText: { fontSize: 10, fontWeight: '800', color: '#fff' },

  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modal: {
    flex: 1,
    backgroundColor: C.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: C.hairline,
  },
  modalTitle: { fontSize: 16, fontWeight: '700', color: C.text },
  closeBtn: { fontSize: 20, color: C.textDim, padding: 4 },

  stats: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingVertical: 10,
    gap: 16,
  },
  statItem: { alignItems: 'center' },
  statValue: { fontSize: 18, fontWeight: '800', color: C.text },
  statLabel: { fontSize: 9, color: C.textDim, marginTop: 1 },
  clearBtn: {
    marginLeft: 'auto',
    backgroundColor: C.dangerDim,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  clearBtnText: { fontSize: 12, fontWeight: '700', color: C.danger },

  list: { paddingHorizontal: 14, paddingBottom: 20 },
  row: {
    borderRadius: 10,
    borderLeftWidth: 3,
    padding: 12,
    marginBottom: 8,
  },
  rowHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  rowHeaderRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  activeDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  rowCode: { fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  rowTime: { fontSize: 9, color: C.textDim },
  rowMessage: { fontSize: 13, fontWeight: '600', color: C.text },
  rowDetail: { fontSize: 11, color: C.textMuted, marginTop: 2 },
  helpBox: {
    backgroundColor: C.bgElevated,
    borderRadius: 8,
    padding: 10,
    marginTop: 8,
    borderLeftWidth: 2,
    borderLeftColor: C.warning,
  },
  helpLabel: {
    fontSize: 9,
    fontWeight: '800',
    color: C.warning,
    letterSpacing: 1,
    marginBottom: 3,
  },
  helpText: {
    fontSize: 12,
    color: C.textMuted,
    lineHeight: 17,
  },
  rowFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 6,
  },
  tapHint: {
    marginLeft: 'auto',
    fontSize: 10,
    color: C.textDim,
  },
  severityBadge: {
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  severityText: { fontSize: 8, fontWeight: '800', letterSpacing: 0.5 },
  countBadge: {
    backgroundColor: C.bgElevated,
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  countText: { fontSize: 10, fontWeight: '700', color: C.textMuted },

  empty: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: { fontSize: 14, color: C.textMuted },
});
