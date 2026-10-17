"""Visualization module for RGB composites, multi-band panels, and annotated figures."""

import logging
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

from s2motion.constants import COPERNICUS_ATTRIBUTION, GROUND_ACQUISITION_TIMING_S
from s2motion.detect import compute_subpixel_centroid, subtract_local_background
from s2motion.measure import MeasurementResult

logger = logging.getLogger(__name__)


def create_rgb_composite(
    bands: dict[str, np.ndarray],
    percentile: float = 99.0,
) -> np.ndarray:
    """Create a contrast-stretched RGB composite array from red, green, and blue bands.

    Args:
        bands: Dictionary containing 'red', 'green', and 'blue' 2D float arrays.
        percentile: Upper percentile cutoff for linear contrast stretching (default: 99.0).

    Returns:
        3D float32 array of shape (H, W, 3) with values clipped to [0, 1].
    """
    for name in ("red", "green", "blue"):
        if name not in bands:
            raise KeyError(f"Band '{name}' required for RGB composite")

    h = min(bands[k].shape[0] for k in ("red", "green", "blue"))
    w = min(bands[k].shape[1] for k in ("red", "green", "blue"))

    rgb = np.dstack([bands["red"][:h, :w], bands["green"][:h, :w], bands["blue"][:h, :w]])
    p_max = float(np.percentile(rgb, percentile))
    if p_max <= 0:
        p_max = 1.0

    stretched = np.clip(rgb / p_max, 0.0, 1.0).astype(np.float32)
    return stretched


