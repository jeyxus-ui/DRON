import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, StyleSheet, TouchableOpacity, Modal, Alert,
} from 'react-native';
import { getStoredIp, saveIp } from '../utils/ipConfig';

const VIOLET = '#8B5CF6';
const LABEL = '#666';

interface Props {
  visible: boolean;
  onClose: (changed: boolean) => void;
}

export const IpConfigModal: React.FC<Props> = ({ visible, onClose }) => {
  const [ip, setIp] = useState('');

  useEffect(() => {
    if (visible) {
      getStoredIp().then(setIp);
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
    await saveIp(trimmed);
    onClose(true);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={() => onClose(false)}>
      <View style={styles.overlay}>
        <View style={styles.content}>
          <Text style={styles.title}>CONFIGURACIÓN DE RED</Text>
          <Text style={styles.label}>IP del servidor / drone:</Text>
          <TextInput
            style={styles.input}
            value={ip}
            onChangeText={setIp}
            keyboardType="decimal-pad"
            placeholder="192.168.1.100"
            placeholderTextColor="#444"
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="done"
            onSubmitEditing={handleSave}
          />
          <Text style={styles.hint}>La app se reconectará automáticamente al guardar</Text>
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
    backgroundColor: 'rgba(15,20,35,0.95)',
    borderWidth: 1.5,
    borderColor: VIOLET + '66',
    borderRadius: 18,
    padding: 20,
    shadowColor: VIOLET,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 12,
  },
  title: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 2,
    textAlign: 'center',
    marginBottom: 14,
    textShadowColor: VIOLET,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 6,
  },
  label: {
    color: LABEL,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  input: {
    backgroundColor: 'rgba(0,0,0,0.4)',
    borderWidth: 1.5,
    borderColor: VIOLET + '44',
    borderRadius: 10,
    color: '#fff',
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
    paddingVertical: 12,
    paddingHorizontal: 10,
    fontFamily: 'monospace',
  },
  hint: {
    color: '#555',
    fontSize: 8,
    fontWeight: '600',
    textAlign: 'center',
    marginTop: 8,
    marginBottom: 16,
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
    borderColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  cancelText: {
    color: '#888',
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
    backgroundColor: VIOLET + '20',
    shadowColor: VIOLET,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 6,
  },
  saveText: {
    color: VIOLET,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
    textShadowColor: VIOLET,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 4,
  },
});
