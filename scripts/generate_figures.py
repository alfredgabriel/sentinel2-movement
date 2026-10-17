"""Script to generate all reproducible documentation and social figures for s2motion.

Generates:
  1. Multiband panels (B02, B03, B04, B08) with marked centroids.
  2. High-zoom RGB crops with pixel grid lines and subpixel centroids.
  3. Case 1 & Case 2 overview and detailed analysis figures.
  4. 4:5 social cards (1080x1350 px) in docs/img/social/.

Usage:
  python scripts/generate_figures.py [--lang es|en] [--online]
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np

# Ensure src is on sys.path when running script directly
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from s2motion.detect import detect_all_centroids  # noqa: E402
from s2motion.geo import calculate_runway_proximity, pixel_to_wgs84  # noqa: E402
from s2motion.measure import calculate_motion  # noqa: E402
from s2motion.parallax import correct_parallax  # noqa: E402
from s2motion.stac import get_scene_by_date, read_scene_bands  # noqa: E402
from s2motion.viz import (  # noqa: E402
    create_annotated_figure,
    create_multiband_panel,
    create_overview_figure,
    create_pixel_grid_zoom,
    create_social_card,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("generate_figures")


def load_case_data(
    case_date: str,
    data_dir: Path,
    online: bool = False,
    bbox: tuple[float, float, float, float] = (-2.945, 43.285, -2.875, 43.325),
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Load case band arrays and metadata either from offline npz or remote STAC."""
    npz_file = data_dir / f"loiu_{case_date}.npz"
    if not online and npz_file.exists():
        logger.info("Loading offline data fixture: %s", npz_file)
        archive = np.load(npz_file, allow_pickle=True)
        bands = {k: archive[k] for k in ("red", "green", "blue", "nir") if k in archive}
        transform = archive["transform"] if "transform" in archive else None
        crs = str(archive["crs"]) if "crs" in archive else None
        meta = {
            "date": str(archive["date"]) if "date" in archive else case_date,
            "scene_id": str(archive["scene_id"]) if "scene_id" in archive else "",
            "transform": transform,
            "crs": crs,
        }
        return bands, meta

    logger.info("Fetching remote STAC scene for date %s...", case_date)
    item = get_scene_by_date(case_date, bbox=bbox)
    bands, meta = read_scene_bands(item, assets=("red", "green", "blue", "nir"), bbox=bbox)
    return bands, meta


def run_case_1(
    data_dir: Path,
    img_dir: Path,
    lang: str = "es",
    online: bool = False,
) -> None:
    """Generate all figures for Case 1 (final approach to LEBB runway 12)."""
    logger.info("Generating Case 1 figures (2026-08-12)...")
    bands, meta = load_case_data("2026-08-12", data_dir, online=online)

    seeds = {"red": (66, 158), "green": (70, 160), "blue": (74, 162)}
    centroids = detect_all_centroids(bands, seeds)

    # Compute runway proximity if transform is available
    runway_prox = None
    if meta.get("transform") is not None and not np.all(meta["transform"] == 0):
        try:
            rx, ry = centroids["red"]
            lat_red, lon_red = pixel_to_wgs84(
                rx, ry, transform=meta["transform"], crs=meta.get("crs")
            )
            runway_prox = calculate_runway_proximity(lat_red, lon_red)
        except Exception as e:
            logger.debug("Runway proximity calculation skipped: %s", e)

    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids.get("green"),
        band_order="red-first",
        runway_heading_deg=116.7,
        runway_proximity=runway_prox,
    )

    # 1. Overview
    create_overview_figure(
        bands=bands,
        target_coords=centroids["green"],
        title="Sentinel-2 Scene Overview · Bilbao Airport (LEBB/BIO) · 2026-08-12",
        out_path=img_dir / "loiu_2026-08-12_overview.png",
    )

    # 2. Detail annotated
    create_annotated_figure(
        bands=bands,
        centroids=centroids,
        result=result,
        title="Sentinel-2 Motion Detection: Approach to Runway 12 (LEBB/BIO)",
        out_path=img_dir / "loiu_2026-08-12_measured.png",
    )

    # 3. Multiband panel (B02, B03, B04, B08)
    create_multiband_panel(
        bands=bands,
        centroids=centroids,
        title="Sentinel-2 Spectral Bands (B04, B08, B03, B02) · Approach Runway 12",
        out_path=img_dir / "loiu_2026-08-12_bands.png",
    )

    # 4. Pixel grid zoom
    create_pixel_grid_zoom(
        bands=bands,
        centroids=centroids,
        result=result,
        title="Subpixel Pixel Grid Resolution (10 m/px) · Approach Runway 12",
        out_path=img_dir / "loiu_2026-08-12_pixelgrid.png",
    )

    # 5. Social card 4:5
    social_dir = img_dir / "social"
    social_dir.mkdir(parents=True, exist_ok=True)
    create_social_card(
        case_id="case1",
        bands=bands,
        centroids=centroids,
        result=result,
        lang=lang,
        out_path=social_dir / "case1_approach_4x5.png",
    )


