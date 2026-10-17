"""Physical constants, satellite sensor parameters, and scientific citations.

References:
    - Krauß, T. (2021). "EXTRACTION OF CLOUD HEIGHTS FROM SENTINEL-2 MULTISPECTRAL IMAGES",
      ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences,
      Vol. V-1-2021, pp. 17-23. DOI: 10.5194/isprs-annals-V-1-2021-17-2021
    - Binet, R., Bergsma, E., & Poulain, V. (2022). "ACCURATE SENTINEL-2 INTER-BAND TIME DELAYS",
      ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences,
      Vol. V-1-2022, pp. 57-66. DOI: 10.5194/isprs-annals-V-1-2022-57-2022
"""

from typing import Final

# ---------------------------------------------------------------------------
# Sentinel-2 Pushbroom Inter-Band Temporal Delays (10 m bands)
# Delays referenced to B02 (Blue): B02=0.000s, B08=0.264s, B03=0.527s, B04=1.005s.
# Source: Krauß (2021), p. 17.
#
# Physical ground acquisition order in flight direction (descending orbit):
# The detector for Band 4 (Red) leads on the focal plane along-track and reaches
# a ground target FIRST. Band 3 (Green), Band 8 (NIR), and Band 2 (Blue) follow sequentially.
# Therefore, an object in motion is imaged first in Red and last in Blue:
#   t_red   = 0.000 s  (B04, leading ground acquisition)
#   t_green = 1.005 - 0.527 = 0.478 s  (B03)
#   t_nir   = 1.005 - 0.264 = 0.741 s  (B08)
#   t_blue  = 1.005 s  (B02, trailing ground acquisition)
# ---------------------------------------------------------------------------
BAND_DELAYS_S: Final[dict[str, float]] = {
    "B02": 0.000,  # Blue (490 nm)
    "B08": 0.264,  # NIR (842 nm)
    "B03": 0.527,  # Green (560 nm)
    "B04": 1.005,  # Red (665 nm)
}

# Ground acquisition timing referenced to the first ground exposure (Red / B04 = 0.000 s)
GROUND_ACQUISITION_TIMING_S: Final[dict[str, float]] = {
    "red": 0.000,  # B04: leading detector
    "green": 0.478,  # B03: 1.005 - 0.527 s
    "nir": 0.741,  # B08: 1.005 - 0.264 s
    "blue": 1.005,  # B02: trailing detector (+1.005 s)
}

# Band name aliases mapping common names to Sentinel-2 band identifiers
BAND_ALIASES: Final[dict[str, str]] = {
    "red": "B04",
    "green": "B03",
    "nir": "B08",
    "blue": "B02",
}

# Chronological order of ground imaging for a moving object: Red -> Green -> Blue
CHRONOLOGICAL_GROUND_ORDER: Final[tuple[str, ...]] = ("red", "green", "blue")

# Total time elapsed between Red and Blue bands in seconds
DELTA_T_RED_BLUE_S: Final[float] = 1.005

# Theoretical relative position of green along the red-to-blue trajectory:
# (t_green - t_red) / (t_blue - t_red) = 0.478 / 1.005 ~= 0.4756
EXPECTED_GREEN_RELATIVE_FRACTION: Final[float] = 0.478 / DELTA_T_RED_BLUE_S


def get_band_timing(order: str = "red-first") -> dict[str, float]:
    """Return ground acquisition timing (in seconds) for 10m bands under specified order.

    Args:
        order: Temporal direction, either 'red-first' (empirically determined default)
               or 'blue-first'.

    Returns:
        Mapping of band name to acquisition time in seconds from initial band exposure.

    Raises:
        ValueError: If order is not 'red-first' or 'blue-first'.
    """
    if order == "red-first":
        return {
            "red": 0.000,
            "green": 0.478,  # 1.005 - 0.527 s
            "nir": 0.741,  # 1.005 - 0.264 s
            "blue": 1.005,
        }
    elif order == "blue-first":
        return {
            "blue": 0.000,
            "nir": 0.264,
            "green": 0.527,
            "red": 1.005,
        }
    else:
        raise ValueError(f"Invalid band order '{order}'. Must be 'red-first' or 'blue-first'.")


