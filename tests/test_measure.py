"""Unit tests for kinematics, heading, velocity, and uncertainty propagation."""

import math

import pytest

from s2motion.constants import EXPECTED_GREEN_RELATIVE_FRACTION
from s2motion.measure import calculate_motion


def test_calculate_motion_cardinal_headings() -> None:
    """Verify heading calculations for all 4 cardinal directions (Red -> Blue)."""
    # North: y decreases in raster coords (upward)
    res_north = calculate_motion(red_centroid=(100.0, 100.0), blue_centroid=(100.0, 90.0))
    assert abs(res_north.heading_deg - 0.0) < 1e-4

    # East: x increases in raster coords (rightward)
    res_east = calculate_motion(red_centroid=(100.0, 100.0), blue_centroid=(110.0, 100.0))
    assert abs(res_east.heading_deg - 90.0) < 1e-4

    # South: y increases in raster coords (downward)
    res_south = calculate_motion(red_centroid=(100.0, 100.0), blue_centroid=(100.0, 110.0))
    assert abs(res_south.heading_deg - 180.0) < 1e-4

    # West: x decreases in raster coords (leftward)
    res_west = calculate_motion(red_centroid=(100.0, 100.0), blue_centroid=(90.0, 100.0))
    assert abs(res_west.heading_deg - 270.0) < 1e-4


def test_calculate_motion_speed_and_uncertainty_bounds() -> None:
    """Verify nominal velocity and uncertainty interval."""
    # 8 pixels displacement at 10 m/px = 80 m
    # nominal delta t = 1.005 s -> speed = 80 / 1.005 ~= 79.6 m/s ~= 286.56 km/h
    res = calculate_motion(
        red_centroid=(50.0, 50.0),
        blue_centroid=(58.0, 50.0),
        pixel_size_m=10.0,
        delta_t_s=1.005,
    )
    assert abs(res.distance_m - 80.0) < 1e-4
    assert abs(res.speed_kmh - (80.0 / 1.005 * 3.6)) < 1e-2

    # Verify bounds: min < nominal < max
    assert res.speed_kmh_min < res.speed_kmh < res.speed_kmh_max
    assert res.distance_min_m < res.distance_m < res.distance_max_m
    assert res.delta_t_min_s < res.delta_t_s < res.delta_t_max_s


def test_collinearity_and_green_relative_position() -> None:
    """Verify collinearity offset and green temporal fraction on ideal trajectory (Red -> Green -> Blue)."""
    red = (10.0, 20.0)
    blue = (110.0, 20.0)
    # Total vector = (100.0, 0.0). Expected fraction = ~0.47562
    ideal_gx = 10.0 + 100.0 * EXPECTED_GREEN_RELATIVE_FRACTION
    ideal_gy = 20.0
    green = (ideal_gx, ideal_gy)

    res = calculate_motion(red_centroid=red, blue_centroid=blue, green_centroid=green)
    assert abs(res.collinearity_px) < 1e-6
    assert abs(res.green_relative_fraction - EXPECTED_GREEN_RELATIVE_FRACTION) < 1e-6
    assert res.fraction_deviation < 1e-6


def test_runway_alignment() -> None:
    """Verify bidirectional runway axis differences."""
    # Runway 12/30 (axis 120 deg)
    # Heading 120 deg (takeoff along runway 12):
    # dx_east = 10 * sin(120 deg), dy_north = 10 * cos(120 deg)
    # in raster: x = x0 + dx_east, y = y0 - dy_north
    h120_rad = math.radians(120.0)
    res_takeoff12 = calculate_motion(
        red_centroid=(100.0, 100.0),
        blue_centroid=(100.0 + 10.0 * math.sin(h120_rad), 100.0 - 10.0 * math.cos(h120_rad)),
        runway_heading_deg=120.0,
    )
    assert abs(res_takeoff12.heading_deg - 120.0) < 0.1
    assert res_takeoff12.runway_diff_deg is not None
    assert abs(res_takeoff12.runway_diff_deg - 0.0) < 0.1

    # Heading 125 deg -> diff with runway axis (120 deg) should be 5 deg
    h125_rad = math.radians(125.0)
    res_125deg = calculate_motion(
        red_centroid=(100.0, 100.0),
        blue_centroid=(100.0 + 10.0 * math.sin(h125_rad), 100.0 - 10.0 * math.cos(h125_rad)),
        runway_heading_deg=120.0,
    )
    assert abs(res_125deg.heading_deg - 125.0) < 0.1
    assert res_125deg.runway_diff_deg is not None
    assert abs(res_125deg.runway_diff_deg - 5.0) < 0.1


def test_zero_displacement_raises() -> None:
    """Verify error on identical coordinates."""
    with pytest.raises(ValueError, match="Centroid displacement is zero"):
        calculate_motion(red_centroid=(10.0, 10.0), blue_centroid=(10.0, 10.0))


def test_calculate_motion_with_aerodynamics() -> None:
    """Verify aero object passing and summary telemetry formatting."""
    from s2motion.weather import WeatherObservation, compute_aerodynamics

    obs = WeatherObservation(
        timestamp_utc="2026-08-12T11:00",
        latitude=43.301,
        longitude=-2.911,
        temperature_c=28.7,
        surface_pressure_hpa=1014.3,
        wind_speed_mps=10.2 / 3.6,
        wind_direction_deg=14.0,
    )
    aero = compute_aerodynamics(
        ground_speed_mps=290.0 / 3.6,
        heading_deg=117.4,
        weather=obs,
        elevation_m=42.0,
    )
    res = calculate_motion(
        red_centroid=(100.0, 100.0),
        blue_centroid=(107.2, 103.7),
        runway_heading_deg=120.0,
        aero=aero,
    )

    assert res.aero is not None
    assert abs(res.aero.weather.temperature_c - 28.7) < 1e-4
    assert res.aero.density_altitude_ft > 1000.0

    summary_text = res.summary()
    assert "Aeronautical & Weather Telemetry (Open-Meteo):" in summary_text
    assert "Density Altitude:" in summary_text
    assert "TAS:" in summary_text
    assert "Wind Components:" in summary_text
