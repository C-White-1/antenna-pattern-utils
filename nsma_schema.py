"""Generate CSV and JSON reference artifacts from ``nsma_standard.py``."""

import csv
import json
from pathlib import Path

from nsma_standard import FIELDS, REVISION_DATE, STANDARD_NAME

ROOT = Path(__file__).parent


def csv_rows():
    """Return rows using the historical ``nsma.csv`` column layout."""

    return [
        {
            "required": "TRUE" if field.required else "FALSE",
            "name": field.name,
            "length": field.max_length,
            "abbrev": field.abbreviation,
        }
        for field in FIELDS
    ]


def json_fields():
    """Return fields using the existing expanded JSON schema layout."""

    return [
        {
            "section": None,
            "abbrev": field.abbreviation,
            "name": field.name,
            "required": field.required,
            "length": field.max_length,
            "prefix": field.prefix,
            "format": None,
            "description": None,
            "example": None,
            "raw": None,
            "parsed_type": None,
            "parse": False,
            "ui": {"label": field.name, "tooltip": None},
            "validation": {"regex": None, "min": None, "max": None},
        }
        for field in FIELDS
    ]


def write_csv(path=ROOT / "nsma.csv"):
    """Generate the CSV reference artifact."""

    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output, fieldnames=["required", "name", "length", "abbrev"]
        )
        writer.writeheader()
        writer.writerows(csv_rows())


def write_json(path=ROOT / "nsma_schema.json"):
    """Generate the JSON reference artifact."""

    schema = {
        "standard": STANDARD_NAME,
        "revision_date": REVISION_DATE,
        "generated_from": "nsma_standard.py",
        "fields": json_fields(),
    }
    with path.open("w", encoding="utf-8") as output:
        json.dump(schema, output, indent=2)
        output.write("\n")


def main():
    """Regenerate both reference artifacts."""

    write_csv()
    write_json()
    print("Generated nsma.csv and nsma_schema.json from nsma_standard.py")


if __name__ == "__main__":
    main()
