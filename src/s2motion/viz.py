"""Visualization module for RGB composites, multi-band panels, and annotated figures."""

import logging
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

from s2motion.constants import GROUND_ACQUISITION_TIMING_S
from s2motion.detect import subtract_local_background
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

    # Draw motion vector arrow: Red -> Blue
    rx, ry = centroids["red"]
    bx, by = centroids["blue"]
    ax_main.annotate(
        "",
        xy=(bx, by),
        xytext=(rx, ry),
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
        f"Zoomed RGB Composite (10 m/px) | Vector: Red -> Blue\nDisplacement: {result.distance_m:.1f} m | Heading: {result.heading_deg:.1f}°",
        fontsize=12,
        fontweight="bold",
    )
    ax_main.legend(loc="upper right", framealpha=0.85, facecolor="#1e1e1e", labelcolor="white")

    # Add overlay metrics box on bottom left
    metrics_text = (
        f"Direction: Red -> Green -> Blue\n"
        f"Velocity:  {result.speed_kmh:.0f} km/h [{result.speed_kmh_min:.0f} - {result.speed_kmh_max:.0f} km/h]\n"
        f"Heading:   {result.heading_deg:.1f}° (N=0°, clockwise)\n"
        f"Delta t:   {result.delta_t_s:.3f} s (+/-2%)\n"
        f"Collinearity: {result.collinearity_px:.2f} px\n"
        f"Green pos:    {result.green_relative_fraction:.2f} (exp: {result.expected_green_fraction:.2f})"
    )
    if result.runway_proximity is not None:
        p = result.runway_proximity
        metrics_text += (
            f"\nRunway Axis Diff: {result.runway_diff_deg:.1f}°\n"
            f"Distance to THR 12: {p.dist_thr12_m:.0f} m (offset: {p.cross_axis_m:.1f} m)"
        )
    elif result.runway_diff_deg is not None:
        metrics_text += f"\nRunway axis diff: {result.runway_diff_deg:.1f}°"

    if result.aero is not None:
        a = result.aero
        obs = a.weather
        metrics_text += (
            f"\n-- Surface Weather Context (10m AGL) --\n"
            f"Wind:      {obs.wind_speed_kmh:.1f} km/h ({obs.wind_speed_knots:.1f} kt) from {obs.wind_direction_deg:.0f}°\n"
            f"Headwind:  {a.headwind_mps * 3.6:+.1f} km/h ({a.headwind_mps * 1.94384:+.1f} kt) | Cross: {a.crosswind_mps * 3.6:+.1f} km/h\n"
            f"Airspeeds: TAS = {a.true_airspeed_kmh:.0f} km/h [{a.true_airspeed_knots:.0f} kt] (GS: {result.speed_kmh:.0f})\n"
            f"Density:   DA = {a.density_altitude_ft:.0f} ft ({a.density_delta_ft:+.0f} ft vs field)"
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

    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_p, dpi=180, bbox_inches="tight")
        logger.info("Saved annotated figure to %s", out_p)

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
