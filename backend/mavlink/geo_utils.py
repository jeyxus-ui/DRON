import math


def relative_to_gps(lat: float, lon: float, alt: float,
                    yaw_deg: float,
                    forward_m: float, right_m: float, up_m: float):
    """
    Convert body-frame relative offsets (forward, right, up) to
    absolute GPS coordinates using current position and heading.
    forward = direction drone is facing (nose)
    right   = direction to drone's right
    up      = altitude increase
    """
    yaw = math.radians(yaw_deg)
    dx = forward_m * math.cos(yaw) - right_m * math.sin(yaw)
    dy = forward_m * math.sin(yaw) + right_m * math.cos(yaw)

    lat_rad = math.radians(lat)
    new_lat = lat + (dx / 111320.0)
    new_lon = lon + (dy / (111320.0 * math.cos(lat_rad)))
    new_alt = alt + up_m

    return new_lat, new_lon, new_alt


def waypoints_relative_to_gps(current_lat: float, current_lon: float,
                               current_alt: float, yaw_deg: float,
                               rel_waypoints: list[dict]) -> list[dict]:
    """
    Convert a list of relative waypoints to absolute GPS waypoints.
    Each relative waypoint: {forward, right, up} or {x, y, z} (meters)
    Waypoints are cumulative from the current position.
    """
    abs_waypoints = []
    cum_forward = 0.0
    cum_right = 0.0
    cum_up = 0.0

    for wp in rel_waypoints:
        f = wp.get('forward') or wp.get('x', 0)
        r = wp.get('right') or wp.get('y', 0)
        u = wp.get('up') or wp.get('z', 0)

        cum_forward += f
        cum_right += r
        cum_up += u

        lat, lon, alt = relative_to_gps(
            current_lat, current_lon, current_alt,
            yaw_deg, cum_forward, cum_right, cum_up
        )
        abs_waypoints.append({'lat': lat, 'lon': lon, 'alt': alt})

    return abs_waypoints
