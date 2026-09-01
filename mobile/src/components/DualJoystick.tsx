import React, { useRef, useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, Animated, GestureResponderEvent } from 'react-native';

interface DualJoystickProps {
  onLeftMove: (x: number, y: number) => void;
  onRightMove: (x: number, y: number) => void;
  onLeftTouchActive?: (active: boolean) => void;
  onRightTouchActive?: (active: boolean) => void;
  leftSize: number;
  rightSize: number;
  leftColor?: string;
  rightColor?: string;
  leftResetToBottom?: boolean;
}

export const DualJoystick: React.FC<DualJoystickProps> = ({
  onLeftMove,
  onRightMove,
  onLeftTouchActive,
  onRightTouchActive,
  leftSize,
  rightSize,
  leftColor = '#FF8800',
  rightColor = '#3B82F6',
  leftResetToBottom = false,
}) => {
  const leftResetToBottomRef = useRef(leftResetToBottom);
  useEffect(() => { leftResetToBottomRef.current = leftResetToBottom; }, [leftResetToBottom]);
  const containerRef = useRef<View>(null);
  const containerPos = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const activeTouches = useRef<Map<number, { side: 'left' | 'right' }>>(new Map());

  const leftStickR = leftSize / 4;
  const leftMaxDist = leftSize / 2 - leftStickR;
  const leftAnimX = useRef(new Animated.Value(0)).current;
  const leftAnimY = useRef(new Animated.Value(0)).current;

  const rightStickR = rightSize / 4;
  const rightMaxDist = rightSize / 2 - rightStickR;
  const rightAnimX = useRef(new Animated.Value(0)).current;
  const rightAnimY = useRef(new Animated.Value(0)).current;

  const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

  const hasLeftTouch = () => {
    for (const info of activeTouches.current.values()) {
      if (info.side === 'left') return true;
    }
    return false;
  };

  const hasRightTouch = () => {
    for (const info of activeTouches.current.values()) {
      if (info.side === 'right') return true;
    }
    return false;
  };

  const getCenter = (side: 'left' | 'right') => {
    const { x, y, w, h } = containerPos.current;
    return side === 'left'
      ? { cx: x + w * 0.25, cy: y + h / 2 }
      : { cx: x + w * 0.75, cy: y + h / 2 };
  };

  const normalizeLeft = useCallback((pageX: number, pageY: number) => {
    const { cx, cy } = getCenter('left');
    const dx = pageX - cx;
    const dy = pageY - cy;

    const tx = clamp(dx, -leftMaxDist, leftMaxDist);
    const ty = clamp(dy, -leftMaxDist, leftMaxDist);

    leftAnimX.setValue(tx);
    leftAnimY.setValue(ty);

    const x = tx / leftMaxDist;        // derecha = +yaw (giro)
    const y = -ty / leftMaxDist;       // arriba = +throttle

    onLeftMove(x, y);
  }, [leftMaxDist, leftAnimX, leftAnimY, onLeftMove]);

  const normalizeRight = useCallback((pageX: number, pageY: number) => {
    const { cx, cy } = getCenter('right');
    const dx = pageX - cx;
    const dy = pageY - cy;

    const dxClamped = clamp(dx, -rightMaxDist, rightMaxDist);
    const dyClamped = clamp(dy, -rightMaxDist, rightMaxDist);

    rightAnimX.setValue(dxClamped);
    rightAnimY.setValue(dyClamped);

    const x = dxClamped / rightMaxDist;  // derecha = +roll (lateral)
    const y = -dyClamped / rightMaxDist; // arriba = +pitch (avance)

    onRightMove(x, y);
  }, [rightMaxDist, rightAnimX, rightAnimY, onRightMove]);

  const handleTouchStart = useCallback((e: GestureResponderEvent) => {
    const touches = e.nativeEvent.touches;
    if (!touches) return;

    const snapshot: { id: number; pageX: number; pageY: number }[] = [];
    for (let i = 0; i < touches.length; i++) {
      snapshot.push({ id: touches[i].identifier, pageX: touches[i].pageX, pageY: touches[i].pageY });
    }

    containerRef.current?.measureInWindow((x, y, w, h) => {
      containerPos.current = { x, y, w, h };
      const midX = x + w / 2;

      for (const t of snapshot) {
        const side = t.pageX < midX ? 'left' : 'right';
        activeTouches.current.set(t.id, { side });
        if (side === 'left') {
          onLeftTouchActive?.(true);
          normalizeLeft(t.pageX, t.pageY);
        } else {
          onRightTouchActive?.(true);
          normalizeRight(t.pageX, t.pageY);
        }
      }
    });
  }, [normalizeLeft, normalizeRight, onLeftTouchActive]);

  const handleTouchMove = useCallback((e: GestureResponderEvent) => {
    const changed = e.nativeEvent.changedTouches;
    if (!changed) return;

    for (let i = 0; i < changed.length; i++) {
      const t = changed[i];
      const info = activeTouches.current.get(t.identifier);
      if (!info) continue;
      if (info.side === 'left') normalizeLeft(t.pageX, t.pageY);
      else normalizeRight(t.pageX, t.pageY);
    }
  }, [normalizeLeft, normalizeRight]);

  const handleTouchEnd = useCallback((e: GestureResponderEvent) => {
    const changed = e.nativeEvent.changedTouches;
    if (!changed) return;

    for (let i = 0; i < changed.length; i++) {
      const t = changed[i];
      const info = activeTouches.current.get(t.identifier);
      if (!info) continue;
      activeTouches.current.delete(t.identifier);

      if (info.side === 'left') {
        if (!hasLeftTouch()) {
          onLeftTouchActive?.(false);
          Animated.parallel([
            Animated.spring(leftAnimX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
            Animated.spring(leftAnimY, { toValue: leftMaxDist, useNativeDriver: true, tension: 150, friction: 10 }),
          ]).start();
          onLeftMove(0, -1);
        }
      } else {
        if (!hasRightTouch()) {
          onRightTouchActive?.(false);
          Animated.parallel([
            Animated.spring(rightAnimX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
            Animated.spring(rightAnimY, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
          ]).start();
          onRightMove(0, 0);
        }
      }
    }
  }, [leftMaxDist, leftAnimX, leftAnimY, rightAnimX, rightAnimY, onLeftMove, onRightMove, onLeftTouchActive]);

  useEffect(() => {
    if (leftResetToBottom) {
      leftAnimX.stopAnimation();
      leftAnimY.stopAnimation();
      Animated.parallel([
        Animated.spring(leftAnimX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
        Animated.spring(leftAnimY, { toValue: leftMaxDist, useNativeDriver: true, tension: 150, friction: 10 }),
      ]).start();
      onLeftMove(0, -1);
    }
  }, [leftResetToBottom]);

  const leftThrottleScale = leftAnimY.interpolate({
    inputRange: [-leftMaxDist, leftMaxDist],
    outputRange: [1, 0],
    extrapolate: 'clamp',
  });

  const renderJoystick = (
    side: 'left' | 'right',
    size: number,
    color: string,
    animX: Animated.Value,
    animY: Animated.Value,
    showThrottle: boolean,
  ) => {
    const stickR = size / 4;
    const axisLabel = side === 'left' ? 'ALT · LATERAL' : 'PITCH · YAW';
    return (
      <View style={{ width: size, height: size + 36, justifyContent: 'center', alignItems: 'center' }}>
        <Text style={[styles.label, { color }]}>{axisLabel}</Text>
        <View style={{ width: size, height: size, justifyContent: 'center', alignItems: 'center' }}>
          <View style={[styles.base, { width: size, height: size, borderRadius: size / 2, borderColor: color + '4D' }]}>
            <View style={[styles.ring, { width: size * 0.6, height: size * 0.6, borderRadius: size * 0.3, borderColor: color + '26' }]} />
            <View style={[styles.deadzone, { width: size * 0.1, height: size * 0.1, borderRadius: size * 0.05, borderColor: color + '40' }]} />
            <View style={[styles.line, styles.lineV, { backgroundColor: color + '33' }]} />
            <View style={[styles.line, styles.lineH, { backgroundColor: color + '33' }]} />
            <View style={[styles.tick, styles.tickTop, { backgroundColor: color + '59' }]} />
            <View style={[styles.tick, styles.tickBottom, { backgroundColor: color + '59' }]} />
            <View style={[styles.tick, styles.tickLeft, { backgroundColor: color + '59' }]} />
            <View style={[styles.tick, styles.tickRight, { backgroundColor: color + '59' }]} />
            <View style={[styles.centerDot, { backgroundColor: color + '80' }]} />
            {showThrottle && (
              <View style={[styles.throttleTrack, { borderColor: color + '40' }]}>
                <Animated.View style={[styles.throttleFill, { backgroundColor: color, transform: [{ scaleY: leftThrottleScale }] }]} />
              </View>
            )}
          </View>
          <Animated.View style={[styles.stick, {
            width: stickR * 2, height: stickR * 2, borderRadius: stickR, backgroundColor: color,
            transform: [{ translateX: animX }, { translateY: animY }],
          }]}>
            <View style={styles.stickInner} />
          </Animated.View>
        </View>
      </View>
    );
  };

  return (
    <View
      ref={containerRef}
      style={styles.container}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
    >
      {renderJoystick('left', leftSize, leftColor, leftAnimX, leftAnimY, true)}
      {renderJoystick('right', rightSize, rightColor, rightAnimX, rightAnimY, false)}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    alignSelf: 'stretch',
  },
  base: {
    position: 'absolute',
    backgroundColor: 'rgba(20,20,30,0.9)',
    borderWidth: 3,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  line: { position: 'absolute' },
  lineV: { width: 2, height: '80%' },
  lineH: { width: '80%', height: 2 },
  centerDot: { width: 8, height: 8, borderRadius: 4 },
  ring: {
    position: 'absolute',
    borderWidth: 1.5,
  },
  deadzone: {
    position: 'absolute',
    borderWidth: 1.5,
    borderStyle: 'dashed',
    opacity: 0.8,
  },
  tick: { position: 'absolute', borderRadius: 1 },
  tickTop: { width: 3, height: 10, top: '8%' },
  tickBottom: { width: 3, height: 10, bottom: '8%' },
  tickLeft: { width: 10, height: 3, left: '8%' },
  tickRight: { width: 10, height: 3, right: '8%' },
  label: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1,
    opacity: 0.85,
    marginBottom: 6,
  },
  throttleTrack: {
    position: 'absolute',
    right: 10,
    top: '15%',
    bottom: '15%',
    width: 4,
    borderRadius: 2,
    borderWidth: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
    overflow: 'hidden',
  },
  throttleFill: {
    width: '100%',
    height: '100%',
    borderRadius: 2,
  },
  stick: {
    position: 'absolute',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.25)',
    elevation: 15,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
  },
  stickInner: {
    width: '60%',
    height: '60%',
    borderRadius: 100,
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
});
