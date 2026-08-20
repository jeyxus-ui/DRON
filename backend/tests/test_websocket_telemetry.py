"""Tests para get_telemetry_data (fix indentación / camino feliz)."""
import asyncio
from unittest.mock import MagicMock, patch


def test_get_telemetry_data_happy_path_returns_dict():
    """Sin excepción previa, debe retornar dict con claves de telemetría real."""
    from backend.api.websocket import get_telemetry_data

    telemetry = MagicMock()
    telemetry.get_attitude.return_value = {"roll": 1.0, "pitch": 2.0, "yaw": 3.0}
    telemetry.get_gps.return_value = {
        "alt": 10.5, "lat": 4.6, "lon": -74.0, "satellites": 8, "hdop": 1.2,
    }
    telemetry.get_battery.return_value = {
        "voltage": 41.16, "current": 1.5, "remaining": 95,
    }
    telemetry.get_velocity.return_value = {
        "ground_speed": 0.5, "vertical_speed": 0.0,
    }

    mav = MagicMock()
    mav.telemetry = telemetry
    mav.is_armed.return_value = False
    mav.get_mode.return_value = "STABILIZE"

    with patch("backend.api.websocket._get_sensor_data", return_value={}):
        result = asyncio.run(get_telemetry_data(mav))

    assert isinstance(result, dict)
    assert "error" not in result
    assert result["armed"] is False
    assert result["mode"] == "STABILIZE"
    assert result["battery_voltage"] == 41.16
    assert result["satellites"] == 8
    assert result["altitude"] == 10.5


def test_get_telemetry_data_sim_fallback():
    """Si no hay objeto telemetry pero sí get_telemetry(), usa simulador."""
    from backend.api.websocket import get_telemetry_data

    mav = MagicMock(spec=["is_armed", "get_mode", "get_telemetry", "telemetry"])
    mav.telemetry = None
    mav.is_armed.return_value = True
    mav.get_mode.return_value = "GUIDED"
    mav.get_telemetry.return_value = {
        "altitude": 5.0,
        "gps": {"lat": 1.0, "lon": 2.0, "satellites": 0, "hdop": 99.99},
        "attitude": {"roll": 0, "pitch": 0, "yaw": 0},
        "battery": {"voltage": 12.0, "current": 0, "remaining": 50},
        "speed": 0,
        "climb_rate": 0,
    }

    with patch("backend.api.websocket._get_sensor_data", return_value={}):
        result = asyncio.run(get_telemetry_data(mav))

    assert isinstance(result, dict)
    assert result["armed"] is True
    assert result["mode"] == "GUIDED"
    assert result["battery_voltage"] == 12.0
    assert result["altitude"] == 5.0
