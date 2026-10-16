"""Tests for constants module."""

from s2motion.constants import (
    BAND_ALIASES,
    BAND_DELAYS_S,
    CHRONOLOGICAL_GROUND_ORDER,
    CITATIONS,
    DEFAULT_PIXEL_SIZE_M,
    DELTA_T_RED_BLUE_S,
    EXPECTED_GREEN_RELATIVE_FRACTION,
    GROUND_ACQUISITION_TIMING_S,
)


def test_band_delays_and_ground_timing() -> None:
    """Verify raw band delays and chronological ground acquisition timing."""
    assert BAND_DELAYS_S["B02"] == 0.000
    assert BAND_DELAYS_S["B08"] == 0.264
    assert BAND_DELAYS_S["B03"] == 0.527
    assert BAND_DELAYS_S["B04"] == 1.005

    # Ground acquisition timing (Red first -> Green -> NIR -> Blue last)
    assert GROUND_ACQUISITION_TIMING_S["red"] == 0.000
    assert abs(GROUND_ACQUISITION_TIMING_S["green"] - 0.478) < 1e-4
    assert abs(GROUND_ACQUISITION_TIMING_S["nir"] - 0.741) < 1e-4
    assert abs(GROUND_ACQUISITION_TIMING_S["blue"] - 1.005) < 1e-4
    assert CHRONOLOGICAL_GROUND_ORDER == ("red", "green", "blue")


def test_delta_t_and_expected_fraction() -> None:
    """Verify computed delta t and theoretical relative fraction of green."""
    assert abs(DELTA_T_RED_BLUE_S - 1.005) < 1e-6
    # (0.478 / 1.005) ~= 0.47562
    assert abs(EXPECTED_GREEN_RELATIVE_FRACTION - (0.478 / 1.005)) < 1e-6
    assert 0.47 < EXPECTED_GREEN_RELATIVE_FRACTION < 0.48


def test_band_aliases_and_gsd() -> None:
    """Verify alias mapping and default GSD."""
    assert BAND_ALIASES["red"] == "B04"
    assert BAND_ALIASES["green"] == "B03"
    assert BAND_ALIASES["nir"] == "B08"
    assert BAND_ALIASES["blue"] == "B02"
    assert DEFAULT_PIXEL_SIZE_M == 10.0


def test_citations_content() -> None:
    """Verify verified citations are fully populated."""
    assert "krauss_2021" in CITATIONS
    assert "binet_2022" in CITATIONS
    assert "Thomas Krauß" in CITATIONS["krauss_2021"]["authors"]
    assert "10.5194/isprs-annals-V-1-2021-17-2021" == CITATIONS["krauss_2021"]["doi"]
    assert "10.5194/isprs-annals-V-1-2022-57-2022" == CITATIONS["binet_2022"]["doi"]
