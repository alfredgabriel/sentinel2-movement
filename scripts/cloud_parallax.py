"""Measure cloud disparity and stereoscopic parallax between Sentinel-2 spectral bands.

Implements normalized 2D cross-correlation to estimate subpixel inter-band disparity
for cloud fields, computes along-track parallax displacement, and infers apparent
cloud height following Krauß (2021).

Important Scientific Note:
    Clouds are subject to ambient wind advection during the ~1.005 s inter-band delay.
    Ambiguity depends on the along-track wind component at cloud height: with wind predominantly
    perpendicular to the track, along-track displacement is small compared to high-altitude
    cirrus parallax (~90 m at 10.5 km). However, significant along-track wind components
    (e.g. 50 km/h = 13.9 m/s along-track -> 14 m drift) introduce an altitude shift of ~1.6 km,
    which should be considered when assessing band order consistency.

References:
    - Krauß, T. (2021). "EXTRACTION OF CLOUD HEIGHTS FROM SENTINEL-2 MULTISPECTRAL IMAGES",
      ISPRS Annals, Vol. V-1-2021, pp. 17-23. DOI: 10.5194/isprs-annals-V-1-2021-17-2021
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy import signal

from s2motion.constants import (
    DEFAULT_PIXEL_SIZE_M as GSD_M,
)
from s2motion.constants import (
    DELTA_T_RED_BLUE_S,
    SENTINEL2_MEAN_ALTITUDE_M,
)
from s2motion.parallax import calculate_satellite_ground_track

# Default peak localization uncertainty (subpixel parabolic refinement)
CORRELATION_UNCERTAINTY_PX: Final[float] = 0.15


@dataclass(frozen=True)
class CloudDisparityResult:
    """Disparity and stereoscopic cloud height result."""

    dx_px: float  # Horizontal pixel shift (columns, positive Eastward)
    dy_px: float  # Vertical pixel shift (rows, positive Southward)
    correlation_peak: float
    dx_m: float  # Displacement Eastward in meters
    dy_m: float  # Displacement Northward in meters
    along_track_m: float  # Displacement component along satellite ground track
    cross_track_m: float  # Displacement component across satellite ground track
    inferred_altitude_m: float
    altitude_uncertainty_m: float
    band_order: str
    wind_ambiguity_note: str


def compute_subpixel_disparity(
    image_ref: np.ndarray,
    image_target: np.ndarray,
    gsd_m: float = GSD_M,
) -> tuple[float, float, float]:
    """Compute 2D subpixel displacement of image_target relative to image_ref.

    Uses normalized 2D cross-correlation followed by 2D quadratic peak interpolation.

    Args:
        image_ref: Reference band image 2D array (e.g. Red / B04).
        image_target: Target band image 2D array (e.g. Blue / B02).
        gsd_m: Ground sampling distance in meters (default: 10.0 m).

    Returns:
        tuple (dx_px, dy_px, peak_corr) where dx_px is column shift (Eastward)
        and dy_px is row shift (Southward).
    """
    ref = image_ref.astype(np.float64)
    target = image_target.astype(np.float64)

    # Normalize by subtracting mean and dividing by standard deviation
    ref_norm = ref - np.mean(ref)
    target_norm = target - np.mean(target)
    ref_std = np.std(ref_norm)
    target_std = np.std(target_norm)

    if ref_std < 1e-6 or target_std < 1e-6:
        return 0.0, 0.0, 0.0

    ref_norm /= ref_std
    target_norm /= target_std

    # 2D cross-correlation via FFT convolution
    # mode='same' centers the zero-lag response at center of array
    corr = signal.fftconvolve(ref_norm, target_norm[::-1, ::-1], mode="same")
    corr /= ref_norm.size

    # Integer peak location
    center_y, center_x = ref.shape[0] // 2, ref.shape[1] // 2
    peak_y, peak_x = np.unravel_index(np.argmax(corr), corr.shape)

    # Subpixel refinement using 3x3 quadratic interpolation
    sub_y = float(peak_y)
    sub_x = float(peak_x)

    if 0 < peak_y < corr.shape[0] - 1:
        c_m1 = corr[peak_y - 1, peak_x]
        c_0 = corr[peak_y, peak_x]
        c_p1 = corr[peak_y + 1, peak_x]
        denom = c_m1 - 2.0 * c_0 + c_p1
        if abs(denom) > 1e-9:
            sub_y += (c_m1 - c_p1) / (2.0 * denom)

    if 0 < peak_x < corr.shape[1] - 1:
        c_m1 = corr[peak_y, peak_x - 1]
        c_0 = corr[peak_y, peak_x]
        c_p1 = corr[peak_y, peak_x + 1]
        denom = c_m1 - 2.0 * c_0 + c_p1
        if abs(denom) > 1e-9:
            sub_x += (c_m1 - c_p1) / (2.0 * denom)

    # Relative shift of target relative to reference:
    # Target position = Reference position + (dx_px, dy_px)
    # Since fftconvolve(ref, target[::-1,::-1]) peaks at (-dy, -dx):
    dx_px = -(sub_x - center_x)
    dy_px = -(sub_y - center_y)
    peak_corr = float(corr[peak_y, peak_x])

    return dx_px, dy_px, peak_corr


def analyze_cloud_parallax(
    dx_px: float,
    dy_px: float,
    peak_corr: float,
    latitude_deg: float = 43.3,
    band_order: str = "red-first",
    gsd_m: float = GSD_M,
    delta_t_s: float = DELTA_T_RED_BLUE_S,
    satellite_altitude_m: float = SENTINEL2_MEAN_ALTITUDE_M,
) -> CloudDisparityResult:
    """Project measured cloud disparity onto satellite ground track and infer altitude.

    Args:
        dx_px: Measured column shift in pixels (Eastward).
        dy_px: Measured row shift in pixels (Southward).
        peak_corr: Normalized cross-correlation peak value.
        latitude_deg: Scene latitude in degrees.
        band_order: Assumed sequence ('red-first' or 'blue-first').
        gsd_m: Ground sampling distance in meters (default: 10.0 m).
        delta_t_s: Inter-band delay in seconds (default: 1.005 s).
        satellite_altitude_m: Satellite height in meters (default: 786000.0 m).

    Returns:
        CloudDisparityResult with along-track projection and height estimation.
    """
    track = calculate_satellite_ground_track(latitude_deg=latitude_deg)

    # Ground displacements:
    # dx_px > 0 -> Eastward (+X)
    # dy_px > 0 -> Southward (-Y in cartographic North)
    dx_m = dx_px * gsd_m
    dy_m = -dy_px * gsd_m  # Northward displacement

    # Ground track unit vector (heading psi_track clockwise from North)
    psi_rad = math.radians(track.ground_track_heading_deg)
    u_north = math.cos(psi_rad)
    u_east = math.sin(psi_rad)

    # Cross-track unit vector (perpendicular to track, pointing right / East-Southeast)
    u_cross_north = -math.sin(psi_rad)
    u_cross_east = math.cos(psi_rad)

    # Decompose displacement vector onto along-track and cross-track axes
    along_track_disp_m = dy_m * u_north + dx_m * u_east
    cross_track_disp_m = dy_m * u_cross_north + dx_m * u_cross_east

    # In pushbroom geometry:
    # For leading band to trailing band:
    # Parallax displacement is directed OPPOSITE to satellite ground track:
    # d_parallax = -(h / H) * v_track * dt
    # If the cloud is static, along_track_disp_m ~= -(h / H) * v_track * dt
    # Therefore, inferred height h = -along_track_disp_m * H / (v_track * dt)
    h_inferred = (
        -along_track_disp_m * satellite_altitude_m / (track.ground_track_speed_mps * delta_t_s)
    )

    # Uncertainty from cross-correlation peak localization (~0.15 px = 1.5 m)
    sigma_disp_m = CORRELATION_UNCERTAINTY_PX * gsd_m
    sigma_h = (sigma_disp_m * satellite_altitude_m) / (track.ground_track_speed_mps * delta_t_s)

    wind_note = (
        "WIND ADVECTION SENSITIVITY: Inferred altitude depends primarily on the along-track "
        "component of upper-air wind during the 1.005 s delay. For winds predominantly cross-track, "
        "along-track displacement is small relative to high cirrus parallax (~90 m at 10.5 km). "
        "However, significant along-track wind components (e.g. 50 km/h = 13.9 m/s along-track -> "
        "14 m drift) introduce an altitude shift of ~1.6 km, which should be accounted for when "
        "interpreting the disparity."
    )

    return CloudDisparityResult(
        dx_px=dx_px,
        dy_px=dy_px,
        correlation_peak=peak_corr,
        dx_m=dx_m,
        dy_m=dy_m,
        along_track_m=along_track_disp_m,
        cross_track_m=cross_track_disp_m,
        inferred_altitude_m=h_inferred,
        altitude_uncertainty_m=sigma_h,
        band_order=band_order,
        wind_ambiguity_note=wind_note,
    )


def generate_synthetic_cloud_pair(
    size_px: int = 128,
    cloud_altitude_m: float = 3000.0,
    wind_u_mps: float = 0.0,  # Eastward wind
    wind_v_mps: float = 0.0,  # Northward wind
    latitude_deg: float = 43.3,
    noise_std: float = 0.02,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Generate synthetic Red/Blue cloud crop pair exhibiting stereoscopic parallax.

    Returns:
        tuple (ref_red, target_blue, true_dx_px, true_dy_px)
    """
    rng = np.random.default_rng(seed)

    # Generate synthetic smooth cloud pattern using low-pass filtered Gaussian noise
    raw = rng.standard_normal((size_px, size_px))
    kernel_size = 15
    y, x = np.mgrid[-kernel_size : kernel_size + 1, -kernel_size : kernel_size + 1]
    kernel = np.exp(-(x**2 + y**2) / (2.0 * 4.0**2))
    kernel /= kernel.sum()
    cloud = signal.convolve2d(raw, kernel, mode="same")
    cloud = (cloud - cloud.min()) / (cloud.max() - cloud.min())

    track = calculate_satellite_ground_track(latitude_deg=latitude_deg)
    H = SENTINEL2_MEAN_ALTITUDE_M
    dt = DELTA_T_RED_BLUE_S

    # Pure parallax displacement (opposite to ground track)
    psi_rad = math.radians(track.ground_track_heading_deg)
    par_disp_m = (cloud_altitude_m / H) * track.ground_track_speed_mps * dt

    disp_north_m = -par_disp_m * math.cos(psi_rad) + wind_v_mps * dt
    disp_east_m = -par_disp_m * math.sin(psi_rad) + wind_u_mps * dt

    # Convert to pixel shifts
    true_dx_px = disp_east_m / GSD_M
    true_dy_px = -disp_north_m / GSD_M  # Row index increases Southward

    # Shift target image using Fourier phase shift theorem
    ny, nx = cloud.shape
    ky = np.fft.fftfreq(ny)[:, None]
    kx = np.fft.fftfreq(nx)[None, :]
    shift_phase = np.exp(-2j * np.pi * (ky * true_dy_px + kx * true_dx_px))
    shifted_cloud = np.real(np.fft.ifft2(np.fft.fft2(cloud) * shift_phase))

    # Add detector noise
    ref_red = np.clip(cloud + rng.normal(0, noise_std, cloud.shape), 0.0, 1.0)
    target_blue = np.clip(shifted_cloud + rng.normal(0, noise_std, shifted_cloud.shape), 0.0, 1.0)

    return ref_red, target_blue, true_dx_px, true_dy_px


