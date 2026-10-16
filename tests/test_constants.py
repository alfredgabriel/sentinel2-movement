"""Tests for constants module."""

from s2motion.constants import (
    BAND_ALIASES,
    BAND_DELAYS_S,
    CHRONOLOGICAL_BAND_ORDER,
    CITATIONS,
    DEFAULT_PIXEL_SIZE_M,
    DELTA_T_BLUE_RED_S,
    EXPECTED_GREEN_RELATIVE_FRACTION,
)


def test_band_delays_and_order() -> None:
    """Verify band delay values and chronological order."""
    assert BAND_DELAYS_S["B02"] == 0.000
    assert BAND_DELAYS_S["B08"] == 0.264
    assert BAND_DELAYS_S["B03"] == 0.527
    assert BAND_DELAYS_S["B04"] == 1.005

    # Check ascending chronological order
    delays = [BAND_DELAYS_S[b] for b in CHRONOLOGICAL_BAND_ORDER]
    assert delays == sorted(delays)
    assert CHRONOLOGICAL_BAND_ORDER == ("B02", "B08", "B03", "B04")


def test_delta_t_and_expected_fraction() -> None:
    """Verify computed delta t and theoretical relative fraction of green."""
    assert abs(DELTA_T_BLUE_RED_S - 1.005) < 1e-6
    # 0.527 / 1.005 ~= 0.524378
    assert abs(EXPECTED_GREEN_RELATIVE_FRACTION - (0.527 / 1.005)) < 1e-6
    assert 0.52 < EXPECTED_GREEN_RELATIVE_FRACTION < 0.53


def test_band_aliases_and_gsd() -> None:
    """Verify alias mapping and default GSD."""
    assert BAND_ALIASES["blue"] == "B02"
    assert BAND_ALIASES["green"] == "B03"
    assert BAND_ALIASES["red"] == "B04"
    assert BAND_ALIASES["nir"] == "B08"
    assert DEFAULT_PIXEL_SIZE_M == 10.0


def test_citations_content() -> None:
    """Verify verified citations are fully populated."""
    assert "krauss_2021" in CITATIONS
    assert "binet_2022" in CITATIONS
    assert "Thomas Krauß" in CITATIONS["krauss_2021"]["authors"]
    assert "10.5194/isprs-annals-V-1-2021-17-2021" == CITATIONS["krauss_2021"]["doi"]
    assert "10.5194/isprs-annals-V-1-2022-57-2022" == CITATIONS["binet_2022"]["doi"]