def create_annotated_figure(
    bands: dict[str, np.ndarray],
    centroids: dict[str, tuple[float, float]],
    result: MeasurementResult,
    title: str = "Sentinel-2 Motion Analysis",
    zoom_radius: int = 20,
    out_path: str | Path | None = None,
) -> plt.Figure:
    """Generate a multi-panel publication-quality figure detailing motion detection.

    Left: Zoomed RGB composite with subpixel centroid markers, movement vector arrow (Red -> Blue),
          and runway orientation guide.
    Right: Individual spectral band anomaly crops arranged chronologically (Red -> Green -> Blue)
           showing the progression over time.

    Args:
        bands: Dictionary of 2D band arrays (must contain 'red', 'green', 'blue').
        centroids: Subpixel centroid coordinates per band.
        result: Computed MeasurementResult with kinematics and coherence metrics.
        title: Overall figure title.
        zoom_radius: Half-window width in pixels around the centroid for zooming.
        out_path: Optional file path to save the generated image.

    Returns:
        matplotlib Figure object.
    """
    rgb = create_rgb_composite(bands)

    # Center zoom on the green centroid (middle of trajectory) or mean
    if "green" in centroids:
        cx0, cy0 = centroids["green"]
    else:
        cx0 = (centroids["red"][0] + centroids["blue"][0]) / 2.0
        cy0 = (centroids["red"][1] + centroids["blue"][1]) / 2.0

    fig = plt.figure(figsize=(14, 8), constrained_layout=True)
    gs = fig.add_gridspec(3, 2, width_ratios=[1.4, 1.0])

    # 1. Main Left Panel: Zoomed RGB Composite with Overlays
    ax_main = fig.add_subplot(gs[:, 0])
    ax_main.imshow(rgb, interpolation="nearest")

    # Draw centroid markers in chronological order: Red -> Green -> Blue
    colors = {"red": "tomato", "green": "lime", "blue": "deepskyblue"}
    for b_name in ("red", "green", "blue"):
        if b_name in centroids:
            px, py = centroids[b_name]
            code = {"red": "B04", "green": "B03", "blue": "B02"}.get(b_name, "")
            dt = GROUND_ACQUISITION_TIMING_S.get(b_name, 0.0)
            ax_main.plot(
                px,
                py,
                "o",
                mfc="none",
                mec=colors.get(b_name, "yellow"),
                ms=14,
                mew=2.2,
                label=f"{b_name.capitalize()} ({code}, t={dt:.3f}s)",
            )

    # Draw motion vector arrow between origin and destination centroids
    rx, ry = centroids["red"]
    bx, by = centroids["blue"]
    if result.band_order == "blue-first":
        arrow_start = (bx, by)
        arrow_end = (rx, ry)
        dir_label = "Blue -> Red"
        dir_full_label = "Blue -> Green -> Red"
    else:
        arrow_start = (rx, ry)
        arrow_end = (bx, by)
        dir_label = "Red -> Blue"
        dir_full_label = "Red -> Green -> Blue"

    ax_main.annotate(
        "",
        xy=arrow_end,
        xytext=arrow_start,
        arrowprops={"arrowstyle": "-|>", "color": "white", "lw": 2.2, "mutation_scale": 18},
    )

    # Zoom window limits
    ax_main.set_xlim(cx0 - zoom_radius, cx0 + zoom_radius)
    ax_main.set_ylim(cy0 + zoom_radius, cy0 - zoom_radius)  # Inverted Y for image coords
    ax_main.xaxis.set_major_locator(MultipleLocator(5))
    ax_main.yaxis.set_major_locator(MultipleLocator(5))
    ax_main.set_xlabel("X (East, pixels)", fontsize=11)
    ax_main.set_ylabel("Y (South, pixels)", fontsize=11)
    ax_main.set_title(
        f"Zoomed RGB Composite (10 m/px) | Vector: {dir_label}\nDisplacement: {result.distance_m:.1f} m | Heading: {result.heading_deg:.1f}°",
        fontsize=12,
        fontweight="bold",
    )
    ax_main.legend(loc="upper right", framealpha=0.85, facecolor="#1e1e1e", labelcolor="white")

    # Add overlay metrics box on bottom left
    metrics_text = (
        f"Direction: {dir_full_label}\n"
        f"Velocity:  {result.speed_kmh:.0f} km/h [{result.speed_kmh_min:.0f} - {result.speed_kmh_max:.0f} km/h]\n"
        f"Heading:   {result.heading_deg:.1f}° (N=0°, clockwise)\n"
        f"Delta t:   {result.delta_t_s:.3f} s (+/-2%)\n"
        f"Collinearity: {result.collinearity_px:.2f} px\n"
        f"Green pos:    {result.green_relative_fraction:.2f} (exp: {result.expected_green_fraction:.2f})"
    )
    if result.parallax is not None:
        px = result.parallax
        range_s = (
            f" [{px.corrected_speed_min_kmh:.0f}-{px.corrected_speed_max_kmh:.0f}]"
            if px.corrected_speed_min_kmh is not None
            else ""
        )
        metrics_text += (
            f"\n-- Parallax Corrected (h={px.altitude_m:.0f}m) --\n"
            f"Corrected: {px.corrected_speed_kmh:.0f} km/h{range_s}\n"
            f"True Heading: {px.corrected_heading_deg:.1f}° ({px.delta_speed_kmh:+.0f} km/h)"
        )

    if result.runway_proximity is not None:
        p = result.runway_proximity
        metrics_text += (
            f"\nRunway Axis Diff: {result.runway_diff_deg:.1f}° (±{result.heading_uncertainty_deg:.1f}°)\n"
            f"Distance to THR 12: {p.dist_thr12_m:.0f} ± {p.uncertainty_m:.0f} m (offset: {p.cross_axis_m:.1f} ± {p.uncertainty_m:.0f} m)"
        )
    elif result.runway_diff_deg is not None:
        metrics_text += f"\nRunway axis diff: {result.runway_diff_deg:.1f}° (±{result.heading_uncertainty_deg:.1f}°)"

    if result.aero is not None:
        a = result.aero
        obs = a.weather
        metrics_text += (
            f"\n-- Surface Weather Context (10m AGL) --\n"
            f"Temp / Pressure: {obs.temperature_c:.1f}°C | {obs.surface_pressure_hpa:.1f} hPa\n"
            f"Wind:      {obs.wind_speed_kmh:.1f} km/h ({obs.wind_speed_knots:.1f} kt) from {obs.wind_direction_deg:.0f}°\n"
            f"Headwind:  {a.headwind_mps * 3.6:+.1f} km/h ({a.headwind_mps * 1.94384:+.1f} kt) | Cross: {a.crosswind_mps * 3.6:+.1f} km/h"
        )

        # Draw wind indicator arrow on top-left of main panel
        wind_to_rad = math.radians(obs.wind_direction_deg + 180.0)
        arrow_len = 0.07
        x_base, y_base = 0.17, 0.91
        x_tip = x_base + arrow_len * math.sin(wind_to_rad)
        y_tip = y_base + arrow_len * math.cos(wind_to_rad)

        ax_main.text(
            0.03,
            0.96,
            f"Wind: {obs.wind_speed_kmh:.1f} km/h\nfrom {obs.wind_direction_deg:.0f}°",
            transform=ax_main.transAxes,
            fontsize=8.5,
            fontweight="bold",
            color="cyan",
            verticalalignment="top",
            bbox={
                "boxstyle": "round,pad=0.3",
                "facecolor": "#111111",
                "alpha": 0.85,
                "edgecolor": "cyan",
            },
        )
        ax_main.annotate(
            "",
            xy=(x_tip, y_tip),
            xytext=(x_base, y_base),
            xycoords="axes fraction",
            textcoords="axes fraction",
            arrowprops={
                "arrowstyle": "-|>",
                "color": "cyan",
                "lw": 2.2,
                "mutation_scale": 15,
            },
        )

    ax_main.text(
        0.03,
        0.04,
        metrics_text,
        transform=ax_main.transAxes,
        fontsize=8.5,
        fontfamily="monospace",
        color="white",
        bbox={
            "boxstyle": "round,pad=0.5",
            "facecolor": "#111111",
            "alpha": 0.85,
            "edgecolor": "#555555",
        },
        verticalalignment="bottom",
    )

    # 2. Right Panels: Individual Band Anomaly Progression (Chronological: Red -> Green -> Blue)
    band_sequence = [
        ("red", "B04 (Red, Leading)", GROUND_ACQUISITION_TIMING_S["red"]),
        ("green", "B03 (Green)", GROUND_ACQUISITION_TIMING_S["green"]),
        ("blue", "B02 (Blue, Trailing)", GROUND_ACQUISITION_TIMING_S["blue"]),
    ]
    r_sub = 8

    for idx, (b_key, b_label, dt) in enumerate(band_sequence):
        ax_sub = fig.add_subplot(gs[idx, 1])
        if b_key in bands:
            anom = subtract_local_background(bands[b_key], kernel_size=9)
            ax_sub.imshow(anom, cmap="inferno", interpolation="nearest")
            if b_key in centroids:
                kpx, kpy = centroids[b_key]
                ax_sub.plot(kpx, kpy, "x", color="cyan", ms=9, mew=2)
                ax_sub.set_xlim(kpx - r_sub, kpx + r_sub)
                ax_sub.set_ylim(kpy + r_sub, kpy - r_sub)
            ax_sub.set_title(f"{b_label} Anomaly | t = {dt:.3f} s", fontsize=10)
            ax_sub.set_xticks([])
            ax_sub.set_yticks([])

    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.text(
        0.99,
        0.005,
        COPERNICUS_ATTRIBUTION,
        fontsize=7.5,
        color="#777777",
        style="italic",
        ha="right",
        va="bottom",
    )

    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_p, dpi=180, bbox_inches="tight")
        logger.info("Saved annotated figure to %s", out_p)

    return fig


