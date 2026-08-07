"""Unit tests for pure NSMA formatting, parsing, and comparison helpers."""

import pytest

from antenna_models import AntennaPattern, PatternCut
from nsma import (
    compare_patterns,
    fmt,
    fmt_signed,
    nsma_polarization,
    nsma_tilt,
    split_gain,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "0.000"),
        (-0.0, "0.000"),
        (1e-10, "0.000"),
        (3.5, "+3.500"),
        (-3.5, "-3.500"),
    ],
)
def test_fmt(value, expected):
    assert fmt(value) == expected


def test_fmt_signed_always_includes_sign():
    assert fmt_signed(0.0) == "+0.000"
    assert fmt_signed(-1.25) == "-1.250"


def test_split_gain_parses_value_and_units():
    assert split_gain("14.5 dBi") == ("14.5", "DBI")


def test_split_gain_rejects_malformed_input():
    with pytest.raises(ValueError):
        split_gain("14.5")


@pytest.mark.parametrize(
    ("polarization", "expected"),
    [("Vertical", "V/V"), ("V", "V/V"), ("Horizontal", "H/H"), ("H", "H/H")],
)
def test_nsma_polarization(polarization, expected):
    antenna = AntennaPattern(fields={"POLARIZATION": polarization})
    cut = PatternCut(source_name="PLANET", axis="AZ")
    assert nsma_polarization(antenna, cut) == expected


def test_nsma_polarization_rejects_unknown_value():
    antenna = AntennaPattern(fields={"POLARIZATION": "Circular"})
    cut = PatternCut(source_name="PLANET", axis="AZ")
    with pytest.raises(ValueError):
        nsma_polarization(antenna, cut)


def test_nsma_tilt_with_numeric_tilt_and_tolerance():
    assert nsma_tilt("2.5", "0.5") == "ELTILT:,2.5,0.5"


def test_nsma_tilt_defaults_when_not_supplied():
    assert nsma_tilt("", None) == "ELTILT:,0.0,0.0"


def test_compare_patterns_reports_no_differences_for_matching_cuts():
    planet = AntennaPattern(
        cuts=[PatternCut(source_name="PLANET", axis="AZ", points=[(0.0, -3.0)])]
    )
    nsma = AntennaPattern(
        cuts=[PatternCut(source_name="NSMA", axis="AZ", points=[(0.0, -3.0)])]
    )
    differences, compared_points = compare_patterns(planet, nsma)
    assert differences == []
    assert compared_points == 1


def test_compare_patterns_reports_value_differences():
    planet = AntennaPattern(
        cuts=[PatternCut(source_name="PLANET", axis="AZ", points=[(0.0, -3.0)])]
    )
    nsma = AntennaPattern(
        cuts=[PatternCut(source_name="NSMA", axis="AZ", points=[(0.0, -4.0)])]
    )
    differences, compared_points = compare_patterns(planet, nsma)
    assert compared_points == 1
    assert len(differences) == 1
    assert "AZ point 1 differs" in differences[0]


def test_compare_patterns_reports_mismatched_cut_sets():
    planet = AntennaPattern(
        cuts=[PatternCut(source_name="PLANET", axis="AZ", points=[(0.0, -3.0)])]
    )
    nsma = AntennaPattern(
        cuts=[PatternCut(source_name="NSMA", axis="EL", points=[(0.0, -3.0)])]
    )
    differences, compared_points = compare_patterns(planet, nsma)
    assert compared_points == 0
    assert any("Cut sets differ" in difference for difference in differences)
