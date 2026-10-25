# MCP, REST and Python interfaces

Vixl is a headless design engine for AI agents; people can drive the same interfaces. See [new resources and SVG](resources.md) for 0.11 additions.

## MCP server

Start: `vixl mcp --workspace DIR` (stdio; MCP support is part of the base `vixl-engine` package and the Windows installer).
Legacy form `vixl --project /abs/poster.vixl mcp` opens that document and uses its folder as the
workspace. Client config:

```json
{"mcpServers": {"vixl": {"command": "vixl", "args": ["mcp", "--workspace", "/home/you/Pictures/Vixl"],
                         "env": {"VIXL_NO_UPDATE": "1"}}}}
```

**Seven tools.** `vixl_document`, `vixl_apply`, `vixl_check`, `vixl_render`, `vixl_export`, `vixl_reference` and
`vixl_job`. Each advertises a few typed fields (`action` or `kind` picks what it does) plus `options`; any other
argument is folded into `options` and validated against the chosen action, so `vixl_render(max_width=200)` works.
`vixl_reference("vixl_export")` (any tool with actions: all but `vixl_job`) lists every action with its options and
`vixl_reference("vixl_export", name="timeline")` one action; an unknown or mistyped option fails with
`invalid_arguments`, the closest names and that schema (`vixl_job` and the `vixl_ai_*` tools take no `options`: an
unknown argument there is ignored with a warning).

**Two servers:** `vixl mcp` serves the design tools; `vixl mcp --tools ai` serves the provider-backed `vixl_ai_*`
tools and `vixl_models_list`, plus `vixl_document`, `vixl_render` and `vixl_job`.
Register them as `vixl` and `vixl-ai` with the same workspace; skip `vixl-ai` when no provider is
configured. Edits are saved at once and each server reloads a document that changed on disk, so
the two see each other's work.

Windows installer path if `vixl` is not on PATH: `%LOCALAPPDATA%\Programs\Vixl\bin\vixl.exe`
(escape backslashes in JSON). Restart the client after install/config changes.

**Session model:** one *active document* per MCP client session. Nothing works without `document=`
until you call `vixl_document(action='create')` or `vixl_document(action='open')` (error: "Create or open a document
first"). Every result names the document it acted on (`"document": "poster.vixl"`). Subagents sharing
one stdio server share its one client session, so pass `document=` on every call. Once a connection has
created, opened or addressed more than one document it has not closed (or has chosen none while several
are open), a call without `document=` is refused (`ambiguous_document`, listing them under `documents`);
with one open it keeps working. Start the server with `--require-document` (or `VIXL_REQUIRE_DOCUMENT=1`)
to make `document=` mandatory (`document_required`).
All paths are server-local and relative to (or absolute inside) the workspace; escaping paths and
symlinks out are rejected; `vixl_document(action='create')` (also with a template) and exports create missing
directories inside the workspace. Successful edits are saved immediately,
so switching documents never loses work. External edits to the file are detected and reloaded.
Results are terse by default (a new document: path, canvas, seed, the fonts chosen); `verbose: true` on
`vixl_document` and on a `vixl_apply` batch returns everything.

**Long calls:** a call still running after ~40 s (`VIXL_MCP_INLINE_SECONDS`, or `--call-timeout`/`VIXL_CALL_TIMEOUT`)
returns `{"status":"running","job":"job_…"}` and carries on; `as_job: true` on `vixl_apply`, `vixl_check`,
`vixl_export` and the `vixl_ai_*` tools does so at once. `vixl_render` always answers inline. Under load (more calls
than `VIXL_MCP_WORKERS`) calls become jobs sooner; `queued: true` means it has not started yet.
Follow it with `vixl_job(action="status"|"result"|"cancel"|"list", id, wait=…)`; never resend a call
that timed out. A server with a hard timeout (`--call-hard-timeout`, 600 s by default on `vixl mcp --http`) cancels a
call that runs longer: split the work (fewer pages, frames or operations) rather than retrying it whole. A timeline export's `progress` has `timing` (`elapsed_s`, `eta_s`, `setup_ms`, `raster_ms`).
With `VIXL_PROFILE=1` in the server's environment, results carry a `render_profile` (REST: also the
`X-Vixl-Profile` header). `vixl_document`, `vixl_apply`, `vixl_export` and the `vixl_ai_*` tools take `request_id`
(up to 64 characters): repeating a call with the same id returns the first result (`"replayed": true`) instead of
applying twice, and the same id with different arguments is `request_id_conflict`.
A shared server may set per-call limits (`vixl_job(action="list")` shows them under `limits`). A call over
one fails with `limit_exceeded` and names the `limit`: `max_megapixels` (lower `scale` or export fewer
pages), `max_pages` (export a page range, then the next) or `max_concurrent` (wait for a running job, then retry).

