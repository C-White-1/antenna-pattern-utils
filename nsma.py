"""Read, write, and compare NSMA WG16.99.050 antenna-pattern data."""

from antenna_models import AntennaPattern, PatternCut
from nsma_standard import REVISION_DATE, STANDARD_NAME


def fmt(value):
    """Format a pattern value using the signed NSMA three-decimal form."""

    return "0.000" if abs(value) < 1e-9 else f"{value:+.3f}"


def fmt_signed(value):
    """Format a value with an explicit sign and three decimal places."""

    return f"{value:+.3f}"


def split_gain(gain_text):
    """Split a PLANET ``'<value> <units>'`` gain field into its two parts."""

    parts = gain_text.split()
    if len(parts) != 2:
        raise ValueError(f"Expected GAIN as '<value> <units>', got {gain_text!r}")
    return parts[0], parts[1].upper()


def nsma_polarization(antenna, cut):
    """Return the co-polarized NSMA designator for a PLANET antenna.

    Polarization describes the antenna-under-test and illuminating source; it
    is independent of whether the associated cut is H, V, AZ, or EL.
    """

    polarization = antenna.fields.get("POLARIZATION", "").strip().upper()

    if polarization.startswith("V"):
        return "V/V"
    if polarization.startswith("H"):
        return "H/H"

    raise ValueError(
        "Expected PLANET POLARIZATION to be Horizontal or Vertical, "
        f"got {antenna.fields.get('POLARIZATION', '')!r}"
    )


def build_nsma_lines(antenna, low_freq, high_freq):
    """Serialize an antenna as ordered WG16.99.050 records.

    Frequencies are expressed in MHz. The returned strings do not contain line
    terminators and can be passed directly to :func:`write_nsma`.
    """

    fields = antenna.fields
    gain, gain_units = split_gain(fields.get("GAIN", ""))

    lines = [
        f"REVNUM:, {STANDARD_NAME}",
        f"REVDAT:,{REVISION_DATE}",
        f"COMNT1:,{fields.get('COMMENT', '')}",
        f"ANTMAN:,{fields.get('MAKE', '')}",
        f"MODNUM:,{fields.get('NAME', '')}",
        f"LOWFRQ:,{low_freq}",
        f"HGHFRQ:,{high_freq}",
        f"GUNITS:,{gain_units}/DBR",
        f"MDGAIN:,{gain}",
    ]
    append_optional(lines, "AZWIDT", fields.get("H_WIDTH"))
    append_optional(lines, "ELWIDT", fields.get("V_WIDTH"))
    append_optional(lines, "FRTOBA", fields.get("FRONT_TO_BACK"))
    lines.extend(
        [
            nsma_tilt(fields.get("TILT", ""), fields.get("TILT_TOLERANCE")),
            f"PATTYP:,{fields.get('PATTERN_TYPE', 'typical')}",
            "NOFREQ:,1",
            f"PATFRE:,{fields.get('FREQUENCY', '')}",
            f"NUMCUT:,{len(antenna.cuts)}",
        ]
    )

    for cut in antenna.cuts:
        lines.extend(nsma_cut_lines(antenna, cut))

    lines.append("ENDFIL:,EOF")
    return lines


def append_optional(lines, tag, value):
    """Append an optional NSMA record only when it has a value."""

    if value is not None and str(value).strip():
        lines.append(f"{tag}:,{value}")


def nsma_tilt(tilt, tolerance=None):
    """Return the NSMA electrical-tilt record used by PLANET conversions.

    PLANET files in scope do not provide a numeric tilt tolerance, so the
    converter emits zero nominal tilt and zero tolerance.
    """

    supplied_numeric = True
    try:
        nominal = float(tilt)
    except (TypeError, ValueError):
        nominal = 0.0
        supplied_numeric = False
    try:
        tolerance_value = float(tolerance)
    except (TypeError, ValueError):
        tolerance_value = 0.0
    if not supplied_numeric and tolerance is None:
        return "ELTILT:,0.0,0.0"
    return f"ELTILT:,{nominal:g},{tolerance_value:g}"


