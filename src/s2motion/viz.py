"""Visualization module for RGB composites, multi-band panels, and annotated figures."""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

from s2motion.constants import BAND_DELAYS_S
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

    Left: Zoomed RGB composite with subpixel centroid markers, movement vector arrow,
          and runway orientation guide.
    Right: Individual spectral band anomaly crops arranged chronologically (Blue -> Green -> Red)
           showing the progression over time.

    Args:
        bands: Dictionary of 2D band arrays (must contain 'blue', 'green', 'red').
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
        cx0 = (centroids["blue"][0] + centroids["red"][0]) / 2.0
        cy0 = (centroids["blue"][1] + centroids["red"][1]) / 2.0

    fig = plt.figure(figsize=(14, 8), constrained_layout=True)
    gs = fig.add_gridspec(3, 2, width_ratios=[1.4, 1.0])

    # 1. Main Left Panel: Zoomed RGB Composite with Overlays
    ax_main = fig.add_subplot(gs[:, 0])
    ax_main.imshow(rgb, interpolation="nearest")

    # Draw centroid markers
    colors = {"blue": "deepskyblue", "green": "lime", "red": "tomato"}
    for b_name in ("blue", "green", "red"):
        if b_name in centroids:
            px, py = centroids[b_name]
            code = {"blue": "B02", "green": "B03", "red": "B04"}.get(b_name, "")
            dt = BAND_DELAYS_S.get(code, 0.0)
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

    # Draw motion vector arrow: Blue -> Red
    bx, by = centroids["blue"]
    rx, ry = centroids["red"]
    ax_main.annotate(
        "",
        xy=(rx, ry),
        xytext=(bx, by),
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
        f"Zoomed RGB Composite (10 m/px)\nDisplacement: {result.distance_m:.1f} m | Heading: {result.heading_deg:.1f}°",
        fontsize=12,
        fontweight="bold",
    )
    ax_main.legend(loc="upper right", framealpha=0.85, facecolor="#1e1e1e", labelcolor="white")

    # Add overlay metrics box on bottom left
    metrics_text = (
        f"Velocity: {result.speed_kmh:.0f} km/h [{result.speed_kmh_min:.0f} - {result.speed_kmh_max:.0f} km/h]\n"
        f"Heading:  {result.heading_deg:.1f}° (N={0}°, clockwise)\n"
        f"Delta t:  {result.delta_t_s:.3f} s (+/-2%)\n"
        f"Collinearity: {result.collinearity_px:.2f} px\n"
        f"Green pos:    {result.green_relative_fraction:.2f} (exp: {result.expected_green_fraction:.2f})"
    )
    if result.runway_diff_deg is not None:
        metrics_text += f"\nRunway axis diff: {result.runway_diff_deg:.1f}°"

    ax_main.text(
        0.03,
        0.04,
        metrics_text,
        transform=ax_main.transAxes,
        fontsize=9.5,
        fontfamily="monospace",
        color="white",
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "#111111", "alpha": 0.85, "edgecolor": "#555555"},
        verticalalignment="bottom",
    )

    # 2. Right Panels: Individual Band Anomaly Progression (Chronological)
    band_sequence = [("blue", "B02 (Blue)", 0.000), ("green", "B03 (Green)", 0.527), ("red", "B04 (Red)", 1.005)]
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
            print(f"Clicked seed: x={event.xdata:.1f}, y={event.ydata:.1f} (integer: {int(round(event.xdata))}, {int(round(event.ydata))})")

    fig.canvas.mpl_connect("button_press_event", onclick)
    plt.tight_layout()
    plt.show()
