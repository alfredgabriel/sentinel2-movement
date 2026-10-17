"""Georeferencing and runway proximity calculations for s2motion.

Converts raster subpixel coordinates to WGS84 geographic coordinates and computes
spatial metrics relative to aerodrome runways (e.g. distances to threshold and extended centerline).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rasterio.transform import Affine
from rasterio.warp import transform as warp_transform

if TYPE_CHECKING:
    from rasterio.crs import CRS


@dataclass(frozen=True)
class RunwayProximityResult:
    """Spatial relationship between a detected object and an aerodrome runway."""

    runway_name: str
    runway_bearing_deg: float
    object_lon: float
    object_lat: float
    dist_thr12_m: float
    dist_thr30_m: float
    closest_threshold: str
    dist_closest_thr_m: float
    along_axis_m: (
        float  # Longitudinal distance along extended axis from THR 12 (negative = in approach)
    )
    cross_axis_m: float  # Perpendicular distance to extended centerline
    is_on_runway: bool

    def summary(self) -> str:
        """Format a human-readable summary of runway proximity."""
        loc_desc = (
            "ON RUNWAY"
            if self.is_on_runway
            else f"APPROACH CORRIDOR ({abs(self.along_axis_m):.0f} m before THR {self.closest_threshold})"
            if self.along_axis_m < 0
            else f"BEYOND RUNWAY END ({self.dist_closest_thr_m:.0f} m from THR {self.closest_threshold})"
        )
        return (
            f"Runway Position ({self.runway_name}, axis {self.runway_bearing_deg:.1f}°):\n"
            f"  - Geodetic Coordinates:   lat {self.object_lat:.6f}°, lon {self.object_lon:.6f}°\n"
            f"  - Proximity to THR 12:    {self.dist_thr12_m:.0f} m (along extended axis: {self.along_axis_m:+.0f} m)\n"
            f"  - Centerline Offset:      {self.cross_axis_m:.1f} m\n"
            f"  - Status:                 {loc_desc} [on runway surface: {self.is_on_runway}]"
        )


def pixel_to_wgs84(
    col: float,
    row: float,
    transform: Affine,
    crs: CRS | str,
) -> tuple[float, float]:
    """Convert raster subpixel coordinate (col, row) to WGS84 (lon, lat).

    Args:
        col: Subpixel column coordinate (X).
        row: Subpixel row coordinate (Y).
        transform: Affine transformation matrix mapping pixel to projected coordinates.
        crs: Coordinate Reference System of the raster (e.g. EPSG:32630).

    Returns:
        Tuple of (longitude, latitude) in EPSG:4326.
    """
    # Affine mapping: x = c + col * a + row * b, y = f + col * d + row * e
    x_proj = transform.c + col * transform.a + row * transform.b
    y_proj = transform.f + col * transform.d + row * transform.e
    lons, lats = warp_transform(crs, "EPSG:4326", [x_proj], [y_proj])
    return float(lons[0]), float(lats[0])


def calculate_geodetic_bearing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate the forward geodetic azimuth/bearing from point 1 to point 2.

    Formula:
        theta = atan2(sin(dlon)*cos(lat2), cos(lat1)*sin(lat2) - sin(lat1)*cos(lat2)*cos(dlon))

    Args:
        lat1: Latitude of start point in degrees.
        lon1: Longitude of start point in degrees.
        lat2: Latitude of destination point in degrees.
        lon2: Longitude of destination point in degrees.

    Returns:
        Initial bearing in degrees clockwise from true North (0° to 360°).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return bearing


def calculate_runway_proximity(
    obj_lon: float,
    obj_lat: float,
    thr12_latlon: tuple[float, float],
    thr30_latlon: tuple[float, float],
    runway_width_m: float = 45.0,
    runway_name: str = "LEBB Runway 12/30",
    projected_crs: str = "EPSG:32630",
) -> RunwayProximityResult:
    """Calculate spatial proximity of an object to a runway and its extended centerline.

    Projected in a metric CRS (default UTM 30N for Bilbao Airport).

    Args:
        obj_lon: Object WGS84 longitude in degrees.
        obj_lat: Object WGS84 latitude in degrees.
        thr12_latlon: (latitude, longitude) of Threshold 12 (NW).
        thr30_latlon: (latitude, longitude) of Threshold 30 (SE).
        runway_width_m: Physical runway width in meters (default: 45 m).
        runway_name: Human readable runway label.
        projected_crs: Metric CRS for accurate planar distance calculations.

    Returns:
        RunwayProximityResult containing distances, offsets, and surface containment.
    """
    lat12, lon12 = thr12_latlon
    lat30, lon30 = thr30_latlon

    # Calculate true forward geodetic bearing from threshold coordinates
    bearing_geodetic = calculate_geodetic_bearing(lat12, lon12, lat30, lon30)

    # Project thresholds and object to planar metric coordinates
    lons = [lon12, lon30, obj_lon]
    lats = [lat12, lat30, obj_lat]
    xs, ys = warp_transform("EPSG:4326", projected_crs, lons, lats)

    x12, y12 = xs[0], ys[0]
    x30, y30 = xs[1], ys[1]
    x_obj, y_obj = xs[2], ys[2]

    # Vector along runway axis from THR 12 to THR 30
    rwy_dx = x30 - x12
    rwy_dy = y30 - y12
    rwy_len = math.hypot(rwy_dx, rwy_dy)

    if rwy_len < 1.0:
        raise ValueError("Runway threshold coordinates are virtually identical")

    # Unit vector along runway axis
    u_x = rwy_dx / rwy_len
    u_y = rwy_dy / rwy_len

    # Normal unit vector (perpendicular to centerline)
    n_x = -u_y
    n_y = u_x

    # Vector from THR 12 to Object
    v_dx = x_obj - x12
    v_dy = y_obj - y12

    # Vector from THR 30 to Object
    v30_dx = x_obj - x30
    v30_dy = y_obj - y30

    dist_thr12 = math.hypot(v_dx, v_dy)
    dist_thr30 = math.hypot(v30_dx, v30_dy)

    # Distance along runway axis from THR 12 (negative means NW of THR 12 / in approach)
    along_axis = v_dx * u_x + v_dy * u_y

    # Perpendicular distance to extended centerline
    cross_axis = abs(v_dx * n_x + v_dy * n_y)

    # Closer threshold
    closest_thr = "12" if dist_thr12 <= dist_thr30 else "30"
    dist_closest = min(dist_thr12, dist_thr30)

    # Is the object within the physical pavement rectangle?
    is_on_runway = (0.0 <= along_axis <= rwy_len) and (cross_axis <= runway_width_m / 2.0)

    return RunwayProximityResult(
        runway_name=runway_name,
        runway_bearing_deg=bearing_geodetic,
        object_lon=obj_lon,
        object_lat=obj_lat,
        dist_thr12_m=dist_thr12,
        dist_thr30_m=dist_thr30,
        closest_threshold=closest_thr,
        dist_closest_thr_m=dist_closest,
        along_axis_m=along_axis,
        cross_axis_m=cross_axis,
        is_on_runway=is_on_runway,
    )
