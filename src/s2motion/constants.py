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

# Total time elapsed from Red to Blue in seconds
DELTA_T_RED_BLUE_S: Final[float] = 1.005

# Theoretical relative position of green along the red-to-blue trajectory:
# (t_green - t_red) / (t_blue - t_red) = 0.478 / 1.005 ~= 0.4756
EXPECTED_GREEN_RELATIVE_FRACTION: Final[float] = 0.478 / DELTA_T_RED_BLUE_S

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

# Runway 12/30 heading in degrees clockwise from true North (~120 deg for 12, ~300 deg for 30)
BILBAO_RUNWAY_12_30_HEADING_DEG: Final[float] = 120.0

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
}
