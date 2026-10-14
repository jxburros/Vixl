import argparse
import json
import sys

from . import repair, repair_table, run, table


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.craft_backtest",
                                     description="Run the composition checks on the round-1 backtest documents.")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--repair", action="store_true",
                        help="run repair-layout on each document and count the composition findings it resolves")
    args = parser.parse_args(argv)
    result = repair() if args.repair else run()
    print(json.dumps(result, indent=2) if args.json else (repair_table if args.repair else table)(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
