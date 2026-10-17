"""ADS-B trajectory validation module for Sentinel-2 moving object kinematics.

Provides offline validation against external ADS-B / Mode-S transponder records
(e.g., OpenSky Network CSV or ADS-B Exchange JSON), performs continuous trajectory
interpolation to find the Closest Point of Approach (CPA), and tests kinematic
concordance against both 'red-first' and 'blue-first' band order hypotheses.

References:
    - OpenSky Network: https://opensky-network.org/
    - ADS-B Exchange: https://www.adsbexchange.com/
    - ICAO Annex 10, Vol. IV (Surveillance and Collision Avoidance Systems).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Final

from s2motion.constants import EARTH_MEAN_RADIUS_M
from s2motion.parallax import correct_parallax

# Conversion constants
FEET_TO_METERS: Final[float] = 0.3048
KNOTS_TO_MPS: Final[float] = 0.5144444444444445
MPS_TO_KMH: Final[float] = 3.6


class MatchStatus(str, Enum):
    """Categorical outcome of ADS-B cross-validation."""

    COMPATIBLE_RED_FIRST = "COMPATIBLE_RED_FIRST"
    COMPATIBLE_BLUE_FIRST = "COMPATIBLE_BLUE_FIRST"
    AMBIGUOUS_BOTH = "AMBIGUOUS_BOTH"
    INCOMPATIBLE_NEITHER = "INCOMPATIBLE_NEITHER"
    NO_DATA_OR_NO_MATCH = "NO_DATA_OR_NO_MATCH"


@dataclass(frozen=True)
class ADSBStateVector:
    """Single ADS-B state vector observation."""

    timestamp: float  # UNIX epoch seconds (UTC)
    icao24: str
    callsign: str | None
    latitude: float
    longitude: float
    altitude_baro_m: float | None
    altitude_geom_m: float | None
    ground_speed_mps: float | None
    heading_deg: float | None
    vertical_rate_mps: float | None = None
    on_ground: bool | None = None


@dataclass(frozen=True)
class ADSBValidationCriteria:
    """A priori concordance criteria defined before inspecting observational data.

    Criteria must be set prior to matching to avoid post-hoc tuning.
    """

    max_distance_m: float = (
        1000.0  # Spatial tolerance (1 km for Case 1 approach, 2 km for Case 2 cruise)
    )
    time_window_s: float = 60.0  # Temporal matching window: +/- 60 s around satellite overpass
    heading_tolerance_deg: float = 14.0  # 2-sigma angular tolerance (2 * ~7.0 deg for Case 1)
    speed_tolerance_relative: float = 0.15  # +/- 15% tolerance if explicit interval not used


@dataclass(frozen=True)
class ADSBInterpolatedState:
    """Interpolated state vector at the Closest Point of Approach (CPA)."""

    icao24: str
    callsign: str | None
    cpa_timestamp: float
    cpa_datetime_iso: str
    cpa_latitude: float
    cpa_longitude: float
    distance_to_target_m: float
    time_offset_s: (
        float  # cpa_timestamp - sensing_timestamp (positive = CPA after satellite sensing)
    )
    heading_deg: float
    ground_speed_mps: float
    ground_speed_kmh: float
    altitude_baro_m: float | None
    altitude_geom_m: float | None
    baro_geom_diff_m: float | None


@dataclass(frozen=True)
class HypothesisComparison:
    """Comparison of an ADS-B state against one band-order hypothesis."""

    band_order: str
    measured_heading_deg: float
    heading_diff_deg: float  # (measured - adsb), normalized to [-180, +180]
    heading_compatible: bool
    measured_speed_kmh: float
    speed_min_kmh: float
    speed_max_kmh: float
    adsb_speed_kmh: float
    speed_diff_kmh: float  # (measured - adsb)
    speed_compatible: bool
    distance_m: float
    distance_compatible: bool
    overall_compatible: bool


@dataclass(frozen=True)
class ADSBValidationReport:
    """Comprehensive validation report against ADS-B telemetry."""

    target_lat: float
    target_lon: float
    sensing_timestamp: float
    sensing_datetime_iso: str
    criteria: ADSBValidationCriteria
    status: MatchStatus
    best_candidate: ADSBInterpolatedState | None
    red_first: HypothesisComparison | None
    blue_first: HypothesisComparison | None
    recalculated_parallax_speed_kmh: float | None
    recalculated_parallax_diff_kmh: float | None
    recalculated_parallax_heading_deg: float | None
    message: str

    def summary(self) -> str:
        """Format a human-readable validation summary."""
        lines = [
            "============================================================",
            "Sentinel-2 Moving Object ADS-B Validation Report",
            "============================================================",
            f"Target Position:         lat {self.target_lat:.6f}°, lon {self.target_lon:.6f}°",
            f"Sensing Time:            {self.sensing_datetime_iso} (epoch {self.sensing_timestamp:.1f} s)",
            "A Priori Criteria:",
            f"  - Max Distance:        {self.criteria.max_distance_m:.0f} m",
            f"  - Time Window:         ±{self.criteria.time_window_s:.0f} s",
            f"  - Heading 2-sigma:     ±{self.criteria.heading_tolerance_deg:.1f}°",
            "------------------------------------------------------------",
            f"Validation Outcome:      {self.status.value}",
            f"Diagnostics:             {self.message}",
        ]

        if self.best_candidate is not None:
            c = self.best_candidate
            cs = c.callsign or "N/A"
            lines.extend(
                [
                    "------------------------------------------------------------",
                    f"Matched Aircraft:        {cs} (ICAO24: {c.icao24})",
                    f"CPA Timestamp:           {c.cpa_datetime_iso} (offset: {c.time_offset_s:+.2f} s)",
                    f"CPA Distance:            {c.distance_to_target_m:.1f} m",
                    f"ADS-B Ground Speed:      {c.ground_speed_kmh:.1f} km/h [{c.ground_speed_mps:.1f} m/s]",
                    f"ADS-B Track Heading:     {c.heading_deg:.1f}°",
                ]
            )
            if c.altitude_baro_m is not None:
                geom_str = f"{c.altitude_geom_m:.0f} m" if c.altitude_geom_m is not None else "N/A"
                diff_str = (
                    f"{c.baro_geom_diff_m:+.0f} m" if c.baro_geom_diff_m is not None else "N/A"
                )
                lines.append(
                    f"Altitude:                Barometric: {c.altitude_baro_m:.0f} m ({c.altitude_baro_m / FEET_TO_METERS:.0f} ft) | "
                    f"Geometric: {geom_str} | Diff: {diff_str}"
                )

        if self.red_first is not None and self.blue_first is not None:
            lines.extend(
                [
                    "------------------------------------------------------------",
                    "Band Order Hypothesis Concordance:",
                    "  1. red-first (Red -> Blue):",
                    f"     - Heading:  measured {self.red_first.measured_heading_deg:.1f}° vs ADS-B {self.best_candidate.heading_deg:.1f}° (diff: {self.red_first.heading_diff_deg:+.1f}°) -> {'PASS' if self.red_first.heading_compatible else 'FAIL'}",
                    f"     - Speed:    measured {self.red_first.measured_speed_kmh:.0f} km/h (range: {self.red_first.speed_min_kmh:.0f}-{self.red_first.speed_max_kmh:.0f}) vs ADS-B {self.best_candidate.ground_speed_kmh:.0f} km/h (diff: {self.red_first.speed_diff_kmh:+.0f}) -> {'PASS' if self.red_first.speed_compatible else 'FAIL'}",
                    f"     - Verdict:  {'COMPATIBLE' if self.red_first.overall_compatible else 'INCOMPATIBLE'}",
                    "  2. blue-first (Blue -> Red):",
                    f"     - Heading:  measured {self.blue_first.measured_heading_deg:.1f}° vs ADS-B {self.best_candidate.heading_deg:.1f}° (diff: {self.blue_first.heading_diff_deg:+.1f}°) -> {'PASS' if self.blue_first.heading_compatible else 'FAIL'}",
                    f"     - Speed:    measured {self.blue_first.measured_speed_kmh:.0f} km/h (range: {self.blue_first.speed_min_kmh:.0f}-{self.blue_first.speed_max_kmh:.0f}) vs ADS-B {self.best_candidate.ground_speed_kmh:.0f} km/h (diff: {self.blue_first.speed_diff_kmh:+.0f}) -> {'PASS' if self.blue_first.speed_compatible else 'FAIL'}",
                    f"     - Verdict:  {'COMPATIBLE' if self.blue_first.overall_compatible else 'INCOMPATIBLE'}",
                ]
            )

        if self.recalculated_parallax_speed_kmh is not None and self.best_candidate is not None:
            lines.extend(
                [
                    "------------------------------------------------------------",
                    "Parallax Recalculation with Real ADS-B Altitude:",
                    f"  - Recalculated Speed:   {self.recalculated_parallax_speed_kmh:.1f} km/h (heading: {self.recalculated_parallax_heading_deg:.1f}°)",
                    f"  - ADS-B Ground Speed:   {self.best_candidate.ground_speed_kmh:.1f} km/h",
                    f"  - Residual Speed Diff:  {self.recalculated_parallax_diff_kmh:+.1f} km/h",
                ]
            )

        lines.append("============================================================")
        return "\n".join(lines)


def calculate_haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two coordinates in meters."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_MEAN_RADIUS_M * c


def parse_timestamp(value: Any) -> float:
    """Parse various timestamp representations to UNIX epoch seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip()
        try:
            return float(v)
        except ValueError:
            pass
        # Try ISO format
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt.timestamp()
    raise ValueError(f"Cannot parse timestamp from value: {value!r}")


