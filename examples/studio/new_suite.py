"""Create a design test starter. Customize expectations before attaching it to artwork."""

import argparse
import json
from pathlib import Path

from vixl.assurance import validate_suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--palette", nargs="+", help='Allowed colors, e.g. --palette "#102030" "#ffffff"')
    parser.add_argument("--text-target", help="Add a text-fit rule for a layer name or stable ID")
    parser.add_argument("--minimum-size", type=int, default=18)
    args = parser.parse_args()
    suite = {
        "version": 1,
        "description": "Replace or extend these rules with the design brief's actual requirements.",
        "rules": [{"id": "delivery", "kind": "design", "options": {"checks": ["bounds", "blanks"]}}],
    }
    if args.palette:
        from vixl.resources import validate

        validate("palettes", args.palette)
        suite["rules"].append(
            {"id": "palette", "kind": "palette", "colors": args.palette, "tolerance": 8, "max_fraction": 0.01}
        )
    if args.text_target:
        suite["rules"].append(
            {"id": "text-fit", "kind": "text-fit", "target": args.text_target, "minimum": args.minimum_size}
        )
    validate_suite(suite)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(suite, stream, indent=2)
        stream.write("\n")
    print(f"Created {args.output}. Edit its rules, attach with vixl suite-set, then run workflow check.")


if __name__ == "__main__":
    main()
