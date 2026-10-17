"""Meteorological data retrieval and aeronautical aerodynamics module.

Fetches historical surface observations from Open-Meteo Historical Weather API
and computes aeronautical kinematics:
  - Headwind and Crosswind components along runway track
  - True Airspeed (TAS) vs Ground Speed (GS)
  - Pressure Altitude (PA) and Density Altitude (DA)
"""

import json
import logging
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Standard Atmosphere constants (ICAO Standard Atmosphere)
STANDARD_SEA_LEVEL_PRESSURE_HPA = 1013.25
STANDARD_SEA_LEVEL_TEMP_C = 15.0
TEMPERATURE_LAPSE_RATE_C_PER_M = 0.0065  # ~1.98 °C per 1,000 ft
METERS_TO_FEET = 3.28084
KMH_TO_MPS = 1.0 / 3.6
MPS_TO_KNOTS = 1.94384


@dataclass(frozen=True)
class WeatherObservation:
    """Historical surface weather observation for an airport location."""

    timestamp_utc: str
    latitude: float
    longitude: float
    temperature_c: float
    surface_pressure_hpa: float
    wind_speed_mps: float
    wind_direction_deg: float  # Direction FROM which wind blows (0 = North, 90 = East)
    wind_gusts_mps: float | None = None

    @property
    def wind_speed_kmh(self) -> float:
        """Wind speed in km/h."""
        return self.wind_speed_mps * 3.6

    @property
    def wind_speed_knots(self) -> float:
        """Wind speed in knots."""
        return self.wind_speed_mps * MPS_TO_KNOTS


@dataclass(frozen=True)
class AerodynamicResult:
    """Aeronautical aerodynamic and atmospheric density telemetry."""

    weather: WeatherObservation
    runway_heading_deg: float

    # Wind decomposition relative to aircraft ground track
    headwind_mps: float  # Positive = headwind, Negative = tailwind
    crosswind_mps: float  # Positive = from right, Negative = from left

    # Airspeeds
    ground_speed_mps: float
    true_airspeed_mps: float
    ground_speed_kmh: float
    true_airspeed_kmh: float
    ground_speed_knots: float
    true_airspeed_knots: float

    # Atmospheric density altitudes
    elevation_m: float
    pressure_altitude_m: float
    density_altitude_m: float
    density_altitude_ft: float
    density_delta_ft: float  # Difference between density altitude and field elevation

    # Runway wind alignment diagnostic
    is_favorable_headwind: bool


def calculate_wind_components(
    wind_speed_mps: float,
    wind_direction_deg: float,
    track_heading_deg: float,
) -> tuple[float, float]:
    """Decompose wind into headwind and crosswind components relative to track heading.

    Meteorological convention: wind direction is the angle FROM which wind blows.
    Aircraft heading: direction TOWARDS which the aircraft moves.

    Args:
        wind_speed_mps: Wind speed in meters per second.
        wind_direction_deg: Wind origin direction in degrees (0-360).
        track_heading_deg: Aircraft ground track / runway heading in degrees (0-360).

    Returns:
        Tuple of (headwind_mps, crosswind_mps).
        headwind_mps: >0 indicates headwind, <0 indicates tailwind.
        crosswind_mps: >0 indicates crosswind from right, <0 indicates from left.
    """
    # Angle between wind origin and aircraft track
    angle_rad = math.radians(wind_direction_deg - track_heading_deg)
    headwind = wind_speed_mps * math.cos(angle_rad)
    crosswind = wind_speed_mps * math.sin(angle_rad)
    return headwind, crosswind


def calculate_density_altitude(
    elevation_m: float,
    qnh_hpa: float,
    temperature_c: float,
) -> tuple[float, float]:
    """Calculate Pressure Altitude (PA) and Density Altitude (DA).

    Density altitude represents the altitude in the standard atmosphere at which
    the air density is equal to the actual air density observed. High density
    altitude degrades engine thrust and aerodynamic wing lift.

    Args:
        elevation_m: Airport elevation above mean sea level in meters.
        qnh_hpa: Surface barometric pressure in hPa.
        temperature_c: Ambient surface temperature in degrees Celsius.

    Returns:
        Tuple of (pressure_altitude_m, density_altitude_m).
    """
    # Pressure Altitude (m): elevation + barometric correction (~8.43 m/hPa)
    pa_m = elevation_m + (STANDARD_SEA_LEVEL_PRESSURE_HPA - qnh_hpa) * 8.43

    # Standard temperature at the pressure altitude
    t_std_c = STANDARD_SEA_LEVEL_TEMP_C - (pa_m * TEMPERATURE_LAPSE_RATE_C_PER_M)

    # Density Altitude (m): PA + ~36.6 m per degree Celsius above standard
    # (equivalent to ~120 ft / °C)
    temp_delta_c = temperature_c - t_std_c
    da_m = pa_m + (temp_delta_c * 36.6)

    return pa_m, da_m


