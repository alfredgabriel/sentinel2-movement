"""Unit tests for the offline ADS-B trajectory validation module."""

import json
from pathlib import Path

import pytest

from s2motion.adsb import (
    ADSBStateVector,
    ADSBValidationCriteria,
    MatchStatus,
    calculate_haversine_distance_m,
    interpolate_track_cpa,
    parse_adsbx_json,
    parse_opensky_csv,
    parse_timestamp,
    validate_adsb,
)
from s2motion.cli import main


def test_parse_timestamp_formats() -> None:
    """Verify numeric epoch, string numeric, and ISO-8601 parsing."""
    t_num = 1718968180.0
    assert parse_timestamp(t_num) == 1718968180.0
    assert parse_timestamp("1718968180") == 1718968180.0
    assert parse_timestamp("2026-06-21T11:09:40Z") == 1782040180.0


def test_haversine_distance() -> None:
    """Verify great-circle distance calculation."""
    # Bilbao Airport to nearby point ~1 km away
    d = calculate_haversine_distance_m(43.300, -2.900, 43.309, -2.900)
    assert 990.0 < d < 1010.0


def test_parse_opensky_csv(tmp_path: Path) -> None:
    """Verify parsing OpenSky Network state vectors CSV format."""
    csv_file = tmp_path / "opensky_sample.csv"
    csv_file.write_text(
        "time,icao24,lat,lon,velocity,heading,vertrate,callsign,onground,baroaltitude,geoaltitude\n"
        "1782040180,3442c5,43.31077,-2.93687,82.0,117.4,-3.5,IBE420,False,150.0,158.0\n",
        encoding="utf-8",
    )
    records = parse_opensky_csv(csv_file)
    assert len(records) == 1
    rec = records[0]
    assert rec.icao24 == "3442c5"
    assert rec.callsign == "IBE420"
    assert abs(rec.latitude - 43.31077) < 1e-4
    assert abs(rec.ground_speed_mps - 82.0) < 1e-4
    assert abs(rec.heading_deg - 117.4) < 1e-4
    assert rec.altitude_baro_m == 150.0
    assert rec.altitude_geom_m == 158.0


def test_parse_adsbx_json(tmp_path: Path) -> None:
    """Verify parsing ADS-B Exchange JSON format with units conversion."""
    json_file = tmp_path / "adsbx_sample.json"
    data = {
        "now": 1782040180.0,
        "aircraft": [
            {
                "hex": "4ca854",
                "flight": "RYR123",
                "lat": 43.3023,
                "lon": -2.9187,
                "seen_pos": 0.0,
                "alt_baro": 35000,  # feet
                "alt_geom": 35400,  # feet
                "gs": 460.0,  # knots
                "track": 316.5,
            }
        ],
    }
    json_file.write_text(json.dumps(data), encoding="utf-8")
    records = parse_adsbx_json(json_file)
    assert len(records) == 1
    rec = records[0]
    assert rec.icao24 == "4ca854"
    assert rec.callsign == "RYR123"
    # 35000 ft * 0.3048 = 10668 m
    assert abs(rec.altitude_baro_m - 10668.0) < 1.0
    # 460 kt * 0.514444 = ~236.6 m/s
    assert abs(rec.ground_speed_mps - (460.0 * 0.5144444444444445)) < 0.1
    assert abs(rec.heading_deg - 316.5) < 0.1


def test_interpolate_track_cpa_exact_match() -> None:
    """Verify finding the exact Closest Point of Approach (CPA) on a trajectory."""
    t_target = 1000.0
    # Aircraft flying southeast across target at t=1000.0
    v1 = ADSBStateVector(
        timestamp=990.0,
        icao24="abc123",
        callsign="TEST01",
        latitude=43.320,
        longitude=-2.950,
        altitude_baro_m=200.0,
        altitude_geom_m=210.0,
        ground_speed_mps=80.0,
        heading_deg=117.0,
    )
    v2 = ADSBStateVector(
        timestamp=1010.0,
        icao24="abc123",
        callsign="TEST01",
        latitude=43.300,
        longitude=-2.920,
        altitude_baro_m=100.0,
        altitude_geom_m=105.0,
        ground_speed_mps=80.0,
        heading_deg=117.0,
    )
    # Target is halfway between v1 and v2: lat 43.310, lon -2.935
    target_lat = (43.320 + 43.300) / 2.0
    target_lon = (-2.950 + -2.920) / 2.0

    cpa = interpolate_track_cpa(
        [v1, v2],
        target_lat=target_lat,
        target_lon=target_lon,
        sensing_timestamp=t_target,
        time_window_s=60.0,
    )
    assert cpa is not None
    assert abs(cpa.cpa_timestamp - 1000.0) < 0.5
    assert abs(cpa.time_offset_s - 0.0) < 0.5
    assert cpa.distance_to_target_m < 50.0
    assert abs(cpa.altitude_baro_m - 150.0) < 1.0
    assert abs(cpa.ground_speed_mps - 80.0) < 1.0