### vixl_document

| Action | Parameters | Returns / notes |
| --- | --- | --- |
| `inspect` (default) | `target`, `object`, `verbose` | Canvas + one entry per layer with `bounds`; `verbose`: every field (with `resolved_bounds`); `object`: one object's tree (`"*"` all) |
| `create` | **`path`**, `size` or `width`+`height` or `purpose` (none: 1080×1080), `background`, `dpi`, `orientation`, `bleed`, `seed`, `variety`, `font_pairing`, `workspace_fonts=true`, `house_style` (`on`/`off`), `template` (+ `variables`) | Creates + activates (and creates missing directories); refuses existing files. Rolls `design_defaults`; without `background` the canvas is the palette background (transparent for logo/icon/favicon sizes and mark purposes); installs the rolled font pairing (cache, then network). `house_style="off"` (or `.vixl/variety.json` `"house_style": "off"`) rolls none of it: white canvas (transparent for marks), workspace fonts else the bundled font, neutral `design_defaults` (`house_style: "off"`) that layout-apply follows. `creation` reports the choices (`verbose` adds the whole rolled direction) |
| `open` | **`path`** | Activates an existing `.vixl`; other open documents stay open (up to 8). |
| `close` | `document` | Drops a document from the session (edits are already saved) |
| `list` | `path="."`, `offset=0`, `limit=100` (≤200) | `entries[{path,directory?}]`, `active`, `open`, `next_offset` |
| `history` | `offset`, `limit=20` | Newest-first revision summaries, head, branches, checkpoints |
| `undo` / `redo` | `count=1` | The new head |
| `checkpoint` / `branch` / `checkout` | **`ref`** | Name a revision, start a branch, move to a revision (`head~N`, branch, checkpoint, ID) |
| `begin` / `commit` / `rollback` | | Transactions: `begin` → several `vixl_apply` calls → `commit` (one undo step) or `rollback` |
| `compact` | `dry_run`, `fonts=true` | Drops all undo history and unused embedded files; try `dry_run` first |
| `notes` | `text` (add) or `resolve` (an ID) | Human review notes left in `vixl view` |

### vixl_apply

