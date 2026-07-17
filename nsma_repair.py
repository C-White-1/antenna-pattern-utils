"""Conservatively repair common NSMA formatting defects."""

import argparse
import re
from pathlib import Path

from nsma_audit import POINT_RECORD, audit_nsma, finding_sort_key
from nsma_standard import FIELD_ORDER, FIELDS, REVISION_DATE

TAGGED_RECORD = re.compile(r"^([A-Z0-9]+):,(.*)$")
REFERENCE_COPY_TAGS = tuple(
    field.abbreviation
    for field in FIELDS
    if FIELD_ORDER["COMNT1"] <= FIELD_ORDER[field.abbreviation] <= FIELD_ORDER["PATTYP"]
)


def normalize_records(data):
    """Decode a file and return non-empty logical records plus change messages."""

    changes = []
    text = data.decode("utf-8-sig")

    crcrlf_count = data.count(b"\r\r\n")
    crlf_count = data.count(b"\r\n") - crcrlf_count
    normalized = data.replace(b"\r\r\n", b"\n").replace(b"\r\n", b"\n")
    cr_only_count = normalized.count(b"\r")
    normalized = normalized.replace(b"\r", b"\n")
    lf_count = normalized.count(b"\n")

    if crcrlf_count:
        changes.append(f"Normalized {crcrlf_count} CRCRLF record ending(s) to CRLF.")
    if cr_only_count:
        changes.append(f"Normalized {cr_only_count} CR-only record ending(s) to CRLF.")
    if lf_count and not crcrlf_count and not crlf_count:
        changes.append(f"Normalized {lf_count} LF-only record ending(s) to CRLF.")

    text = normalized.decode("utf-8")
    raw_records = text.split("\n")
    blank_count = sum(not record.strip() for record in raw_records)
    records = [record.strip() for record in raw_records if record.strip()]
    if blank_count:
        changes.append(f"Removed {blank_count} empty record(s).")
    return records, changes


def repair_records(records, eltilt, eltilt_tolerance):
    """Apply safe record-level repairs and return records plus a change log."""

    repaired = []
    changes = []
    point_comma_count = 0
    removed_eof_count = 0
    seen_eof = False

    for line_number, record in enumerate(records, start=1):
        tag_match = TAGGED_RECORD.match(record)
        if tag_match:
            tag, value = tag_match.groups()

            if tag == "REVDAT" and value != REVISION_DATE:
                record = f"REVDAT:,{REVISION_DATE}"
                changes.append(
                    f"Record {line_number}: set REVDAT to the published "
                    f"WG16.99.050 date {REVISION_DATE}."
                )
            elif tag == "PATTYP" and value in {"Typical", "TYPICAL"}:
                record = "PATTYP:,typical"
                changes.append(
                    f"Record {line_number}: normalized PATTYP to lowercase 'typical'."
                )
            elif tag == "PATTYP" and value in {"Envelope", "ENVELOPE"}:
                record = "PATTYP:,envelope"
                changes.append(
                    f"Record {line_number}: normalized PATTYP to lowercase 'envelope'."
                )
            elif tag == "ELTILT":
                parts = value.split(",")
                valid_pair = False
                if len(parts) == 2:
                    try:
                        float(parts[0])
                        float(parts[1])
                        valid_pair = True
                    except ValueError:
                        pass
                requested_tilt = eltilt is not None or eltilt_tolerance is not None
                if requested_tilt or not valid_pair:
                    nominal = eltilt if eltilt is not None else 0.0
                    tolerance = (
                        eltilt_tolerance if eltilt_tolerance is not None else 0.0
                    )
                    record = (
                        f"ELTILT:,{format_number(nominal)},{format_number(tolerance)}"
                    )
                    changes.append(
                        f"Record {line_number}: set ELTILT nominal/tolerance to "
                        f"{format_number(nominal)},{format_number(tolerance)}."
                    )
            elif tag == "ENDFIL":
                if seen_eof:
                    removed_eof_count += 1
                    continue
                seen_eof = True

            repaired.append(record)
            continue

        if POINT_RECORD.match(record) and not record.endswith(","):
            record += ","
            point_comma_count += 1
        repaired.append(record)

    if point_comma_count:
        changes.append(
            f"Added a trailing comma to {point_comma_count} pattern-point record(s)."
        )
    if removed_eof_count:
        changes.append(f"Removed {removed_eof_count} duplicate ENDFIL record(s).")

    if not any(record.startswith("ELTILT:,") for record in repaired):
        nominal = eltilt if eltilt is not None else 0.0
        tolerance = eltilt_tolerance if eltilt_tolerance is not None else 0.0
        insert_at = next(
            (
                index
                for index, record in enumerate(repaired)
                if record.startswith(("RADCTR:,", "POTOPO:,", "MAXPOW:,", "PATTYP:,"))
            ),
            len(repaired),
        )
        repaired.insert(
            insert_at,
            f"ELTILT:,{format_number(nominal)},{format_number(tolerance)}",
        )
        changes.append(
            "Inserted missing ELTILT with nominal/tolerance "
            f"{format_number(nominal)},{format_number(tolerance)}."
        )

    repaired, cut_changes = repair_cut_metadata(repaired)
    return repaired, changes + cut_changes


