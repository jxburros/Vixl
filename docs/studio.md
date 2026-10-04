# Creative tools and collaborative projects

All editing uses the existing atomic operation engine. Workspace resources, design tests,
effects, plugin packs, project groups and agent branches use **one workflow dispatcher**:

```bash
vixl workflow schema
vixl -p campaign.vixl workflow ACTION --request request.json --workspace .
vixl mcp --workspace . --tools compact --schema slim
```

MCP: `vixl_workflow(action, request, document?)`; Python:
`dispatch(Session("campaign.vixl", workspace="."), action, request)` from
`vixl.workflows`. `vixl_workflow_schema` discovers action names and allowed/required fields.
The compact profile exposes 12 tools for documents, operations, workflow discovery/execution,
preview, import and export. Use `core` for the full typography/catalog convenience tools,
and `ai` for provider-backed tools. Existing tool names remain available in the original profiles.
REST exposes the document/resource actions at `/workflow/{action}`; branch, group and plugin
pack management need a workspace CLI/MCP/Python session.

Run the offline tour:

```bash
python examples/build_studio_demo.py --output examples/output/studio
```

It generates editable projects, a checked campaign, a standalone HTML export and an effect
contact sheet. Choose a fresh output directory when repeating it. No external AI or fonts
are needed for this demonstration; choose production typefaces for actual deliverables.

## Wand, lasso and pen

```bash
vixl select wand 120 80 --tolerance 20
vixl select wand 120 80 --tolerance 20 --global
vixl select lasso '[[20,20],[180,30],[140,120],[30,90]]' --feather 2
vixl select path 'M20 20 Q100 0 180 20 L140 120 Z'
vixl mask from-selection portrait
vixl pen --name flourish --points '[[20,100],[80,20],[150,120],[220,40]]' --stroke '#006d77' --stroke-width 4
```

Wand samples the rendered canvas at an integer seed pixel. Tolerance is the maximum RGBA
channel difference (0–255); fully transparent seed pixels compare alpha alone. The default
is a four-connected region; `contiguous:false` (`--global`) selects all matching pixels.
Lassos use canvas coordinates. Paths accept the full SVG path language, including relative
coordinates, repeated coordinates, arcs, and smooth Bézier commands. Subpaths in lasso masks
are unioned (holes are not subtracted automatically). All selections support replace/add/
subtract/intersect and feathering, and feed existing masks and selection-scoped effects.
This is deterministic color selection, not semantic segmentation or magnetic edge tracing.

Pen accepts either `points` (smooth Catmull–Rom interpolation, `smooth:false` for straight
segments) or explicit anchor nodes. Handle coordinates are absolute in the path's local space:

```json
{"type":"pen","name":"curve","width":240,"height":160,"nodes":[
  {"point":[20,120],"out":[40,10]},
  {"point":[220,120],"in":[180,10]}
],"stroke":"#006d77","stroke_width":4,"fill":"transparent"}
```

Use `target` instead of `name` to replace an existing path's geometry while preserving its
layer ID, styles and history. `closed:true` closes an irregular shape; set a fill as needed.
Shapes remain editable through resizing, masks, pathfinder, styles and SVG export. The pen
supports up to 512 anchors; paths support 1,024 normalized commands and 32 KiB of source.

## Palettes and tests that measure the picture

```json
[
  {"type":"palette-define","name":"brand","colors":["#003049","#edf6f9","#006d77"]},
  {"type":"palette-apply","name":"brand"}
]
```

`palette-define` stores a custom palette inside the document. `palette-apply` snapshots
catalog palettes into the document too, so reopening the project does not depend on a
user's resource file. Its default `policy:"strict"` assigns every role from the chosen
colors. `policy:"accessible"` retains the previous behavior of deriving additional colors
to improve contrast. Strict palettes can have poor contrast: check accessibility separately.
`roles:false` adds only numbered swatches. Role-linked artwork recolors; literal colors and
imported photographs are not automatically quantized.

Run workflow `palette-check` with:

```json
{"palette":"brand","tolerance":8,"max_fraction":0.01,"alpha_min":1}
```

It renders at full resolution and reports the out-of-palette fraction, pixel count,
maximum RGB distance and example offending colors. Transparent pixels below `alpha_min`
are excluded; an empty visible region reports an error/needs-review, never a vacuous pass.
An optional `region:[x,y,width,height]` scopes the measurement. Alpha is used for coverage,
not color matching. Antialiasing, shadows, gradients and translucent composites create
intermediate colors; set the tolerance and permitted fraction deliberately for the brief.
Defaults allow 8 RGB levels and 1% outside pixels. The demo declares a 2% edge allowance
before editing because its small composition contains antialiased type and curves.

For a repeatable acceptance test, freeze colors in the suite itself:

