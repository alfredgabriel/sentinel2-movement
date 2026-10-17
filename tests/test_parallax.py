"""Tests for stereoscopic parallax correction module."""

import math

import pytest

from s2motion.parallax import (
    calculate_satellite_ground_track,
    correct_parallax,
)


class TestSatelliteGroundTrack:
    """Validate satellite velocity parameters derived from orbital mechanics."""

    def test_orbital_and_ground_track_speed_bilbao(self) -> None:
        """Verify ground track kinematics at Bilbao latitude (~43.3 deg)."""
        track = calculate_satellite_ground_track(latitude_deg=43.3)

        # Orbital speed: sqrt(mu / a) ~= 7462.8 m/s
        assert 7460.0 < track.orbital_speed_mps < 7465.0
        assert math.isclose(track.orbital_speed_mps, 7462.8, rel_tol=1e-3)

        # Subsatellite speed: v_orb * (R_E / a) ~= 6643.2 m/s
        assert 6640.0 < track.subsatellite_speed_mps < 6650.0

        # Earth eastward rotation speed at 43.3°: omega_E * R_E * cos(lat) ~= 338.1 m/s
        assert 335.0 < track.earth_rotation_speed_mps < 342.0

        # Ground track speed relative to Earth surface ~= 6721.0 m/s (~6.72 km/s)
        assert 6700.0 < track.ground_track_speed_mps < 6750.0
        assert math.isclose(track.ground_track_speed_mps, 6721.0, rel_tol=1e-3)

        # Ground track heading for descending pass: ~194.7 deg (towards SSW)
        assert 192.0 < track.ground_track_heading_deg < 196.0
        assert math.isclose(track.ground_track_heading_deg, 194.71, abs_tol=0.2)

        # Southward component is negative
        assert track.v_north_mps < 0.0
        # Westward relative to rotating Earth is negative
        assert track.v_east_mps < 0.0

    def test_difference_between_orbital_and_ground_track(self) -> None:
        """Document difference between orbital speed and ground track speed (~740 m/s, ~11%)."""
        track = calculate_satellite_ground_track(latitude_deg=43.3)
        diff_mps = track.orbital_speed_mps - track.ground_track_speed_mps
        assert 700.0 < diff_mps < 770.0
        rel_diff = diff_mps / track.ground_track_speed_mps
        assert 0.10 < rel_diff < 0.12


class TestSyntheticStaticElevatedTarget:
    """Validate parallax displacement magnitude and sign for static elevated target."""

    def test_static_object_at_10km_recovers_zero_speed_red_first(self) -> None:
        """For a stationary elevated object (v_true = 0), apparent motion is purely parallax.

        First band (Red) images object forward along track; trailing band (Blue) images
        it behind. The apparent displacement vector from Red to Blue points OPPOSITE
        to the ground track heading (194.7° - 180° = 14.7°).
        Under the complete pushbroom projection, apparent ground speed is (h / (H - h)) * v_track.
        """
        track = calculate_satellite_ground_track(latitude_deg=43.3)
        h = 10000.0
        H = 786000.0

        # Exact ground projection disparity for static target
        apparent_speed_mps = (h / (H - h)) * track.ground_track_speed_mps
        apparent_heading_deg = (track.ground_track_heading_deg - 180.0) % 360.0

        # Run correction under red-first
        res = correct_parallax(
            apparent_speed_mps=apparent_speed_mps,
            apparent_heading_deg=apparent_heading_deg,
            altitude_m=h,
            latitude_deg=43.3,
            band_order="red-first",
        )

        # Corrected true speed must be 0 m/s
        assert math.isclose(res.corrected_speed_mps, 0.0, abs_tol=1e-4)
        assert math.isclose(res.corrected_speed_kmh, 0.0, abs_tol=1e-3)

    def test_static_object_at_10km_recovers_zero_speed_blue_first(self) -> None:
        """Under blue-first, the leading band (Blue) still images the object forward along track.

        The vector from first exposure (Blue) to trailing exposure (Red) is directed
        opposite to the satellite ground track: (194.71 - 180) = 14.71 deg.
        Applying parallax correction with band_order='blue-first' recovers zero speed.
        """
        track = calculate_satellite_ground_track(latitude_deg=43.3)
        h = 10000.0
        H = 786000.0

        apparent_speed_mps = (h / (H - h)) * track.ground_track_speed_mps
        apparent_heading_deg = (track.ground_track_heading_deg - 180.0) % 360.0

        res = correct_parallax(
            apparent_speed_mps=apparent_speed_mps,
            apparent_heading_deg=apparent_heading_deg,
            altitude_m=h,
            latitude_deg=43.3,
            band_order="blue-first",
        )

        assert math.isclose(res.corrected_speed_mps, 0.0, abs_tol=1e-4)
        assert math.isclose(res.corrected_speed_kmh, 0.0, abs_tol=1e-3)


class TestParallaxLowAltitudeCase1:
    """Validate that parallax correction is negligible (<2 m, <1 km/h) for low approach."""

    @pytest.mark.parametrize("altitude_m", [50.0, 100.0])
    def test_case_1_approach_displacement_under_2m(self, altitude_m: float) -> None:
        """Case 1 (Bilbao approach, h=50-100 m): parallax shift is strictly < 2 m."""
        res = correct_parallax(
            apparent_speed_mps=82.0,  # ~295 km/h
            apparent_heading_deg=117.4,
            altitude_m=altitude_m,
            latitude_deg=43.3,
            band_order="red-first",
        )

        # Displacement is (h / H) * v_track * dt
        assert res.parallax_displacement_m < 2.0
        # Speed correction is negligible (< 1 km/h)
        assert abs(res.delta_speed_kmh) < 1.0
        assert math.isclose(res.corrected_speed_kmh, 295.2, abs_tol=1.0)


