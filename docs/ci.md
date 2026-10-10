# Check designs in CI

[Documentation home](README.md) · [Production workflows](production.md) · [Export guide](exporting.md)

Design files change like code, so they can be reviewed like code. The repository root holds a composite
GitHub Action (`action.yml`) that checks every matching `.vixl` document on a pull request with
[`vixl check --all`](production.md#checking-many-documents), the same workspace report the CLI, MCP
(`vixl_workflow` `check-all`) and Python use:

1. installs Vixl (the version at the action's ref, or `vixl-version` from PyPI);
2. checks each document (design checks plus the suites attached to it, and a shared check suite when given), in
   parallel; with `group`, the members of a project group plus the group consistency checks;
3. with `changed-only: true`, checks only the documents the pull request changed;
4. with `compare-base: true`, renders each document as it is on the base branch (`git show BASE:path`) and
   pixel-diffs it against the pull request version;
5. writes a Markdown table to the job summary (errors, warnings, `fix` findings, changed pixels, status) and lists the
   findings that fail the build, and prints them as annotations on the files;
6. writes report files into `.vixl-ci/` (`formats`: JSON, Markdown, JUnit XML, SARIF, annotations), and with
   `sarif: true` uploads the SARIF to GitHub code scanning;
7. with `proof: true`, uploads a [proof page](production.md#proof-pages) (thumbnails, findings, before/after
   diffs) as the `vixl-proof` artifact.

## Example workflow

```yaml
# .github/workflows/designs.yml
name: Designs
on:
  pull_request:
    paths: ["designs/**.vixl"]

jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write   # only for sarif: true
    steps:
      - uses: actions/checkout@v4
      - uses: jxburros/Vixl@v0.24.1   # pin a release tag (or a commit SHA)
        with:
          paths: designs/**/*.vixl
          fail-on: error          # error | warning | fix | never
          compare-base: true      # diff against the pull request's base branch
          changed-only: false     # true: check only the documents this pull request changed
          proof: true             # upload the proof page as an artifact
          formats: json junit     # report files in .vixl-ci/
          sarif: true             # findings in the Security tab and on the pull request
```

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `paths` | `**/*.vixl` | Globs, separated by spaces or newlines |
| `group` | | A project group: its members and the [group consistency checks](studio.md#group-consistency-checks); with the default `paths`, only the members |
| `checks` | (standard checks) | `vixl check` names, space-separated (`contrast print fonts` …) |
| `suite` | | A check-suite JSON file (see [design check suites](production.md#design-check-suites)) run on every document; suites attached to a document always run |
| `fail-on` | `error` | `error`: any error; `warning`: errors or warnings; `fix`: any finding whose action is `fix`; `never`: report only. A suite that does not pass fails at every level but `never` |
| `vixl-version` | | Install `vixl-engine==VERSION` from PyPI (0.25.0 or later); empty installs the Vixl at the action's ref |
| `compare-base` | `false` | On pull requests, render the base version and report the changed share of pixels |
| `changed-only` | `false` | On pull requests, check only the documents changed against the base branch |
| `proof` | `false` | Write `.vixl-ci/proof.html` and upload `.vixl-ci/` (proof page, reports and diff images) |
| `annotations` | `true` | Print each finding as a workflow annotation (`::error file=designs/poster.vixl,title=Vixl contrast::…`) |
| `formats` | `json` | Report files written into `.vixl-ci/`: `json` (`report.json`), `markdown` (`report.md`), `junit` (`junit.xml`), `sarif` (`vixl.sarif`), `github` (`annotations.txt`) |
| `sarif` | `false` | Write `.vixl-ci/vixl.sarif` and upload it to code scanning (needs `security-events: write`) |
| `python-version` | `3.12` | Python used to run Vixl |

Outputs: `summary` (the Markdown summary file), `report`, `junit` and `sarif` (the paths of the files written).

A document that is new in the pull request shows `new` in the Changed column. The diff is a review aid, not a
failure condition: a moved logo is meant to change pixels. To fail on visual change, run `vixl diff` yourself with
`--max-fraction`.

The JUnit file has one testsuite per document and one testcase per check and suite rule, so test reporters (for
example a JUnit report action) show each document as a suite. The SARIF file has one result per finding: the check
name (or `suite/NAME/RULE`, or `group-layout` …) is the rule, the severity is the level, the `.vixl` path is the
location and the layer names are logical locations.

## The same checks locally

```bash
vixl check --all "designs/**/*.vixl" --fail-on error
vixl check --all "designs/**/*.vixl" --base origin/main --write proof=proof.html
vixl check --all "designs/**/*.vixl" --changed-since origin/main --format github
vixl -p designs/poster.vixl check --strict --json
vixl diff /tmp/poster-base.vixl designs/poster.vixl --out poster-diff.png
```

`scripts/check_documents.py` (`--paths`, `--checks`, `--suite`, `--fail-on`, `--base`, `--proof`, `--work`) is kept
as a thin wrapper over the same report for workflows that call it directly.

Each local run is recorded in `.vixl-checks/history/`; `--since-last` reports the documents that newly fail since
the previous run (and whether a Vixl upgrade or an edit caused it). The action passes `--no-history`, since a CI
checkout starts empty; to track results over time, run `vixl check --all --since-last` on a schedule in a workflow
that keeps `.vixl-checks/` (for example as a cached or committed folder).

`vixl diff BEFORE AFTER` compares two `.vixl` documents or images (PNG, JPEG, WEBP, TIFF, SVG; PDF with the `pdf`
extra), at the first one's size, and reports `changed_pixels`, `changed_fraction` and `changed_region`. `--out`
writes the after image dimmed with changed pixels in red (`--mode side-by-side` shows before | after | diff),
`--threshold` sets the per-channel change that counts (default 8 of 255) and `--max-fraction` exits nonzero above
that share. It never replaces an existing image unless `--overwrite` is given.
