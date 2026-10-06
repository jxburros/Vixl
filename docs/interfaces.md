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

`Project.render()` returns a Pillow RGBA image. In a notebook a `Project` displays as its rendered PNG, and `Project.show(page=None, region=None)` returns the image (optionally one page, cropped to `[x, y, width, height]`). `Project.export()` returns encoded bytes, optionally writing to a path. `Project.inspect()` returns an independent JSON-serializable state description. History methods: `undo`, `redo`, `branch`, `checkpoint`, `checkout`, `begin`, `commit`, `rollback`.

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
| `POST /operations` | `{operations: [...] or operations_path: "ops.jsonl", dry_run: false, detail: "compact", check?, preview?}` → change summary (use `full` for snapshots); `check`/`preview` as for `vixl_operations_apply`, the preview as `preview_base64` |
| `GET /render` | PNG bytes |
| `POST /render` | `{variables: {title: "Hello"}}` → PNG bytes |
| `POST /validate` | `{profile: "instagram-post", rules: [...]}` → checks |
| `GET /history` | History graph and named references |
| `POST /history/{action}` | `{ref: "name", count: 1}`; undo/redo/branch/checkpoint/checkout/begin/commit/rollback |
| `POST /assets?name=photo` | Raw image bytes → imported layer |
| `POST /ai/{command}` | `{args: ["--prompt", "forest", "--provider", "local"]}`; uses locally configured providers |

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

Start with `--tools core --schema slim`. The offline suite passes all 16 tasks with these flags.
The schema costs approximately 6,898 tokens (JSON characters ÷ 4), versus 12,789 for full/all,
a 46% reduction. This measures tool context, not model performance; defaults remain full/all
until the scheduled live-agent comparison provides evidence to change them. With slim schemas,
call `vixl_operation_schema` for the fields of unfamiliar operations.

### Two servers: core and AI

`vixl mcp` can serve its tools as two servers, so an agent loads only the tools it uses:

- `--tools core`: documents, operations, rendering, checks, export, sizes, layouts, fonts, color, brushes, animation, workflows, batch export, layout adaptation, jobs, and the guidance tools `vixl_guide` and `vixl_styles` (47 tools).
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

Give both the same workspace. Every edit is saved immediately and each server reloads a document that changed on disk (writes are serialized with file locks), so an image generated through `vixl-ai` appears in `vixl` on its next call. AI tools take `document=` or use the document opened with `vixl_document_open`. Leave out `vixl-ai` when no AI provider is configured. The default, `--tools all` (or `VIXL_MCP_TOOLS`), keeps serving every tool from one server, so existing configurations are unchanged.

Existing `vixl --project /absolute/path/poster.vixl mcp` configurations still work: they open that document and use its parent directory as the workspace. You can also pass `--workspace` explicitly; the starting project must be within it.

### Tools and workflow

Vixl is designed to be driven mainly by agents. The intended loop is: create or open a document → `vixl_operations_apply` in atomic batches (use `dry_run` to test) → `vixl_check` to find problems without looking → `vixl_render_preview` (with `region` to zoom) → fix → `vixl_export_file`.

