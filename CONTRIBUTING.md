# Contributing

Use the canonical operation schema for CLI, Python, REST and MCP changes. Keep historical spellings in `normalize.py`; aliases must validate and execute through the same implementation as their canonical operation. New operations need a short description, typed and described fields, and regression coverage of their public behavior.

Run `pytest -q` and build the distributions before submitting a release change. Keep the package, plugin manifests and versioned installation URLs synchronized; document user-visible changes in `CHANGELOG.md`. Release automation publishes only after Linux and Windows verification and installer checks succeed. See [the release process](docs/reference/releases.md).

Commit messages, generated pull requests, issue text and generated artwork should describe the work without model signatures or authorship trailers. Keep comments that explain constraints, tradeoffs or non-obvious behavior; remove comments that only repeat the next statement. Provider configuration identifiers are functional data and should remain intact.

Showcases, experiments, films, marketing media, published evaluation results and large content packs belong in
[VixlExamples](https://github.com/jxburros/VixlExamples), not here; link to them from the docs. Keep media in this repository only when
tests, docs or packaging need it (`docs/assets`, `assets/`, `examples/`, `tests/fixtures`).

## New features: core or plugin

Optional features live in built-in plugins under `src/vixl/plugins/` and join the core through the registry in
`vixl.plugins`. Before adding a feature, go through the parameters in [plugins](docs/reference/plugins.md#is-a-new-feature-a-plugin)
and state the decision in the pull request. The core never imports a plugin module; `tests/test_plugins.py` checks
this and lists the remaining exceptions. Large data that only some features use is a content pack in
[VixlExamples](https://github.com/jxburros/VixlExamples/tree/main/packs), downloaded on first use by `vixl.packs`.

## Changing a default

Defaults for sparse briefs live in the house style (`src/vixl/data/house-style.json`, read through `src/vixl/house_style.py`); read values from there instead of adding constants. Pre-release: breaking changes are allowed; note them in the changelog, and do not add version switches to the engine: documents saved with older behaviour are handled by the conversion kit (`src/vixl/convert/`, [converting](docs/reference/converting.md)), which the engine never imports. Default changes must still pass the house-style quality/diversity eval. Compare `python -m evals.house_style --compare evals/house-style-baseline.json` before and after; quality must not fall. See [house style](docs/project/house-style.md#changing-defaults-h2).

## Visual regression tests

`tests/visual` renders a small set of fixture documents (shapes, paths, text, gradients, effects, raster resampling, blends, groups, charts, organic shapes) and compares them with reference files in `tests/visual/golden`: PNG renders for every fixture, SVG and PPTX structural text snapshots, and PDF exports rendered to PNG with pypdfium2. Image comparison has a tolerance (a pixel differs when a channel moves by more than 3; the test fails when more than 0.05% of pixels differ or any channel moves by more than 48), so anti-aliasing noise does not fail the suite but a changed colour, shape or position does.

- Run: `pytest -m visual` (or `pytest tests/visual`). A failure prints the reference, actual and diff paths; the actual output and a `reference | actual | difference` image are written to `tests/visual/_failures/` (git-ignored; CI uploads it as an artifact).
- Update after an intended render change: `VIXL_UPDATE_GOLDEN=1 pytest tests/visual`, review the changed files in `tests/visual/golden` (`git diff --stat`, open the PNGs), and commit them in the same commit as the change. Do not update references to silence an unexplained difference.
- New fixtures: add a builder to `tests/visual/visual_fixtures.py` (canvas at most 256 px), then generate its references as above.
- References are generated on Linux, because text rasterization differs across operating systems and FreeType versions. The suite is skipped on other platforms; set `VIXL_VISUAL=1` to run it anyway (expect text differences). CI runs it in a dedicated Linux job.

## Performance tests

`tests/test_perf.py` (marker `perf`, so `pytest -m perf` runs only these) gives the paths that once grew with the document a time budget: one move on 4,096 layers, a batch of moves, the overlap check on dense text, the composition check on 1,500 scattered labels, a poster's design check, re-rendering a large canvas of styled layers after a move, a full-canvas multiply, a dithered full-canvas gradient and a 100,000-character text flow. They run in the default suite and take a few seconds each. A budget is several times what the code needs on a loaded CI runner and far below what the old behaviour took; when a speed claim goes into the changelog, add or tighten a budget here instead of quoting a number. Caches that make these fast need a test that changes each input the cached value reads (see `tests/test_apply_speed.py`).
