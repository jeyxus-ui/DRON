import React, { useRef, useCallback, useEffect } from 'react';
import { View, StyleSheet, Dimensions, PanResponder, Animated } from 'react-native';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface JoystickProps {
  onMove:          (x: number, y: number) => void;
  size?:           number;
  mode?:           'vertical' | 'horizontal' | 'both' | 'mode2';
  color?:          string;
  smoothing?:      boolean;
  deadzoneX?:      number;
  deadzoneY?:      number;
  resetToBottom?:  boolean; // pulso para resetear throttle al fondo (al armar)
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

  // mode2: throttle inicia abajo (maxDist), persiste al soltar
  const initY = mode === 'mode2' ? maxDist : 0;

  const animX       = useRef(new Animated.Value(0)).current;
  const animY       = useRef(new Animated.Value(initY)).current;
  const throttleRef = useRef(initY);

  const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

  const notify = useCallback((x: number, y: number) => {
    onMove(x, y);
  }, [onMove]);

  // ── Reset al fondo cuando se arma el dron ──────────────────────────────────
  useEffect(() => {
    if (mode === 'mode2' && resetToBottom) {
      animX.stopAnimation();
      animY.stopAnimation();
      Animated.spring(animX, { toValue: 0,       useNativeDriver: true, tension: 150, friction: 10 }).start();
      Animated.spring(animY, { toValue: maxDist, useNativeDriver: true, tension: 150, friction: 10 }).start();
      throttleRef.current = maxDist;
      notify(0, 0); // throttle 0 al armar
    }
  }, [resetToBottom]);

  const panResponder = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder:  () => true,

    onPanResponderGrant: () => {
      animX.stopAnimation();
      animY.stopAnimation();
      if (mode === 'mode2') {
        throttleRef.current = (animY as any)._value;
      }
    },

    onPanResponderMove: (_, g) => {
      if (mode === 'mode2') {
        // Y relativo a donde estaba el throttle
        let ty = clamp(throttleRef.current + g.dy, -maxDist, maxDist);
        const maxX = Math.sqrt(Math.max(0, maxDist * maxDist - ty * ty));
        let tx = clamp(g.dx, -maxX, maxX);

        animX.setValue(tx);
        animY.setValue(ty);

        // Normalizar: x = yaw (-1..1), y = throttle (0..1)
        let yawNorm      = tx / maxDist;
        let throttleNorm = (maxDist - ty) / (2 * maxDist); // abajo=0, arriba=1
        if (Math.abs(yawNorm) < deadzoneX) yawNorm = 0;
        if (throttleNorm < deadzoneY)       throttleNorm = 0;

        notify(yawNorm, throttleNorm);

      } else {
        let tx = mode === 'vertical'   ? 0 : g.dx;
        let ty = mode === 'horizontal' ? 0 : g.dy;

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

        notify(nx, ny);
      }
    },

    onPanResponderRelease: () => {
      if (mode === 'mode2') {
        // Guardar posición Y actual — throttle se QUEDA donde está
        const currentY = (animY as any)._value;
        throttleRef.current = currentY;
        animX.stopAnimation();
        animY.stopAnimation();
        // Solo X (yaw) vuelve al centro
        Animated.spring(animX, {
          toValue: 0, useNativeDriver: true, tension: 150, friction: 10,
        }).start();
        const throttleNorm = (maxDist - currentY) / (2 * maxDist);
        notify(0, throttleNorm < deadzoneY ? 0 : throttleNorm);
      } else {
        // Joystick derecho: ambos ejes vuelven al centro
        Animated.parallel([
          Animated.spring(animX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
          Animated.spring(animY, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
        ]).start();
        notify(0, 0);
      }
    },

    onPanResponderTerminate: () => {
      if (mode === 'mode2') {
        const currentY = (animY as any)._value;
        throttleRef.current = currentY;
        animX.stopAnimation();
        animY.stopAnimation();
        Animated.spring(animX, {
          toValue: 0, useNativeDriver: true, tension: 150, friction: 10,
        }).start();
        const throttleNorm = (maxDist - currentY) / (2 * maxDist);
        notify(0, throttleNorm < deadzoneY ? 0 : throttleNorm);
      } else {
        Animated.parallel([
          Animated.spring(animX, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
          Animated.spring(animY, { toValue: 0, useNativeDriver: true, tension: 150, friction: 10 }),
        ]).start();
        notify(0, 0);
      }
    },
  })).current;

  // Barra de throttle animada (mode2)
  // ⚠️ 'height' no es soportado por useNativeDriver — usamos scaleY en su lugar
  const throttleBarScale = animY.interpolate({
    inputRange:  [-maxDist, maxDist],
    outputRange: [1, 0],        // arriba=escala 1 (lleno), abajo=escala 0 (vacío)
    extrapolate: 'clamp',
  });

  return (
    <View style={[styles.root, { width: size, height: size }]}>
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
        {...panResponder.panHandlers}
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
    height:       '100%',   // ocupa todo — scaleY lo reduce desde el centro
    borderRadius: 2,
    // transformOrigin no existe en RN, pero scaleY desde height:100% + overflow hidden
    // da el efecto correcto de barra que crece desde abajo
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