def copy_missing_metadata(records, reference_records):
    """Fill missing global metadata from a trusted NSMA reference.

    Only records in the global antenna header are eligible. Existing non-empty
    values and all frequency-block, cut, and pattern-point data are preserved.
    """

    reference_values = {}
    for record in reference_records:
        match = TAGGED_RECORD.match(record)
        if match and match.group(1) in REFERENCE_COPY_TAGS:
            reference_values.setdefault(match.group(1), match.group(2))

    repaired = list(records)
    changes = []
    for tag in REFERENCE_COPY_TAGS:
        reference_value = reference_values.get(tag, "")
        if not reference_value.strip():
            continue
        current = next(
            (
                (index, match.group(2))
                for index, record in enumerate(repaired)
                if (match := TAGGED_RECORD.match(record)) and match.group(1) == tag
            ),
            None,
        )
        if current is not None:
            index, current_value = current
            if current_value.strip():
                continue
            repaired[index] = f"{tag}:,{reference_value}"
            changes.append(
                f"Reference copy: filled empty {tag} with {reference_value!r}."
            )
            continue

        insertion_index = next(
            (
                index
                for index, record in enumerate(repaired)
                if (match := TAGGED_RECORD.match(record))
                and FIELD_ORDER.get(match.group(1), len(FIELD_ORDER)) > FIELD_ORDER[tag]
            ),
            len(repaired),
        )
        repaired.insert(insertion_index, f"{tag}:,{reference_value}")
        changes.append(
            f"Reference copy: inserted missing {tag} with {reference_value!r}."
        )

    return repaired, changes


def format_number(value):
    """Format a repair-supplied number without unnecessary trailing zeros."""

    return f"{value:g}"


def repair_cut_metadata(records):
    """Derive each cut's NUPOIN and FSTLST from its actual pattern points."""

    repaired = list(records)
    changes = []
    cut_starts = [
        index for index, record in enumerate(records) if record.startswith("PATCUT:,")
    ]

    for cut_number, start in enumerate(cut_starts, start=1):
        end = cut_starts[cut_number] if cut_number < len(cut_starts) else len(records)
        for index in range(start, end):
            if records[index].startswith("ENDFIL:,"):
                end = index
                break

        point_indices = [
            index
            for index in range(start, end)
            if not TAGGED_RECORD.match(records[index])
            and POINT_RECORD.match(records[index])
        ]
        if not point_indices:
            continue

        first_angle = float(POINT_RECORD.match(records[point_indices[0]]).group(1))
        last_angle = float(POINT_RECORD.match(records[point_indices[-1]]).group(1))
        actual_count = len(point_indices)
        axis = records[start].partition(",")[2]

        nupoin_index = next(
            (
                index
                for index in range(start, end)
                if records[index].startswith("NUPOIN:,")
            ),
            None,
        )
        if nupoin_index is not None:
            expected = f"NUPOIN:,{actual_count}"
            if repaired[nupoin_index] != expected:
                changes.append(
                    f"{axis} cut: changed NUPOIN from "
                    f"{repaired[nupoin_index].partition(',')[2]!r} to {actual_count}."
                )
                repaired[nupoin_index] = expected

        fstlst_index = next(
            (
                index
                for index in range(start, end)
                if records[index].startswith("FSTLST:,")
            ),
            None,
        )
        expected = f"FSTLST:,{format_number(first_angle)},{format_number(last_angle)}"
        if fstlst_index is not None and repaired[fstlst_index] != expected:
            changes.append(
                f"{axis} cut: derived FSTLST as "
                f"{format_number(first_angle)},{format_number(last_angle)}."
            )
            repaired[fstlst_index] = expected

    return repaired, changes


def repaired_bytes(records):
    """Serialize logical records using exactly one CRLF per record."""

    return "".join(f"{record}\r\n" for record in records).encode("utf-8")


