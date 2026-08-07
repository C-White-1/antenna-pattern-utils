"""Convert PLANET antenna patterns to NSMA format and optionally plot them."""

import argparse
from pathlib import Path

from nsma import build_nsma_lines, compare_patterns, parse_nsma, write_nsma
from planet_parser import parse_planet
from plotting import plot_patterns


def default_output_path(input_path):
    """Return the input path with its extension replaced by ``.nsm``."""

    return input_path.with_suffix(".nsm")


def prompt_if_missing(value, prompt):
    """Return a CLI value or request it interactively when omitted."""

    return value if value is not None else input(prompt)


def parse_args():
    """Define and parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Convert a PLANET ASCII antenna pattern file to NSMA format."
    )
    parser.add_argument("input", type=Path, help="PLANET .pln input file.")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--low-frequency")
    parser.add_argument("--high-frequency")
    parser.add_argument(
        "--compare-nsm",
        type=Path,
        help="Compare an existing NSMA file with the PLANET pattern data.",
    )
    parser.add_argument(
        "--plot", action="store_true", help="Display polar plots of all cuts."
    )
    parser.add_argument(
        "--plot-output", type=Path, help="Save the polar plots to an image."
    )
    parser.add_argument(
        "--plot-floor",
        type=float,
        help="Lowest displayed pattern level in dB (default: automatic).",
    )
    return parser.parse_args()


def main():
    """Run conversion, optional comparison, and optional plotting."""

    args = parse_args()
    input_path = args.input
    output_path = args.output or default_output_path(input_path)
    if args.compare_nsm and output_path.resolve() == args.compare_nsm.resolve():
        raise SystemExit(
            "The output and --compare-nsm paths must differ; use -o to preserve "
            "the NSMA reference file."
        )

    low_freq = prompt_if_missing(args.low_frequency, "Enter low frequency (MHz): ")
    high_freq = prompt_if_missing(args.high_frequency, "Enter high frequency (MHz): ")

    antenna = parse_planet(input_path)
    comparison = parse_nsma(args.compare_nsm) if args.compare_nsm else None
    differences = []
    compared_points = 0
    if comparison is not None:
        differences, compared_points = compare_patterns(antenna, comparison)

    lines = build_nsma_lines(antenna, low_freq, high_freq)
    write_nsma(output_path, lines)

    if args.plot or args.plot_output is not None:
        plot_patterns(
            antenna,
            comparison=comparison,
            output_path=args.plot_output,
            show=args.plot,
            floor_db=args.plot_floor,
        )

    print(f"Wrote {output_path}")
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
