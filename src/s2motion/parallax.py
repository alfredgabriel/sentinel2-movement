"""Stereoscopic parallax correction module for elevated moving airborne targets.

In Sentinel-2 pushbroom observations, an elevated object at altitude h is viewed
from different line-of-sight angles across spectral bands. This module derives
the satellite ground track velocity from orbital mechanics, computes the parallax
vector along the satellite ground track, and resolves the true horizontal ground
velocity from apparent inter-band displacements.

References:
    - Krauß, T. (2021). "EXTRACTION OF CLOUD HEIGHTS FROM SENTINEL-2 MULTISPECTRAL IMAGES",
      ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences,
      Vol. V-1-2021, pp. 17-23. DOI: 10.5194/isprs-annals-V-1-2021-17-2021
    - Heiselberg, H. (2019). "Aircraft and Ship Velocity Determination in Sentinel-2
      Multispectral Images", Sensors, 19(13), 2873. DOI: 10.3390/s19132873
    - Heiselberg, H. (2021). "Aircraft Detection above Clouds by Sentinel-2 MSI Parallax",
      Remote Sensing, 13(12), 2327. DOI: 10.3390/rs13122327
    - Binet, R., Bergsma, E., & Poulain, V. (2022). "ACCURATE SENTINEL-2 INTER-BAND TIME DELAYS",
      ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences,
      Vol. V-1-2022, pp. 57-66. DOI: 10.5194/isprs-annals-V-1-2022-57-2022
"""

import math
from dataclasses import dataclass
from typing import Final

from s2motion.constants import (
    DELTA_T_RED_BLUE_S,
    EARTH_GM,
    EARTH_MEAN_RADIUS_M,
    EARTH_ROTATION_RATE_RAD_S,
    SENTINEL2_INCLINATION_DEG,
    SENTINEL2_MEAN_ALTITUDE_M,
    SENTINEL2_SEMI_MAJOR_AXIS_M,
)

# Conversion factors
MPS_TO_KMH: Final[float] = 3.6


@dataclass(frozen=True)
class SatelliteGroundTrack:
    """Satellite velocity parameters derived from orbital mechanics."""

    latitude_deg: float
    orbital_speed_mps: float  # In-plane inertial speed: sqrt(mu / a) (~7463 m/s)
    subsatellite_speed_mps: float  # Inertial ground-projected speed: v_orb * (R_E / a) (~6643 m/s)
    ground_track_speed_mps: float  # Ground track speed relative to rotating Earth (~6721 m/s)
    ground_track_heading_deg: float  # Track heading clockwise from North (~194.7 deg at lat 43.3)
    earth_rotation_speed_mps: float  # Linear surface speed of Earth at latitude (~338 m/s)
    v_north_mps: float  # Northward velocity component of ground track
    v_east_mps: float  # Eastward velocity component of ground track


def calculate_satellite_ground_track(
    latitude_deg: float = 43.3,
    semi_major_axis_m: float = SENTINEL2_SEMI_MAJOR_AXIS_M,
    inclination_deg: float = SENTINEL2_INCLINATION_DEG,
    earth_gm: float = EARTH_GM,
    earth_rotation_rad_s: float = EARTH_ROTATION_RATE_RAD_S,
    earth_radius_m: float = EARTH_MEAN_RADIUS_M,
) -> SatelliteGroundTrack:
    """Derive satellite ground track velocity and heading from orbital mechanics.

    Accounts for satellite orbital motion and the eastward rotational velocity of
    the Earth's surface at the specified latitude.

    For descending orbit passes (sun-synchronous descending node in morning):
        - Inertial orbital velocity: v_orb = sqrt(mu / a) ~= 7463 m/s.
        - Subsatellite inertial velocity: v_sub = v_orb * (R_E / a) ~= 6643 m/s.
        - Descending ground track azimuth chi relative to true North:
          cos(i) = cos(lat) * sin(chi)
          sin(chi) = cos(i) / cos(lat)
          chi = pi - arcsin(sin(chi)) ~= 191.9 deg (towards South-Southwest).
        - Ground track velocity relative to rotating Earth surface:
          v_N_track = v_sub * cos(chi)
          v_E_track = v_sub * sin(chi) - omega_E * R_E * cos(lat)
          v_track = sqrt(v_N_track^2 + v_E_track^2) ~= 6721 m/s (heading ~= 194.7 deg).

    Args:
        latitude_deg: Geodetic latitude of target scene in degrees (default: 43.3 for Bilbao).
        semi_major_axis_m: Orbit semi-major axis in meters (default: 7157000.0 m).
        inclination_deg: Orbit inclination in degrees (default: 98.62 deg).
        earth_gm: Earth gravitational parameter in m^3/s^2 (default: 3.986004418e14).
        earth_rotation_rad_s: Earth angular velocity in rad/s (default: 7.292115e-5).
        earth_radius_m: Earth mean radius in meters (default: 6371000.0 m).

    Returns:
        SatelliteGroundTrack dataclass with complete kinematic breakdown.
    """
    v_orb = math.sqrt(earth_gm / semi_major_axis_m)
    v_sub = v_orb * (earth_radius_m / semi_major_axis_m)

    phi = math.radians(latitude_deg)
    inc = math.radians(inclination_deg)

    # Descending track angle chi relative to North
    cos_phi = max(1e-6, math.cos(phi))
    sin_chi = math.cos(inc) / cos_phi
    sin_chi = max(-1.0, min(1.0, sin_chi))
    # In descending pass, azimuth is in the third quadrant (between 180° and 270°)
    chi_rad = math.pi - math.asin(sin_chi)

    v_n_inertial = v_sub * math.cos(chi_rad)
    v_e_inertial = v_sub * math.sin(chi_rad)

    # Earth eastward surface velocity at this latitude
    v_e_rot = earth_rotation_rad_s * earth_radius_m * cos_phi

    v_n_track = v_n_inertial
    v_e_track = v_e_inertial - v_e_rot

    v_track = math.hypot(v_n_track, v_e_track)
    track_heading = (math.degrees(math.atan2(v_e_track, v_n_track)) + 360.0) % 360.0

    return SatelliteGroundTrack(
        latitude_deg=latitude_deg,
        orbital_speed_mps=v_orb,
        subsatellite_speed_mps=v_sub,
        ground_track_speed_mps=v_track,
        ground_track_heading_deg=track_heading,
        earth_rotation_speed_mps=v_e_rot,
        v_north_mps=v_n_track,
        v_east_mps=v_e_track,
    )


