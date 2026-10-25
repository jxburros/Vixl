# Check designs in CI

[Documentation home](../../README.md) · [Production workflows](production.md) · [Export guide](../output/exporting.md)

Design files change like code, so they can be reviewed like code. The repository root holds a composite
GitHub Action (`action.yml`) that checks every matching `.vixl` document on a pull request with
[`vixl check --all`](production.md#checking-many-documents), the same workspace report the CLI, MCP
(`vixl_apply(workflow='check-all')`) and Python use:

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
      - uses: jxburros/Vixl@v0.31.0   # pin a release tag (or a commit SHA)
        with:
          paths: designs/**/*.vixl
          profile: final          # draft | review | final | a .vixl-checks.json profile (optional)
          fail-on: ""             # empty: the profile's fail_on, else error; or error | warning | fix | review | never
          compare-base: true      # diff against the pull request's base branch
          changed-only: false     # true: check only the documents this pull request changed
          proof: true             # upload the proof page as an artifact
          formats: json junit     # report files in .vixl-ci/
          sarif: true             # findings in the Security tab and on the pull request
```

A tag such as `v0.31.0` is easy to read but can be moved to other code. For a pin nothing can change, use the
release's full commit SHA with the version in a comment, `uses: jxburros/Vixl@<40-character-sha>  # v0.31.0`, and
let Dependabot (`package-ecosystem: github-actions`) propose updates. The action itself pins `setup-python`,
`upload-artifact` and `upload-sarif` by commit SHA, and passes every input to its scripts through environment
variables, never by pasting `${{ inputs.* }}` into a shell line.

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `paths` | `**/*.vixl` | Globs, separated by spaces or newlines |
| `group` | | A project group: its members and the [group consistency checks](studio.md#group-consistency-checks); with the default `paths`, only the members |
| `checks` | (standard checks) | `vixl check` names, space-separated (`contrast print fonts` …) |
| `suite` | | A check-suite JSON file (see [design check suites](production.md#design-check-suites)) run on every document; suites attached to a document always run (with a `profile`, the suites the profile names) |
| `fail-on` | (empty) | `error`: any error; `warning`: errors or warnings; `fix`: any finding whose action is `fix`; `review`: any fix or review finding; `never`: report only. Empty: the `profile`'s own `fail_on`, else `error`. A suite that does not pass fails at every level but `never` (under a profile, a suite that only needs review fails at `warning` and `review`) |
| `profile` | | A [check profile](production.md#waivers-and-check-profiles) (`draft`, `review`, `final`, one in the repository's `.vixl-checks.json` or the group's `profiles`): every document is checked with its checks and suites (`vixl check --all --profile`) |
| `vixl-version` | | Install `vixl-engine[pdf]==VERSION` from PyPI (0.25.0 or later); empty installs the Vixl at the action's ref |
| `compare-base` | `false` | On pull requests, render the base version and report the changed share of pixels |
| `changed-only` | `false` | On pull requests, check only the documents changed against the base branch |
| `proof` | `false` | Write `.vixl-ci/proof.html` and upload `.vixl-ci/` (proof page, reports and diff images) |
| `annotations` | `true` | Print each finding as a workflow annotation (`::error file=designs/poster.vixl,title=Vixl contrast::…`) |
| `formats` | `json` | Report files written into `.vixl-ci/`: `json` (`report.json`), `markdown` (`report.md`), `junit` (`junit.xml`), `sarif` (`vixl.sarif`), `github` (`annotations.txt`) |
| `sarif` | `false` | Write `.vixl-ci/vixl.sarif` and upload it to code scanning (needs `security-events: write`) |
| `python-version` | `3.12` | Python used to run Vixl |

Outputs: `summary` (the Markdown summary file), `report`, `junit` and `sarif` (the paths of the files written).

Run `vixl convert` once on documents saved by 0.26 or earlier ([Converting](../../reference/converting.md#convert-a-document)): the
action's Vixl reads current documents only, so a format-1 file (0.10 and earlier) is reported as could not be checked
("Unsupported project format"), and a newer one draws with today's defaults unless the conversion writes its old look
into its fields.

A document that is new in the pull request shows `new` in the Changed column. The diff is a review aid, not a
failure condition: a moved logo is meant to change pixels. To fail on visual change, run `vixl diff` yourself with
`--max-fraction`.

The JUnit file has one testsuite per document and one testcase per check and suite rule, so test reporters (for
example a JUnit report action) show each document as a suite. The SARIF file has one result per finding: the check
name (or `suite/NAME/RULE`, or `group-layout` …) is the rule, the severity is the level, the `.vixl` path is the
location and the layer names are logical locations.

## Profiles and waivers

A [check profile](production.md#waivers-and-check-profiles) says how strict a run is: `draft` fails only on errors,
`review` on any `fix` finding and on attached suites, `final` on `fix` and `review` findings with `color_vision`
and `composition` added. The repository's `.vixl-checks.json` adds or overrides profiles (and a project group's `profiles` override
both for its members), so a pull request can check sketches with `profile: draft` and a release branch with
`profile: final` from the same documents. Without `fail-on`, the profile's level decides; an explicit `fail-on`
overrides it.

Findings a document waives (`layer-intent waive`, the `waiver` operation, `waivers` in `.vixl-checks.json` or a
group's `shared.waivers`) stay in the report as informational, never fail the build and are listed under Waivers in
the summary with their reason and expiry. A waiver past its `expires` date turns its finding back on and adds an
`expired waiver` fix finding, so the build fails until someone fixes the design or renews the waiver.
`vixl check --all --no-waivers` reports every finding as if there were none.

## The same checks locally

```bash
vixl check --all "designs/**/*.vixl" --fail-on error
vixl check --all "designs/**/*.vixl" --profile final
vixl check --all "designs/**/*.vixl" --base origin/main --write proof=proof.html
vixl check --all "designs/**/*.vixl" --changed-since origin/main --format github
vixl -p designs/poster.vixl check --strict --json
vixl diff /tmp/poster-base.vixl designs/poster.vixl --out poster-diff.png
```

`scripts/check_documents.py` (`--paths`, `--checks`, `--suite`, `--fail-on`, `--profile`, `--base`, `--proof`,
`--work`) is kept
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
SVG files must be self-contained, as for SVG appearance import: an external `href` or `url()`, a DOCTYPE or
ENTITY, scripts, more than 64 levels or 10,000 elements fail with `unsupported_svg` or `resource_limit`, and the
declared width × height is checked against the pixel limit before anything is rasterized. The same rules apply to
SVG previews in proof pages, workspace diffs, `reproduce`, `replace-across` and logo packages.

## Locking renders and exports

A render lockfile records what a document draws and what its exports are, so a later run (a scheduled job, a release
build, another machine) can say whether anything moved. Commit the lockfile next to the document:

```bash
vixl -p designs/poster.vixl reproduce --write-lock designs/poster.lock.json --export png "jpg:quality=85" pdf
vixl -p designs/poster.vixl reproduce --lock designs/poster.lock.json --export --export-tolerance 8
```

The second command re-renders every page, artboard and sampled frame, encodes the locked exports again and exits
nonzero when something differs. It names what: `page 2`, `jpg.quality`, `mp4.ffmpeg`, `pdf.icc_profile`
([reproduction](../../reference/agent-trust.md#reproduction)). Run it on the runner that built the lockfile for an exact
check, or on any runner with `--export-visual` to judge every export by its pixels.

### The limits of exact reproduction

Two runs of the same Vixl on the same machine give the same bytes. Across machines these differ, and each shows up as
`environment_drift` or as an export that is `visually_equivalent` but not `byte_identical`:

| What differs | What it changes | What to do |
| --- | --- | --- |
| Fonts: another build or version of a family, or the bundled proofing fallback standing in for a missing font | Text pixels, line breaks and every export of the page | Embed the fonts in the document (`vixl font install FAMILY`); the lockfile hashes each font file |
| Text rasterisation: FreeType, HarfBuzz and the platform's hinting | The anti-aliased edge of every glyph, so the render hash changes while the pixels look the same | Compare with a reference image and `--tolerance`, not the hash; the golden-image suite runs on Linux only for this reason |
| The platform's zlib (zlib-ng or system zlib) | PNG, APNG and PDF stream bytes, not their pixels | `--export-visual`; or build the lock and the check on one image |
| Pillow, libjpeg, libwebp, libavif versions | JPEG, WebP, AVIF and GIF bytes and slightly their pixels | Judged by pixels within `--export-tolerance`; the versions are in `environment_drift` |
| The ffmpeg and encoder version, and threading | MP4 and WebM bytes (VP9 output is not always byte-stable even on one machine) and slightly their pixels | Judged by decoded frames; `toolchain` drift names the ffmpeg version |
| An ICC profile or its file | CMYK conversions | The profile's SHA-256 is locked; keep the profile in the repository |
| Remote AI inference | Generated pixels | They are embedded assets and locked as inputs; the model call is not replayed |

A lockfile that was written by a different Vixl, Python or imaging build reports `environment_drift` first; those
differences explain the rest, and `input_drift` (the document, a page, a variable, an export setting) is what someone
changed.
