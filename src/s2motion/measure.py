"""Measurement module for kinematics, coherence tests, and uncertainty propagation.

Sentinel-2 captures spectral bands with slight sub-second time delays.
By tracking the subpixel displacement of an object from Band 2 (Blue, acquired at t=0 s)
to Band 4 (Red, acquired at t=1.005 s), this module computes:
  - Vector displacement and distance in meters
  - Heading in degrees (0 = North, clockwise)
  - Speed in m/s and km/h with explicit uncertainty bounds
  - Collinearity and temporal sequence consistency checks
"""

import math
from dataclasses import dataclass

from s2motion.constants import (
    CENTROID_UNCERTAINTY_PX,
    DEFAULT_PIXEL_SIZE_M,
    DELTA_T_BLUE_RED_S,
    DELTA_T_RELATIVE_UNCERTAINTY,
    EXPECTED_GREEN_RELATIVE_FRACTION,
)


@dataclass(frozen=True)
class MeasurementResult:
    """Rigorous kinematics and coherence result with propagated uncertainties."""

    # Displacements
    dx_px: float  # Displacement along X (East-West), pixels: x_red - x_blue
    dy_px: float  # Displacement along Y (North-South in raster coords): y_red - y_blue
    distance_px: float
    distance_m: float
    distance_min_m: float
    distance_max_m: float
    distance_std_m: float

    # Timing
    delta_t_s: float
    delta_t_min_s: float
    delta_t_max_s: float

    # Velocities
    speed_mps: float
    speed_mps_min: float
    speed_mps_max: float
    speed_kmh: float
    speed_kmh_min: float
    speed_kmh_max: float

    # Heading and orientation (degrees clockwise from North, 0-360)
    heading_deg: float
    heading_uncertainty_deg: float

    # Coherence checks
    collinearity_px: float
    green_relative_fraction: float
    expected_green_fraction: float
    fraction_deviation: float
    runway_diff_deg: float | None = None

    def summary(self) -> str:
        """Format a human-readable multi-line summary."""
        lines = [
            "============================================================",
            "Sentinel-2 Moving Object Kinematics & Coherence Report",
            "============================================================",
            f"Distance:     {self.distance_m:.1f} m (range: {self.distance_min_m:.1f} - {self.distance_max_m:.1f} m, 1-sigma: +/-{self.distance_std_m:.1f} m)",
            f"Heading:      {self.heading_deg:.1f} deg clockwise from North (+/-{self.heading_uncertainty_deg:.1f} deg)",
            f"Velocity:     {self.speed_kmh:.0f} km/h (range: {self.speed_kmh_min:.0f} - {self.speed_kmh_max:.0f} km/h) [{self.speed_mps:.1f} m/s]",
            f"Delta t:      {self.delta_t_s:.3f} s (range: {self.delta_t_min_s:.3f} - {self.delta_t_max_s:.3f} s)",
            "------------------------------------------------------------",
            "Coherence Diagnostics:",
            f"  - Green collinearity offset: {self.collinearity_px:.2f} px (expected < ~1.0 px)",
            f"  - Green relative position:  {self.green_relative_fraction:.2f} (expected: {self.expected_green_fraction:.2f}, delta: {self.fraction_deviation:.2f})",
        ]
        if self.runway_diff_deg is not None:
            lines.append(f"  - Runway axis difference:   {self.runway_diff_deg:.1f} deg")
        lines.append("============================================================")
        return "\n".join(lines)


