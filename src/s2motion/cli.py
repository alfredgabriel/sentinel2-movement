"""Command-line interface (CLI) for s2motion.

Subcommands:
  - crops:   Search STAC scenes and generate cropped RGB PNG previews.
  - view:    Open interactive matplotlib viewer to inspect pixels and determine seeds.
  - measure: Run subpixel centroid detection, kinematics measurement, and figure export.
"""

import argparse
import dataclasses
import logging
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from s2motion.constants import (
    BILBAO_AIRPORT_BBOX,
    DEFAULT_PIXEL_SIZE_M,
    LEBB_RUNWAY_12_THR_WGS84,
    LEBB_RUNWAY_30_THR_WGS84,
)
from s2motion.detect import detect_all_centroids
from s2motion.geo import calculate_runway_proximity, pixel_to_wgs84
from s2motion.measure import calculate_motion
from s2motion.stac import get_scene_by_date, read_scene_bands, search_scenes
from s2motion.viz import create_annotated_figure, create_rgb_composite, show_interactive_viewer
from s2motion.weather import compute_aerodynamics, fetch_historical_weather

logger = logging.getLogger("s2motion")


def load_toml_config(config_path: Path) -> dict[str, Any]:
    """Parse a TOML configuration file."""
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def cmd_crops(args: argparse.Namespace) -> int:
    """Execute 'crops' subcommand: search STAC and save preview RGB images."""
    bbox = tuple(args.bbox) if args.bbox else BILBAO_AIRPORT_BBOX
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = search_scenes(
        bbox=bbox,
        start_date=args.start,
        end_date=args.end,
        max_cloud=args.max_cloud,
    )
    print(f"Found {len(items)} scenes with cloud cover < {args.max_cloud}%")

    for item in items:
        date_str = item.properties.get("datetime", "")[:10]
        out_file = out_dir / f"loiu_{date_str}.png"
        if out_file.exists() and not args.force:
            logger.info("Skipping existing crop: %s", out_file)
            continue

        try:
            bands, _ = read_scene_bands(item, assets=("red", "green", "blue"), bbox=bbox)
            rgb = create_rgb_composite(bands)
            if args.scale > 1:
                rgb = np.kron(rgb, np.ones((args.scale, args.scale, 1), dtype=np.float32))
            plt.imsave(out_file, rgb)
            print(f"Saved: {out_file} (date: {date_str})")
        except Exception as err:
            logger.error("Failed to process scene %s: %s", item.id, err)

    return 0


