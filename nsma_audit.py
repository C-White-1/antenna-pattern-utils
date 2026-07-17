"""Audit NSMA WG16.99.050 files without modifying them."""

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from nsma_standard import (
    FIELD_ORDER,
    FIELDS,
    REVISION_DATE,
    STANDARD_NAME,
)

TAGGED_RECORD = re.compile(r"^([A-Z0-9]+):,(.*)$")
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
POINT_RECORD = re.compile(rf"^({NUMBER}),({NUMBER})(?:,({NUMBER}))?,?$")
PATTERN_CUTS = {"H", "V", "AZ", "EL"}
POLARIZATIONS = {
    "H/H",
    "H/V",
    "V/V",
    "V/H",
    "SLR/SLR",
    "SLR/SLL",
    "SLL/SLL",
    "SLL/SLR",
    "RCP/RCP",
    "RCP/LCP",
    "LCP/LCP",
    "LCP/RCP",
}


@dataclass
class Finding:
    """One audit result with severity, location, and explanatory text."""

    severity: str
    message: str
    line: int | None = None


@dataclass
class CutState:
    """Records and pattern points collected for one NSMA cut."""

    axis: str
    line: int
    declared_points: int | None = None
    first_last: tuple[float, float] | None = None
    points: list[tuple[int, float, float]] = None

    def __post_init__(self):
        """Create an independent point list for each cut."""

        if self.points is None:
            self.points = []


def load_schema(path=None):
    """Load the trusted built-in schema or an explicit external CSV override."""

    if path is None:
        fields = {
            field.abbreviation: {
                "required": field.required,
                "length": field.max_length,
            }
            for field in FIELDS
        }
        return fields, dict(FIELD_ORDER)

    with path.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    fields = {}
    order = {}
    for index, row in enumerate(rows):
        abbreviation = row["abbrev"].strip()
        fields[abbreviation] = {
            "required": row["required"].strip().upper() == "TRUE",
            "length": int(row["length"]),
        }
        order[abbreviation] = index
    return fields, order


def decode_file(path):
    """Read bytes, report encoding problems, and return decoded text."""

    findings = []
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        findings.append(
            Finding("ERROR", f"File is not valid UTF-8: {exc}", exc.start + 1)
        )
        text = data.decode("utf-8-sig", errors="replace")
    return data, text, findings


def audit_line_endings(data):
    """Check for CRLF records, mixed endings, and missing final termination."""

    findings = []
    extra_cr_count = data.count(b"\r\r\n")
    normalized = data.replace(b"\r\r\n", b"\r\n")
    crlf_count = normalized.count(b"\r\n")
    lf_only_count = normalized.count(b"\n") - crlf_count
    cr_only_count = normalized.count(b"\r") - crlf_count

    if extra_cr_count:
        findings.append(
            Finding(
                "ERROR",
                f"Found {extra_cr_count} CRCRLF record ending(s). Each record must "
                "end with one CRLF; the extra CR creates an apparent blank line.",
            )
        )
    if lf_only_count:
        findings.append(
            Finding(
                "ERROR",
                f"Found {lf_only_count} LF-only line ending(s); NSMA requires CRLF.",
            )
        )
    if cr_only_count:
        findings.append(
            Finding(
                "ERROR",
                f"Found {cr_only_count} CR-only line ending(s); NSMA requires CRLF.",
            )
        )
    if data and not normalized.endswith(b"\r\n"):
        findings.append(Finding("ERROR", "Final record is not terminated by CRLF."))
    if crlf_count and not extra_cr_count and not lf_only_count and not cr_only_count:
        findings.append(Finding("INFO", f"All {crlf_count} record ending(s) use CRLF."))
    return findings