def default_output_path(input_path):
    """Return a non-destructive default output path beside the input file."""

    return input_path.with_name(f"{input_path.stem}.repaired.nsm")


def parse_args():
    """Parse repair command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Repair safe NSMA formatting defects without inventing data."
    )
    parser.add_argument("input", type=Path, help="NSMA file to repair.")
    parser.add_argument("-o", "--output", type=Path, help="Repaired output path.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed changes without writing an output file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacement of an existing output file.",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        help="Trusted NSMA file from which to copy missing header metadata.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept proposed reference copies without interactive confirmation.",
    )
    parser.add_argument(
        "--eltilt",
        type=float,
        help="Electrical tilt in degrees (default for invalid/missing data: 0).",
    )
    parser.add_argument(
        "--eltilt-tolerance",
        type=float,
        help="Electrical-tilt tolerance in degrees (default: 0).",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        help="Advanced: external CSV override for the post-repair audit.",
    )
    return parser.parse_args()


def print_changes(changes):
    """Print the repair change log."""

    if not changes:
        print("No safe automatic repairs were identified.")
        return
    print("Proposed repairs:")
    for change in changes:
        print(f"  - {change}")


def print_unresolved(findings):
    """Print post-repair findings in auditor order."""

    errors = sum(finding.severity == "ERROR" for finding in findings)
    warnings = sum(finding.severity == "WARNING" for finding in findings)
    if not findings:
        print("Post-repair audit: no findings.")
        return errors, warnings

    print("Post-repair audit:")
    for finding in sorted(findings, key=finding_sort_key):
        location = f"line {finding.line}: " if finding.line is not None else ""
        print(f"  {finding.severity}: {location}{finding.message}")
    print(f"  Summary: {errors} error(s), {warnings} warning(s)")
    return errors, warnings


def confirm_reference_copy(reference, changes):
    """Warn about reference provenance and request explicit confirmation."""

    copied = [change for change in changes if change.startswith("Reference copy:")]
    if not copied:
        return True
    print()
    print("WARNING: Metadata will be copied from another antenna pattern file.")
    print(f"Reference: {reference}")
    print(
        "Confirm that both files describe the same antenna or that every value "
        "listed above is applicable to the target. Pattern data is not copied."
    )
    try:
        answer = input("Proceed with these repairs? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def main():
    """Repair a file, preserve its source, and report unresolved audit findings."""

    args = parse_args()
    if args.schema is not None:
        print(
            "WARNING: Using an external schema; strict built-in WG16.99.050 "
            "field validation is overridden."
        )
    if not args.input.is_file():
        raise SystemExit(f"Input file does not exist: {args.input}")
    if args.reference is not None:
        if not args.reference.is_file():
            raise SystemExit(f"Reference file does not exist: {args.reference}")
        if args.reference.resolve() == args.input.resolve():
            raise SystemExit("The reference and input files must differ.")
        reference_findings = audit_nsma(args.reference, None)
        reference_errors = [
            finding for finding in reference_findings if finding.severity == "ERROR"
        ]
        if reference_errors:
            raise SystemExit(
                f"Reference file failed its audit with {len(reference_errors)} "
                "error(s); repair or select a trusted reference first."
            )

    output = args.output or default_output_path(args.input)
    if output.resolve() == args.input.resolve():
        raise SystemExit("The repair output must differ from the input file.")
    if output.exists() and not args.force and not args.dry_run:
        raise SystemExit(f"Output already exists; use --force to replace it: {output}")

    records, normalization_changes = normalize_records(args.input.read_bytes())
    reference_changes = []
    if args.reference is not None:
        reference_records, _ = normalize_records(args.reference.read_bytes())
        records, reference_changes = copy_missing_metadata(records, reference_records)
    records, record_changes = repair_records(
        records, args.eltilt, args.eltilt_tolerance
    )
    changes = normalization_changes + reference_changes + record_changes
    data = repaired_bytes(records)
    print_changes(changes)

    if args.dry_run:
        print(f"Dry run only; would write {output}.")
        raise SystemExit(0)

    if args.reference is not None and not args.yes:
        if not confirm_reference_copy(args.reference, changes):
            raise SystemExit("Repair cancelled; no output file was written.")

    output.write_bytes(data)
    print(f"Wrote {output}")

    findings = audit_nsma(output, args.schema)
    errors, _warnings = print_unresolved(findings)
    raise SystemExit(2 if errors else 0)


if __name__ == "__main__":
    main()
