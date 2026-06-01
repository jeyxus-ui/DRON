import React, { useRef, useState } from 'react';
import { View, Dimensions, StyleSheet, FlatList, Text, TouchableOpacity, Animated } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { DroneProvider } from './src/context/DroneContext';
import { DroneControlScreen } from './src/screens/DroneControlScreen';
import { TelemetryScreen }    from './src/screens/TelemetryScreen';
import { GPSScreen } from './src/screens/GPSScreen';
import { WaypointScreen }     from './src/screens/WaypointScreen';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

const SCREENS = [
  { id: 'control',   component: DroneControlScreen, label: 'CONTROL', icon: '⚡' },
  { id: 'gps',       component: GPSScreen,           label: 'GPS',     icon: '🛰' },
  { id: 'waypoint',  component: WaypointScreen,      label: 'RUTA',    icon: '🎯' },
  { id: 'telemetry', component: TelemetryScreen,     label: 'DATA',    icon: '📡' },
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
            {SCREENS.map((s, i) => (
              <TouchableOpacity
                key={s.id}
                style={[styles.tabItem, activeIdx === i && styles.tabItemActive]}
                onPress={() => scrollToScreen(i)}
                activeOpacity={0.75}
              >
                <Text style={styles.tabIcon}>{s.icon}</Text>
                <Text style={[styles.tabLabel, activeIdx === i && styles.tabLabelActive]}>
                  {s.label}
                </Text>
                {activeIdx === i && <View style={styles.tabIndicator} />}
              </TouchableOpacity>
            ))}
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
    backgroundColor: '#07070d',
    borderTopWidth:  1,
    borderTopColor:  '#0d0d1a',
    paddingBottom:   4,
  },
  tabItem: {
    flex:           1,
    alignItems:     'center',
    paddingVertical: 8,
    gap:            2,
    position:       'relative',
  },
  tabItemActive: {
    backgroundColor: '#00ff8808',
  },
  tabIcon:  { fontSize: 15 },
  tabLabel: {
    color:       '#333',
    fontSize:    8,
    fontWeight:  '800',
    letterSpacing: 1.5,
  },
  tabLabelActive: { color: '#00ff88' },
  tabIndicator: {
    position:        'absolute',
    top:             0,
    left:            '25%',
    right:           '25%',
    height:          2,
    backgroundColor: '#00ff88',
    borderRadius:    1,
  },
});