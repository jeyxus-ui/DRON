import React, { useRef, useCallback, useEffect } from 'react';
import { View, StyleSheet, Animated, GestureResponderEvent } from 'react-native';

interface DualJoystickProps {
  onLeftMove: (x: number, y: number) => void;
  onRightMove: (x: number, y: number) => void;
  leftSize: number;
  rightSize: number;
  leftColor?: string;
  rightColor?: string;
  leftResetToBottom?: boolean;
}

const DEADZONE_X = 0.05;
const DEADZONE_Y = 0.04;

export const DualJoystick: React.FC<DualJoystickProps> = ({
  onLeftMove,
  onRightMove,
  leftSize,
  rightSize,
  leftColor = '#FF8800',
  rightColor = '#3B82F6',
  leftResetToBottom = false,
}) => {
  const containerRef = useRef<View>(null);
  const containerPos = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const activeTouches = useRef<Map<number, { side: 'left' | 'right' }>>(new Map());

  const leftStickR = leftSize / 4;
  const leftMaxDist = leftSize / 2 - leftStickR;
  const leftAnimX = useRef(new Animated.Value(0)).current;
  const leftAnimY = useRef(new Animated.Value(leftMaxDist)).current;

  const rightStickR = rightSize / 4;
  const rightMaxDist = rightSize / 2 - rightStickR;
  const rightAnimX = useRef(new Animated.Value(0)).current;
  const rightAnimY = useRef(new Animated.Value(0)).current;

  const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

  const getCenter = (side: 'left' | 'right') => {
    const { x, y, w, h } = containerPos.current;
    return side === 'left'
      ? { cx: x + w * 0.25, cy: y + h / 2 }
      : { cx: x + w * 0.75, cy: y + h / 2 };
  };

  const normalizeLeft = useCallback((pageX: number, pageY: number) => {
    const { cx, cy } = getCenter('left');
    let dx = pageX - cx;
    let dy = pageY - cy;

    let ty = clamp(dy, -leftMaxDist, leftMaxDist);
    const maxX = Math.sqrt(Math.max(0, leftMaxDist * leftMaxDist - ty * ty));
    let tx = clamp(dx, -maxX, maxX);

    leftAnimX.setValue(tx);
    leftAnimY.setValue(ty);

    let yawNorm = tx / leftMaxDist;
    let throttleNorm = (leftMaxDist - ty) / (2 * leftMaxDist);
    if (Math.abs(yawNorm) < DEADZONE_X) yawNorm = 0;
    if (throttleNorm < DEADZONE_Y) throttleNorm = 0;

    onLeftMove(yawNorm, throttleNorm);
  }, [leftMaxDist, leftAnimX, leftAnimY, onLeftMove]);

  const normalizeRight = useCallback((pageX: number, pageY: number) => {
    const { cx, cy } = getCenter('right');
    let dx = pageX - cx;
    let dy = pageY - cy;

    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist > rightMaxDist) {
      const angle = Math.atan2(dy, dx);
      dx = Math.cos(angle) * rightMaxDist;
      dy = Math.sin(angle) * rightMaxDist;
    }

    rightAnimX.setValue(dx);
    rightAnimY.setValue(dy);

    let nx = dx / rightMaxDist;
    let ny = -dy / rightMaxDist;
    if (Math.abs(nx) < DEADZONE_X) nx = 0;
    if (Math.abs(ny) < DEADZONE_Y) ny = 0;

    onRightMove(nx, ny);
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
        if (side === 'left') normalizeLeft(t.pageX, t.pageY);
        else normalizeRight(t.pageX, t.pageY);
      }
    });
  }, [normalizeLeft, normalizeRight]);

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
        Animated.spring(leftAnimX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }).start();
        Animated.spring(leftAnimY, { toValue: leftMaxDist, useNativeDriver: true, tension: 150, friction: 10 }).start();
        onLeftMove(0, 0);
      } else {
        Animated.parallel([
          Animated.spring(rightAnimX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
          Animated.spring(rightAnimY, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
        ]).start();
        onRightMove(0, 0);
      }
    }
  }, [leftMaxDist, leftAnimX, leftAnimY, rightAnimX, rightAnimY, onLeftMove, onRightMove]);

  useEffect(() => {
    if (leftResetToBottom) {
      leftAnimX.stopAnimation();
      leftAnimY.stopAnimation();
      Animated.spring(leftAnimX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }).start();
      Animated.spring(leftAnimY, { toValue: leftMaxDist, useNativeDriver: true, tension: 150, friction: 10 }).start();
      onLeftMove(0, 0);
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
    return (
      <View style={{ width: size, height: size, justifyContent: 'center', alignItems: 'center' }}>
        <View style={[styles.base, { width: size, height: size, borderRadius: size / 2, borderColor: color + '4D' }]}>
          <View style={[styles.line, styles.lineV, { backgroundColor: color + '33' }]} />
          <View style={[styles.line, styles.lineH, { backgroundColor: color + '33' }]} />
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