```json
{"type":"suite-set","name":"brand-contract","suite":{"rules":[
  {"id":"brand-pixels","kind":"palette","colors":["#003049","#edf6f9","#006d77"],"tolerance":8,"max_fraction":0.01}
]}}
```

A named `palette` (or the active palette when omitted) instead follows that document's
palette definition. Checks never recolor the artwork or change expectations.

## Make a custom test part of each brief

Seven ready-to-use suites are discoverable through workflow `resource-list`, kind `suites`:
`delivery`, `palette`, `opaque`, `print-ready`, `accessible`, `no-placeholders`, `containers`.
Read one with `resource-get`, then attach it with `suite-use`, e.g. `{"name":"palette"}`.
Run `check` with `{"suite":"palette"}`. Warnings and unmeasurable rules count as needs-review.

Start a custom contract in seconds:

```bash
python examples/studio/new_suite.py my-suite.json --palette '#003049' '#edf6f9' --text-target title
vixl -p campaign.vixl suite-set my-contract --file my-suite.json
# checks.json contains {"suite":"my-contract"}
vixl -p campaign.vixl workflow check --request checks.json --workspace .
```

Edit the generated rules to express the brief. Use `property` for dimensions and exact
content, `gap` for spacing, `text-fit` for readable text, `palette` for rendered colors,
`container` for modular rules, and `suite-capture` for intentional structural/pixel
baselines. Rules, animation sampling and checked production are described in
[production.md](production.md). Never weaken expectations to repair a failing picture.
An existing check is a starting point, not a substitute for the brief or visual inspection.

Save a custom suite for future projects with `resource-save`:
`{"kind":"suites","name":"my-contract","value":{"rules":[...]}}`.
Resources live in workspace `.vixl-resources.json`; workspace entries override the user
library, then built-ins. User CLI `palette add` / `template add` remains supported.
The example [brand contract](../examples/studio/brand-suite.json) is ready to customize.

Developers: `pytest tests/test_studio.py -q` covers pixel masks, geometry, palettes, templates,
reuse, plugin lifecycle, real concurrent writers, conflict resolution, recovery and interfaces.
Add behavioral tests alongside it, using small generated images and temporary workspaces.
Run the full `pytest -q` suite before shipping; it needs no live AI credentials. A runnable
agent brief or production recipe can also be paired with saved suites and added to `evals`.

## Modular templates, containers and saved shapes

Eight additions span simple and complex compositions: `modular-card`, `modular-quote`,
`modular-logo`, `modular-split`, `modular-story`, `modular-editorial`, `modular-campaign`,
`modular-gallery`. They use six interchangeable 480×320 containers, with text and geometric
variants. Text placeholders are registered and detected by the existing blanks check.

```bash
vixl template new modular-split -o campaign.vixl
vixl text slot-1/title --text 'New directions'
vixl text slot-1/body --text 'Made together'
vixl container-reflow slot-1
vixl container-swap organic-mark --target slot-2
```

`container-place` creates a named group at x/y. `container-swap` keeps that group's ID,
position, transforms and styles, replacing its children with a resource of the **same native
size**. Children get new IDs; external references to deleted children can prevent a swap.
Refer to the container group when coordinating agents. Reflow preserves child IDs.

Custom container resources contain `width`, `height`, `operations`, optional `defaults`,
and `rules`: `layout` free/vertical/horizontal/grid, `padding`, `gap`, `columns`, `max_items`,
`contain`. Content is self-contained text, shape, pen, solid or gradient operations, with
unique local names. Placed names become `container-name/local-name`. Use `${variable}`
placeholders and supply `variables` when placing/swapping. File reads and recursive content
are excluded. Placement and swaps enforce bounds and layout rules atomically.

After text/geometry edits, run `container-reflow`; it refuses overflow so content can be
resized or fitted explicitly. Each modular template includes the `container-layout` suite,
which detects later rule violations without silently moving artwork. Rules measure geometry,
not the visual spread of effects such as glows. Containers do not provide a live CSS engine.

Save a shape using workflow `shape-save`, `{"target":"my-shape","name":"brand-mark"}`.
Reuse it with `{"type":"shape-place","resource":"brand-mark","name":"mark","x":20,"y":20}`.
Optional width/height/fill/stroke overrides adapt it. Geometry, intrinsic dimensions and
resolved colors are saved; use the existing component library for full styled groups/assets.
Shapes, palettes, containers, templates, suites and effect workflows share resource-list/get/save.

## Effects as inspectable workflows

Five built-ins combine existing tools: `neon-sign` (overlay/glow/shadow), `vintage-print`
(sepia/grain/vignette), `comic-poster` (contrast/posterize/halftone), `cut-paper`
(overlay/stroke/shadow), and `ink-illustration` (grayscale/sketch/contrast).

```json
{"name":"neon-sign","variables":{"target":"headline","color":"#00f5d4"},"dry_run":false}
```