def cmd_view(args: argparse.Namespace) -> int:
    """Execute 'view' subcommand: interactive inspector for determining seeds."""
    date_str: str | None = None
    bbox = BILBAO_AIRPORT_BBOX

    if args.config:
        cfg = load_toml_config(Path(args.config))
        scene_cfg = cfg.get("scene", {})
        date_str = scene_cfg.get("date")
        if "bbox" in scene_cfg:
            bbox = tuple(scene_cfg["bbox"])
    if args.date:
        date_str = args.date
    if args.bbox:
        bbox = tuple(args.bbox)

    if not date_str:
        logger.error("Date must be provided either via --config or --date")
        return 1

    item = get_scene_by_date(date_str, bbox=bbox)
    bands, _ = read_scene_bands(item, assets=("red", "green", "blue"), bbox=bbox)
    rgb = create_rgb_composite(bands)
    show_interactive_viewer(rgb, title=f"Sentinel-2 Loiu Crop - {date_str}")
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    """Execute 'measure' subcommand: centroid detection, kinematics, and figure generation."""
    date_str: str | None = None
    bbox = BILBAO_AIRPORT_BBOX
    runway_heading: float | None = None
    seeds: dict[str, tuple[float, float]] = {}
    kernel_size = 9
    radius = 3
    threshold_ratio = 0.5
    out_fig: Path | None = None
    title = "Sentinel-2 Moving Object Analysis"

    # 1. Load configuration file if specified
    weather_enabled = False
    weather_elevation_m = 42.0
    weather_lat: float | None = None
    weather_lon: float | None = None

    if args.config:
        cfg = load_toml_config(Path(args.config))
        scene_cfg = cfg.get("scene", {})
        date_str = scene_cfg.get("date")
        if "bbox" in scene_cfg:
            bbox = tuple(scene_cfg["bbox"])
        if "runway_heading" in scene_cfg:
            runway_heading = float(scene_cfg["runway_heading"])
        if "description" in scene_cfg:
            title = f"{scene_cfg['description']} ({date_str})"

        for b_name, coords in cfg.get("seeds", {}).items():
            seeds[b_name] = (float(coords[0]), float(coords[1]))

        det_cfg = cfg.get("detection", {})
        kernel_size = det_cfg.get("median_kernel", kernel_size)
        radius = det_cfg.get("radius", radius)
        threshold_ratio = det_cfg.get("threshold_ratio", threshold_ratio)

        weather_cfg = cfg.get("weather", {})
        weather_enabled = weather_cfg.get("enabled", weather_enabled)
        weather_elevation_m = weather_cfg.get("elevation_m", weather_elevation_m)
        weather_lat = weather_cfg.get("latitude", weather_lat)
        weather_lon = weather_cfg.get("longitude", weather_lon)

        out_cfg = cfg.get("output", {})
        if "figure" in out_cfg:
            out_fig = Path(out_cfg["figure"])

    # 2. Apply CLI overrides
    if args.date:
        date_str = args.date
    if args.bbox:
        bbox = tuple(args.bbox)
    if args.runway_heading is not None:
        runway_heading = args.runway_heading
    if getattr(args, "weather", False):
        weather_enabled = True
    if getattr(args, "elevation", None) is not None:
        weather_elevation_m = args.elevation
    if args.out:
        out_fig = Path(args.out)

    if not date_str:
        logger.error("Date must be provided either via --config or --date")
        return 1

    if "red" not in seeds or "blue" not in seeds:
        logger.error("Seeds must contain at least 'red' and 'blue' (e.g. in config or via seeds)")
        return 1

    print(f"Reading Sentinel-2 scene for date: {date_str} ...")
    item = get_scene_by_date(date_str, bbox=bbox)
    bands, meta = read_scene_bands(item, assets=("red", "green", "blue"), bbox=bbox)

    print("\nDetecting subpixel centroids...")
    centroids = detect_all_centroids(
        bands=bands,
        seeds=seeds,
        kernel_size=kernel_size,
        radius=radius,
        threshold_ratio=threshold_ratio,
    )
    for b_name, (cx, cy) in centroids.items():
        print(
            f"  - {b_name.capitalize():6s} (initial: {seeds[b_name]}): subpixel centroid = ({cx:.2f}, {cy:.2f})"
        )

    # 3. Georeference centroids to WGS84 and compute runway proximity if applicable
    runway_prox = None
    if meta.get("transform") is not None and meta.get("crs") is not None:
        col_r, row_r = centroids["red"]
        lon_r, lat_r = pixel_to_wgs84(col_r, row_r, meta["transform"], meta["crs"])
        print(f"\nGeoreferenced Red centroid: lat {lat_r:.6f}°, lon {lon_r:.6f}° (WGS84)")

        if runway_heading is not None:
            runway_prox = calculate_runway_proximity(
                obj_lon=lon_r,
                obj_lat=lat_r,
                thr12_latlon=LEBB_RUNWAY_12_THR_WGS84,
                thr30_latlon=LEBB_RUNWAY_30_THR_WGS84,
            )

    print("\nCalculating kinematics and uncertainty...")
    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids.get("green"),
        pixel_size_m=DEFAULT_PIXEL_SIZE_M,
        runway_heading_deg=runway_heading,
        runway_proximity=runway_prox,
    )

    if weather_enabled:
        w_lat = weather_lat if weather_lat is not None else (bbox[1] + bbox[3]) / 2.0
        w_lon = weather_lon if weather_lon is not None else (bbox[0] + bbox[2]) / 2.0
        hour_utc = 11
        dt_val = item.properties.get("datetime")
        if dt_val and len(dt_val) >= 13 and "T" in dt_val:
            try:
                hour_utc = int(dt_val.split("T")[1][:2])
            except ValueError:
                pass

        print(
            f"Fetching Open-Meteo weather for ({w_lat:.3f}, {w_lon:.3f}) at {date_str} (scene time: {dt_val})..."
        )
        try:
            weather_obs = fetch_historical_weather(
                latitude=w_lat,
                longitude=w_lon,
                date_str=date_str,
                hour_utc=hour_utc,
                datetime_str=dt_val,
            )
            aero = compute_aerodynamics(
                ground_speed_mps=result.speed_mps,
                heading_deg=result.heading_deg,
                weather=weather_obs,
                elevation_m=weather_elevation_m,
            )
            result = dataclasses.replace(result, aero=aero)
        except Exception as err:
            logger.warning("Could not fetch or compute weather aerodynamics: %s", err)

    print("\n" + result.summary() + "\n")

    if out_fig:
        create_annotated_figure(
            bands=bands,
            centroids=centroids,
            result=result,
            title=title,
            out_path=out_fig,
        )
        print(f"Saved measurement figure: {out_fig}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the command line parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="s2motion",
        description="Detection and velocity measurement of moving objects with Sentinel-2 inter-band parallax.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: crops
    p_crops = subparsers.add_parser(
        "crops", help="Search STAC scenes and generate RGB preview PNGs"
    )
    p_crops.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        help="Bounding box in EPSG:4326",
    )
    p_crops.add_argument("--start", default="2025-01-01", help="Start date (YYYY-MM-DD)")
    p_crops.add_argument("--end", default="2026-09-30", help="End date (YYYY-MM-DD)")
    p_crops.add_argument("--max-cloud", type=float, default=10.0, help="Max cloud cover percentage")
    p_crops.add_argument(
        "--scale", type=int, default=1, help="Enlargement factor without smoothing (default: 1)"
    )
    p_crops.add_argument("--out", default="outputs", help="Output directory (default: outputs/)")
    p_crops.add_argument("--force", action="store_true", help="Overwrite existing PNG files")

    # Subcommand: view
    p_view = subparsers.add_parser("view", help="Interactive pixel coordinate inspector")
    p_view.add_argument("--config", help="Path to scenario .toml configuration file")
    p_view.add_argument("--date", help="Scene date (YYYY-MM-DD)")
    p_view.add_argument(
        "--bbox", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT")
    )

    # Subcommand: measure
    p_measure = subparsers.add_parser("measure", help="Measure velocity, heading, and coherence")
    p_measure.add_argument("--config", help="Path to scenario .toml configuration file")
    p_measure.add_argument("--date", help="Scene date (YYYY-MM-DD)")
    p_measure.add_argument(
        "--bbox", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT")
    )
    p_measure.add_argument(
        "--runway-heading", type=float, help="Runway heading in degrees clockwise from North"
    )
    p_measure.add_argument(
        "--weather",
        action="store_true",
        help="Fetch historical weather from Open-Meteo and compute aerodynamic telemetry (TAS, headwind, density altitude)",
    )
    p_measure.add_argument(
        "--elevation",
        type=float,
        default=None,
        help="Airport elevation in meters above MSL (default: 42.0 m for Bilbao Airport)",
    )
    p_measure.add_argument("--out", help="Path to save annotated output figure")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.subcommand == "crops":
        return cmd_crops(args)
    elif args.subcommand == "view":
        return cmd_view(args)
    elif args.subcommand == "measure":
        return cmd_measure(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