def parse_opensky_csv(
    filepath: Path,
    column_mapping: dict[str, str] | None = None,
) -> list[ADSBStateVector]:
    """Parse an OpenSky Network CSV state vector export file.

    Columns standard in OpenSky state vectors:
    time, icao24, lat, lon, velocity, heading, vertrate, callsign, onground,
    baroaltitude, geoaltitude, lastposupdate, lastcontact.
    """
    mapping = {
        "time": "time",
        "icao24": "icao24",
        "callsign": "callsign",
        "lat": "lat",
        "lon": "lon",
        "velocity": "velocity",
        "heading": "heading",
        "vertrate": "vertrate",
        "baroaltitude": "baroaltitude",
        "geoaltitude": "geoaltitude",
        "onground": "onground",
    }
    if column_mapping:
        mapping.update(column_mapping)

    vectors: list[ADSBStateVector] = []
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Time
                t_val = row.get(mapping["time"])
                if not t_val:
                    continue
                ts = parse_timestamp(t_val)

                icao = (row.get(mapping["icao24"]) or "").strip().lower()
                callsign = (row.get(mapping["callsign"]) or "").strip() or None

                lat_str = row.get(mapping["lat"])
                lon_str = row.get(mapping["lon"])
                if not lat_str or not lon_str:
                    continue
                lat = float(lat_str)
                lon = float(lon_str)

                # Velocity (OpenSky velocity is in m/s)
                v_str = row.get(mapping["velocity"])
                speed_mps = float(v_str) if v_str else None

                # Heading / track (degrees)
                hdg_str = row.get(mapping["heading"])
                hdg = float(hdg_str) if hdg_str else None

                # Vertical rate (m/s)
                vr_str = row.get(mapping["vertrate"])
                vertrate = float(vr_str) if vr_str else None

                # Altitudes (OpenSky raw is in meters)
                baro_str = row.get(mapping["baroaltitude"])
                alt_baro = float(baro_str) if baro_str else None

                geom_str = row.get(mapping["geoaltitude"])
                alt_geom = float(geom_str) if geom_str else None

                # Onground
                og_str = (row.get(mapping["onground"]) or "").strip().lower()
                onground = og_str in ("true", "1", "t") if og_str else None

                vectors.append(
                    ADSBStateVector(
                        timestamp=ts,
                        icao24=icao,
                        callsign=callsign,
                        latitude=lat,
                        longitude=lon,
                        altitude_baro_m=alt_baro,
                        altitude_geom_m=alt_geom,
                        ground_speed_mps=speed_mps,
                        heading_deg=hdg,
                        vertical_rate_mps=vertrate,
                        on_ground=onground,
                    )
                )
            except (ValueError, KeyError):
                continue

    return vectors


