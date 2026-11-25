"""``python -m evals.lab``: start the comparison lab on http://localhost:8765/."""

import argparse
import os

from .server import serve


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.lab", description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--results", default="lab-results", help="folder for runs and lab.db (default lab-results)")
    parser.add_argument("--chromium", help="a Chromium executable for Playwright, when its own is not installed")
    parser.add_argument("--no-browser", action="store_true", help="do not open the page in a browser")
    options = parser.parse_args(argv)
    if options.chromium:
        os.environ["VIXL_LAB_CHROMIUM"] = options.chromium
    serve(options.results, port=options.port, open_browser=not options.no_browser)


if __name__ == "__main__":
    main()
