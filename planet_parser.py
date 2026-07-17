"""Parser for PLANET ASCII antenna-pattern files."""

from antenna_models import AntennaPattern, PatternCut

PLANET_HEADER_FIELDS = {
    "NAME",
    "MAKE",
    "FREQUENCY",
    "COMMENT",
    "H_WIDTH",
    "V_WIDTH",
    "FRONT_TO_BACK",
    "GAIN",
    "TILT",
    "POLARIZATION",
}

PATTERN_TYPES = {
    "HORIZONTAL": "H",
    "VERTICAL": "V",
}

TILTED_PATTERN_TYPES = {
    "HORIZONTAL": "AZ",
    "VERTICAL": "EL",
}


def parse_planet(path):
    """Parse a PLANET file into a normalized :class:`AntennaPattern`.

    PLANET stores attenuation as positive values. Pattern levels are negated
    during parsing so the shared model and NSMA output use relative dB levels.
    Untilited HORIZONTAL/VERTICAL cuts map to NSMA H/V; tilted cuts map to
    NSMA AZ/EL as defined by WG16.99.050.
    """

    antenna = AntennaPattern()

    with path.open(newline="", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            key, *value = line.split(maxsplit=1)
            text = value[0] if value else ""

            if key in PATTERN_TYPES:
                antenna.cuts.append(parse_pattern_cut(f, key, int(text)))
            elif key in PLANET_HEADER_FIELDS:
                antenna.fields[key] = text

    if has_tilt(antenna.fields.get("TILT", "")):
        for cut in antenna.cuts:
            cut.axis = TILTED_PATTERN_TYPES[cut.source_name]

    return antenna


def has_tilt(tilt):
    """Return whether a PLANET tilt field describes a non-zero tilt."""

    value = tilt.strip().upper()
    return value not in {"", "NONE", "NO", "0", "0.0", "0.00", "0.000"}


def parse_pattern_cut(lines, source_name, num_points):
    """Read exactly ``num_points`` pattern rows from an open PLANET stream."""

    cut = PatternCut(source_name=source_name, axis=PATTERN_TYPES[source_name])

    while len(cut.points) < num_points:
        line = next(lines).strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        try:
            angle = float(parts[0])
            attenuation = float(parts[1])
        except ValueError:
            continue

        cut.points.append((angle, -attenuation))

    return cut
