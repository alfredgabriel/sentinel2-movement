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
    altitude_m: float | None = None
    altitude_min_m: float | None = None
    altitude_max_m: float | None = None
    contrail_points: tuple[tuple[float, float], tuple[float, float]] | None = None

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

        motion_cfg = cfg.get("motion", {})
        if "band_order" in motion_cfg:
            band_order = motion_cfg["band_order"]

        parallax_cfg = cfg.get("parallax", {})
        if "altitude_m" in parallax_cfg:
            altitude_m = float(parallax_cfg["altitude_m"])
        if "altitude_min_m" in parallax_cfg:
            altitude_min_m = float(parallax_cfg["altitude_min_m"])
        if "altitude_max_m" in parallax_cfg:
            altitude_max_m = float(parallax_cfg["altitude_max_m"])

        contrail_cfg = cfg.get("contrail", {})
        if "p_tail" in contrail_cfg and "p_head" in contrail_cfg:
            contrail_points = (
                (float(contrail_cfg["p_tail"][0]), float(contrail_cfg["p_tail"][1])),
                (float(contrail_cfg["p_head"][0]), float(contrail_cfg["p_head"][1])),
            )

    # 2. Apply CLI overrides
    if getattr(args, "contrail_points", None) is not None:
        y1, x1, y2, x2 = args.contrail_points
        contrail_points = ((y1, x1), (y2, x2))
    if args.date:
        date_str = args.date
    if args.bbox:
        bbox = tuple(args.bbox)
    if args.runway_heading is not None:
        runway_heading = args.runway_heading
    if getattr(args, "band_order", None):
        band_order = args.band_order
    if getattr(args, "altitude", None) is not None:
        altitude_m = args.altitude
    if getattr(args, "altitude_range", None) is not None:
        altitude_min_m, altitude_max_m = args.altitude_range
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
    ref_band = "blue" if band_order == "blue-first" else "red"
    if meta.get("transform") is not None and meta.get("crs") is not None:
        col_ref, row_ref = centroids[ref_band]
        lon_ref, lat_ref = pixel_to_wgs84(col_ref, row_ref, meta["transform"], meta["crs"])
        print(
            f"\nGeoreferenced {ref_band.capitalize()} centroid: lat {lat_ref:.6f}°, lon {lon_ref:.6f}° (WGS84, est. spatial uncertainty: ±15 m)"
        )

        if runway_heading is not None:
            runway_prox = calculate_runway_proximity(
                obj_lon=lon_ref,
                obj_lat=lat_ref,
                thr12_latlon=LEBB_RUNWAY_12_THR_WGS84,
                thr30_latlon=LEBB_RUNWAY_30_THR_WGS84,
                centroid_name=ref_band.capitalize(),
                uncertainty_m=15.0,
            )

    print("\nCalculating kinematics and uncertainty...")
    result = calculate_motion(
        red_centroid=centroids["red"],
        blue_centroid=centroids["blue"],
        green_centroid=centroids.get("green"),
        pixel_size_m=DEFAULT_PIXEL_SIZE_M,
        band_order=band_order,
        runway_heading_deg=runway_heading,
        runway_proximity=runway_prox,
        contrail_points=contrail_points,
    )

    if altitude_m is not None:
        from s2motion.parallax import correct_parallax

        mean_lat = (bbox[1] + bbox[3]) / 2.0
        parallax_res = correct_parallax(
            apparent_speed_mps=result.speed_mps,
            apparent_heading_deg=result.heading_deg,
            altitude_m=altitude_m,
            altitude_min_m=altitude_min_m,
            altitude_max_m=altitude_max_m,
            latitude_deg=mean_lat,
            band_order=band_order,
            delta_t_s=result.delta_t_s,
        )
        result = dataclasses.replace(result, parallax=parallax_res)

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
            f"Fetching Open-Meteo weather for ({w_lat:.3f}, {w_lon:.3f}) at {date_str} (product sensing time: {dt_val}, target overpass may differ by seconds)..."
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


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate satellite kinematics against external ADS-B state vectors."""
    from s2motion.adsb import (
        ADSBValidationCriteria,
        load_adsb_records,
        parse_timestamp,
        validate_adsb,
    )

    adsb_file = Path(args.adsb)
    if not adsb_file.exists():
        logger.error(f"ADS-B trajectory file not found: {adsb_file}")
        return 1

    # Default parameters
    target_lat = getattr(args, "target_lat", None)
    target_lon = getattr(args, "target_lon", None)
    sensing_time = getattr(args, "sensing_time", None)
    heading_deg = getattr(args, "heading", None)
    speed_kmh = getattr(args, "speed", None)
    speed_bounds = getattr(args, "speed_bounds", None)
    speed_min_kmh = speed_bounds[0] if speed_bounds else None
    speed_max_kmh = speed_bounds[1] if speed_bounds else None
    max_dist_m = getattr(args, "max_dist", None)
    time_window_s = getattr(args, "time_window", 60.0)
    heading_tol = getattr(args, "heading_tolerance", None)
    app_speed_mps = getattr(args, "apparent_speed_mps", None)
    app_hdg_deg = getattr(args, "apparent_heading", None)
    terrain_elev = getattr(args, "terrain_elevation", None)
    max_time_offset_s = getattr(args, "max_time_offset", None)

    # Load from config if available
    if args.config:
        cfg = load_toml_config(Path(args.config))
        val_cfg = cfg.get("validation", {})
        if target_lat is None:
            target_lat = val_cfg.get("target_lat")
        if target_lon is None:
            target_lon = val_cfg.get("target_lon")
        if sensing_time is None:
            sensing_time = val_cfg.get("sensing_time")
        if heading_deg is None:
            heading_deg = val_cfg.get("heading_deg")
        if speed_kmh is None:
            speed_kmh = val_cfg.get("speed_kmh")
        if speed_min_kmh is None:
            speed_min_kmh = val_cfg.get("speed_min_kmh")
        if speed_max_kmh is None:
            speed_max_kmh = val_cfg.get("speed_max_kmh")
        if max_dist_m is None:
            max_dist_m = val_cfg.get("max_distance_m", 1000.0)
        if time_window_s == 60.0:
            time_window_s = val_cfg.get("time_window_s", 60.0)
        if heading_tol is None:
            heading_tol = val_cfg.get("heading_tolerance_deg")
        if app_speed_mps is None:
            app_speed_mps = val_cfg.get("apparent_speed_mps")
        if app_hdg_deg is None:
            app_hdg_deg = val_cfg.get("apparent_heading_deg")
        if terrain_elev is None:
            terrain_elev = val_cfg.get("terrain_elevation_m", 0.0)
        if max_time_offset_s is None:
            max_time_offset_s = val_cfg.get("max_time_offset_s", 20.0)

    if target_lat is None or target_lon is None:
        logger.error(
            "Target coordinates (target_lat, target_lon) must be specified via --config or flags"
        )
        return 1

    if sensing_time is None:
        logger.error("Sensing time must be specified via --config or --sensing-time")
        return 1

    if heading_deg is None or speed_kmh is None:
        logger.error("Measured kinematics (heading, speed) must be specified via --config or flags")
        return 1

    if speed_min_kmh is None:
        speed_min_kmh = speed_kmh * 0.85
    if speed_max_kmh is None:
        speed_max_kmh = speed_kmh * 1.15
    if max_dist_m is None:
        max_dist_m = 1000.0
    if heading_tol is None:
        heading_tol = 14.0
    if terrain_elev is None:
        terrain_elev = 0.0
    if max_time_offset_s is None:
        max_time_offset_s = 20.0

    sensing_ts = parse_timestamp(sensing_time)
    criteria = ADSBValidationCriteria(
        max_distance_m=float(max_dist_m),
        time_window_s=float(time_window_s),
        max_time_offset_s=float(max_time_offset_s),
        heading_tolerance_deg=float(heading_tol),
        terrain_elevation_m=float(terrain_elev),
    )

    fmt_hint = getattr(args, "format", "auto")
    vectors = load_adsb_records(adsb_file, format_hint=fmt_hint)

    report = validate_adsb(
        vectors=vectors,
        target_lat=float(target_lat),
        target_lon=float(target_lon),
        sensing_timestamp=sensing_ts,
        measured_heading_red_first=float(heading_deg),
        speed_kmh_red_first=float(speed_kmh),
        speed_min_kmh_red_first=float(speed_min_kmh),
        speed_max_kmh_red_first=float(speed_max_kmh),
        criteria=criteria,
        apparent_speed_mps=float(app_speed_mps) if app_speed_mps is not None else None,
        apparent_heading_deg=float(app_hdg_deg) if app_hdg_deg is not None else None,
    )

    print(report.summary())
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
        "--band-order",
        choices=["red-first", "blue-first"],
        default="red-first",
        help="Temporal acquisition order across bands: 'red-first' (Red->Green->Blue, default) or 'blue-first' (Blue->Green->Red)",
    )
    p_measure.add_argument(
        "--weather",
        action="store_true",
        help="Fetch historical surface weather from Open-Meteo as environmental context (10m AGL)",
    )
    p_measure.add_argument(
        "--elevation",
        type=float,
        default=None,
        help="Airport elevation in meters above MSL (default: 42.0 m for Bilbao Airport)",
    )
    p_measure.add_argument(
        "--altitude",
        type=float,
        default=None,
        help="Estimated flight altitude in meters for stereoscopic parallax correction",
    )
    p_measure.add_argument(
        "--altitude-range",
        nargs=2,
        type=float,
        metavar=("MIN_ALT", "MAX_ALT"),
        default=None,
        help="Altitude interval [MIN_ALT, MAX_ALT] in meters for parallax sensitivity bounds",
    )
    p_measure.add_argument(
        "--contrail-points",
        nargs=4,
        type=float,
        metavar=("Y_TAIL", "X_TAIL", "Y_HEAD", "X_HEAD"),
        default=None,
        help="Two points defining contrail axis (tail to head in row, col) for heading comparison",
    )
    p_measure.add_argument("--out", help="Path to save annotated output figure")

    # Subcommand: validate
    p_val = subparsers.add_parser(
        "validate", help="Validate kinematics against external ADS-B state vectors"
    )
    p_val.add_argument(
        "--adsb",
        required=True,
        help="Path to ADS-B trajectory file (OpenSky CSV or ADS-B Exchange JSON)",
    )
    p_val.add_argument("--config", help="Path to scenario .toml configuration file")
    p_val.add_argument(
        "--format", choices=["auto", "opensky", "adsbx"], default="auto", help="File format hint"
    )
    p_val.add_argument("--target-lat", type=float, help="Target georeferenced latitude (degrees)")
    p_val.add_argument("--target-lon", type=float, help="Target georeferenced longitude (degrees)")
    p_val.add_argument(
        "--sensing-time", help="Satellite product sensing time (ISO string or epoch seconds)"
    )
    p_val.add_argument(
        "--heading", type=float, help="Measured heading in degrees clockwise from North"
    )
    p_val.add_argument("--speed", type=float, help="Measured ground speed in km/h")
    p_val.add_argument(
        "--speed-bounds",
        nargs=2,
        type=float,
        metavar=("MIN_KMH", "MAX_KMH"),
        help="Speed confidence interval [MIN, MAX] in km/h",
    )
    p_val.add_argument(
        "--max-dist",
        type=float,
        help="Maximum distance threshold in meters (default: 1000 m for approach, 2000 m for cruise)",
    )
    p_val.add_argument(
        "--time-window",
        type=float,
        default=60.0,
        help="Matching temporal window in seconds (default: 60.0 s)",
    )
    p_val.add_argument(
        "--heading-tolerance",
        type=float,
        help="Heading 2-sigma tolerance in degrees (default: 14.0 deg)",
    )
    p_val.add_argument(
        "--max-time-offset",
        type=float,
        default=20.0,
        help="Maximum CPA time offset in seconds for tile scan limit (default: 20.0 s)",
    )
    p_val.add_argument(
        "--terrain-elevation",
        type=float,
        default=0.0,
        help="Local terrain elevation in meters to compute geometric height AGL (default: 0.0 m)",
    )

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
    elif args.subcommand == "validate":
        return cmd_validate(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
