"""Tests unitarios para backend/mavlink/geo_utils.py — conversión metros→GPS."""
import pytest

from backend.mavlink.geo_utils import relative_to_gps, waypoints_relative_to_gps

METERS_PER_DEG = 111320.0


class TestRelativeToGps:

    def test_zero_offset_returns_same_position(self):
        lat, lon, alt = relative_to_gps(10.0, 20.0, 5.0, 0.0, 0.0, 0.0, 0.0)
        assert lat == pytest.approx(10.0)
        assert lon == pytest.approx(20.0)
        assert alt == pytest.approx(5.0)

    def test_up_adds_directly_to_altitude(self):
        _, _, alt = relative_to_gps(0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 7.5)
        assert alt == pytest.approx(17.5)

    def test_up_negative_subtracts_from_altitude(self):
        _, _, alt = relative_to_gps(0.0, 0.0, 10.0, 0.0, 0.0, 0.0, -4.0)
        assert alt == pytest.approx(6.0)

    def test_yaw_zero_forward_moves_longitude(self):
        lat, lon, _ = relative_to_gps(0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0)
        assert lat == pytest.approx(0.0, abs=1e-9)
        assert lon == pytest.approx(100.0 / METERS_PER_DEG)

    def test_yaw_zero_right_moves_latitude(self):
        lat, lon, _ = relative_to_gps(0.0, 0.0, 0.0, 0.0, 0.0, 50.0, 0.0)
        assert lat == pytest.approx(50.0 / METERS_PER_DEG)
        assert lon == pytest.approx(0.0, abs=1e-9)

    def test_yaw_90_forward_moves_latitude(self):
        lat, lon, _ = relative_to_gps(0.0, 0.0, 0.0, 90.0, 100.0, 0.0, 0.0)
        assert lat == pytest.approx(100.0 / METERS_PER_DEG, rel=1e-6)
        assert lon == pytest.approx(0.0, abs=1e-6)

    def test_yaw_180_forward_moves_longitude_negative(self):
        lat, lon, _ = relative_to_gps(0.0, 0.0, 0.0, 180.0, 100.0, 0.0, 0.0)
        assert lon == pytest.approx(-100.0 / METERS_PER_DEG, rel=1e-6)
        assert lat == pytest.approx(0.0, abs=1e-6)

    def test_negative_forward_moves_opposite_direction(self):
        _, lon_pos, _ = relative_to_gps(0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0)
        _, lon_neg, _ = relative_to_gps(0.0, 0.0, 0.0, 0.0, -100.0, 0.0, 0.0)
        assert lon_neg == pytest.approx(-lon_pos)

    def test_longitude_delta_grows_with_latitude(self):
        """Mismo desplazamiento en metros produce mayor delta de longitud
        en grados a mayor latitud (el denominador 111320*cos(lat) se achica)."""
        _, lon_at_equator, _ = relative_to_gps(0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0)
        _, lon_at_60, _ = relative_to_gps(60.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0)
        assert abs(lon_at_60) > abs(lon_at_equator)

    def test_returns_plain_floats(self):
        result = relative_to_gps(1.0, 2.0, 3.0, 45.0, 10.0, 5.0, 1.0)
        assert len(result) == 3
        assert all(isinstance(v, float) for v in result)


class TestWaypointsRelativeToGps:

    def test_empty_list_returns_empty(self):
        assert waypoints_relative_to_gps(0.0, 0.0, 0.0, 0.0, []) == []

    def test_single_waypoint_matches_relative_to_gps(self):
        result = waypoints_relative_to_gps(
            1.0, 2.0, 3.0, 0.0, [{'forward': 10, 'right': 5, 'up': 2}]
        )
        expected_lat, expected_lon, expected_alt = relative_to_gps(1.0, 2.0, 3.0, 0.0, 10, 5, 2)
        assert result == [{
            'lat': pytest.approx(expected_lat),
            'lon': pytest.approx(expected_lon),
            'alt': pytest.approx(expected_alt),
        }]

    def test_waypoints_are_cumulative(self):
        result = waypoints_relative_to_gps(0.0, 0.0, 0.0, 0.0, [
            {'forward': 10, 'right': 0, 'up': 0},
            {'forward': 10, 'right': 0, 'up': 0},
        ])
        # El segundo waypoint acumula forward=20 (10+10), no 10 de nuevo.
        assert result[1]['lon'] == pytest.approx(2 * result[0]['lon'])
        assert result[1]['lon'] == pytest.approx(20.0 / METERS_PER_DEG)

    def test_supports_xyz_key_aliases(self):
        result_xyz = waypoints_relative_to_gps(0.0, 0.0, 0.0, 0.0, [{'x': 10, 'y': 5, 'z': 2}])
        result_fru = waypoints_relative_to_gps(0.0, 0.0, 0.0, 0.0, [{'forward': 10, 'right': 5, 'up': 2}])
        assert result_xyz == result_fru

    def test_missing_keys_default_to_zero(self):
        result = waypoints_relative_to_gps(5.0, 6.0, 7.0, 0.0, [{}])
        assert result == [{
            'lat': pytest.approx(5.0),
            'lon': pytest.approx(6.0),
            'alt': pytest.approx(7.0),
        }]

    def test_multiple_waypoints_returns_one_entry_each(self):
        result = waypoints_relative_to_gps(0.0, 0.0, 0.0, 0.0, [
            {'forward': 1}, {'forward': 2}, {'forward': 3},
        ])
        assert len(result) == 3
        for wp in result:
            assert set(wp.keys()) == {'lat', 'lon', 'alt'}
