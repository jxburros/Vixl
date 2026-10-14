# Converting documents and tool calls from earlier releases

[Documentation home](README.md) · [File format](file-format.md)

This release removed the code that kept documents from earlier releases rendering as they used to: format-1 archives,
the pre-0.21 `lookup` field and `vixl upgrade`, house-style versions, and the fallbacks for recipes saved before 0.23.
The MCP server went from 51 tools to seven, and closed shapes draw their stroke inside and flush with the box. The
conversion kit rewrites old `.vixl` files and saved tool calls once, so that the current code opens them, and says
what it changed and what it could not convert.

The kit is separate from the engine (`src/vixl/convert/`): Vixl itself only reads current documents, and the
migration logic lives in the kit.

## Convert a document

```bash
vixl new 400x300 -o poster.vixl
vixl convert poster.vixl -o poster-converted.vixl --report poster-report.json
vixl convert poster.vixl --look current --dry-run
```

`vixl convert OLD.vixl` writes `OLD-converted.vixl` beside it (or the `-o` path), opens the result with the current
code and checks it against the [file format schema](file-format.md) before it is written. It never replaces a file:
an existing output is an `output_exists` error unless you pass `--overwrite`, and the source itself is never the
output. `--dry-run` converts and checks without writing; `--report FILE` also saves the report as JSON. Documents
saved by 0.27 or later pass through unchanged; for older ones each rule only touches what it finds, so a document
that needs nothing comes out the same.

A folder converts recursively into a new folder with the same layout. A file that fails is listed and the others still
convert; a `.vixl/variety.json` with the removed `house_style` key is converted too.

```bash
vixl new 300x200 -o drafts/card.vixl
vixl convert drafts --out converted
```

In Python:

```python
from vixl.convert import convert_file, convert_project, convert_directory

report = convert_file("poster-0.20.vixl", "poster.vixl")           # look="preserve"
report = convert_file("poster-0.20.vixl", look="current", dry_run=True)
project = convert_project("poster-0.20.vixl")                      # a Project in memory; project.conversion is the report
convert_directory("old-docs", "converted")
```

An SVG exported by a development build between the SVG round trip and payload version 2 carries its document as
payload version 1 (state plus base64 images and fonts); current Vixl imports such a file as plain SVG elements.
`vixl convert OLD.svg -o NEW.vixl` reads the payload instead and writes the editable document, converted like a
`.vixl` saved by 0.26 (an SVG whose payload left out images is refused: convert the original `.vixl`).

Other options: `--history drop` starts a new undo history instead of converting every revision, and
`--saved-by VERSION` names the release that saved a document whose `vixl_version` is missing or wrong. `--batch`
treats the source as saved tool calls, like `vixl convert-batch`.

## Two modes

| Mode | What it does | Use it when |
| --- | --- | --- |
| `preserve` (default) | Keeps the old look: behaviour that used to be implied is written into explicit fields (a white fill, a padding, a line height, a box position), and fields the current code no longer reads are rewritten into the ones it does. | The document should look and edit as it did. |
| `current` | Only rewrites what the current code cannot read (the archive format, the `lookup` field, the house-style stamp, out-of-range values) and lets today's defaults apply. Every place that will look different is listed under `warnings`. | You want the current defaults and a list of what moves. |

## What is converted

Each change in the report has a `change` ID from this table. "Saved before" is the release whose documents the rule
applies to; rules without one look at the fields themselves.

