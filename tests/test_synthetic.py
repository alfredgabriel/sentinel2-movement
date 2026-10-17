"""Synthetic end-to-end test with a moving Gaussian blob.

Verifies that the detection and measurement pipeline recovers the known velocity
within < 5 % error and known heading within < 2 deg, simulating Sentinel-2 pushbroom delays
in chronological ground order: Red -> Green -> Blue.
"""

import math

import numpy as np

from s2motion.constants import (
    DEFAULT_PIXEL_SIZE_M,
    EXPECTED_GREEN_RELATIVE_FRACTION,
    GROUND_ACQUISITION_TIMING_S,
)
from s2motion.detect import detect_all_centroids
from s2motion.measure import calculate_motion


def test_synthetic_moving_aircraft_recovery() -> None:
    """Simulate an aircraft moving at 270 km/h with 120 deg heading (runway 12 alignment)."""
    # Ground truth parameters
    true_speed_kmh = 270.0
    true_speed_mps = true_speed_kmh / 3.6  # 75.0 m/s
    true_speed_px_per_s = true_speed_mps / DEFAULT_PIXEL_SIZE_M  # 7.5 px/s
    true_heading_deg = 120.0  # Runway 12 orientation

    # Starting position at t=0 (Red, leading acquisition) in a 120x120 raster
    x0, y0 = 50.0, 50.0

    # Direction components
    heading_rad = math.radians(true_heading_deg)
    vx_east = true_speed_px_per_s * math.sin(heading_rad)
    vy_north = true_speed_px_per_s * math.cos(heading_rad)

    # In raster space: x increases East, y increases South (-vy_north)
    vx_raster = vx_east
    vy_raster = -vy_north

    # Generate synthetic bands with pushbroom ground acquisition order: Red -> Green -> Blue
    size = 120
    ys, xs = np.mgrid[0:size, 0:size]
    sigma = 1.3
    amplitude = 250.0
    background_level = 60.0

    bands: dict[str, np.ndarray] = {}
    seeds: dict[str, tuple[float, float]] = {}

    for band_name in ("red", "green", "blue"):
        t = GROUND_ACQUISITION_TIMING_S[band_name]
        true_x = x0 + vx_raster * t
        true_y = y0 + vy_raster * t

        # Gaussian blob
        dist_sq = (xs - true_x) ** 2 + (ys - true_y) ** 2
        blob = amplitude * np.exp(-dist_sq / (2.0 * sigma**2))

        # Add background and slight noise
        band = (
            background_level + blob + np.random.default_rng(42).normal(0.0, 1.0, size=(size, size))
        )
        bands[band_name] = band.astype(np.float32)

        # Realistic integer seed rounded from detection or manual click
        seeds[band_name] = (float(round(true_x)), float(round(true_y)))

    # Step 1: Detect subpixel centroids
    detected_centroids = detect_all_centroids(bands, seeds, radius=3, threshold_ratio=0.5)

    # Step 2: Compute kinematics (Red -> Blue)
    result = calculate_motion(
        red_centroid=detected_centroids["red"],
        blue_centroid=detected_centroids["blue"],
        green_centroid=detected_centroids["green"],
        pixel_size_m=DEFAULT_PIXEL_SIZE_M,
        runway_heading_deg=120.0,
    )

    # Verification: velocity error < 5 %
    speed_error_rel = abs(result.speed_kmh - true_speed_kmh) / true_speed_kmh
    assert speed_error_rel < 0.05, (
        f"Speed error {speed_error_rel:.3%} exceeds 5% (got {result.speed_kmh:.1f} km/h)"
    )

    # Verification: heading error < 2 deg
    heading_error = abs(result.heading_deg - true_heading_deg)
    assert heading_error < 2.0, (
        f"Heading error {heading_error:.2f} deg exceeds 2 deg (got {result.heading_deg:.1f} deg)"
    )

    # Verification: collinearity offset < 0.5 px
    assert result.collinearity_px < 0.5, (
        f"Collinearity offset {result.collinearity_px:.2f} px too large"
    )

    # Verification: green relative position close to theoretical ~0.476
    assert abs(result.green_relative_fraction - EXPECTED_GREEN_RELATIVE_FRACTION) < 0.05, (
        f"Green relative fraction {result.green_relative_fraction:.3f} deviates from expected"
    )

    # Verification: uncertainty interval contains true value
    assert result.speed_kmh_min <= true_speed_kmh <= result.speed_kmh_max
