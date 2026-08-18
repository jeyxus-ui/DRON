import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../context/AuthContext';
import { getHostIp } from '../config';
import { theme } from '../theme';

const C = theme.colors;

export const LoginScreen: React.FC = () => {
  const { login, enterDemo } = useAuth();
  const insets = useSafeAreaInsets();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [lockout, setLockout] = useState(0);
  const lockoutRef = useRef(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const setLockoutFrom = (seconds: number) => {
    lockoutRef.current = seconds;
    setLockout(seconds);
    if (tickRef.current) clearInterval(tickRef.current);
    tickRef.current = setInterval(() => {
      lockoutRef.current -= 1;
      setLockout(lockoutRef.current);
      if (lockoutRef.current <= 0 && tickRef.current) {
        clearInterval(tickRef.current);
        tickRef.current = null;
      }
    }, 1000);
  };

  useEffect(() => () => {
    if (tickRef.current) clearInterval(tickRef.current);
  }, []);

  const handleLogin = async () => {
    setError('');
    if (!username.trim()) {
      setError('Ingresa el nombre de usuario');
      return;
    }
    if (password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres');
      return;
    }
    setBusy(true);
    const result = await login(username.trim(), password);
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? 'Error al iniciar sesión');
      if (result.retryAfter) setLockoutFrom(result.retryAfter);
    }
  };

  const handleDemo = () => {
    setError('');
    enterDemo();
  };

  const host = getHostIp();

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={[styles.center, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 24 }]}>

        {/* ── Marca ── */}
        <View style={styles.brand}>
          <View style={styles.brandBadge}>
            <Text style={styles.brandIcon}>▲</Text>
          </View>
          <Text style={styles.brandTitle}>ODD</Text>
          <Text style={styles.brandSub}>OJO DE DIOS</Text>
        </View>

        {/* ── Tarjeta de login ── */}
        <View style={styles.card}>
          <Text style={styles.cardLabel}>ACCESO OPERADOR</Text>

          <Text style={styles.fieldLabel}>USUARIO</Text>
          <TextInput
            style={styles.input}
            value={username}
            onChangeText={setUsername}
            placeholder="operador"
            placeholderTextColor={C.textDim}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="next"
          />

          <Text style={styles.fieldLabel}>CONTRASEÑA</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor={C.textDim}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="go"
            onSubmitEditing={handleLogin}
          />

          {error !== '' && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          )}

          {lockout > 0 && (
            <View style={styles.lockoutBox}>
              <Text style={styles.lockoutText}>
                ⏱ BLOQUEO TEMPORAL — REINTENTA EN {lockout}s
              </Text>
            </View>
          )}

          <TouchableOpacity
            style={[styles.loginBtn, busy && styles.loginBtnBusy]}
            onPress={handleLogin}
            disabled={busy || lockout > 0}
            activeOpacity={0.8}
          >
            {busy ? (
              <ActivityIndicator color={C.surface} size="small" />
            ) : (
              <Text style={styles.loginBtnText}>INGRESAR</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* ── Modo demo (fallback) ── */}
        <TouchableOpacity style={styles.demoBtn} onPress={handleDemo} activeOpacity={0.7}>
          <Text style={styles.demoBtnText}>MODO DEMO (OFFLINE)</Text>
        </TouchableOpacity>

        {/* ── Pie ── */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>SERVIDOR: {host}:8000</Text>
          <Text style={styles.footerSub}>
            Contraseñas con hash PBKDF2 · bloqueo tras intentos fallidos · sesión con token
          </Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: C.bg,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 28,
    gap: 28,
  },

  brand: {
    alignItems: 'center',
    gap: 6,
  },
  brandBadge: {
    width: 64,
    height: 64,
    borderRadius: 18,
    borderWidth: 2,
    borderColor: C.primary,
    backgroundColor: C.primaryDim,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  brandIcon: {
    color: C.primary,
    fontSize: 30,
    fontWeight: '900',
  },
  brandTitle: {
    color: C.navy,
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: 4,
  },
  brandSub: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 2.5,
  },

  card: {
    backgroundColor: C.surface,
    borderRadius: theme.radii.xl,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    padding: 22,
    gap: 8,
  },
  cardLabel: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 2,
    marginBottom: 6,
  },
  fieldLabel: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginTop: 6,
  },
  input: {
    backgroundColor: C.bgElevated,
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    borderRadius: theme.radii.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: C.text,
    fontSize: 15,
    fontFamily: 'monospace',
    letterSpacing: 1,
  },
  errorBox: {
    backgroundColor: C.dangerDim,
    borderWidth: 1,
    borderColor: C.danger + '66',
    borderRadius: theme.radii.sm,
    padding: 10,
    marginTop: 6,
  },
  errorText: {
    color: C.danger,
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'center',
  },
  lockoutBox: {
    backgroundColor: C.warning + '14',
    borderWidth: 1,
    borderColor: C.warning + '66',
    borderRadius: theme.radii.sm,
    padding: 10,
    marginTop: 2,
    alignItems: 'center',
  },
  lockoutText: {
    color: C.warning,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1,
  },
  loginBtn: {
    backgroundColor: C.primary,
    borderRadius: theme.radii.md,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 12,
  },
  loginBtnBusy: {
    opacity: 0.7,
  },
  loginBtnText: {
    color: C.surface,
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 2.5,
  },

  demoBtn: {
    borderWidth: 1.5,
    borderColor: C.hairlineStrong,
    borderRadius: theme.radii.md,
    paddingVertical: 12,
    alignItems: 'center',
    backgroundColor: C.surface,
  },
  demoBtnText: {
    color: C.textMuted,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.5,
  },

  footer: {
    alignItems: 'center',
    gap: 4,
  },
  footerText: {
    color: C.cyan,
    fontSize: 10,
    fontWeight: '700',
    fontFamily: 'monospace',
    letterSpacing: 1,
  },
  footerSub: {
    color: C.textDim,
    fontSize: 8,
    fontWeight: '600',
    textAlign: 'center',
    letterSpacing: 0.4,
  },
});
