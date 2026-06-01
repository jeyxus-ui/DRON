/**
 * URL del backend (Raspberry Pi) para pruebas.
 * En producción puedes usar: process.env.NEXT_PUBLIC_BACKEND_URL
 */
const BACKEND_HOST = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://192.168.137.43:8000';

export const API_URL = BACKEND_HOST;
export const WS_URL = BACKEND_HOST.replace(/^http/, 'ws') + '/ws/telemetry';