| Form | Parameters | Returns / notes |
| --- | --- | --- |
| batch (default) | **`operations`** (1–10000 objects) or `operations_path` (workspace `.json`/`.jsonl`), `dry_run`, `check`, `suites`, `preview`, `repair`, `detail="brief"\|"compact"\|"full"` (or `verbose`), `document`, `request_id`, `as_job` | Atomic. Items are operations (fields: `vixl_reference("operations", name=[…])`) or session steps that run in the same all-or-nothing batch: `import-image` {`path` \| `data_base64` (base64 or `data:` URL) \| `url` (public `https://`), `name`, `credit`, `license`; returns `{id, name, width, height, bounds, asset, source}` under `steps`}, `import-document` {`path` \| `data_base64` \| `source` (a Figma URL or key), `format` svg\|pdf\|figma, `page`, `dpi`, `svg_mode` editable\|appearance\|auto, Figma `node_id` and `rasterize_unsupported`; the Figma token comes from `FIGMA_TOKEN`/`VIXL_FIGMA_TOKEN` only}, `import-font` {`name`, `path` \| `url`}, `font-pair` {`pairing` (default random), `mood`, `best_for`, `seed`, `scope`}, `font-install` {`family`, `weight`, `italic`, `name`, `role`, `scope`}, `style-use` {`name`, `palette`}, `roll` {`purpose`, `mood`, `seed`, `variety`, `locks`, `slots`, `unfilled`}; `scope: "workspace"` writes `brand.json` instead. `check=true` (or check names) adds vixl_check's findings for the touched layers plus every `fix` and every composition finding, and `check.regions`: the two weakest regions; `suites=true` (or names) runs the document's attached check suites and lists the rules that did not pass; `preview=true` (or `{page, region, max_width, time, isolate, overlay, focus, regions}`) adds a 512 px PNG and, with `check`, real-size crops of those regions after it (`regions: 0` leaves them out). Brief (default): per layer ID, new layers as `added`, `name`, `type`, `bounds` (plus a shape's `content_bounds` and a text layer's `ink_bounds` and `baseline`), changed layers as `{changed: [fields], bounds}`, numbers rounded to 2 decimals; at most 25 added and 50 changed/removed layers, the rest counted under `changes.layers_omitted` / `changed_omitted` / `removed_omitted` `{count, by_parent, sample}`; compact adds the new values; full: before/after snapshots. `warnings` and `normalized` appear when relevant. An invalid item's error carries its exact schema. |
| `create={…}` | **`create`** {`path`, `size` or `width`/`height` or `purpose`, `background`, `variety`, `dpi`, `orientation`, `bleed`, `seed`, `house_style` (`on`/`off`), `font_pairing`, `layout` ({name, …slots}), `style`, `look` ({look, target?, …} or a list)}, `operations` or `operations_path`, `check=True`, `strict=False`, `preview`, `exports` (paths or export targets), `overwrite`, `dry_run` | A whole new piece in one atomic call: create → fonts → layout → style → look → operations → check → preview → save → exports. Nothing is saved or exported unless every step succeeds; errors keep the normal schema plus `step`. Layout `image`/`images` accept workspace paths and https URLs; `style` fills open layout `align`/`palette`/`mode` and, without `font_pairing`, installs the style's first pairing. Like `create` it makes the new document active (`active_document: true`, with a warning naming the one it replaced) |
| `workflow=ACTION` | **`workflow`**, `request` (the action's fields: `vixl_reference("workflows", name=ACTION)`), `document` | Production actions: suites (`check`, `act`, `suite-use`, `suite-infer`), resources (`resource-list/get/save`), libraries, branches and groups, `check-all`, `replace-across`, `pipeline-run`, `data-sync`, `bulk-upgrade`, `merge-impose`, `form-fill`, `repair-layout`, `protected-edit`, `adapt-sizes` (**`sizes`** 1–16, `directory`, `name="{name}-{size}"`, `options`, `formats`, `overwrite`, `report`: each size a saved, re-laid-out copy), film and lyric video, `logo-package`, `brand-board`, `proof`, emoji and mockup actions, `submit`/`status` for durable jobs |

### vixl_check (read-only unless `repair`)

| Action | Parameters | Returns |
| --- | --- | --- |
| `design` (default) | `checks` (default: bounds, overlap, contrast, safe_area, legibility, blanks, placeholders, fonts, brand, content, form, links, diagram, flow, codes, composition, object; opt-in: print, color_vision, guides, alignment, drawing, style, motion, character, captions, connected, cost, deck, accessibility, budget, spelling, approval (on with the defaults once the document is approved) …; an explicit list replaces the defaults; `vixl_reference("checks")` describes each), `targets`, `safe_area` (px, `"5%"` or `{left,top,right,bottom}`), `avoid`, `thumbnail_width="auto"` (320; null disables), `min_thumbnail_text=10`, `min_contrast`, `ink_limit`, `min_ppi`, `page`, `deck`, `sample`, `style`, `connect_tolerance`, `artboard`, `comp`, `repair`, `offset`/`limit`, `profile`, `waivers`, `artboards`/`pages`/`comps` (`"all"` or names), `include_hidden` | `{passed, errors, warnings, issues[{check,severity,action,layers,message,…}], by_action, outcome}` — only problems. `passed` is false while any issue has action `fix`; `by_action` lists issue indexes under fix / review / informational |
| `measure` | `point=[x,y]`, `region=[x,y,w,h]`, `foreground`, `target`, `histogram="summary"\|"full"\|"none"`, `artboard`, `comp` | RGBA/hex sample, alpha-weighted average, channel percentiles (or 256-bin histograms), WCAG contrast |
| `spacing` | `targets`, `axis="vertical"`, `around`/`before`/`after`, `expected`, `tolerance=1`, `artboard`, `comp` | Per-gap pixels, overlap, min/max/mean/spread, `passed` |
| `validate` | `profile`, `rules`, `verbose` (include passes), `targets`, `severity`, `suppress`, `offset`, `limit=50` (≤200) | Overall `valid`, counts and paginated findings |
| `spatial` | `target`, `targets`, `to`, `mode` (relations, canvas, matrix, grid, guides, composition, hit, free, snap, all), `bounds="box"\|"ink"`, `tolerance`, `point`, `region`, `grid`, `describe`, `limit`, `page`, `safe_area` | Relations, gaps, alignment, margins, grid and guide offsets, hit tests, free regions, snap operations |
| `pixels` | `target` | `{id,name,width,height,palette,rows}` — read sprites as text |

Assertion grammar: `canvas.width == 1920`, `layer.NAME.exists`, `layer.NAME.bounds within canvas`,
`text.NAME.font-size >= 48`; comparators `== != > < >= <=`.

### vixl_render

| Action | Parameters | Notes |
| --- | --- | --- |
| `preview` (default) | `max_width=1024`, `max_height=1024` (≤4096), `max_bytes=1048576` (64 KiB–4 MiB), `region=[x,y,w,h]` (px or %), `page` (or `"all"`), `time`, `isolate=[layer…]`, `views=["parts"]`, `exploded`, `overlay`, `proof`, `simulate`, `guides`, `show_fields`, `values`, `variables`, `artboard`, `comp` | PNG at preview resolution; `region` zooms up to 8×; `isolate` shows one object (a group, an object path such as `person/guitar`, or `object:KIND`) alone, cropped to its ink; `views=["parts"]` adds a labelled sheet of each part; `overlay` outlines each fix finding with its rule and layer ID |
| `compare` | `before="previous"`, `after="head"`, `mode="side-by-side"\|"diff"`, `max_width`, `max_height`, `isolate` | Summary (`changed_fraction`, `changed_region`) + image |
| `timeline` | `time` **or** `count=8` **or** `times=[…]`, `thumbnail` (poster/middle/last at that width), `columns`, `max_width=1600` | One frame or a labelled contact sheet of keyframed motion |
| `timeline-inspect` | `verbose` (paginated keys), `targets`, `properties`, `start`, `end`, `offset`, `limit=50`, `key_offset`, `key_limit=50` | Bounded track/key counts and ranges |
| `animation` | **`name`**, `scale=1`, `sampling` | Crisp nearest-neighbor PNG of a saved frame |
| `animation-inspect` | — | Frame names, sizes, durations, total; named animations (order, timing, loop) |

### vixl_export

| Kind | Parameters | Notes |
| --- | --- | --- |
| `file` (default) | **`path`** (format from the extension), `overwrite`, `quality`, `scale=1` (0.01–16), `profile`, `variables`, `background="white"`, `sampling`, `svg_policy`, `artboard`, `comp`, `color_space="rgb"\|"cmyk"`, `icc_profile` (workspace path), `intent`, `black_generation`, `ink_limit`, `proof`, `simulate`, `dpi`, `icon_sizes`, `time`, `page`, `pages`, `pdf_content`, `fillable`, `values`, `fill_mode`, `alpha`, `presenter`, `title`, `max_bytes`, `isolate`, `padding`, `check`, `spec` | PNG/JPEG/WEBP/TIFF/AVIF/SVG/PDF/ICO/HTML/PPTX/PSD; returns `{path, format, bytes, …}` and never image bytes (`vixl_reference("exports")` explains the formats). `check=true` or `spec` (a delivery preset such as `print-letter-bleed`, `instagram-feed`, `web-banner`, or fields `{max_bytes, pages, trim, bleed, fonts_embedded, color, dpi, alpha …}`) reads the written file back: the result is `export_check` (`check: "export"` findings), and the outcome takes its validation; batch targets take the same two fields |
| `batch` | **`targets`** (1–64 of `{path, document?, overwrite?, …any file option}`), `defaults`, `overwrite`, `stop_on_error` | Everything is validated before the first file is written; each target reports its metadata or its own `error` |
| `timeline` | **`path`** (.gif/.apng/.webp/.zip/.mp4/.webm, or `format="sheet"`), `fps`, `scale`, `start`, `end`, `background`, `columns`, `quality`, `colors`, `dither`, `max_bytes`, `target_bytes`, `preset` (`chat`/`web`/`email`), `poster`, `sample_rate`, `overwrite` | Keyframed motion; MP4/WebM need ffmpeg |
| `animation` | **`path`**, `format`, `animation=NAME`, `scale` (0.05–32), `sampling`, `colors`, `dither`, `max_bytes`, `quality`, `columns`, `overwrite` | Saved frames; a sheet also writes `same-stem.json` with frame rects, durations and the `animations` map |
| `audio` | **`path`** (.wav), `sample_rate` | Mix of the audio tracks at the highest source rate (≤48 kHz), mono when every source is mono and unpanned |
| `icons` | **`path`** (a folder), `icon_set` `web\|apple\|android\|windows\|all`, `sampling` | favicon.ico, PNG sizes, site.webmanifest |
| `character` | **`path`** (.vixl), **`target`** | A portable character document for `character-load source` (packages with poses, expressions and motions: workflow `character-package`) |

Without `kind`, `.wav` is audio, `targets` is a batch, and `.gif`/`.apng`/`.mp4`/`.webm`/`.zip` are the
timeline, or the saved-frame animation when the document has frames and no timeline.

### vixl_reference

`vixl_reference()` is the first call for an open brief: the start-here recipe and every kind of work.
`vixl_reference("a mascot for a coffee brand")` (a kind or free text) returns the approach, operations, layouts,
looks, styles, a working example and `motifs`; its rolled `direction` favours palettes with the moods the brief's
words imply (`direction.mood_source: "brief"`, `brief_moods`, `mood_words`) and suggests the motif to draw
(`motif_suggestion`, no layers added); a guidance name (`finishing`, `testing`, `batches`, `checks`,
`exports`, `looping-motion` …) returns its text. Topics with `name` (and `options`):
`operations` (`name=[types]`: exact schemas; none: every operation by purpose), `workflows`, `capabilities`
(`name=TOPIC`, `fields`), `sizes` (`name` search, `category`), `layouts`, `fonts` (a pairing or family name, or
`view`, `mood`, `best_for`, `category`, `role`), `brushes`, `styles` (`name`, or `query`), `looks`, `color`
(**`name`**: colours, `action` info\|convert\|harmony\|scale\|mix\|contrast\|names\|natural, `to`, `scheme`, `count`,
`amount`, `space`), `roll` (`purpose`, `mood`, `seed`, `variety`, `locks`: a direction without applying it),
`palettes`, `templates`, `guidance`, `objects`, `house-style`, `guide` (`name`: a kind of work or brief, `seed`,
`variety`) and any tool name with actions (its actions and options; not `vixl_job`).
`vixl_check` also takes `style=` (and `checks=["style"]`) to evaluate a style's rules.

### AI tools (`vixl mcp --tools ai`; need configured providers; see ai.md)

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
| `vixl_ai_plan` | **`prompt`**, `apply=False`, `provider` — only with `vixl mcp --tools ai --planner` |
| `vixl_models_list` | `provider`, `capability` (plan, describe, detect, ocr, generate, segment, upscale, background-remove), `refresh` — the model IDs an account offers |

Every document tool also accepts `document` (workspace path) to address a document other than the active one.

### Resource

`vixl://operations` — the full operation JSON Schema (same as `vixl schema --all`). Usually unnecessary:
`vixl_reference("operations", name=[…])` returns the types you need.

### MCP-specific restrictions

- Operation fields `path` and `linked` are rejected → import with an `import-image` step; reference
  embedded images by `asset` ID (see `vixl_document(action='inspect')`), e.g. in `frame`/`replace-contents`/`add`.
- `font` works in batches (`text`, `text-set`, `rich-text` spans, `layout-apply`, fields):
  pass a registered font name or a role (`heading`, `body`). Install first with a `font-pair`,
  `font-install` or `import-font` (`path` or `url`) step; a file path or unregistered name is an error that lists the
  registered names. No font files over MCP.
- No plugins, no linked files. CSV `render --data` and `export-screens` are CLI/Python only.
- Tool errors carry JSON: `{"error","message","field","operation_index","operation_type","allowed"?,"suggestions"?,"schema"?}`
  — e.g. `layer_not_found` with `suggestions: ["title"]`, or an invalid operation with the `schema` of its type.
  Correct the named field and retry; nothing was changed by a failed call.
  File paths in errors are relative to the workspace. `"internal": true` (with `exception`) marks a Python
  exception from inside an operation rather than a validation error: check the values, then report it.

## REST API

Start: `vixl -p poster.vixl serve [--host 127.0.0.1] [--port 8765]`. OpenAPI docs at `/docs`.
Non-loopback hosts require a bearer token of at least 24 characters from `VIXL_API_TOKEN` (or `--token-env NAME`);
send `Authorization: Bearer …`. 20 bad tokens from one address within 60 s answer 429 with `Retry-After`. A remote
bind over plain HTTP warns on stderr: use a TLS proxy or `--tls-cert`/`--tls-key`. `--offline` (`VIXL_OFFLINE=1`)
refuses URL imports, font downloads and providers with `network_disabled`. One fixed project per server.

| Route | Body / query | Result |
| --- | --- | --- |
| `GET /schema` | | Operation JSON Schema |
| `GET /document` · `GET /layers` | | Inspection |
| `POST /operations` | `{"operations":[…],"dry_run":false,"detail":"compact"}`, or `operations_path`; optional `check`, `suites`, `repair`, `preview` as for `vixl_apply` | Change summary (`preview_base64` with `preview`) |
| `GET /render` | | PNG |
| `POST /render` | `{"variables":{…},"artboard":…,"comp":…}` | PNG |
| `POST /measure` | `{"point":[x,y]}` / `{"region":[…],"foreground":…}` / `{"target":…}` | Measurements |
| `POST /spacing` | same keys as `vixl_check(action='spacing')` | Spacing report |
| `POST /validate` | `{"profile":…,"rules":[…]}` | Checks |
| `POST /check` | same keys as `vixl_check`; `sample` is `"worst"` or a workspace CSV path; unknown keys are a 400 | Design issues |
| `POST /preview` | `{"max_width":…,"max_height":…,"max_bytes":…,"region":[…],"isolate":[…]}` | PNG |
| `POST /compose` | vixl_apply(create=…) fields without `path`, `exports` or `operations_path` | Dry run: steps, check findings, `preview_base64` (the server serves one fixed document, so nothing is saved) |
| `POST /compare` | `{"before":"previous","after":"head","mode":"side-by-side","isolate":[…]}` | Summary + `image_base64` |
| `GET /pixels/{target}` | | Pixel rows/palette |
| `GET /animation` · `GET /animation/frame/{name}?scale=1` | | Frame list + named animations · PNG |
| `POST /animation/export` | `{"format":"gif"\|"apng"\|"webp"\|"mp4"\|"webm"\|"sheet","animation":"walk","scale":8,"sampling":…,"colors":…,"quality":…,"columns":…}` | Animation bytes (mp4/webm need ffmpeg) |
| `GET /history` · `POST /history/{action}` | `{"ref":…,"count":1}` | History graph / new head |
| `POST /assets?name=photo` | raw image bytes, or empty with `url=https://…`; optional `credit`, `license` | New layer |
| `POST /import?format=svg\|pdf\|figma` | raw bytes (Figma: the URL or file key); `name`, `page`, `dpi`, `svg_mode`, `node_id`, `rasterize_unsupported`, `font_map` (repeat `SRC=NAME`), `install_fonts` | Editable layers (`svg_mode=appearance`: one image) |
| `POST /fonts?name=brand` | raw TTF/OTF bytes (≤16 MiB) | Registered font |
| `GET /resources/{kind}` · `GET\|POST /resources/{kind}/{name}` | POST `{"value":…}` | Names · one entry · save |
| `POST /workflow/{action}` · `GET /workflow/schema` | the action's request | Workflows allowed on a fixed document (`docs/reference/interfaces.md#capability-matrix` lists them) |
| `GET /limits` · `GET /jobs` · `GET /jobs/{id}?wait=20` · `GET /jobs/{id}/result` | | Per-call limits · detached calls (a call over `--call-timeout` answers `202` with a job) |
| `POST /ai/{command}` | `{"args":["--prompt","forest","--provider","local"]}` | CLI-style AI call |
| `POST /export` | `{"format":"PDF","color_space":"cmyk","ink_limit":300}`, `ICO`+`icon_sizes`, `icc_profile_base64`, `proof`, `simulate`, `dpi`, `time` | File bytes |
| `GET /sizes?category=` · `GET /layouts` · `GET /brushes` · `GET /guide?brief=` · `GET /styles?query=\|name=` · `GET /looks` | | Catalogs |
| `POST /color` | `{"action":"harmony","colors":["#2563eb"],"scheme":"triadic"}` | Color tools |
| `GET /timeline` · `GET /timeline/frame?time=1.5s` | | Tracks · PNG frame |
| `POST /timeline/export` | `{"format":"gif","fps":15,"scale":0.5}` | Animation bytes |

Errors: HTTP 400 with `{"error":CODE,"message":…}` (401 without the token, 403 for `forbidden`, 404 for a missing
workspace file, 413 for oversized bodies and `limit_exceeded`, 429 with `Retry-After` for `max_concurrent` or
repeated bad tokens).
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

p = Project(1080, 1080, background="#101828")              # new, unsaved plain canvas
p = Project(purpose="social", seed=7)    # design document as vixl new/vixl_document(action='create') make it
p = Project.new("letter", seed=7, report=info)             # every creation option; info["creation"]
p = Project.new("letter", house_style="off")               # no rolled direction: white canvas, neutral defaults
p = Project.load("poster.vixl", limits=Limits(max_pixels=16_000_000), allow_linked=False)

p.apply([{"type": "text", "name": "title", "text": "Hi", "size": 64}], dry_run=False, detail="compact")
p.apply(ops, check=True)    # also runs the design check: result["check"], as vixl_apply(check=true); or check names
p.apply(ops, validator=fn)  # fn(op) for each validated operation before the batch runs; raise VixlError to refuse
p.import_image("photo.jpg", name="hero", credit="Photo: Ana Ruiz", license="CC0")   # or data=bytes
p.import_image(url="https://images.example.com/cat.jpg", name="cat", license="CC BY 4.0")  # https, public hosts only
p.inspect()                 # dict; p.inspect("title") for one layer
p.bounds("title")           # (x, y, w, h) on the canvas, grouped or not; space="parent" for group coordinates
p.layer("title")            # live layer dict (read-only use)
img = p.render(variables={"title": "Hello"}, artboard=None, comp=None)   # Pillow RGBA
data = p.export("out.png", quality=90, scale=2, profile=None, sampling="smooth")  # bytes, writes path
p.save() ; p.save("copy.vixl")   # another existing file needs overwrite=True

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

from vixl.compose import run    # vixl_apply(create=…): a new piece in one atomic call, inside a workspace folder
run("work", path="card.vixl", size="instagram-post", layout={"name": "hero-statement", "title": "Hi"},
    exports=["card.png"], preview=True)   # result dict; preview PNG bytes under "preview_png"
from vixl.image_diff import diff_files   # vixl diff
diff_files("before.png", "after.vixl", "diff.png")     # changed_pixels, changed_fraction, changed_region
from vixl.plugins.workspace_qa.proof import proof_page        # workflow proof
proof_page(["card.vixl", {"path": "card.png", "before": "old.png"}], "proof.html", decisions=True)

try:
    p.apply({"type": "move", "target": "nope", "x": 1})
except VixlError as e:
    print(e.code, e.details, e.as_dict())
```

Python is a trusted local API: `path`, `font` and `linked` fields work. Enable plugins with
`vixl.plugins.enable_plugins()`.

See `docs/reference/interfaces.md#capability-matrix` for the generated interface comparison. REST permits only its
fixed-document workflow allow-list; CLI, MCP and Python Session workflows expose the workspace registry.
MCP screen capture is opt-in. Service timeouts detach work, not kill it. Archive opening defaults to at most
160 million cumulative image pixels and 64 font assets, configurable through Python `Limits`.
