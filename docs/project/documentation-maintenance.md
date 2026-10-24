# Maintain the documentation and visuals

[Documentation home](../README.md)

Documentation is organized by purpose, one folder per kind of page:

| Location | Kind | Put a page here when |
| --- | --- | --- |
| `docs/` (top level) | Learning path: [hub](../README.md), [overview](../overview.md), getting started, concepts, gallery, use-case catalog, troubleshooting | Every new user needs it |
| `docs/tutorials/` | Walkthroughs that build one complete artifact | It is a start-to-finish lesson with committed assets |
| `docs/guides/<area>/` | Task-oriented feature guides (`layout`, `shapes`, `finishing`, `text`, `images`, `motion`, `output`, `automation`) | It explains when and how to use a feature and its limits |
| `docs/reference/` | Syntax, formats, interfaces, coverage, releases | A reader looks it up rather than reads it through |
| `docs/project/` | Decisions, plans, measurements, maintenance | Only people working on Vixl need it |
| `docs/assets/` | Generated visuals, gallery images, editable masters and recipes | A page embeds or links it |
| `skills/vixl/SKILL.md` | The agent skill's entry point: start-here path, core loop, top gotchas, feature map | Every agent needs it on every task (kept under 10,500 bytes by a test) |
| `skills/vixl/references/` | Agent reference pages, opened on demand from the feature map | An agent needs it for one kind of work |

Keep feature details in their existing guide and link to them from tutorials rather than
copying a second full reference. A new page goes into its folder's `README.md` index and the
hub's feature table in the same change. The use-case catalog keeps the reader's table (use case, route, time,
notes); where each figure comes from goes into [use-case evidence](use-case-evidence.md). Guidance that several
pages need, such as the finishing checklist, lives once in the guidance registry (`src/vixl/guidance.py`); pages
link to it (`vixl guide finishing`) instead of copying it.

## Rebuild the visual examples

From the repository root, using the latest source environment:

```bash
python -m pip install -e '.[dev]'
python examples/build_documentation.py
python examples/build_poster.py --output examples/output  # copy after-hours.png to docs/assets/example-poster.png, after-hours.vixl to examples/
python examples/build_filter_gallery.py     # docs/assets/filter-gallery.png
python examples/build_organic_gallery.py    # docs/assets/organic-gallery.png
python examples/build_irregular_gallery.py  # docs/assets/irregular-gallery.png
python examples/build_drawing_pipeline.py   # docs/assets/drawing-pipeline.png
```

The gallery builders write into `docs/assets/` by default and also take `--output DIR`.

The builder needs no network, AI service, GPU or ffmpeg. It intentionally uses the bundled
font for portable proofing. Outputs go to `docs/assets/generated/` by default; use
`--output /tmp/vixl-docs` to validate without replacing committed assets.

For each of eight scenes it saves a PNG preview, `.vixl` master and JSON operation recipe.
It also exports campaign/form variants, real fillable PDF, multi-page PDF, editable PPTX,
animated WebP and static motion poses. `manifest.json` records scene sizes, data where
applicable, runtime version and bounds reports. The builder verifies scene bounds and
save/load render equivalence. These are structural checks; inspect pictures as well.

The editable masters are explicitly included by `.gitignore`. Publish them alongside
previews so readers can learn by inspecting and editing actual layers. Documentation
charts must identify illustrative data; diagrams should explain a real workflow and
avoid implying capabilities the engine does not implement.

## Executable examples

`tests/test_docs_executable.py` (`pytest -m docs`, also part of the normal run) runs the
`vixl …` lines of every `bash`/`sh` block in `docs/` and `skills/` in a fresh temporary
workspace, and validates every JSON operation block against the operation schema before
applying it to a new document. New and edited blocks are picked up automatically.

- A command on a document the block made with `vixl new` must succeed. Other snippets run
  against a stand-in document and may fail only for missing context (a layer or file the
  reader supplies), never with an unknown command, option, field or value.
- Synopsis lines (`[--flag]`, `a|b`, `…`, `NAME` placeholders), servers, AI providers,
  downloads and, without ffmpeg, video commands are not run.
- Steer a block with an HTML comment on the line before its fence:
  `<!-- docs-test: continue -->` runs a shell block after the page's previous shell block in the
  same workspace (walkthroughs); `<!-- docs-test: save hello-ops.json -->` writes a block's text
  to that file for the page's shell blocks; `<!-- docs-test: skip REASON -->` leaves a block out.
- Write examples a reader can run top to bottom: give repeated exports different file names
  and remove a feature before switching its mode.

## Verify changes

1. Rebuild assets into a temporary directory and inspect the changed scenes.
2. Run tutorial commands in a fresh directory with explicit project paths (the executable
   examples test does this for every block). Verify the JSON recipes replay against the
   current runtime.
3. Open exported PDF/PPTX/animation files or inspect their structure: field names, page
   counts, editable objects and frame counts matter as well as screenshots.
4. Check local Markdown links and anchors, including images and editable downloads.
5. Run relevant engine regression tests when docs rely on recent behavior, then
   `git diff --check` and lint changed Python code.

Live provider examples need a configured service and appropriate credentials. Mark whether
they were actually exercised; offline contract tests do not establish current model
availability or output quality.

## Versions and navigation

Keep README, the hub, release installation URLs and package version consistent: the version
in `src/vixl/__init__.py`, `.claude-plugin/plugin.json`, the `.mcp.json` tag URL, the install
URLs in `README.md` and `getting-started.md`, the action pin in `ci.md` and the tag example in
`releases.md` ([release steps](../reference/releases.md#maintaining-releases)). Latest
`main` can contain source-only changes while the package version still matches a tag.
Label these explicitly and link the changelog's Unreleased section. Coverage should show
the release that shipped a feature, not retain stale “unreleased” labels;
`tests/test_docs_coverage.py` fails when `coverage.md` has no `(X.Y)` row for the changelog's newest release.

Every topical guide links back to the hub. Moving a page breaks external links to it, so
move pages rarely, keep filenames and section anchors, and update every reference in the same
change: links in Markdown, `docs/…` paths in code, tests and scripts, and the skill references.
Add new guides to the hub's feature table, not just to a long unstructured README list. Keep
`product-spec.md` as historical design context and use `coverage.md` for actual support.