def audit_nsma(path, schema_path):
    """Return findings from a structural and numeric audit of an NSMA file."""

    fields, field_order = load_schema(schema_path)
    point_max_length = fields["/point"]["length"]
    data, text, findings = decode_file(path)
    findings.extend(audit_line_endings(data))

    # Treat CRCRLF as a malformed record terminator, not as a real empty record,
    # so structural checks can continue without generating cascading findings.
    text = text.replace("\r\r\n", "\n")
    lines = text.splitlines()
    tagged = []
    cuts = []
    current_cut = None
    in_cut_data = False
    points_without_trailing_comma = []

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            findings.append(
                Finding(
                    "WARNING",
                    "Blank line found; CRLF terminates a record and does not require "
                    "an additional empty line.",
                    line_number,
                )
            )
            continue

        tag_match = TAGGED_RECORD.match(line)
        if tag_match:
            tag, value = tag_match.groups()
            tagged.append((line_number, tag, line))
            in_cut_data = False

            definition = fields.get(tag)
            if definition is None:
                findings.append(
                    Finding("WARNING", f"Unknown record type {tag!r}.", line_number)
                )
            elif len(line) > definition["length"]:
                findings.append(
                    Finding(
                        "ERROR",
                        f"{tag} record has {len(line)} characters; maximum is "
                        f"{definition['length']}.",
                        line_number,
                    )
                )

            if tag == "PATCUT":
                current_cut = CutState(axis=value.strip(), line=line_number)
                cuts.append(current_cut)
            elif tag == "NUPOIN" and current_cut is not None:
                try:
                    current_cut.declared_points = int(value)
                except ValueError:
                    findings.append(
                        Finding(
                            "ERROR", f"Invalid NUPOIN value {value!r}.", line_number
                        )
                    )
            elif tag == "FSTLST" and current_cut is not None:
                parts = value.split(",")
                in_cut_data = True
                try:
                    current_cut.first_last = (float(parts[0]), float(parts[1]))
                except (ValueError, IndexError):
                    findings.append(
                        Finding(
                            "ERROR", f"Invalid FSTLST value {value!r}.", line_number
                        )
                    )
            continue

        if in_cut_data and current_cut is not None:
            point_match = POINT_RECORD.match(line)
            if not point_match:
                findings.append(
                    Finding("ERROR", "Malformed pattern-point record.", line_number)
                )
                continue
            if len(line) > point_max_length:
                findings.append(
                    Finding(
                        "ERROR",
                        f"Pattern-point record has {len(line)} characters; maximum "
                        f"is {point_max_length}.",
                        line_number,
                    )
                )
            angle, level, _phase = point_match.groups()
            current_cut.points.append((line_number, float(angle), float(level)))
            if not line.endswith(","):
                points_without_trailing_comma.append(line_number)
        else:
            findings.append(
                Finding(
                    "ERROR", "Unrecognized data outside a pattern cut.", line_number
                )
            )

    audit_records(tagged, fields, field_order, findings)
    audit_record_values(tagged, findings)
    audit_cuts(tagged, cuts, findings)
    if points_without_trailing_comma:
        first_line = points_without_trailing_comma[0]
        findings.append(
            Finding(
                "ERROR",
                f"{len(points_without_trailing_comma)} pattern-point record(s) omit "
                "the required trailing comma.",
                first_line,
            )
        )
    return findings


def audit_records(tagged, fields, field_order, findings):
    """Validate required fields, record ordering, and singleton duplication."""

    present = Counter(tag for _, tag, _ in tagged)
    for tag, definition in fields.items():
        if definition["required"] and tag != "/point" and present[tag] == 0:
            findings.append(Finding("ERROR", f"Required record {tag} is missing."))

    for line_number, tag, line in tagged:
        definition = fields.get(tag)
        if definition is None or not definition["required"]:
            continue
        value = line.partition(",")[2].strip()
        if not value:
            findings.append(
                Finding(
                    "ERROR", f"Required record {tag} has an empty value.", line_number
                )
            )

    repeatable = {"PATCUT", "POLARI", "NUPOIN", "FSTLST"}
    for tag, count in present.items():
        if count > 1 and tag not in repeatable:
            findings.append(
                Finding("ERROR", f"Record {tag} occurs {count} times; expected once.")
            )

    previous_order = -1
    for line_number, tag, _line in tagged:
        order = field_order.get(tag)
        if order is None:
            continue
        if tag in repeatable:
            continue
        if order < previous_order:
            findings.append(
                Finding(
                    "ERROR",
                    f"Record {tag} is out of standard field order.",
                    line_number,
                )
            )
        previous_order = max(previous_order, order)

    if tagged and tagged[-1][1] != "ENDFIL":
        findings.append(Finding("ERROR", "ENDFIL is not the final tagged record."))
    for line_number, tag, line in tagged:
        if tag == "ENDFIL" and line != "ENDFIL:,EOF":
            findings.append(
                Finding("ERROR", "ENDFIL must contain exactly 'EOF'.", line_number)
            )