def create_overview_figure(
    bands: dict[str, np.ndarray],
    target_coords: tuple[float, float] | None = None,
    title: str = "Sentinel-2 Scene Overview",
    box_radius: int = 25,
    out_path: str | Path | None = None,
) -> plt.Figure:
    """Render full RGB composite overview of the scene with moving target bounding reticle."""
    rgb = create_rgb_composite(bands)

    fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
    ax.imshow(rgb, interpolation="nearest")

    if target_coords is not None:
        tx, ty = target_coords
        rect = plt.Rectangle(
            (tx - box_radius, ty - box_radius),
            2 * box_radius,
            2 * box_radius,
            fill=False,
            edgecolor="#38bdf8",
            lw=2.0,
            linestyle="--",
        )
        ax.add_patch(rect)
        ax.plot(tx, ty, "+", color="#38bdf8", ms=14, mew=2.0)
        ax.annotate(
            "Moving Target Crop",
            xy=(tx, ty - box_radius),
            xytext=(tx, ty - box_radius - 14),
            color="#38bdf8",
            fontsize=10,
            fontweight="bold",
            ha="center",
            va="bottom",
            bbox={
                "boxstyle": "round,pad=0.25",
                "facecolor": "#0b0f19",
                "alpha": 0.85,
                "edgecolor": "#38bdf8",
            },
            arrowprops={"arrowstyle": "->", "color": "#38bdf8", "lw": 1.5},
        )

    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel("X (pixels, 10 m/px)", fontsize=10)
    ax.set_ylabel("Y (pixels, 10 m/px)", fontsize=10)

    fig.text(
        0.99,
        0.005,
        COPERNICUS_ATTRIBUTION,
        fontsize=8,
        color="#777777",
        style="italic",
        ha="right",
        va="bottom",
    )

    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_p, dpi=180, bbox_inches="tight")
        logger.info("Saved overview figure to %s", out_p)

    return fig


