import argparse
import json
import sys

from . import run, table


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.craft_backtest",
                                     description="Run the composition checks on the round-1 backtest documents.")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    result = run()
    print(json.dumps(result, indent=2) if args.json else table(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