def parse_adsbx_json(
    filepath: Path,
    key_mapping: dict[str, str] | None = None,
) -> list[ADSBStateVector]:
    """Parse an ADS-B Exchange JSON snapshot or trace export.

    Standard ADSBx fields:
    - hex (icao24)
    - flight (callsign)
    - lat, lon
    - alt_baro (feet or 'ground')
    - alt_geom (feet)
    - gs (knots)
    - track (degrees)
    """
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    vectors: list[ADSBStateVector] = []
    base_time = float(
        data.get("now", data.get("timestamp", datetime.now(timezone.utc).timestamp()))
    )

    # Format 1: {"aircraft": [{...}, {...}]}
    if "aircraft" in data and isinstance(data["aircraft"], list):
        for ac in data["aircraft"]:
            try:
                icao = (ac.get("hex") or "").strip().lower()
                callsign = (ac.get("flight") or "").strip() or None
                lat = ac.get("lat")
                lon = ac.get("lon")
                if lat is None or lon is None:
                    continue

                # Timestamp: base_time minus seen_pos if present
                seen_pos = ac.get("seen_pos", ac.get("seen", 0.0))
                ts = base_time - float(seen_pos)

                # Ground speed: ADSBx 'gs' is in knots -> convert to m/s
                gs_kt = ac.get("gs")
                speed_mps = float(gs_kt) * KNOTS_TO_MPS if gs_kt is not None else None

                track = ac.get("track")
                hdg = float(track) if track is not None else None

                # Altitudes: in feet -> convert to meters
                baro_val = ac.get("alt_baro")
                alt_baro = None
                on_ground = None
                if baro_val == "ground":
                    on_ground = True
                    alt_baro = 0.0
                elif baro_val is not None:
                    alt_baro = float(baro_val) * FEET_TO_METERS
                    on_ground = False

                geom_val = ac.get("alt_geom")
                alt_geom = float(geom_val) * FEET_TO_METERS if geom_val is not None else None

                vectors.append(
                    ADSBStateVector(
                        timestamp=ts,
                        icao24=icao,
                        callsign=callsign,
                        latitude=float(lat),
                        longitude=float(lon),
                        altitude_baro_m=alt_baro,
                        altitude_geom_m=alt_geom,
                        ground_speed_mps=speed_mps,
                        heading_deg=hdg,
                        on_ground=on_ground,
                    )
                )
            except (ValueError, TypeError):
                continue

    # Format 2: Trace format {"icao": "...", "trace": [[offset_s, lat, lon, alt_ft, gs_kt, track, ...], ...]}
    elif "trace" in data and isinstance(data["trace"], list):
        icao = (data.get("icao") or data.get("hex") or "").strip().lower()
        callsign = (data.get("callsign") or data.get("flight") or "").strip() or None
        trace_list = data["trace"]
        for pt in trace_list:
            try:
                if len(pt) < 3:
                    continue
                offset_s = float(pt[0])
                lat = float(pt[1])
                lon = float(pt[2])
                ts = base_time + offset_s

                alt_baro = None
                speed_mps = None
                hdg = None

                if len(pt) > 3 and pt[3] is not None:
                    alt_baro = float(pt[3]) * FEET_TO_METERS
                if len(pt) > 4 and pt[4] is not None:
                    speed_mps = float(pt[4]) * KNOTS_TO_MPS
                if len(pt) > 5 and pt[5] is not None:
                    hdg = float(pt[5])

                vectors.append(
                    ADSBStateVector(
                        timestamp=ts,
                        icao24=icao,
                        callsign=callsign,
                        latitude=lat,
                        longitude=lon,
                        altitude_baro_m=alt_baro,
                        altitude_geom_m=None,
                        ground_speed_mps=speed_mps,
                        heading_deg=hdg,
                    )
                )
            except (ValueError, TypeError):
                continue

    return vectors


