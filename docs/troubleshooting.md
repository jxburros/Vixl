# Troubleshooting

[Documentation home](README.md) · [Commands](reference/commands.md) · [Coverage and limits](reference/coverage.md)

Start with `vixl --version`, the exact command and its structured error (a terminal shows a one-line
`ERROR:` with the suggestions; `--json` or `VIXL_JSON=1` prints the full JSON). For source installs,
record `git rev-parse HEAD`. Use `vixl -p your-file.vixl inspect --json` to confirm the target
document before changing anything.

| Symptom | Cause to check | Next step |
| --- | --- | --- |
| `vixl` is not found | Terminal/client PATH or inactive virtual environment | Activate the environment or reopen the terminal; Windows users see [PATH repair](reference/releases.md#using-the-current-terminal) |
| Old version after updating | Another executable on PATH or a running old session | Check executable location, run its `--version`, restart the client/session |
| Server/view or PDF import is unavailable | Missing optional dependency | Install `.[server]` or `.[pdf]` in the same environment as Vixl |
| Command edits the wrong file | Directory-default project selection | Pass `-p file.vixl` explicitly (the terminal summary starts with the file it edited); MCP tools accept `document=` |
| `unsafe_workspace` when starting `vixl mcp` or a `Session()` | No workspace was given and the current directory (or the remembered document's folder) is your home folder or a filesystem root | Pass `--workspace DIR` (`Session(workspace=DIR)`) or start in a project folder; the server prints its workspace on stderr at start-up |
| The first text in a new document is slow, or `font_install` warns | The rolled pairing is not in the font cache and is being downloaded, or the download failed (offline) | `VIXL_AUTO_FONTS=cache` (cache only) or `off`, `VIXL_OFFLINE=1`, or choose fonts yourself with `font-pair`/`font-install` |
| Unknown operation/field | Wrong spelling or syntax from another release | Inspect `vixl schema` and command `--help` (MCP: the error carries the schema, or `vixl_reference('operations', name=[…])`); follow the error's field and suggestions |
| `Unknown tool: vixl_…`, or `vixl mcp --tools core` is refused | A saved call, prompt or client configuration from before 0.27 names a removed tool or flag; the server has seven tools (`--tools` is `default` or `ai`) | `vixl convert-batch OLD.json` rewrites it ([Converting](reference/converting.md#convert-saved-tool-calls)) |
| MCP call fails with “Create or open a document first” or `document_required` | This client has no active document, or the server runs with `--require-document` | `vixl_document(action='create')` or `open`, or pass `document=` on every call ([interfaces](reference/interfaces.md#several-agents-on-one-server)) |
| MCP call fails with `ambiguous_document` | Several documents are open and this connection (shared by subagents, for example) has touched more than one of them, or none | Pass `document=` with one of the paths the error lists, or close the ones you are done with ([interfaces](reference/interfaces.md#several-agents-on-one-server)) |
| MCP call answers `{"status": "running", "job": …}` | It outlived the inline wait (about 40 s) or was sent with `as_job`; the work carries on | `vixl_job(action='result', id=…, wait=30)`; do not resend it ([long calls](reference/interfaces.md#long-calls-retries-and-progress)) |
| Call refused with `limit_exceeded` | The server was started with per-call limits | Lower `scale`, export fewer pages or wait for a running job ([per-call limits](reference/interfaces.md#per-call-limits)) |
| `Malformed operation (KeyError: …)` with `"internal": true` | The schema accepted the operation, but its executor raised a Python exception: a field value Vixl does not check yet, or a Vixl bug. `exception` names the exception type; validation errors never carry `internal` | Check the operation's values against `vixl schema`; if they look right, report the operation and the full error ([report an issue](#report-a-reproducible-issue)). Python: `logging.getLogger("vixl.project").setLevel(logging.DEBUG)` logs the traceback |
| `not_found` / `io_error` naming a file | A file the call reads is missing or unreadable. Over MCP and REST the path is shown relative to the workspace (a file outside it by its name only), never as an absolute server path; the Python API shows the operation's own `path` | Check the file exists under the workspace and is readable |
| `invalid_project` “Malformed Vixl archive: unsupported or encrypted ZIP member” | The `.vixl` was re-zipped with a password (including AES, compression method 99) or a compression method Vixl cannot read | Re-save it from Vixl, or re-zip it without a password using standard deflate |
| Layer not found | Typo, renamed layer or wrong active page | Inspect layers/pages; use the immutable layer ID when names can change |
| “Unknown swatch” / undefined variable | `@name` or `${name}` has no definition | Define it first, or use a literal; inspect the reported operation index |
| Image/font file denied through a service | Services restrict operation file paths | Import with an `import-image` or `import-font` step in `vixl_apply`, or the REST `/assets` and `/fonts` endpoints; reuse embedded asset IDs |
| Effect changes only part of a layer | Selection was active when effect was added | Clear selection before adding whole-layer effects; edit/remove the old masked effect |
| Layer stops responding to canvas resize | Absolute move/align cleared constraints | Reapply intended constraints, then preview the new canvas |
| Text is cut off or too small | Copy exceeded box or fit reduced size | Inspect resolved bounds, use a suitable text-layout box and review at destination size |
| Chinese, Japanese, Korean, Devanagari or Thai text draws as empty boxes, or the apply warns it "does not embed" a face | No document font covers the script. Vixl draws it from a matching face already on the machine (the font cache, or `VIXL_CJK_PACK`) and never downloads one while rendering; with none, the characters stay empty boxes | Run the step the warning names, such as `{"type": "font-cover", "scripts": ["Han"]}` (CLI `vixl font cover --script Han`): it embeds the face (from the cache, else a download) ([scripts](guides/text/typography.md#scripts-the-bundled-fonts-do-not-draw)) |
| Text looks different after an update: Noto Sans instead of DejaVu Sans | Noto Sans is now the proofing face for text without a font | Choose real type (`font-pair`), or keep DejaVu Sans ([keeping DejaVu Sans](guides/text/typography.md#keeping-dejavu-sans)) |
| `check` lists `composition.*` review findings, or `--profile final` fails on them | A dead band, drifting margin, uneven rhythm, crowding under a rule or heading, a clumped scatter, or a hierarchy finding (`flat_hierarchy`, `single_weight`, `no_focal`, `accent_unused`) ([composition](guides/layout/guides.md#composition)) | `vixl_apply(workflow='repair-layout')` repairs most spacing findings ([layout repair](reference/agent-trust.md#layout-repair)) and lists suggestions for the hierarchy ones, which are judgement calls; otherwise fix the layout, or waive a deliberate finding with a reason |
| Layout contains `[Label]` placeholders | Unfilled template/layout slots | Discover slots, fill all required copy and reapply with the same seed |
| Pixel sprite looks blurred | Smooth resampling | Use nearest sampling and integer scaling |
| Strict SVG fails | Content needs a raster fallback | Read the layer/effect details; simplify or use appearance export |
| Export refuses a destination | Existing file or protected extension | Use a fresh filename; MCP needs `overwrite=true` for allowed export overwrite |
| Movie/audio export fails | ffmpeg unavailable or input invalid | Check `ffmpeg -version`; try WebP or frame output to isolate encoding |
| Figma import fails with `figma_token_missing`, `figma_forbidden`, `figma_not_found` or `figma_rate_limited` | No or invalid `FIGMA_TOKEN`, no access to the file, a wrong key or node id, or Figma's rate limit (`retry_after_s`) | Set `FIGMA_TOKEN` (or `VIXL_FIGMA_TOKEN`) in the process environment; import one frame with `--node` ([Figma errors](guides/images/figma.md#errors)) |
| Provider command fails | Missing config/key, unsupported model/capability or service error | Check [provider discovery](reference/providers.md); image generators and vision providers have different abilities |

## Interpret checks

A passing report certifies its requested checks and samples. It does not certify all
export formats, every animation frame or artistic quality. Every finding carries an
`action`, and `by_action` lists the issue indexes under `fix`, `review` and `informational`.
Each finding also has a stable `rule` (`bounds.text-overflow`, `contrast.text-contrast` …),
`layer_ids`, its measured `actual` and `expected` values and, for fix findings, a suggested
`repair` you can dry-run; `outcome` keeps validation (fix findings) apart from review. See
[outcomes, diagnostics and repair](reference/agent-trust.md).
Since 0.24 `passed` is false whenever a `fix` finding remains, including warnings from the
legibility, fonts, content, guides, alignment, blanks, placeholders and brand checks unless the finding
is marked `review` (such as a body-measure or underfilled-canvas note); `review` and
`informational` findings do not fail it. A fallback-font finding is expected in an early
proof, but replace the fonts before final delivery. A contrast check does not
remove the need to inspect text over complex imagery.

Use targeted checks to investigate a problem, and a broader suite before delivery:

```bash
vixl -p campaign.vixl check --checks bounds contrast
vixl -p registration.vixl check --checks form --sample worst
vixl -p slides.vixl check --checks deck
vixl -p flyer.vixl check --checks print
```

Respond to findings by changing the design or explicitly revising requirements with a
reason. Do not lower thresholds simply to make a report pass. [Studio](guides/automation/studio.md) and
[production](guides/automation/production.md) describe reusable contracts and coverage.

## Find out why a render is slow

Set `VIXL_PROFILE=1` in the environment of the CLI, the MCP server or the REST server. Every call then returns a
`render_profile` next to its result: in CLI `--json` output and other JSON results (in a terminal the CLI prints a short
summary without it, so add `--json`; a command that writes an image to stdout prints it on stderr instead), in MCP result envelopes (a text note after an image), and in REST JSON
bodies and the `X-Vixl-Profile` header (a shorter summary, also on PNG responses). With the variable unset nothing
is recorded and the renderer does no extra work.

| Field | What it tells you |
| --- | --- |
| `layers` | The 25 slowest layers drawn from scratch: `ms` (its own time; a group's excludes its children), `draws`, and `stages_ms` (`draw`, `effects`, `transform`) |
| `by_type` | Time and count per layer type |
| `phases_ms` | `render` (whole renders), `resolve` and `layout` (resolving variables and constraints), `styles` (drop shadows, glows, strokes), `frame_setup` and `frame_raster` (timeline exports) |
| `caches` | `layer_hits`, `layer_misses`, `layer_writes`, `layer_evictions`, `layer_uncacheable` (rendered layers and composited groups), `styled_hits`/`styled_misses`, `svg_hits`/`svg_misses` (rasterised text and paths; process-wide), `disk_hits`, `disk_misses`, `disk_writes`, `disk_frame_hits`, `disk_frame_misses`, `disk_frame_writes`, `disk_frame_writes_skipped`, `disk_evictions`, `disk_bytes_written` |
| `renders` | Each render: `incremental` (only a box was redrawn), `dirty_box` and `dirty_pixels` against `canvas_pixels`, `from_disk`, or the `reason` it drew everything |

To find the culprit without reading numbers, run the opt-in `cost` check: it draws the document once with empty
caches and flags, as a `review` finding, every layer that takes over 10× the median layer and at least 50 ms,
naming the blur radius, effects, stroke points or size behind it.

```bash
vixl -p poster.vixl check --checks cost
vixl cache info
```

Layers whose drawing is mostly image work (effects, drop shadows and glows, placed images, large gradients) are drawn
ahead on a pool of threads while the stack is composited in order, so the pixels are those of a one-thread render.
`VIXL_RENDER_THREADS` sets its size (default: one per core, at most 8; `0` or `1` turns it off). Plain vector shapes
and text are not drawn ahead: their rasteriser holds Python's interpreter lock, so threads would only add overhead.
With `VIXL_PROFILE=1` every layer is drawn on the calling thread, so the profile stays per layer.

The disk cache (`vixl cache info`, `vixl cache clear`, `VIXL_RENDER_CACHE=off`, `VIXL_CACHE_MAX_MB`) is described
under [production](guides/automation/production.md#persistent-rendering-cache-and-library). Long timeline exports report per-frame
timing in their progress (`vixl_job` status): `timing.elapsed_s`, `timing.eta_s`, and the frame's `setup_ms`
(sampling the timeline) and `raster_ms`.

## Recover a design

Use `undo` for the last edit or `checkout` for a named checkpoint. Atomic batches fail
without partial document changes. A persistent CLI transaction can be rolled back:

```bash
vixl -p campaign.vixl undo
vixl -p campaign.vixl checkout approved-layout
vixl -p campaign.vixl transaction rollback
```

Use the command matching your situation; rollback requires an open transaction. Keep
backups of masters. Windows runtime rollback is separate (`vixl update --rollback`);
see [releases](reference/releases.md). Restart interrupted durable job workers and inspect job
status rather than blindly repeating an uncertain external generation request.

## Report a reproducible issue

Include version/commit, operating system, interface, command or operation JSON, full
structured error, expected result and a small non-sensitive document/input that reproduces
the problem. For visual differences include preview and export settings. Do not include
provider credentials or private form data. Source tests run with `python -m pytest -q`
after installing `.[dev]`; [architecture](reference/architecture.md) explains module boundaries.