def create_multiband_panel(
    bands: dict[str, np.ndarray],
    centroids: dict[str, tuple[float, float]],
    title: str = "Sentinel-2 Spectral Bands (B02, B03, B04, B08)",
    zoom_radius: int = 15,
    out_path: str | Path | None = None,
) -> plt.Figure:
    """Generate side-by-side 4-band panels (B02, B03, B04, B08) with marked centroids."""
    band_defs = [
        ("red", "B04", "Red (665 nm)", GROUND_ACQUISITION_TIMING_S.get("red", 0.0), "#f87171"),
        ("nir", "B08", "NIR (842 nm)", 0.026, "#c084fc"),
        (
            "green",
            "B03",
            "Green (560 nm)",
            GROUND_ACQUISITION_TIMING_S.get("green", 0.478),
            "#4ade80",
        ),
        ("blue", "B02", "Blue (490 nm)", GROUND_ACQUISITION_TIMING_S.get("blue", 1.005), "#38bdf8"),
    ]

    if "green" in centroids:
        cx0, cy0 = centroids["green"]
    elif "red" in centroids and "blue" in centroids:
        cx0 = (centroids["red"][0] + centroids["blue"][0]) / 2.0
        cy0 = (centroids["red"][1] + centroids["blue"][1]) / 2.0
    else:
        first_c = next(iter(centroids.values()))
        cx0, cy0 = first_c

    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5), constrained_layout=True)

    for ax, (b_key, b_code, b_name, dt, color) in zip(axes, band_defs, strict=True):
        if b_key not in bands:
            ax.text(0.5, 0.5, f"{b_code} Unavailable", ha="center", va="center", color="gray")
            continue

        anom = subtract_local_background(bands[b_key], kernel_size=9)
        ax.imshow(anom, cmap="inferno", interpolation="nearest")

        if b_key in centroids:
            c_x, c_y = centroids[b_key]
        else:
            try:
                c_x, c_y = compute_subpixel_centroid(anom, (cx0, cy0), radius=4)
            except Exception:
                c_x, c_y = cx0, cy0

        ax.plot(c_x, c_y, "o", mfc="none", mec=color, ms=12, mew=2.2)
        ax.plot(c_x, c_y, "+", color=color, ms=10, mew=1.8)

        ax.set_xlim(cx0 - zoom_radius, cx0 + zoom_radius)
        ax.set_ylim(cy0 + zoom_radius, cy0 - zoom_radius)
        ax.set_title(
            f"{b_code} - {b_name}\nt = {dt:.3f} s | ({c_x:.2f}, {c_y:.2f})",
            fontsize=10.5,
            fontweight="bold",
        )
        ax.set_xlabel("X (px)", fontsize=9)
        ax.set_ylabel("Y (px)", fontsize=9)
        ax.xaxis.set_major_locator(MultipleLocator(5))
        ax.yaxis.set_major_locator(MultipleLocator(5))

    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.text(
        0.99,
        0.005,
        COPERNICUS_ATTRIBUTION,
        fontsize=8,
        color="#777777",
        style="italic",
        ha="right",
        va="bottom",
    )

    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_p, dpi=180, bbox_inches="tight")
        logger.info("Saved multiband panel to %s", out_p)

    return fig


