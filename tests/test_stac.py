"""Tests for STAC queries and COG window extraction."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from s2motion.constants import BILBAO_AIRPORT_BBOX
from s2motion.stac import get_scene_by_date, read_scene_bands, search_scenes


def test_read_scene_bands_shape_harmonization() -> None:
    """Verify that multi-band window reading trims arrays to identical dimensions."""
    mock_item = MagicMock()
    mock_item.id = "S2A_TEST"
    mock_item.properties = {"datetime": "2026-08-12T11:00:00Z", "eo:cloud_cover": 2.5}

    # Simulate slight shape discrepancies across bands (e.g. 100x102 vs 101x100)
    def fake_read_window(item, asset, bbox):
        if asset == "red":
            return np.ones((100, 102), dtype=np.float32)
        elif asset == "green":
            return np.ones((101, 100), dtype=np.float32)
        else:
            return np.ones((102, 103), dtype=np.float32)

    with patch("s2motion.stac.read_band_window", side_effect=fake_read_window):
        bands, meta = read_scene_bands(mock_item, assets=("red", "green", "blue"))

    assert bands["red"].shape == (100, 100)
    assert bands["green"].shape == (100, 100)
    assert bands["blue"].shape == (100, 100)
    assert meta["date"] == "2026-08-12"
    assert meta["cloud_cover"] == 2.5


@pytest.mark.network
def test_search_scenes_network() -> None:
    """Verify live STAC search against AWS Earth Search endpoint."""
    items = search_scenes(
        bbox=BILBAO_AIRPORT_BBOX,
        start_date="2026-08-01",
        end_date="2026-08-15",
        max_cloud=15.0,
    )
    assert len(items) > 0


@pytest.mark.network
def test_get_scene_by_date_network() -> None:
    """Verify live scene retrieval for 2026-08-12."""
    item = get_scene_by_date("2026-08-12", bbox=BILBAO_AIRPORT_BBOX)
    assert "2026-08-12" in item.properties["datetime"]
    assert "red" in item.assets
    assert "green" in item.assets
    assert "blue" in item.assets
