"""STAC catalog search and remote COG window reading for Sentinel-2."""

import logging
from typing import Any

import numpy as np
import rasterio
from pystac import Item, ItemCollection
from pystac_client import Client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from s2motion.constants import (
    BILBAO_AIRPORT_BBOX,
    DEFAULT_COLLECTION,
    DEFAULT_STAC_URL,
    STAC_ASSET_MAP,
)

logger = logging.getLogger(__name__)


def search_scenes(
    bbox: tuple[float, float, float, float] = BILBAO_AIRPORT_BBOX,
    start_date: str = "2025-01-01",
    end_date: str = "2026-09-30",
    max_cloud: float = 10.0,
    stac_url: str = DEFAULT_STAC_URL,
    collection: str = DEFAULT_COLLECTION,
) -> ItemCollection:
    """Search STAC items matching bounding box, date range, and maximum cloud cover.

    Args:
        bbox: Bounding box in WGS84 (lon_min, lat_min, lon_max, lat_max).
        start_date: Start date string (YYYY-MM-DD).
        end_date: End date string (YYYY-MM-DD).
        max_cloud: Maximum cloud cover percentage (0-100).
        stac_url: STAC API endpoint URL.
        collection: STAC collection name.

    Returns:
        pystac ItemCollection of matching scenes.
    """
    logger.info(
        "Searching STAC scenes in %s between %s and %s (cloud < %s %%)",
        collection,
        start_date,
        end_date,
        max_cloud,
    )
    catalog = Client.open(stac_url)
    search = catalog.search(
        collections=[collection],
        bbox=bbox,
        datetime=f"{start_date}/{end_date}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    items = search.item_collection()
    logger.info("Found %d matching scenes", len(items))
    return items


def get_scene_by_date(
    date_str: str,
    bbox: tuple[float, float, float, float] = BILBAO_AIRPORT_BBOX,
    stac_url: str = DEFAULT_STAC_URL,
    collection: str = DEFAULT_COLLECTION,
) -> Item:
    """Retrieve a single Sentinel-2 STAC item matching a specific calendar date.

    Args:
        date_str: Date string in YYYY-MM-DD format.
        bbox: Bounding box in WGS84.
        stac_url: STAC API URL.
        collection: STAC collection.

    Returns:
        Matching pystac Item.

    Raises:
        ValueError: If no scenes are found for the given date and bbox.
    """
    logger.info("Retrieving scene for date %s", date_str)
    catalog = Client.open(stac_url)
    items = catalog.search(
        collections=[collection],
        bbox=bbox,
        datetime=f"{date_str}T00:00:00Z/{date_str}T23:59:59Z",
    ).item_collection()

    if not items:
        raise ValueError(f"No Sentinel-2 scene found for date {date_str} and bbox {bbox}")
    return items[0]


def read_band_window(
    item: Item,
    asset_name: str,
    bbox: tuple[float, float, float, float] = BILBAO_AIRPORT_BBOX,
) -> np.ndarray:
    """Read a spatial window of a single band from a remote Cloud-Optimized GeoTIFF (COG).

    Transforms the WGS84 bounding box into the native scene CRS and reads only
    the requested sub-window without downloading the full tile.

    Args:
        item: STAC Item containing asset metadata and remote URLs.
        asset_name: Asset identifier (e.g. 'red', 'green', 'blue', 'nir').
        bbox: Target bounding box in WGS84 (lon_min, lat_min, lon_max, lat_max).

    Returns:
        2D float32 array of pixel values.

    Raises:
        KeyError: If asset_name is not present in item assets.
    """
    asset_key = STAC_ASSET_MAP.get(asset_name, asset_name)
    if asset_key not in item.assets:
        raise KeyError(
            f"Asset '{asset_key}' not found in item {item.id}. Available: {list(item.assets.keys())}"
        )

    href = item.assets[asset_key].href
    logger.debug("Reading window from %s (asset: %s)", href, asset_key)

    with rasterio.open(href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(*bounds, transform=src.transform)
        data = src.read(1, window=win).astype(np.float32)
        return data


def read_scene_bands(
    item: Item,
    assets: tuple[str, ...] = ("red", "green", "blue"),
    bbox: tuple[float, float, float, float] = BILBAO_AIRPORT_BBOX,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Read spatial windows for multiple bands from a STAC item and crop to common dimensions.

    Args:
        item: STAC Item.
        assets: Tuple of asset names to read.
        bbox: Target bounding box in WGS84.

    Returns:
        Tuple of:
          - Dict mapping asset name to cropped 2D float32 array
          - Metadata dict containing scene date, item id, and cloud cover
    """
    raw_bands = {asset: read_band_window(item, asset, bbox=bbox) for asset in assets}

    # Harmonize shapes to minimum common height and width
    min_h = min(arr.shape[0] for arr in raw_bands.values())
    min_w = min(arr.shape[1] for arr in raw_bands.values())

    bands = {asset: arr[:min_h, :min_w] for asset, arr in raw_bands.items()}
    meta = {
        "id": item.id,
        "datetime": item.properties.get("datetime", ""),
        "date": item.properties.get("datetime", "")[:10],
        "cloud_cover": item.properties.get("eo:cloud_cover"),
        "shape": (min_h, min_w),
    }
    return bands, meta