def calculate_motion(
    blue_centroid: tuple[float, float],
    red_centroid: tuple[float, float],
    green_centroid: tuple[float, float] | None = None,
    pixel_size_m: float = DEFAULT_PIXEL_SIZE_M,
    delta_t_s: float = DELTA_T_BLUE_RED_S,
    delta_t_rel_uncertainty: float = DELTA_T_RELATIVE_UNCERTAINTY,
    centroid_uncertainty_px: float = CENTROID_UNCERTAINTY_PX,
    runway_heading_deg: float | None = None,
) -> MeasurementResult:
    """Calculate displacement, heading, speed and coherence metrics.

    Motion vector is defined from Blue (acquired first at t=0 s) to Red (acquired last at t=1.005 s).

    In image raster space:
        x increases Eastwards (+X)
        y increases Southwards (+Y, rows increasing downwards)
    Therefore:
        dx_east = x_red - x_blue
        dy_north = -(y_red - y_blue) = y_blue - y_red

    Args:
        blue_centroid: (x, y) subpixel position in blue band (t=0 s).
        red_centroid: (x, y) subpixel position in red band (t=1.005 s).
        green_centroid: Optional (x, y) position in green band (t=0.527 s) for coherence.
        pixel_size_m: Physical pixel size in meters (default: 10.0 m).
        delta_t_s: Time difference between blue and red bands in seconds (default: 1.005 s).
        delta_t_rel_uncertainty: Relative variation in delta t (default: 0.02 = +/-2%).
        centroid_uncertainty_px: Subpixel localization uncertainty per endpoint (default: 0.5 px).
        runway_heading_deg: Optional runway heading for alignment test.

    Returns:
        MeasurementResult containing all computed values and bounds.
    """
    bx, by = blue_centroid
    rx, ry = red_centroid

    # Vector in raster pixel coordinates (Blue -> Red)
    dx_px = rx - bx
    dy_px = ry - by

    # Distance
    dist_px = math.hypot(dx_px, dy_px)
    if dist_px < 1e-6:
        raise ValueError("Centroid displacement is zero; cannot compute heading or velocity")

    dist_m = dist_px * pixel_size_m

    # Distance uncertainty propagation:
    # Worst-case bounds: +/- (2 * centroid_uncertainty) in pixels
    worst_case_delta_px = 2.0 * centroid_uncertainty_px
    dist_min_m = max(0.0, (dist_px - worst_case_delta_px) * pixel_size_m)
    dist_max_m = (dist_px + worst_case_delta_px) * pixel_size_m

    # 1-sigma standard deviation: sigma_d = sqrt(2) * centroid_uncertainty_px * pixel_size_m
    dist_std_m = math.sqrt(2.0) * centroid_uncertainty_px * pixel_size_m

    # Temporal bounds
    dt_min = delta_t_s * (1.0 - delta_t_rel_uncertainty)
    dt_max = delta_t_s * (1.0 + delta_t_rel_uncertainty)

    # Velocities
    speed_mps = dist_m / delta_t_s
    speed_mps_min = dist_min_m / dt_max
    speed_mps_max = dist_max_m / dt_min

    speed_kmh = speed_mps * 3.6
    speed_kmh_min = speed_mps_min * 3.6
    speed_kmh_max = speed_mps_max * 3.6

    # Geographic Heading (0 deg = North, 90 deg = East, 180 deg = South, 270 deg = West)
    dx_east = dx_px
    dy_north = -dy_px
    heading_deg = math.degrees(math.atan2(dx_east, dy_north)) % 360.0

    # Angular uncertainty: worst-case angular deviation
    sin_arg = min(1.0, worst_case_delta_px / dist_px)
    heading_uncertainty_deg = math.degrees(math.asin(sin_arg))

    # Coherence checks with Green band
    if green_centroid is not None:
        gx, gy = green_centroid
        # Vector from Blue to Green
        gdx_px = gx - bx
        gdy_px = gy - by

        # Perpendicular distance from Green to the Blue-Red vector line (in pixels):
        # |v x gv| / |v|
        collinearity_px = abs(dx_px * gdy_px - dy_px * gdx_px) / dist_px

        # Relative longitudinal fraction along the trajectory: (gv . v) / |v|^2
        green_relative_fraction = (gdx_px * dx_px + gdy_px * dy_px) / (dist_px**2)
        fraction_deviation = abs(green_relative_fraction - EXPECTED_GREEN_RELATIVE_FRACTION)
    else:
        collinearity_px = 0.0
        green_relative_fraction = EXPECTED_GREEN_RELATIVE_FRACTION
        fraction_deviation = 0.0

    # Runway alignment check
    runway_diff_deg = None
    if runway_heading_deg is not None:
        # Runway axis is bidirectional (e.g. runway 12/30 is 120 deg or 300 deg)
        # Calculate acute angle between heading and the runway axis (0 to 90 deg)
        axis_diff = abs((heading_deg - runway_heading_deg + 90.0) % 180.0 - 90.0)
        runway_diff_deg = axis_diff

    return MeasurementResult(
        dx_px=dx_px,
        dy_px=dy_px,
        distance_px=dist_px,
        distance_m=dist_m,
        distance_min_m=dist_min_m,
        distance_max_m=dist_max_m,
        distance_std_m=dist_std_m,
        delta_t_s=delta_t_s,
        delta_t_min_s=dt_min,
        delta_t_max_s=dt_max,
        speed_mps=speed_mps,
        speed_mps_min=speed_mps_min,
        speed_mps_max=speed_mps_max,
        speed_kmh=speed_kmh,
        speed_kmh_min=speed_kmh_min,
        speed_kmh_max=speed_kmh_max,
        heading_deg=heading_deg,
        heading_uncertainty_deg=heading_uncertainty_deg,
        collinearity_px=collinearity_px,
        green_relative_fraction=green_relative_fraction,
        expected_green_fraction=EXPECTED_GREEN_RELATIVE_FRACTION,
        fraction_deviation=fraction_deviation,
        runway_diff_deg=runway_diff_deg,
    )
