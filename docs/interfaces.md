# Python, REST, MCP, and extension interfaces

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

See [spacing checks and pixel animation](pixel-animation-spacing.md) for the 0.9.0 tools and API examples.

See [design tools and template production](design-tools.md) for groups, clipping, shapes, styles, artboards, CSV rendering, measurements, and the other design operations.

## Python

```python
from vixl import Project, VixlError
from vixl.model import Limits

project = Project.load("poster.vixl", limits=Limits(max_pixels=16_000_000))
proposal = [{"type": "opacity", "target": "logo", "value": 0.7}]
print(project.apply(proposal, dry_run=True))
project.apply(proposal)
project.save()
```

`Project.apply(..., detail="compact")` returns changed fields keyed by stable layer ID; the Python API keeps `detail="full"` as its compatibility default.

`Project.import_image(path=None, *, url=None, data=None, name="image", credit=None, license=None)` embeds an image from a file, bytes or an `https://` URL as a new layer and returns its id, size, bounds, `asset` and `source` (see [Import existing artwork](#import-existing-artwork)).

`Project.save(path=None, *, overwrite=False)` writes the document. Saving to the file it was loaded from or last saved to always works; another existing `.vixl` is refused with `output_exists` unless `overwrite=True`, as `vixl new`, `vixl save` and exports do.

`Project.render()` returns a Pillow RGBA image; `Project.render(region=[x, y, width, height])` returns that crop (whole pixels inside the canvas), drawing only that part unless something in the document reads the whole canvas. In a notebook a `Project` displays as its rendered PNG, and `Project.show(page=None, region=None)` returns the image (optionally one page, cropped to `[x, y, width, height]`). `Project.export()` returns encoded bytes, optionally writing to a path. `Project.inspect()` returns an independent JSON-serializable state description. History methods: `undo`, `redo`, `branch`, `checkpoint`, `checkout`, `begin`, `commit`, `rollback`.

Loading does not implicitly trust linked image paths; use `allow_linked=True` only when those local file references are intended. Direct Python APIs are trusted local APIs and can import files. Exceptions expose `VixlError.code`, `.details`, and `.as_dict()`.

## REST

```bash
python -m pip install -e '.[server]'
vixl -p poster.vixl serve
```

Default binding is `127.0.0.1:8765`. OpenAPI is at `/docs`. To bind beyond loopback, configure a bearer token with `VIXL_API_TOKEN` and use `--host 0.0.0.0`; use TLS at a reverse proxy. `--token-env NAME` selects a different environment variable. A configured token protects all document APIs, including docs; `/view` serves a public empty HTML shell. Without a token, host-header validation restricts requests to loopback names. This is a local single-user service, not a multi-tenant hosted product.

| Route | Request / result |
| --- | --- |
| `GET /document` | Inspected state |
| `GET /layers` | Layer list |
| `GET /schema` | Canonical operation batch JSON Schema |
| `POST /operations` | `{operations: [...] or operations_path: "ops.jsonl", dry_run: false, detail: "compact", check?, suites?, preview?}` → change summary (use `full` for snapshots); `check`/`suites`/`preview` as for `vixl_operations_apply`, the preview as `preview_base64` |
| `GET /render` | PNG bytes |
| `POST /render` | `{variables: {title: "Hello"}}` → PNG bytes |
| `POST /validate` | `{profile: "instagram-post", rules: [...]}` → checks |
| `GET /history` | History graph and named references |
| `POST /history/{action}` | `{ref: "name", count: 1}`; undo/redo/branch/checkpoint/checkout/begin/commit/rollback |
| `POST /assets?name=photo` | Raw image bytes → imported layer; or an empty body with `url=https://…` to download one. `credit` and `license` are recorded in provenance |
| `POST /ai/{command}` | `{args: ["--prompt", "forest", "--provider", "local"]}`; uses locally configured providers |
| `POST /compose` | `vixl_compose` fields without `path`, `exports` or `operations_path` → a dry run: steps, findings, `preview_base64` |

```bash
curl http://127.0.0.1:8765/document
curl -X POST http://127.0.0.1:8765/operations \
  -H 'Content-Type: application/json' \
  -d '{"operations":[{"type":"move","target":"logo","x":20,"y":40}]}'
curl http://127.0.0.1:8765/render -o preview.png
```

REST sessions fix the project path when launched. Operation `path` and `linked` fields are rejected, and `font` accepts only a registered font name or role (`heading`, `body`), never a file; import image bytes with `/assets` and fonts with `/fonts` or `font install`. Services do not enable third-party plugins or linked-file reads. Local AI configuration is trusted, and services can invoke it. Do not share API access with users who should not be able to use your configured AI service. Authentication is all-or-nothing; there are no per-user roles or quotas.

## MCP

The Windows installer includes MCP. The Python base package includes MCP. Give Vixl an existing workspace directory that contains the images/documents the model should edit:

```powershell
vixl mcp --workspace "C:\Users\jeffr\Pictures\Vixl"
```

The workspace can start without any `.vixl` documents. MCP defaults to stdio using the official SDK; stdout contains protocol messages only. Configure your client to start it (escape Windows backslashes in JSON):

```json
{
  "mcpServers": {
    "vixl": {
      "command": "vixl",
      "args": ["mcp", "--workspace", "C:\\Users\\jeffr\\Pictures\\Vixl"]
    }
  }
}
```

Several agents sharing one server (common with subagents of one session) are the usual source of mistakes: see [several agents on one server](#several-agents-on-one-server) for `--require-document` and per-client documents.

If the client cannot find `vixl` on PATH, use the absolute executable path, normally `C:\Users\jeffr\AppData\Local\Programs\Vixl\bin\vixl.exe` for the Windows installer. Restart the client after installing/updating or changing its configuration. On macOS/Linux, use your installed `vixl` executable and a workspace such as `/home/you/Pictures/Vixl`.

### Recommended starting configuration

`vixl mcp` defaults to `--tools core --schema slim` (`VIXL_MCP_TOOLS` and `VIXL_MCP_SCHEMA` override it). Its tool list is about 60k JSON characters, against about 151k for `--tools all --schema full`,
the default in 0.21 and earlier; pass those flags to get the old behaviour. The offline reference suite passes with
both. With slim schemas, call `vixl_operation_schema` for the fields of unfamiliar operations.
`--tools compact --schema slim` (13 tools, about 24k characters) is the smallest surface; see
[MCP toolsets](mcp-toolsets.md) for the measurements.

### Two servers: core and AI

`vixl mcp` can serve its tools as two servers, so an agent loads only the tools it uses:

- `--tools core`: documents, operations, rendering, checks, export, sizes, layouts, fonts, color, brushes, animation, workflows, batch export, layout adaptation, jobs, and the guidance tools `vixl_guide` and `vixl_styles` (51 tools).
- `--tools ai`: the provider-backed tools (`vixl_ai_*`, `vixl_models_list`) plus `vixl_workspace_list`, `vixl_document_open`, `vixl_document_inspect` and `vixl_render_preview`, so the AI server can find layers and check its results, plus `vixl_job` (16 tools).

```json
{
  "mcpServers": {
    "vixl": {
      "command": "vixl",
      "args": ["mcp", "--workspace", "C:\\Users\\jeffr\\Pictures\\Vixl", "--tools", "core"]
    },
    "vixl-ai": {
      "command": "vixl",
      "args": ["mcp", "--workspace", "C:\\Users\\jeffr\\Pictures\\Vixl", "--tools", "ai"]
    }
  }
}
```

Give both the same workspace. Every edit is saved immediately and each server reloads a document that changed on disk (writes are serialized with file locks), so an image generated through `vixl-ai` appears in `vixl` on its next call. AI tools take `document=` or use the document opened with `vixl_document_open`. Leave out `vixl-ai` when no AI provider is configured. `--tools all` serves core and AI tools from one server.

Existing `vixl --project /absolute/path/poster.vixl mcp` configurations still work: they open that document and use its parent directory as the workspace. You can also pass `--workspace` explicitly; the starting project must be within it.

### Tools and workflow

Vixl is designed to be driven mainly by agents. The intended loop is: create or open a document → `vixl_operations_apply` in atomic batches (use `dry_run` to test) → `vixl_check` to find problems without looking → `vixl_render_preview` (with `region` to zoom) → fix → `vixl_export_file`. For a new piece whose content is known, `vixl_compose` runs that whole chain in one atomic call.

| Tool | Purpose |
| --- | --- |
| `vixl_workspace_list(directory, offset, limit)` | Discover workspace paths and the open documents |
| `vixl_document_create(path, width?, height?, background?, purpose?, size?, dpi?, orientation?, bleed?, seed?, variety?, font_pairing?, workspace_fonts?)` | Create and activate a new `.vixl` from pixels, a named size or a `purpose` (else 1080×1080); creates missing directories; refuses overwrites. Like every surface it rolls and stores `design_defaults`, uses the palette background unless `background` is given (transparent for logos, icons and favicons), and embeds the workspace default fonts from `brand.json` (`workspace_fonts`) or else the rolled pairing from the font cache or network; `creation` reports the size, background and fonts chosen and why (see [Safe variety](safe-variety.md#new-documents)). `font_pairing` installs that pairing instead (same as `vixl_font_pair`); `workspace_fonts: false` embeds no fonts |
| `vixl_document_open(path, upgrade?)` / `vixl_document_close(document)` | Activate an existing document / drop one from the session; edits are already saved. A document saved before 0.21 lists the layers that render differently under `upgrade`; `upgrade="accept"` stops the notice and `"pin-fills"` also restores the white fill of open stroked shapes (CLI: `vixl upgrade`) |
| `vixl_document_inspect(target?, detail)` | `compact` (default): canvas plus one line per layer with resolved `[x, y, w, h]` bounds; `full`: every stored field |
| `vixl_import_image(path? \| data_base64? \| url?, name, credit?, license?)` | Embed a workspace file, base64/data-URL bytes or a public `https://` image as a layer; returns id, size, bounds and `source` (final `url`, `bytes`, `sha256`, `fetched_at`). `credit`/`license` are kept in the layer's provenance and shown by inspect |
| `vixl_operations_apply(operations or operations_path, dry_run, detail, check?, suites?, preview?, request_id?, as_job?)` | Atomic edits; `operations_path` is a workspace-relative `.json` array or `.jsonl` file (one operation per line, errors cite the line) used instead of inline `operations`; schemas are included directly in tools/list (or on demand in slim mode). `detail` is `brief` (default), `compact` or `full`; results carry `warnings`. `check` (true or check names) adds a `check` block shaped like `vixl_check`'s, listing every `fix` finding and the findings on the layers the batch touched (at most 20; `omitted` counts the rest); `suites` (true or suite names) runs the document's check suites and lists the rules that did not pass; `preview` (true or `{page, region, max_width, max_height, time, isolate}`, 512 px by default) adds a PNG after the JSON. All three also work with `dry_run`, and are skipped with a `review_skipped` note when the edit itself took more than half of `VIXL_MCP_INLINE_SECONDS`. A call that became a job keeps the JSON only. |
| `vixl_operation_schema(types)` | Exact JSON Schema for named operation types |
| `vixl_check(checks, targets, safe_area, avoid, thumbnail_width, ..., ink_limit, min_ppi, style, connect_tolerance)` | Design problems: bounds, text overlap, WCAG contrast, safe area/reserved zones, thumbnail legibility, `diagram` (overlapping nodes, edges through nodes or on top of each other, unreadable labels) and `flow` (text-flow overflow); `codes` (QR/barcode module size, contrast and quiet zone); opt-in `print`, `color_vision`, `style` and `connected` (parts of a group that float free of its main body, gaps above `connect_tolerance` px, default 2). Every issue has a `severity` (error, warning, info) and an `action` (fix, review, informational); `by_action` lists the issue indexes under each. A layer marked `allow_crop` (`layer-intent`) reports its edge crop as informational; `thumbnail_width: null` turns the thumbnail test off, the canvas safe area is checked by default, and the summary reports `layers_checked` and `layers_total` |
| `vixl_guide(brief?)` | What to make: the start-here recipe and every kind of work, or the approach, operations, layouts, looks, styles and a working example for a kind or free-text brief; `brief=operations` and `brief=looks` list those catalogs |
| `vixl_styles(action, name?, query?, palette?)` | 28 design styles: list/search, get (principles, palettes, type, layout, imagery, do/don't, checks), apply (tag the document, store the brief, optionally the palette), check (same as `vixl_check` `style`) |
| `vixl_render_preview(variables, max_width, max_height, max_bytes, region, time, proof, simulate, isolate)` | Fast preview-resolution PNG; `region` zooms in (up to 8×); `time` shows a timeline frame; `proof` soft-proofs CMYK; `simulate` shows color-vision deficiency; `isolate` (layer IDs or names, a group with all its parts) shows only that object on the canvas background, zoomed to its ink with a small margin unless `region` is given |
| `vixl_render_compare(before, after, mode, isolate)` | Side-by-side or red-highlight diff of two revisions (`previous`, `head~N`, branch, checkpoint, ID) plus the changed region; `isolate` compares one object alone, both sides cropped to its ink (`region` in the summary) |
| `vixl_export_file(path, quality, title, max_bytes, scale, profile, variables, background, overwrite, color_space, icc_profile, intent, black_generation, ink_limit, proof, simulate, dpi, icon_sizes, time)` | Save full-resolution PNG/JPEG/WEBP/TIFF/AVIF/SVG/PDF/ICO, CMYK for print; return only file metadata |
| `vixl_export_batch(targets, defaults?, overwrite, stop_on_error)` | Several files in one call: sizes, formats or artboards of a document, or several documents |
| `vixl_compose(path, size? \| width/height \| purpose?, background?, seed?, variety?, font_pairing?, layout?, style?, look?, operations? \| operations_path?, check, strict, preview?, exports?, overwrite, dry_run)` | A new piece in one atomic call: create → fonts → layout → style → look → operations → check → preview → save → exports; see [below](#build-a-piece-in-one-call) |
| `vixl_adapt_layout(sizes, directory?, name?, options?, formats?, overwrite?, report?)` | Adapt one document to several sizes in one call: each size is a saved (optionally exported) copy re-laid out by the `adapt-layout` operation (proportional by default; `options: {"recompose": true}` rebuilds a stored generated layout for each size, replacing edits to its layers), with per-size canvas, scale, moved layers and warnings ([operations](operations.md#bulk-edits-and-resizing-a-whole-layout-unreleased)) |
| `vixl_job(action, id?, wait?)` | Follow a long call: `status` (optionally waiting), `result`, `cancel`, `list`; see [long calls](#long-calls-retries-and-progress). The `--tools compact` set has no `vixl_job`; it polls through `vixl_workflow` (`action: "status"`, `request: {id}`) |
| `vixl_sizes_list`, `vixl_layouts_list`, `vixl_brushes_list` | Named sizes, principled layouts, brushes (no document needed) |
| `vixl_color(action, colors, …)` | Color info, conversion, harmonies, scales, mixing, contrast and name search |
| `vixl_timeline_inspect`, `vixl_timeline_preview(time \| count)`, `vixl_export_timeline(path, format, fps, scale, …)` | Keyframe timelines: inspect, preview a frame or contact sheet, export GIF/APNG/WebP/sheet/PNG ZIP/MP4/WebM |
| `vixl_export_icons(directory, icon_set)` | Standard icon sets (web favicons and manifest, Apple, Android, Windows) |
| `vixl_measure`, `vixl_measure_spacing`, `vixl_validate` | Samples, channel statistics, contrast; spacing intent; assertions and profiles |
| `vixl_spatial(target?, targets?, mode, …)` | Canvas-space relationships, gaps, alignment, margins, guide offsets, hit tests, empty regions and snap operations; box or ink bounds |
| `vixl_capabilities(topic, fields?)` | Field-level reference for a topic (text, drawing, animation, film, layout, color, export or free words): matching operations (`fields=true` adds their fields), workflows, gotchas, limits and guidance names |
| `vixl_workflow(action, request, document?)`, `vixl_workflow_schema()` | Production actions (proof, logo-package, merge-impose, emoji-*, app-animation-package, screen-capture …) and their request fields; see [production](production.md) |
| `vixl_pixels_inspect`, `vixl_animation_inspect`, `vixl_animation_preview`, `vixl_export_animation` | Frame-by-frame animation (saved frames, sprites, pixel art): pixel rows and palette, frames and named animations, one frame, GIF/APNG/WebP/MP4/WebM/sprite sheet |
| `vixl_export_audio(path, sample_rate?)`, `vixl_export_character(target, output)` | Mix the audio tracks to a new WAV; save one character and its assets to a `.vixl` library |
| `vixl_history(action, ref, count, offset, limit, dry_run, fonts)` | Undo/redo/transactions/branches/checkpoints; newest-first summaries; `compact` discards undo history and drops embedded files the design does not use (`dry_run` reports first; see [commands](commands.md#scripts-presets-history)) |

The server instructions carry the start-here recipe: `vixl_guide` for the kind of work, then `vixl_sizes_list` → `vixl_document_create(size=…)`,
`vixl_layouts_list` → `layout-apply` (all slots filled; art with no text frame is built from `shape`/`organic`/`pathfinder`/`radial-repeat`),
`vixl_fonts` → `vixl_font_pair`, a `look` or `vixl_styles` to finish, then `vixl_check` (fix the `fix` findings) → `vixl_render_preview` → `vixl_export_file`.
Open-ended briefs default to that path instead of freehand shapes.

`vixl_operation_schema(types=[…])` returns each operation's one-line `description`, every field with a JSON type and a description,
and `examples` for the common ones (gradients, glows, shadows, radial repeats, layouts, palettes …). `tools/list` stays lean: it carries
types and constraints only.

Every document tool accepts an optional `document` path. Up to 8 documents stay open per server; addressing one with `document` does not change the active document. Every result names the document it acted on (`"document": "poster.vixl"`; previews add a text line after the image), so a call that landed on the wrong document is visible.

For example, create `poster.vixl` at 4000×3000, import `photo.jpg` as `photo`, apply `[{"type":"move","target":"photo","x":20}]`, run `vixl_check`, request a preview, then export `poster.png`. File paths refer to the machine running Vixl; a client without access to that file system can send image bytes with `data_base64` instead.

Relative and absolute paths are accepted within the workspace. Paths escaping it, including symlinks to outside directories, are rejected. Export refuses existing files unless `overwrite: true` is supplied, and cannot overwrite `.vixl` documents. `vixl_document_create`, `vixl_template_create` and the export tools create missing directories inside the workspace (nothing outside it is ever created). Operation `path` and `linked` fields remain unavailable (checked after alias normalization); use the import tool. `font` (and `display_font`, rich-text span fonts and `font=` in rich-text Markdown) is accepted in `vixl_operations_apply` batches: a font registered in the document (`vixl_font_pair`, `vixl_font_install`, `vixl_import_font`, or a `font-register` earlier in the same batch) or a role. A file path or an unregistered name is refused with `forbidden`/`missing_font`, listing the registered names and the install tools. Services do not enable third-party plugins or linked-file reads.

### Build a piece in one call

When the agent already knows the size, the layout and its copy, the look and the operations, `vixl_compose` replaces
the create → apply → check → preview → export round trips:

```json
{"path": "launch/card.vixl", "size": "instagram-post", "font_pairing": "ibm-plex-serif-sans",
 "layout": {"name": "hero-statement", "title": "Ship it", "subtitle": "Release notes inside", "seed": 7},
 "look": {"look": "grain", "target": "background"}, "style": "swiss",
 "operations": [{"type": "shape", "shape": "ellipse", "name": "dot", "x": 900, "y": 80, "width": 60, "height": 60, "fill": "@accent"}],
 "check": true, "preview": true, "exports": ["launch/card.png", {"path": "launch/card.pdf", "color_space": "cmyk"}]}
```

The `layout`'s `image` and `images` slots take a workspace path or an `https://` URL as well as an asset id, so a
meme or photo card is one call (`{"name": "meme-top-bottom", "image": "memes/cat.jpg", "title": "…"}`). Paths stay
inside the workspace and URLs go through the same fetch policy and byte and pixel limits as `vixl_import_image`; the
layout step lists what it embedded under `imported` (path or url, sha256). A `background` is kept when a layout runs:
it becomes the layout's background role, with the text and accents chosen to read on it (`transparent` keeps the
layout from painting one); a layout's own `colors.background` or `transparent` wins. A `style` shapes what the call
leaves open: the alignment its text-align rule asks for, its first palette (unless the workspace brand sets one), a
dark mode when it asks for a dark background, and, without `font_pairing`, workspace fonts or a layout `font`, its
first font pairing (a pairing that cannot be downloaded is noted under `fonts` and the call goes on). The layout step
reports these under `from_style`, so `check` with the style's rules passes on the result.

The steps run in that order on an unsaved document. The `.vixl` is written only when every step succeeded and the
exports only after it; a failed export removes the document and the files the call wrote. Export targets (the
`vixl_export_batch` options) are validated before anything is built, so an existing file fails at once. An error keeps
the normal schema (`error`, `message`, `field`, `operation_index` …) and adds `step`: `request`, `create`, `fonts`,
`layout`, `style`, `look`, `operations`, `check`, `preview`, `save` or `export`. `strict: true` turns `fix` findings into
a `check` failure (nothing saved); `dry_run: true` builds, checks and previews without writing (`path` optional). The
result lists `steps`, the layout's seed, blanks and notes, the check findings, the saved `document` and the `exports`,
followed by the preview image. Like `vixl_document_create`, a saved compose makes the new document the active one
(`active_document: true`); when another document was active, a warning names it, since later calls without
`document=` now edit and export the composed piece. Like other heavy tools it becomes a job after ~40 s (or at once with `as_job`) and takes
`request_id`. It is in the core and compact toolsets.

The same request works as `vixl compose --request req.json [--preview p.png]`, as `vixl.compose.run(workspace, **request)`
in Python, and as `POST /compose` on REST, where it is a dry run (no `path`, `exports` or `operations_path`: that server
serves one fixed document) returning the findings and `preview_base64`.

### Forgiving input and actionable errors

Model-written operations are normalized before validation, the same way in every interface, and each rewrite is reported under `normalized` in the result so the agent learns the canonical form:

- type and key spellings: `rect`/`circle`/`triangle` (→ `shape`), `add-text`, `drop_shadow`, camelCase and kebab-case keys, `font_size`, `fill`/`color`, `layer`/`layer_id` → `target`;
- values: opacity is 0–1 everywhere and `"70%"` is read as 0.7 (a bare `70` is an error suggesting both spellings); CSS `rgb()`/`rgba()` with 0–1 alpha, and with channels outside 0–255 clamped as CSS does (`rgb(300, 0, 0)` → `#ff0000`); style setting aliases (`offsetX` → `dx`);
- geometry: `x`/`y` accept `"center"` and `"N%"`, `width`/`height` accept `"N%"` (of the canvas, or of the parent group);
- layers: `targets` with one entry on a single-layer operation → `target`; a lone `target` on `group`/`distribute`/`pathfinder` → `targets`.

Errors are JSON: `{"error", "message", "field", "operation_index", "operation_type", "allowed"?, "suggestions"?, "fields"?, "schema"?, "expected"?}`. Unknown layers suggest close (including case-insensitive) names and list available ones; unknown fields, enum values and operation types get did-you-mean suggestions; a failing batch names the operation that failed. The whole batch is validated before anything runs, and every invalid operation is reported in one error: the top-level fields describe the first, `errors` lists each (`operation_index`, `operation_type`, `field`, `message`, `suggestions`, at most 50), `error_count` counts them, and `message` lists them all (MCP, REST and the CLI's `ERROR:` line show the same list; `dry_run` too). Errors raised while the batch runs stop at the first. A schema error ends with `(see vixl_operation_schema(types=['shape']))`, the same hint is in `schema`, `fields` lists the accepted field names and, for a wrong type, `expected` holds the field's schema. Unknown fields are rejected, never silently accepted.

A call that succeeds can still carry `warnings` (a list of strings) about the layers it changed: text or artwork cut off by the canvas edge (a small bleed is ignored), text that does not fit its `text-layout` box or spills out of its group, and valid fields that change nothing for that operation (`radius` on a plain rectangle, `angle` on a non-angled gradient, `start`/`end` next to `stops`, `stroke_width` without `stroke`). Unknown fields and invalid values are errors, never warnings. Warnings only concern the layers of that call; `vixl_check` is the complete audit. A tool call that passes an argument the tool does not take (`detial="full"`) is not silently dropped: its result gets a warning naming the argument and the closest parameter (image tools add a text line after the picture).

### Small responses and previews

Tool results are minified JSON text with no duplicated structured copy. Advertised schemas omit pydantic titles and collapse optional fields. `vixl mcp --schema slim` advertises only the operation type names (about half the tool-list size) and the agent fetches fields with `vixl_operation_schema`. The provider-backed planner (`vixl_ai_plan`) is hidden unless `--planner` is passed, because the calling agent already plans its own edits.

The default `detail: "brief"` apply response over MCP returns, per stable layer ID, only what the caller cannot already know: new layers as `added`/`name`/`type`/`bounds` (plus a shape's `content_bounds`, and a text layer's metrics
(`ink_bounds`, `line_bounds`, `baseline`, `baselines`, `ascent`, `descent`, `cap_height`, `x_height`, `metrics_space`) so text can be aligned without another call), changed layers as the list of changed field names plus their resolved `bounds`, removals, `warnings` and `normalized`; state other than layers is listed by name under `also_changed`. `detail: "compact"` (the REST/CLI default) returns the **new** values of changed fields and the main content of new layers; `detail: "full"` returns before/after snapshots. Python's `Project.apply` accepts all three. `vixl_measure` summarizes channels as percentiles unless `histogram: "full"`.

Preview defaults: **1024×1024 maximum and 1 MiB of encoded PNG data**, preserving transparency and aspect ratio. Previews render a geometrically scaled copy of the document (JPEG sources decode at reduced scale), so a 24-megapixel document previews in a fraction of a second. Every layer edge (and every copy of a `repeat`) lands on a whole preview pixel, so layers or tiles that meet in the full render still meet in the preview and no seam appears between them; documents with canvas-sized effect selections fall back to a full render. `region: [x, y, w, h]` (pixels or percentages) zooms into part of the canvas. File export always uses full resolution unless a scale/profile is requested.

### Long calls, retries and progress

An MCP client typically gives up on a call after about 60 s, while the server still finishes the work and saves it. Vixl runs every tool call in a worker thread (a slow render no longer blocks other calls or the heartbeat) and turns a slow call into a job:

- **Automatic jobs.** A call that is still running after `VIXL_MCP_INLINE_SECONDS` (default 40, `0` disables) returns `{"status": "running", "job": "job_…", …}` while it carries on. Poll with `vixl_job`.
- **Under load.** Calls run on `VIXL_MCP_WORKERS` threads (default 32). When more calls are in flight than there are workers, a new call waits proportionally less (inline seconds × workers ÷ calls in flight, at least 2 s) before it becomes a job, so a call stuck behind others is not lost to a client timeout. Job pointers and `vixl_job` report `queued` (still waiting for a worker), `wait_ms` (time spent waiting for a worker) and, in pointers, `queue_depth` (calls waiting).
- **`as_job: true`** on the heavy tools (`vixl_operations_apply`, `vixl_import_image`, `vixl_import_document`, the export tools, `vixl_compose`, `vixl_adapt_layout`, `vixl_font_pair`, `vixl_font_install`, `vixl_workflow`, `vixl_roll`, `vixl_check`, the `vixl_ai_*` tools) starts the call as a job and returns its id at once.
- **`vixl_job(action, id, wait)`:** `status` reports `queued`/`running`/`completed`/`failed`/`cancelled` with `progress` (`wait=20` blocks up to that many seconds, at most 50, so one call replaces a polling loop); `result` returns the call's normal result under `result` (or `error`); `cancel` stops a queued job, or a running one at its next checkpoint (a batch of operations is atomic, so a cancelled batch changes nothing; timeline exports stop between frames); `list` shows recent jobs, including calls that timed out on your side. The server remembers the last 100 jobs in memory; durable workspace jobs from `vixl_workflow submit` use the same tool with their 32-character ids.
- **Retries: `request_id`.** The mutating tools (`vixl_operations_apply`, imports, exports, `vixl_compose`, `vixl_adapt_layout`, `vixl_document_create`/`close`, `vixl_template_create`, fonts, `vixl_history`, `vixl_workflow`, `vixl_roll`, the AI tools) accept an optional `request_id` (1–64 characters). Repeating a call with the same id returns the first call's recorded result with `"replayed": true` instead of applying twice; if the first call is still running, the repeat waits briefly and then points at its job. An id reused with different arguments is an error (`request_id_conflict`), and a call that failed is not remembered, so its retry runs. The store keeps the last 64 ids per document (512 overall), in memory.
- **Progress.** A client that sends a progress token receives `notifications/progress` while operation batches (one tick per operation), timeline exports (one per frame) and batch exports (one per file) run. Once a call has become a job, read its `progress` with `vixl_job`.

Recommended pattern for agents: send heavy calls with a fresh `request_id`; if one times out or returns a job, call `vixl_job(action="result", id, wait=30)` (or `list` when you never saw the id) instead of resending, and resend with the same `request_id` only if the result says it failed.

### Several agents on one server

The server keeps documents loaded in one shared cache, but the **active document is per MCP client session**: with Streamable HTTP each connected client opens, creates and closes documents without moving anyone else's active document, and a client that has opened nothing gets the document the server was started with (or none). A stdio server has exactly one client connection, so subagents of one parent agent still share one active document there. Three safeguards help in that case:

- `vixl mcp --require-document` (or `VIXL_REQUIRE_DOCUMENT=1`) makes `document=` mandatory on every document tool: there is no active document to fall back to, and a call without it fails with `document_required`. `vixl_document_create`/`open` still work and name the document in their result.
- Every result names the document it acted on (`document`), so a mistake shows up in the first response.
- Pass `document=` on every call, with `request_id` on mutating ones.

For many agents at once, run one `vixl mcp --http` server they all connect to (each gets its own active document and the calls share one worker pool and job store) rather than one stdio server per agent; raise `VIXL_MCP_WORKERS` when results come back as `queued` jobs.

### Typed AI tools

These call your [configured providers](providers.md) with named fields, without CLI flags:

- `vixl_ai_generate(prompt, mode, width, height, seed, name, provider, model, negative_prompt, strength)`; mode is `generate`, `inpaint`, or `img2img`. Supply both dimensions or neither. Inpainting needs a selection.
- `vixl_ai_remove`, `vixl_ai_content_aware_fill`, `vixl_ai_select_subject`, `vixl_ai_remove_background(layer)` and `vixl_ai_select_object(label)`.
- `vixl_ai_analyze(capability, query, provider)`; capability is `describe`, `detect`, or `ocr`. Detections return `objects[].box` as `[x, y, w, h]` document pixels for every provider.
- `vixl_ai_upscale(layer, scale)`, `vixl_ai_regenerate(layer, prompt, seed)`, `vixl_ai_extend(prompt, left, right, top, bottom, seed, name)`.
- `vixl_ai_plan(prompt, apply)` only with `vixl mcp --planner`.

Provider capability limits still apply. Local provider settings and credentials remain on the server. Layer provenance is available through inspection.

### Session performance and consistency

REST and MCP retain loaded projects between calls. A file fingerprint (identity, size and high-resolution modification/change times) triggers a fresh load when an external edit is detected. Edit candidates share immutable history and the content-addressed render and decoded-image caches, so an edit costs roughly the same at revision 10 or 2,000. Thread and interprocess locks serialize edits; saves retain optimistic revision checks and atomic replacement, and store image assets without recompressing them. Failed edits, provider calls or saves discard the cached instance before the next access.

### REST additions

`POST /check` (same options as `vixl_check`), `POST /preview` (`max_width`, `max_height`, `max_bytes`, `region`, `isolate`, …; returns PNG) and `POST /compare` (`before`, `after`, `mode`, `isolate`; returns the summary plus `image_base64`). The CLI takes `--isolate LAYER…` on `compare` and on `apply --preview`. The REST service is bound to its one document and rejects a `document` field.

## Trusted extensions

Installed Python packages can register entry points:

```toml
[project.entry-points."vixl.filters"]
my_filter = "my_package:filter_image"
[project.entry-points."vixl.providers"]
my_provider = "my_package:Provider"
```

A filter receives `(rgba_image_copy, effect_dict)` and returns a same-size Pillow RGBA image. Provider classes accept `(provider_name, configuration)` and expose `invoke(capability, request) -> dict`; see the HTTP gateway contract for request/result shapes. The provider instance exposes `.name`.

Enable plugins explicitly with `vixl --plugins ...` or `vixl.plugins.enable_plugins()` in Python. Plugins are trusted Python code with the user's process privileges; they are **not sandboxed**. No plugin is imported from a project archive. Trusted operation producers and declarative resource packs are described in [studio.md](studio.md). Codec, layout, validator, and asset-source entry-point categories remain future work; built-in Pillow codecs and the current validator/layout engine cover those functions today.

## New agent resources (0.11)

MCP adds `vixl_resources_list`, `vixl_resource_get`, `vixl_resource_add`, `vixl_template_create`, `vixl_import_font` (a workspace `path` or an `https://` `url`), and `vixl_models_list` (in `--tools ai` and `all`). Resource discovery needs no open document. Font paths and document destinations remain workspace scoped. `vixl_export_file` accepts `.svg`; operations accept registered font names while service operations continue to reject filesystem font paths.

REST adds GET `/resources/{kind}`, GET/POST `/resources/{kind}/{name}` (POST body `{"value":...}`), POST `/fonts?name=brand` with raw TTF/OTF bytes (16 MiB maximum), and POST `/export` with options such as `{"format":"SVG"}`. Export returns bytes and accepts no destination path. Python exposes the matching `vixl.resources` and `vixl.fonts` helpers. [Detailed examples and boundaries](agent-resources.md).

## Sizes, layouts, color, brushes and timelines (0.13)

All new editing features are ordinary operations, so `vixl_operations_apply`, `POST /operations`, `Project.apply` and scripts use them directly. MCP adds the discovery, timeline and icon tools listed above; `vixl_render_preview` and `vixl_export_file` gain `time`, `proof`, `simulate` and print options. `icc_profile` is a workspace path in MCP.

REST adds `GET /sizes?category=`, `GET /layouts`, `GET /brushes`, `GET /guide?brief=`, `GET /styles?query=|name=`, `GET /looks`, `POST /color` (`{"action", "colors", "to"?, "scheme"?, "count"?, "amount"?, "space"?}`), `GET /timeline`, `GET /timeline/frame?time=1.5s` (PNG), and `POST /timeline/export` (`{"format", "fps", "scale", "start", "end", "background", "columns", "quality"}`; returns bytes). `POST /export` accepts `color_space`, `icc_profile_base64`, `intent`, `black_generation`, `ink_limit`, `proof`, `simulate`, `dpi`, `icon_sizes` and `time`, and formats `PDF` and `ICO`. `POST /preview` accepts `time`, `proof` and `simulate`.

Python: `Project.sized("letter", bleed=True)`, `project.export("flyer.pdf", color_space="cmyk", icc_profile=bytes)`, `vixl.colors` (parse, describe, harmony, scale, mix, contrast_ratio, simulate_vision, cmyk_image), `vixl.sizes` (resolve, catalog), `vixl.layouts.catalog()`, `vixl.brushes.catalog()`, `vixl.timeline` (project_at, render_at, contact_sheet, export_timeline) and `vixl.exports.export_icons`.

<a id="pages-forms-drawings-and-lyric-videos-unreleased"></a>

## Pages, forms, drawings and lyric videos (0.19)

All editing is ordinary operations. MCP: `vixl_render_preview` gains `page` (`"all"` for a contact
sheet), `values` and `show_fields`; `vixl_export_file` gains `page`, `pages`, `pdf_content`,
`fillable`, `values`, `fill_mode` and `presenter` and writes `.pptx` and `.html` presentations
(see [presenter](presenter.md)); `vixl_check` gains `page`, `deck`
settings, `sample`, and the `deck`, `form` and `drawing` families; `vixl_document_inspect` lists
pages and fields. `vixl_workflow` adds `lyric-video-plan/build/export`, `organic-catalog`,
`form-fill`, `drawing-report` and `drawing-compare`; jobs add the `lyric-video` and `form-fill`
kinds.

PDF export is vector by default (also with `color_space="cmyk"`); the export result reports `content`, `content_reason`,
`color_space` and `page_size`, and `dpi` sizes PDF pages and PowerPoint slides alike. A PPTX result's `warnings`
name the fonts that are not embedded and must be installed where the deck is opened (`fonts_not_embedded`, with each one's fsType permission and license under `font_embedding`).

REST: `POST /export` accepts `page`, `pages`, `pdf_content`, `fillable`, `values`, `fill_mode` and
`presenter` (HTML slide presentation options) and formats `PPTX` and `PSD` (layered, see [exporting](exporting.md#layered-psd-for-designer-handoff)); `POST /preview` accepts `guides`, `page`, `values` and `show_fields`; the fixed
project's workflow routes include `lyric-video-plan`, `organic-catalog`, `form-fill` and
`drawing-report`.

Python: `project.export("deck.pptx")`, `project.export("form.pdf", fillable=True)`,
`project.render(page=2)`, `vixl.forms.fill` / `fill_data`, `vixl.deck.check_deck` /
`contact_sheet`, `vixl.drawing` (`clean`, `report`, `compare`, `ai_color`), `vixl.lyrics`
(`parse_lrc`, `plan`, `build`, `export`).

Linked documents and print merge are ordinary operations and one workflow action each: `link` (create, or change with a `target`),
`link-refresh` and `link-embed` go through `vixl_operations_apply` / `POST /operations`; `vixl_workflow("links", {})` (also `POST /workflow/links`) lists
each link's state; `vixl_workflow("merge-impose", request, document=template)` merges a CSV into print sheets (MCP and CLI only:
it writes files). Link sources and merge paths stay inside the workspace. See [linked documents](linked-documents.md) and
[imposition](imposition.md).

### Streamable HTTP and live review

```bash
# MCP over HTTP, for clients supporting a static Authorization header:
vixl mcp --workspace . --http --port 8766 --tools core --schema slim
# For a remote bind, set VIXL_API_TOKEN, then add --host 0.0.0.0.
# Connect to https://YOUR-HOST/mcp through your TLS reverse proxy.

# Serve a fixed document and open its live viewer:
vixl -p poster.vixl view
# Or run `serve` and open http://127.0.0.1:8765/view yourself.
vixl -p poster.vixl notes list
vixl -p poster.vixl notes resolve NOTE_ID
```

HTTP MCP uses the official SDK's Streamable HTTP transport. Stdio remains the default.
HTTP and REST use `Authorization: Bearer TOKEN`, with `VIXL_API_TOKEN` (or `--token-env`)
and reject remote binds without it. Use a TLS reverse proxy for remote access. OAuth discovery
is not implemented: clients that require OAuth, including some hosted connector setups, need
an OAuth-capable gateway. Each connected client has its own active document (see
[several agents on one server](#several-agents-on-one-server)); agents that share one stdio connection should
still pass `document` explicitly on every document tool. Access covers the entire
configured workspace and any locally configured provider accounts.

The viewer polls once per second, showing the current PNG, layers, history, and review notes.
Only its empty HTML shell is public; document APIs require the token when configured. Enter
that token in the viewer; it is kept in memory, never placed in a URL or browser storage.
Notes persist in `DOCUMENT.vixl.notes.json`, separately from undo history. Agents read/add/resolve
them with `vixl_review_notes`; CLI users use `notes list|add|resolve`. REST provides `GET /review`,
`GET /notes`, `POST /notes` (`{"text":"..."}`), and `POST /notes/{id}/resolve`.

### Import existing artwork

```bash
vixl -p poster.vixl import logo.svg
# Optional PDF dependency: pip install 'vixl-engine[pdf]'
vixl -p poster.vixl import flyer.pdf --page 1 --dpi 144 --name reference
vixl -p poster.vixl import photo.jpg --name hero --credit "Photo: Ana Ruiz" --license "CC0"
vixl -p poster.vixl import https://images.example.com/cat.jpg --name cat --credit "Photo: Ana Ruiz / Unsplash" --license "Unsplash License"
```

MCP: `vixl_import_document(format="svg", path="logo.svg")`, or `data_base64` instead of `path`.
REST: `POST /import?format=svg` with raw bytes. PDF additionally accepts a one-based `page` and
`dpi` (36–600); it imports a raster reference layer, not editable PDF text or paths.

Any other file, or an `https://` URL, is imported as an image layer, the same as
`vixl_import_image(url=…)`, `POST /assets?url=…` and `Project.import_image(url=…)` in Python. A URL
download is HTTPS only, follows at most 5 redirects, refuses private, loopback and link-local hosts
and is size-capped; the bytes must decode as an image whatever the server's `Content-Type` says (see
[architecture](architecture.md#trust-and-security)). The layer's `provenance` records
`source: {url, fetched_at, sha256, bytes}`, plus `credit` and `license` when you pass them (also for
file and base64 imports, and the `add` operation's `credit`/`license` fields). Compact inspect shows
`source_url`, `credit` and `license`; `vixl dependencies` lists them under `attributions`. Use web
images only with the rights to do so (guidance `image-rights`).

SVG imports create editable path layers with solid fills, strokes, translations, scales,
rotations, matrix transforms, and compound nonzero-winding paths (including holes). Arc and
shorthand path commands are converted to editable Bézier geometry. UTF-8 SVG files are limited
to 4 MiB and existing document resource limits. Unsupported features fail before changing the
document: text, images, gradients, CSS classes, clipping, filters, evenodd fills, rounded rectangles,
group opacity and nonuniformly transformed strokes. This is the default `svg_mode="editable"`. Use `svg_mode="appearance"` to render supported self-contained static SVG while retaining the source, or `"auto"` to try editable then appearance. See [studio.md](studio.md) for support and input restrictions.
Imports never fetch external resources. The original SVG element IDs become layer names.

### Source folders, emoji, app packages and capture (0.24)

`vixl pack` / `vixl unpack` convert between a `.vixl` and a readable source folder; Python has the same `pack` and
`unpack` in `vixl.project_folder` ([commands](commands.md#reviewing-editable-projects-in-git)). The workflow actions
`emoji-list`, `emoji-get`, `emoji-template`, `emoji-settings`, `emoji-replace`, `emoji-pack-install`, `emoji-reset`,
`emoji-destinations`, `emoji-requirements` and `emoji-export` back the `vixl emoji` command ([emojis](emojis.md));
`app-animation-package` writes an app animation package ([animation authoring](animation-authoring.md)), and
`screen-capture` captures the local desktop to PNG. They run through `vixl_workflow` and `vixl workflow ACTION`; the
REST workflow route, scoped to its one document, does not serve them.

### Consolidated studio workflows

`vixl mcp --tools compact --schema slim` exposes 13 document/operation/workflow/compose/preview/import/export tools. Workflow actions include resource-list/get/save, shape-save, suite-use, palette-check, effect-run, group-list/define/show/apply/recover, branch-list/fork/status/merge and plugin-list/install/remove. REST allows the resource/test/effect actions while retaining fixed-project scope. `vixl_export_file` and REST export support HTML. Full contracts and examples: [studio.md](studio.md).