def audit_record_values(tagged, findings):
    """Validate standard constants and enumerated record values."""

    for line_number, tag, line in tagged:
        value = line.partition(",")[2].strip()
        if tag == "REVNUM" and value != STANDARD_NAME:
            findings.append(
                Finding(
                    "ERROR",
                    f"REVNUM is {value!r}; expected {STANDARD_NAME!r}.",
                    line_number,
                )
            )
        elif tag == "REVDAT" and value != REVISION_DATE:
            findings.append(
                Finding(
                    "ERROR",
                    f"REVDAT is {value!r}; the published WG16.99.050 "
                    f"recommendation is dated {REVISION_DATE!r}.",
                    line_number,
                )
            )
        elif tag == "PATTYP" and value not in {"typical", "envelope"}:
            findings.append(
                Finding(
                    "ERROR",
                    f"PATTYP is {value!r}; expected lowercase 'typical' or 'envelope'.",
                    line_number,
                )
            )
        elif tag == "ELTILT":
            values = value.split(",")
            if len(values) != 2:
                findings.append(
                    Finding(
                        "ERROR",
                        "ELTILT must contain nominal tilt and tolerance.",
                        line_number,
                    )
                )
            else:
                try:
                    float(values[0])
                    float(values[1])
                except ValueError:
                    findings.append(
                        Finding(
                            "ERROR",
                            f"ELTILT contains a non-numeric value: {value!r}.",
                            line_number,
                        )
                    )
        elif tag == "PATCUT" and value not in PATTERN_CUTS:
            try:
                float(value)
            except ValueError:
                findings.append(
                    Finding(
                        "ERROR",
                        f"Unknown PATCUT designator {value!r}.",
                        line_number,
                    )
                )
        elif tag == "POLARI" and value not in POLARIZATIONS:
            findings.append(
                Finding(
                    "ERROR",
                    f"Unknown POLARI designator {value!r}.",
                    line_number,
                )
            )


def audit_cuts(tagged, cuts, findings):
    """Validate cut counts, point counts, angle ranges, and monotonic ordering."""

    declared_cut_count = None
    for line_number, tag, line in tagged:
        if tag == "NUMCUT":
            try:
                declared_cut_count = int(line.partition(",")[2])
            except ValueError:
                findings.append(
                    Finding("ERROR", "NUMCUT is not an integer.", line_number)
                )

    if declared_cut_count is not None and declared_cut_count != len(cuts):
        findings.append(
            Finding(
                "ERROR",
                f"NUMCUT declares {declared_cut_count}, "
                f"but {len(cuts)} cut(s) were found.",
            )
        )

    for cut in cuts:
        if cut.declared_points is None:
            findings.append(
                Finding("ERROR", f"{cut.axis} cut has no valid NUPOIN.", cut.line)
            )
        elif cut.declared_points != len(cut.points):
            findings.append(
                Finding(
                    "ERROR",
                    f"{cut.axis} cut declares {cut.declared_points} points "
                    f"but contains {len(cut.points)}.",
                    cut.line,
                )
            )

        if not cut.points:
            continue

        angles = [angle for _, angle, _ in cut.points]
        if any(right <= left for left, right in zip(angles, angles[1:])):
            findings.append(
                Finding(
                    "ERROR",
                    f"{cut.axis} cut angles are not strictly increasing.",
                    cut.line,
                )
            )
        if len(angles) != len(set(angles)):
            findings.append(
                Finding("ERROR", f"{cut.axis} cut contains duplicate angles.", cut.line)
            )
        audit_equivalent_angles(cut, findings)

        if cut.first_last is not None:
            expected_first, expected_last = cut.first_last
            if abs(angles[0] - expected_first) > 0.0005:
                findings.append(
                    Finding(
                        "ERROR",
                        f"{cut.axis} FSTLST first angle is {expected_first}, but first "
                        f"point is {angles[0]}.",
                        cut.line,
                    )
                )
            if abs(angles[-1] - expected_last) > 0.0005:
                findings.append(
                    Finding(
                        "ERROR",
                        f"{cut.axis} FSTLST last angle is {expected_last}, but last "
                        f"point is {angles[-1]}.",
                        cut.line,
                    )
                )


