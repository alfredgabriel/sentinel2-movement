"""Tests for visualization functions."""

import numpy as np
import pytest

from s2motion.measure import calculate_motion
from s2motion.viz import create_annotated_figure, create_rgb_composite


def test_create_rgb_composite() -> None:
    """Verify RGB composition dimensions and normalization."""
    red = np.full((50, 60), 200.0, dtype=np.float32)
    green = np.full((50, 60), 100.0, dtype=np.float32)
    blue = np.full((50, 60), 50.0, dtype=np.float32)

    rgb = create_rgb_composite({"red": red, "green": green, "blue": blue})
    assert rgb.shape == (50, 60, 3)
    assert 0.0 <= rgb.min() <= rgb.max() <= 1.0


def test_create_rgb_composite_missing_band() -> None:
    """Verify error when required band is missing."""
    with pytest.raises(KeyError, match="Band 'blue' required"):
        create_rgb_composite({"red": np.zeros((10, 10)), "green": np.zeros((10, 10))})


def test_create_annotated_figure_save(tmp_path) -> None:
    """Verify figure creation and image file generation."""
    h, w = 60, 60
    bands = {
        "red": np.ones((h, w), dtype=np.float32) * 50,
        "green": np.ones((h, w), dtype=np.float32) * 50,
        "blue": np.ones((h, w), dtype=np.float32) * 50,
    }
    centroids = {"red": (20.0, 30.0), "green": (24.0, 28.0), "blue": (28.0, 26.0)}
    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids["green"],
        runway_heading_deg=120.0,
    )

    out_file = tmp_path / "test_figure.png"
    fig = create_annotated_figure(
        bands=bands,
        centroids=centroids,
        result=result,
        title="Test Figure",
        out_path=out_file,
    )
    assert fig is not None
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_create_annotated_figure_with_aerodynamics(tmp_path) -> None:
    """Verify annotated figure generation with weather and aerodynamic telemetry overlays."""
    from s2motion.weather import WeatherObservation, compute_aerodynamics

    h, w = 60, 60
    bands = {
        "red": np.ones((h, w), dtype=np.float32) * 50,
        "green": np.ones((h, w), dtype=np.float32) * 50,
        "blue": np.ones((h, w), dtype=np.float32) * 50,
    }
    centroids = {"red": (20.0, 30.0), "green": (24.0, 28.0), "blue": (28.0, 26.0)}
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
        ground_speed_mps=80.0,
        heading_deg=117.4,
        weather=obs,
        elevation_m=42.0,
    )
    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids["green"],
        runway_heading_deg=120.0,
        aero=aero,
    )

    out_file = tmp_path / "test_aero_figure.png"
    fig = create_annotated_figure(
        bands=bands,
        centroids=centroids,
        result=result,
        title="Test Aero Figure",
        out_path=out_file,
    )
    assert fig is not None
    assert out_file.exists()
    assert out_file.stat().st_size > 0
