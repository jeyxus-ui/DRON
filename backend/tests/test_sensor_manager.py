"""Tests unitarios para backend/sensors/manager.py — SensorManager."""
from unittest.mock import MagicMock
import pytest

from backend.sensors.manager import SensorManager
from backend.sensors.base import DistanceReading, LidarScan, LidarPoint


@pytest.fixture
def manager(monkeypatch):
    mock_mtf = MagicMock()
    mock_mtf.start.return_value = True
    mock_mtf.status = {'name': 'mtf01', 'running': True}
    mock_mtf.read.return_value = DistanceReading(timestamp=0, valid=False, distance_m=0.0)
    mock_lidar = MagicMock()
    mock_lidar.start.return_value = True
    mock_lidar.status = {'name': 'lidar', 'running': True}
    mock_lidar.read.return_value = LidarScan(timestamp=0, valid=False, points=[])

    monkeypatch.setattr('backend.sensors.manager.MTF01Sensor', lambda sim_mode: mock_mtf)
    monkeypatch.setattr('backend.sensors.manager.YDLidarX4', lambda sim_mode: mock_lidar)

    sm = SensorManager(sim_mode=True)
    sm.mtf01 = mock_mtf
    sm.lidar = mock_lidar
    return sm


class TestStartStop:
    def test_start_succeeds_when_a_sensor_starts(self, manager):
        assert manager.start() is True
        assert manager._running is True
        manager.stop()

    def test_start_fails_when_no_sensor_starts(self, manager):
        manager.mtf01.start.return_value = False
        manager.lidar.start.return_value = False
        assert manager.start() is False
        assert manager._running is False

    def test_stop_stops_both_sensors(self, manager):
        manager.start()
        manager.stop()
        manager.mtf01.stop.assert_called_once()
        manager.lidar.stop.assert_called_once()
        assert manager._running is False


class TestYawAndVision:
    def test_set_drone_yaw(self, manager):
        manager.set_drone_yaw(45.0)
        assert manager._drone_yaw == 45.0

    def test_update_from_vision_stores_detections(self, manager):
        detections = [MagicMock(distance=3.0, bbox=(0, 0, 10, 10), zone='safe')]
        manager.update_from_vision(detections, drone_yaw_deg=10.0, frame_width=800)
        assert manager._latest_vision == detections
        assert manager._last_frame_width == 800

    def test_update_from_vision_uses_current_yaw_if_not_given(self, manager):
        manager.set_drone_yaw(99.0)
        manager.update_from_vision([], drone_yaw_deg=None)
        # No debe lanzar; el yaw usado internamente es el guardado.


class TestGetForwardDistance:
    def test_returns_none_when_invalid(self, manager):
        manager._latest_mtf01 = DistanceReading(timestamp=0, valid=False, distance_m=0)
        assert manager.get_forward_distance() is None

    def test_returns_distance_when_valid(self, manager):
        manager._latest_mtf01 = DistanceReading(timestamp=0, valid=True, distance_m=1.5)
        assert manager.get_forward_distance() == 1.5


class TestGetData:
    def test_shape_with_no_sensors_valid(self, manager):
        data = manager.get_data()
        assert set(data.keys()) == {
            'mtf01', 'lidar', 'vision', 'obstacle_map', 'drone_yaw', 'safe_direction',
        }
        assert data['mtf01']['valid'] is False
        assert data['lidar']['valid'] is False
        assert data['vision']['valid'] is False

    def test_includes_mtf01_distance_when_valid(self, manager):
        manager._latest_mtf01 = DistanceReading(timestamp=0, valid=True, distance_m=2.5)
        data = manager.get_data()
        assert data['mtf01']['distance_m'] == 2.5

    def test_includes_closest_lidar_point(self, manager):
        points = [LidarPoint(angle_deg=10, distance_m=5.0, quality=100),
                  LidarPoint(angle_deg=20, distance_m=1.5, quality=100)]
        manager._latest_lidar = LidarScan(timestamp=0, valid=True, points=points)
        data = manager.get_data()
        assert data['lidar']['closest_distance'] == 1.5
        assert data['lidar']['closest_angle'] == 20.0
        assert data['lidar']['points'] == 2

    def test_includes_closest_vision_detection(self, manager):
        det = MagicMock(distance=2.0, bbox=(300, 200, 340, 240), zone='warning', label='person')
        manager._latest_vision = [det]
        manager._last_frame_width = 640
        data = manager.get_data()
        assert data['vision']['closest']['label'] == 'person'
        assert data['vision']['closest']['distance_m'] == 2.0
        assert data['vision']['count'] == 1

    def test_vision_far_detections_excluded(self, manager):
        det = MagicMock(distance=999, bbox=(0, 0, 10, 10), zone='safe')
        manager._latest_vision = [det]
        data = manager.get_data()
        assert data['vision']['closest'] is None

    def test_vision_bad_bbox_falls_back_to_zero_angle(self, manager):
        det = MagicMock(distance=2.0, zone='safe', label='x')
        det.bbox = None  # provoca excepción al desempaquetar
        manager._latest_vision = [det]
        data = manager.get_data()
        assert data['vision']['closest']['angle_offset_deg'] == 0.0


class TestStatus:
    def test_get_status_shape(self, manager):
        status = manager.get_status()
        assert status['sim_mode'] is True
        assert 'mtf01' in status and 'lidar' in status


class TestHasObstacleAhead:
    def test_false_by_default(self, manager):
        assert manager.has_obstacle_ahead() is False

    def test_true_when_mtf01_close(self, manager):
        manager._latest_mtf01 = DistanceReading(timestamp=0, valid=True, distance_m=1.0)
        assert manager.has_obstacle_ahead(threshold_m=2.0) is True

    def test_true_when_lidar_point_close_and_frontal(self, manager):
        points = [LidarPoint(angle_deg=10, distance_m=1.0, quality=100)]
        manager._latest_lidar = LidarScan(timestamp=0, valid=True, points=points)
        assert manager.has_obstacle_ahead(threshold_m=2.0) is True

    def test_false_when_lidar_point_close_but_lateral(self, manager):
        points = [LidarPoint(angle_deg=90, distance_m=1.0, quality=100)]
        manager._latest_lidar = LidarScan(timestamp=0, valid=True, points=points)
        assert manager.has_obstacle_ahead(threshold_m=2.0) is False


class TestSafeDirectionProperty:
    def test_returns_current_heading_when_clear(self, manager):
        manager.set_drone_yaw(15.0)
        assert manager.safe_direction == 15.0


class TestLoop:
    def test_loop_single_iteration_updates_obstacle_map(self, manager, monkeypatch):
        monkeypatch.setattr('backend.sensors.manager.time.sleep',
                             lambda s: setattr(manager, '_running', False))
        manager.mtf01.read.return_value = DistanceReading(timestamp=0, valid=True, distance_m=1.0)
        manager.lidar.read.return_value = LidarScan(
            timestamp=0, valid=True,
            points=[LidarPoint(angle_deg=0, distance_m=3.0, quality=100)],
        )
        manager._running = True
        manager._loop()
        assert manager._latest_mtf01.valid is True
        assert manager._latest_lidar.valid is True
