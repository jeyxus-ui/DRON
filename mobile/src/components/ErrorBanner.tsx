import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useDrone, AppError } from '../context/DroneContext';

const SEVERITY_COLORS: Record<string, string> = {
  info: '#00B4D8',
  warn: '#ffaa00',
  error: '#ff6644',
  critical: '#ff0044',
};

const AUTO_DISMISS_MS: Record<string, number> = {
  info: 4000,
  warn: 6000,
  error: 8000,
  critical: 12000,
};

// IDs descartados localmente (solo del banner, no afecta al contexto)
const dismissedLocally = new Set<string>();

const ErrorCard: React.FC<{ error: AppError }> = ({ error }) => {
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(-20)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      Animated.timing(translateY, { toValue: 0, duration: 200, useNativeDriver: true }),
    ]).start();
    const timer = setTimeout(() => {
      dismissedLocally.add(error.id);
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }).start();
    }, AUTO_DISMISS_MS[error.severity] ?? 6000);
    return () => clearTimeout(timer);
  }, []);

  const color = SEVERITY_COLORS[error.severity] ?? '#888';

  const handleDismiss = () => {
    dismissedLocally.add(error.id);
    Animated.timing(opacity, { toValue: 0, duration: 150, useNativeDriver: true }).start();
  };

  return (
    <Animated.View style={[styles.card, { borderLeftColor: color, opacity, transform: [{ translateY }] }]}>
      <View style={styles.cardContent}>
        <View style={styles.cardHeader}>
          <Text style={[styles.cardCode, { color }]}>{error.code}</Text>
          {error.count > 1 && (
            <View style={[styles.countBadge, { backgroundColor: color }]}>
              <Text style={styles.countText}>x{error.count}</Text>
            </View>
          )}
        </View>
        <Text style={styles.cardMessage}>{error.message}</Text>
        {error.detail && <Text style={styles.cardDetail}>{error.detail}</Text>}
      </View>
      <TouchableOpacity onPress={handleDismiss} style={styles.dismissBtn}>
        <Text style={styles.dismissText}>✕</Text>
      </TouchableOpacity>
    </Animated.View>
  );
};

export const ErrorBanner: React.FC = () => {
  const { errors } = useDrone();
  const insets = useSafeAreaInsets();

  const visible = errors
    .filter(e => !e.acknowledged && !dismissedLocally.has(e.id))
    .slice(0, 3);

  if (visible.length === 0) return null;

  return (
    <View style={[styles.container, { top: insets.top + 8 }]}>
      {visible.map(err => (
        <ErrorCard key={err.id} error={err} />
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: 8,
    right: 8,
    zIndex: 9999,
    gap: 6,
  },
  card: {
    backgroundColor: 'rgba(10,10,20,0.92)',
    borderRadius: 10,
    borderLeftWidth: 3,
    padding: 10,
    flexDirection: 'row',
    alignItems: 'flex-start',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 8,
  },
  cardContent: {
    flex: 1,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 2,
  },
  cardCode: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1,
  },
  countBadge: {
    borderRadius: 8,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  countText: {
    fontSize: 9,
    fontWeight: '700',
    color: '#fff',
  },
  cardMessage: {
    fontSize: 13,
    fontWeight: '600',
    color: '#ddd',
  },
  cardDetail: {
    fontSize: 11,
    color: '#666',
    marginTop: 2,
  },
  dismissBtn: {
    padding: 4,
    marginLeft: 8,
  },
  dismissText: {
    color: '#555',
    fontSize: 14,
    fontWeight: '700',
  },
});
