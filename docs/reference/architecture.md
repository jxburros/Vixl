# Architecture and operational boundaries

[Documentation home](../README.md) · [Getting started](../getting-started.md) · [Visual gallery](../gallery.md)

Vixl is a headless design engine for AI agents; people can drive the same interfaces.

```text
CLI / shell / scripts / Python / REST / MCP / AI planner
                         |
             schema + canonical operations
                         |
      atomic candidate document + state validation
                         |
        history snapshots + embedded asset store
                         |
   variables / constraints / Pillow + NumPy renderer
                         |
   PNG / JPEG / WebP / TIFF / AVIF / SVG / PDF / PPTX / PSD / HTML / motion
```

`project.py` owns document lifecycle, candidate-state commits, history and archives. `operations.py` changes document state; it has no dependency on CLI output. `render.py` converts state into pixels without changing it. `text.py` shares HarfBuzz/bidi shaping and font outlines between PNG (resvg rasterization) and SVG; `artistic.py` owns deterministic local treatments; `svg_effects.py` maps supported effects/styles to SVG primitives. `commands.py` compiles the human syntax; scripts use the same compiler. `ai.py` delegates inference to providers and inserts ordinary assets/masks. `interfaces.py` holds the cached project sessions and the REST service; `mcp_tools.py` builds the seven MCP tools, `mcp_actions.py` holds the typed actions behind them (their signatures are the option contract that `vixl_reference(TOOL)` serves), `mcp_runtime.py` runs each call in a worker thread with progress, retries and detaching to a job after the inline wait, `steps.py` runs the workspace steps (`import-image`, `import-document`, `import-font`, `font-pair`, `roll` ...) inside the same atomic batch as the operations, and `call_limits.py` and `calls.py` carry the per-call limits and context; `untrusted.py` names the result paths that hold document or provider text ([agent trust](agent-trust.md#untrusted-document-text)). `colors.py` parses the color language and performs CMYK separation, proofing and vision simulation; `sizes.py` holds the named-size catalog and canvas print metadata; `layouts.py` builds seeded, principled layouts from ordinary operations; `brushes.py` renders paint-layer stroke data; `timeline.py` samples keyframe tracks into render-only document copies and streams animation exports. `schema.py` publishes the operation contract. `validation.py` checks structures, design rules, and dependencies. `inplace.py` lets `shape`, `solid`, `gradient` and `text` edit a targeted layer in place; `stacks.py` resolves `hide_if_empty` text and auto-layout stacks while layers are resolved for layout, so every renderer, export and check sees the same collapsed layout. `links.py` renders linked `.vixl` documents live (cached by content hash, confined to the workspace, cycle- and depth-checked) and `imposition.py` merges a template and a CSV into print sheets (a PDF with vector text, and an editable sheet document of links); see [linked documents](../guides/output/linked-documents.md) and [imposition](../guides/output/imposition.md). `charts.py` lays data-bound charts out as ordinary vector layers and keeps them in step with their table; `chart_pptx.py` writes them to PPTX as native charts with an embedded workbook. `pathfinder_geometry.py` and `booleans.py` turn pathfinder layers into exact compound-path geometry (Bézier outlines split where they cross, pieces kept by inside/outside tests) for the SVG, PDF and PowerPoint exports; `pdf_export.py`/`pdf_writer.py` write vector PDFs and `pdf_color.py` separates their colours to DeviceCMYK. `house_style.py` reads the one house style (`data/house-style.json`) that sparse briefs fall back to; there are no house-style versions to replay. `composition.py` is the `composition` check family, `composition_repair.py` its repair candidates for `layout_repair.py`, and `critique.py` picks the weakest regions that `vixl_apply` returns with `check` and `preview`. `atmosphere.py` builds `haze`, `star-field`, `string-lights`, `bokeh` and `reflection`, `key_values.py` the aligned `key-value-list` (and chart value legends) and `scatter.py` the seeded scatter and `pattern-scatter` tiles; `finishing.py` is the single hook for looks, symmetry, scatter and styles. `emojis.py` holds the offline emoji art, document overrides and pack export. `project_folder.py` packs and unpacks deterministic, current-state source folders for Git review; `document_schema.py` generates the published JSON Schema of a `.vixl` file's `project.json` ([file format](file-format.md)); `imports.py` is the entry point for SVG, PDF and Figma imports (`import_document`, with SVG sanitizing and the one-image `appearance` mode), `svg_import.py`, `pdf_import.py` and `figma_import.py` read them as editable layers, and `image_import.py` holds the shared image imports (see [exporting](../guides/output/exporting.md#importing-svg-and-pdf) and [Figma](../guides/images/figma.md)); `cli_summary.py` prints the short terminal summaries (piped output, `--json` and `VIXL_JSON=1` keep the JSON); `convert/` is the conversion kit for documents and saved tool calls from earlier releases, which the engine never imports ([converting](converting.md)); `app_animation.py` builds app-animation packages with the timeline encoders; `screen_capture.py` captures the local desktop only when the `screen-capture` workflow asks, never while rendering or loading.

The implementation uses Python, Pillow, and NumPy to cover the complete editing/automation workflow with a reusable API. The specification's Rust-core recommendation is a future performance/distribution option, not the current implementation. Image operations are deterministic for a fixed document and imaging-library/font environment; random filters use explicit seeds. AI inference and provider availability are external.

## Persistence and concurrency

Production extensions: `assurance.py` owns saved, read-only design contracts;
`automation.py` compiles bounded actions and role-based motion to canonical operations;
`production.py` handles typed recipe snapshots, variant plans, manifests and component
libraries. `render_cache.py` supplies an optional persistent, bounded PNG cache keyed
by render inputs, font bytes and runtime versions. `film.py` assembles bounded shot
sequences; `jobs.py` persists workspace jobs and frozen inputs, with per-job worker
locks and cooperative cancellation. `workflows.py` is the shared CLI/MCP dispatcher;
REST exposes its fixed-project subset. See [production](../guides/automation/production.md).

New document fields (`suites`, `roles`, `motions`, `actions`, `recipe`) are optional,
validated on load and committed through existing history. Archives must be format 2;
`vixl convert` rewrites older documents once ([converting](converting.md)). Job, recipe, suite, library and production manifests carry their own v1
contracts. Raw provider credentials never enter these records. Scripts still cannot
execute shell/Python; reusable actions cannot rewrite check suites or recurse.

Parallel production uses independent document candidates, bounded worker counts and
staged output publication. It does not make concurrent edits to a shared project.
Recovery never assumes a timed-out external generation request was cancelled. Pollable
video gateways use durable IDs/client keys; uncertain synchronous image generation
requires review. Workers need restarting after process/machine termination.

A successful CLI editing command autosaves via a same-directory temporary file, `fsync`, and atomic replace. An advisory project lock serializes CLI and service read-modify-write cycles. Direct Python saves use an optimistic archive hash check to reject stale writes. A loader hashes the exact archive bytes it parses, preventing a concurrent replacement from being mistaken for the same revision.

History is a DAG of revisions. Each revision stores a structural delta from its parent, with a full snapshot every 32 revisions on a chain, so memory and file size grow with what changed rather than with document size × edits. Historical states are reconstructed, then validated, when a revision is restored. When `max_history` (2,000) is reached, the oldest revisions not referenced by the head, a branch, a checkpoint or the redo stack are squashed (their children become snapshots), so editing never stops. Font assets are ZIP-compressed; already-compressed images remain stored without recompression. Assets are content-addressed and shared; assets no remaining revision references are dropped on save. Open transactions preserve provisional state across commands, then commit as one history entry or restore the previous state. Transactions provide rollback, not isolation from other clients. Use separate projects or a single coordinating client for simultaneous independent editing.

## Resource policy

Defaults (`vixl.model.Limits`):

- 40 million pixels per canvas/layer; 16,384 pixels per dimension.
- 4,096 layers per document (per page in a multi-page document); 256 effects per layer. Lists of layer
  references (`targets`) take up to the same number. Earlier releases allowed 512 layers and refuse to open a
  document with more.
- 64 MiB per imported asset/provider response.
- REST request bodies: 1 MiB, or the asset limit for `/assets` and `/import` (16 MiB for `/fonts`). A larger
  `Content-Length` gets `413 resource_limit` before the body is read; a body without one is cut off at the limit.
- 256 MiB per archive and its expanded contents.
- 10,000 operations per submitted batch; 2,000 history revisions (older ones are squashed, not refused).
- At most 10,000 archive entries.
- Layer-render cache (layer images, composited groups and styled patches): 8,192 entries / 384 MiB, with entries under 96 MiB; rasterised-SVG cache (text and path shapes, shared by all documents in a process): 96 MiB; last-render snapshot: one canvas per document view, for canvases up to 40 million pixels; decoded-asset cache: 256 MiB; persistent disk cache: 256 MiB (`VIXL_CACHE_MAX_MB`), entries under a quarter of it.

Per-operation caps, each refused with `resource_limit` or `invalid_operation` naming the field:

| What | Cap |
| --- | --- |
| Nested groups (a layer inside groups inside groups) | 15 groups |
| `repeat` copies / `radial-repeat` copies | 512 / 360 |
| `scatter` copies | 5,000 |
| `pen` points, nodes or corners | 512 |
| Effects per layer | 256 |
| Frame (pixel) animation frames | 256 |
| Timeline length / rendered frames | 600 s / 3,600 frames |
| Document dpi | 36–2,400, and the page must still fit the pixel budget (Letter at 1,200 dpi does not) |
| Polygon and star `sides` | 3–128 |

`--max-pixels` adjusts the pixel budget (image imports may read sources up to four times it when they downsample); Python APIs can pass a complete `Limits` instance. These are input/allocation bounds, **not a hard resident-memory or CPU quota**. Float blending and snapshot copies can use multiples of image size. Use operating-system/container limits for untrusted workloads and reduce pixel/layer/history limits on small machines. Running out of memory is reported as a `resource_limit` error (“Not enough memory for this operation …”) by the Python API, the CLI, MCP and REST, after the failed call's memory is released; the document is unchanged. CLI processes share rendered layers and frames of saved documents only through the persistent disk cache (`VIXL_RENDER_CACHE`, capped by `VIXL_CACHE_MAX_MB`); the in-memory caches benefit a reused Python `Project` instance. REST/MCP cache the active document, reloading when the on-disk file changes (the reloaded document keeps its in-memory render caches, whose keys are content-addressed), and serialize read/write requests for persistence/concurrency correctness.

### Cost of an edit

An apply validates and inspects the whole document once (the result's `changes` compare the state before and after), so its cost grows with the document, but not with the document times the operations:

- A per-layer edit (`move`, `resize`, `rotate`, `scale`, centering …) lays out only that layer and what it depends on: the layers its constraints name, its parent for `canvas.*` constraints inside a group, and a symbol's master. A stack, or a member of one, lays out the whole document as before.
- Text measurements (ink and line boxes, baselines) are cached by everything they read: the font file and its fallback chain, every layer field except its position, and the size limits. Rich text is measured each time. The document's variables and form values are computed once per inspection, check or layout.
- The inspection an apply ends with is kept for the next apply, while the state, the embedded assets and the history head are unchanged. Documents with linked layers are always inspected afresh.
- A render reuses what the previous render of the same document view drew. Each top-level layer has a fingerprint (its resolved fields, its descendants, their boxes and what it is clipped to), and only the box covering the layers that changed, where they drew and where they draw now, is composited again. Documents with scene lighting, adjustment layers, canvas-edge blur on a top-level layer or selection-masked effects read the whole canvas and render in full. `render(region=...)` uses the same path to draw only a region; styled and clipped layers are drawn on a patch around their ink, not a canvas-sized tile.
- Text and single-colour path shapes are rasterised by content: the same label or outline in another layer, or recoloured, reuses the rasterised glyphs (a one-colour fill is a coverage stencil that is then painted).
- Text, path shapes, ellipses, rounded rectangles and capsules with no effects, mask or paper texture are drawn from their outlines straight into their final place: a fractional position, a turn, a flip or a skew costs no resampling, so their edges stay as sharp as on whole pixels. Any other layer at a fractional position is resampled once to that place (with its rotation, in the same pass, when it is turned). Gradients are dithered below one level, so a subtle ramp shows no 8-bit bands. [Render parity](../project/render-parity.md) measures both against Chromium and exact references. Reduced previews (`vixl_render` below 0.75 scale, `proxy.render_preview`) round each layer to the nearest whole preview pixel instead, so they skip that resample; exports and full-size renders keep exact placement.
- The overlap check reads each text layer's coverage only inside the box it compares; wrapping measures each line from one shaping, so a 100,000-character word flows in seconds.

On a 4-core machine one `move` on a 4,096-layer document (1,024 of them text) takes well under a second, and the 10,000-operation batch limit finishes in a few seconds. `pytest -m perf` (`tests/test_perf.py`) holds these as time budgets.

## Trust and security

Archive members are validated and read in memory, never extracted; duplicate/unsafe entries, missing assets, bad checksums, cyclic history, unsupported format versions, and oversized expanded content are rejected. Images are decoded with decompression-bomb handling and explicit dimensions. Do not disable these limits for unknown files.

Image bytes are opened only with the decoders of the raster formats Vixl imports: PNG, JPEG (including multi-picture camera JPEGs), WebP, GIF, TIFF, BMP, AVIF and ICO (`assets.RASTER_FORMATS`, through `assets.open_image`). Pillow's other plugins (EPS/PostScript through Ghostscript, PSD, JPEG 2000 and the legacy formats) are never loaded for them, and bytes in another format fail as `invalid_image`; internal round trips through resvg open PNG only. A test fails when an `Image.open` in `src/vixl` does not name its formats. Pillow's decompression-bomb guard is one process-wide number: Vixl raises it once, when `vixl.assets` is imported, to the largest source any limits can read (4 × 16,384², about 1.07 gigapixels; a lower setting by the host is raised, `None` is left alone) and never changes it while decoding. Each decode then checks the image against the call's own pixel limit right after reading the header, before any pixels are decoded. An application embedding Vixl that relies on Pillow's 89-megapixel default for its own decoding should set its own check.

Scripts compile only supported Vixl operations; they do not run shell/Python code. Assertions use a parsed comparison grammar. JSON operations are schema-checked, including unknown-field rejection and finite-number checks. Service clients cannot request arbitrary host file imports, linked files, custom font paths, or Python plugins. Linked files are opt-in for the CLI/Python API and remain external dependencies. Linked-document layers are confined the same way: through REST and MCP a source must resolve inside the workspace (absolute paths, `..` and symlink escapes are refused, when linking and when drawing), only the CLI/Python `--allow-linked` permits one outside it, and linked documents are checked for cycles and a depth of four.

Plugins and local provider configuration are trusted code/configuration. A provider may transmit the current rendered image, selection, text and document metadata to its configured service. Credentials are referenced by environment-variable name and not copied into Vixl's request provenance. Provider metadata should contain provenance only; Vixl stores only an allow-list of scalar keys from it. Layer names, text, notes, guidance and provider metadata reach agents as data: MCP and REST results name those paths under `untrusted` ([agent trust](agent-trust.md#untrusted-document-text)). HTTP adapters preserve TLS verification and do not follow redirects. They fetch result URLs only where a service requires it: FLUX polling and signed result URLs must be HTTPS on approved hosts (`*.bfl.ai`, `*.blob.core.windows.net`, configurable) and are fetched without credentials. ComfyUI files are fetched only from the configured server.

Managed Windows updates (`vixl.updater`, also frozen into the stable launcher) do not trust the release that carries
them on its own. Each release's `vixl-update.json` comes with `vixl-update.json.sig`, an Ed25519 signature over the
manifest's exact bytes, and the updater checks it against the public keys pinned in `vixl.updater_sign.TRUSTED_KEYS`
(a dependency-free RFC 8032 verifier) before it parses the manifest. Only then does it trust the manifest's SHA-256
and size for the runtime ZIP. A missing or invalid signature, or a build with no pinned key, refuses the update and
keeps the current version. The signing key is held only in the protected `release` environment of the release
workflow, so write access to the repository's releases is not enough to ship an update. Hosts are limited to GitHub
over HTTPS and the archive is extracted under path and size checks, as before. See [releases](releases.md#update-signing).

Vixl reaches the network on its own only for the AI providers above, `font install`/`font pair` (Google Fonts), the rolled font pairing of a new document (`vixl new`, `vixl_document(action='create')`, `Project.new()`: not at creation but on the first batch that sets text, and only when the pairing is not in the font cache; `VIXL_AUTO_FONTS=cache` or `off` prevents it), content packs fetched on first use (`vixl.packs`, such as the emoji artwork; `VIXL_PACK_DOWNLOAD=off` prevents it), importing a Vixl SVG whose Google fonts are not in the font cache (it downloads just those families; Python `install_fonts=False` keeps it offline and falls back with a warning) and the explicit [Figma import](../guides/images/figma.md) (`api.figma.com`, with the token from `FIGMA_TOKEN`; its image downloads use the policy below). `VIXL_OFFLINE=1` (or `--offline`) turns all of these off. Everything else is an explicit URL import: image imports with `url` (`import-image`, `vixl import URL`, `POST /assets?url=`, `Project.import_image(url=)`) and font imports from a URL (an `import-font` step, `vixl font import URL`). These share one bounded fetch (`vixl.fetch.fetch_bounded`):

- HTTPS only; a URL with a user name or password is refused.
- Internal names are refused before they are resolved: `localhost`, `*.localhost`, `*.local` (and so `*.cluster.local`), `*.internal` (including `metadata.google.internal`), `*.svc`, and names without a dot.
- With `VIXL_FETCH_HOSTS` set (a comma list of hosts and `*.suffix` patterns, for example `cdn.example.com,*.githubusercontent.com`), an explicit URL import, and every redirect it follows, must name a listed host. Content packs, Figma image downloads, Google Fonts and AI providers use the hosts Vixl or their configuration chose and are not affected.
- At most 5 redirects, each one validated again like the first URL (an HTTPS page cannot redirect to `http:` or to an internal address).
- A 30 s timeout per network step (120 s in all) and a streamed byte cap (the asset byte limit for images, 16 MiB for fonts); a larger `Content-Length` is refused before reading.
- Every address the host resolves to must be public. Private (10/8, 172.16/12, 192.168/16, fc00::/7), loopback, link-local (including the 169.254.169.254 cloud metadata address), shared/CGNAT, multicast, reserved, documentation (192.0.2/24 and the like, 2001:db8::/32, 3fff::/20), deprecated site-local (fec0::/10), SRv6 (5f00::/16) and unspecified addresses are refused, also when embedded in IPv6 (IPv4-mapped, IPv4-translated `::ffff:0:0:0/96`, IPv4-compatible, NAT64, 6to4, Teredo). Literal IP hosts get the same check.
- Without a proxy, the connection goes to the address that was checked; the host name is kept for the `Host` header, TLS SNI and certificate verification, so a second DNS answer cannot move the request to another address (DNS rebinding).
- Downloaded bytes are not trusted by `Content-Type`: images are decoded under the normal pixel and decompression-bomb limits, fonts are validated as TrueType/OpenType.

When an `HTTPS_PROXY`/`ALL_PROXY` environment proxy applies, the proxy resolves and connects. Vixl still resolves the name itself and refuses a private answer, and when it cannot resolve the name it refuses the download (`fetch_failed`) instead of letting the proxy decide. Set `VIXL_PROXY_RESOLVES=1` in sandboxes where only the proxy can resolve names; the name checks still apply, but the address check is then the proxy's. Residual limit: Vixl cannot pin the address the proxy connects to. Set `VIXL_ALLOW_PRIVATE_FETCH=1` to allow intranet or local test hosts (internal names included); the other rules still apply.

`VIXL_OFFLINE=1` (or `--offline` on `vixl mcp`, `serve` and `view`) turns off every network access listed above: URL imports, font downloads and installs, content packs, the Figma import and AI provider calls fail with `network_disabled` before connecting; automatic fonts at creation fall back to the font cache and say why. `GET /limits` reports the policy in force under `network`. A URL import records `source: {url, fetched_at, sha256, bytes}` (and `requested_url` after a redirect) in the layer's provenance, with optional caller-supplied `credit` and `license`.

The REST service defaults to loopback, validates host headers without a token, requires a token for non-loopback binding, and limits bodies before JSON parsing. Use a TLS reverse proxy for remote use. API tokens do not create a multi-tenant permission system. Image/font codecs and optional plugins still execute native/Python code in-process; a container remains the appropriate boundary for hostile inputs.

## Verification

The test suite covers pixel-level blending, selection boundaries, effect disable/re-enable, masks, text/rasterization, variables, constraints and cycles, archive round trips, malformed archives, resource limits, optimistic write conflicts, history/transactions, subprocess CLI and binary pipelines, batch processing, authenticated REST and request limits, real MCP stdio negotiation/tool calls, and mocked AI adapter contracts. Live AI services are not required by tests.
