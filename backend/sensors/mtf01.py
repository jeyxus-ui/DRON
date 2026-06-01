"""
MTF01 ultrasonic distance sensor.
Real: communicates via I2C (address 0x57) or PWM.
Sim: generates realistic distance readings.

Range: 2cm - 400cm
Accuracy: ±1cm
Update rate: 20Hz
"""
import logging
import math
import time
from typing import Optional
from .base import BaseSensor, DistanceReading

logger = logging.getLogger(__name__)

MTF01_I2C_ADDR = 0x57
MTF01_MIN_CM = 2
MTF01_MAX_CM = 400


class MTF01Sensor(BaseSensor):
    def __init__(self, sim_mode: bool = True, i2c_bus: int = 1, i2c_addr: int = MTF01_I2C_ADDR):
        super().__init__('MTF01', sim_mode)
        self.i2c_bus = i2c_bus
        self.i2c_addr = i2c_addr
        self._device = None
        self._last_distance = 0.0
        self._sim_start = 0.0

    def start(self) -> bool:
        if self.sim_mode:
            logger.info('[MTF01] Modo simulación — distancias simuladas')
            self._sim_start = time.time()
            self._running = True
            return True
        try:
            import smbus
            self._device = smbus.SMBus(self.i2c_bus)
            self._running = True
            logger.info('[MTF01] Conectado por I2C bus=%d addr=0x%02x', self.i2c_bus, self.i2c_addr)
            return True
        except ImportError:
            logger.error('[MTF01] smbus no disponible en esta plataforma')
            return False
        except Exception as e:
            logger.error('[MTF01] Error conectando: %s', e)
            self._error_count += 1
            return False

    def stop(self):
        self._running = False
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        logger.info('[MTF01] Detenido')

    def read(self) -> DistanceReading:
        t = time.time()
        if not self._running:
            return DistanceReading(timestamp=t, valid=False)
        if self.sim_mode:
            return self._sim_read(t)
        return self._real_read(t)

    def _sim_read(self, t: float) -> DistanceReading:
        elapsed = t - self._sim_start
        sim_distance = 1.5 + 1.0 * math.sin(elapsed * 0.3)
        sim_distance = max(MTF01_MIN_CM / 100, min(MTF01_MAX_CM / 100, sim_distance))
        self._last_distance = sim_distance
        return DistanceReading(
            timestamp=t,
            valid=True,
            distance_m=round(sim_distance, 3),
        )

    def _real_read(self, t: float) -> DistanceReading:
        try:
            data = self._device.read_i2c_block_data(self.i2c_addr, 0x01, 2)
            raw = (data[0] << 8) | data[1]
            cm = raw / 58.0
            cm = max(MTF01_MIN_CM, min(MTF01_MAX_CM, cm))
            self._last_distance = cm / 100.0
            return DistanceReading(timestamp=t, valid=True, distance_m=self._last_distance)
        except Exception as e:
            logger.error('[MTF01] Error leyendo: %s', e)
            self._error_count += 1
            return DistanceReading(timestamp=t, valid=False, distance_m=self._last_distance)

    def get_distance(self) -> Optional[float]:
        return self.read().distance_m if self._running else None
