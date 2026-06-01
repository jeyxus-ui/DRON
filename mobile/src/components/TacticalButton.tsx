import React, { useRef } from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  Animated,
  View,
} from 'react-native';

interface TacticalButtonProps {
  label: string;
  icon: string;
  color?: string;
  onPress: () => void;
  disabled?: boolean;
  compact?: boolean;
  active?: boolean;
  size?: 'normal' | 'large';
}

export const TacticalButton: React.FC<TacticalButtonProps> = ({
  label,
  icon,
  color = '#00ff88',
  onPress,
  disabled = false,
  compact = false,
  active = false,
  size = 'normal',
}) => {
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handlePressIn = () => {
    Animated.spring(scaleAnim, {
      toValue: 0.95,
      useNativeDriver: true,
      tension: 150,
      friction: 8,
    }).start();
  };

  const handlePressOut = () => {
    Animated.spring(scaleAnim, {
      toValue: 1,
      useNativeDriver: true,
      tension: 150,
      friction: 8,
    }).start();
  };

  return (
    <Animated.View style={[{ transform: [{ scale: scaleAnim }] }, size === 'large' ? styles.largeWrapper : compact ? styles.compactWrapper : styles.wrapper]}>
      <TouchableOpacity
        onPress={onPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={disabled}
        activeOpacity={0.8}
        style={[
          size === 'large' ? styles.largeButton : compact ? styles.compactButton : styles.button,
          {
            borderColor: disabled ? '#333' : active ? color : color + '80',
            backgroundColor: disabled ? '#111' : active ? color + '25' : color + '12',
          },
          !disabled && {
            shadowColor: color,
            shadowOffset: { width: 0, height: active ? 6 : 3 },
            shadowOpacity: active ? 0.8 : 0.4,
            shadowRadius: active ? 16 : 8,
            elevation: active ? 12 : 6,
          },
        ]}
      >
        <Text style={[
          size === 'large' ? styles.largeIcon : compact ? styles.compactIcon : styles.icon,
          { color: disabled ? '#444' : color },
        ]}>
          {icon}
        </Text>
        <Text style={[
          size === 'large' ? styles.largeLabel : compact ? styles.compactLabel : styles.label,
          { color: disabled ? '#444' : '#ddd' },
        ]}>
          {label}
        </Text>
      </TouchableOpacity>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  wrapper: { flex: 1 },
  compactWrapper: { flex: 1 },
  largeWrapper: { flex: 1 },
  button: {
    paddingVertical: 10,
    paddingHorizontal: 6,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    gap: 3,
  },
  compactButton: {
    paddingVertical: 7,
    paddingHorizontal: 4,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    gap: 2,
  },
  largeButton: {
    paddingVertical: 16,
    paddingHorizontal: 10,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    gap: 6,
    minWidth: 80,
  },
  icon: { fontSize: 16, lineHeight: 20 },
  compactIcon: { fontSize: 13, lineHeight: 16 },
  largeIcon: { fontSize: 20, lineHeight: 24 },
  label: { fontSize: 9, fontWeight: '800', letterSpacing: 0.8 },
  compactLabel: { fontSize: 8, fontWeight: '800', letterSpacing: 0.5 },
  largeLabel: { fontSize: 11, fontWeight: '900', letterSpacing: 1 },
});
