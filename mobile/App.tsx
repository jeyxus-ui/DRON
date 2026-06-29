import React, { useRef, useState } from 'react';
import { View, Dimensions, StyleSheet, FlatList, Text, TouchableOpacity, Animated } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { DroneProvider } from './src/context/DroneContext';
import { DroneControlScreen } from './src/screens/DroneControlScreen';
import { TelemetryScreen }    from './src/screens/TelemetryScreen';
import { GPSScreen } from './src/screens/GPSScreen';
import { WaypointScreen }     from './src/screens/WaypointScreen';
import { ErrorBanner } from './src/components/ErrorBanner';
import { ErrorHistoryModal } from './src/components/ErrorHistoryModal';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

const TAB_ACCENTS = ['#FF8800', '#00B4D8', '#8B5CF6', '#14B8A6'];

const SCREENS = [
  { id: 'control',   component: DroneControlScreen, label: 'CONTROL', icon: '⚡', accent: TAB_ACCENTS[0] },
  { id: 'gps',       component: GPSScreen,           label: 'GPS',     icon: '🛰', accent: TAB_ACCENTS[1] },
  { id: 'waypoint',  component: WaypointScreen,      label: 'RUTA',    icon: '🎯', accent: TAB_ACCENTS[2] },
  { id: 'telemetry', component: TelemetryScreen,     label: 'DATA',    icon: '📡', accent: TAB_ACCENTS[3] },
];

export default function App() {
  const flatListRef  = useRef<FlatList>(null);
  const [activeIdx, setActiveIdx] = useState(0);

  const scrollToScreen = (index: number) => {
    flatListRef.current?.scrollToIndex({ index, animated: true });
    setActiveIdx(index);
  };

  const onViewableItemsChanged = useRef(({ viewableItems }: any) => {
    if (viewableItems.length > 0) {
      setActiveIdx(viewableItems[0].index ?? 0);
    }
  }).current;

  const renderScreen = ({ item }: { item: (typeof SCREENS)[0] }) => {
    const ScreenComponent = item.component;
    return (
      <View style={styles.screen}>
        <ScreenComponent />
      </View>
    );
  };

  return (
    <SafeAreaProvider>
      <DroneProvider>
        <View style={styles.root}>
          <ErrorBanner />
          <ErrorHistoryModal />
          <FlatList
            ref={flatListRef}
            data={SCREENS}
            renderItem={renderScreen}
            keyExtractor={(item) => item.id}
            horizontal
            pagingEnabled
            showsHorizontalScrollIndicator={false}
            bounces={false}
            scrollEventThrottle={16}
            onViewableItemsChanged={onViewableItemsChanged}
            viewabilityConfig={{ itemVisiblePercentThreshold: 50 }}
          />

          {/* ── Tab bar de navegación ── */}
          <View style={styles.tabBar}>
            {SCREENS.map((s, i) => {
              const accent = s.accent;
              return (
                <TouchableOpacity
                  key={s.id}
                  style={[styles.tabItem, activeIdx === i && { backgroundColor: accent + '12' }]}
                  onPress={() => scrollToScreen(i)}
                  activeOpacity={0.75}
                >
                  <Text style={styles.tabIcon}>{s.icon}</Text>
                  <Text style={[styles.tabLabel, { color: activeIdx === i ? accent : '#333' }]}>
                    {s.label}
                  </Text>
                  {activeIdx === i && (
                    <View style={[styles.tabIndicator, { backgroundColor: accent }]} />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      </DroneProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex:            1,
    backgroundColor: '#050508',
  },
  screen: {
    width:           SCREEN_WIDTH,
    flex:            1,
    backgroundColor: '#050508',
  },

  // ── Tab bar ──
  tabBar: {
    flexDirection:   'row',
    backgroundColor: 'rgba(15,25,40,0.35)',
    borderTopWidth:  1.5,
    borderTopColor:  'rgba(255,255,255,0.18)',
    paddingBottom:   4,
    shadowColor:     '#000',
    shadowOffset:    { width: 0, height: -4 },
    shadowOpacity:   0.3,
    shadowRadius:    8,
    elevation:       12,
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
    fontSize:    8,
    fontWeight:  '800',
    letterSpacing: 1.5,
  },
  tabIndicator: {
    position:        'absolute',
    top:             0,
    left:            '25%',
    right:           '25%',
    height:          2,
    borderRadius:    1,
    shadowOffset:    { width: 0, height: 0 },
    shadowOpacity:   0.8,
    shadowRadius:    6,
    elevation:       6,
  },
});