"""Parser for EDX Wireless ASCII antenna-pattern files."""

import math
import re

from antenna_models import AntennaPattern, PatternCut

HEADER = re.compile(
    r"^\s*'([^']{1,20})'\s*,\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*([12])\s*$"
)


def parse_pair(line, description):
    """Parse a comma/space-separated numeric pair."""

    parts = [part for part in re.split(r"[\s,]+", line.strip()) if part]
    if len(parts) != 2:
        raise ValueError(f"Expected {description} as two values, got {line!r}")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise ValueError(f"Invalid {description}: {line!r}") from exc


def parse_counts(line):
    """Parse EDX ``NUM_SLICES, NELV`` values."""

    first, second = parse_pair(line, "NUM_SLICES, NELV")
    if not first.is_integer() or not second.is_integer():
        raise ValueError("NUM_SLICES and NELV must be integers")
    return int(first), int(second)


def convert_levels(points, key_pattern):
    """Convert EDX field-strength or dB values into dB."""

    converted = []
    for angle, value in points:
        if key_pattern == 1:
            if value <= 0:
                raise ValueError(
                    "Relative-field pattern values must be greater than zero"
                )
            value = 20.0 * math.log10(value)
        converted.append((angle, value))

    return converted


def normalize_levels(points):
    """Normalize dB points so their maximum is zero."""

    maximum = max(value for _, value in points)
    return [(angle, value - maximum) for angle, value in points]


def parse_edx(path):
    """Parse an EDX pattern and return an antenna plus source metadata.

    Horizontal data becomes an H cut. Two vertical slices at azimuths 0 and
    180 degrees are combined into one complete V cut using the EDX elevation
    convention validated against equivalent PLANET pattern data.
    """

    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError(f"EDX file is empty: {path}")

    header = HEADER.match(lines[0])
    if not header:
        raise ValueError("Invalid EDX header; expected 'Antenna Type', GAIN, KYPAT")
    name, gain_text, key_text = header.groups()
    gain = float(gain_text)
    key_pattern = int(key_text)

    try:
        separator = lines.index("999", 1)
    except ValueError as exc:
        raise ValueError("EDX horizontal section has no 999 separator") from exc

    horizontal = [
        parse_pair(line, "horizontal angle and pattern value")
        for line in lines[1:separator]
    ]
    validate_angles(horizontal, "horizontal", ascending=True)
    if not any(abs(angle) < 1e-9 for angle, _ in horizontal):
        raise ValueError("EDX horizontal pattern must include 0 degrees")
    if max_gap(horizontal) > 45.0 + 1e-9:
        raise ValueError("EDX horizontal azimuth increment exceeds 45 degrees")

    antenna = AntennaPattern(
        fields={
            "NAME": name,
            "GAIN": f"{gain:g} dBi",
            "EDX_KYPAT": str(key_pattern),
        }
    )
    antenna.cuts.append(
        PatternCut(
            source_name="EDX_HORIZONTAL",
            axis="H",
            points=normalize_levels(convert_levels(horizontal, key_pattern)),
        )
    )

    if separator + 1 >= len(lines):
        raise ValueError("EDX file ends before NUM_SLICES, NELV")
    number_slices, elevations_per_slice = parse_counts(lines[separator + 1])
    if number_slices == 0 and elevations_per_slice == 0:
        return antenna
    if not 1 <= number_slices <= 72:
        raise ValueError("EDX NUM_SLICES must be between 1 and 72")
    if not 5 <= elevations_per_slice <= 361:
        raise ValueError("EDX NELV must be between 5 and 361")

    slices = {}
    position = separator + 2
    reference_elevations = None
    for _ in range(number_slices):
        if position >= len(lines):
            raise ValueError("EDX file ends before all vertical slices are read")
        try:
            slice_azimuth = float(lines[position])
        except ValueError as exc:
            raise ValueError(f"Invalid EDX slice azimuth: {lines[position]!r}") from exc
        position += 1
        if not 0 <= slice_azimuth <= 360:
            raise ValueError("EDX slice azimuth must be between 0 and 360 degrees")

        points = []
        for _ in range(elevations_per_slice):
            if position >= len(lines):
                raise ValueError("EDX file ends inside a vertical slice")
            points.append(
                parse_pair(lines[position], "elevation angle and pattern value")
            )
            position += 1
        validate_angles(points, f"{slice_azimuth:g}-degree slice", ascending=False)
        elevations = [angle for angle, _ in points]
        if reference_elevations is None:
            reference_elevations = elevations
        elif elevations != reference_elevations:
            raise ValueError("All EDX vertical slices must use the same elevations")
        slices[canonical_azimuth(slice_azimuth)] = convert_levels(points, key_pattern)

    if position != len(lines):
        raise ValueError(
            f"Unexpected EDX data after vertical slices: {lines[position]!r}"
        )
    if 0.0 not in slices:
        raise ValueError("EDX vertical data must include the 0-degree slice")

    if set(slices) == {0.0, 180.0}:
        vertical = normalize_levels(combine_vertical_slices(slices[0.0], slices[180.0]))
        antenna.cuts.append(
            PatternCut(source_name="EDX_VERTICAL", axis="V", points=vertical)
        )
    else:
        raise ValueError(
            "NSMA conversion currently supports vertical data only when EDX "
            "contains exactly the 0- and 180-degree slices"
        )

    return antenna


def canonical_azimuth(value):
    """Normalize an EDX slice azimuth, treating 360 degrees as zero."""

    value %= 360.0
    return 0.0 if abs(value) < 1e-9 else value


def validate_angles(points, description, ascending):
    """Validate angle range, uniqueness, and ordering."""

    if not points:
        raise ValueError(f"EDX {description} pattern contains no points")
    angles = [angle for angle, _ in points]
    if len(angles) != len(set(angles)):
        raise ValueError(f"EDX {description} pattern contains duplicate angles")
    pairs = zip(angles, angles[1:])
    if ascending and any(right <= left for left, right in pairs):
        raise ValueError(f"EDX {description} angles must be ascending")
    if not ascending and any(right >= left for left, right in pairs):
        raise ValueError(f"EDX {description} elevations must descend")


def max_gap(points):
    """Return the largest increment in an ordered point collection."""

    angles = [angle for angle, _ in points]
    return max(right - left for left, right in zip(angles, angles[1:]))


def combine_vertical_slices(front, rear):
    """Combine EDX 0/180-degree slices into an increasing 0–359 degree V cut."""

    combined = {}
    for elevation, level in front:
        combined[(-elevation) % 360.0] = level
    for elevation, level in rear:
        combined[(180.0 + elevation) % 360.0] = level

    # Both slices can describe the same boundary direction. Equal values are
    # naturally collapsed; inconsistent duplicates indicate ambiguous input.
    expected_count = len(front) + len(rear)
    if len(combined) not in {expected_count, expected_count - 1}:
        raise ValueError("EDX vertical slices contain ambiguous duplicate directions")
    return sorted(combined.items())