def test_validate_adsb_case1_compatible_red_first() -> None:
    """Verify Case 1 (final approach) matches red-first and rejects blue-first."""
    t_sensing = 1782040180.0
    lat_target = 43.310770
    lon_target = -2.936874

    # Trajectory crossing target at t_sensing with speed 82 m/s (295 km/h) and heading 117.4°
    v1 = ADSBStateVector(
        timestamp=t_sensing - 10.0,
        icao24="3442c5",
        callsign="IBE420",
        latitude=lat_target + 0.003,
        longitude=lon_target - 0.006,
        altitude_baro_m=150.0,
        altitude_geom_m=160.0,
        ground_speed_mps=82.0,
        heading_deg=117.4,
    )
    v2 = ADSBStateVector(
        timestamp=t_sensing + 10.0,
        icao24="3442c5",
        callsign="IBE420",
        latitude=lat_target - 0.003,
        longitude=lon_target + 0.006,
        altitude_baro_m=80.0,
        altitude_geom_m=88.0,
        ground_speed_mps=82.0,
        heading_deg=117.4,
    )

    criteria = ADSBValidationCriteria(
        max_distance_m=1000.0,
        time_window_s=60.0,
        heading_tolerance_deg=14.0,  # 2-sigma (~2 * 7.0 deg)
    )

    report = validate_adsb(
        vectors=[v1, v2],
        target_lat=lat_target,
        target_lon=lon_target,
        sensing_timestamp=t_sensing,
        measured_heading_red_first=117.4,
        speed_kmh_red_first=295.0,
        speed_min_kmh_red_first=254.0,
        speed_max_kmh_red_first=338.0,
        criteria=criteria,
    )

    assert report.status == MatchStatus.COMPATIBLE_RED_FIRST
    assert report.best_candidate is not None
    assert report.best_candidate.callsign == "IBE420"
    assert report.red_first.overall_compatible is True
    assert report.blue_first.overall_compatible is False
    assert abs(report.red_first.heading_diff_deg) < 1.0
    assert "COMPATIBLE_RED_FIRST" in report.summary()


def test_validate_adsb_case2_with_real_altitude_recalculation() -> None:
    """Verify Case 2 cruising aircraft with real ADS-B altitude recalculating parallax speed."""
    t_sensing = 1782040180.0
    lat_target = 43.302306
    lon_target = -2.918740

    # Real flight at 10,800 m geometric altitude flying heading 316.5° at 930 km/h (258.3 m/s)
    v1 = ADSBStateVector(
        timestamp=t_sensing - 5.0,
        icao24="4ca854",
        callsign="RYR999",
        latitude=lat_target - 0.005,
        longitude=lon_target + 0.005,
        altitude_baro_m=10668.0,  # 35,000 ft
        altitude_geom_m=10800.0,  # 10,800 m geometric
        ground_speed_mps=258.33,  # 930 km/h
        heading_deg=316.5,
    )
    v2 = ADSBStateVector(
        timestamp=t_sensing + 5.0,
        icao24="4ca854",
        callsign="RYR999",
        latitude=lat_target + 0.005,
        longitude=lon_target - 0.005,
        altitude_baro_m=10668.0,
        altitude_geom_m=10800.0,
        ground_speed_mps=258.33,
        heading_deg=316.5,
    )

    criteria = ADSBValidationCriteria(
        max_distance_m=2000.0,  # 2 km for en-route cruise
        time_window_s=60.0,
        heading_tolerance_deg=3.6,  # 2-sigma (~2 * 1.8 deg)
    )

    report = validate_adsb(
        vectors=[v1, v2],
        target_lat=lat_target,
        target_lon=lon_target,
        sensing_timestamp=t_sensing,
        measured_heading_red_first=316.4,
        speed_kmh_red_first=932.0,
        speed_min_kmh_red_first=907.0,
        speed_max_kmh_red_first=960.0,
        criteria=criteria,
        apparent_speed_mps=319.81,
        apparent_heading_deg=330.41,
    )

    assert report.status == MatchStatus.COMPATIBLE_RED_FIRST
    assert report.recalculated_parallax_speed_kmh is not None
    # Recalculated with real altitude 10,800 m should be close to 930 km/h
    assert abs(report.recalculated_parallax_speed_kmh - 930.0) < 15.0
    assert abs(report.recalculated_parallax_diff_kmh) < 15.0
    assert "Parallax Recalculation with Real ADS-B Altitude:" in report.summary()