def main() -> None:
    """CLI runner for cloud disparity and parallax analysis."""
    parser = argparse.ArgumentParser(
        description="Measure cloud disparity and stereoscopic parallax in Sentinel-2 images."
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run synthetic cloud demonstration with controlled parallax and wind.",
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=3500.0,
        help="Simulated cloud altitude in meters for synthetic test (default: 3500 m).",
    )
    parser.add_argument(
        "--wind-speed-kmh",
        type=float,
        default=0.0,
        help="Simulated horizontal wind speed in km/h for synthetic test (default: 0 km/h).",
    )
    parser.add_argument(
        "--wind-heading-deg",
        type=float,
        default=270.0,
        help="Simulated wind direction (origin) in degrees (default: 270 deg = West).",
    )
    parser.add_argument(
        "--latitude",
        type=float,
        default=43.3,
        help="Scene latitude in degrees (default: 43.3).",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("Sentinel-2 Cloud Disparity & Stereoscopic Parallax Tool")
    print("=" * 65)

    if args.synthetic:
        # Convert wind to Eastward and Northward m/s
        wind_mps = args.wind_speed_kmh / 3.6
        wind_rad = math.radians(args.wind_heading_deg)
        # Meteorological wind: from angle, so motion vector points towards angle + 180°
        wind_u = -wind_mps * math.sin(wind_rad)
        wind_v = -wind_mps * math.cos(wind_rad)

        print(f"Simulating synthetic cloud layer at h = {args.altitude:.0f} m")
        if args.wind_speed_kmh > 0:
            print(
                f"Applying ambient wind: {args.wind_speed_kmh:.1f} km/h from {args.wind_heading_deg:.0f}°"
            )
        else:
            print("Ambient wind: 0.0 km/h (static atmosphere assumption)")

        red_crop, blue_crop, true_dx, true_dy = generate_synthetic_cloud_pair(
            size_px=128,
            cloud_altitude_m=args.altitude,
            wind_u_mps=wind_u,
            wind_v_mps=wind_v,
            latitude_deg=args.latitude,
        )

        dx_meas, dy_meas, peak_corr = compute_subpixel_disparity(red_crop, blue_crop)
        res = analyze_cloud_parallax(
            dx_px=dx_meas,
            dy_px=dy_meas,
            peak_corr=peak_corr,
            latitude_deg=args.latitude,
        )

        print("-" * 65)
        print("Cross-Correlation Disparity:")
        print(f"  - Measured Shift:   dx = {res.dx_px:+.2f} px, dy = {res.dy_px:+.2f} px")
        print(f"  - True Ground Disp: dx = {true_dx * 10.0:+.1f} m, dy = {-true_dy * 10.0:+.1f} m")
        print(f"  - Correlation Peak: {res.correlation_peak:.4f}")
        print("-" * 65)
        print("Along-Track Kinematics:")
        print(f"  - Along-Track Disp: {res.along_track_m:+.2f} m")
        print(f"  - Cross-Track Disp: {res.cross_track_m:+.2f} m")
        print(
            f"  - Inferred Height:  {res.inferred_altitude_m:.0f} m (±{res.altitude_uncertainty_m:.0f} m)"
        )
        print(f"  - Height Residual:  {res.inferred_altitude_m - args.altitude:+.0f} m")
        print("-" * 65)
        print(res.wind_ambiguity_note)
        print("=" * 65)
    else:
        print("Run with --synthetic to execute synthetic cloud demonstration.")
        print(
            "Example: python scripts/cloud_parallax.py --synthetic --altitude 4000 --wind-speed-kmh 30"
        )


if __name__ == "__main__":
    main()