def get_expected_green_fraction(order: str = "red-first") -> float:
    """Return expected longitudinal fraction of Green between origin and destination bands.

    For 'red-first' (Red -> Green -> Blue):
        (t_green - t_red) / (t_blue - t_red) = 0.478 / 1.005 ~= 0.4756

    For 'blue-first' (Blue -> Green -> Red):
        (t_green - t_blue) / (t_red - t_blue) = 0.527 / 1.005 ~= 0.5244

    Args:
        order: Temporal direction, either 'red-first' or 'blue-first'.

    Returns:
        Expected relative longitudinal fraction (0.0 to 1.0).

    Raises:
        ValueError: If order is not 'red-first' or 'blue-first'.
    """
    if order == "red-first":
        return 0.478 / DELTA_T_RED_BLUE_S
    elif order == "blue-first":
        return 0.527 / DELTA_T_RED_BLUE_S
    else:
        raise ValueError(f"Invalid band order '{order}'. Must be 'red-first' or 'blue-first'.")


# ---------------------------------------------------------------------------
# Sensor and Physical Constants
# ---------------------------------------------------------------------------
# Ground Sampling Distance (GSD) for Sentinel-2 bands 2, 3, 4, 8
DEFAULT_PIXEL_SIZE_M: Final[float] = 10.0

# Temporal delay variability due to optical distortion, satellite altitude variations,
# and orbital perturbations (~ +/-2 %). Source: Binet et al. (2022).
DELTA_T_RELATIVE_UNCERTAINTY: Final[float] = 0.02

# Estimated 1-sigma subpixel centroid localization error per coordinate (pixels)
CENTROID_UNCERTAINTY_PX: Final[float] = 0.5

# ---------------------------------------------------------------------------
# Default Study Area: Bilbao Airport (Loiu, LEBB)
# ---------------------------------------------------------------------------
# WGS84 Bounding Box: (lon_min, lat_min, lon_max, lat_max)
BILBAO_AIRPORT_BBOX: Final[tuple[float, float, float, float]] = (
    -2.945,
    43.285,
    -2.875,
    43.325,
)

# Bilbao Airport (LEBB) Runway 12/30 threshold coordinates from AIP España (ENAIRE AD 2-LEBB):
# THR 12 (NW): 43°18'22.85"N, 002°55'29.78"W (lat 43.306347, lon -2.924939)
# THR 30 (SE): 43°17'45.91"N, 002°53'49.02"W (lat 43.296086, lon -2.896950)
# Dimensions: 2600 m x 45 m.
# True forward geodetic azimuth computed between thresholds: 116.73° (rounded to 116.7°).
LEBB_RUNWAY_12_THR_WGS84: Final[tuple[float, float]] = (43.306347, -2.924939)
LEBB_RUNWAY_30_THR_WGS84: Final[tuple[float, float]] = (43.296086, -2.896950)
LEBB_RUNWAY_WIDTH_M: Final[float] = 45.0
LEBB_RUNWAY_LENGTH_M: Final[float] = 2600.0

# Runway 12/30 true geodetic axis heading in degrees clockwise from true North
# Derived from AIP threshold coordinates (116.7°); '120°' is only the nominal magnetic runway designation.
BILBAO_RUNWAY_12_30_HEADING_DEG: Final[float] = 116.7

# ---------------------------------------------------------------------------
# AWS Earth Search STAC Defaults
# ---------------------------------------------------------------------------
DEFAULT_STAC_URL: Final[str] = "https://earth-search.aws.element84.com/v1"
DEFAULT_COLLECTION: Final[str] = "sentinel-2-l2a"

# Mapping from common band names to AWS Earth Search STAC asset names
STAC_ASSET_MAP: Final[dict[str, str]] = {
    "red": "red",
    "green": "green",
    "blue": "blue",
    "nir": "nir",
}

