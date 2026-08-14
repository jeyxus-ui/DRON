/**
 * Tema visual unificado — "Aero Claro".
 * Identidad clara: fondo suave, tarjetas blancas, cabeceras azul marino,
 * acento azul eléctrico. Sin glow ni cristal oscuro.
 */

export const theme = {
  colors: {
    bg:          '#EEF1F6',
    bgElevated:  '#E4E9F1',
    surface:     '#FFFFFF',
    glass:       'rgba(255,255,255,0.75)',
    hairline:    '#DCE2EC',
    hairlineStrong: '#C3CBD9',

    navy:        '#0F2A4A',
    navyElevated:'#173A63',

    primary:     '#2563EB',
    primaryDim:  'rgba(37,99,235,0.10)',
    primaryLight:'#60A5FA',
    cyan:        '#0EA5E9',
    cyanDim:     'rgba(14,165,233,0.10)',
    indigo:      '#4F46E5',
    teal:        '#0D9488',
    success:     '#16A34A',
    danger:      '#DC2626',
    dangerDim:   'rgba(220,38,38,0.10)',
    warning:     '#D97706',

    text:        '#0B1B33',
    textMuted:   '#4B5A6F',
    textDim:     '#94A3B8',
  },
  radii: {
    sm: 8,
    md: 12,
    lg: 16,
    xl: 22,
    pill: 999,
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
  },
  typography: {
    title:  { fontSize: 20, fontWeight: '900' as const, letterSpacing: 3 },
    section: { fontSize: 9, fontWeight: '800' as const, letterSpacing: 2 },
    mono:   { fontFamily: 'monospace' as const },
  },
  glow: {
    amber: { textShadowColor: 'transparent' as const, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 0 },
    red:   { textShadowColor: 'transparent' as const, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 0 },
    cyan:  { textShadowColor: 'transparent' as const, textShadowOffset: { width: 0, height: 0 }, textShadowRadius: 0 },
  },
};

export type Theme = typeof theme;
