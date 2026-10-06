# Vixl: notes for agent contributors

Vixl is a layered-image engine (CLI, Python API, MCP server, REST) in `src/vixl`. Tests are in `tests/`,
user docs in `docs/`, the agent skill in `skills/vixl/`. `CONTRIBUTING.md` has the full rules.

## Running tests
- `pytest -n auto` runs the whole suite (about 2,250 tests). Iterate on one file first: `pytest -q tests/test_x.py`.
- If `vixl` is editable-installed from another checkout, set `PYTHONPATH=$PWD/src` on the same command line.
- `pytest -m visual` runs the golden-image suite in `tests/visual` (Linux only; references in
  `tests/visual/golden`). After an intended render change, regenerate with
  `VIXL_UPDATE_GOLDEN=1 pytest tests/visual`, review `git diff --stat` and the PNGs, and commit them with the change.
  Failures write reference/actual/diff images to `tests/visual/_failures/`. Never update goldens to silence an unexplained diff.

## Conventions
- **Schema.** Operation schemas live in `schema.py` and friends. Shared constants (`S`, `N`, `B`, ...) are never
  mutated: give a field its own description with `schema.field(base, "text")`. Every field needs a type and a
  description (`tests/test_operation_docs.py`).
- **Aliases.** Historical spellings and forgiving input (camelCase, `rect`, `font_size`, `"50%"`, `"none"`) are handled
  in `normalize.py` and reported under `normalized`. Opacity is 0-1 everywhere; use `normalize.opacity`.
  Remove duplicate concepts, not leniency.
- **Targets.** `targets.py` classifies every operation as `EACH` (per-layer, fans out over `targets` inside one atomic
  batch), `JOINT` (group, align, distribute, pathfinder ...) or one. When you add an operation, add it to the right set
  and regenerate the table in `docs/operations.md` from `vixl.targets.markdown_table()`; a test compares them.
- **Geometry.** One anchor table (`geometry.ANCHORS`, `canonical_anchor`), one Bezier evaluator (`geometry.bezier_points`),
  one number formatter (`geometry.compact_number`). Open shapes and paths with a stroke and no fill stay unfilled in
  every renderer: use `geometry.OPEN_SHAPES` and `default_fill(layer)`, do not re-derive it.
- **Guidance.** Craft guidance texts live in one registry, `guidance.py`; `vixl_guide`, `vixl_resource_get` and
  `vixl_capabilities` all read it. Do not add a second copy. Tool descriptions must not mention unknown `vixl_*` names
  (a test checks docs and skills).
- **Effects.** Effects run in the layer's own frame before flip/rotate/skew (`render.layer_effects`); LUT lookups are
  ordinary stack effects.
- **Exports.** SVG, PDF, PPTX and raster share the same fill/stroke rules; a change to one usually needs the others.

## Checklist for a user-visible change
1. Code plus a regression test that fails without it.
2. Docs: the relevant `docs/*.md`, and `skills/vixl/SKILL.md` and `skills/vixl/references/*.md` when behaviour,
   fields or defaults change. Grep for removed names; do not leave stale text.
3. `CHANGELOG.md`: add to the current top section. Breaking changes need a migration hint.
4. Goldens, if rendering changed (see above).
5. Version bumps stay synchronized (`src/vixl/__init__.py`, plugin manifest, `.mcp.json`, README and install URLs); see
   `docs/releases.md`. The self-updater and release manifest path (`src/vixl/updater*`, `distribution/`) must stay stable.

## Rules
- Do not put model names, signatures or authorship trailers in code, docs, generated artwork or commit/PR text
  (CONTRIBUTING.md). Comments explain constraints and non-obvious behaviour, not the next line.
- Exports refuse to overwrite existing files unless `overwrite=True`.