def audit_equivalent_angles(cut, findings, tolerance=0.0005):
    """Reject angles that describe the same direction modulo 360 degrees.

    WG16.99.050 explicitly prohibits repeated azimuth directions such as both
    0 and 360 degrees. The same circular rule also makes -180 and +180
    equivalent.
    """

    directions = {}
    for line_number, angle, _level in cut.points:
        direction = angle % 360.0
        if abs(direction - 360.0) <= tolerance or abs(direction) <= tolerance:
            direction = 0.0
        key = round(direction / tolerance)
        previous = directions.get(key)
        if previous is not None and abs(angle - previous[1]) > tolerance:
            previous_line, previous_angle = previous
            findings.append(
                Finding(
                    "ERROR",
                    f"{cut.axis} cut angles {previous_angle:g} (line "
                    f"{previous_line}) and {angle:g} describe the same direction "
                    "modulo 360 degrees.",
                    line_number,
                )
            )
        else:
            directions[key] = (line_number, angle)


def parse_args():
    """Parse command-line arguments for one or more NSMA files."""

    parser = argparse.ArgumentParser(
        description="Audit NSMA WG16.99.050 files without changing them."
    )
    parser.add_argument("files", nargs="+", type=Path, help="NSMA file(s) to audit.")
    parser.add_argument(
        "--schema",
        type=Path,
        help="Advanced: override the trusted built-in schema with an external CSV.",
    )
    return parser.parse_args()


def main():
    """Audit requested files, print findings, and return a useful exit status."""

    args = parse_args()
    any_errors = False
    if args.schema is not None:
        print(
            "WARNING: Using an external schema; strict built-in WG16.99.050 "
            "field validation is overridden."
        )

    for path in args.files:
        print(f"\nAudit: {path}")
        print("-" * (7 + len(str(path))))
        if not path.is_file():
            print("ERROR: File does not exist.")
            any_errors = True
            continue

        findings = audit_nsma(path, args.schema)
        errors = sum(finding.severity == "ERROR" for finding in findings)
        warnings = sum(finding.severity == "WARNING" for finding in findings)
        any_errors = any_errors or errors > 0

        for finding in sorted(findings, key=finding_sort_key):
            location = f"line {finding.line}: " if finding.line is not None else ""
            print(f"{finding.severity}: {location}{finding.message}")

        print(f"Summary: {errors} error(s), {warnings} warning(s)")

    raise SystemExit(1 if any_errors else 0)


def finding_sort_key(finding):
    """Sort file-wide findings first, followed by source lines in order.

    Unlocated structural findings are placed last because they are commonly a
    consequence or summary of line-specific problems.
    """

    if finding.line is not None:
        return (1, finding.line, finding.severity, finding.message)
    if finding.message.startswith(("Found ", "File is ", "Final record ")):
        return (0, 0, finding.severity, finding.message)
    return (2, 0, finding.severity, finding.message)


if __name__ == "__main__":
    main()
