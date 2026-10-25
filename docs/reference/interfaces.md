# Python, REST, MCP, and extension interfaces

[Documentation home](../README.md) · [Getting started](../getting-started.md) · [Visual gallery](../gallery.md)

Vixl is a headless design engine for AI agents; people can drive the same interfaces.

See [spacing checks and pixel animation](../guides/motion/pixel-animation-spacing.md) for the 0.9.0 tools and API examples.

See [design tools and template production](../guides/shapes/design-tools.md) for groups, clipping, shapes, styles, artboards, CSV rendering, measurements, and the other design operations.

## Capability matrix

<!-- interface-capabilities:start -->
| Capability | REST | MCP | CLI | Python |
| --- | --- | --- | --- | --- |
| Documents per session | One fixed document | Multiple, inside the workspace | One active document; workspace workflows | Multiple Project instances; Session for workflows |
| Workflows | `act`, `check`, `drawing-report`, `effect-run`, `film-plan`, `form-fill`, `links`, `lyric-video-plan`, `organic-catalog`, `palette-check`, `plan`, `protected-edit`, `repair-layout`, `resource-get`, `resource-list`, `resource-save`, `shape-save`, `suite-use` | All 92 registered actions | All 92 registered actions | All 92 registered actions via workflows.dispatch(Session, ...) |
| AI tools | Configured local providers via /ai | Configured local providers; a second server, vixl mcp --tools ai | Configured local providers | Configured local providers |
| Linked files outside workspace | Forbidden | Forbidden | Explicit --allow-linked | Explicit allow_linked=True |
| Screen capture | Unavailable | Disabled by default; --allow-screen-capture or VIXL_ALLOW_SCREEN_CAPTURE=1 | Explicit screen-capture workflow | Explicit screen-capture workflow |
| Jobs | Detached timed-out calls via /jobs; no durable workflow queue | Durable workflow queue and detached calls | Durable workflow queue | Durable queue via Session/workflows |
| Authentication | Optional bearer token; required beyond loopback | stdio: OS process access; HTTP: bearer token required beyond loopback | OS process access | Caller controls access |
| Per-call limits | Configurable timeout, megapixels, pages, concurrency | Configurable timeout, megapixels, pages, concurrency | Resource Limits; service flags for serve/view/mcp | Resource Limits; CallLimits for service builders |
<!-- interface-capabilities:end -->

The workflow row is generated from the same allow-list enforced by REST and the shared workflow registry. The provider-backed MCP tools run as a second server (`--tools ai`), and screen capture requires its own opt-in. Service timeouts detach work into a job; they do not terminate the computation. Limits are opt-in unless configured in the environment.

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

`Project.apply(operations, *, dry_run=False, detail="full", check=None, validator=None)`: `check` means what it means
in MCP `vixl_apply`: `check=True` (or a check name or a list of names) runs the design check on the result and attaches
it as `result["check"]`, with an `outcome`. `validator` is a function called with each validated operation before the
batch runs; it raises `VixlError` to refuse one (the services pass their path and font policy here). A function passed
as `check` is an error that names `validator=`. A file an operation cannot read raises `VixlError` (`not_found` or
`io_error`) naming the operation's own `path`, not a raw `OSError`.

