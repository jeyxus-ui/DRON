/**
 * Configuración de conexión al backend.
 * En BlueStacks/emulador, usa la IP LAN del host (ej: 192.168.20.38).
 * Para ADB reverse (emulador estándar), usar 'localhost'.
 * Para dispositivo real en misma red, usar la IP LAN del servidor.
 */
const HOST_IP = '192.168.137.121';

export const API_URL = `http://${HOST_IP}:8000`;
export const WS_URL = `ws://${HOST_IP}:8000/ws/telemetry`;