| Tool | Purpose |
| --- | --- |
| `vixl_workspace_list(directory, offset, limit)` | Discover workspace paths and the open documents |
| `vixl_document_create(path, width?, height?, background, size?, dpi?, orientation?, bleed?, font_pairing?)` | Create and activate a new `.vixl` from pixels or a named size; creates missing directories; refuses overwrites; `font_pairing` also installs a pairing as the document typography (same as `vixl_font_pair`) |
| `vixl_document_open(path)` / `vixl_document_close(document)` | Activate an existing document / drop one from the session; edits are already saved |
| `vixl_document_inspect(target?, detail)` | `compact` (default): canvas plus one line per layer with resolved `[x, y, w, h]` bounds; `full`: every stored field |
| `vixl_import_image(path? \| data_base64?, name)` | Embed a workspace file or base64/data-URL bytes as a layer; returns id, size, bounds |
| `vixl_operations_apply(operations or operations_path, dry_run, detail, check?, preview?, request_id?, as_job?)` | Atomic edits; `operations_path` is a workspace-relative `.json` array or `.jsonl` file (one operation per line, errors cite the line) used instead of inline `operations`; schemas are included directly in tools/list (or on demand in slim mode). `detail` is `brief` (default), `compact` or `full`; results carry `warnings`. `check` (true or check names) adds a `check` block shaped like `vixl_check`'s, listing every `fix` finding and the findings on the layers the batch touched (at most 20; `omitted` counts the rest); `preview` (true or `{page, region, max_width, max_height, time}`, 512 px by default) adds a PNG after the JSON. Both also work with `dry_run`, and are skipped with a `review_skipped` note when the edit itself took more than half of `VIXL_MCP_INLINE_SECONDS`. A call that became a job keeps the JSON only. |
| `vixl_operation_schema(types)` | Exact JSON Schema for named operation types |
| `vixl_check(checks, targets, safe_area, avoid, thumbnail_width, ..., ink_limit, min_ppi, style)` | Design problems: bounds, text overlap, WCAG contrast, safe area/reserved zones, thumbnail legibility, `diagram` (overlapping nodes, edges through nodes, unreadable labels) and `flow` (text-flow overflow); opt-in `print`, `color_vision` and `style`. Every issue has a `severity` (error, warning, info) and an `action` (fix, review, informational); `by_action` lists the issue indexes under each. A layer marked `allow_crop` (`layer-intent`) reports its edge crop as informational |
| `vixl_guide(brief?)` | What to make: the start-here recipe and every kind of work, or the approach, operations, layouts, looks, styles and a working example for a kind or free-text brief; `brief=operations` and `brief=looks` list those catalogs |
| `vixl_styles(action, name?, query?, palette?)` | 28 design styles: list/search, get (principles, palettes, type, layout, imagery, do/don't, checks), apply (tag the document, store the brief, optionally the palette), check (same as `vixl_check` `style`) |
| `vixl_render_preview(variables, max_width, max_height, max_bytes, region, time, proof, simulate)` | Fast preview-resolution PNG; `region` zooms in (up to 8×); `time` shows a timeline frame; `proof` soft-proofs CMYK; `simulate` shows color-vision deficiency |
| `vixl_render_compare(before, after, mode)` | Side-by-side or red-highlight diff of two revisions (`previous`, `head~N`, branch, checkpoint, ID) plus the changed region |
| `vixl_export_file(path, quality, title, max_bytes, scale, profile, variables, background, overwrite, color_space, icc_profile, intent, black_generation, ink_limit, proof, simulate, dpi, icon_sizes, time)` | Save full-resolution PNG/JPEG/WEBP/TIFF/AVIF/SVG/PDF/ICO, CMYK for print; return only file metadata |
| `vixl_export_batch(targets, defaults?, overwrite, stop_on_error)` | Several files in one call: sizes, formats or artboards of a document, or several documents |
| `vixl_adapt_layout(sizes, directory?, name?, options?, formats?, overwrite?, report?)` | Adapt one document to several sizes in one call: each size is a saved (optionally exported) copy re-laid out by the proportional `adapt-layout` operation, with per-size canvas, scale, moved layers and warnings ([operations](operations.md#bulk-edits-and-resizing-a-whole-layout-unreleased)) |
| `vixl_job(action, id?, wait?)` | Follow a long call: `status` (optionally waiting), `result`, `cancel`, `list`; see [long calls](#long-calls-retries-and-progress). The `--tools compact` set has no `vixl_job`; it polls through `vixl_workflow` (`action: "status"`, `request: {id}`) |
| `vixl_sizes_list`, `vixl_layouts_list`, `vixl_brushes_list` | Named sizes, principled layouts, brushes (no document needed) |
| `vixl_color(action, colors, …)` | Color info, conversion, harmonies, scales, mixing, contrast and name search |
| `vixl_timeline_inspect`, `vixl_timeline_preview(time \| count)`, `vixl_export_timeline(path, format, fps, scale, …)` | Keyframe timelines: inspect, preview a frame or contact sheet, export GIF/APNG/WebP/sheet/PNG ZIP/MP4/WebM |
| `vixl_export_icons(directory, icon_set)` | Standard icon sets (web favicons and manifest, Apple, Android, Windows) |
| `vixl_measure`, `vixl_measure_spacing`, `vixl_validate` | Samples, channel statistics, contrast; spacing intent; assertions and profiles |
| `vixl_history(action, ref, count, offset, limit)` | Undo/redo/transactions/branches/checkpoints; newest-first summaries |

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

### Forgiving input and actionable errors

Model-written operations are normalized before validation, the same way in every interface, and each rewrite is reported under `normalized` in the result so the agent learns the canonical form:

- type and key spellings: `rect`/`circle`/`triangle` (→ `shape`), `add-text`, `drop_shadow`, camelCase and kebab-case keys, `font_size`, `fill`/`color`, `layer`/`layer_id` → `target`;
- values: `opacity` 1–100 is a percentage; CSS `rgb()`/`rgba()` with 0–1 alpha; style setting aliases (`offsetX` → `dx`);
- geometry: `x`/`y` accept `"center"` and `"N%"`, `width`/`height` accept `"N%"` (of the canvas, or of the parent group).

Errors are JSON: `{"error", "message", "field", "operation_index", "operation_type", "allowed"?, "suggestions"?, "fields"?, "schema"?, "expected"?}`. Unknown layers suggest close (including case-insensitive) names and list available ones; unknown fields, enum values and operation types get did-you-mean suggestions; a failing batch names the operation that failed. A schema error ends with `(see vixl_operation_schema(types=['shape']))`, the same hint is in `schema`, `fields` lists the accepted field names and, for a wrong type, `expected` holds the field's schema. Unknown fields are rejected, never silently accepted.

A call that succeeds can still carry `warnings` (a list of strings) about the layers it changed: text or artwork cut off by the canvas edge (a small bleed is ignored), text that does not fit its `text-layout` box or spills out of its group, and fields the engine accepted but that change nothing for that operation (`radius` on a plain rectangle, `angle` on a non-angled gradient, `start`/`end` next to `stops`, `stroke_width` without `stroke`). Warnings only concern the layers of that call; `vixl_check` is the complete audit. A tool call that passes an argument the tool does not take (`detial="full"`) is not silently dropped: its result gets a warning naming the argument and the closest parameter (image tools add a text line after the picture).

### Small responses and previews

Tool results are minified JSON text with no duplicated structured copy. Advertised schemas omit pydantic titles and collapse optional fields. `vixl mcp --schema slim` advertises only the operation type names (about half the tool-list size) and the agent fetches fields with `vixl_operation_schema`. The provider-backed planner (`vixl_ai_plan`) is hidden unless `--planner` is passed, because the calling agent already plans its own edits.

The default `detail: "brief"` apply response over MCP returns, per stable layer ID, only what the caller cannot already know: new layers as `added`/`name`/`type`/`bounds`, changed layers as the list of changed field names plus their resolved `bounds`, removals, `warnings` and `normalized`; state other than layers is listed by name under `also_changed`. `detail: "compact"` (the REST/CLI default) returns the **new** values of changed fields and the main content of new layers; `detail: "full"` returns before/after snapshots. Python's `Project.apply` accepts all three. `vixl_measure` summarizes channels as percentiles unless `histogram: "full"`.

Preview defaults: **1024×1024 maximum and 1 MiB of encoded PNG data**, preserving transparency and aspect ratio. Previews render a geometrically scaled copy of the document (JPEG sources decode at reduced scale), so a 24-megapixel document previews in a fraction of a second. Every layer edge (and every copy of a `repeat`) lands on a whole preview pixel, so layers or tiles that meet in the full render still meet in the preview and no seam appears between them; documents with canvas-sized effect selections fall back to a full render. `region: [x, y, w, h]` (pixels or percentages) zooms into part of the canvas. File export always uses full resolution unless a scale/profile is requested.

### Long calls, retries and progress

An MCP client typically gives up on a call after about 60 s, while the server still finishes the work and saves it. Vixl runs every tool call in a worker thread (a slow render no longer blocks other calls or the heartbeat) and turns a slow call into a job:

- **Automatic jobs.** A call that is still running after `VIXL_MCP_INLINE_SECONDS` (default 40, `0` disables) returns `{"status": "running", "job": "job_…", …}` while it carries on. Poll with `vixl_job`.
- **`as_job: true`** on the heavy tools (`vixl_operations_apply`, `vixl_import_image`, `vixl_import_document`, the export tools, `vixl_font_pair`, `vixl_font_install`, `vixl_workflow`, `vixl_roll`, `vixl_check`, the `vixl_ai_*` tools) starts the call as a job and returns its id at once.
- **`vixl_job(action, id, wait)`:** `status` reports `queued`/`running`/`completed`/`failed`/`cancelled` with `progress` (`wait=20` blocks up to that many seconds, at most 50, so one call replaces a polling loop); `result` returns the call's normal result under `result` (or `error`); `cancel` stops a queued job, or a running one at its next checkpoint (a batch of operations is atomic, so a cancelled batch changes nothing; timeline exports stop between frames); `list` shows recent jobs, including calls that timed out on your side. The server remembers the last 100 jobs in memory; durable workspace jobs from `vixl_workflow submit` use the same tool with their 32-character ids.
- **Retries: `request_id`.** The mutating tools (`vixl_operations_apply`, imports, exports, `vixl_document_create`/`close`, `vixl_template_create`, fonts, `vixl_history`, `vixl_workflow`, `vixl_roll`, the AI tools) accept an optional `request_id` (1–64 characters). Repeating a call with the same id returns the first call's recorded result with `"replayed": true` instead of applying twice; if the first call is still running, the repeat waits briefly and then points at its job. An id reused with different arguments is an error (`request_id_conflict`), and a call that failed is not remembered, so its retry runs. The store keeps the last 64 ids per document (512 overall), in memory.
- **Progress.** A client that sends a progress token receives `notifications/progress` while operation batches (one tick per operation), timeline exports (one per frame) and batch exports (one per file) run. Once a call has become a job, read its `progress` with `vixl_job`.

Recommended pattern for agents: send heavy calls with a fresh `request_id`; if one times out or returns a job, call `vixl_job(action="result", id, wait=30)` (or `list` when you never saw the id) instead of resending, and resend with the same `request_id` only if the result says it failed.

### Several agents on one server

The server keeps documents loaded in one shared cache, but the **active document is per MCP client session**: with Streamable HTTP each connected client opens, creates and closes documents without moving anyone else's active document, and a client that has opened nothing gets the document the server was started with (or none). A stdio server has exactly one client connection, so subagents of one parent agent still share one active document there. Three safeguards help in that case:

- `vixl mcp --require-document` (or `VIXL_REQUIRE_DOCUMENT=1`) makes `document=` mandatory on every document tool: there is no active document to fall back to, and a call without it fails with `document_required`. `vixl_document_create`/`open` still work and name the document in their result.
- Every result names the document it acted on (`document`), so a mistake shows up in the first response.
- Pass `document=` on every call, with `request_id` on mutating ones.

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

`POST /check` (same options as `vixl_check`), `POST /preview` (`max_width`, `max_height`, `max_bytes`, `region`, …; returns PNG) and `POST /compare` (`before`, `after`, `mode`; returns the summary plus `image_base64`). The REST service is bound to its one document and rejects a `document` field.

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

MCP adds `vixl_resources_list`, `vixl_resource_get`, `vixl_resource_add`, `vixl_template_create`, `vixl_import_font`, and `vixl_models_list`. Resource discovery needs no open document. Font paths and document destinations remain workspace scoped. `vixl_export_file` accepts `.svg`; operations accept registered font names while service operations continue to reject filesystem font paths.

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
name the fonts that are not embedded and must be installed where the deck is opened (`fonts_not_embedded`).

REST: `POST /export` accepts `page`, `pages`, `pdf_content`, `fillable`, `values`, `fill_mode` and
`presenter` (HTML slide presentation options) and format `PPTX`; `POST /preview` accepts `guides`, `page`, `values` and `show_fields`; the fixed
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
an OAuth-capable gateway. A shared server has one active-document selection; concurrent
agents should pass `document` explicitly on every document tool. Access covers the entire
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
```

MCP: `vixl_import_document(format="svg", path="logo.svg")`, or `data_base64` instead of `path`.
REST: `POST /import?format=svg` with raw bytes. PDF additionally accepts a one-based `page` and
`dpi` (36–600); it imports a raster reference layer, not editable PDF text or paths.

SVG imports create editable path layers with solid fills, strokes, translations, scales,
rotations, matrix transforms, and compound nonzero-winding paths (including holes). Arc and
shorthand path commands are converted to editable Bézier geometry. UTF-8 SVG files are limited
to 4 MiB and existing document resource limits. Unsupported features fail before changing the
document: text, images, gradients, CSS classes, clipping, filters, evenodd fills, rounded rectangles,
group opacity and nonuniformly transformed strokes. This is the default `svg_mode="editable"`. Use `svg_mode="appearance"` to render supported self-contained static SVG while retaining the source, or `"auto"` to try editable then appearance. See [studio.md](studio.md) for support and input restrictions.
Imports never fetch external resources. The original SVG element IDs become layer names.

### Consolidated studio workflows

`vixl mcp --tools compact --schema slim` exposes 12 document/operation/workflow/preview/import/export tools. Workflow actions include resource-list/get/save, shape-save, suite-use, palette-check, effect-run, group-list/define/show/apply/recover, branch-list/fork/status/merge and plugin-list/install/remove. REST allows the resource/test/effect actions while retaining fixed-project scope. `vixl_export_file` and REST export support HTML. Full contracts and examples: [studio.md](studio.md).
