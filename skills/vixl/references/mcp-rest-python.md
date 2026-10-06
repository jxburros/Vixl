# MCP, REST and Python interfaces

Vixl is headless and designed for autonomous AI agents; humans can use the same interfaces. See [new resources and SVG](resources.md) for 0.11 additions.

## MCP server

Start: `vixl mcp --workspace DIR` (stdio; requires the `mcp` extra or the Windows installer).
Legacy form `vixl --project /abs/poster.vixl mcp` opens that document and uses its folder as the
workspace. Client config:

```json
{"mcpServers": {"vixl": {"command": "vixl", "args": ["mcp", "--workspace", "/home/you/Pictures/Vixl"],
                         "env": {"VIXL_NO_UPDATE": "1"}}}}
```

**Two servers (recommended):** `--tools core` serves editing, rendering, checks, export and the
catalogs; `--tools ai` serves the provider-backed `vixl_ai_*` tools and `vixl_models_list`, plus
`vixl_workspace_list`, `vixl_document_open`, `vixl_document_inspect` and `vixl_render_preview`.
Register them as `vixl` and `vixl-ai` with the same workspace; skip `vixl-ai` when no provider is
configured. Edits are saved at once and each server reloads a document that changed on disk, so
the two see each other's work. The default `--tools all` serves everything from one server.

Windows installer path if `vixl` is not on PATH: `%LOCALAPPDATA%\Programs\Vixl\bin\vixl.exe`
(escape backslashes in JSON). Restart the client after install/config changes.