def calculate_true_airspeed(
    ground_speed_mps: float,
    headwind_mps: float,
) -> float:
    """Calculate True Airspeed (TAS) from Ground Speed (GS) and headwind.

    In straight-line ground roll, drift angle is constrained by the runway, so:
        TAS = Ground Speed + Headwind

    Args:
        ground_speed_mps: Ground speed in m/s.
        headwind_mps: Headwind component in m/s (negative if tailwind).

    Returns:
        True Airspeed (TAS) in m/s.
    """
    return max(0.0, ground_speed_mps + headwind_mps)


def compute_aerodynamics(
    ground_speed_mps: float,
    heading_deg: float,
    weather: WeatherObservation,
    elevation_m: float = 42.0,  # Bilbao Airport (LEBB) elevation
) -> AerodynamicResult:
    """Compute complete aerodynamic telemetry fusing ground kinematics and surface weather.

    Args:
        ground_speed_mps: Aircraft ground speed in m/s from satellite tracking.
        heading_deg: Aircraft ground track / runway heading in degrees.
        weather: Weather observation for the airport.
        elevation_m: Airport field elevation above MSL in meters.

    Returns:
        AerodynamicResult object.
    """
    headwind_mps, crosswind_mps = calculate_wind_components(
        wind_speed_mps=weather.wind_speed_mps,
        wind_direction_deg=weather.wind_direction_deg,
        track_heading_deg=heading_deg,
    )

    tas_mps = calculate_true_airspeed(
        ground_speed_mps=ground_speed_mps,
        headwind_mps=headwind_mps,
    )

    pa_m, da_m = calculate_density_altitude(
        elevation_m=elevation_m,
        qnh_hpa=weather.surface_pressure_hpa,
        temperature_c=weather.temperature_c,
    )

    elevation_ft = elevation_m * METERS_TO_FEET
    da_ft = da_m * METERS_TO_FEET

    return AerodynamicResult(
        weather=weather,
        runway_heading_deg=heading_deg,
        headwind_mps=headwind_mps,
        crosswind_mps=crosswind_mps,
        ground_speed_mps=ground_speed_mps,
        true_airspeed_mps=tas_mps,
        ground_speed_kmh=ground_speed_mps * 3.6,
        true_airspeed_kmh=tas_mps * 3.6,
        ground_speed_knots=ground_speed_mps * MPS_TO_KNOTS,
        true_airspeed_knots=tas_mps * MPS_TO_KNOTS,
        elevation_m=elevation_m,
        pressure_altitude_m=pa_m,
        density_altitude_m=da_m,
        density_altitude_ft=da_ft,
        density_delta_ft=da_ft - elevation_ft,
        is_favorable_headwind=headwind_mps >= 0.0,
    )