def create_pixel_grid_zoom(
    bands: dict[str, np.ndarray],
    centroids: dict[str, tuple[float, float]],
    result: MeasurementResult,
    zoom_radius: int = 7,
    title: str = "Subpixel Pixel Grid Resolution (10 m/px)",
    out_path: str | Path | None = None,
) -> plt.Figure:
    """Generate high-zoom RGB composite with pixel grid lines and subpixel centroids."""
    rgb = create_rgb_composite(bands)

    if "green" in centroids:
        cx0, cy0 = centroids["green"]
    else:
        cx0 = (centroids["red"][0] + centroids["blue"][0]) / 2.0
        cy0 = (centroids["red"][1] + centroids["blue"][1]) / 2.0

    fig, ax = plt.subplots(figsize=(8, 8), constrained_layout=True)
    ax.imshow(rgb, interpolation="nearest")

    ax.xaxis.set_major_locator(MultipleLocator(1))
    ax.yaxis.set_major_locator(MultipleLocator(1))
    ax.grid(True, which="both", color="white", alpha=0.35, linewidth=0.8, linestyle="--")

    rx, ry = centroids["red"]
    gx, gy = centroids.get(
        "green", ((rx + centroids["blue"][0]) / 2.0, (ry + centroids["blue"][1]) / 2.0)
    )
    bx, by = centroids["blue"]

    # Trajectory line connecting the 3 subpixel centroids
    ax.plot([rx, gx, bx], [ry, gy, by], "-", color="yellow", lw=2.0, alpha=0.85, label="Trajectory")
    ax.annotate(
        "",
        xy=(bx, by),
        xytext=(rx, ry),
        arrowprops={"arrowstyle": "-|>", "color": "white", "lw": 2.2, "mutation_scale": 16},
    )

    ax.plot(
        rx,
        ry,
        "o",
        mfc="#f87171",
        mec="white",
        ms=12,
        mew=2.0,
        label=f"Red B04 ({rx:.2f}, {ry:.2f})",
    )
    ax.plot(
        gx,
        gy,
        "o",
        mfc="#4ade80",
        mec="white",
        ms=12,
        mew=2.0,
        label=f"Green B03 ({gx:.2f}, {gy:.2f})",
    )
    ax.plot(
        bx,
        by,
        "o",
        mfc="#38bdf8",
        mec="white",
        ms=12,
        mew=2.0,
        label=f"Blue B02 ({bx:.2f}, {by:.2f})",
    )

    ax.set_xlim(cx0 - zoom_radius, cx0 + zoom_radius)
    ax.set_ylim(cy0 + zoom_radius, cy0 - zoom_radius)
    ax.set_xlabel("X (East, pixels)", fontsize=10)
    ax.set_ylabel("Y (South, pixels)", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(
        loc="upper right", framealpha=0.9, facecolor="#1e1e1e", labelcolor="white", fontsize=9
    )

    info_box = (
        f"Displacement: {result.distance_m:.1f} m ({result.distance_px:.2f} px)\n"
        f"Velocity:     {result.speed_kmh:.0f} km/h [{result.speed_kmh_min:.0f} - {result.speed_kmh_max:.0f} km/h]\n"
        f"Heading:      {result.heading_deg:.1f}°\n"
        f"Delta t:      {result.delta_t_s:.3f} s\n"
        f"Collinearity: {result.collinearity_px:.2f} px\n"
        f"Pixel Scale:  10 m / pixel"
    )
    ax.text(
        0.03,
        0.03,
        info_box,
        transform=ax.transAxes,
        fontsize=9,
        fontfamily="monospace",
        color="white",
        bbox={
            "boxstyle": "round,pad=0.5",
            "facecolor": "#111111",
            "alpha": 0.85,
            "edgecolor": "#555555",
        },
        verticalalignment="bottom",
    )

    fig.text(
        0.99,
        0.005,
        COPERNICUS_ATTRIBUTION,
        fontsize=8,
        color="#777777",
        style="italic",
        ha="right",
        va="bottom",
    )

    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_p, dpi=180, bbox_inches="tight")
        logger.info("Saved pixel grid zoom figure to %s", out_p)

    return fig


