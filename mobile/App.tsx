import React, { useState } from 'react';
import { View, StyleSheet, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthProvider, useAuth } from './src/context/AuthContext';
import { DroneProvider } from './src/context/DroneContext';
import { DroneControlScreen } from './src/screens/DroneControlScreen';
import { TelemetryScreen }    from './src/screens/TelemetryScreen';
import { GPSScreen } from './src/screens/GPSScreen';
import { WaypointScreen }     from './src/screens/WaypointScreen';
import { BenchTestScreen }    from './src/screens/BenchTestScreen';
import { LoginScreen } from './src/screens/LoginScreen';
import { ErrorHistoryModal } from './src/components/ErrorHistoryModal';
import { theme } from './src/theme';

const C = theme.colors;

const TAB_ACCENTS = [C.primary, C.cyan, C.indigo, C.teal, C.warning];

const SCREENS = [
  { id: 'control',   component: DroneControlScreen, label: 'CONTROL', icon: '⚡', accent: TAB_ACCENTS[0] },
  { id: 'gps',       component: GPSScreen,           label: 'GPS',     icon: '🛰', accent: TAB_ACCENTS[1] },
  { id: 'waypoint',  component: WaypointScreen,      label: 'RUTA',    icon: '🎯', accent: TAB_ACCENTS[2] },
  { id: 'telemetry', component: TelemetryScreen,     label: 'DATA',    icon: '📡', accent: TAB_ACCENTS[3] },
  { id: 'bench',     component: BenchTestScreen,     label: 'BENCH',   icon: '🧪', accent: TAB_ACCENTS[4] },
];

const SplashScreen: React.FC = () => (
  <View style={styles.splash}>
    <View style={styles.splashBadge}>
      <Text style={styles.splashIcon}>▲</Text>
    </View>
    <Text style={styles.splashTitle}>DRON GCS</Text>
    <Text style={styles.splashSub}>RESTAURANDO SESIÓN…</Text>
    <ActivityIndicator color={C.primary} size="small" style={styles.splashSpinner} />
  </View>
);

function AppShell() {
  const { status, isDemo, logout } = useAuth();
  const [activeIdx, setActiveIdx] = useState(0);
  const ScreenComponent = SCREENS[activeIdx].component;

  if (status === 'loading') return <SplashScreen />;
  if (status === 'anonymous') return <LoginScreen />;

  return (
    <DroneProvider>
      <View style={styles.root}>
        <ErrorHistoryModal />
        <View style={styles.screen}>
          <ScreenComponent />
        </View>
        <View style={styles.tabBar}>
          {SCREENS.map((s, i) => {
            const accent = s.accent;
            return (
              <TouchableOpacity
                key={s.id}
                style={[styles.tabItem, activeIdx === i && { backgroundColor: accent + '14' }]}
                onPress={() => setActiveIdx(i)}
                activeOpacity={0.75}
              >
                <Text style={styles.tabIcon}>{s.icon}</Text>
                <Text style={[styles.tabLabel, { color: activeIdx === i ? accent : C.textDim }]}>
                  {s.label}
                </Text>
                {activeIdx === i && (
                  <View style={[styles.tabIndicator, { backgroundColor: accent }]} />
                )}
              </TouchableOpacity>
            );
          })}
          <TouchableOpacity style={styles.logoutBtn} onPress={logout} activeOpacity={0.75}>
            <Text style={styles.logoutIcon}>⏻</Text>
            <Text style={styles.logoutLabel}>{isDemo ? 'DEMO' : 'SALIR'}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </DroneProvider>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex:            1,
    backgroundColor: C.bg,
  },
  screen: {
    flex:            1,
    backgroundColor: C.bg,
  },

  // ── Splash ──
  splash: {
    flex:            1,
    backgroundColor: C.bg,
    alignItems:      'center',
    justifyContent:  'center',
    gap:             8,
  },
  splashBadge: {
    width: 72,
    height: 72,
    borderRadius: theme.radii.lg,
    borderWidth: 2,
    borderColor: C.primary,
    backgroundColor: C.primaryDim,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  splashIcon: {
    color: C.primary,
    fontSize: 34,
    fontWeight: '900',
  },
  splashTitle: {
    color: C.navy,
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: 5,
  },
  splashSub: {
    color: C.textMuted,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 2.5,
  },
  splashSpinner: {
    marginTop: 18,
  },

  // ── Tab bar ──
  tabBar: {
    flexDirection:   'row',
    backgroundColor: C.surface,
    borderTopWidth:  1.5,
    borderTopColor:  C.hairlineStrong,
    paddingBottom:   4,
    shadowColor:     C.text,
    shadowOffset:    { width: 0, height: -3 },
    shadowOpacity:   0.08,
    shadowRadius:    6,
    elevation:       8,
  },
  tabItem: {
    flex:           1,
    alignItems:     'center',
    paddingVertical: 8,
    gap:            2,
    position:       'relative',
  },
  tabIcon:  { fontSize: 15 },
  tabLabel: {
    fontSize:        8,
    fontWeight:      '800',
    letterSpacing:   1.5,
  },
  tabIndicator: {
    position:        'absolute',
    top:             0,
    left:            '25%',
    right:           '25%',
    height:          2.5,
    borderRadius:    1.5,
  },

  // ── Logout ──
  logoutBtn: {
    width:            54,
    alignItems:       'center',
    justifyContent:   'center',
    paddingVertical:  8,
    gap:              2,
    borderLeftWidth:  1,
    borderLeftColor:  C.hairline,
  },
  logoutIcon: {
    color:      C.textMuted,
    fontSize:   15,
    fontWeight: '700',
  },
  logoutLabel: {
    color:      C.textDim,
    fontSize:   7,
    fontWeight: '800',
    letterSpacing: 1,
  },
});
