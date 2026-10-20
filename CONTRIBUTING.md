# Contributing

Use the canonical operation schema for CLI, Python, REST and MCP changes. Keep historical spellings in `normalize.py`; aliases must validate and execute through the same implementation as their canonical operation. New operations need a short description, typed and described fields, and regression coverage of their public behavior.

Run `pytest -n auto` (see Setup) and build the distributions before submitting a release change. Keep the package, plugin manifests and versioned installation URLs synchronized; document user-visible changes in `CHANGELOG.md`. Release automation publishes only after Linux and Windows verification and installer checks succeed. See [the release process](docs/reference/releases.md).

Opening the repository in an MCP client starts `vixl mcp --workspace .` from `.mcp.json`, which creates the workspace settings folder `.vixl/` (rolls and variety settings) at the root. It is git-ignored, and the tests and `vixl convert` skip it; delete it whenever you like.

Commit messages, generated pull requests, issue text and generated artwork should describe the work without model signatures or authorship trailers. Keep comments that explain constraints, tradeoffs or non-obvious behavior; remove comments that only repeat the next statement. Provider configuration identifiers are functional data and should remain intact.

`scripts/hooks/commit-msg` removes `Co-Authored-By:` and `Claude-Session:` lines from a commit message; install it
with `git config core.hooksPath scripts/hooks` (or copy it to `.git/hooks/commit-msg`). Coding agents whose tooling
appends such lines by default should use it. An advisory CI check (`pr-hygiene.yml`) warns about trailers in a pull
request's commits or description; it does not fail the run. Past commits are not rewritten for trailers.

Showcases, experiments, films, marketing media, published evaluation results and large content packs belong in
[VixlExamples](https://github.com/jxburros/VixlExamples), not here; link to them from the docs. Keep media in this repository only when
tests, docs or packaging need it (`docs/assets`, `assets/`, `examples/`, `tests/fixtures`).

## Setup

```bash
git clone https://github.com/jxburros/Vixl.git   # add --filter=blob:none for a smaller clone: old history carries large media
cd Vixl
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                           # or: uv sync --extra dev
pytest -n auto                                    # whole suite; iterate with: pytest -q tests/test_x.py
ruff check
```

If `vixl` is editable-installed from another checkout, set `PYTHONPATH=$PWD/src` on the same command line. Optional:
`git config core.hooksPath scripts/hooks` installs the commit-message hook described below.

## Reporting bugs and vulnerabilities

Open an issue with the bug template: the version (`vixl --version`), operating system, Python, the interface (CLI,
MCP, REST or Python), the smallest batch or command that reproduces it, and the expected and actual result.
Vulnerabilities go through GitHub's private reporting, never a public issue; see [SECURITY.md](SECURITY.md).
Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Licence of contributions

Vixl is source-available under the PolyForm Small Business License and also offered under commercial terms. How
contributions are licensed inbound (a Developer Certificate of Origin with `Signed-off-by`, or a contributor licence
agreement that allows relicensing) is an open owner and counsel decision; until it is made, no sign-off or agreement
text is required or implied. Ask in the pull request if this matters for your contribution.

## New features: core or plugin

Optional features live in built-in plugins under `src/vixl/plugins/` and join the core through the registry in
`vixl.plugins`. Before adding a feature, go through the parameters in [plugins](docs/reference/plugins.md#is-a-new-feature-a-plugin)
and state the decision in the pull request. The core never imports a plugin module; `tests/test_plugins.py` checks
this and lists the remaining exceptions. Large data that only some features use is a content pack in
[VixlExamples](https://github.com/jxburros/VixlExamples/tree/main/packs), downloaded on first use by `vixl.packs`.

## Changing a default

Defaults for sparse briefs live in the house style (`src/vixl/data/house-style.json`, read through `src/vixl/house_style.py`); read values from there instead of adding constants. Pre-release: breaking changes are allowed; note them in the changelog, and do not add version switches to the engine: documents saved with older behaviour are handled by the conversion kit (`src/vixl/convert/`, [converting](docs/reference/converting.md)), which the engine never imports. Default changes must still pass the house-style quality/diversity eval. Compare `python -m evals.house_style --compare evals/house-style-baseline.json` before and after; quality must not fall. See [house style](docs/project/house-style.md#changing-defaults-h2).

## Change size and release rhythm

- Keep a pull request to about 800 changed lines, not counting `tests/visual/golden`, `CHANGELOG.md` and the generated
  table in `docs/reference/operations.md`. Split larger work by area, or say in the pull request why it cannot be.
  The advisory `pr-size.yml` workflow prints a warning above that size; it never fails.
- Ship mechanical moves (`git mv` only, no edits) as their own pull request, so the diff reads with `git diff -M`.
- Let a pull request soak before merging: no earlier than 24 hours after it opens, unless it fixes a release blocker.
  This is a convention; branch protection and required reviews are the maintainer's setting.
- Release rhythm, soak and candidate builds are in [releases](docs/reference/releases.md#release-rhythm-and-soak).

## Visual regression tests

`tests/visual` renders a small set of fixture documents (shapes, paths, text, gradients, effects, raster resampling, blends, groups, charts, organic shapes) and compares them with reference files in `tests/visual/golden`: PNG renders for every fixture, SVG and PPTX structural text snapshots, and PDF exports rendered to PNG with pypdfium2. Image comparison has a tolerance (a pixel differs when a channel moves by more than 3; the test fails when more than 0.05% of pixels differ or any channel moves by more than 48), so anti-aliasing noise does not fail the suite but a changed colour, shape or position does.

- Run: `pytest -m visual` (or `pytest tests/visual`). A failure prints the reference, actual and diff paths; the actual output and a `reference | actual | difference` image are written to `tests/visual/_failures/` (git-ignored; CI uploads it as an artifact).
- Update after an intended render change: `VIXL_UPDATE_GOLDEN=1 pytest tests/visual`, review the changed files in `tests/visual/golden` (`git diff --stat`, open the PNGs), and commit them in the same commit as the change. Do not update references to silence an unexplained difference.
- New fixtures: add a builder to `tests/visual/visual_fixtures.py` (canvas at most 256 px), then generate its references as above.
- References are generated on Linux, because text rasterization differs across operating systems and FreeType versions. The suite is skipped on other platforms; set `VIXL_VISUAL=1` to run it anyway (expect text differences). CI runs it in a dedicated Linux job.

## Performance tests

`tests/test_perf.py` (marker `perf`, so `pytest -m perf` runs only these) gives the paths that once grew with the document a time budget: one move on 4,096 layers, a batch of moves, the overlap check on dense text, the composition check on 1,500 scattered labels, a poster's design check, re-rendering a large canvas of styled layers after a move, a full-canvas multiply, a dithered full-canvas gradient and a 100,000-character text flow. They run in the default suite and take a few seconds each. A budget is several times what the code needs on a loaded CI runner and far below what the old behaviour took; when a speed claim goes into the changelog, add or tighten a budget here instead of quoting a number. Caches that make these fast need a test that changes each input the cached value reads (see `tests/test_apply_speed.py`).
