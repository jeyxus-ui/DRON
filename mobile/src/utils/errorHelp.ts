/**
 * Mapa de posibles motivos para cada código de error.
 * El usuario puede ver esto al abrir el historial de errores.
 */
export const ERROR_HELP: Record<string, string> = {
  // WebSocket
  'WS_CREATE':    'No se pudo crear la conexión WebSocket. Revisa que el backend esté corriendo y que la IP del servidor sea correcta en Configuración.',
  'WS_ERROR':     'Error de conexión con el servidor. El backend puede haber dejado de responder o la red está inestable.',
  'WS_CLOSED':    'Se perdió la conexión con el servidor. El dron puede seguir funcionando pero no recibirás telemetría.',
  'WS_RECONNECT': 'Intentando reconectar al servidor. Si el problema persiste, revisa que el backend esté activo.',
  'WS_CONNECTED': 'Conexión establecida correctamente con el servidor.',
  'WS_PARSE':     'Error al interpretar un mensaje del servidor. Posible incompatibilidad de versiones.',

  // Comandos
  'CMD_FAILED':   'El comando enviado al dron fue rechazado. Revisa que el dron esté armado y en el modo correcto.',
  'CMD_TIMEOUT':  'El dron no respondió al comando en 5 segundos. Revisa la conexión MAVLink con el Pixhawk.',

  // Telemetría
  'TELEMETRY_ERROR': 'Error al recibir datos de telemetría del dron. Revisa conexión MAVLink.',
  'DEMO_MODE':    'Modo demostración activo: los datos mostrados son simulados, no del dron real. Conecta el backend con MAVLink para datos reales.',

  // Cámara
  'CAM_ERROR':    'Error general de la cámara. Revisa que la cámara esté conectada por USB y que los drivers estén instalados.',
  'CAM_HTTP_ERROR': 'No se pudo cargar el stream de la cámara (error HTTP). Revisa que el servidor de video esté corriendo en el backend.',
  'CAM_NETWORK':  'No se puede conectar al servidor de video. Revisa la IP y que el puerto 8000 esté accesible.',
  'CAM_NOT_CONNECTED': 'No se detecta ninguna cámara conectada al backend. Revisa cable USB, que la cámara esté encendida y los drivers instalados.',
  'CAM_OK':       'La cámara se ha conectado correctamente.',

  // ARM/DISARM
  'ARM_FAILED':   'No se pudo armar el dron. El backend no tiene conexión con el Pixhawk — verifica cable USB, puerto serie y que el dron esté encendido.',
  'DISARM_FAILED':'No se pudo desarmar el dron. El backend no tiene conexión con el Pixhawk — verifica cable USB y heartbeat MAVLink.',
  'ARM_OK':       'Dron armado correctamente.',
  'DISARM_OK':    'Dron desarmado correctamente.',

  // TAKEOFF/LAND
  'TAKEOFF_FAILED':'No se pudo iniciar el despegue. Revisa que el dron esté armado, con GPS fijo y batería suficiente.',
  'LAND_FAILED':   'No se pudo iniciar el aterrizaje. Revisa conexión MAVLink y que el dron esté en un modo que permita landing.',
  'RTL_FAILED':    'No se pudo iniciar el regreso a casa (RTL). Revisa que el home position esté configurado.',

  // Emergency
  'EMERGENCY_STOP': 'Parada de emergencia activada. El dron debería detenerse inmediatamente.',
  'EMERGENCY_RTL':  'Regreso a casa (RTL) de emergencia activado.',
  'EMERGENCY_LAND': 'Aterrizaje de emergencia activado.',

  // Sensores
  'SENSOR_MTF01_ERROR': 'Error leyendo sensor ultrasónico MTF01 (I2C). Revisa cableado y dirección I2C 0x57.',
  'SENSOR_LIDAR_ERROR': 'Error leyendo LIDAR YDLIDAR X4 (serial). Revisa cableado USB y puerto /dev/ttyUSB1.',
  'SENSOR_NO_DATA':     'No se reciben datos de sensores. El bridge raspberry puede no estar corriendo.',

  // General
  'UNKNOWN':      'Error desconocido. Revisa los logs del backend para más detalles.',
};

export function getErrorHelp(code: string): string | undefined {
  return ERROR_HELP[code] ?? ERROR_HELP['UNKNOWN'];
}
