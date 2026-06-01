import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    timestamp: float = 0.0
    valid: bool = False


@dataclass
class DistanceReading(SensorReading):
    distance_m: float = 0.0


@dataclass
class LidarPoint:
    angle_deg: float
    distance_m: float
    quality: int


@dataclass
class LidarScan(SensorReading):
    points: list = field(default_factory=list)
    min_angle: float = 0.0
    max_angle: float = 360.0


class BaseSensor(ABC):
    def __init__(self, name: str, sim_mode: bool = True):
        self.name = name
        self.sim_mode = sim_mode
        self._running = False
        self._error_count = 0

    @abstractmethod
    def start(self) -> bool:
        ...

    @abstractmethod
    def stop(self):
        ...

    @abstractmethod
    def read(self):
        ...

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> dict:
        return {
            'name': self.name,
            'running': self._running,
            'sim_mode': self.sim_mode,
            'errors': self._error_count,
        }
