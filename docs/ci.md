# Check designs in CI

[Documentation home](README.md) · [Production workflows](production.md) · [Export guide](exporting.md)

Design files change like code, so they can be reviewed like code. The repository root holds a composite
GitHub Action (`action.yml`) that checks every matching `.vixl` document on a pull request:

1. installs Vixl (the version at the action's ref, or `vixl-version` from PyPI);
2. runs `vixl check --strict --json` on each document (and a check suite, when given);
3. with `compare-base: true`, renders each document as it is on the base branch (`git show BASE:path`) and
   pixel-diffs it against the pull request version with `vixl diff`;
4. writes a Markdown table to the job summary (errors, warnings, `fix` findings, changed pixels) and lists the
   findings that fail the build;
5. with `proof: true`, uploads a [proof page](production.md#proof-pages) (thumbnails, findings, before/after
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
    steps:
      - uses: actions/checkout@v4
      - uses: jxburros/Vixl@v0.23.0   # pin a release tag (or a commit SHA)
        with:
          paths: designs/**/*.vixl
          fail-on: error          # error | warning | fix | never
          compare-base: true      # diff against the pull request's base branch
          proof: true             # upload the proof page as an artifact
```

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `paths` | `**/*.vixl` | Globs, separated by spaces or newlines |
| `checks` | (standard checks) | `vixl check` names, space-separated (`contrast print fonts` …) |
| `suite` | | A check-suite JSON file (see [design check suites](production.md#design-check-suites)) run on every document |
| `fail-on` | `error` | `error`: any error; `warning`: errors or warnings; `fix`: any finding whose action is `fix`; `never`: report only |
| `vixl-version` | | Install `vixl-engine==VERSION` from PyPI; empty installs the Vixl at the action's ref |
| `compare-base` | `false` | On pull requests, render the base version and report the changed share of pixels |
| `proof` | `false` | Write `.vixl-ci/proof.html` and upload `.vixl-ci/` (proof page and diff images) |
| `python-version` | `3.12` | Python used to run Vixl |

A document that is new in the pull request shows `new` in the Changed column. The diff is a review aid, not a
failure condition: a moved logo is meant to change pixels. To fail on visual change, run `vixl diff` yourself with
`--max-fraction`.

## The same checks locally

```bash
vixl -p designs/poster.vixl check --strict --json
git show origin/main:designs/poster.vixl > /tmp/poster-base.vixl
vixl diff /tmp/poster-base.vixl designs/poster.vixl --out poster-diff.png
python scripts/check_documents.py --paths "designs/**/*.vixl" --base origin/main --proof proof.html
```

`vixl diff BEFORE AFTER` compares two `.vixl` documents or images (PNG, JPEG, WEBP, TIFF, SVG; PDF with the `pdf`
extra), at the first one's size, and reports `changed_pixels`, `changed_fraction` and `changed_region`. `--out`
writes the after image dimmed with changed pixels in red (`--mode side-by-side` shows before | after | diff),
`--threshold` sets the per-channel change that counts (default 8 of 255) and `--max-fraction` exits nonzero above
that share. It never replaces an existing image unless `--overwrite` is given.