# ---------------------------------------------------------------------------
# Orbital and Satellite Parameters
# ---------------------------------------------------------------------------
# Sentinel-2 nominal orbit semi-major axis (meters)
SENTINEL2_SEMI_MAJOR_AXIS_M: Final[float] = 7157000.0

# Sentinel-2 nominal orbital altitude above mean sea level (meters)
SENTINEL2_MEAN_ALTITUDE_M: Final[float] = 786000.0

# Sun-synchronous orbit inclination (degrees)
SENTINEL2_INCLINATION_DEG: Final[float] = 98.62

# Standard gravitational parameter of Earth (m^3 / s^2)
EARTH_GM: Final[float] = 3.986004418e14

# Earth angular rotation rate (rad/s)
EARTH_ROTATION_RATE_RAD_S: Final[float] = 7.292115e-5

# Volumetric mean Earth radius (meters)
EARTH_MEAN_RADIUS_M: Final[float] = 6371000.0

# ---------------------------------------------------------------------------
# Literature Citations
# ---------------------------------------------------------------------------
CITATIONS: Final[dict[str, dict[str, str]]] = {
    "krauss_2021": {
        "authors": "Thomas Krauß",
        "title": "EXTRACTION OF CLOUD HEIGHTS FROM SENTINEL-2 MULTISPECTRAL IMAGES",
        "journal": (
            "ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences"
        ),
        "volume": "V-1-2021",
        "pages": "17-23",
        "year": "2021",
        "doi": "10.5194/isprs-annals-V-1-2021-17-2021",
        "url": "https://isprs-annals.copernicus.org/articles/V-1-2021/17/2021/",
    },
    "binet_2022": {
        "authors": "Renaud Binet, Erwin Bergsma, Vincent Poulain",
        "title": "ACCURATE SENTINEL-2 INTER-BAND TIME DELAYS",
        "journal": (
            "ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences"
        ),
        "volume": "V-1-2022",
        "pages": "57-66",
        "year": "2022",
        "doi": "10.5194/isprs-annals-V-1-2022-57-2022",
        "url": "https://isprs-annals.copernicus.org/articles/V-1-2022/57/2022/",
    },
    "heiselberg_2019": {
        "authors": "Henning Heiselberg",
        "title": "Aircraft and Ship Velocity Determination in Sentinel-2 Multispectral Images",
        "journal": "Sensors",
        "volume": "19",
        "number": "13",
        "pages": "2873",
        "year": "2019",
        "doi": "10.3390/s19132873",
        "url": "https://doi.org/10.3390/s19132873",
    },
    "heiselberg_2021": {
        "authors": "Peder Heiselberg, Henning Heiselberg",
        "title": "Aircraft Detection above Clouds by Sentinel-2 MSI Parallax",
        "journal": "Remote Sensing",
        "volume": "13",
        "number": "15",
        "pages": "3016",
        "year": "2021",
        "doi": "10.3390/rs13153016",
        "url": "https://doi.org/10.3390/rs13153016",
    },
    "esa_sentinel2_spec": {
        "authors": "European Space Agency (ESA)",
        "title": "Copernicus Sentinel-2 Mission Specification and Data Quality",
        "portal_url": "https://earth.esa.int/eoportal/satellite-missions/c-missions/sentinel-2",
        "geometric_quality_url": "https://sentiwiki.copernicus.eu/web/s2-geometric-data-quality",
        "year": "2023",
        "note": (
            "Specifies absolute geolocation requirement < 20 m (at 2-sigma / 95.5% confidence level) "
            "without GCPs on WGS84, and multi-temporal co-registration better than 4.5 m at 95% confidence "
            "with the Global Reference Image (GRI). "
            "TODO: verify direct permanent public URLs for ESA internal document codes S2-RS-ESA-SY-0001 and ESA-EOPG-EOQC-RP-0001."
        ),
    },
}

# Copernicus Sentinel-2 mandatory data attribution statement
COPERNICUS_ATTRIBUTION: Final[str] = "Contains modified Copernicus Sentinel data [2026]"
