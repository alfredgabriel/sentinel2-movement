import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

from s2motion.measure import calculate_motion
from s2motion.viz import (
    create_annotated_figure,
    create_multiband_panel,
    create_overview_figure,
    create_pixel_grid_zoom,
    create_rgb_composite,
    create_social_card,
)


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


def test_create_overview_figure(tmp_path) -> None:
    """Verify overview figure creation with target bounding reticle."""
    h, w = 100, 100
    bands = {
        "red": np.ones((h, w), dtype=np.float32) * 40,
        "green": np.ones((h, w), dtype=np.float32) * 50,
        "blue": np.ones((h, w), dtype=np.float32) * 60,
    }
    out_file = tmp_path / "overview.png"
    fig = create_overview_figure(
        bands=bands,
        target_coords=(50.0, 50.0),
        title="Test Overview",
        out_path=out_file,
    )
    assert fig is not None
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_create_multiband_panel(tmp_path) -> None:
    """Verify multiband 4-panel generation (B02, B03, B04, B08)."""
    h, w = 60, 60
    bands = {
        "red": np.ones((h, w), dtype=np.float32) * 40,
        "green": np.ones((h, w), dtype=np.float32) * 50,
        "blue": np.ones((h, w), dtype=np.float32) * 60,
        "nir": np.ones((h, w), dtype=np.float32) * 70,
    }
    centroids = {
        "red": (25.0, 30.0),
        "green": (26.0, 28.0),
        "blue": (27.0, 26.0),
        "nir": (25.1, 29.9),
    }
    out_file = tmp_path / "multiband.png"
    fig = create_multiband_panel(
        bands=bands,
        centroids=centroids,
        title="Test Multiband",
        out_path=out_file,
    )
    assert fig is not None
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_create_pixel_grid_zoom(tmp_path) -> None:
    """Verify pixel grid zoom figure generation."""
    h, w = 40, 40
    bands = {
        "red": np.ones((h, w), dtype=np.float32) * 40,
        "green": np.ones((h, w), dtype=np.float32) * 50,
        "blue": np.ones((h, w), dtype=np.float32) * 60,
    }
    centroids = {"red": (20.0, 20.0), "green": (21.0, 19.0), "blue": (22.0, 18.0)}
    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids["green"],
    )
    out_file = tmp_path / "pixel_grid.png"
    fig = create_pixel_grid_zoom(
        bands=bands,
        centroids=centroids,
        result=result,
        title="Test Pixel Grid",
        out_path=out_file,
    )
    assert fig is not None
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_create_social_card_dimensions_and_lang(tmp_path) -> None:
    """Verify 4:5 social media card dimensions (1080x1350) and bilingual rendering."""
    import matplotlib.image as mpimg

    h, w = 40, 40
    bands = {
        "red": np.ones((h, w), dtype=np.float32) * 40,
        "green": np.ones((h, w), dtype=np.float32) * 50,
        "blue": np.ones((h, w), dtype=np.float32) * 60,
    }
    centroids = {"red": (20.0, 20.0), "green": (21.0, 19.0), "blue": (22.0, 18.0)}
    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids["green"],
    )

    out_es = tmp_path / "social_es.png"
    create_social_card(
        case_id="case1",
        bands=bands,
        centroids=centroids,
        result=result,
        lang="es",
        out_path=out_es,
    )
    assert out_es.exists()
    img_es = mpimg.imread(str(out_es))
    # 6.0 in * 180 dpi = 1080 px; 7.5 in * 180 dpi = 1350 px
    assert img_es.shape[0] == 1350
    assert img_es.shape[1] == 1080

    out_en = tmp_path / "social_en.png"
    create_social_card(
        case_id="case2",
        bands=bands,
        centroids=centroids,
        result=result,
        lang="en",
        out_path=out_en,
    )
    assert out_en.exists()
    img_en = mpimg.imread(str(out_en))
    assert img_en.shape[0] == 1350
    assert img_en.shape[1] == 1080


def test_offline_examples_data_fixtures_exist() -> None:
    """Verify that offline data fixtures exist in examples/data/ and load properly."""
    from pathlib import Path

    case1_npz = Path("examples/data/loiu_2026-08-12.npz")
    case2_npz = Path("examples/data/loiu_2026-06-21.npz")

    assert case1_npz.exists(), "Offline fixture for case 1 must exist"
    assert case2_npz.exists(), "Offline fixture for case 2 must exist"

    data1 = np.load(case1_npz)
    for band in ("red", "green", "blue", "nir"):
        assert band in data1
        assert data1[band].ndim == 2
        assert data1[band].size > 1000

    data2 = np.load(case2_npz)
    for band in ("red", "green", "blue", "nir"):
        assert band in data2
        assert data2[band].ndim == 2
        assert data2[band].size > 1000