@dataclass(frozen=True)
class ParallaxCorrectionResult:
    """Kinematics result with stereoscopic parallax correction."""

    altitude_m: float
    altitude_min_m: float | None
    altitude_max_m: float | None
    satellite_altitude_m: float
    satellite_track_speed_mps: float
    satellite_track_heading_deg: float
    apparent_speed_mps: float
    apparent_speed_kmh: float
    apparent_heading_deg: float
    corrected_speed_mps: float
    corrected_speed_kmh: float
    corrected_speed_min_kmh: float | None
    corrected_speed_max_kmh: float | None
    corrected_heading_deg: float
    parallax_speed_mps: float
    parallax_speed_kmh: float
    parallax_displacement_m: float
    delta_speed_kmh: float  # corrected_speed_kmh - apparent_speed_kmh
    band_order: str
    is_user_parameter: bool = True

    def summary(self) -> str:
        """Format human-readable parallax correction summary."""
        range_str = (
            f" (range: {self.altitude_min_m:.0f} - {self.altitude_max_m:.0f} m)"
            if self.altitude_min_m is not None and self.altitude_max_m is not None
            else ""
        )
        speed_range_str = (
            f" (range: {self.corrected_speed_min_kmh:.0f} - {self.corrected_speed_max_kmh:.0f} km/h)"
            if self.corrected_speed_min_kmh is not None and self.corrected_speed_max_kmh is not None
            else ""
        )
        sign_str = f"{self.delta_speed_kmh:+.0f} km/h vs apparent"
        return (
            f"Stereoscopic Parallax Correction (Satellite Track: {self.satellite_track_speed_mps:.0f} m/s, heading: {self.satellite_track_heading_deg:.1f}°):\n"
            f"  - Target Altitude:          {self.altitude_m:.0f} m{range_str}\n"
            f"  - Disclaimer:               Flight altitude is a user-specified parameter, not an independently measured observable.\n"
            f"  - Parallax Shift:           {self.parallax_displacement_m:.1f} m along satellite track ({self.parallax_speed_kmh:.0f} km/h apparent contribution)\n"
            f"  - Apparent Velocity:        {self.apparent_speed_kmh:.0f} km/h [{self.apparent_speed_mps:.1f} m/s] | Heading: {self.apparent_heading_deg:.1f}°\n"
            f"  - Parallax-Corrected Vel:   {self.corrected_speed_kmh:.0f} km/h [{self.corrected_speed_mps:.1f} m/s]{speed_range_str} | Heading: {self.corrected_heading_deg:.1f}° [{sign_str}]"
        )


