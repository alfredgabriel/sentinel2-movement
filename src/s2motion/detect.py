"""Detection module for local anomaly extraction and subpixel centroiding."""

import logging

import numpy as np
from scipy.ndimage import median_filter

logger = logging.getLogger(__name__)


def subtract_local_background(
    band: np.ndarray,
    kernel_size: int = 9,
) -> np.ndarray:
    """Subtract local background using a 2D median filter.

    Highlights bright local anomalies (e.g. moving vehicles or aircraft against runways)
    by subtracting the spatial median background and clipping negative values to zero.

    Args:
        band: 2D float array containing single-band reflectance/radiance.
        kernel_size: Neighborhood kernel size for the median filter (default: 9).

    Returns:
        2D float array of positive local anomalies (band - median_background >= 0).
    """
    if band.ndim != 2:
        raise ValueError(f"Expected a 2D array, got shape {band.shape}")
    if kernel_size < 1 or kernel_size % 2 == 0:
        raise ValueError(f"kernel_size must be a positive odd integer, got {kernel_size}")

    bg = median_filter(band, size=kernel_size)
    anomaly = np.clip(band - bg, 0, None)
    return anomaly.astype(np.float32)


def compute_subpixel_centroid(
    anomaly: np.ndarray,
    seed: tuple[float, float],
    radius: int = 3,
    threshold_ratio: float = 0.5,
) -> tuple[float, float]:
    """Compute subpixel weighted center of mass around a seed coordinate.

    Args:
        anomaly: 2D float array of positive local anomalies.
        seed: Initial (x, y) seed coordinate in pixel space.
        radius: Half-window radius in pixels (default: 3, forming a (2*radius+1)^2 box).
        threshold_ratio: Fraction of local maximum used for peak filtering (default: 0.5).

    Returns:
        Subpixel (x, y) centroid coordinates.

    Raises:
        ValueError: If seed is outside array bounds or if no signal is found in window.
    """
    if anomaly.ndim != 2:
        raise ValueError(f"Expected 2D anomaly array, got {anomaly.shape}")

    h, w = anomaly.shape
    x0, y0 = int(round(seed[0])), int(round(seed[1]))

    if not (0 <= x0 < w and 0 <= y0 < h):
        raise ValueError(f"Seed ({seed[0]}, {seed[1]}) is out of bounds for image of shape ({h}, {w})")

    y_min = max(0, y0 - radius)
    y_max = min(h, y0 + radius + 1)
    x_min = max(0, x0 - radius)
    x_max = min(w, x0 + radius + 1)

    sub = anomaly[y_min:y_max, x_min:x_max]
    if sub.size == 0:
        raise ValueError(f"Empty window around seed ({seed[0]}, {seed[1]})")

    max_val = float(sub.max())
    if max_val <= 0:
        logger.warning(
            "No positive anomaly found around seed (%s, %s); falling back to integer seed",
            seed[0],
            seed[1],
        )
        return float(seed[0]), float(seed[1])

    ys, xs = np.mgrid[y_min:y_max, x_min:x_max]
    weights = np.where(sub >= threshold_ratio * max_val, sub, 0.0)
    total_weight = float(weights.sum())

    if total_weight <= 0:
        return float(seed[0]), float(seed[1])

    cx = float((xs * weights).sum() / total_weight)
    cy = float((ys * weights).sum() / total_weight)
    return cx, cy


def detect_band_centroid(
    band: np.ndarray,
    seed: tuple[float, float],
    kernel_size: int = 9,
    radius: int = 3,
    threshold_ratio: float = 0.5,
) -> tuple[float, float]:
    """Run full detection pipeline on a single band: background subtraction and centroiding.

    Args:
        band: 2D float array for one spectral band.
        seed: Initial (x, y) seed coordinate.
        kernel_size: Median filter window size.
        radius: Search radius around seed.
        threshold_ratio: Threshold relative to maximum anomaly in search window.

    Returns:
        Subpixel (x, y) centroid coordinate.
    """
    anomaly = subtract_local_background(band, kernel_size=kernel_size)
    return compute_subpixel_centroid(
        anomaly,
        seed=seed,
        radius=radius,
        threshold_ratio=threshold_ratio,
    )


def detect_all_centroids(
    bands: dict[str, np.ndarray],
    seeds: dict[str, tuple[float, float]],
    kernel_size: int = 9,
    radius: int = 3,
    threshold_ratio: float = 0.5,
) -> dict[str, tuple[float, float]]:
    """Detect subpixel centroids for multiple bands given seed coordinates.

    Args:
        bands: Dictionary mapping band names (e.g. 'red', 'green', 'blue') to 2D arrays.
        seeds: Dictionary mapping band names to initial (x, y) seed tuples.
        kernel_size: Median filter window size.
        radius: Search radius in pixels.
        threshold_ratio: Threshold factor for peak weighting.

    Returns:
        Dictionary mapping band names to detected subpixel (x, y) centroids.
    """
    centroids: dict[str, tuple[float, float]] = {}
    for band_name, seed in seeds.items():
        if band_name not in bands:
            raise KeyError(f"Band '{band_name}' provided in seeds but missing from bands dictionary")
        centroids[band_name] = detect_band_centroid(
            bands[band_name],
            seed=seed,
            kernel_size=kernel_size,
            radius=radius,
            threshold_ratio=threshold_ratio,
        )
    return centroids