def nsma_cut_lines(antenna, cut):
    """Serialize one pattern cut and all of its data points."""

    if cut.first_angle is None or cut.last_angle is None:
        raise ValueError(f"{cut.source_name} cut contains no points")

    lines = [
        f"PATCUT:,{cut.axis}",
        f"POLARI:,{nsma_polarization(antenna, cut)}",
        f"NUPOIN:,{len(cut.points)}",
        f"FSTLST:,{fmt_signed(cut.first_angle)},{fmt_signed(cut.last_angle)}",
    ]

    for angle, value in cut.points:
        lines.append(f"{fmt(angle)},{fmt(value)},")

    return lines


def write_nsma(path, lines):
    """Write NSMA records using one CRLF terminator per record."""

    data = "".join(f"{line}\r\n" for line in lines)
    path.write_bytes(data.encode("utf-8"))


def parse_nsma(path):
    """Parse the cut geometry and pattern points from an NSMA file.

    ``NUPOIN`` is validated for every cut. Descriptive records that are not
    required for plotting or point comparison are intentionally ignored.
    """

    antenna = AntennaPattern()
    expected_points = {}
    current_cut = None

    with path.open(newline="", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("MODNUM:,"):
                antenna.fields["NAME"] = line.partition(",")[2]
            elif line.startswith("PATCUT:,"):
                axis = line.partition(",")[2].strip()
                current_cut = PatternCut(source_name="NSMA", axis=axis)
                antenna.cuts.append(current_cut)
            elif line.startswith("NUPOIN:,") and current_cut is not None:
                expected_points[id(current_cut)] = int(line.partition(",")[2])
            elif current_cut is not None and not line[0].isalpha():
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                try:
                    current_cut.points.append((float(parts[0]), float(parts[1])))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid NSMA pattern point at {path}:{line_number}: {line!r}"
                    ) from exc

    if not antenna.cuts:
        raise ValueError(f"No PATCUT records found in {path}")

    for cut in antenna.cuts:
        expected = expected_points.get(id(cut))
        if expected is None:
            raise ValueError(f"{path}: {cut.axis} cut has no NUPOIN record")
        if len(cut.points) != expected:
            raise ValueError(
                f"{path}: {cut.axis} cut declares {expected} points but contains "
                f"{len(cut.points)}"
            )

    return antenna


def compare_patterns(planet_antenna, nsma_antenna, tolerance=0.0005):
    """Compare PLANET and NSMA cuts by axis, angle, and relative dB level.

    Returns ``(differences, compared_points)``. At most ten detailed
    differences are returned, followed by an omission notice when necessary.
    The default tolerance accommodates NSMA's three-decimal serialization.
    """

    differences = []
    planet_cuts = {cut.axis: cut for cut in planet_antenna.cuts}
    nsma_cuts = {cut.axis: cut for cut in nsma_antenna.cuts}

    if planet_cuts.keys() != nsma_cuts.keys():
        differences.append(
            "Cut sets differ: PLANET has "
            f"{sorted(planet_cuts)}, NSMA has {sorted(nsma_cuts)}"
        )

    compared_points = 0
    for axis in sorted(planet_cuts.keys() & nsma_cuts.keys()):
        planet_cut = planet_cuts[axis]
        nsma_cut = nsma_cuts[axis]
        if len(planet_cut.points) != len(nsma_cut.points):
            differences.append(
                f"{axis} point count differs: PLANET has {len(planet_cut.points)}, "
                f"NSMA has {len(nsma_cut.points)}"
            )
            continue

        for point_number, (planet_point, nsma_point) in enumerate(
            zip(planet_cut.points, nsma_cut.points), start=1
        ):
            compared_points += 1
            angle_difference = abs(planet_point[0] - nsma_point[0])
            level_difference = abs(planet_point[1] - nsma_point[1])
            if angle_difference > tolerance or level_difference > tolerance:
                differences.append(
                    f"{axis} point {point_number} differs: PLANET "
                    f"{planet_point}, NSMA {nsma_point}"
                )
                if len(differences) >= 10:
                    differences.append("Further differences omitted")
                    return differences, compared_points

    return differences, compared_points
