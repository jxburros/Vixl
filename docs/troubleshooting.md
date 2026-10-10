# Troubleshooting

[Documentation home](README.md) · [Commands](commands.md) · [Coverage and limits](coverage.md)

Start with `vixl --version`, the exact command and its structured error. For source installs,
record `git rev-parse HEAD`. Use `vixl -p your-file.vixl inspect --json` to confirm the target
document before changing anything.

| Symptom | Cause to check | Next step |
| --- | --- | --- |
| `vixl` is not found | Terminal/client PATH or inactive virtual environment | Activate the environment or reopen the terminal; Windows users see [PATH repair](releases.md#using-the-current-terminal) |
| Old version after updating | Another executable on PATH or a running old session | Check executable location, run its `--version`, restart the client/session |
| Server/view or PDF import is unavailable | Missing optional dependency | Install `.[server]` or `.[pdf]` in the same environment as Vixl |
| Command edits the wrong file | Directory-default project selection | Pass `-p file.vixl` explicitly; MCP tools accept `document=` |
| Unknown operation/field | Wrong spelling or syntax from another release | Inspect `vixl schema` and command `--help`; follow the error's field and suggestions |
| Layer not found | Typo, renamed layer or wrong active page | Inspect layers/pages; use the immutable layer ID when names can change |
| “Unknown swatch” / undefined variable | `@name` or `${name}` has no definition | Define it first, or use a literal; inspect the reported operation index |
| Image/font file denied through a service | Services restrict operation file paths | Import through MCP image/font tools or REST asset endpoints; reuse embedded asset IDs |
| Effect changes only part of a layer | Selection was active when effect was added | Clear selection before adding whole-layer effects; edit/remove the old masked effect |
| Layer stops responding to canvas resize | Absolute move/align cleared constraints | Reapply intended constraints, then preview the new canvas |
| Text is cut off or too small | Copy exceeded box or fit reduced size | Inspect resolved bounds, use a suitable text-layout box and review at destination size |
| Layout contains `[Label]` placeholders | Unfilled template/layout slots | Discover slots, fill all required copy and reapply with the same seed |
| Pixel sprite looks blurred | Smooth resampling | Use nearest sampling and integer scaling |
| Strict SVG fails | Content needs a raster fallback | Read the layer/effect details; simplify or use appearance export |
| Export refuses a destination | Existing file or protected extension | Use a fresh filename; MCP needs `overwrite=true` for allowed export overwrite |
| Movie/audio export fails | ffmpeg unavailable or input invalid | Check `ffmpeg -version`; try WebP or frame output to isolate encoding |
| Provider command fails | Missing config/key, unsupported model/capability or service error | Check [provider discovery](providers.md); image generators and vision providers have different abilities |

## Interpret checks

A passing report certifies its requested checks and samples. It does not certify all
export formats, every animation frame or artistic quality. Every finding carries an
`action`, and `by_action` lists the issue indexes under `fix`, `review` and `informational`.
Each finding also has a stable `rule` (`bounds.text-overflow`, `contrast.text-contrast` …),
`layer_ids`, its measured `actual` and `expected` values and, for fix findings, a suggested
`repair` you can dry-run; `outcome` keeps validation (fix findings) apart from review. See
[outcomes, diagnostics and repair](agent-trust.md).
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
reason. Do not lower thresholds simply to make a report pass. [Studio](studio.md) and
[production](production.md) describe reusable contracts and coverage.

## Find out why a render is slow

Set `VIXL_PROFILE=1` in the environment of the CLI, the MCP server or the REST server. Every call then returns a
`render_profile` next to its result: in CLI `--json` output and other JSON results (a command that writes an image
to stdout prints it on stderr instead), in MCP result envelopes (a text note after an image), and in REST JSON
bodies and the `X-Vixl-Profile` header (a shorter summary, also on PNG responses). With the variable unset nothing
is recorded and the renderer does no extra work.

| Field | What it tells you |
| --- | --- |
| `layers` | The 25 slowest layers drawn from scratch: `ms` (its own time; a group's excludes its children), `draws`, and `stages_ms` (`draw`, `effects`, `transform`) |
| `by_type` | Time and count per layer type |
| `phases_ms` | `render` (whole renders), `resolve` and `layout` (resolving variables and constraints), `styles` (drop shadows, glows, strokes), `frame_setup` and `frame_raster` (timeline exports) |
| `caches` | `layer_hits`, `layer_misses`, `layer_writes`, `layer_evictions` (rendered layers and composited groups), `styled_hits`/`styled_misses`, `svg_hits`/`svg_misses` (rasterised text and paths; process-wide), `disk_hits`, `disk_misses`, `disk_writes`, `disk_frame_hits`, `disk_frame_writes`, `disk_frame_writes_skipped`, `disk_evictions`, `disk_bytes_written` |
| `renders` | Each render: `incremental` (only a box was redrawn), `dirty_box` and `dirty_pixels` against `canvas_pixels`, `from_disk`, or the `reason` it drew everything |

To find the culprit without reading numbers, run the opt-in `cost` check: it draws the document once with empty
caches and flags, as a `review` finding, every layer that takes over 10× the median layer and at least 50 ms,
naming the blur radius, effects, stroke points or size behind it.

```bash
vixl -p poster.vixl check --checks cost
vixl cache info
```

The disk cache (`vixl cache info`, `vixl cache clear`, `VIXL_RENDER_CACHE=off`, `VIXL_CACHE_MAX_MB`) is described
under [production](production.md#persistent-rendering-cache-and-library). Long timeline exports report per-frame
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
see [releases](releases.md). Restart interrupted durable job workers and inspect job
status rather than blindly repeating an uncertain external generation request.

## Report a reproducible issue

Include version/commit, operating system, interface, command or operation JSON, full
structured error, expected result and a small non-sensitive document/input that reproduces
the problem. For visual differences include preview and export settings. Do not include
provider credentials or private form data. Source tests run with `python -m pytest -q`
after installing `.[dev]`; [architecture](architecture.md) explains module boundaries.
