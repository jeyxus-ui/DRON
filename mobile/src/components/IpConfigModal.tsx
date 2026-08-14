import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, StyleSheet, TouchableOpacity, Modal, Alert,
} from 'react-native';
import { getStoredIp, saveIp, getStoredMaxAltitude, saveMaxAltitude } from '../utils/ipConfig';
import { getApiUrl, setMaxAltitude } from '../config';
import { authFetch } from '../utils/authFetch';
import { theme } from '../theme';

const C = theme.colors;
const VIOLET = C.primary;
const LABEL = C.textMuted;

interface Props {
  visible: boolean;
  onClose: (changed: boolean) => void;
}

export const IpConfigModal: React.FC<Props> = ({ visible, onClose }) => {
  const [ip, setIp] = useState('');
  const [maxAlt, setMaxAlt] = useState('');

  useEffect(() => {
    if (visible) {
      getStoredIp().then(setIp);
      getStoredMaxAltitude().then(a => setMaxAlt(String(a)));
    }
  }, [visible]);

  const handleSave = async () => {
    const trimmed = ip.trim();
    if (!trimmed) { Alert.alert('Error', 'Ingresa una IP válida'); return; }
    const parts = trimmed.split('.');
    if (parts.length !== 4 || parts.some(p => isNaN(Number(p)) || Number(p) < 0 || Number(p) > 255)) {
      Alert.alert('Error', 'IP inválida (ej: 192.168.1.100)');
      return;
    }
    const altNum = parseInt(maxAlt, 10);
    if (isNaN(altNum) || altNum < 2 || altNum > 500) {
      Alert.alert('Error', 'Límite de altura debe ser entre 2 y 500 m');
      return;
    }
    await saveIp(trimmed);
    await saveMaxAltitude(altNum);
    setMaxAltitude(altNum);
    try {
      await authFetch(`${getApiUrl()}/api/diag/param/set?name=FENCE_ENABLE&value=1`, { method: 'POST' });
      await authFetch(`${getApiUrl()}/api/diag/param/set?name=FENCE_ALT_MAX&value=${altNum}`, { method: 'POST' });
    } catch {
      // backend puede estar offline, se aplicará al reconectar
    }
    onClose(true);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={() => onClose(false)}>
      <View style={styles.overlay}>
        <View style={styles.content}>
          <Text style={styles.title}>CONFIGURACIÓN</Text>
          <Text style={styles.label}>IP del servidor / drone:</Text>
          <TextInput
            style={styles.input}
            value={ip}
            onChangeText={setIp}
            keyboardType="decimal-pad"
            placeholder="192.168.1.100"
            placeholderTextColor={C.textDim}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="next"
          />
          <Text style={styles.divider}>─</Text>
          <Text style={styles.label}>Altura máxima (m):</Text>
          <TextInput
            style={styles.input}
            value={maxAlt}
            onChangeText={setMaxAlt}
            keyboardType="number-pad"
            placeholder="100"
            placeholderTextColor={C.textDim}
            returnKeyType="done"
          />
          <Text style={styles.hint}>La app se reconectará automáticamente al guardar la IP</Text>
          <View style={styles.actions}>
            <TouchableOpacity style={styles.cancelBtn} onPress={() => onClose(false)} activeOpacity={0.7}>
              <Text style={styles.cancelText}>CANCELAR</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.saveBtn} onPress={handleSave} activeOpacity={0.7}>
              <Text style={styles.saveText}>GUARDAR</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  content: {
    width: '100%',
    backgroundColor: C.surface,
    borderWidth: 1.5,
    borderColor: VIOLET + '66',
    borderRadius: 18,
    padding: 20,
  },
  title: {
    color: C.text,
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 2,
    textAlign: 'center',
    marginBottom: 14,
  },
  label: {
    color: LABEL,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  input: {
    backgroundColor: C.bgElevated,
    borderWidth: 1.5,
    borderColor: VIOLET + '44',
    borderRadius: 10,
    color: C.text,
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
    paddingVertical: 12,
    paddingHorizontal: 10,
    fontFamily: 'monospace',
  },
  hint: {
    color: C.textDim,
    fontSize: 8,
    fontWeight: '600',
    textAlign: 'center',
    marginTop: 8,
    marginBottom: 16,
  },
  divider: {
    color: VIOLET + '44',
    fontSize: 14,
    textAlign: 'center',
    marginVertical: 6,
  },
  actions: {
    flexDirection: 'row',
    gap: 8,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    alignItems: 'center',
    backgroundColor: C.glass,
  },
  cancelText: {
    color: C.textMuted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  saveBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: VIOLET + '88',
    alignItems: 'center',
    backgroundColor: C.primaryDim,
  },
  saveText: {
    color: VIOLET,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
});