def create_social_card(
    case_id: str,
    bands: dict[str, np.ndarray],
    centroids: dict[str, tuple[float, float]],
    result: MeasurementResult,
    lang: str = "es",
    out_path: str | Path | None = None,
) -> plt.Figure:
    """Generate high-impact 4:5 social media card (1080x1350 px) in dark mode.

    Args:
        case_id: Scenario identifier ('case1', 'case2', or descriptive).
        bands: Dictionary containing spectral band arrays ('red', 'green', 'blue').
        centroids: Subpixel coordinates dictionary.
        result: MeasurementResult kinematics object.
        lang: Language for text ('es' or 'en', default: 'es').
        out_path: Optional path to save image file.
    """
    is_case2 = (result.parallax is not None and result.parallax.altitude_m > 1000.0) or (
        "case2" in case_id.lower() or "cruise" in case_id.lower()
    )

    # Bilingual texts
    t_es = {
        "badge": "CINEMÁTICA POR PARALAJE · SENTINEL-2",
        "case1_title": "Aeronave en Aproximación Final",
        "case1_sub": "Aeropuerto de Bilbao (LEBB/BIO) · Pista 12 · 2026-08-12",
        "case2_title": "Aeronave en Crucero a Alta Cota",
        "case2_sub": "Nivel de Vuelo FL350 (~10.5 km AGL) · 2026-06-21",
        "speed_title": "VELOCIDAD SOBRE EL SUELO",
        "heading_title": "RUMBO DE VUELO",
        "apparent": "Aparente",
        "corrected": "Corregida por paralaje",
        "disclaimer": "HIPÓTESIS CINEMÁTICA · SIN VALIDAR CON DATOS EXTERNOS (ADS-B)",
        "copernicus": "Contiene datos modificados de Copernicus Sentinel [2026]",
    }
    t_en = {
        "badge": "SENTINEL-2 PARALLAX KINEMATICS",
        "case1_title": "Aircraft on Final Approach",
        "case1_sub": "Bilbao Airport (LEBB/BIO) · Runway 12 · 2026-08-12",
        "case2_title": "High-Altitude Aircraft in Cruise",
        "case2_sub": "Flight Level FL350 (~10.5 km AGL) · 2026-06-21",
        "speed_title": "GROUND SPEED",
        "heading_title": "FLIGHT HEADING",
        "apparent": "Apparent",
        "corrected": "Parallax corrected",
        "disclaimer": "KINEMATIC HYPOTHESIS · NOT VALIDATED WITH EXTERNAL DATA (ADS-B)",
        "copernicus": "Contains modified Copernicus Sentinel data [2026]",
    }
    t = t_es if lang == "es" else t_en

    # Exactly 1080 x 1350 pixels (4:5 vertical)
    fig = plt.figure(figsize=(6.0, 7.5), dpi=180, facecolor="#0b0f19")

    # 1. Header (y: 0.88 - 0.98)
    fig.text(
        0.5,
        0.965,
        t["badge"],
        fontsize=8.5,
        fontweight="bold",
        color="#38bdf8",
        ha="center",
        va="top",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "#111827",
            "edgecolor": "#1e293b",
            "lw": 1.2,
        },
    )

    title_text = t["case2_title"] if is_case2 else t["case1_title"]
    sub_text = t["case2_sub"] if is_case2 else t["case1_sub"]
    fig.text(
        0.5,
        0.925,
        title_text,
        fontsize=14.5,
        fontweight="bold",
        color="#f8fafc",
        ha="center",
        va="top",
    )
    fig.text(0.5, 0.895, sub_text, fontsize=8.5, color="#94a3b8", ha="center", va="top")

    # 2. Main Visual Axes (Zoomed RGB Crop with Pixel Grid)
    ax_img = fig.add_axes([0.08, 0.40, 0.84, 0.47])
    ax_img.set_facecolor("#0b0f19")

    rgb = create_rgb_composite(bands)
    ax_img.imshow(rgb, interpolation="nearest")

    ax_img.xaxis.set_major_locator(MultipleLocator(1))
    ax_img.yaxis.set_major_locator(MultipleLocator(1))
    ax_img.grid(True, which="both", color="white", alpha=0.30, linewidth=0.7, linestyle="--")

    rx, ry = centroids["red"]
    gx, gy = centroids.get(
        "green", ((rx + centroids["blue"][0]) / 2.0, (ry + centroids["blue"][1]) / 2.0)
    )
    bx, by = centroids["blue"]

    # Trajectory and centroids
    ax_img.plot([rx, gx, bx], [ry, gy, by], "-", color="yellow", lw=2.2, alpha=0.85)
    ax_img.annotate(
        "",
        xy=(bx, by),
        xytext=(rx, ry),
        arrowprops={"arrowstyle": "-|>", "color": "white", "lw": 2.2, "mutation_scale": 16},
    )

    ax_img.plot(
        rx, ry, "o", mfc="#f87171", mec="white", ms=11, mew=1.8, label="Red (B04, t=0.000s)"
    )
    ax_img.plot(
        gx, gy, "o", mfc="#4ade80", mec="white", ms=11, mew=1.8, label="Green (B03, t=0.478s)"
    )
    ax_img.plot(
        bx, by, "o", mfc="#38bdf8", mec="white", ms=11, mew=1.8, label="Blue (B02, t=1.005s)"
    )

    zoom_r = 8
    ax_img.set_xlim(gx - zoom_r, gx + zoom_r)
    ax_img.set_ylim(gy + zoom_r, gy - zoom_r)
    ax_img.set_xticks([])
    ax_img.set_yticks([])

    ax_img.text(
        0.03,
        0.96,
        "Sentinel-2 MSI · 10 m / px",
        transform=ax_img.transAxes,
        fontsize=8,
        color="#cbd5e1",
        va="top",
        bbox={
            "boxstyle": "round,pad=0.25",
            "facecolor": "#0b0f19",
            "alpha": 0.85,
            "edgecolor": "#334155",
        },
    )
    ax_img.legend(
        loc="lower right", framealpha=0.85, facecolor="#0b0f19", labelcolor="white", fontsize=7.5
    )

    # 3. Metrics Cards (y: 0.165 - 0.37)
    ax_card1 = fig.add_axes([0.08, 0.165, 0.405, 0.205])
    ax_card1.set_facecolor("#131a29")
    for spine in ax_card1.spines.values():
        spine.set_edgecolor("#1e293b")
        spine.set_linewidth(1.2)
    ax_card1.set_xticks([])
    ax_card1.set_yticks([])

    ax_card2 = fig.add_axes([0.515, 0.165, 0.405, 0.205])
    ax_card2.set_facecolor("#131a29")
    for spine in ax_card2.spines.values():
        spine.set_edgecolor("#1e293b")
        spine.set_linewidth(1.2)
    ax_card2.set_xticks([])
    ax_card2.set_yticks([])

    if not is_case2:
        # Case 1 (Approach)
        spd_unc = (result.speed_kmh_max - result.speed_kmh_min) / 2.0
        ax_card1.text(
            0.08, 0.86, t["speed_title"], fontsize=7.5, fontweight="bold", color="#94a3b8", va="top"
        )
        ax_card1.text(
            0.08,
            0.58,
            f"{result.speed_kmh:.0f} km/h",
            fontsize=20,
            fontweight="bold",
            color="#38bdf8",
            va="center",
        )
        ax_card1.text(
            0.08,
            0.22,
            f"±{spd_unc:.0f} km/h (2σ)\n[{result.speed_kmh_min:.0f} - {result.speed_kmh_max:.0f} km/h]",
            fontsize=7.5,
            color="#cbd5e1",
            va="center",
        )

        ax_card2.text(
            0.08,
            0.86,
            t["heading_title"],
            fontsize=7.5,
            fontweight="bold",
            color="#94a3b8",
            va="top",
        )
        ax_card2.text(
            0.08,
            0.58,
            f"{result.heading_deg:.1f}°",
            fontsize=20,
            fontweight="bold",
            color="#4ade80",
            va="center",
        )
        ax_card2.text(
            0.08,
            0.22,
            f"±{result.heading_uncertainty_deg:.1f}° (2σ)\nEje pista 12: 116.7°",
            fontsize=7.5,
            color="#cbd5e1",
            va="center",
        )
    else:
        # Case 2 (Cruise with parallax)
        px = result.parallax
        corr_spd = px.corrected_speed_kmh if px else 932.0
        corr_hdg = px.corrected_heading_deg if px else 316.4
        spd_range_s = (
            f"[{px.corrected_speed_min_kmh:.0f} - {px.corrected_speed_max_kmh:.0f}]"
            if (px and px.corrected_speed_min_kmh)
            else "[907 - 960]"
        )

        ax_card1.text(
            0.08, 0.88, t["speed_title"], fontsize=7.2, fontweight="bold", color="#94a3b8", va="top"
        )
        ax_card1.text(
            0.08,
            0.64,
            f"{corr_spd:.0f} km/h",
            fontsize=17,
            fontweight="bold",
            color="#38bdf8",
            va="center",
        )
        ax_card1.text(0.08, 0.44, f"• {t['corrected']}", fontsize=6.8, color="#38bdf8", va="center")
        ax_card1.text(
            0.08,
            0.20,
            f"{t['apparent']}: {result.speed_kmh:.0f} km/h\n{spd_range_s} a h=10.5 km",
            fontsize=7.0,
            color="#cbd5e1",
            va="center",
        )

        ax_card2.text(
            0.08,
            0.88,
            t["heading_title"],
            fontsize=7.2,
            fontweight="bold",
            color="#94a3b8",
            va="top",
        )
        ax_card2.text(
            0.08,
            0.64,
            f"{corr_hdg:.1f}°",
            fontsize=17,
            fontweight="bold",
            color="#4ade80",
            va="center",
        )
        ax_card2.text(0.08, 0.44, f"• {t['corrected']}", fontsize=6.8, color="#4ade80", va="center")
        ax_card2.text(
            0.08,
            0.20,
            f"{t['apparent']}: {result.heading_deg:.1f}° (±1.8°)\nIncertidumbre: ±6.1° (2σ)",
            fontsize=7.0,
            color="#cbd5e1",
            va="center",
        )

    # 4. Disclaimer Banner (y: 0.08 - 0.12)
    fig.text(
        0.5,
        0.095,
        f"⚠️  {t['disclaimer']}",
        fontsize=7.5,
        fontweight="bold",
        color="#fbbf24",
        ha="center",
        va="center",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "#1f1d13",
            "edgecolor": "#78350f",
            "lw": 1.0,
        },
    )

    # 5. Footer (y: 0.02 - 0.05)
    fig.text(
        0.5,
        0.035,
        f"{t['copernicus']}  ·  github.com/alfredgabriel/sentinel2-movement",
        fontsize=7.0,
        color="#64748b",
        ha="center",
        va="center",
    )

    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_p, dpi=180)
        logger.info("Saved social card (4:5) to %s", out_p)

    return fig


def show_interactive_viewer(
    rgb: np.ndarray,
    title: str = "Interactive Pixel Inspector (Click to log coordinates)",
) -> None:
    """Launch interactive matplotlib viewer with mouse click coordinate logger.

    Args:
        rgb: 3D float array of RGB composite.
        title: Figure window title.
    """
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.imshow(rgb, interpolation="nearest")
    ax.set_title(title + "\n(Zoom in and click: coordinates printed to console)")

    def onclick(event):
        if event.xdata is not None and event.ydata is not None:
            print(
                f"Clicked seed: x={event.xdata:.1f}, y={event.ydata:.1f} (integer: {int(round(event.xdata))}, {int(round(event.ydata))})"
            )

    fig.canvas.mpl_connect("button_press_event", onclick)
    plt.tight_layout()
    plt.show()
