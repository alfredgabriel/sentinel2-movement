import pytest

from s2motion.constants import (
    BAND_ALIASES,
    BAND_DELAYS_S,
    CHRONOLOGICAL_GROUND_ORDER,
    CITATIONS,
    DEFAULT_PIXEL_SIZE_M,
    DELTA_T_RED_BLUE_S,
    EXPECTED_GREEN_RELATIVE_FRACTION,
    GROUND_ACQUISITION_TIMING_S,
    get_band_timing,
    get_expected_green_fraction,
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


def test_lebb_runway_constants() -> None:
    """Verify Bilbao runway threshold coordinates and geodetic heading."""
    from s2motion.constants import (
        BILBAO_RUNWAY_12_30_HEADING_DEG,
        LEBB_RUNWAY_12_THR_WGS84,
        LEBB_RUNWAY_30_THR_WGS84,
        LEBB_RUNWAY_LENGTH_M,
        LEBB_RUNWAY_WIDTH_M,
    )

    assert abs(BILBAO_RUNWAY_12_30_HEADING_DEG - 116.7) < 0.1
    assert LEBB_RUNWAY_12_THR_WGS84[0] > 43.3
    assert LEBB_RUNWAY_30_THR_WGS84[0] < 43.3
    assert LEBB_RUNWAY_LENGTH_M == 2600.0
    assert LEBB_RUNWAY_WIDTH_M == 45.0


def test_citations_content() -> None:
    """Verify verified citations are fully populated."""
    assert "krauss_2021" in CITATIONS
    assert "binet_2022" in CITATIONS
    assert "Thomas Krauß" in CITATIONS["krauss_2021"]["authors"]
    assert "10.5194/isprs-annals-V-1-2021-17-2021" == CITATIONS["krauss_2021"]["doi"]
    assert "10.5194/isprs-annals-V-1-2022-57-2022" == CITATIONS["binet_2022"]["doi"]


def test_get_band_timing_and_green_fraction() -> None:
    """Verify get_band_timing and get_expected_green_fraction for both orders."""
    # red-first
    t_red = get_band_timing("red-first")
    assert t_red["red"] == 0.000
    assert abs(t_red["green"] - 0.478) < 1e-4
    assert abs(t_red["nir"] - 0.741) < 1e-4
    assert t_red["blue"] == 1.005

    frac_red = get_expected_green_fraction("red-first")
    assert abs(frac_red - (0.478 / 1.005)) < 1e-6
    assert 0.47 < frac_red < 0.48

    # blue-first
    t_blue = get_band_timing("blue-first")
    assert t_blue["blue"] == 0.000
    assert t_blue["nir"] == 0.264
    assert t_blue["green"] == 0.527
    assert t_blue["red"] == 1.005

    frac_blue = get_expected_green_fraction("blue-first")
    assert abs(frac_blue - (0.527 / 1.005)) < 1e-6
    assert 0.52 < frac_blue < 0.53

    # invalid order
    with pytest.raises(ValueError, match="Invalid band order"):
        get_band_timing("green-first")

    with pytest.raises(ValueError, match="Invalid band order"):
        get_expected_green_fraction("invalid")
