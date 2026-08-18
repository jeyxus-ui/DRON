import React, { useRef, useCallback, useEffect } from 'react';
import { View, StyleSheet, Dimensions, Animated, GestureResponderEvent } from 'react-native';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface JoystickProps {
  onMove:          (x: number, y: number) => void;
  size?:           number;
  mode?:           'vertical' | 'horizontal' | 'both' | 'mode2';
  color?:          string;
  smoothing?:      boolean;
  deadzoneX?:      number;
  deadzoneY?:      number;
  resetToBottom?:  boolean;
}

export const Joystick: React.FC<JoystickProps> = ({
  onMove,
  size          = SCREEN_WIDTH * 0.35,
  mode          = 'both',
  color         = '#00ff88',
  smoothing     = false,
  deadzoneX     = 0.05,
  deadzoneY     = 0.04,
  resetToBottom = false,
}) => {
  const stickR  = size / 4;
  const maxDist = size / 2 - stickR;

  const initY = mode === 'mode2' ? maxDist : 0;

  const animX       = useRef(new Animated.Value(0)).current;
  const animY       = useRef(new Animated.Value(initY)).current;
  const throttleRef = useRef(initY);
  const touchId     = useRef<string | null>(null);
  const viewRef     = useRef<View>(null);

  const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

  const normalize = useCallback((px: number, py: number) => {
    if (mode === 'mode2') {
      let ty = clamp(py, -maxDist, maxDist);
      const maxX = Math.sqrt(Math.max(0, maxDist * maxDist - ty * ty));
      let tx = clamp(px, -maxX, maxX);

      animX.setValue(tx);
      animY.setValue(ty);

      let yawNorm      = tx / maxDist;
      let throttleNorm = (maxDist - ty) / (2 * maxDist);
      if (Math.abs(yawNorm) < deadzoneX)      yawNorm = 0;
      if (throttleNorm < deadzoneY) throttleNorm = 0;

      onMove(yawNorm, throttleNorm);
    } else {
      let tx = mode === 'vertical'   ? 0 : px;
      let ty = mode === 'horizontal' ? 0 : py;

      const dist = Math.sqrt(tx * tx + ty * ty);
      if (dist > maxDist) {
        const angle = Math.atan2(ty, tx);
        tx = Math.cos(angle) * maxDist;
        ty = Math.sin(angle) * maxDist;
      }

      animX.setValue(tx);
      animY.setValue(ty);

      let nx =  tx / maxDist;
      let ny = -ty / maxDist;
      if (Math.abs(nx) < deadzoneX) nx = 0;
      if (Math.abs(ny) < deadzoneY) ny = 0;

      onMove(nx, ny);
    }
  }, [mode, maxDist, deadzoneX, deadzoneY, animX, animY, onMove]);

  const resetStick = useCallback(() => {
    if (mode === 'mode2') {
      const currentY = (animY as any)._value;
      throttleRef.current = currentY;
      Animated.spring(animX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }).start();
      const tn = (maxDist - currentY) / (2 * maxDist);
      onMove(0, tn < deadzoneY ? 0 : tn);
    } else {
      Animated.parallel([
        Animated.spring(animX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
        Animated.spring(animY, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
      ]).start();
      onMove(0, 0);
    }
  }, [mode, maxDist, deadzoneY, animX, animY, onMove]);

  useEffect(() => {
    if (mode === 'mode2' && resetToBottom) {
      animX.stopAnimation();
      animY.stopAnimation();
      Animated.spring(animX, { toValue: 0,       useNativeDriver: true, tension: 150, friction: 10 }).start();
      Animated.spring(animY, { toValue: maxDist, useNativeDriver: true, tension: 150, friction: 10 }).start();
      throttleRef.current = maxDist;
      onMove(0, 0);
    }
  }, [resetToBottom]);

  const touchPos = useRef({ x: 0, y: 0 });

  const handleTouchStart = useCallback((e: GestureResponderEvent) => {
    const touch = e.nativeEvent.touches?.[0] ?? e.nativeEvent.changedTouches?.[0];
    if (!touch) return;
    touchId.current = touch.identifier;
    touchPos.current = { x: touch.pageX, y: touch.pageY };

    viewRef.current?.measureInWindow((wx, wy, w, h) => {
      const cx = wx + w / 2;
      const cy = wy + h / 2;
      normalize(touchPos.current.x - cx, touchPos.current.y - cy);
    });
  }, [normalize]);

  const handleTouchMove = useCallback((e: GestureResponderEvent) => {
    const touch = e.nativeEvent.changedTouches?.[0];
    if (!touch) return;
    touchId.current = touch.identifier;
    touchPos.current = { x: touch.pageX, y: touch.pageY };

    viewRef.current?.measureInWindow((wx, wy, w, h) => {
      const cx = wx + w / 2;
      const cy = wy + h / 2;
      normalize(touchPos.current.x - cx, touchPos.current.y - cy);
    });
  }, [normalize]);

  const handleTouchEnd = useCallback(() => {
    touchId.current = null;
    resetStick();
  }, [resetStick]);

  const throttleBarScale = animY.interpolate({
    inputRange:  [-maxDist, maxDist],
    outputRange: [1, 0],
    extrapolate: 'clamp',
  });

  return (
    <View
      ref={viewRef}
      style={[styles.root, { width: size, height: size }]}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
    >
      <View style={[styles.base, {
        width: size, height: size,
        borderRadius: size / 2,
        borderColor:  color + '4D',
      }]}>
        {mode !== 'horizontal' && (
          <View style={[styles.line, styles.lineV, { backgroundColor: color + '33' }]} />
        )}
        {mode !== 'vertical' && (
          <View style={[styles.line, styles.lineH, { backgroundColor: color + '33' }]} />
        )}
        <View style={[styles.centerDot, { backgroundColor: color + '80' }]} />

        {mode === 'mode2' && (
          <View style={[styles.throttleTrack, { borderColor: color + '40' }]}>
            <Animated.View style={[
              styles.throttleFill,
              {
                backgroundColor: color,
                transform: [{ scaleY: throttleBarScale }],
              },
            ]} />
          </View>
        )}
      </View>

      <Animated.View
        style={[
          styles.stick,
          {
            width:           stickR * 2,
            height:          stickR * 2,
            borderRadius:    stickR,
            backgroundColor: color,
            transform: [
              { translateX: animX },
              { translateY: animY },
            ],
          },
        ]}
      >
        <View style={styles.stickInner} />
      </Animated.View>
    </View>
  );
};

const styles = StyleSheet.create({
  root: { justifyContent: 'center', alignItems: 'center' },
  base: {
    position:        'absolute',
    backgroundColor: 'rgba(20,20,30,0.9)',
    borderWidth:     3,
    justifyContent:  'center',
    alignItems:      'center',
    overflow:        'hidden',
  },
  line:  { position: 'absolute' },
  lineV: { width: 2,     height: '80%' },
  lineH: { width: '80%', height: 2     },
  centerDot: { width: 8, height: 8, borderRadius: 4 },

  throttleTrack: {
    position:        'absolute',
    right:           10,
    top:             '15%',
    bottom:          '15%',
    width:           4,
    borderRadius:    2,
    borderWidth:     1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent:  'flex-end',
    overflow:        'hidden',
  },
  throttleFill: {
    width:        '100%',
    height:       '100%',
    borderRadius: 2,
  },

  stick: {
    position:        'absolute',
    justifyContent:  'center',
    alignItems:      'center',
    borderWidth:     2,
    borderColor:     'rgba(255,255,255,0.25)',
    elevation:       15,
    shadowColor:     '#000',
    shadowOffset:    { width: 0, height: 4 },
    shadowOpacity:   0.4,
    shadowRadius:    8,
  },
  stickInner: {
    width:           '60%',
    height:          '60%',
    borderRadius:    100,
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
});