def correct_parallax(
    apparent_speed_mps: float,
    apparent_heading_deg: float,
    altitude_m: float,
    altitude_min_m: float | None = None,
    altitude_max_m: float | None = None,
    latitude_deg: float = 43.3,
    band_order: str = "red-first",
    delta_t_s: float = DELTA_T_RED_BLUE_S,
    satellite_altitude_m: float = SENTINEL2_MEAN_ALTITUDE_M,
) -> ParallaxCorrectionResult:
    """Correct apparent velocity for stereoscopic parallax induced by target flight altitude.

    Geometric Derivation:
        In a pushbroom sensor, each spectral band looks at a distinct along-track angle theta_b.
        An elevated object at altitude h is projected onto the cartographic ground plane
        forward by h * tan(theta_b) relative to its true nadir ground position.

        Between the initial band and the trailing band separated by temporal delay delta_t:
            tan(theta_leading) - tan(theta_trailing) = (v_track * delta_t) / H
        The first band images the elevated target further forward along the satellite track than
        the last band by:
            delta_r_parallax = (h / H) * v_track * delta_t (directed along track).

        The complete geometric pushbroom model projects rays from satellite altitude H through target
        altitude h to the ground ellipsoid:
            v_apparent = (H / (H - h)) * v_true - (h / (H - h)) * v_track
        Multiplying by (1 - h / H):
            v_true = (1 - h / H) * v_apparent + (h / H) * v_track

        This complete form reduces the apparent velocity term by (h / H) * v_apparent (~15 km/h at 10.5 km)
        compared to the simplified linear approximation v_apparent + (h / H) * v_track.

    Args:
        apparent_speed_mps: Measured uncorrected ground speed in m/s.
        apparent_heading_deg: Measured uncorrected heading in degrees clockwise from North.
        altitude_m: Assumed flight altitude in meters above terrain/ellipsoid.
        altitude_min_m: Optional lower bound of altitude interval in meters.
        altitude_max_m: Optional upper bound of altitude interval in meters.
        latitude_deg: Scene latitude for satellite ground track derivation (default: 43.3).
        band_order: Acquisition sequence, either 'red-first' or 'blue-first'.
        delta_t_s: Elapsed time between initial and final bands in seconds (default: 1.005 s).
        satellite_altitude_m: Orbital height above ground in meters (default: 786000.0 m).

    Returns:
        ParallaxCorrectionResult containing apparent, parallax, and corrected vectors.

    Raises:
        ValueError: If altitude_m < 0, or if altitude_min_m > altitude_max_m.
    """
    if band_order not in ("red-first", "blue-first"):
        raise ValueError(
            f"Invalid band_order: '{band_order}'. Must be 'red-first' or 'blue-first'."
        )
    if altitude_m < 0:
        raise ValueError(f"Altitude cannot be negative (got {altitude_m} m)")
    if altitude_min_m is not None and altitude_max_m is not None:
        if altitude_min_m > altitude_max_m:
            raise ValueError(
                f"altitude_min_m ({altitude_min_m}) cannot exceed altitude_max_m ({altitude_max_m})"
            )

    track = calculate_satellite_ground_track(latitude_deg=latitude_deg)

    # Decompose apparent velocity into North and East components
    app_head_rad = math.radians(apparent_heading_deg)
    v_app_n = apparent_speed_mps * math.cos(app_head_rad)
    v_app_e = apparent_speed_mps * math.sin(app_head_rad)

    def _solve_for_h(h_val: float) -> tuple[float, float, float]:
        scale = h_val / satellite_altitude_m
        # Complete pushbroom model: v_true = (1 - h/H) * v_apparent + (h/H) * v_track
        # Accounts for finite target altitude (reduces apparent speed by ~15 km/h at 10.5 km cruise vs linear form)
        v_n = (1.0 - scale) * v_app_n + scale * track.v_north_mps
        v_e = (1.0 - scale) * v_app_e + scale * track.v_east_mps
        v_mag = math.hypot(v_n, v_e)
        heading = (math.degrees(math.atan2(v_e, v_n)) + 360.0) % 360.0
        return v_mag, heading, scale * track.ground_track_speed_mps

    v_corr_mps, corr_heading_deg, v_par_mps = _solve_for_h(altitude_m)
    v_corr_kmh = v_corr_mps * MPS_TO_KMH
    v_app_kmh = apparent_speed_mps * MPS_TO_KMH

    v_corr_min_kmh = None
    v_corr_max_kmh = None
    if altitude_min_m is not None and altitude_max_m is not None:
        v_min_mps, _, _ = _solve_for_h(altitude_min_m)
        v_max_mps, _, _ = _solve_for_h(altitude_max_m)
        # Note: speed can be monotonically decreasing or increasing with altitude depending on geometry
        v_corr_min_kmh = min(v_min_mps, v_max_mps) * MPS_TO_KMH
        v_corr_max_kmh = max(v_min_mps, v_max_mps) * MPS_TO_KMH

    parallax_disp_m = (altitude_m / satellite_altitude_m) * track.ground_track_speed_mps * delta_t_s

    return ParallaxCorrectionResult(
        altitude_m=altitude_m,
        altitude_min_m=altitude_min_m,
        altitude_max_m=altitude_max_m,
        satellite_altitude_m=satellite_altitude_m,
        satellite_track_speed_mps=track.ground_track_speed_mps,
        satellite_track_heading_deg=track.ground_track_heading_deg,
        apparent_speed_mps=apparent_speed_mps,
        apparent_speed_kmh=v_app_kmh,
        apparent_heading_deg=apparent_heading_deg,
        corrected_speed_mps=v_corr_mps,
        corrected_speed_kmh=v_corr_kmh,
        corrected_speed_min_kmh=v_corr_min_kmh,
        corrected_speed_max_kmh=v_corr_max_kmh,
        corrected_heading_deg=corr_heading_deg,
        parallax_speed_mps=v_par_mps,
        parallax_speed_kmh=v_par_mps * MPS_TO_KMH,
        parallax_displacement_m=parallax_disp_m,
        delta_speed_kmh=v_corr_kmh - v_app_kmh,
        band_order=band_order,
        is_user_parameter=True,
    )