class TestParallaxHighAltitudeCase2:
    """Validate Case 2 high-altitude parallax correction outputs."""

    def test_case_2_nominal_10500m_red_first(self) -> None:
        """Case 2 under red-first at nominal FL345 (10.5 km) with complete model."""
        res = correct_parallax(
            apparent_speed_mps=319.82,  # 1151.3 km/h
            apparent_heading_deg=330.4,
            altitude_m=10500.0,
            altitude_min_m=9000.0,
            altitude_max_m=12000.0,
            latitude_deg=43.3,
            band_order="red-first",
        )

        # Complete model produces 932.4 km/h (+/- 1 km/h)
        assert 931.0 < res.corrected_speed_kmh < 934.0
        assert math.isclose(res.corrected_speed_kmh, 932.4, abs_tol=0.5)

        # True heading is ~316.4 deg
        assert 315.5 < res.corrected_heading_deg < 317.5

        # Speed delta is ~ -219 km/h
        assert math.isclose(res.delta_speed_kmh, -218.9, abs_tol=0.5)

        # Range [9000, 12000] m spans 907 - 960 km/h
        assert res.corrected_speed_min_kmh is not None
        assert res.corrected_speed_max_kmh is not None
        assert 905.0 < res.corrected_speed_min_kmh < 908.0
        assert 958.0 < res.corrected_speed_max_kmh < 961.0

    def test_case_2_nominal_10500m_blue_first(self) -> None:
        """Case 2 counter-hypothesis under blue-first at nominal FL345 (10.5 km)."""
        res = correct_parallax(
            apparent_speed_mps=319.82,  # 1151.3 km/h
            apparent_heading_deg=150.4,
            altitude_m=10500.0,
            altitude_min_m=9000.0,
            altitude_max_m=12000.0,
            latitude_deg=43.3,
            band_order="blue-first",
        )

        # Blue-first reinforces velocity -> supersonic 1385.8 km/h (+/- 1 km/h)
        assert 1384.0 < res.corrected_speed_kmh < 1387.0
        assert math.isclose(res.corrected_speed_kmh, 1385.8, abs_tol=0.5)

        # True heading is ~159.8 deg
        assert 158.5 < res.corrected_heading_deg < 161.0

        # Speed delta is ~ +234 km/h
        assert math.isclose(res.delta_speed_kmh, 234.4, abs_tol=0.5)

        # Range [9000, 12000] m spans 1350 - 1422 km/h
        assert res.corrected_speed_min_kmh is not None
        assert res.corrected_speed_max_kmh is not None
        assert 1349.0 < res.corrected_speed_min_kmh < 1352.0
        assert 1420.0 < res.corrected_speed_max_kmh < 1423.0

    def test_linear_vs_complete_model_difference(self) -> None:
        """Document that simplified linear model differs by ~15 km/h at 10.5 km cruise."""
        res_complete = correct_parallax(
            apparent_speed_mps=319.82,
            apparent_heading_deg=330.4,
            altitude_m=10500.0,
            latitude_deg=43.3,
            band_order="red-first",
        )
        # Simplified linear approximation: v_true = v_app + (h / H) * v_track
        track = calculate_satellite_ground_track(latitude_deg=43.3)
        head_rad = math.radians(330.4)
        v_app_n = 319.82 * math.cos(head_rad)
        v_app_e = 319.82 * math.sin(head_rad)
        scale = 10500.0 / 786000.0
        v_lin_n = v_app_n + scale * track.v_north_mps
        v_lin_e = v_app_e + scale * track.v_east_mps
        v_lin_kmh = math.hypot(v_lin_n, v_lin_e) * 3.6

        diff_kmh = v_lin_kmh - res_complete.corrected_speed_kmh
        # Difference is approximately 14.9 km/h (~15 km/h)
        assert 14.0 < diff_kmh < 16.0
        assert math.isclose(diff_kmh, 14.9, abs_tol=0.5)


class TestParallaxErrorsAndEdgeCases:
    """Validate edge cases and error handling in parallax module."""

    def test_negative_altitude_raises_error(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            correct_parallax(
                apparent_speed_mps=100.0,
                apparent_heading_deg=90.0,
                altitude_m=-500.0,
            )

    def test_inverted_altitude_range_raises_error(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            correct_parallax(
                apparent_speed_mps=100.0,
                apparent_heading_deg=90.0,
                altitude_m=10000.0,
                altitude_min_m=12000.0,
                altitude_max_m=9000.0,
            )

    def test_invalid_band_order_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid band_order"):
            correct_parallax(
                apparent_speed_mps=100.0,
                apparent_heading_deg=90.0,
                altitude_m=5000.0,
                band_order="invalid-order",
            )

    def test_zero_altitude_returns_zero_delta(self) -> None:
        res = correct_parallax(
            apparent_speed_mps=100.0,
            apparent_heading_deg=45.0,
            altitude_m=0.0,
        )
        assert math.isclose(res.corrected_speed_mps, 100.0)
        assert math.isclose(res.corrected_heading_deg, 45.0)
        assert math.isclose(res.delta_speed_kmh, 0.0)
        assert math.isclose(res.parallax_displacement_m, 0.0)
