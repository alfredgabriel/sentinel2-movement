"""Tests for weather retrieval and aeronautical kinematics."""

import pytest

from s2motion.weather import (
    WeatherObservation,
    calculate_density_altitude,
    calculate_true_airspeed,
    calculate_wind_components,
    compute_aerodynamics,
    fetch_historical_weather,
)


def test_calculate_wind_components_cardinal() -> None:
    """Verify wind decomposition relative to track heading."""
    wind_spd = 10.0
    track = 120.0

    # 1. Pure headwind (wind from 120 deg directly into track 120 deg)
    hw, xw = calculate_wind_components(wind_spd, wind_direction_deg=120.0, track_heading_deg=track)
    assert abs(hw - 10.0) < 1e-4
    assert abs(xw - 0.0) < 1e-4

    # 2. Pure tailwind (wind from 300 deg from behind)
    hw_tail, xw_tail = calculate_wind_components(
        wind_spd, wind_direction_deg=300.0, track_heading_deg=track
    )
    assert abs(hw_tail - (-10.0)) < 1e-4
    assert abs(xw_tail - 0.0) < 1e-4

    # 3. Pure crosswind from right (wind from 210 deg: 120 + 90)
    hw_r, xw_r = calculate_wind_components(
        wind_spd, wind_direction_deg=210.0, track_heading_deg=track
    )
    assert abs(hw_r - 0.0) < 1e-4
    assert abs(xw_r - 10.0) < 1e-4

    # 4. Pure crosswind from left (wind from 030 deg: 120 - 90)
    hw_l, xw_l = calculate_wind_components(
        wind_spd, wind_direction_deg=30.0, track_heading_deg=track
    )
    assert abs(hw_l - 0.0) < 1e-4
    assert abs(xw_l - (-10.0)) < 1e-4


def test_calculate_density_altitude_standard_day() -> None:
    """Verify density altitude on a standard ICAO sea level atmosphere."""
    # Sea level, 15 °C, 1013.25 hPa -> PA = 0, DA = 0
    pa, da = calculate_density_altitude(elevation_m=0.0, qnh_hpa=1013.25, temperature_c=15.0)
    assert abs(pa) < 1e-2
    assert abs(da) < 1e-2


def test_calculate_density_altitude_hot_summer_day() -> None:
    """Verify density altitude increases significantly on a hot day (Loiu 28.7 °C)."""
    # Bilbao Airport elevation: 42 m
    pa, da = calculate_density_altitude(elevation_m=42.0, qnh_hpa=1014.3, temperature_c=28.7)
    # Pressure altitude slightly below elevation due to high pressure (1014.3 > 1013.25)
    assert pa < 42.0
    # Density altitude should be much higher due to 28.7 °C (well over 500 m / 1,600 ft)
    assert da > 500.0
    assert (da - pa) > 450.0


def test_calculate_true_airspeed() -> None:
    """Verify True Airspeed calculation from Ground Speed and headwind component."""
    # Headwind increases airspeed required relative to ground: TAS = GS + HW
    tas_head = calculate_true_airspeed(ground_speed_mps=80.0, headwind_mps=10.0)
    assert abs(tas_head - 90.0) < 1e-4

    # Tailwind decreases airspeed relative to ground: TAS = GS + (-5) = 75
    tas_tail = calculate_true_airspeed(ground_speed_mps=80.0, headwind_mps=-5.0)
    assert abs(tas_tail - 75.0) < 1e-4


def test_compute_aerodynamics_end_to_end() -> None:
    """Verify full aerodynamic telemetry object assembly."""
    obs = WeatherObservation(
        timestamp_utc="2026-08-12T11:00:00Z",
        latitude=43.30,
        longitude=-2.91,
        temperature_c=28.7,
        surface_pressure_hpa=1014.3,
        wind_speed_mps=2.83,  # ~10.2 km/h
        wind_direction_deg=14.0,  # From NNE
    )

    aero = compute_aerodynamics(
        ground_speed_mps=82.0,  # ~295 km/h
        heading_deg=117.4,  # Runway 12 takeoff
        weather=obs,
        elevation_m=42.0,
    )

    assert aero.ground_speed_kmh == pytest.approx(295.2, rel=1e-2)
    # Headwind is slight negative (tailwind from behind-left)
    assert aero.headwind_mps < 0.0
    assert not aero.is_favorable_headwind
    # Density altitude in feet is > 1500 ft above field
    assert aero.density_altitude_ft > 1500.0
    assert aero.density_delta_ft > 1300.0


@pytest.mark.network
def test_fetch_historical_weather_live() -> None:
    """Verify live query to Open-Meteo Historical Weather API."""
    obs = fetch_historical_weather(
        latitude=43.30,
        longitude=-2.91,
        date_str="2026-08-12",
        hour_utc=11,
    )
    assert obs.timestamp_utc == "2026-08-12T11:00:00Z"
    assert 15.0 < obs.temperature_c < 45.0
    assert 950.0 < obs.surface_pressure_hpa < 1050.0
    assert 0.0 <= obs.wind_speed_mps < 50.0
    assert 0.0 <= obs.wind_direction_deg <= 360.0
