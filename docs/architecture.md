# Architecture and operational boundaries

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

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
                    PNG / JPEG / WebP / TIFF / AVIF / SVG
```

`project.py` owns document lifecycle, candidate-state commits, history and archives. `operations.py` changes document state; it has no dependency on CLI output. `render.py` converts state into pixels without changing it. `text.py` shares HarfBuzz/bidi shaping and font outlines between PNG (resvg rasterization) and SVG; `artistic.py` owns deterministic local treatments; `svg_effects.py` maps supported effects/styles to SVG primitives. `commands.py` compiles the human syntax; scripts use the same compiler. `ai.py` delegates inference to providers and inserts ordinary assets/masks. `interfaces.py` exposes the shared boundary to REST and MCP. `colors.py` parses the color language and performs CMYK separation, proofing and vision simulation; `sizes.py` holds the named-size catalog and canvas print metadata; `layouts.py` builds seeded, principled layouts from ordinary operations; `brushes.py` renders paint-layer stroke data; `timeline.py` samples keyframe tracks into render-only document copies and streams animation exports. `schema.py` publishes the operation contract. `validation.py` checks structures, design rules, and dependencies. `inplace.py` lets `shape`, `solid`, `gradient` and `text` edit a targeted layer in place; `stacks.py` resolves `hide_if_empty` text and auto-layout stacks while layers are resolved for layout, so every renderer, export and check sees the same collapsed layout. `links.py` renders linked `.vixl` documents live (cached by content hash, confined to the workspace, cycle- and depth-checked) and `imposition.py` merges a template and a CSV into print sheets (a PDF with vector text, and an editable sheet document of links); see [linked documents](linked-documents.md) and [imposition](imposition.md). `charts.py` lays data-bound charts out as ordinary vector layers and keeps them in step with their table; `chart_pptx.py` writes them to PPTX as native charts with an embedded workbook. `pathfinder_geometry.py` and `booleans.py` turn pathfinder layers into exact compound-path geometry (Bézier outlines split where they cross, pieces kept by inside/outside tests) for the SVG, PDF and PowerPoint exports; `pdf_export.py`/`pdf_writer.py` write vector PDFs and `pdf_color.py` separates their colours to DeviceCMYK.

The implementation uses Python, Pillow, and NumPy to cover the complete editing/automation workflow with a reusable API. The specification's Rust-core recommendation is a future performance/distribution option, not the current implementation. Image operations are deterministic for a fixed document and imaging-library/font environment; random filters use explicit seeds. AI inference and provider availability are external.

## Persistence and concurrency

Production extensions: `assurance.py` owns saved, read-only design contracts;
`automation.py` compiles bounded actions and role-based motion to canonical operations;
`production.py` handles typed recipe snapshots, variant plans, manifests and component
libraries. `render_cache.py` supplies an optional persistent, bounded PNG cache keyed
by render inputs, font bytes and runtime versions. `film.py` assembles bounded shot
sequences; `jobs.py` persists workspace jobs and frozen inputs, with per-job worker
locks and cooperative cancellation. `workflows.py` is the shared CLI/MCP dispatcher;
REST exposes its fixed-project subset. See [production](production.md).

New document fields (`suites`, `roles`, `motions`, `actions`, `recipe`) are optional,
validated on load and committed through existing history. Older archives need no
migration. Job, recipe, suite, library and production manifests carry their own v1
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
- 256 MiB per archive and its expanded contents.
- 10,000 operations per submitted batch; 2,000 history revisions (older ones are squashed, not refused).
- At most 10,000 archive entries.
- Layer-render cache: 16 entries / 64 MiB, with entries under 32 MiB; decoded-asset cache: 256 MiB.

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

`--max-pixels` adjusts the pixel budget (image imports may read sources up to four times it when they downsample); Python APIs can pass a complete `Limits` instance. These are input/allocation bounds, **not a hard resident-memory or CPU quota**. Float blending and snapshot copies can use multiples of image size. Use operating-system/container limits for untrusted workloads and reduce pixel/layer/history limits on small machines. CLI processes do not share render caches; caching benefits a reused Python `Project` instance. REST/MCP cache the active document, reloading when the on-disk file changes, and serialize read/write requests for persistence/concurrency correctness.

## Trust and security

Archive members are validated and read in memory, never extracted; duplicate/unsafe entries, missing assets, bad checksums, cyclic history, unsupported format versions, and oversized expanded content are rejected. Images are decoded with decompression-bomb handling and explicit dimensions. Do not disable these limits for unknown files.

Scripts compile only supported Vixl operations; they do not run shell/Python code. Assertions use a parsed comparison grammar. JSON operations are schema-checked, including unknown-field rejection and finite-number checks. Service clients cannot request arbitrary host file imports, linked files, custom font paths, or Python plugins. Linked files are opt-in for the CLI/Python API and remain external dependencies. Linked-document layers are confined the same way: through REST and MCP a source must resolve inside the workspace (absolute paths, `..` and symlink escapes are refused, when linking and when drawing), only the CLI/Python `--allow-linked` permits one outside it, and linked documents are checked for cycles and a depth of four.

Plugins and local provider configuration are trusted code/configuration. A provider may transmit the current rendered image, selection, text and document metadata to its configured service. Credentials are referenced by environment-variable name and not copied into Vixl's request provenance. Provider metadata should contain provenance only. HTTP adapters preserve TLS verification and do not follow redirects. They fetch result URLs only where a service requires it: FLUX polling and signed result URLs must be HTTPS on approved hosts (`*.bfl.ai`, `*.blob.core.windows.net`, configurable) and are fetched without credentials. ComfyUI files are fetched only from the configured server.

Vixl reaches the network on its own only for the AI providers above and `font install`/`font pair` (Google Fonts). Everything else is an explicit URL import: image imports with `url` (`vixl_import_image`, `vixl import URL`, `POST /assets?url=`, `Project.import_image(url=)`) and font imports from a URL (`vixl_import_font(url=)`, `vixl font import URL`). These share one bounded fetch (`vixl.fetch.fetch_bounded`):

- HTTPS only; a URL with a user name or password is refused.
- At most 5 redirects, each one validated again like the first URL (an HTTPS page cannot redirect to `http:` or to an internal address).
- A 30 s timeout per network step (120 s in all) and a streamed byte cap (the asset byte limit for images, 16 MiB for fonts); a larger `Content-Length` is refused before reading.
- Every address the host resolves to must be public. Private (10/8, 172.16/12, 192.168/16, fc00::/7), loopback, link-local (including the 169.254.169.254 cloud metadata address), shared/CGNAT, multicast, reserved, documentation and unspecified addresses are refused, also when embedded in IPv6 (IPv4-mapped, IPv4-compatible, NAT64, 6to4, Teredo). Literal IP hosts get the same check.
- Without a proxy, the connection goes to the address that was checked; the host name is kept for the `Host` header, TLS SNI and certificate verification, so a second DNS answer cannot move the request to another address (DNS rebinding).
- Downloaded bytes are not trusted by `Content-Type`: images are decoded under the normal pixel and decompression-bomb limits, fonts are validated as TrueType/OpenType.

Residual limits: when an `HTTPS_PROXY`/`ALL_PROXY` environment proxy applies, the proxy resolves and connects, so Vixl checks its own resolution of the name (and refuses a private answer) but cannot pin the address the proxy uses; the proxy's policy is the final boundary. Set `VIXL_ALLOW_PRIVATE_FETCH=1` to allow intranet or local test hosts; the other rules still apply. A URL import records `source: {url, fetched_at, sha256, bytes}` (and `requested_url` after a redirect) in the layer's provenance, with optional caller-supplied `credit` and `license`.

The REST service defaults to loopback, validates host headers without a token, requires a token for non-loopback binding, and limits bodies before JSON parsing. Use a TLS reverse proxy for remote use. API tokens do not create a multi-tenant permission system. Image/font codecs and optional plugins still execute native/Python code in-process; a container remains the appropriate boundary for hostile inputs.

## Verification

The test suite covers pixel-level blending, selection boundaries, effect disable/re-enable, masks, text/rasterization, variables, constraints and cycles, archive round trips, malformed archives, resource limits, optimistic write conflicts, history/transactions, subprocess CLI and binary pipelines, batch processing, authenticated REST and request limits, real MCP stdio negotiation/tool calls, and mocked AI adapter contracts. Live AI services are not required by tests.