**Session model:** one *active document* per MCP client session. Nothing works without `document=`
until you call `vixl_document_create` or `vixl_document_open` (error: "Create or open a document
first"). Every result names the document it acted on (`"document": "poster.vixl"`). Subagents sharing
one stdio server share its one client session, so pass `document=` on every call; start the server
with `--require-document` (or `VIXL_REQUIRE_DOCUMENT=1`) to make that mandatory (`document_required`).
All paths are server-local and relative to (or absolute inside) the workspace; escaping paths and
symlinks out are rejected; `vixl_document_create`, `vixl_template_create` and exports create missing
directories inside the workspace. Successful edits are saved immediately,
so switching documents never loses work. External edits to the file are detected and reloaded.

**Long calls:** a call still running after ~40 s (`VIXL_MCP_INLINE_SECONDS`) returns
`{"status":"running","job":"job_…"}` and carries on; `as_job: true` on heavy tools does so at once.
Follow it with `vixl_job(action="status"|"result"|"cancel"|"list", id, wait=…)`; never resend a call
that timed out. Mutating tools take `request_id`: repeating a call with the same id returns the first
result (`"replayed": true`) instead of applying twice.

### Documents and files

| Tool | Parameters | Returns / notes |
| --- | --- | --- |
| `vixl_workspace_list` | `directory="."`, `offset=0`, `limit=100` (≤200) | `entries[{path,directory?}]`, `active`, `open`, `next_offset` |
| `vixl_document_create` | **`path`**, **`width`**, **`height`**, `background="transparent"` | Creates + activates (and creates missing directories); refuses existing files |
| `vixl_document_open` | **`path`** | Activates an existing `.vixl`; other open documents stay open (up to 8) |
| `vixl_document_close` | `document` | Drops a document from the session (edits are already saved) |
| `vixl_document_inspect` | `target=None`, `detail="compact"\|"full"` | Compact: canvas + one entry per layer with `bounds`; full: every field (with `resolved_bounds`) |
| `vixl_import_image` | `path` **or** `data_base64` (base64 or `data:` URL), `name="image"` | New layer; returns `{id, name, width, height, bounds, asset}` (≤64 MiB) |
| `vixl_export_file` | **`path`**, `quality` (default 90; also JPEG-compresses PDF images when given), `title` (PDF title), `max_bytes` (warn when a raster file is larger), `scale=1` (0.01–16), `profile`, `variables`, `background="white"`, `overwrite=False`, `sampling="smooth"\|"nearest"`, `artboard`, `comp` | Writes PNG/JPEG/WEBP/TIFF/AVIF (by extension); returns `{path, format, bytes}` |
| `vixl_export_batch` | **`targets`** (1–64 of `{path, document?, overwrite?, …any export option}`), `defaults`, `overwrite=False`, `stop_on_error=False` | Several sizes/formats/artboards/documents in one call. Everything is validated before the first file is written; each target reports `{path, format, bytes, document}` or its own `error` |
| `vixl_adapt_layout` | **`sizes`** (1–16: named size, `"1080x1920"` or `{size\|width+height, orientation, dpi, bleed, name}`), `directory`, `name="{name}-{size}"`, `options` (`scale`, `anchors`, `where`, `text`), `formats` (e.g. `["png"]`), `overwrite`, `report="summary"\|"layers"` | One call, a whole campaign: each size is a saved copy re-laid out by `adapt-layout` (optionally exported); the source is untouched; per size: file, canvas, scale, layers moved, warnings |
| `vixl_job` | `action="status"\|"result"\|"cancel"\|"list"`, `id`, `wait` (≤50 s) | Follow a long call or durable workflow job; see Long calls above. The compact tool set polls through `vixl_workflow` (`action: "status"`, `request: {id}`) |

### Editing and viewing

| Tool | Parameters | Returns / notes |
| --- | --- | --- |
| `vixl_operations_apply` | **`operations`** (1–10000 operation objects) or `operations_path` (workspace `.json`/`.jsonl` file), `dry_run=False`, `detail="brief"\|"compact"\|"full"`, `request_id`, `as_job` | Atomic. Brief (default): per layer ID, new layers as `{added, name, type, bounds}`, changed layers as `{changed: [fields], bounds}`; compact adds the new values of changed fields; full: before/after snapshots. `warnings` (text cut off or overflowing its box/group, fields that change nothing) and `normalized` (rewritten spellings) appear when relevant. |
| `vixl_capabilities` | `topic`, `fields=False` | Task-specific operations, exact fields, limits and gotchas |
| `vixl_operation_schema` | **`types`** (1–20 names) | Exact JSON Schema for those operation types (needed with `vixl mcp --schema slim`) |
| `vixl_render_preview` | `variables`, `max_width=1024`, `max_height=1024` (≤4096), `max_bytes=1048576` (64 KiB–4 MiB), `region=[x,y,w,h]` (px or %), `artboard`, `comp` | PNG at preview resolution (fast); `region` zooms in up to 8× |
| `vixl_render_compare` | `before="previous"`, `after="head"`, `mode="side-by-side"\|"diff"`, `max_width`, `max_height` | Summary (`changed_fraction`, `changed_region`) + image; refs: `head`, `previous`, `head~N`, branch, checkpoint, revision ID |
| `vixl_history` | `action="list"\|"undo"\|"redo"\|"branch"\|"checkpoint"\|"checkout"\|"begin"\|"commit"\|"rollback"`, `ref`, `count=1`, `offset`, `limit=20` | `list` → paginated node summaries; others → new head/branch |

Transactions: `vixl_history(action="begin")` → several `vixl_operations_apply` calls →
`commit` (one undo step) or `rollback`. Name branches/checkpoints with `ref`.

### Measurement and validation (read-only)

| Tool | Parameters | Returns |
| --- | --- | --- |
| `vixl_check` | `checks` (`bounds`,`overlap`,`contrast`,`safe_area`,`legibility`; default all), `targets`, `safe_area` (px, `"5%"` or `{left,top,right,bottom}`; default: the canvas's own safe area), `avoid` (reserved zones), `thumbnail_width=320` (null disables), `min_thumbnail_text=10`, `min_contrast`, `artboard`, `comp` | `{passed, errors, warnings, issues[{check,severity,layers,message,…}]}` — only problems |
| `vixl_measure` | `point=[x,y]`, `region=[x,y,w,h]`, `foreground`, `target`, `histogram="summary"\|"full"\|"none"`, `artboard`, `comp` | RGBA/hex sample, alpha-weighted average, channel percentiles (or 256-bin histograms), WCAG contrast min/p10/mean/max |
| `vixl_measure_spacing` | `targets`, `axis="vertical"`, `around`/`before`/`after`, `expected`, `tolerance=1`, `artboard`, `comp` | Per-gap pixels, overlap, min/max/mean/spread, `passed` |
| `vixl_validate` | `profile`, `rules`, `detail="summary"\|"full"`, `targets`, `severity`, `suppress`, `offset`, `limit=50` (≤200) | Overall `valid`, counts and paginated findings; full includes passing checks. Layer intent can mark deliberate bleed. |

Assertion grammar: `canvas.width == 1920`, `layer.NAME.exists`, `layer.NAME.bounds within canvas`,
`text.NAME.font-size >= 48`; comparators `== != > < >= <=`.

### Pixel art and animation

| Tool | Parameters | Notes |
| --- | --- | --- |
| `vixl_pixels_inspect` | `target` | `{id,name,width,height,palette,rows}` — read/modify sprites as text |
| `vixl_animation_inspect` | — | Frame names, sizes, durations, total; named animations (order, timing, loop) |
| `vixl_animation_preview` | **`name`**, `scale=1` (1–8) | Crisp nearest-neighbor PNG of a saved frame |
| `vixl_export_animation` | **`path`**, `format="gif"\|"apng"\|"webp"\|"mp4"\|"webm"\|"sheet"` (default: from extension), `animation=NAME`, `scale=1` (1–32), `sampling`, `colors`, `quality=90`, `columns`, `overwrite=False` | `animation` exports one named animation, else every saved frame; sheet also writes `same-stem.json` with frame rects/durations and the `animations` map; mp4/webm need ffmpeg; overwrites only when requested |

Edits use `vixl_operations_apply` with `pixel-art`, `pixel-draw`, `pixel-palette`, `frame-save`,
`frame-apply`, `frame-delete`, `animation-set` (`name`+`order` defines a named animation) and
`frames-edit` (the same operations applied to every saved frame, or an animation's, atomically).

### Guide, looks and styles

`vixl_guide(brief?)` is the first call for an open brief: with no argument it returns the start-here recipe and every
kind of work; with a kind or free text ("a mascot for a coffee brand") it returns the approach, operations, layouts,
looks, styles and a working example (`brief="operations"` and `brief="looks"` list those catalogs).
`vixl_styles(action="list|get|apply|check", name?, query?, palette?)` serves the 28 design styles; `apply` tags the
document (`style-set`), stores the brief as guidance and optionally applies the palette; `check` is
`vixl_check(checks=["style"])`. `vixl_check` also takes `style=` and returns `by_action` (fix / review /
informational) with every issue's `action`.

### Sizes, layouts, color, timelines and icons (0.13)

| Tool | Parameters | Notes |
| --- | --- | --- |
| `vixl_document_create` | `path`, `width`+`height` **or** `size`, `background`, `dpi`, `orientation`, `bleed` | Named sizes: `vixl_sizes_list(category, search)` |
| `vixl_layouts_list` | — | Layout names, principles, content keys and options (apply with `layout-apply`) |
| `vixl_brushes_list` | — | Brushes and settings (paint with the `paint` operation) |
| `vixl_color` | **`action`** `info\|convert\|harmony\|scale\|mix\|contrast\|names`, **`colors`**, `to`, `scheme`, `count`, `amount`, `space` | Color language tools |
| `vixl_timeline_inspect` | `detail="summary"\|"full"`, `targets`, `properties`, `start`, `end`, `offset`, `limit=50`, `key_offset`, `key_limit=50` (limits ≤200) | Bounded track/key counts and ranges; full adds paginated keys |
| `vixl_timeline_preview` | `time` **or** `count=8`, `columns`, `max_width=1600` | One frame or a labelled contact sheet |
| `vixl_export_timeline` | **`path`** (.gif/.png/.webp/.zip/.mp4/.webm), `format` (`sheet`), `fps`, `scale`, `start`, `end`, `background`, `columns`, `quality`, `overwrite` | Never overwrites unless asked |
| `vixl_export_icons` | **`directory`**, `icon_set` `web\|apple\|android\|windows\|all`, `sampling` | favicon.ico, PNG sizes, site.webmanifest |

`vixl_render_preview` also takes `time`, `proof`, `simulate`; `vixl_export_file` also takes `.pdf`/`.ico`
paths, `color_space="cmyk"`, `icc_profile` (workspace path), `intent`, `black_generation`, `ink_limit`,
`proof`, `simulate`, `dpi`, `icon_sizes`, `time`; `vixl_check` also takes `checks=["print","color_vision"]`,
`ink_limit`, `min_ppi`.

### Character, audio and spatial authoring

`vixl_export_character(target, output)` saves reusable character artwork and rigs as a portable `.vixl`.
`vixl_export_audio(path)` writes timeline score, sound effects and imported audio to WAV.
Use `vixl_spatial` for bounds, nearest/between/relative queries, free regions, snap candidates, grid cells, guides and hit tests.
Fetch exact operations with `vixl_capabilities(topic="animation")` and `vixl_operation_schema(types=[...])`.

### AI tools (need configured providers; see ai.md)

| Tool | Parameters |
| --- | --- |
| `vixl_ai_generate` | **`prompt`**, `mode="generate"\|"inpaint"\|"img2img"`, `width`+`height` (both or neither; default canvas), `seed`, `name="generated"`, `provider`, `model`, `negative_prompt`, `strength=0.75` |
| `vixl_ai_extend` | **`prompt`**, `left`/`right`/`top`/`bottom` (px, ≥1 positive), `seed`, `name`, `provider` |
| `vixl_ai_upscale` | **`layer`**, `scale=2` (≤16), `provider` |
| `vixl_ai_regenerate` | **`layer`**, `prompt`, `seed`, `provider` (defaults to the original provider) |
| `vixl_ai_remove_background` | **`layer`**, `provider` — attaches an editable mask |
| `vixl_ai_select_object` | **`label`**, `provider` — sets the active selection |
| `vixl_ai_select_subject` | `provider` |
| `vixl_ai_remove` | `name="removed-object"`, `provider` — inpaints the current selection |
| `vixl_ai_content_aware_fill` | `prompt`, `name="filled-region"`, `provider` |
| `vixl_ai_analyze` | **`capability`** `describe`\|`detect`\|`ocr`, `query`, `provider` |
| `vixl_ai_plan` | **`prompt`**, `apply=False`, `provider` — only when the server runs with `vixl mcp --planner` |

Every document tool also accepts `document` (workspace path) to address a document other than the active one.

### Resource

`vixl://operations` — the full operation JSON Schema (same as `vixl schema`). Usually unnecessary
because the schema is inline in `vixl_operations_apply`.

### MCP-specific restrictions

- Operation fields `path` and `linked` are rejected → import with `vixl_import_image`; reference
  embedded images by `asset` ID (see `vixl_document_inspect`), e.g. in `frame`/`replace-contents`/`add`.
- `font` works in batches (`text`, `text-set`, `rich-text` spans, `layout-apply`, fields) like `vixl_text_add`:
  pass a registered font name or a role (`heading`, `body`). Install first with `vixl_font_pair` /
  `vixl_font_install` / `vixl_import_font`; a file path or unregistered name is an error that lists the
  registered names. No font files over MCP.
- No plugins, no linked files. CSV `render --data` and `export-screens` are CLI/Python only.
- Tool errors carry JSON: `{"error","message","field","operation_index","operation_type","allowed"?,"suggestions"?}`
  — e.g. `layer_not_found` with `suggestions: ["title"]`. Correct the named field and retry; nothing
  was changed by a failed call.
- `vixl mcp --schema slim` advertises only operation type names (smaller tool list); look up fields
  with `vixl_operation_schema`.

## REST API

Start: `vixl -p poster.vixl serve [--host 127.0.0.1] [--port 8765]`. OpenAPI docs at `/docs`.
Non-loopback hosts require a bearer token from `VIXL_API_TOKEN` (or `--token-env NAME`); send
`Authorization: Bearer …`. One fixed project per server.

| Route | Body / query | Result |
| --- | --- | --- |
| `GET /schema` | | Operation JSON Schema |
| `GET /document` · `GET /layers` | | Inspection |
| `POST /operations` | `{"operations":[…],"dry_run":false,"detail":"compact"}` | Change summary |
| `GET /render` | | PNG |
| `POST /render` | `{"variables":{…},"artboard":…,"comp":…}` | PNG |
| `POST /measure` | `{"point":[x,y]}` / `{"region":[…],"foreground":…}` / `{"target":…}` | Measurements |
| `POST /spacing` | same keys as `vixl_measure_spacing` | Spacing report |
| `POST /validate` | `{"profile":…,"rules":[…]}` | Checks |
| `POST /check` | same keys as `vixl_check` | Design issues |
| `POST /preview` | `{"max_width":…,"max_height":…,"max_bytes":…,"region":[…]}` | PNG |
| `POST /compare` | `{"before":"previous","after":"head","mode":"side-by-side"}` | Summary + `image_base64` |
| `GET /pixels/{target}` | | Pixel rows/palette |
| `GET /animation` · `GET /animation/frame/{name}?scale=1` | | Frame list + named animations · PNG |
| `POST /animation/export` | `{"format":"gif"\|"apng"\|"webp"\|"mp4"\|"webm"\|"sheet","animation":"walk","scale":8,"sampling":…,"colors":…,"quality":…,"columns":…}` | Animation bytes (mp4/webm need ffmpeg) |
| `GET /history` · `POST /history/{action}` | `{"ref":…,"count":1}` | History graph / new head |
| `POST /assets?name=photo` | raw image bytes | New layer |
| `POST /ai/{command}` | `{"args":["--prompt","forest","--provider","local"]}` | CLI-style AI call |
| `POST /export` | `{"format":"PDF","color_space":"cmyk","ink_limit":300}`, `ICO`+`icon_sizes`, `icc_profile_base64`, `proof`, `simulate`, `dpi`, `time` | File bytes |
| `GET /sizes?category=` · `GET /layouts` · `GET /brushes` · `GET /guide?brief=` · `GET /styles?query=\|name=` · `GET /looks` | | Catalogs |
| `POST /color` | `{"action":"harmony","colors":["#2563eb"],"scheme":"triadic"}` | Color tools |
| `GET /timeline` · `GET /timeline/frame?time=1.5s` | | Tracks · PNG frame |
| `POST /timeline/export` | `{"format":"gif","fps":15,"scale":0.5}` | Animation bytes |

Errors: HTTP 400 with `{"error":CODE,"message":…}` (403 for `forbidden`, 413 for oversized bodies).
`path`/`linked` operation fields are rejected and `font` takes only a registered name or role, as with MCP.

```bash
curl -s -X POST http://127.0.0.1:8765/operations -H 'Content-Type: application/json' \
  -d '{"operations":[{"type":"move","target":"logo","x":20,"y":40}]}'
curl -s http://127.0.0.1:8765/render -o preview.png
curl -s -X POST 'http://127.0.0.1:8765/assets?name=photo' --data-binary @photo.jpg
```

## Python API

```python
from vixl import Project, VixlError
from vixl.model import Limits

p = Project(1080, 1080, background="#101828")              # new, unsaved
p = Project.load("poster.vixl", limits=Limits(max_pixels=16_000_000), allow_linked=False)

p.apply([{"type": "text", "name": "title", "text": "Hi", "size": 64}], dry_run=False, detail="compact")
p.inspect()                 # dict; p.inspect("title") for one layer
p.layer("title")            # live layer dict (read-only use)
img = p.render(variables={"title": "Hello"}, artboard=None, comp=None)   # Pillow RGBA
data = p.export("out.png", quality=90, scale=2, profile=None, sampling="smooth")  # bytes, writes path
p.save() ; p.save("copy.vixl")

p.undo(1); p.redo(1); p.checkpoint("clean"); p.branch("vivid"); p.checkout("clean")
p.begin(); ...; p.commit()  # or p.rollback()

p.measure(point=(10, 10)); p.measure(region=(0, 0, 100, 100), foreground="#fff"); p.measure(target="title")
p.measure_spacing(targets=["a", "b", "c"], axis="vertical", expected=24, tolerance=1)
p.check(safe_area="5%", avoid=[["85%", "85%", "15%", "15%"]], thumbnail_width=320)
p.at("previous").render()   # a read-only view at head~1, a branch, checkpoint or revision ID
p.inspect_pixels("sprite"); p.inspect_animation(); p.render_frame("idle", scale=4)
p.export_animation("sprite.gif", format="gif", scale=8)      # or "apng" / "webp" / "mp4" / "webm" / "sheet" (columns=)
p.export_animation("walk.gif", animation="walk", scale=8)    # one named animation; REST POST /animation/export {"animation": "walk"}
p.export_screens("screens", scales=(1, 2))
p.render_data("rows.csv", "campaign")
p.manifest()

try:
    p.apply({"type": "move", "target": "nope", "x": 1})
except VixlError as e:
    print(e.code, e.details, e.as_dict())
```

Python is a trusted local API: `path`, `font` and `linked` fields work. Enable plugins with
`vixl.plugins.enable_plugins()`.
