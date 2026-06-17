/**
 * Configuración de conexión al backend.
 * La IP se puede modificar desde la app (botón ⚙ en GCS).
 * Se persiste con RNFS, valor por defecto: 172.20.10.2.
 */

const DEFAULT_HOST = '172.20.10.2';
let currentHost: string = DEFAULT_HOST;

export const getHostIp = (): string => currentHost;
export const setHostIp = (ip: string): void => { currentHost = ip; };
export const resetHostIp = (): void => { currentHost = DEFAULT_HOST; };

export const getApiUrl = (): string => `http://${currentHost}:8000`;
export const getWsUrl = (): string => `ws://${currentHost}:8000/ws/telemetry`;

// Para componentes que necesitan IP dinámica (ej: WebView)
export const getStaticApiUrl = (): string => `http://${currentHost}:8000`;