def interpolate_weather_from_hourly(
    hourly: dict[str, list[Any]],
    date_str: str,
    datetime_str: str | None,
    hour_utc: int,
    latitude: float,
    longitude: float,
) -> WeatherObservation:
    """Extract and linearly interpolate surface weather telemetry from hourly series.

    Interpolates between adjacent hourly steps when a full ISO 8601 UTC datetime is provided.

    Args:
        hourly: Dictionary containing hourly series from Open-Meteo.
        date_str: Calendar date string (YYYY-MM-DD).
        datetime_str: Optional ISO 8601 UTC timestamp string (e.g. '2026-08-12T11:09:40Z').
        hour_utc: Integer hour (0-23) used if datetime_str is None or lacks sub-hour precision.
        latitude: Target latitude in degrees.
        longitude: Target longitude in degrees.

    Returns:
        WeatherObservation object representing surface conditions (10 m AGL).
    """
    target_h = max(0, min(23, hour_utc))
    frac = 0.0
    ts_str = f"{date_str}T{target_h:02d}:00:00Z"

    if datetime_str and "T" in datetime_str:
        try:
            # Parse time component: HH:MM:SS
            time_part = datetime_str.split("T")[1].rstrip("Z")
            parts = time_part.split(":")
            h_val = int(parts[0])
            m_val = int(parts[1]) if len(parts) > 1 else 0
            s_val = float(parts[2]) if len(parts) > 2 else 0.0

            target_h = max(0, min(23, h_val))
            frac = (m_val * 60.0 + s_val) / 3600.0
            ts_str = datetime_str
        except Exception:
            frac = 0.0

    times = hourly.get("time", [])
    h0 = target_h
    if times:
        prefix = f"{date_str}T{target_h:02d}:"
        found = False
        for i, t in enumerate(times):
            if t.startswith(prefix):
                h0 = i
                found = True
                break
        if not found:
            h0 = min(target_h, len(times) - 1)

    max_idx = len(hourly["temperature_2m"]) - 1
    h0 = max(0, min(max_idx, h0))
    h1 = min(max_idx, h0 + 1) if frac > 0.0 else h0
    f = frac if h1 > h0 else 0.0

    temp0 = float(hourly["temperature_2m"][h0])
    temp1 = float(hourly["temperature_2m"][h1])
    temp_c = (1.0 - f) * temp0 + f * temp1

    press0 = float(hourly["surface_pressure"][h0])
    press1 = float(hourly["surface_pressure"][h1])
    press_hpa = (1.0 - f) * press0 + f * press1

    wind0 = float(hourly["wind_speed_10m"][h0])
    wind1 = float(hourly["wind_speed_10m"][h1])
    wind_kmh = (1.0 - f) * wind0 + f * wind1

    dir0 = float(hourly["wind_direction_10m"][h0])
    dir1 = float(hourly["wind_direction_10m"][h1])
    # Angular interpolation using shortest circular distance
    dir_diff = ((dir1 - dir0 + 180.0) % 360.0) - 180.0
    wind_dir = ((dir0 + f * dir_diff) + 360.0) % 360.0

    gusts_mps = None
    if "wind_gusts_10m" in hourly and hourly["wind_gusts_10m"][h0] is not None:
        g0 = float(hourly["wind_gusts_10m"][h0])
        if h1 > h0 and hourly["wind_gusts_10m"][h1] is not None:
            g1 = float(hourly["wind_gusts_10m"][h1])
            gusts_mps = ((1.0 - f) * g0 + f * g1) * KMH_TO_MPS
        else:
            gusts_mps = g0 * KMH_TO_MPS

    return WeatherObservation(
        timestamp_utc=ts_str,
        latitude=latitude,
        longitude=longitude,
        temperature_c=temp_c,
        surface_pressure_hpa=press_hpa,
        wind_speed_mps=wind_kmh * KMH_TO_MPS,
        wind_direction_deg=wind_dir,
        wind_gusts_mps=gusts_mps,
    )


def fetch_historical_weather(
    latitude: float,
    longitude: float,
    date_str: str,
    hour_utc: int = 11,
    datetime_str: str | None = None,
    timeout_s: float = 10.0,
) -> WeatherObservation:
    """Fetch surface historical weather (10 m AGL) from Open-Meteo Historical Weather API.

    Open-Meteo Historical API is free, open, requires no API key, and provides
    ERA5-reanalysis calibrated observations for any global coordinate.
    When datetime_str is provided, values are linearly interpolated to the exact scene timestamp.

    Note:
        These parameters capture local ground-level atmospheric state (10 m AGL)
        and provide environmental context; they do not imply physical causality for
        aircraft speeds or flight dynamics.

    Args:
        latitude: Target latitude in WGS84.
        longitude: Target longitude in WGS84.
        date_str: Date string in YYYY-MM-DD format.
        hour_utc: Hour of day in UTC (0-23, default: 11 for Sentinel-2 overpass).
        datetime_str: Optional ISO 8601 UTC timestamp string for linear interpolation.
        timeout_s: Network timeout in seconds.

    Returns:
        WeatherObservation object.

    Raises:
        RuntimeError: If API request fails or returns invalid data.
    """
    params = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "start_date": date_str,
        "end_date": date_str,
        "hourly": (
            "temperature_2m,relative_humidity_2m,surface_pressure,"
            "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        ),
    }
    url = f"https://archive-api.open-meteo.com/v1/archive?{urllib.parse.urlencode(params)}"
    logger.info(
        "Fetching historical surface weather from Open-Meteo for %s (time: %s, hour: %02d UTC)",
        date_str,
        datetime_str or f"{hour_utc:02d}:00",
        hour_utc,
    )

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "s2motion/0.1.0 (Sentinel-2 Motion Tracking)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as err:
        raise RuntimeError(f"Failed to fetch weather from Open-Meteo ({url}): {err}") from err

    hourly = data.get("hourly", {})
    try:
        return interpolate_weather_from_hourly(
            hourly=hourly,
            date_str=date_str,
            datetime_str=datetime_str,
            hour_utc=hour_utc,
            latitude=latitude,
            longitude=longitude,
        )
    except (KeyError, IndexError, TypeError) as err:
        raise RuntimeError(f"Unexpected response format from Open-Meteo: {err}") from err
