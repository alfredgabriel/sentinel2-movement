"""Unit tests for s2motion.geo module (georeferencing and runway proximity)."""

import pytest
from rasterio.transform import Affine

from s2motion.constants import (
    LEBB_RUNWAY_12_THR_WGS84,
    LEBB_RUNWAY_30_THR_WGS84,
)
from s2motion.geo import (
    calculate_geodetic_bearing,
    calculate_runway_proximity,
    pixel_to_wgs84,
)


def test_calculate_geodetic_bearing_cardinal() -> None:
    """Verify bearing calculation for cardinal directions."""
    # Due North: lat increases, lon constant -> bearing 0°
    b_north = calculate_geodetic_bearing(lat1=43.0, lon1=-3.0, lat2=44.0, lon2=-3.0)
    assert abs(b_north - 0.0) < 1e-3

    # Due South: lat decreases, lon constant -> bearing 180°
    b_south = calculate_geodetic_bearing(lat1=44.0, lon1=-3.0, lat2=43.0, lon2=-3.0)
    assert abs(b_south - 180.0) < 1e-3

    # Due East along equator
    b_east = calculate_geodetic_bearing(lat1=0.0, lon1=0.0, lat2=0.0, lon2=1.0)
    assert abs(b_east - 90.0) < 1e-3


def test_calculate_geodetic_bearing_lebb() -> None:
    """Verify geodetic bearing of Bilbao Airport Runway 12/30 thresholds."""
    lat12, lon12 = LEBB_RUNWAY_12_THR_WGS84
    lat30, lon30 = LEBB_RUNWAY_30_THR_WGS84
    bearing = calculate_geodetic_bearing(lat12, lon12, lat30, lon30)
    # Forward bearing from THR 12 to THR 30 should be approximately 116.73°
    assert abs(bearing - 116.73) < 0.1


def test_pixel_to_wgs84() -> None:
    """Verify pixel to WGS84 conversion with a known UTM transform."""
    # Affine transform for UTM 30N (10 m pixels)
    # Origin at (500000, 4800000)
    transform = Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 4800000.0)
    crs = "EPSG:32630"

    lon, lat = pixel_to_wgs84(0.0, 0.0, transform=transform, crs=crs)
    assert -3.1 < lon < -2.9
    assert 43.2 < lat < 43.5

    # 100 pixels east, 100 pixels south
    lon2, lat2 = pixel_to_wgs84(100.0, 100.0, transform=transform, crs=crs)
    assert lon2 > lon
    assert lat2 < lat


def test_calculate_runway_proximity_on_and_off_runway() -> None:
    """Verify runway containment and approach corridor classification."""
    thr12 = LEBB_RUNWAY_12_THR_WGS84  # (43.306347, -2.924939)
    thr30 = LEBB_RUNWAY_30_THR_WGS84  # (43.296086, -2.896950)

    # 1. Point at the exact THR 12 threshold
    res_thr12 = calculate_runway_proximity(
        obj_lon=thr12[1],
        obj_lat=thr12[0],
        thr12_latlon=thr12,
        thr30_latlon=thr30,
    )
    assert res_thr12.dist_thr12_m < 1.0
    assert abs(res_thr12.along_axis_m) < 1.0
    assert res_thr12.cross_axis_m < 1.0
    assert res_thr12.is_on_runway is True

    # 2. Point in the approach corridor (NW of THR 12, ~1 km out, ~10 m off centerline)
    # Case 1 coordinates: lat ~43.31077, lon ~-2.93687
    res_approach = calculate_runway_proximity(
        obj_lon=-2.93687,
        obj_lat=43.31077,
        thr12_latlon=thr12,
        thr30_latlon=thr30,
    )
    assert 1000.0 < res_approach.dist_thr12_m < 1200.0
    assert res_approach.along_axis_m < 0.0  # In approach prior to threshold
    assert res_approach.cross_axis_m < 20.0  # Close to centerline
    assert res_approach.is_on_runway is False
    assert res_approach.closest_threshold == "12"

    # Summary text validation
    summary = res_approach.summary()
    assert "APPROACH CORRIDOR" in summary
    assert "Reference Centroid:" in summary
    assert "± 15 m" in summary
    assert "on runway surface: False" in summary


def test_calculate_runway_proximity_identical_points_raises() -> None:
    """Verify error when threshold points are identical."""
    with pytest.raises(ValueError, match="virtually identical"):
        calculate_runway_proximity(
            obj_lon=-2.9,
            obj_lat=43.3,
            thr12_latlon=(43.3, -2.9),
            thr30_latlon=(43.3, -2.9),
        )
