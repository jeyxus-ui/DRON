import { useState, useEffect, useRef } from 'react';
import Geolocation, { GeolocationResponse, GeolocationError } from '@react-native-community/geolocation';

interface DeviceLocation {
  latitude: number;
  longitude: number;
  accuracy: number;
  altitude: number | null;
  speed: number | null;
  timestamp: number;
}

export function useDeviceLocation() {
  const [location, setLocation] = useState<DeviceLocation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const watchId = useRef<number | null>(null);

  useEffect(() => {
    Geolocation.requestAuthorization(
      () => {
        setAuthorized(true);
        watchId.current = Geolocation.watchPosition(
          (pos: GeolocationResponse) => {
            setLocation({
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
              accuracy: pos.coords.accuracy,
              altitude: pos.coords.altitude,
              speed: pos.coords.speed,
              timestamp: pos.timestamp,
            });
            setError(null);
          },
          (err: GeolocationError) => {
            setError(err.message);
          },
          {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 5000,
            distanceFilter: 1,
          },
        );
      },
      () => {
        setAuthorized(false);
        setError('Location permission denied');
      },
    );

    return () => {
      if (watchId.current !== null) {
        Geolocation.clearWatch(watchId.current);
      }
    };
  }, []);

  return { location, error, authorized };
}