| `change` | Saved before | `preserve` | `current` |
| --- | --- | --- | --- |
| `archive-format` | 0.11 | Format 1 becomes format 2 (the rest of `project.json` is the same). | Same. |
| `manifest-fields` | | `upgraded_from` (from `vixl upgrade`) and other unknown keys are removed. | Same. |
| `lookup-field` | 0.21 | A layer's `lookup` field becomes a `lookup` effect at the end of its stack, where it rendered. | Same. |
| `house-style-version` | | `house_style_version` is removed from `design_defaults` and its direction (and `house_style` from `.vixl/variety.json`). A warning notes that re-rolling or re-applying the layout from the stored seed now gives the current house style. | Same. |
| `open-shape-fill` | 0.21 | Open shapes (lines, waves, open paths) with a stroke and no fill get the explicit white fill they were drawn with. | Warning: now unfilled. |
| `effects-before-transform` | 0.21 | Warning only: effects on rotated, flipped or skewed layers now run before the transform. | Same. |
| `temperature-tint-scale` | 0.21 | `temperature` and `tint` amounts move to the multiplicative scale (× 0.1185 and × 17.6, capped at ±100). Approximate: it matches the shift on mid grey. | Values beyond ±100 are capped; a warning says the rest read stronger (temperature) or weaker (tint). |
| `text-box-height` | 0.24 | A text box given only a width kept its height and cut off the lines below it; the height is made explicit so it still does, and `check` reports the overflow. | Warning: the box grows and the hidden lines show. |
| `irregular-strength` | | `irregular` and `tear` recipes without a strength (made before 0.23) get `strength: "natural"`, the strength they were drawn at. The drawn outline is stored, so this matters when the recipe is edited. | Warning: an edit redraws at `subtle`. |
| `diagram-line-height` | | Diagrams without a `line_height` (before 0.23) get the multiple that gives their old label leading (0.18 × size over the font's pitch). | Warning: the next `diagram-set` uses the caption line height. |
| `chart-padding` | | Charts in documents made before house style 3 (every plain document, and designed documents before 0.24) get `padding: 0.8 × font size`, so a chart edit keeps the spacing. | Warning: the next chart edit pads by two spacing units. |
| `heading-wrap` | | Boxed headings in documents before house style 4 get `wrap: "greedy"`, so resizing the box keeps greedy breaks. | Warning: a resize balances the lines. |
| `scatter-distribution` | | `pattern-scatter` tiles without a `distribution` get `poisson`, so a rebuild keeps every copy where it is. | Warning: a rebuild lays the tile out progressively. |
| `closed-stroke-geometry` | 0.27 | When the installed renderer draws closed strokes flush with the box: plain rectangles, rounded rectangles, capsules and ellipses with a visible stroke move in by half the stroke on every side (the centre stays put, also when rotated), keeping their corner radius (a default radius is stored explicitly). The ink lands where it was. The source shape kept by an `irregular` record and the positions layer comps store move too. | Warning: the stroke now starts at the box edge, so the shape looks half a stroke larger. |
| `rectangle-radius` | 0.27 | A `rectangle` with a non-zero `radius` (drawn rounded in PNG, square in SVG and PDF) becomes the `rounded-rectangle` it drew as, as `normalize` now does for new operations. | Warning. |
| `styled-stroke-align` | 0.27 | A dashed, multi-stroke or profiled stroke, or a catalog shape's stroke (heart, arrow, speech bubble …), without `stroke_align` gets `"center"`, its old default. | Warning (with the flush renderer): the stroke now sits inside. |
| `polygon-joins` | 0.27 | With the flush renderer: plain polygons, stars and shortcut shapes keep their box; their stroke's outer corners were round and are now mitred, so they get `line_join: "round"`. | Warning: the corners are sharp. |
| `thick-stroke` | 0.27 | Warning only, with the flush renderer: a plain stroke as wide as its shape drew nothing and now fills the shape with the stroke colour. | Same. |
| `dash-fit` | | Dashed shapes (or extra `strokes` with a dash) get `dash_fit: false`: the pattern was drawn at its exact lengths from the start of the outline. | Warning: the pattern is fitted to the corners. |
| `pdf-bleed` | 0.23 | Warning only: the canvas holds a bleed rounded up to whole pixels, so a PDF export is a pixel larger than trim plus bleed. | Same. |
| `history` | | Every undo revision is converted the same way (`--history drop` keeps only the current state); the report gives the count under `history`. A warning says so when the history could not be read. | Same. |
| `transaction` | | A document saved inside an open transaction is rolled back to its last committed state (warning). | Same. |

Polygons and stars already drew their stroke from the edge inward (only their corners change), and lines, arcs and
paths keep their geometry. Which stroke model applies is measured on the installed renderer
(`report.stroke_model`: `inset` or `flush`), so a document converted by a release that still insets strokes keeps its
boxes.

## The report

`vixl convert` prints a line per file and the warnings in a terminal, and the full JSON when piped or with `--json`:

```json
{
  "converted": [{
    "source": "poster-0.20.vixl", "output": "poster.vixl", "dry_run": false, "saved_by": "0.20.0",
    "look": "preserve", "stroke_model": "inset", "history": {"revisions": 6, "kept": true},
    "changes": [
      {"change": "lookup-field", "layer": "sky", "field": "effects", "lut": "warm",
       "reason": "The lookup field became a lookup effect at the end of the effect stack, where it rendered"},
      {"change": "temperature-tint-scale", "layer": "sun", "field": "effects.temperature.amount", "before": 40,
       "after": 4.7, "reason": "temperature moved to the multiplicative -100…100 scale …"}
    ],
    "warnings": [],
    "counts": {"changes": 2, "warnings": 0}
  }],
  "failed": [],
  "summary": {"files": 1, "converted": 1, "failed": 0, "changes": 2, "warnings": 0,
              "by_change": {"lookup-field": 1, "temperature-tint-scale": 1}}
}
```

Each change names the `layer` (or the document `field`), what changed (`before`, `after`) and why; `warnings` lists
what was not converted, and in `current` mode what will look different. A file that could not be converted is listed
under `failed` with its `error` code and `message`.

## Convert saved tool calls

`vixl convert-batch` rewrites saved MCP calls, operation batches and MCP client configurations for the seven-tool
server. It reads JSON (one call, a list of calls, a JSON-RPC `tools/call`, a `tool_use` block with `name` and
`input`, an operation batch, or an `mcpServers` configuration) or JSONL (one call per line), and writes
`NAME-converted.json` (`.jsonl` for JSONL) beside the source unless `-o` names another file; `--dry-run`, `--report FILE`
and `--overwrite` work as for documents. Client prefixes such as `mcp__vixl__` are kept.

<!-- docs-test: save old-calls.json -->
```json
[
  {"tool": "vixl_compose", "arguments": {"path": "card.vixl", "size": "instagram-post", "layout": "poster-classic",
                                          "exports": ["card.png"]}},
  {"tool": "vixl_import_image", "arguments": {"path": "photo.jpg", "name": "photo"}},
  {"tool": "vixl_render_preview", "arguments": {"max_width": 400}},
  {"tool": "vixl_export_file", "arguments": {"path": "card.pdf", "dpi": 300}}
]
```

```bash
vixl convert-batch old-calls.json -o new-calls.json
```

gives

```json
[
  {"tool": "vixl_apply", "arguments": {"create": {"path": "card.vixl", "size": "instagram-post",
                                                    "layout": "poster-classic"}, "options": {"exports": ["card.png"]}}},
  {"tool": "vixl_apply", "arguments": {"operations": [{"type": "import-image", "path": "photo.jpg",
                                                         "name": "photo"}]}},
  {"tool": "vixl_render", "arguments": {"action": "preview", "options": {"max_width": 400}}},
  {"tool": "vixl_export", "arguments": {"kind": "file", "path": "card.pdf", "options": {"dpi": 300}}}
]
```

Parameters the new tool advertises stay at the top level and the rest go into `options`, where each action reads
them ([MCP tool surface](mcp-toolsets.md)). Operations inside batches are unchanged, except that a
`house_style_version` field is dropped. In an MCP configuration, `vixl mcp --tools core|compact|all` and
`--schema full|slim` are removed (`--tools ai` stays) and so are the `VIXL_MCP_TOOLS` and `VIXL_MCP_SCHEMA`
environment variables. In Python: `vixl.convert.convert_batch(value)` returns `(converted, report)`.

Every tool of 0.26 and earlier and what replaces it (generated from `vixl.convert.batches.TOOLS`):

<!-- conversion-table: start -->
| Earlier tool | Now |
| --- | --- |
| `vixl_document_create` | `vixl_document(action='create')` |
| `vixl_document_open` | `vixl_document(action='open')`; upgrade dropped |
| `vixl_document_close` | `vixl_document(action='close')` |
| `vixl_document_inspect` | `vixl_document(action='inspect')`; detail='full' → verbose |
| `vixl_workspace_list` | `vixl_document(action='list')`; directory → path |
| `vixl_template_create` | `vixl_document(action='create')`; name → template |
| `vixl_history` | vixl_document with the history action: list → history, undo, redo, checkpoint, checkout, branch, begin, commit, rollback, compact |
| `vixl_review_notes` | vixl_document(action='notes'): add → text, resolve → resolve |
| `vixl_operations_apply` | `vixl_apply` |
| `vixl_compose` | vixl_apply(create={path, size, layout …}, operations, check, preview; exports in options) |
| `vixl_workflow` | vixl_apply(workflow=action, request) |
| `vixl_adapt_layout` | vixl_apply(workflow='adapt-sizes', request={sizes, formats …}) |
| `vixl_resource_add` | vixl_apply(workflow='resource-save', request={kind, name, value}) |
| `vixl_import_image` | an `import-image` step in `vixl_apply` |
| `vixl_import_document` | an `import-document` step in `vixl_apply` |
| `vixl_import_font` | an `import-font` step in `vixl_apply` |
| `vixl_font_pair` | a `font-pair` step in `vixl_apply` |
| `vixl_font_install` | a `font-install` step in `vixl_apply` |
| `vixl_styles` | list/get → vixl_reference('styles'); apply → a style-use step in vixl_apply; check → vixl_check(checks=['style']) |
| `vixl_roll` | apply: true → a roll step in vixl_apply; otherwise vixl_reference('roll') |
| `vixl_text_add` | a text operation in vixl_apply |
| `vixl_check` | `vixl_check(action='design')` |
| `vixl_validate` | `vixl_check(action='validate')`; detail='full' → verbose |
| `vixl_measure` | `vixl_check(action='measure')` |
| `vixl_measure_spacing` | `vixl_check(action='spacing')` |
| `vixl_spatial` | `vixl_check(action='spatial')` |
| `vixl_pixels_inspect` | `vixl_check(action='pixels')` |
| `vixl_render_preview` | `vixl_render(action='preview')` |
| `vixl_render_compare` | `vixl_render(action='compare')` |
| `vixl_timeline_preview` | `vixl_render(action='timeline')` |
| `vixl_timeline_inspect` | `vixl_render(action='timeline-inspect')`; detail='full' → verbose |
| `vixl_animation_preview` | `vixl_render(action='animation')` |
| `vixl_animation_inspect` | `vixl_render(action='animation-inspect')` |
| `vixl_export_file` | `vixl_export(kind='file')` |
| `vixl_export_batch` | `vixl_export(kind='batch')` |
| `vixl_export_animation` | `vixl_export(kind='animation')` |
| `vixl_export_timeline` | `vixl_export(kind='timeline')` |
| `vixl_export_audio` | `vixl_export(kind='audio')` |
| `vixl_export_icons` | `vixl_export(kind='icons')`; directory → path |
| `vixl_export_character` | `vixl_export(kind='character')`; output → path |
| `vixl_guide` | vixl_reference(topic=brief), or vixl_reference() without a brief |
| `vixl_capabilities` | `vixl_reference(topic='capabilities')`; topic → name |
| `vixl_operation_schema` | `vixl_reference(topic='operations')`; types → name |
| `vixl_workflow_schema` | `vixl_reference(topic='workflows')` |
| `vixl_sizes_list` | `vixl_reference(topic='sizes')`; search → name |
| `vixl_layouts_list` | `vixl_reference(topic='layouts')` |
| `vixl_fonts` | vixl_reference('fonts', name=family or pairing, view …) |
| `vixl_brushes_list` | `vixl_reference(topic='brushes')` |
| `vixl_color` | `vixl_reference(topic='color')`; colors → name |
| `vixl_resources_list` | `vixl_reference`; kind → topic |
| `vixl_resource_get` | vixl_reference(topic=kind, name) |
| `vixl_job` | unchanged |
| `vixl_models_list` | unchanged |
| `vixl_ai_generate` | unchanged |
| `vixl_ai_remove` | unchanged |
| `vixl_ai_content_aware_fill` | unchanged |
| `vixl_ai_select_subject` | unchanged |
| `vixl_ai_remove_background` | unchanged |
| `vixl_ai_select_object` | unchanged |
| `vixl_ai_plan` | unchanged |
| `vixl_ai_analyze` | unchanged |
| `vixl_ai_upscale` | unchanged |
| `vixl_ai_regenerate` | unchanged |
| `vixl_ai_extend` | unchanged |
<!-- conversion-table: end -->

The report lists each rewrite as a change (`tool`, `operation-field`, `server-flag`, `server-env`) with its position
in the file under `at`. A tool name that is not in this table and not a current tool is left as it is and reported as
an `unmapped-tool` warning; a dropped parameter is a `parameter` warning.

## What is not converted

- **Look changes with no stored field.** Rendering that changed without a setting to restore it: effects on turned
  layers (reported), the in-place drawing and gradient dithering of [render parity](render-parity.md), text set about
  a pixel higher than in 0.10, and the width of irregular ink ribbons. These stay within a few percent of edge pixels.
- **Defaults for new content.** A sprite, timeline, stack, text flow or container added to a converted document gets
  today's defaults (shaded sprites, seamless loops, 2u gaps …); the kit only fixes what is already in the document.
  A timeline cannot be stored with `loop_mode: "off"`: an existing timeline without `loop_mode` keeps playing once.
- **Seeded rolls.** Rolling or re-applying a layout from a document's stored seed gives the current house style; the
  old roll tables are gone (`house-style-version` warns).
- **Keyframes.** Animated position, size or effect amounts are not shifted or rescaled (warned).
- **Recorded operations.** History revisions keep the operations that made them as they were; replaying them
  (`reproduce`) runs today's code.
- **Exact colour.** The temperature and tint rescale matches mid grey; saturated colours can differ by a few levels.
- **PDF bleed.** A bleed rounded up before 0.23 stays rounded (warned); re-create the canvas for the exact bleed.
- **Shell scripts.** `vixl upgrade FILE` is now `vixl convert FILE`, and `vixl roll --house-style N` has no
  replacement; command lines in scripts are not rewritten.

## How it is tested

`tests/fixtures/convert/` holds small documents made by v0.10.0 (format 1), v0.20.0, v0.22.1, v0.26.0, the last
commit before the compatibility code was removed (afaee33) and the last build with inset strokes (9d0a4ce, which also
wrote a version-1 SVG), each with the render that release made of it (`python -m scripts.convert_fixtures` rebuilds
them from the tags). `tests/test_convert.py` converts every one, opens and schema-checks the result, and compares
its render with the old one: a pixel counts as different when a channel moves by more than 32 levels, and at most
0.5 % of pixels may differ, with a mean difference under two levels (gradients are dithered now). The exceptions are
measured differences with no field behind them: 2.5 % for irregular outlines (their ribbons are drawn differently
since render parity), 2.5 % and a mean of three for the shape fixtures (the old renderer supersampled thick strokes
and put their anti-aliased edges up to half a pixel off the exact outline the flush rule draws; a `current`
conversion of the same files differs by 12–19 %), and 5 % for v0.10 text (set about a pixel higher since 0.20).
Edits after conversion are tested too: a chart redrawn and an irregular outline regrown from its recipe in a
`preserve` conversion match the old render, and in a `current` conversion they do not.
