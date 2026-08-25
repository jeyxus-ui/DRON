/**
 * Controles básicos de vuelo para drones — esquema Mode 2.
 *
 * Genera comandos de vuelo normalizados a partir de dos joysticks virtuales.
 * NO controla motores directamente: produce los comandos throttle/roll/pitch/yaw
 * que luego son interpretados por un controlador de vuelo (MAVLink/Pixhawk).
 *
 * Mapeo de control:
 *   Joystick IZQUIERDO : Y = throttle/altura (arriba +), X = lateral/roll (derecha +)
 *   Joystick DERECHO   : Y = pitch/avance    (arriba +), X = yaw/giro    (derecha +)
 *
 * Rangos de salida:
 *   roll/pitch/yaw : -1.0 .. 1.0
 *   throttle       : -1.0 .. 1.0  (0 = neutro / mantener altura, +1 = subir, -1 = bajar)
 */

export type FlightAxis = 'throttle' | 'roll' | 'pitch' | 'yaw';

export interface AxisConfig {
  /** Zona muerta (fracción de deflexión total, 0..1). Valores |v| < deadzone → 0. */
  deadzone: number;
  /** Sensibilidad 0..1 (multiplicador del eje). 1 = máxima deflexión. */
  sensitivity: number;
  /** Invierte el eje (útil por orientación del hardware). */
  inverted: boolean;
  /** Límite inferior de salida. */
  min: number;
  /** Límite superior de salida. */
  max: number;
}

export interface FlightControlConfig {
  throttle: AxisConfig;
  roll: AxisConfig;
  pitch: AxisConfig;
  yaw: AxisConfig;
  /** Suavizado 0..1 (mayor = más responsive, menor = más suave). */
  smoothing: number;
}

export interface FlightCommands {
  throttle: number;
  roll: number;
  pitch: number;
  yaw: number;
}

export interface StickInput {
  /** Deflexión horizontal normalizada -1..1 (derecha = +). */
  x: number;
  /** Deflexión vertical normalizada -1..1 (arriba = +). */
  y: number;
}

export const DEFAULT_FLIGHT_CONFIG: FlightControlConfig = {
  throttle: { deadzone: 0.05, sensitivity: 1.2, inverted: false, min: -1, max: 1 },
  roll: { deadzone: 0.05, sensitivity: 1.2, inverted: false, min: -1, max: 1 },
  pitch: { deadzone: 0.05, sensitivity: 1.2, inverted: false, min: -1, max: 1 },
  yaw: { deadzone: 0.05, sensitivity: 1.2, inverted: false, min: -1, max: 1 },
  smoothing: 0.45,
};

export function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

/**
 * Aplica zona muerta con reentrada progresiva para evitar saltos bruscos:
 * el rango [deadzone, 1] se escala linealmente a [0, 1].
 */
export function applyDeadzone(v: number, deadzone: number): number {
  const az = Math.abs(v);
  if (az <= deadzone) return 0;
  const sign = Math.sign(v);
  return sign * ((az - deadzone) / (1 - deadzone));
}

/** Aplica dead zone + sensibilidad + inversión + límites a un eje. */
export function shapeAxis(raw: number, cfg: AxisConfig): number {
  let v = applyDeadzone(raw, cfg.deadzone);
  v = v * cfg.sensitivity;
  if (cfg.inverted) v = -v;
  return clamp(v, cfg.min, cfg.max);
}

/**
 * Mapea los dos joysticks al esquema Mode 2, produciendo comandos de vuelo
 * claramente separados en throttle/roll/pitch/yaw.
 */
export function mapMode2(
  left: StickInput,
  right: StickInput,
  cfg: FlightControlConfig,
): FlightCommands {
  return {
    throttle: shapeAxis(left.y,  cfg.throttle),
    roll:     shapeAxis(left.x,  cfg.roll),
    pitch:    shapeAxis(right.y, cfg.pitch),
    yaw:      shapeAxis(right.x, cfg.yaw),
  };
}

/**
 * Puente MAVLink/Pixhawk: convierte los comandos de vuelo (-1..1) al formato
 * que espera el backend RC override.
 *  - roll/pitch/yaw se envían tal cual (-1..1).
 *  - throttle (-1..1, 0 = neutro) se lleva a 0..1 (0.5 = mantener altura).
 */
export function toRcOverride(cmd: FlightCommands): {
  throttle: number;
  roll: number;
  pitch: number;
  yaw: number;
} {
  const throttle01 = clamp((cmd.throttle + 1) / 2, 0, 1);
  return {
    throttle: throttle01,
    roll: cmd.roll,
    pitch: cmd.pitch,
    yaw: cmd.yaw,
  };
}

/**
 * Controlador de vuelo: mantiene el estado suavizado de los comandos y los
 * envía de forma progresiva. Al volver el joystick al centro, el comando
 * retorna progresivamente a 0 (suavizado exponencial).
 */
export class FlightController {
  private cfg: FlightControlConfig;
  private target: FlightCommands = { throttle: 0, roll: 0, pitch: 0, yaw: 0 };
  private current: FlightCommands = { throttle: 0, roll: 0, pitch: 0, yaw: 0 };
  private timer: ReturnType<typeof setInterval> | null = null;
  onCommand?: (cmd: FlightCommands) => void;

  constructor(cfg: FlightControlConfig = DEFAULT_FLIGHT_CONFIG) {
    this.cfg = cfg;
  }

  setConfig(partial: Partial<FlightControlConfig>): void {
    const next: FlightControlConfig = { ...this.cfg };
    (['throttle', 'roll', 'pitch', 'yaw'] as FlightAxis[]).forEach((k) => {
      if (partial[k]) next[k] = { ...next[k], ...(partial[k] as AxisConfig) };
    });
    if (partial.smoothing !== undefined) next.smoothing = partial.smoothing;
    this.cfg = next;
  }

  /** Actualiza el objetivo a partir de comandos ya mapeados. */
  setTarget(partial: Partial<FlightCommands>): void {
    this.target = { ...this.target, ...partial };
  }

  /** Actualiza el objetivo a partir de la lectura cruda de ambos joysticks. */
  setTargetSticks(left: StickInput, right: StickInput): void {
    this.target = mapMode2(left, right, this.cfg);
  }

  /** Lleva todos los comandos a 0 de inmediato (emergencia / desarme). */
  reset(): void {
    const zero: FlightCommands = { throttle: 0, roll: 0, pitch: 0, yaw: 0 };
    this.target = zero;
    this.current = zero;
    this.onCommand?.(zero);
  }

  /** Lleva el throttle al mínimo (stick abajo) y el resto a 0 — estado seguro para armar/desarmar. */
  resetToMin(): void {
    const min: FlightCommands = { throttle: -1, roll: 0, pitch: 0, yaw: 0 };
    this.target = min;
    this.current = min;
    this.onCommand?.(min);
  }

  start(intervalMs = 50): void {
    if (this.timer) return;
    this.timer = setInterval(() => this.tick(), intervalMs);
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private tick(): void {
    const dt = 0.05;
    const alpha = clamp(this.cfg.smoothing * dt * 20, 0.02, 1);
    let changed = false;
    (['throttle', 'roll', 'pitch', 'yaw'] as FlightAxis[]).forEach((k) => {
      const next = this.current[k] + (this.target[k] - this.current[k]) * alpha;
      if (Math.abs(next - this.current[k]) > 1e-4) changed = true;
      this.current[k] = Math.abs(next) < 1e-3 ? 0 : next;
    });
    if (changed) this.onCommand?.({ ...this.current });
  }

  getCurrent(): FlightCommands {
    return { ...this.current };
  }
}
