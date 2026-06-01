import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, TouchableOpacity } from 'react-native';

interface StatusBarProps {
  connected: boolean;
  mode: string;
  modeColor: string;
  modeIcon: string;
  armed: boolean;
  demoMode: boolean;
  onMenuPress: () => void;
  insetsTop: number;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  connected,
  mode,
  modeColor,
  modeIcon,
  armed,
  demoMode,
  onMenuPress,
  insetsTop,
}) => {
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (armed) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.2, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulseAnim.setValue(1);
    }
  }, [armed]);

  const demoPulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (demoMode) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(demoPulse, { toValue: 1.3, duration: 800, useNativeDriver: true }),
          Animated.timing(demoPulse, { toValue: 1, duration: 800, useNativeDriver: true }),
        ])
      ).start();
    } else {
      demoPulse.setValue(1);
    }
  }, [demoMode]);

  return (
    <View style={[styles.container, { paddingTop: insetsTop + 4, paddingBottom: 4 }]}>
      <TouchableOpacity onPress={onMenuPress} style={styles.menuBtn} activeOpacity={0.7}>
        <View style={styles.menuLine} />
        <View style={[styles.menuLine, { width: 14 }]} />
        <View style={styles.menuLine} />
      </TouchableOpacity>

      <View style={[styles.pill, { borderColor: connected ? '#00ff8840' : '#ff004440' }]}>
        <View style={[styles.dot, { backgroundColor: connected ? '#00ff88' : '#ff0044' }]} />
        <Text style={[styles.pillText, { color: connected ? '#00ff88' : '#ff4444' }]}>
          {connected ? 'ONLINE' : 'OFFLINE'}
        </Text>
      </View>

      <View style={[styles.modePill, { borderColor: modeColor + '60', backgroundColor: modeColor + '18' }]}>
        <Text style={[styles.modeIcon, { color: modeColor }]}>{modeIcon}</Text>
        <Text style={[styles.modeText, { color: modeColor }]}>{mode}</Text>
      </View>

      {demoMode && (
        <Animated.View style={[styles.demoBadge, { transform: [{ scale: demoPulse }] }]}>
          <Text style={styles.demoBadgeText}>DEMO</Text>
        </Animated.View>
      )}

      <Animated.View style={[
        styles.armBadge,
        armed
          ? { borderColor: '#ff004460', backgroundColor: '#ff000020', transform: [{ scale: pulseAnim }] }
          : { borderColor: '#333' },
      ]}>
        <View style={[styles.armDot, { backgroundColor: armed ? '#ff4466' : '#555' }]} />
        <Text style={[styles.armText, { color: armed ? '#ff4466' : '#555' }]}>
          {armed ? 'ARMADO' : 'STAND-BY'}
        </Text>
      </Animated.View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    gap: 6,
    backgroundColor: 'rgba(5,5,8,0.95)',
    borderBottomWidth: 1,
    borderBottomColor: '#0d0d1a',
  },
  menuBtn: {
    width: 30,
    height: 30,
    backgroundColor: 'rgba(0,0,0,0.75)',
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#00ff8830',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 3,
  },
  menuLine: { width: 16, height: 2, backgroundColor: '#00ff88', borderRadius: 1 },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.9)',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 16,
    borderWidth: 1.5,
    gap: 6,
    shadowColor: '#00ff88',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 4,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  pillText: { fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  demoBadge: {
    backgroundColor: 'rgba(255,170,0,0.2)',
    borderWidth: 1,
    borderColor: '#ffaa0040',
    borderRadius: 10,
    paddingHorizontal: 6,
    paddingVertical: 2,
    shadowColor: '#ffaa00',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.5,
    shadowRadius: 4,
    elevation: 3,
  },
  demoBadgeText: { color: '#ffaa00', fontSize: 7, fontWeight: '900', letterSpacing: 1.5 },
  armBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 12,
    borderWidth: 1,
    gap: 4,
  },
  armDot: { width: 4, height: 4, borderRadius: 2 },
  armText: { fontSize: 7, fontWeight: '800', letterSpacing: 0.8 },
});
