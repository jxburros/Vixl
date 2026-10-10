"""Check Vixl documents in CI: a thin wrapper over ``vixl check --all`` (the workspace check report).

Kept for workflows that call it directly; the GitHub Action (action.yml) runs ``vixl check --all``
itself. It checks every document matching the globs, optionally pixel-diffs each one against a git
revision, writes the Markdown summary (to $GITHUB_STEP_SUMMARY when set) and optionally a proof page,
and exits non-zero when a finding reaches ``--fail-on``.
"""

import argparse
import os
import sys

LEVELS = ("never", "error", "warning", "fix")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", default="**/*.vixl", help="Globs, separated by spaces or newlines")
    parser.add_argument("--checks", default="", help="vixl check names (default: the standard checks)")
    parser.add_argument("--suite", default="", help="A check-suite JSON file to run on every document")
    parser.add_argument("--fail-on", choices=LEVELS, default="error")
    parser.add_argument("--base", default="", help="Git revision to compare with (empty: no comparison)")
    parser.add_argument("--proof", default="", help="Write a proof page here (.html)")
    parser.add_argument("--work", default=".vixl-ci", help="Folder for base renders and diff images")
    a = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a Windows console cannot print every finding
    try:
        from vixl.interfaces import Session
        from vixl.workspace_checks import markdown, run
    except ImportError:
        print("This script needs vixl-engine 0.25 or later (vixl check --all)", file=sys.stderr)
        return 2
    request = {"documents": a.paths.split() or ["**/*.vixl"], "fail_on": a.fail_on, "history": False}
    if a.checks.split():
        request["checks"] = a.checks.split()
    if a.suite:
        request["suite"] = a.suite
    if a.base:
        request.update(base=a.base, work=a.work)
    if a.proof:
        request.update(outputs={"proof": a.proof}, overwrite=True)
    result = run(Session(None, workspace=os.getcwd()), request)
    text = markdown(result)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as stream:
            stream.write(text)
    print(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
