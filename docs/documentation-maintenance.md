# Maintain the documentation and visuals

[Documentation home](README.md)

Documentation is organized by purpose: the hub and concepts establish a learning path;
tutorials make complete artifacts; topical guides explain features and limits; commands,
operations and live schemas provide syntax. Keep feature details in their existing guide
and link to them from tutorials rather than copying a second full reference.

## Rebuild the visual examples

From the repository root, using the latest source environment:

```bash
python -m pip install -e '.[dev]'
python examples/build_documentation.py
```

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

## Verify changes

1. Rebuild assets into a temporary directory and inspect the changed scenes.
2. Run tutorial commands in a fresh directory with explicit project paths. Verify the
   JSON recipes replay against the current runtime.
3. Open exported PDF/PPTX/animation files or inspect their structure: field names, page
   counts, editable objects and frame counts matter as well as screenshots.
4. Check local Markdown links and anchors, including images and editable downloads.
5. Run relevant engine regression tests when docs rely on recent behavior, then
   `git diff --check` and lint changed Python code.

Live provider examples need a configured service and appropriate credentials. Mark whether
they were actually exercised; offline contract tests do not establish current model
availability or output quality.

## Versions and navigation

Keep README, the hub, release installation URLs and package version consistent. Latest
`main` can contain source-only changes while the package version still matches a tag.
Label these explicitly and link the changelog's Unreleased section. Coverage should show
the release that shipped a feature, not retain stale “unreleased” labels.

Every topical guide links back to the hub. Preserve its existing filename and section
anchors when reorganizing navigation so external links continue to work. Add new guides
to the hub's feature table, not just to a long unstructured README list. Keep
`product-spec.md` as historical design context and use `coverage.md` for actual support.