def load_adsb_records(filepath: Path, format_hint: str = "auto") -> list[ADSBStateVector]:
    """Load ADS-B records from either CSV or JSON with automatic format detection."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"ADS-B trajectory file not found: {filepath}")

    ext = p.suffix.lower()
    if format_hint == "csv" or (format_hint == "auto" and ext == ".csv"):
        return parse_opensky_csv(p)
    elif format_hint == "json" or (format_hint == "auto" and ext == ".json"):
        return parse_adsbx_json(p)
    else:
        # Try JSON first, fallback to CSV
        try:
            return parse_adsbx_json(p)
        except Exception:
            return parse_opensky_csv(p)


def interpolate_track_cpa(
    aircraft_vectors: list[ADSBStateVector],
    target_lat: float,
    target_lon: float,
    sensing_timestamp: float,
    time_window_s: float = 60.0,
) -> ADSBInterpolatedState | None:
    """Find the Closest Point of Approach (CPA) by interpolating trajectory segments."""
    # 1. Filter points within temporal window
    window_pts = [
        v for v in aircraft_vectors if abs(v.timestamp - sensing_timestamp) <= time_window_s
    ]
    if not window_pts:
        return None

    # Sort strictly by timestamp
    window_pts.sort(key=lambda x: x.timestamp)

    # Local metric coordinates conversion helper
    cos_lat = math.cos(math.radians(target_lat))
    m_per_deg_lat = (math.pi / 180.0) * EARTH_MEAN_RADIUS_M
    m_per_deg_lon = m_per_deg_lat * cos_lat

    def to_xy(lat: float, lon: float) -> tuple[float, float]:
        return (lon - target_lon) * m_per_deg_lon, (lat - target_lat) * m_per_deg_lat

    best_dist = float("inf")
    best_time = None
    best_lat = None
    best_lon = None
    best_ref_idx = 0
    best_alpha = 0.0

    # If only 1 point in window
    if len(window_pts) == 1:
        pt = window_pts[0]
        d = calculate_haversine_distance_m(target_lat, target_lon, pt.latitude, pt.longitude)
        baro_diff = (
            (pt.altitude_geom_m - pt.altitude_baro_m)
            if (pt.altitude_geom_m is not None and pt.altitude_baro_m is not None)
            else None
        )
        return ADSBInterpolatedState(
            icao24=pt.icao24,
            callsign=pt.callsign,
            cpa_timestamp=pt.timestamp,
            cpa_datetime_iso=datetime.fromtimestamp(pt.timestamp, tz=timezone.utc).isoformat(),
            cpa_latitude=pt.latitude,
            cpa_longitude=pt.longitude,
            distance_to_target_m=d,
            time_offset_s=pt.timestamp - sensing_timestamp,
            heading_deg=pt.heading_deg or 0.0,
            ground_speed_mps=pt.ground_speed_mps or 0.0,
            ground_speed_kmh=(pt.ground_speed_mps or 0.0) * MPS_TO_KMH,
            altitude_baro_m=pt.altitude_baro_m,
            altitude_geom_m=pt.altitude_geom_m,
            baro_geom_diff_m=baro_diff,
        )

    # Search each adjacent segment [k, k+1]
    for k in range(len(window_pts) - 1):
        p0 = window_pts[k]
        p1 = window_pts[k + 1]
        dt = p1.timestamp - p0.timestamp
        if dt <= 0:
            continue

        x0, y0 = to_xy(p0.latitude, p0.longitude)
        x1, y1 = to_xy(p1.latitude, p1.longitude)
        dx = x1 - x0
        dy = y1 - y0
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq < 1e-6:
            alpha = 0.0
        else:
            # Projection of origin (0, 0) onto segment p(alpha) = p0 + alpha * (p1 - p0)
            # Minimize (x0 + alpha*dx)^2 + (y0 + alpha*dy)^2
            alpha = -(x0 * dx + y0 * dy) / seg_len_sq
            alpha = max(0.0, min(1.0, alpha))

        # Coordinates at alpha
        xi = x0 + alpha * dx
        yi = y0 + alpha * dy
        dist = math.hypot(xi, yi)

        if dist < best_dist:
            best_dist = dist
            best_alpha = alpha
            best_ref_idx = k
            best_time = p0.timestamp + alpha * dt
            best_lat = p0.latitude + alpha * (p1.latitude - p0.latitude)
            best_lon = p0.longitude + alpha * (p1.longitude - p0.longitude)

    if best_time is None:
        return None

    # Interpolate scalar state variables at CPA
    p0 = window_pts[best_ref_idx]
    p1 = window_pts[best_ref_idx + 1]
    a = best_alpha

    # Heading interpolation (shortest circular path)
    h0 = p0.heading_deg or 0.0
    h1 = p1.heading_deg or h0
    dh = ((h1 - h0 + 180.0) % 360.0) - 180.0
    cpa_heading = (h0 + a * dh + 360.0) % 360.0

    # Speed
    s0 = p0.ground_speed_mps or 0.0
    s1 = p1.ground_speed_mps or s0
    cpa_speed_mps = s0 + a * (s1 - s0)

    # Altitudes
    cpa_baro = None
    if p0.altitude_baro_m is not None and p1.altitude_baro_m is not None:
        cpa_baro = p0.altitude_baro_m + a * (p1.altitude_baro_m - p0.altitude_baro_m)
    elif p0.altitude_baro_m is not None:
        cpa_baro = p0.altitude_baro_m

    cpa_geom = None
    if p0.altitude_geom_m is not None and p1.altitude_geom_m is not None:
        cpa_geom = p0.altitude_geom_m + a * (p1.altitude_geom_m - p0.altitude_geom_m)
    elif p0.altitude_geom_m is not None:
        cpa_geom = p0.altitude_geom_m

    baro_diff = (cpa_geom - cpa_baro) if (cpa_geom is not None and cpa_baro is not None) else None

    # Refine exact geodesic distance
    exact_dist_m = calculate_haversine_distance_m(target_lat, target_lon, best_lat, best_lon)

    return ADSBInterpolatedState(
        icao24=p0.icao24,
        callsign=p0.callsign or p1.callsign,
        cpa_timestamp=best_time,
        cpa_datetime_iso=datetime.fromtimestamp(best_time, tz=timezone.utc).isoformat(),
        cpa_latitude=best_lat,
        cpa_longitude=best_lon,
        distance_to_target_m=exact_dist_m,
        time_offset_s=best_time - sensing_timestamp,
        heading_deg=cpa_heading,
        ground_speed_mps=cpa_speed_mps,
        ground_speed_kmh=cpa_speed_mps * MPS_TO_KMH,
        altitude_baro_m=cpa_baro,
        altitude_geom_m=cpa_geom,
        baro_geom_diff_m=baro_diff,
    )


def validate_adsb(
    vectors: list[ADSBStateVector],
    target_lat: float,
    target_lon: float,
    sensing_timestamp: float,
    measured_heading_red_first: float,
    speed_kmh_red_first: float,
    speed_min_kmh_red_first: float,
    speed_max_kmh_red_first: float,
    criteria: ADSBValidationCriteria,
    measured_heading_blue_first: float | None = None,
    speed_kmh_blue_first: float | None = None,
    speed_min_kmh_blue_first: float | None = None,
    speed_max_kmh_blue_first: float | None = None,
    apparent_speed_mps: float | None = None,
    apparent_heading_deg: float | None = None,
    delta_t_s: float = 1.005,
) -> ADSBValidationReport:
    """Validate satellite observations against ADS-B state vectors without post-hoc tuning.

    Evaluates both 'red-first' and 'blue-first' hypotheses strictly against the
    pre-established criteria.
    """
    iso_time = datetime.fromtimestamp(sensing_timestamp, tz=timezone.utc).isoformat()

    # Fallback blue-first parameters if not explicitly provided
    if measured_heading_blue_first is None:
        measured_heading_blue_first = (measured_heading_red_first + 180.0) % 360.0
    if speed_kmh_blue_first is None:
        speed_kmh_blue_first = speed_kmh_red_first
        speed_min_kmh_blue_first = speed_min_kmh_red_first
        speed_max_kmh_blue_first = speed_max_kmh_red_first

    # Group vectors by aircraft (icao24)
    aircraft_groups: dict[str, list[ADSBStateVector]] = {}
    for v in vectors:
        aircraft_groups.setdefault(v.icao24, []).append(v)

    # Find CPA for each aircraft
    candidates: list[ADSBInterpolatedState] = []
    for group in aircraft_groups.values():
        cpa = interpolate_track_cpa(
            group,
            target_lat=target_lat,
            target_lon=target_lon,
            sensing_timestamp=sensing_timestamp,
            time_window_s=criteria.time_window_s,
        )
        if cpa is not None and cpa.distance_to_target_m <= criteria.max_distance_m:
            candidates.append(cpa)

    if not candidates:
        return ADSBValidationReport(
            target_lat=target_lat,
            target_lon=target_lon,
            sensing_timestamp=sensing_timestamp,
            sensing_datetime_iso=iso_time,
            criteria=criteria,
            status=MatchStatus.NO_DATA_OR_NO_MATCH,
            best_candidate=None,
            red_first=None,
            blue_first=None,
            recalculated_parallax_speed_kmh=None,
            recalculated_parallax_diff_kmh=None,
            recalculated_parallax_heading_deg=None,
            message=(
                f"No aircraft found within max distance {criteria.max_distance_m:.0f} m "
                f"and time window ±{criteria.time_window_s:.0f} s. Aircraft transponder may be "
                f"off, not ADS-B Out equipped, or outside receiver station coverage."
            ),
        )

    # Best match is the one with minimum distance to target
    candidates.sort(key=lambda c: c.distance_to_target_m)
    best = candidates[0]

    # Evaluate red-first
    diff_h_red = ((measured_heading_red_first - best.heading_deg + 180.0) % 360.0) - 180.0
    h_compat_red = abs(diff_h_red) <= criteria.heading_tolerance_deg
    s_compat_red = speed_min_kmh_red_first <= best.ground_speed_kmh <= speed_max_kmh_red_first
    d_compat = best.distance_to_target_m <= criteria.max_distance_m
    overall_red = h_compat_red and s_compat_red and d_compat

    red_comp = HypothesisComparison(
        band_order="red-first",
        measured_heading_deg=measured_heading_red_first,
        heading_diff_deg=diff_h_red,
        heading_compatible=h_compat_red,
        measured_speed_kmh=speed_kmh_red_first,
        speed_min_kmh=speed_min_kmh_red_first,
        speed_max_kmh=speed_max_kmh_red_first,
        adsb_speed_kmh=best.ground_speed_kmh,
        speed_diff_kmh=speed_kmh_red_first - best.ground_speed_kmh,
        speed_compatible=s_compat_red,
        distance_m=best.distance_to_target_m,
        distance_compatible=d_compat,
        overall_compatible=overall_red,
    )

    # Evaluate blue-first
    diff_h_blue = ((measured_heading_blue_first - best.heading_deg + 180.0) % 360.0) - 180.0
    h_compat_blue = abs(diff_h_blue) <= criteria.heading_tolerance_deg
    s_compat_blue = speed_min_kmh_blue_first <= best.ground_speed_kmh <= speed_max_kmh_blue_first
    overall_blue = h_compat_blue and s_compat_blue and d_compat

    blue_comp = HypothesisComparison(
        band_order="blue-first",
        measured_heading_deg=measured_heading_blue_first,
        heading_diff_deg=diff_h_blue,
        heading_compatible=h_compat_blue,
        measured_speed_kmh=speed_kmh_blue_first,
        speed_min_kmh=speed_min_kmh_blue_first,
        speed_max_kmh=speed_max_kmh_blue_first,
        adsb_speed_kmh=best.ground_speed_kmh,
        speed_diff_kmh=speed_kmh_blue_first - best.ground_speed_kmh,
        speed_compatible=s_compat_blue,
        distance_m=best.distance_to_target_m,
        distance_compatible=d_compat,
        overall_compatible=overall_blue,
    )

    # Determine status
    if overall_red and not overall_blue:
        status = MatchStatus.COMPATIBLE_RED_FIRST
        msg = f"Match confirmed with {best.callsign or best.icao24}: strictly compatible with 'red-first'."
    elif overall_blue and not overall_red:
        status = MatchStatus.COMPATIBLE_BLUE_FIRST
        msg = f"Match confirmed with {best.callsign or best.icao24}: strictly compatible with 'blue-first'."
    elif overall_red and overall_blue:
        status = MatchStatus.AMBIGUOUS_BOTH
        msg = f"Ambiguous match with {best.callsign or best.icao24}: both hypotheses pass criteria."
    else:
        status = MatchStatus.INCOMPATIBLE_NEITHER
        msg = (
            f"Nearest aircraft {best.callsign or best.icao24} at {best.distance_to_target_m:.0f} m "
            f"is incompatible with both hypotheses (heading or speed out of bounds)."
        )

    # Recalculate parallax if high altitude target and apparent parameters provided
    recalc_speed = None
    recalc_diff = None
    recalc_hdg = None
    if apparent_speed_mps is not None and apparent_heading_deg is not None:
        real_alt_m = best.altitude_geom_m or best.altitude_baro_m
        if real_alt_m is not None and real_alt_m > 1000.0:
            px = correct_parallax(
                apparent_speed_mps=apparent_speed_mps,
                apparent_heading_deg=apparent_heading_deg,
                altitude_m=real_alt_m,
                band_order="red-first",
                delta_t_s=delta_t_s,
            )
            recalc_speed = px.corrected_speed_kmh
            recalc_hdg = px.corrected_heading_deg
            recalc_diff = recalc_speed - best.ground_speed_kmh

    return ADSBValidationReport(
        target_lat=target_lat,
        target_lon=target_lon,
        sensing_timestamp=sensing_timestamp,
        sensing_datetime_iso=iso_time,
        criteria=criteria,
        status=status,
        best_candidate=best,
        red_first=red_comp,
        blue_first=blue_comp,
        recalculated_parallax_speed_kmh=recalc_speed,
        recalculated_parallax_diff_kmh=recalc_diff,
        recalculated_parallax_heading_deg=recalc_hdg,
        message=msg,
    )
