"""Tests for detection and subpixel centroiding."""

import numpy as np
import pytest

from s2motion.detect import (
    compute_subpixel_centroid,
    detect_all_centroids,
    subtract_local_background,
)


def test_subtract_local_background() -> None:
    """Verify that uniform background is removed and spike is preserved."""
    image = np.full((30, 30), 100.0, dtype=np.float32)
    image[15, 15] = 500.0  # Bright local anomaly

    anomaly = subtract_local_background(image, kernel_size=9)
    # The anomaly array should have ~0 in flat background and a strong peak at (15, 15)
    assert anomaly[0, 0] == 0.0
    assert anomaly[15, 15] > 300.0
    assert np.all(anomaly >= 0.0)


def test_subtract_local_background_invalid_args() -> None:
    """Verify parameter validations."""
    with pytest.raises(ValueError, match="kernel_size must be a positive odd integer"):
        subtract_local_background(np.zeros((10, 10)), kernel_size=8)
    with pytest.raises(ValueError, match="Expected a 2D array"):
        subtract_local_background(np.zeros((10, 10, 3)))


def test_compute_subpixel_centroid_synthetic_gaussian() -> None:
    """Verify that a subpixel Gaussian peak is accurately localized."""
    true_x = 24.35
    true_y = 18.65
    size = 40
    y_coords, x_coords = np.mgrid[0:size, 0:size]
    # Gaussian with sigma = 1.2
    sigma = 1.2
    synthetic = 200.0 * np.exp(
        -((x_coords - true_x) ** 2 + (y_coords - true_y) ** 2) / (2 * sigma**2)
    )

    # Seed close to the peak
    seed = (24.0, 19.0)
    cx, cy = compute_subpixel_centroid(synthetic, seed=seed, radius=3, threshold_ratio=0.5)

    # Subpixel localization accuracy within typical 0.15 px window boundary limit
    assert abs(cx - true_x) < 0.15
    assert abs(cy - true_y) < 0.15


def test_compute_subpixel_centroid_boundary_and_fallback() -> None:
    """Verify out-of-bounds check and fallback on uniform array."""
    arr = np.zeros((20, 20), dtype=np.float32)

    with pytest.raises(ValueError, match="out of bounds"):
        compute_subpixel_centroid(arr, seed=(-5, 10))

    # Fallback to integer seed on empty window
    cx, cy = compute_subpixel_centroid(arr, seed=(10.0, 10.0))
    assert (cx, cy) == (10.0, 10.0)


def test_detect_all_centroids() -> None:
    """Verify multi-band centroid detection helper."""
    b_blue = np.zeros((30, 30), dtype=np.float32)
    b_red = np.zeros((30, 30), dtype=np.float32)
    # Notice: array[y, x]
    b_blue[10, 10] = 100.0
    b_red[12, 14] = 100.0

    bands = {"blue": b_blue, "red": b_red}
    seeds = {"blue": (10.0, 10.0), "red": (14.0, 12.0)}

    centroids = detect_all_centroids(bands, seeds, radius=2)
    assert abs(centroids["blue"][0] - 10.0) < 0.01
    assert abs(centroids["blue"][1] - 10.0) < 0.01
    assert abs(centroids["red"][0] - 14.0) < 0.01
    assert abs(centroids["red"][1] - 12.0) < 0.01