def test_validate_adsb_no_match_informative_out_of_window() -> None:
    """Verify that an aircraft passing 5 minutes earlier returns informative NO_DATA_OR_NO_MATCH."""
    t_sensing = 1000.0
    v = ADSBStateVector(
        timestamp=t_sensing - 300.0,  # 5 minutes earlier
        icao24="abc123",
        callsign="EARLY01",
        latitude=43.310,
        longitude=-2.936,
        altitude_baro_m=150.0,
        altitude_geom_m=160.0,
        ground_speed_mps=82.0,
        heading_deg=117.4,
    )
    criteria = ADSBValidationCriteria(max_distance_m=1000.0, time_window_s=60.0)

    report = validate_adsb(
        vectors=[v],
        target_lat=43.310,
        target_lon=-2.936,
        sensing_timestamp=t_sensing,
        measured_heading_red_first=117.4,
        speed_kmh_red_first=295.0,
        speed_min_kmh_red_first=254.0,
        speed_max_kmh_red_first=338.0,
        criteria=criteria,
    )

    assert report.status == MatchStatus.NO_DATA_OR_NO_MATCH
    assert report.best_candidate is None
    assert "No aircraft found" in report.message


def test_validate_adsb_no_match_out_of_spatial_radius() -> None:
    """Verify that an aircraft passing 10 km away returns informative NO_DATA_OR_NO_MATCH."""
    t_sensing = 1000.0
    v = ADSBStateVector(
        timestamp=t_sensing,
        icao24="abc123",
        callsign="FAR01",
        latitude=43.400,  # ~10 km North
        longitude=-2.936,
        altitude_baro_m=150.0,
        altitude_geom_m=160.0,
        ground_speed_mps=82.0,
        heading_deg=117.4,
    )
    criteria = ADSBValidationCriteria(max_distance_m=1000.0, time_window_s=60.0)

    report = validate_adsb(
        vectors=[v],
        target_lat=43.310,
        target_lon=-2.936,
        sensing_timestamp=t_sensing,
        measured_heading_red_first=117.4,
        speed_kmh_red_first=295.0,
        speed_min_kmh_red_first=254.0,
        speed_max_kmh_red_first=338.0,
        criteria=criteria,
    )

    assert report.status == MatchStatus.NO_DATA_OR_NO_MATCH


def test_validate_adsb_incompatible_neither() -> None:
    """Verify nearest aircraft flying opposite direction and incompatible speed."""
    t_sensing = 1000.0
    v = ADSBStateVector(
        timestamp=t_sensing,
        icao24="abc123",
        callsign="CROSS01",
        latitude=43.310,
        longitude=-2.936,
        altitude_baro_m=150.0,
        altitude_geom_m=160.0,
        ground_speed_mps=150.0,  # 540 km/h (way too fast for approach)
        heading_deg=0.0,  # North (incompatible with 117° and 297°)
    )
    criteria = ADSBValidationCriteria(
        max_distance_m=1000.0,
        time_window_s=60.0,
        heading_tolerance_deg=14.0,
    )

    report = validate_adsb(
        vectors=[v],
        target_lat=43.310,
        target_lon=-2.936,
        sensing_timestamp=t_sensing,
        measured_heading_red_first=117.4,
        speed_kmh_red_first=295.0,
        speed_min_kmh_red_first=254.0,
        speed_max_kmh_red_first=338.0,
        criteria=criteria,
    )

    assert report.status == MatchStatus.INCOMPATIBLE_NEITHER
    assert report.red_first.overall_compatible is False
    assert report.blue_first.overall_compatible is False


def test_cli_validate_with_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify s2motion validate CLI execution using loiu_2026-08-12.toml config."""
    csv_file = tmp_path / "flight_test.csv"
    csv_file.write_text(
        "time,icao24,lat,lon,velocity,heading,vertrate,callsign,onground,baroaltitude,geoaltitude\n"
        "1786532980,3442c5,43.31077,-2.93687,82.0,117.4,-3.5,IBE420,False,150.0,158.0\n",
        encoding="utf-8",
    )

    rc = main(["validate", "--adsb", str(csv_file), "--config", "examples/loiu_2026-08-12.toml"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Sentinel-2 Moving Object ADS-B Validation Report" in captured.out
    assert "COMPATIBLE_RED_FIRST" in captured.out
