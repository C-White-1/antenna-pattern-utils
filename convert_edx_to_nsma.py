"""Convert EDX Wireless antenna patterns to NSMA WG16.99.050."""

import argparse
from pathlib import Path

from edx_parser import parse_edx
from nsma import build_nsma_lines, compare_patterns, parse_nsma, write_nsma
from plotting import plot_patterns

TEMPLATE_DEFAULTS = {
    "manufacturer": "",
    "low_frequency": "",
    "high_frequency": "",
    "pattern_frequency": "",
    "polarization": "",
    "tilt": "0",
    "tilt_tolerance": "0",
    "pattern_type": "typical",
    "comment": "Converted from EDX pattern format",
}
REQUIRED_METADATA = (
    "manufacturer",
    "low_frequency",
    "high_frequency",
    "pattern_frequency",
    "polarization",
)


def write_template(path):
    """Write a blank, documented EDX-to-NSMA metadata template."""

    lines = [
        "# EDX to NSMA conversion metadata",
        "# Complete the required values below. Command-line options override them.",
        "# Frequencies are in MHz. Polarization must be H/H or V/V.",
        "",
    ]
    lines.extend(f"{key} = {value}" for key, value in TEMPLATE_DEFAULTS.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_template(path):
    """Read and validate a ``key = value`` conversion template."""

    values = {}
    allowed = set(TEMPLATE_DEFAULTS)
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected key = value")
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.lower().replace("-", "_")
        if key not in allowed:
            raise ValueError(f"{path}:{line_number}: unknown template key {key!r}")
        if key in values:
            raise ValueError(f"{path}:{line_number}: duplicate template key {key!r}")
        values[key] = value
    return values


def default_output_path(input_path):
    """Return the input path with an ``.nsm`` extension."""

    return input_path.with_suffix(".nsm")


def parse_args():
    """Define and parse EDX conversion arguments."""

    parser = argparse.ArgumentParser(
        description="Convert an EDX Wireless antenna pattern to NSMA format."
    )
    parser.add_argument("input", type=Path, nargs="?", help="EDX .pat input file.")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--template", type=Path, help="Metadata template file.")
    parser.add_argument(
        "--make-template",
        "--make_template",
        nargs="?",
        const=Path("edx_nsma_template.txt"),
        type=Path,
        metavar="FILE",
        help="Write a blank template (default: edx_nsma_template.txt) and exit.",
    )
    parser.add_argument("--manufacturer")
    parser.add_argument("--low-frequency", dest="low_frequency")
    parser.add_argument("--high-frequency", dest="high_frequency")
    parser.add_argument("--pattern-frequency", dest="pattern_frequency")
    parser.add_argument(
        "--polarization",
        choices=("H/H", "V/V"),
        help="Co-polarized antenna/source polarization.",
    )
    parser.add_argument("--tilt", type=float)
    parser.add_argument("--tilt-tolerance", type=float)
    parser.add_argument("--pattern-type", choices=("typical", "envelope"))
    parser.add_argument("--comment")
    parser.add_argument("--compare-nsm", type=Path)
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--plot-output", type=Path)
    parser.add_argument("--plot-floor", type=float)
    return parser.parse_args()


def main():
    """Parse EDX data, write NSMA output, compare, and optionally plot."""

    args = parse_args()
    if args.make_template is not None:
        if args.input is not None or args.template is not None:
            raise SystemExit(
                "--make-template cannot be combined with input or --template"
            )
        write_template(args.make_template)
        print(f"Wrote {args.make_template}")
        return
    if args.input is None:
        raise SystemExit("An EDX input file is required (or use --make-template).")

    metadata = dict(TEMPLATE_DEFAULTS)
    if args.template is not None:
        try:
            metadata.update(read_template(args.template))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Cannot read template: {exc}") from exc
    for key in TEMPLATE_DEFAULTS:
        value = getattr(args, key)
        if value is not None:
            metadata[key] = value

    missing = [key for key in REQUIRED_METADATA if str(metadata[key]).strip() == ""]
    if missing:
        options = ", ".join("--" + key.replace("_", "-") for key in missing)
        raise SystemExit(f"Missing required metadata: {options}")
    if metadata["polarization"] not in {"H/H", "V/V"}:
        raise SystemExit("polarization must be H/H or V/V")
    if metadata["pattern_type"] not in {"typical", "envelope"}:
        raise SystemExit("pattern_type must be typical or envelope")
    try:
        metadata["tilt"] = float(metadata["tilt"])
        metadata["tilt_tolerance"] = float(metadata["tilt_tolerance"])
        for key in ("low_frequency", "high_frequency", "pattern_frequency"):
            float(metadata[key])
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Template contains invalid numeric metadata: {exc}") from exc

    output = args.output or default_output_path(args.input)
    if args.compare_nsm and output.resolve() == args.compare_nsm.resolve():
        raise SystemExit(
            "The output and --compare-nsm paths must differ; use -o to preserve "
            "the NSMA reference file."
        )

    antenna = parse_edx(args.input)
    antenna.fields.update(
        {
            "MAKE": metadata["manufacturer"],
            "FREQUENCY": metadata["pattern_frequency"],
            "COMMENT": metadata["comment"],
            "TILT": f"{metadata['tilt']:g}",
            "TILT_TOLERANCE": f"{metadata['tilt_tolerance']:g}",
            "POLARIZATION": metadata["polarization"],
            "PATTERN_TYPE": metadata["pattern_type"],
        }
    )

    comparison = parse_nsma(args.compare_nsm) if args.compare_nsm else None
    differences = []
    compared_points = 0
    if comparison is not None:
        differences, compared_points = compare_patterns(antenna, comparison)

    lines = build_nsma_lines(
        antenna, metadata["low_frequency"], metadata["high_frequency"]
    )
    write_nsma(output, lines)

    if args.plot or args.plot_output is not None:
        plot_patterns(
            antenna,
            comparison=comparison,
            output_path=args.plot_output,
            show=args.plot,
            floor_db=args.plot_floor,
            primary_label="EDX",
            comparison_label="NSMA",
        )

    print(f"Wrote {output}")
    if args.plot_output is not None:
        print(f"Wrote {args.plot_output}")
    if comparison is not None:
        if differences:
            print(f"Comparison failed against {args.compare_nsm}:")
            for difference in differences:
                print(f"  - {difference}")
            raise SystemExit(1)
        print(
            f"Comparison passed: {len(antenna.cuts)} cuts and "
            f"{compared_points} points match {args.compare_nsm}"
        )


if __name__ == "__main__":
    main()