`Project.import_image(path=None, *, url=None, data=None, name="image", credit=None, license=None)` embeds an image from a file, bytes or an `https://` URL as a new layer and returns its id, size, bounds, `asset` and `source` (see [Import existing artwork](#import-existing-artwork)).

`Project.save(path=None, *, overwrite=False, prune_fonts=False)` writes the document. Saving to the file it was loaded from or last saved to always works; another existing `.vixl` is refused with `output_exists` unless `overwrite=True`, as `vixl new`, `vixl save` and exports do. `prune_fonts=True` first unregisters fonts no revision draws and leaves their files out, keeping undo history (`Project.prune_fonts(dry_run=True)` reports what would go; see [commands](commands.md)).

`Project.bounds(target, space="canvas")` returns a layer's `(x, y, width, height)` on the canvas, through the groups it is in (the box around a rotated outline), the same as `inspect()`'s `canvas_bounds`; `space="parent"` gives it in its parent group's content coordinates (`resolved_bounds`).

`Project.render()` returns a Pillow RGBA image; `Project.render(region=[x, y, width, height])` returns that crop (whole pixels inside the canvas), drawing only that part unless something in the document reads the whole canvas. In a notebook a `Project` displays as its rendered PNG, and `Project.show(page=None, region=None)` returns the image (optionally one page, cropped to `[x, y, width, height]`). `Project.export()` returns encoded bytes, optionally writing to a path. `Project.inspect()` returns an independent JSON-serializable state description. History methods: `undo`, `redo`, `branch`, `checkpoint`, `checkout`, `begin`, `commit`, `rollback`.

Loading does not implicitly trust linked image paths; use `allow_linked=True` only when those local file references are intended. Direct Python APIs are trusted local APIs and can import files. Exceptions expose `VixlError.code`, `.details`, and `.as_dict()`.

## REST

```bash
python -m pip install -e '.[server]'
vixl -p poster.vixl serve
```

Default binding is `127.0.0.1:8765`. OpenAPI is at `/docs`. To bind beyond loopback, configure a bearer token with `VIXL_API_TOKEN` and use `--host 0.0.0.0`. `--token-env NAME` selects a different environment variable. A token must be at least 24 characters (generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`); a shorter one is refused at startup. After 20 failed bearer tokens from one client address within 60 seconds, that address gets `429` with `Retry-After` until the oldest failure is a minute old, and its tokens are not compared meanwhile. A configured token protects all document APIs, including docs. `/view` is exempt: it serves a static, empty HTML shell, and every data call it makes needs the token. Without a token, host-header validation restricts requests to loopback names. This is a local single-user service, not a multi-tenant hosted product.

The token travels in a header, so a remote bind over plain HTTP sends it in cleartext; `serve`, `view` and `mcp --http` print a warning on stderr when they bind beyond loopback without TLS. Put a TLS reverse proxy in front, or pass `--tls-cert CERT.pem --tls-key KEY.pem` to serve HTTPS directly. `--offline` (also `VIXL_OFFLINE=1`) turns off every network access the server could make on its own: URL imports, font downloads and AI providers answer `network_disabled` (see [network access](architecture.md#trust-and-security)).

| Route | Request / result |
| --- | --- |
| `GET /document` | Inspected state |
| `GET /layers` | Layer list |
| `GET /schema` | Canonical operation batch JSON Schema |
| `POST /operations` | `{operations: [...] or operations_path: "ops.jsonl", dry_run: false, detail: "compact", check?, suites?, repair?, preview?}` → change summary (use `full` for snapshots); `check`/`suites`/`repair`/`preview` as for `vixl_apply`, the preview as `preview_base64` (and each region crop as its own `preview_base64`) |
| `GET /render` | PNG bytes |
| `POST /render` | `{variables: {title: "Hello"}}` → PNG bytes |
| `POST /validate` | `{profile: "instagram-post", rules: [...]}` → checks |
| `GET /history` | History graph and named references |
| `POST /history/{action}` | `{ref: "name", count: 1}`; undo/redo/branch/checkpoint/checkout/begin/commit/rollback |
| `POST /assets?name=photo` | Raw image bytes → imported layer; or an empty body with `url=https://…` to download one. `credit` and `license` are recorded in provenance |
| `POST /ai/{command}` | `{args: ["--prompt", "forest", "--provider", "local"]}`; uses locally configured providers |
| `POST /compose` | `vixl_apply(create=…)` fields without `path`, `exports` or `operations_path` → a dry run: steps, findings, `preview_base64` |

```bash
curl http://127.0.0.1:8765/document
curl -X POST http://127.0.0.1:8765/operations \
  -H 'Content-Type: application/json' \
  -d '{"operations":[{"type":"move","target":"logo","x":20,"y":40}]}'
curl http://127.0.0.1:8765/render -o preview.png
```

REST sessions fix the project path when launched. Operation `path` and `linked` fields are rejected (SVG path data on `shape`, `paint`, `text-layout` and `select` is allowed), and `font` accepts only a registered font name or role (`heading`, `body`), never a file; import image bytes with `/assets` and fonts with `/fonts` or `font install`. Services do not enable third-party plugins or linked-file reads. Local AI configuration is trusted, and services can invoke it. Do not share API access with users who should not be able to use your configured AI service. Authentication is all-or-nothing; there are no per-user roles or quotas, but a shared server can bound every call (see [per-call limits](#per-call-limits)).

## MCP

The Windows installer includes MCP. The Python base package includes MCP. Give Vixl an existing workspace directory that contains the images/documents the model should edit:

```powershell
vixl mcp --workspace "C:\Users\you\Pictures\Vixl"
```

The workspace can start without any `.vixl` documents. MCP defaults to stdio using the official SDK; stdout contains protocol messages only. Configure your client to start it (escape Windows backslashes in JSON):

```json
{
  "mcpServers": {
    "vixl": {
      "command": "vixl",
      "args": ["mcp", "--workspace", "C:\\Users\\you\\Pictures\\Vixl"]
    }
  }
}
```

Several agents sharing one server (common with subagents of one session) are the usual source of mistakes: see [several agents on one server](#several-agents-on-one-server) for `--require-document` and per-client documents.

If the client cannot find `vixl` on PATH, use the absolute executable path, normally `%LOCALAPPDATA%\Programs\Vixl\bin\vixl.exe` (`C:\Users\you\AppData\Local\Programs\Vixl\bin\vixl.exe`) for the Windows installer. Restart the client after installing/updating or changing its configuration. On macOS/Linux, use your installed `vixl` executable and a workspace such as `/home/you/Pictures/Vixl`.

### The tool surface

`vixl mcp` serves seven tools in about 7,700 characters of tool list (51 tools and 67k characters before 0.27):
`vixl_document`, `vixl_apply`, `vixl_check`, `vixl_render`, `vixl_export`, `vixl_reference` and `vixl_job`. Each
advertises a few typed fields plus `options`; the exact fields of every operation, every action's options and the
long explanations come from `vixl_reference`, and a validation error returns the schema it failed. An argument a tool
does not advertise is folded into `options` and validated against the chosen action, so `vixl_render(max_width=200)`
and `vixl_render(options={max_width: 200})` are the same call. See
[MCP tool surface](mcp-toolsets.md) for the design, the measurements and the ratchet that keeps it from growing.

### Two servers: design and AI

`vixl mcp` serves the design tools; `vixl mcp --tools ai` serves the provider-backed tools (`vixl_ai_*`,
`vixl_models_list`) plus `vixl_document`, `vixl_render` and `vixl_job`, so the AI server can find layers and check its
results (`--planner` adds `vixl_ai_plan`).

```json
{
  "mcpServers": {
    "vixl": {
      "command": "vixl",
      "args": ["mcp", "--workspace", "C:\\Users\\you\\Pictures\\Vixl"]
    },
    "vixl-ai": {
      "command": "vixl",
      "args": ["mcp", "--workspace", "C:\\Users\\you\\Pictures\\Vixl", "--tools", "ai"]
    }
  }
}
```

Give both the same workspace. Every edit is saved immediately and each server reloads a document that changed on disk (writes are serialized with file locks), so an image generated through `vixl-ai` appears in `vixl` on its next call. AI tools take `document=` or use the document opened with `vixl_document(action='open')`. Leave out `vixl-ai` when no AI provider is configured.

Existing `vixl --project /absolute/path/poster.vixl mcp` configurations still work: they open that document and use its parent directory as the workspace. You can also pass `--workspace` explicitly; the starting project must be within it. Without `--workspace` or `--project`, `vixl mcp` uses the folder of the document `vixl open` remembered, and refuses (`unsafe_workspace`) when that folder is your home folder or a filesystem root; a Python `Session()` with neither a path nor a workspace refuses the same folders as its current directory. The server prints its workspace on stderr when it starts.

### Tools and workflow

Vixl is designed to be driven mainly by agents. The intended loop is: create or open a document → `vixl_apply` in atomic batches (use `dry_run` to test) → `vixl_check` to find problems without looking → `vixl_render` (with `region` to zoom) → fix → `vixl_export`. For a new piece whose content is known, `vixl_apply(create={…})` runs that whole chain in one atomic call. `vixl_reference()` returns this loop step by step.

| Tool | Actions | Purpose |
| --- | --- | --- |
| `vixl_document` | `inspect` (default), `create`, `open`, `close`, `list`, `history`, `undo`, `redo`, `checkpoint`, `checkout`, `branch`, `begin`, `commit`, `rollback`, `compact`, `notes` | `create` makes and activates a `.vixl` from a named `size`, `width`/`height`, a `purpose` (else 1080×1080) or a `template` (with `variables`); creates missing directories; refuses overwrites. Like every surface it rolls and stores `design_defaults`, uses the palette background unless `background` is given (transparent for logos, icons and favicons), and embeds the workspace default fonts from `brand.json` (`workspace_fonts`) or else records the rolled pairing, which the first batch with text installs from the font cache or network; the result names the size, background and fonts chosen and why (see [Safe variety](../guides/layout/safe-variety.md#new-documents)), and `verbose: true` adds the whole rolled direction. `inspect` gives the canvas and one line per layer with resolved `[x, y, w, h]` bounds (`verbose`: every stored field; `object`: one object's tree). `list` shows workspace paths and the open documents. `history` lists revisions newest first; `compact` discards undo history and drops unused embedded files (`dry_run` first). `notes` lists, adds (`text`) or resolves (`resolve`) human review notes. |
| `vixl_apply` | a batch, `create={…}`, `workflow=ACTION` | Atomic edits: `operations` inline or `operations_path` (a workspace `.json` array or `.jsonl` file, errors cite the line). Items are operations or session steps (`import-image` from a workspace file, base64 bytes or a public `https://` URL with `credit`/`license`; `import-document` for SVG, a PDF page or a Figma file; `import-font`; `font-pair`; `font-install`; `style-use` for a catalog style; `roll`), all applied to one candidate that is saved only when every item succeeded. Every result has an `outcome` ([outcome states](agent-trust.md#outcome-states)) and, when there are any, `warnings` and `normalized`; `detail` is `brief` (default), `compact` (or `verbose`) or `full`. `check` (true or check names) adds a `check` block listing every `fix` finding, every composition finding and the findings on the touched layers (at most 20; `omitted` counts the rest) and `regions`, the two weakest regions; `suites` runs the document's check suites; `repair` applies the built-in repair map; `preview` (true or `{page, region, max_width, max_height, time, isolate, overlay, focus, regions}`) adds a PNG and, with `check`, real-size crops of the regions. All of them also work with `dry_run`, and are skipped with a `review_skipped` note when the edit took more than half the inline wait (40 s unless [set](#per-call-limits)). `create` builds a new piece ([below](#build-a-piece-in-one-call)); `workflow` runs a production action with its `request` ([production](../guides/automation/production.md)). |
| `vixl_check` | `design` (default), `validate`, `measure`, `spacing`, `spatial`, `pixels` | `design` finds problems without looking: findings carry a stable `rule`, `layer_ids`, `measured` actual versus expected, a `severity`, an `action` (fix, review, informational) and for fix findings a suggested `repair` (canonical operations, applied only with `repair=true`); `offset`/`limit` page them; `profile` picks checks and suites; waivers are reported as informational ([diagnostics](agent-trust.md#actionable-findings), every check in `vixl_reference('checks')`). `validate` runs rules and saved suites against a profile; `measure` samples rendered colour, channel statistics and contrast; `spacing` is a pass/fail equal-gap check; `spatial` answers relations, gaps, alignment, margins, guide offsets, hit tests, free regions and snap operations; `pixels` shows a pixel layer as character rows. |
| `vixl_render` | `preview` (default), `compare`, `timeline`, `timeline-inspect`, `animation`, `animation-inspect` | A bounded preview-resolution PNG: `region` zooms (up to 8×), `page`, `time` (a timeline frame), `proof` (CMYK soft proof), `simulate` (colour-vision deficiency), `isolate` (one object on the canvas background, zoomed to its ink), `overlay` (runs `vixl_check` and outlines each fix finding). `compare` shows two revisions side by side or as a red diff, plus the changed region. `timeline` gives one frame or a contact sheet of keyframed motion and `timeline-inspect` its tracks; `animation` and `animation-inspect` do the same for saved frames (sprites, pixel art). |
| `vixl_export` | `file` (default), `batch`, `animation`, `timeline`, `audio`, `icons`, `character` | Full-resolution PNG, JPEG, WEBP, TIFF, AVIF, SVG, PDF, ICO, HTML, PPTX or PSD (format from the extension), CMYK for print, or the document's drawn font as TTF, OTF or WOFF ([making a font](../guides/text/custom-fonts.md)); returns file metadata only ([formats](../guides/output/exporting.md), `vixl_reference('exports')`). `batch` writes several files (`targets`, `defaults`); `timeline` and `animation` write GIF, APNG, WebP, MP4/WebM, sprite sheets or PNG ZIPs; `audio` mixes the audio tracks to WAV; `icons` writes a favicon/Apple/Android/Windows set into a folder; `character` saves one character library. The kind follows the extension and the document unless given. |
| `vixl_reference` | topics `start` (default), `guide`, `operations`, `workflows`, `capabilities`, `sizes`, `layouts`, `fonts`, `brushes`, `styles`, `looks`, `color`, `roll`, `palettes`, `templates`, `guidance`, `objects`, `house-style`; or a tool name with actions (all but `vixl_job`), a kind of work, a guidance name (`checks`, `exports`, `batches`, `testing`, `finishing` …) or a free-text brief | The start-here recipe; what to make for a kind of work or free-text brief (approach, operations, layouts, looks, styles, an example, motifs); exact operation schemas (`name=[types]`); a tool's actions and options; catalogs of sizes, layouts, typefaces and pairings, brushes, styles, looks, palettes, templates and object kinds; colour tools; a rolled direction; every guidance text. Text that is not a topic is looked up as a kind, then a guidance name, then matched as a brief. |
| `vixl_job` | `status`, `result`, `cancel`, `list` | Follow a long call; see [long calls](#long-calls-retries-and-progress). |

`vixl_reference('operations', name=[…])` returns each operation's one-line `description`, every field with a JSON type and a description,
and `examples` for the common ones (gradients, glows, shadows, radial repeats, layouts, palettes …). `tools/list` stays lean: it carries
types and constraints only.

Every document tool accepts an optional `document` path. Up to 8 documents stay open per server; addressing one with `document` does not change the active document. When several documents are open, a call without `document` is refused with `ambiguous_document` unless the active document unambiguously belongs to the calling connection (see [several agents on one server](#several-agents-on-one-server)). Every result names the document it acted on (`"document": "poster.vixl"`; previews add a text line after the image), so a call that landed on the wrong document is visible.

For example, create `poster.vixl` at 4000×3000, import `photo.jpg` as `photo`, apply `[{"type":"move","target":"photo","x":20}]`, run `vixl_check`, request a preview, then export `poster.png`. File paths refer to the machine running Vixl; a client without access to that file system can send image bytes with `data_base64` instead.

Relative and absolute paths are accepted within the workspace. Paths escaping it, including symlinks to outside directories, are rejected. Export refuses existing files unless `overwrite: true` is supplied; a `.vixl` destination is accepted only for a portable object document (`isolate`). `vixl_document(action='create')` (also with a template) and `vixl_export` create missing directories inside the workspace (nothing outside it is ever created). Operation `path` and `linked` fields remain unavailable (checked after alias normalization); use an `import-image` step. `font` (and `display_font`, rich-text span fonts and `font=` in rich-text Markdown) is accepted in `vixl_apply` batches: a font registered in the document (`font-pair`, `font-install`, `import-font`, or a `font-register` earlier in the same batch) or a role. A file path or an unregistered name is refused with `forbidden`/`missing_font`, listing the registered names and the install tools. Services do not enable third-party plugins or linked-file reads.

### Build a piece in one call

When the agent already knows the size, the layout and its copy, the look and the operations, `vixl_apply(create=…)` replaces
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
inside the workspace and URLs go through the same fetch policy and byte and pixel limits as `import-image`; the
layout step lists what it embedded under `imported` (path or url, sha256). A `background` is kept when a layout runs:
it becomes the layout's background role, with the text and accents chosen to read on it (`transparent` keeps the
layout from painting one); a layout's own `colors.background` or `transparent` wins. A `style` shapes what the call
leaves open: the alignment its text-align rule asks for, its first palette (unless the workspace brand sets one), a
dark mode when it asks for a dark background, and, without `font_pairing`, workspace fonts or a layout `font`, its
first font pairing (a pairing that cannot be downloaded is noted under `fonts` and the call goes on). The layout step
reports these under `from_style`, so `check` with the style's rules passes on the result.

The steps run in that order on an unsaved document. The `.vixl` is written only when every step succeeded and the
exports only after it; a failed export removes the document and the files the call wrote. Export targets (the
`vixl_export(kind='batch')` options) are validated before anything is built, so an existing file fails at once. An error keeps
the normal schema (`error`, `message`, `field`, `operation_index` …) and adds `step`: `request`, `create`, `fonts`,
`layout`, `style`, `look`, `operations`, `check`, `preview`, `save` or `export`. `strict: true` turns `fix` findings into
a `check` failure (nothing saved); `dry_run: true` builds, checks and previews without writing (`path` optional). The
result lists `steps`, the layout's seed, blanks and notes, the check findings, the saved `document` and the `exports`,
followed by the preview image. Like `vixl_document(action='create')`, a saved compose makes the new document the active one
(`active_document: true`); when another document was active, a warning names it, since later calls without
`document=` now edit and export the composed piece. Like other heavy tools it becomes a job after ~40 s (or at once with `as_job`) and takes
`request_id`.

The same request works as `vixl compose --request req.json [--preview p.png]`, as `vixl.compose.run(workspace, **request)`
in Python, and as `POST /compose` on REST, where it is a dry run (no `path`, `exports` or `operations_path`: that server
serves one fixed document) returning the findings and `preview_base64`.

### Forgiving input and actionable errors

Model-written operations are normalized before validation, the same way in every interface, and each rewrite is reported under `normalized` in the result so the agent learns the canonical form:

- type and key spellings: `rect`/`circle`/`triangle` (→ `shape`), `add-text`, `drop_shadow`, camelCase and kebab-case keys, `font_size`, `fill`/`color`, `layer`/`layer_id` → `target`;
- values: opacity is 0–1 everywhere and `"70%"` is read as 0.7 (a bare `70` is an error suggesting both spellings); CSS `rgb()`/`rgba()` with 0–1 alpha, and with channels outside 0–255 clamped as CSS does (`rgb(300, 0, 0)` → `#ff0000`); style setting aliases (`offsetX` → `dx`);
- geometry: `x`/`y` accept `"center"` and `"N%"`, `width`/`height` accept `"N%"` (of the canvas, or of the parent group);
- layers: `targets` with one entry on a single-layer operation → `target`; a lone `target` on `group`/`distribute`/`pathfinder` → `targets`.

Errors are JSON: `{"error", "message", "field", "operation_index", "operation_type", "allowed"?, "suggestions"?, "fields"?, "schema"?, "expected"?}`. Unknown layers suggest close (including case-insensitive) names and list available ones; unknown fields, enum values and operation types get did-you-mean suggestions; a failing batch names the operation that failed. The whole batch is validated before anything runs, and every invalid operation is reported in one error: the top-level fields describe the first, `errors` lists each (`operation_index`, `operation_type`, `field`, `message`, `suggestions`, at most 50), `error_count` counts them, and `message` lists them all (MCP, REST and the CLI's `ERROR:` line show the same list; `dry_run` too). Errors raised while the batch runs stop at the first. A schema error ends with `(see vixl_reference('operations', name=['shape']))`; over MCP `schema` holds the exact schema of each failing operation type (up to three) instead of that hint, `fields` lists the accepted field names and, for a wrong type, `expected` holds the field's schema. Unknown fields are rejected, never silently accepted.

A call that succeeds can still carry `warnings` (a list of strings) about the layers it changed: text or artwork cut off by the canvas edge (a small bleed is ignored), text that does not fit its `text-layout` box or spills out of its group, and valid fields that change nothing for that operation (`radius` on a plain rectangle, `angle` on a non-angled gradient, `start`/`end` next to `stops`, `stroke_width` without `stroke`). Unknown fields and invalid values are errors, never warnings. Warnings only concern the layers of that call; `vixl_check` is the complete audit. An argument the tool does not take is never silently dropped. On the six tools with `options`, an argument that is not one of the chosen action's parameters (`detial="full"`) fails with `invalid_arguments`, the closest name (`did you mean 'detail'?`) and that action's schema; on `vixl_job` and the `vixl_ai_*` tools the result gets a warning naming the argument and the closest parameter (image tools add a text line after the picture).

### Small responses and previews

Tool results are minified JSON text with no duplicated structured copy, and terse by default: a new document reports its path, canvas, seed and the fonts chosen rather than the whole rolled direction (`verbose: true` on `vixl_document` and on a `vixl_apply` batch returns the full result). Advertised schemas omit pydantic titles and collapse optional fields; operation fields and rarer options come from `vixl_reference`. The provider-backed planner (`vixl_ai_plan`) is served only by `vixl mcp --tools ai --planner`, because the calling agent already plans its own edits.

The default `detail: "brief"` apply response over MCP returns, per stable layer ID, only what the caller cannot already know: new layers as `added`/`name`/`type`/`bounds` (plus a shape's `content_bounds`, and a text layer's `ink_bounds` and `baseline` so text can be aligned without another call), changed layers as the list of changed field names plus their resolved `bounds`, removals, `warnings` and `normalized`; state other than layers is listed by name under `also_changed`. Numbers are rounded to 2 decimals. Brief lists at most 25 added layers and 50 changed and 50 removed layers; the rest are counted under `changes.layers_omitted`, `changed_omitted` and `removed_omitted` (`{count, by_parent, sample, more}`), and per-layer `defaults` records past 25 under `defaults_omitted`, so a 1,000-layer batch returns about 6 KB instead of 440 KB. The other text metrics (`line_bounds`, `baselines`, `ascent`, `descent`, `cap_height`, `x_height`) come from `detail: "compact"` or an inspect. `detail: "compact"` (the REST/CLI default) returns the **new** values of changed fields and the main content of new layers; `detail: "full"` returns before/after snapshots. Python's `Project.apply` accepts all three. `vixl_check(action='measure')` summarizes channels as percentiles unless `histogram: "full"`.

Preview defaults: **1024×1024 maximum and 1 MiB of encoded PNG data** for `vixl_render` (a `vixl_apply` preview defaults to 512 px wide and is capped at 512 KB), preserving transparency and aspect ratio. Previews render a geometrically scaled copy of the document (JPEG sources decode at reduced scale), so a 24-megapixel document previews in a fraction of a second. Every layer edge (and every copy of a `repeat`) lands on a whole preview pixel, so layers or tiles that meet in the full render still meet in the preview and no seam appears between them; documents with canvas-sized effect selections fall back to a full render. `region: [x, y, w, h]` (pixels or percentages) zooms into part of the canvas. File export always uses full resolution unless a scale/profile is requested.

### Long calls, retries and progress

An MCP client typically gives up on a call after about 60 s, while the server still finishes the work and saves it. Vixl runs every tool call in a worker thread (a slow render no longer blocks other calls or the heartbeat) and turns a slow call into a job:

- **Automatic jobs.** A call that is still running after `VIXL_MCP_INLINE_SECONDS` (default 40, `0` disables; `--call-timeout` or `VIXL_CALL_TIMEOUT` replaces it, see [per-call limits](#per-call-limits)) returns `{"status": "running", "job": "job_…", …}` while it carries on. Poll with `vixl_job`. `vixl_render` answers inline and is never turned into a job.
- **Under load.** Calls run on `VIXL_MCP_WORKERS` threads (default 32). When more calls are in flight than there are workers, a new call waits proportionally less (inline seconds × workers ÷ calls in flight, at least 2 s) before it becomes a job, so a call stuck behind others is not lost to a client timeout. Job pointers and `vixl_job` report `queued` (still waiting for a worker), `wait_ms` (time spent waiting for a worker) and, in pointers, `queue_depth` (calls waiting).
- **`as_job: true`** on the heavy tools (`vixl_apply` with its batches, steps, `create` and workflows, `vixl_check`, `vixl_export`, the `vixl_ai_*` tools) starts the call as a job and returns its id at once.
- **`vixl_job(action, id, wait)`:** `status` reports `queued`/`running`/`completed`/`failed`/`cancelled` with `progress` (`wait=20` blocks up to that many seconds, at most 50, so one call replaces a polling loop); `result` returns the call's normal result under `result` (or `error`); `cancel` stops a queued job, or a running one at its next checkpoint (a batch of operations is atomic, so a cancelled batch changes nothing; timeline exports stop between frames); `list` shows recent jobs, including calls that timed out on your side. The server remembers the last 100 jobs in memory; durable workspace jobs from `vixl_apply(workflow='submit')` use the same tool with their 32-character ids.
- **Retries: `request_id`.** The mutating tools (`vixl_document`, `vixl_apply`, `vixl_export`, the AI tools) accept an optional `request_id` (1–64 characters). Repeating a call with the same id returns the first call's recorded result with `"replayed": true` instead of applying twice; if the first call is still running, the repeat waits briefly and then points at its job. An id reused with different arguments is an error (`request_id_conflict`), and a call that failed is not remembered, so its retry runs. The store keeps the last 64 ids per document (512 overall), in memory.
- **Progress.** A client that sends a progress token receives `notifications/progress` while operation batches (one tick per operation), timeline exports (one per frame) and batch exports (one per file) run. Once a call has become a job, read its `progress` with `vixl_job`; a timeline export's progress also has `timing`: `elapsed_s`, `eta_s` (estimated seconds left) and the last frame's `setup_ms` (sampling the timeline) and `raster_ms`.
- **Profiling.** With `VIXL_PROFILE=1` in the server's environment every JSON result carries a `render_profile` (per-layer draw times, cache hits, misses and writes, incremental renders; see [troubleshooting](../troubleshooting.md#find-out-why-a-render-is-slow)); an image result gets it in the text note after the picture. The REST server adds it to JSON bodies and, summarised, to the `X-Vixl-Profile` header of every response. Both servers keep a document's render caches when they reload it after it changed on disk.

Recommended pattern for agents: send heavy calls with a fresh `request_id`; if one times out or returns a job, call `vixl_job(action="result", id, wait=30)` (or `list` when you never saw the id) instead of resending, and resend with the same `request_id` only if the result says it failed.

### Per-call limits

A server shared by several people or agents can bound what one call may cost, so one oversized render cannot starve the rest. `vixl serve`, `vixl view` and `vixl mcp` take the same flags (or environment variables). A server other machines can reach (`serve` or `view` with a non-loopback `--host`, and `mcp --http`) starts with defaults: a 120 s timeout (REST only; MCP keeps its 40 s inline wait), a 600 s hard timeout, 40 megapixels, 200 pages and as many concurrent heavy calls as the machine has cores (at least 2). A loopback `serve`/`view` and a stdio `mcp` limit nothing unless one is set. A value of `0` turns one limit off, and `--no-call-limits` drops every default:

| Flag | Environment | Limit |
| --- | --- | --- |
| `--call-timeout S` | `VIXL_CALL_TIMEOUT` | Seconds a call runs inline. A REST call still running then answers `202` with `{"status": "running", "job", "poll", "result_url"}` and a `Location` header; `GET /jobs/{id}?wait=20` reports `running`, `completed` or `failed` (with `error`), and `GET /jobs/{id}/result` returns what the call would have returned (the file, the JSON or the error; `409` while it runs). `GET /jobs` lists recent jobs. For MCP it replaces `VIXL_MCP_INLINE_SECONDS` (default 40). The call itself goes on. |
| `--call-hard-timeout S` | `VIXL_CALL_HARD_TIMEOUT` | Seconds after which a running call, detached or not, is cancelled: it stops at its next checkpoint (between layers, pages, frames, export targets and check families) with `cancelled` and a message naming the limit, and an operation batch is then not applied. A REST job reports `cancelled`. |
| `--max-megapixels N` | `VIXL_MAX_MEGAPIXELS` | Lowers the pixel limit (`--max-pixels`) for canvases, imports and frames to N million, and caps the pixels one export renders: canvas × scale² × pages written as images (vector PDF, SVG, PPTX and HTML count one page). |
| `--max-pages N` | `VIXL_MAX_PAGES` | Pages one export writes (a PDF, PPTX or HTML deck, or a contact sheet). |
| `--max-concurrent N` | `VIXL_MAX_CONCURRENT` | Heavy calls running at once per workspace, background jobs included: exports, renders, previews, checks, operation batches, compose, workflows and provider calls (MCP: the tools that take `as_job`). Inspection and catalog calls are not counted. |

A call over a limit is refused before it renders with `limit_exceeded` and its `limit` (`max_megapixels`, `max_pages` or `max_concurrent`), `value`, `maximum` and a `hint` (REST: status `413`, or `429` with `Retry-After` for concurrency). REST runs heavy calls on 16 worker threads with at most 16 more waiting; the next one gets `503` with `Retry-After` and `limit: max_queue`. `GET /limits` (REST) and `vixl_job(action="list")` (MCP, under `limits`) report the values a server runs with and, under `source`, where each came from (a flag, an environment variable, `default` or `unset`); `GET /limits` also reports the network policy under `network` (`offline`, `fetch_hosts`, `private_addresses`, `proxy_resolves`).

```bash
vixl serve --call-timeout 30 --call-hard-timeout 300 --max-megapixels 50 --max-pages 40 --max-concurrent 2
```

### Several agents on one server

The server keeps documents loaded in one shared cache, but the **active document is per MCP client session**: with Streamable HTTP each connected client opens, creates and closes documents without moving anyone else's active document. A client session is a connection, not an agent: a stdio server has exactly one client connection, so subagents of one parent agent share one active document there, and MCP carries nothing that tells them apart. So a call without `document=` uses the active document only when it unambiguously belongs to the caller:

- A connection that has created, opened or addressed (with `document=`) **one** document that is still open uses it, whatever other connections have open.
- A connection that has touched **two or more** documents it has not closed gets no default: a call without `document=` is refused before it does anything.
- A connection that has chosen **none** gets the document the server was started with only while that is the only open document; with several open it is refused too.

```json
{"error": "ambiguous_document", "field": "document", "documents": ["infographic.vixl", "poster.vixl"],
 "message": "2 documents are open (infographic.vixl, poster.vixl) and this call did not name one. … Pass document= with the .vixl path you mean.",
 "suggestions": ["document='infographic.vixl'", "document='poster.vixl'"]}
```

Pass `document=`, or close documents with `vixl_document(action='close', document=…)` until this connection has one left. Closing the active document makes this connection's previous document active, never another connection's. Further safeguards:

- `vixl mcp --require-document` (or `VIXL_REQUIRE_DOCUMENT=1`) makes `document=` mandatory on every document tool: there is no active document to fall back to, and a call without it fails with `document_required`. `vixl_document(action='create')`/`open` still work and name the document in their result.
- Every result names the document it acted on (`document`), so a mistake shows up in the first response.
- Pass `document=` on every call, with `request_id` on mutating ones.

For many agents at once, run one `vixl mcp --http` server they all connect to (each gets its own active document and the calls share one worker pool and job store) rather than one stdio server per agent; raise `VIXL_MCP_WORKERS` when results come back as `queued` jobs. Calls on different documents run in parallel; calls on the same document wait for each other, so agents that work on separate documents do not slow each other down.

### Typed AI tools

These call your [configured providers](providers.md) with named fields, without CLI flags:

- `vixl_ai_generate(prompt, mode, width, height, seed, name, provider, model, negative_prompt, strength)`; mode is `generate`, `inpaint`, or `img2img`. Supply both dimensions or neither. Inpainting needs a selection.
- `vixl_ai_remove`, `vixl_ai_content_aware_fill`, `vixl_ai_select_subject`, `vixl_ai_remove_background(layer)` and `vixl_ai_select_object(label)`.
- `vixl_ai_analyze(capability, query, provider)`; capability is `describe`, `detect`, or `ocr`. Detections return `objects[].box` as `[x, y, w, h]` document pixels for every provider.
- `vixl_ai_upscale(layer, scale)`, `vixl_ai_regenerate(layer, prompt, seed)`, `vixl_ai_extend(prompt, left, right, top, bottom, seed, name)`.
- `vixl_ai_plan(prompt, apply)` only with `vixl mcp --tools ai --planner`.

Provider capability limits still apply. Local provider settings and credentials remain on the server. Layer provenance is available through verbose inspection (`vixl_document` with `target` and `verbose: true`, or `vixl ai info LAYER`). `vixl_models_list(provider, capability, refresh)` lists the models a configured provider offers.

### Session performance and consistency

REST and MCP retain loaded projects between calls. A file fingerprint (identity, size and high-resolution modification/change times) triggers a fresh load when an external edit is detected. Edit candidates share immutable history and the content-addressed render and decoded-image caches, so an edit costs roughly the same at revision 10 or 2,000. Thread and interprocess locks serialize edits; saves retain optimistic revision checks and atomic replacement, and store image assets without recompressing them. Failed edits, provider calls or saves discard the cached instance before the next access.

### REST additions

`POST /check` (same options as `vixl_check`; `sample` is `"worst"` or a CSV path inside the workspace, and a path outside it answers `403 forbidden`), `POST /preview` (`max_width`, `max_height`, `max_bytes`, `region`, `isolate`, …; returns PNG) and `POST /compare` (`before`, `after`, `mode`, `isolate`; returns the summary plus `image_base64`). The CLI takes `--isolate LAYER…` on `compare` and on `apply --preview`. The REST service is bound to its one document and rejects a `document` field. `/check`, `/measure` and `/spacing`, like `/export`, `/preview` and `/compare`, answer `400` for a field they do not read and name it.

The remaining routes mirror `vixl_check` and the saved-frame tools: `POST /measure` and `POST /spacing`, `GET /pixels/{target}`, `GET /animation`, `GET /animation/frame/{name}` and `POST /animation/export`; `GET /workflow/schema` and `POST /workflow/{action}` serve the fixed-document workflow allow-list shown in the [capability matrix](#capability-matrix); `GET /typefaces`, `GET /typefaces/pairings`, `POST /typefaces/pair`, `POST /typefaces/install` and `GET /roll` cover fonts and a rolled direction; `GET /limits` and `GET /jobs` report the [per-call limits](#per-call-limits) and detached calls.

## Trusted extensions

Installed Python packages can register entry points:

```toml
[project.entry-points."vixl.filters"]
my_filter = "my_package:filter_image"
[project.entry-points."vixl.providers"]
my_provider = "my_package:Provider"
```

A filter receives `(rgba_image_copy, effect_dict)` and returns a same-size Pillow RGBA image. Provider classes accept `(provider_name, configuration)` and expose `invoke(capability, request) -> dict`; see the HTTP gateway contract for request/result shapes. The provider instance exposes `.name`.

Enable plugins explicitly with `vixl --plugins ...` or `vixl.plugins.enable_plugins()` in Python. Plugins are trusted Python code with the user's process privileges; they are **not sandboxed**. No plugin is imported from a project archive. Trusted operation producers and declarative resource packs are described in [studio.md](../guides/automation/studio.md). Codec, layout, validator, and asset-source entry-point categories remain future work; built-in Pillow codecs and the current validator/layout engine cover those functions today.

## New agent resources (0.11)

MCP reads resources with `vixl_reference` (`palettes`, `templates`, `guidance`, `objects`), saves them with `vixl_apply(workflow='resource-save')`, creates from a template with `vixl_document(action='create', template=NAME)`, imports fonts with an `import-font` step (a workspace `path` or an `https://` `url`), and lists provider models with `vixl_models_list` (in `--tools ai`). Resource discovery needs no open document. Font paths and document destinations remain workspace scoped. `vixl_export` accepts `.svg`; operations accept registered font names while service operations continue to reject filesystem font paths.

REST adds GET `/resources/{kind}`, GET/POST `/resources/{kind}/{name}` (POST body `{"value":...}`), POST `/fonts?name=brand` with raw TTF/OTF bytes (16 MiB maximum), and POST `/export` with options such as `{"format":"SVG"}`. Export returns bytes and accepts no destination path. Python exposes the matching `vixl.resources` and `vixl.fonts` helpers. [Detailed examples and boundaries](../guides/layout/agent-resources.md).

## Sizes, layouts, color, brushes and timelines (0.13)

All new editing features are ordinary operations, so `vixl_apply`, `POST /operations`, `Project.apply` and scripts use them directly. MCP adds the discovery (`vixl_reference`), timeline and icon actions listed above; `vixl_render` and `vixl_export` gain `time`, `proof`, `simulate` and print options. `icc_profile` is a workspace path in MCP.

REST adds `GET /sizes?category=`, `GET /layouts`, `GET /brushes`, `GET /guide?brief=`, `GET /styles?query=|name=`, `GET /looks`, `POST /color` (`{"action", "colors", "to"?, "scheme"?, "count"?, "amount"?, "space"?}`), `GET /timeline`, `GET /timeline/frame?time=1.5s` (PNG), and `POST /timeline/export` (`{"format", "fps", "scale", "start", "end", "background", "columns", "quality"}`; returns bytes). `POST /export` accepts `color_space`, `icc_profile_base64`, `intent`, `black_generation`, `ink_limit`, `proof`, `simulate`, `dpi`, `icon_sizes`, `time` and, for SVG, `svg_document` (`false` leaves the embedded Vixl document out), and formats `PDF` and `ICO`. `POST /preview` accepts `time`, `proof` and `simulate`.

Python: `Project.sized("letter", bleed=True)`, `project.export("flyer.pdf", color_space="cmyk", icc_profile=bytes)`, `vixl.colors` (parse, describe, harmony, scale, mix, contrast_ratio, simulate_vision, cmyk_image), `vixl.sizes` (resolve, catalog), `vixl.layouts.catalog()`, `vixl.brushes.catalog()`, `vixl.timeline` (project_at, render_at, contact_sheet, export_timeline) and `vixl.exports.export_icons`. A `project_at` frame shares the layers it does not animate with the document: treat it as read-only, or `clone()` it before editing (`prune=True` also leaves out top-level groups that draw nothing at that time). `vixl.profiling.profile()` records a render profile (`with profile() as run: …; run.report()`), and `vixl.render_cache` has `info()` and `clear()`.

<a id="pages-forms-drawings-and-lyric-videos-unreleased"></a>

## Pages, forms, drawings and lyric videos (0.19)

All editing is ordinary operations. MCP: `vixl_render` gains `page` (`"all"` for a contact
sheet), `values` and `show_fields`; `vixl_export` gains `page`, `pages`, `pdf_content`,
`fillable`, `values`, `fill_mode` and `presenter` and writes `.pptx` and `.html` presentations
(see [presenter](../guides/output/presenter.md)); `vixl_check` gains `page`, `deck`
settings, `sample`, and the `deck`, `form` and `drawing` families; `vixl_document(action='inspect')` lists
pages and fields. `vixl_apply(workflow=…)` adds `lyric-video-plan/build/export`, `organic-catalog`,
`form-fill`, `drawing-report` and `drawing-compare`; jobs add the `lyric-video` and `form-fill`
kinds.

PDF export is vector by default (also with `color_space="cmyk"`); the export result reports `content`, `content_reason`,
`color_space` and `page_size`, and `dpi` sizes PDF pages and PowerPoint slides alike. A PPTX result's `warnings`
name the fonts that are not embedded and must be installed where the deck is opened (`fonts_not_embedded`, with each one's fsType permission and license under `font_embedding`).

REST: `POST /export` accepts `page`, `pages`, `pdf_content`, `fillable`, `values`, `fill_mode` and
`presenter` (HTML slide presentation options) and formats `PPTX`, `PSD` (layered, see [exporting](../guides/output/exporting.md#layered-psd-for-designer-handoff)) and `TTF`, `OTF`, `WOFF`, `WOFF2` (the document's [font design](../guides/text/custom-fonts.md)); `POST /preview` accepts `guides`, `page`, `values` and `show_fields`; the fixed
project's workflow routes include `lyric-video-plan`, `organic-catalog`, `form-fill` and
`drawing-report`.

Python: `project.export("deck.pptx")`, `project.export("form.pdf", fillable=True)`,
`project.render(page=2)`, `vixl.forms.fill` / `fill_data`, `vixl.deck.check_deck` /
`contact_sheet`, `vixl.plugins.drawing.drawing` (`clean`, `report`, `compare`, `ai_color`), `vixl.plugins.lyrics.lyrics`
(`parse_lrc`, `plan`, `build`, `export`).

Linked documents and print merge are ordinary operations and one workflow action each: `link` (create, or change with a `target`),
`link-refresh` and `link-embed` go through `vixl_apply` / `POST /operations`; `vixl_apply(workflow='links', request={})` (also `POST /workflow/links`) lists
each link's state; `vixl_apply(workflow='merge-impose', request=request, document=template)` merges a CSV into print sheets (MCP and CLI only:
it writes files). Link sources and merge paths stay inside the workspace. See [linked documents](../guides/output/linked-documents.md) and
[imposition](../guides/output/imposition.md).

### Streamable HTTP and live review

```bash
# MCP over HTTP, for clients supporting a static Authorization header:
vixl mcp --workspace . --http --port 8766
# For a remote bind, set VIXL_API_TOKEN (24+ characters), then add --host 0.0.0.0.
# Connect to https://YOUR-HOST/mcp through your TLS reverse proxy, or add --tls-cert and --tls-key.

# Serve a fixed document and open its live viewer:
vixl -p poster.vixl view
# Or run `serve` and open http://127.0.0.1:8765/view yourself.
vixl -p poster.vixl notes list
vixl -p poster.vixl notes resolve NOTE_ID
```

HTTP MCP uses the official SDK's Streamable HTTP transport. Stdio remains the default.
HTTP and REST use `Authorization: Bearer TOKEN`, with `VIXL_API_TOKEN` (or `--token-env`)
and reject remote binds without it; the token rules and failure throttle are those of [REST](#rest). Use a TLS
reverse proxy (or `--tls-cert`/`--tls-key`) for remote access. OAuth discovery
is not implemented: clients that require OAuth, including some hosted connector setups, need
an OAuth-capable gateway. Each connected client has its own active document (see
[several agents on one server](#several-agents-on-one-server)); agents that share one stdio connection should
still pass `document` explicitly on every document tool (once a connection has several documents open, a call
without it is refused with `ambiguous_document`). Access covers the entire
configured workspace and any locally configured provider accounts.

The viewer polls once per second, showing the current PNG, layers, history, and review notes.
Only its empty HTML shell is public; document APIs require the token when configured. Enter
that token in the viewer; it is kept in memory, never placed in a URL or browser storage.
Notes persist in `DOCUMENT.vixl.notes.json`, separately from undo history. Agents read/add/resolve
them with `vixl_document(action='notes')`; CLI users use `notes list|add|resolve`. REST provides `GET /review`,
`GET /notes`, `POST /notes` (`{"text":"..."}`), and `POST /notes/{id}/resolve`.

### Import existing artwork

```bash
vixl -p poster.vixl import logo.svg
# Optional PDF dependency: pip install 'vixl-engine[pdf]'
vixl -p poster.vixl import flyer.pdf --page 1 --name flyer
vixl -p poster.vixl import flyer.pdf --page 1 --svg-mode appearance --dpi 144 --name reference
vixl -p poster.vixl import photo.jpg --name hero --credit "Photo: Ana Ruiz" --license "CC0"
vixl -p poster.vixl import https://images.example.com/cat.jpg --name cat --credit "Photo: Ana Ruiz / Unsplash" --license "Unsplash License"
```

MCP: an `import-document` step in `vixl_apply` (`format="svg"`, `path="logo.svg"`), with `data_base64` instead of `path` when there is no file.
REST: `POST /import?format=svg` with raw bytes (`name` and `svg_mode` are query parameters too, and so are `font_map`, repeated as `font_map=SRC=NAME` (or one JSON object), and `install_fonts` for SVG and PDF; an unregistered target fails with `missing_font` on `font_map`). PDF additionally accepts a one-based `page` (a non-numeric `page` is a 400); it imports the page
as editable layers (text, paths, images), or with `svg_mode=appearance` as one image at `dpi` (36–600).
Figma files import with `format=figma` (an `import-document` step with `source` set to the URL or file key, CLI `import URL --format figma`, Python `import_document(project, b"URL", "figma")`,
REST `POST /import?format=figma` with the URL or file key as the body, `page` (a name or number), `node_id` and `rasterize_unsupported` as query parameters) using `FIGMA_TOKEN` from the environment; see
[Import from Figma](../guides/images/figma.md).

Any other file, or an `https://` URL, is imported as an image layer, the same as
an `import-image` step with `url`, `POST /assets?url=…` and `Project.import_image(url=…)` in Python. A URL
download is HTTPS only, follows at most 5 redirects, refuses private, loopback and link-local hosts
and is size-capped; the bytes must decode as an image whatever the server's `Content-Type` says (see
[architecture](architecture.md#trust-and-security)). The layer's `provenance` records
`source: {url, fetched_at, sha256, bytes}`, plus `credit` and `license` when you pass them (also for
file and base64 imports, and the `add` operation's `credit`/`license` fields). Compact inspect shows
`source_url`, `credit` and `license`; `vixl dependencies` lists them under `attributions`. Use web
images only with the rights to do so (guidance `image-rights`).

An SVG Vixl exported comes back as the document it carries (same layers, names, text, groups and effects; see
[SVG round trip](../guides/output/exporting.md#svg-round-trip)). Other SVG becomes editable layers: shapes and paths with fills,
strokes, dashes, opacity and transforms, `<text>` as live text, `<g>` as groups, gradients, embedded images, `<use>`
and class stylesheets. With the default `svg_mode="editable"` an unsupported feature (filters, masks, clip paths,
patterns …) fails before changing the document; `"auto"` draws just those elements as image layers; `"appearance"`
renders the whole SVG as one image while retaining the source. UTF-8 SVG files are limited to 16 MiB (a Vixl SVG
carrying its document, 64 MiB) and existing document resource limits. See
[importing SVG and PDF](../guides/output/exporting.md#importing-svg-and-pdf) for the details and [studio.md](../guides/automation/studio.md) for appearance
input restrictions. Imports never fetch external resources. Element IDs (or `data-layer` names and Inkscape labels)
become layer names.

### Source folders, emoji, app packages and capture (0.24)

`vixl pack` / `vixl unpack` convert between a `.vixl` and a readable source folder; Python has the same `pack` and
`unpack` in `vixl.project_folder` ([commands](commands.md#reviewing-editable-projects-in-git)). The workflow actions
`emoji-list`, `emoji-get`, `emoji-template`, `emoji-settings`, `emoji-replace`, `emoji-pack-install`, `emoji-reset`,
`emoji-destinations`, `emoji-requirements` and `emoji-export` back the `vixl emoji` command ([emojis](../guides/text/emojis.md));
`app-animation-package` writes an app animation package ([animation authoring](../guides/motion/animation-authoring.md)), and
`screen-capture` captures the local desktop to PNG. They run through `vixl_apply(workflow=…)` and `vixl workflow ACTION`; the
REST workflow route, scoped to its one document, does not serve them.

### Consolidated studio workflows

`vixl_apply(workflow=…)` runs them over MCP. Workflow actions include resource-list/get/save, shape-save, suite-use, palette-check, effect-run, group-list/define/show/apply/recover, branch-list/fork/status/merge and plugin-list/install/remove. REST allows the resource/test/effect actions while retaining fixed-project scope. `vixl_export` and REST export support HTML. Full contracts and examples: [studio.md](../guides/automation/studio.md).

### MCP startup requirements

Vixl needs the MCP Python SDK `>=1.21.1,<2`. Startup reports `missing_dependency` with the installed version when the SDK is incompatible; install it with `pip install 'mcp>=1.21.1,<2'`.

MCP desktop capture is disabled by default. Start the server with `--allow-screen-capture` or `VIXL_ALLOW_SCREEN_CAPTURE=1` to enable it for that server; this grants connected agents access to the interactive desktop. Capture output paths are relative to the workspace. The Python `mcp_server` and `build_server` functions accept `allow_screen_capture=True` (or `False` to override the environment).

### Archive parsing budgets

`Limits(max_load_pixels=160_000_000, max_load_fonts=64)` bounds the aggregate image pixels decoded and
font assets parsed when opening a `.vixl`. Image headers and counts are checked before any image decode
or FreeType call; individual asset, dimension, archive-byte and checksum checks still apply. Trusted Python
callers can raise these limits explicitly. Documents exceeding a budget fail with `resource_limit` and the
limit field. Undo/redo deltas preserve object key order, avoiding serialization-only diffs.
