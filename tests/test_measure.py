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
    # Heading 120 deg (aligned along runway 12):
    # dx_east = 10 * sin(120 deg), dy_north = 10 * cos(120 deg)
    # in raster: x = x0 + dx_east, y = y0 - dy_north
    h120_rad = math.radians(120.0)
    res_rwy12 = calculate_motion(
        red_centroid=(100.0, 100.0),
        blue_centroid=(100.0 + 10.0 * math.sin(h120_rad), 100.0 - 10.0 * math.cos(h120_rad)),
        runway_heading_deg=120.0,
    )
    assert abs(res_rwy12.heading_deg - 120.0) < 0.1
    assert res_rwy12.runway_diff_deg is not None
    assert abs(res_rwy12.runway_diff_deg - 0.0) < 0.1

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
    assert "Surface Weather Telemetry (Open-Meteo" in summary_text
    assert "Wind Components:" in summary_text
    assert "Density Altitude:" not in summary_text
    assert "TAS:" not in summary_text


def test_calculate_motion_with_runway_proximity() -> None:
    """Verify integration of RunwayProximityResult inside calculate_motion."""
    from s2motion.constants import (
        LEBB_RUNWAY_12_THR_WGS84,
        LEBB_RUNWAY_30_THR_WGS84,
    )
    from s2motion.geo import calculate_runway_proximity

    prox = calculate_runway_proximity(
        obj_lon=-2.936874,
        obj_lat=43.310770,
        thr12_latlon=LEBB_RUNWAY_12_THR_WGS84,
        thr30_latlon=LEBB_RUNWAY_30_THR_WGS84,
    )
    # Heading along runway axis ~116.7
    h_rad = math.radians(116.73)
    res = calculate_motion(
        red_centroid=(100.0, 100.0),
        blue_centroid=(100.0 + 10.0 * math.sin(h_rad), 100.0 - 10.0 * math.cos(h_rad)),
        runway_proximity=prox,
    )
    assert res.runway_proximity is not None
    assert abs(res.runway_diff_deg) < 0.1
    summary = res.summary()
    assert "Runway Position" in summary
    assert "APPROACH CORRIDOR" in summary


def test_calculate_motion_band_order_comparison() -> None:
    """Verify vector inversion, 180° heading shift, and green fraction under both band orders."""
    # Case 1 coordinates: Red=(66.0, 158.6), Blue=(73.3, 162.3), Green=(69.4, 160.3)
    r_pt = (66.0, 158.6)
    b_pt = (73.3, 162.3)
    g_pt = (69.4, 160.3)

    res_red = calculate_motion(
        red_centroid=r_pt,
        blue_centroid=b_pt,
        green_centroid=g_pt,
        band_order="red-first",
    )
    res_blue = calculate_motion(
        red_centroid=r_pt,
        blue_centroid=b_pt,
        green_centroid=g_pt,
        band_order="blue-first",
    )

    # 1. Magnitudes match exactly
    assert abs(res_red.distance_m - res_blue.distance_m) < 1e-4
    assert abs(res_red.speed_kmh - res_blue.speed_kmh) < 1e-4
    assert abs(res_red.collinearity_px - res_blue.collinearity_px) < 1e-4

    # 2. Heading is rotated by exactly 180°
    assert abs((res_red.heading_deg + 180.0) % 360.0 - res_blue.heading_deg) < 1e-4
    assert abs(res_red.heading_deg - 117.0) < 1.0
    assert abs(res_blue.heading_deg - 297.0) < 1.0

    # 3. Expected green fractions differ according to sensor layout
    assert abs(res_red.expected_green_fraction - (0.478 / 1.005)) < 1e-5
    assert abs(res_blue.expected_green_fraction - (0.527 / 1.005)) < 1e-5

    # 4. Summaries report appropriate directions
    assert "Direction:    Red -> Green -> Blue" in res_red.summary()
    assert "Direction:    Blue -> Green -> Red" in res_blue.summary()

    # 5. Invalid band order raises ValueError
    with pytest.raises(ValueError, match="Invalid band_order"):
        calculate_motion(red_centroid=r_pt, blue_centroid=b_pt, band_order="invalid")