def run_case_2(
    data_dir: Path,
    img_dir: Path,
    lang: str = "es",
    online: bool = False,
) -> None:
    """Generate all figures for Case 2 (high-altitude cruise flight)."""
    logger.info("Generating Case 2 figures (2026-06-21)...")
    bands, meta = load_case_data("2026-06-21", data_dir, online=online)

    seeds = {"red": (212, 253), "green": (206, 239), "blue": (196, 224)}
    centroids = detect_all_centroids(bands, seeds)

    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids.get("green"),
        band_order="red-first",
    )

    # Stereoscopic parallax correction
    px = correct_parallax(
        apparent_speed_mps=result.speed_mps,
        apparent_heading_deg=result.heading_deg,
        altitude_m=10500.0,
        altitude_min_m=9000.0,
        altitude_max_m=12000.0,
        band_order="red-first",
        delta_t_s=result.delta_t_s,
    )
    result = dataclasses.replace(result, parallax=px)

    # 1. Overview
    create_overview_figure(
        bands=bands,
        target_coords=centroids["green"],
        title="Sentinel-2 Scene Overview · High-Altitude Cruise Target · 2026-06-21",
        out_path=img_dir / "loiu_2026-06-21_overview.png",
    )

    # 2. Detail annotated
    create_annotated_figure(
        bands=bands,
        centroids=centroids,
        result=result,
        title="Sentinel-2 Motion Detection: High-Altitude Airliner in Cruise (Parallax Corrected)",
        out_path=img_dir / "loiu_2026-06-21_measured.png",
    )

    # 3. Multiband panel (B02, B03, B04, B08)
    create_multiband_panel(
        bands=bands,
        centroids=centroids,
        title="Sentinel-2 Spectral Bands (B04, B08, B03, B02) · High-Altitude Cruise",
        out_path=img_dir / "loiu_2026-06-21_bands.png",
    )

    # 4. Pixel grid zoom
    create_pixel_grid_zoom(
        bands=bands,
        centroids=centroids,
        result=result,
        title="Subpixel Pixel Grid Resolution (10 m/px) · High-Altitude Cruise",
        out_path=img_dir / "loiu_2026-06-21_pixelgrid.png",
    )

    # 5. Social card 4:5
    social_dir = img_dir / "social"
    social_dir.mkdir(parents=True, exist_ok=True)
    create_social_card(
        case_id="case2",
        bands=bands,
        centroids=centroids,
        result=result,
        lang=lang,
        out_path=social_dir / "case2_cruise_4x5.png",
    )


def main() -> int:
    """CLI parser and figure generation orchestrator."""
    parser = argparse.ArgumentParser(
        description="Regenerate all figures for s2motion (overview, detail, multiband, pixelgrid, social 4:5)"
    )
    parser.add_argument(
        "--lang",
        choices=["es", "en"],
        default="es",
        help="Language for social cards text ('es' or 'en', default: 'es')",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Force remote STAC API query instead of offline fixtures in examples/data/",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "examples" / "data",
        help="Directory containing offline .npz data fixtures",
    )
    parser.add_argument(
        "--img-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "img",
        help="Output directory for generated figures",
    )

    args = parser.parse_args()
    args.img_dir.mkdir(parents=True, exist_ok=True)

    run_case_1(data_dir=args.data_dir, img_dir=args.img_dir, lang=args.lang, online=args.online)
    run_case_2(data_dir=args.data_dir, img_dir=args.img_dir, lang=args.lang, online=args.online)

    logger.info(
        "All figures successfully generated in %s and %s", args.img_dir, args.img_dir / "social"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