Pass this to `effect-run`. Inspect with `resource-get`, kind `workflows`; customize and
save with `resource-save`. A workflow has `description`, `defaults` and an operation list.
Execution is one undoable batch. Workflows cannot invoke arbitrary code, recursively invoke
other workflows, or redefine tests. Effects that append stack entries accumulate on rerun;
use undo or edit/remove those effects before applying again.

## Shared groups and concurrent agents

Workflow `group-define`:

```json
{"name":"launch","documents":["poster.vixl","story.vixl"],"shared":{
  "variables":{"headline":"Launch day"},"swatches":{"accent":"#006d77"}
}}
```

`group-apply` with `{"name":"launch"}` previews all members. Add `dry_run:false` to publish;
optional `operations` append a common edit batch and `suites` check every candidate before
publication. Shared parameters are applied explicitly, not live-linked. Any invalid member
prevents all writes. Locks and rollback handle ordinary failures. Durable backups and a journal
support `group-recover` after interruption; recovery refuses to overwrite later edits. Publication
is sequential, so this is not a cross-file filesystem transaction for readers ignoring locks.
`group-list` discovers groups. `group-show` reports membership/shared values and whether recovery is required. Files live
under `.vixl-groups/`; keep journals/backups until recovery finishes.

`branch-list` discovers agent branches; `branch-status` reads one manifest.
Agents working on one project can use independent branches:

1. `branch-fork` with `{"branch":"copy-agent","output":"copy-agent.vixl","author":"copy-agent"}`.
2. Work on that document using ordinary operations while another agent edits another fork.
3. `branch-merge` with `{"branch":"copy-agent"}` previews a three-way merge into the original.
4. If clear, repeat with `dry_run:false` and optionally `expected_head` from the preview's
   `source_head` to reject intervening source edits.

Layer IDs and individual fields merge independently. Conflicting field edits, edit/delete
collisions and incompatible layer-order changes report JSON-pointer paths with base/ours/theirs.
Here **ours is the original/shared project**, **theirs is the agent branch**. Resolve explicitly
with `resolutions:{"/layers/lyr_ID/x":"theirs"}` or edit the branch and retry. Merge validates
combined constraints/references; missing dependencies must be repaired before committing.
Independent additions survive; duplicate names still need renaming. Asset bytes are verified,
merges are undoable, and file locks serialize publication. Branch bases/manifests live in
`.vixl-branches/`; keep them until merged. Use a fresh branch name for subsequent work.
This is repository-style collaboration, not live cursors, presence or a network sync service.

## SVG import and HTML export

```bash
vixl import artwork.svg --svg-mode auto
vixl export artwork.html
```

`editable` remains the default SVG import mode: supported geometry becomes editable paths
and unsupported appearance fails explicitly. `appearance` accepts self-contained static SVG
supported by resvg, including gradients, masks, clipping, filters, groups, text and embedded
raster images. `auto` tries editable import, then uses appearance when a feature is unsupported.
Appearance import stores a raster layer **and the original SVG source** in the archive. It
reports the fallback; source geometry is not individually editable. Active content, scripts,
foreignObject, animation, file/remote references, entities and nested data-URI SVG are rejected.
Embed PNG/JPEG/WebP images; source size is limited to 4 MiB and normal canvas limits apply.
Text uses the bundled fallback font; arbitrary browser CSS/fonts are not reproduced exactly.

HTML export is a standalone responsive artwork page with a self-contained SVG image, escaped
accessible text and restrictive CSP. It needs no server, JavaScript or external assets. It is
an artwork export, not conversion into editable HTML layout components. CLI, Python, MCP
file export and REST `POST /export` (`format:"HTML"`) share the implementation.

## Plugin packs and trusted Python extensions

`plugin-install` takes `{"manifest":{...}}`; see [the example pack](../examples/studio/plugin.json).
Packs declare `api_version:1`, `name`, semantic `version`, optional exact-version `dependencies`,
and `resources` grouped by category. Resource names must start with `plugin-name-`. Installation
validates the whole manifest, dependencies and collisions, then atomically writes the workspace
resource catalog. `replace:true` upgrades a pack and removes its old resources. Updates that
break dependents or introduce cycles fail. `plugin-list` discovers installed packs without
executing code; `plugin-remove` refuses to remove a dependency. Copy owned resources under a
new name to customize them without changing the pack.

For explicitly trusted local Python code, installed entry points remain available:
`vixl.filters` for image filters and `vixl.operations` for operation producers. Enable with
`enable_plugins()` (or `--plugins` for existing CLI filters). An operation handler declares
`api_version = 1` and accepts `(document_snapshot, options)`, returning ordinary operations.
Call `vixl.plugins.run(project, name, options, dry_run=False)`. The snapshot is isolated;
returned operations are validated and applied atomically. Load/runtime exceptions become
structured errors. Python extensions are trusted code, not sandboxed. Services and project
archives cannot opt into or invoke them. Use declarative packs for portable agent extensions.
