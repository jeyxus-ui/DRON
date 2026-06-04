/**
 * Configuración de conexión al backend.
 * La IP se puede modificar desde la app (botón ⚙ en GCS).
 * Se persiste con RNFS, valor por defecto: 192.168.137.121.
 */

const DEFAULT_HOST = '192.168.137.121';
let currentHost: string = DEFAULT_HOST;

export const getHostIp = (): string => currentHost;
export const setHostIp = (ip: string): void => { currentHost = ip; };
export const resetHostIp = (): void => { currentHost = DEFAULT_HOST; };

export const getApiUrl = (): string => `http://${currentHost}:8000`;
export const getWsUrl = (): string => `ws://${currentHost}:8000/ws/telemetry`;

// Para imports estáticos que no pueden cambiar (ej: WebView)
export const STATIC_API_URL = `http://${DEFAULT_HOST}:8000`;
