# Spacing checks and pixel animation (0.9.0)

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

## Check the spacing you intended

Spacing analysis is opt-in. Vixl does not assume every object in a document should be evenly spaced.

```bash
# Equal edge-to-edge gaps between these siblings, allowing one pixel of rounding.
vixl spacing --targets heading body footer --axis vertical --tolerance 1

# Specifically compare the space above and below body.
vixl spacing --around body --before heading --after footer --axis vertical --tolerance 0

# Require each gap to be 24 pixels; fail the command if the intention is not met.
vixl spacing --targets first second third --axis horizontal --expected 24 --tolerance 1 --check
```

Results include each pair's stable IDs/names, exact gap in pixels, overlap flags, cross-axis overlap, minimum/maximum/mean gap, spread, and `passed`. A negative gap is overlap and always fails. For equal spacing, the largest gap minus the smallest must be within `tolerance`; for an expected spacing, every gap must be within tolerance of `expected`. `equal` is `null` when only one gap is measured. Normal measurement exits successfully even on a mismatch; `--check` returns the structured `spacing_mismatch` error with all measurements and a nonzero exit code.

The targets must be distinct visible siblings. Lists are sorted by position along the requested axis, accounting for unequal object sizes. The `before/around/after` form preserves and validates that explicit order. Bounds use resolved constraints and transformed geometry, excluding shadows/glows. Gaps inside groups use local coordinates; rotated objects use their axis-aligned bounds. A cross-axis overlap of zero is reported for context, not treated as an error. `--artboard` and `--comp` inspect a render variant without changing the document. An artboard's hidden targets cannot be checked.

Python: `project.measure_spacing(targets=[...], axis="vertical", expected=24, tolerance=1)` or `project.measure_spacing(around="body", before="heading", after="footer")`. REST: POST `/spacing` with the same options. MCP: `vixl_measure_spacing`. Use `align` or `distribute` when you actually want to change spacing; measurement never edits the document. `stack` and `layout-apply` gaps also accept shared spacing units (`gap: "2u"`, where one unit is half the document's body size and at least 2 px), so related gaps stay on one scale.

## Make a compact pixel sprite

```bash
vixl new 16x16 --background transparent -o coin.vixl
vixl pixel-art --name coin --width 16 --height 16 --palette '{".":"transparent","g":"#ffc44d","s":"#9c5f22","w":"#fff3bd"}'
vixl pixel-draw coin rect 4 3 --width 8 --height 10 --color s
vixl pixel-draw coin rect 5 4 --width 6 --height 8 --color g
vixl pixel-draw coin line 6 5 --x2 9 --y2 5 --color w
vixl pixels coin
vixl export coin-large.png --scale 8 --sampling nearest
```

A pixel layer stores a small grid of single-character palette indices instead of image bytes. `pixels` returns just the grid, palette, native dimensions and layer ID/name. An agent can read or replace a 16×16 sprite as sixteen short strings. Create a complete pattern in one operation:

```json
{"type":"pixel-art","name":"spark","rows":[".w.","www",".w."],"palette":{".":"transparent","w":"#ffffff"},"x":6,"y":1}
```

Grids are 1–256 pixels per axis with 1–94 printable non-space ASCII palette symbols; every cell must have a palette entry. Palette colors can use `@swatch` or `${variable}`. Without a palette, `.` is transparent and `#` is black. Blank grids use `.` by default; pass `--background SYMBOL` with a custom palette. Explicit rows supply their own dimensions/background and cannot be combined with width/height/background.

`pixel-draw` tools:

- `pixel X Y --color SYMBOL`: set one cell.
- `line X Y --x2 X --y2 Y --color SYMBOL`: one-pixel-wide integer line, including both endpoints.
- `rect X Y --width W --height H --color SYMBOL`: filled rectangle, exactly W×H cells.
- `fill X Y --color SYMBOL`: flood-fill connected cells of the original palette index using four neighbors.

Drawing coordinates refer to the native grid, even after resizing or positioning the layer. Out-of-bounds edits fail atomically. `pixel-palette NAME --colors '{"g":"#ffdd66"}'` updates all cells with that index. Ordinary layer operations such as duplicate, move, flip, resize, mask, and effects still work. Pixel layer transforms use nearest-neighbor sampling; use integer display sizes and 90° rotations for uniform blocks. Filters/styles can intentionally soften pixels. Final ordinary exports default to smooth sampling for compatibility, so specify `--sampling nearest` when enlarging pixel artwork.

Python: `project.inspect_pixels(target)`. REST: GET `/pixels/{target}`. MCP: `vixl_pixels_inspect`; edits use `vixl_operations_apply` with `pixel-art`, `pixel-draw`, and `pixel-palette`.

## Save and export animation frames

```bash
vixl frame-save idle --duration 150
vixl pixel-draw coin pixel 5 4 --color w
vixl frame-save glint --duration 100
vixl frame-apply idle
vixl pixel-draw coin pixel 10 10 --color w
vixl frame-save glint-low --duration 100
vixl animation
vixl animation-set --order idle glint glint-low --loop 0
vixl export-animation --out coin.gif --format gif --scale 8
vixl export-animation --out coin.apng --format apng
vixl export-animation --out coin-sheet.png --format sheet --columns 3
```

Frames are named snapshots of the current editable scene, including palette, variables, styles, masks and geometry, while reusing embedded image assets. Later edits to the scene do not change saved frames (`frames-edit`, below, is the one operation that edits them). `frame-save` creates a frame or replaces the frame with that name in place; omitted duration defaults to 100 ms for a new frame and preserves an existing duration. `frame-apply` restores a frame for editing while keeping the full animation library. `frame-delete NAME` removes a frame. These operations autosave, participate in transactions and support undo/redo.

Frame animation holds at most 256 frames, all the same canvas size. Any canvas size works (a 1080×1080 character included) as long as frames × canvas pixels stays within the pixel budget (`--max-pixels`, 40 million by default: about 34 frames at 1080×1080); for long or high-resolution motion use the keyframe timeline. Pixel-art layers keep their 1–256 cell grid. Durations are 10–60,000 ms in multiples of 10 so GIF and APNG timings agree. Linked files must be embedded before capture. There is no interpolation, onion skin, audio track or timeline GUI. The loop count is the number of additional repetitions after the first play; zero means infinite. Both exports encode that same meaning, despite GIF/APNG's different loop conventions.

`animation` / `vixl_animation_inspect` list names, dimensions, durations and total duration (and any named animations) without returning full snapshots. In MCP compact operation results, saving a frame returns changed frame names/timing, not a duplicate scene. `vixl_animation_preview(name, scale=1)` previews a saved frame at its native size by default. Python offers `project.render_frame(name, scale=1, sampling="nearest")` and `project.inspect_animation()`. REST offers GET `/animation` and GET `/animation/frame/{name}?scale=1`.

GIF, APNG, animated WebP and MP4/WebM export the sequence and timing. GIF uses up to 255 opaque palette colors per frame, no dithering, and an alpha threshold of 128 for its binary transparency; APNG preserves RGBA; WebP preserves RGBA and is lossless with the default crisp (`nearest`) sampling. Encoders may combine identical consecutive frames while retaining their duration. A sprite sheet preserves every named frame, accompanied by a same-stem JSON file with frame rectangles and durations for game engines. `--columns` controls sheet layout; its default is a roughly square grid. Empty cells remain transparent.

Export scaling defaults to `sampling: "nearest"` with an integer scale 1–32, which keeps pixel art crisp. `sampling: "smooth"` accepts any scale 0.05–32 (0.5, 1.5 …) and re-renders each frame at the target size, so vectors, text and shapes stay sharp; raster images resample with LANCZOS. GIF exports accept `colors` (2–256 palette entries, default 256; fewer colors share one palette across frames) and report `bytes`, with a `warnings` entry above 1 MB. Fully opaque GIFs are stored as frame differences without changing how they look. Pixel budgets apply to the entire scaled sequence and the sheet canvas before allocation. Existing output files are never overwritten. Exporting does not change the document. Python: `project.export_animation(path, format="sheet", scale=1, columns=3)` or `project.export_animation(path, scale=0.5, sampling="smooth", colors=64)`; `project.render_frame(name, scale, sampling)`. CLI: `vixl export-animation --out walk.gif --scale 0.5 --sampling smooth --colors 64`. MCP: `vixl_export_animation(animation=, scale=, sampling=, colors=, quality=)` writes inside the configured workspace; `vixl_animation_preview(name, scale, sampling)`. REST: GET `/animation/frame/{name}?scale=0.5&sampling=smooth`, POST `/animation/export` with `{format, animation, scale, sampling, colors, quality, columns}`. Ordinary PNG export via `vixl_export_file` also accepts `sampling="nearest"`.

## Named animations: idle, walk and wave in one document

Saved frames are a pool. A **named animation** plays a subset of that pool with its own order, timing and loop, and exports on its own. One document can therefore hold `idle`, `walk` and `wave` and write `keeper-idle.gif`, `keeper-walk.gif` and `keeper-wave.gif` without copying the document or deleting frames.

```bash
vixl animation-set --name idle --order idle1 idle2
vixl animation-set --name walk --order walk1 walk2 walk3 walk2 --duration 100 --loop 0
vixl animation-set --name wave --order wave1 wave2 --durations 250 250
vixl animation                                           # frames, plus each animation's order and timing
vixl export-animation --out keeper-idle.gif --animation idle --scale 8
vixl export-animation --out keeper-walk.mp4 --animation walk --scale 8
vixl export-animation --out keeper-sheet.png --format sheet --columns 8   # every frame + JSON naming the animations
vixl animation-set --name wave --delete                  # the saved frames stay
```

```json
{"type": "animation-set", "name": "walk", "order": ["walk1", "walk2", "walk3", "walk2"], "duration": 100, "loop": 0}
```

- `animation-set` with `name` and `order` defines (or replaces) the animation. `order` lists saved frames in play order: any subset, in any order, and a frame may repeat (the ping-pong `walk1 walk2 walk3 walk2`) or belong to several animations.
- Timing: without `duration`/`durations` each entry plays for its saved frame's duration. `duration` sets one value for every entry; `durations` gives one per entry of `order`. Values are 10–60,000 ms in multiples of 10. `loop` is the number of additional repetitions (0 = forever) and defaults to the document's loop.
- `animation-set --name N` with only `loop`, `duration` or `durations` updates an existing animation; `--delete` removes one. Redefining with `order` replaces the old timing and loop.
- Animations store frame names, not snapshots. `frame-save` over an existing frame keeps the animations that play it; `frame-delete` refuses a frame an animation still uses (redefine or delete the animation first, in the same batch if you like). Limits: 64 animations of up to 1,024 entries.
- The unnamed default animation is unchanged: every saved frame in saved order. `animation-set --order` without a name still reorders it and still has to list every saved frame (its error now points at named animations). Documents without named animations behave and export exactly as before.
- `export-animation --animation NAME` (MCP `vixl_export_animation(animation=)`, REST `{"animation": NAME}`, Python `export_animation(path, animation=NAME)`) writes that animation's frames, order, timing and loop. Without `animation` every saved frame plays in saved order, as before. An unknown name lists the defined animations.
- Formats: `gif`, `apng`, `webp`, `mp4`, `webm` and `sheet`; the format follows the file extension. WebP is lossless with `nearest` sampling and uses `quality` (1–100, default 90) for `smooth` renders. MP4/WebM need `ffmpeg` and also use `quality`. Video has a constant frame rate, so frames repeat on a tick equal to the greatest common divisor of the durations (400 ms and 120 ms frames share 40 ms, 25 fps; the limits are 100 fps and 36,000 output frames). The loop count is not stored in video, MP4 flattens transparency onto white, and WebM keeps alpha.
- Sprite sheets hold the distinct frames of the selection in order of first use (every saved frame when no animation is named). The JSON keeps the `frames` rectangles with each frame's saved duration and adds `animations`: for every named animation (only the exported one with `--animation`), its resolved `loop`, `total_duration` and its sequence of `{name, duration}` entries, which refer to the `frames` rectangles by name. A document without named animations writes the same JSON as before.

```json
{"width": 64, "height": 32, "loop": 0,
 "frames": [{"name": "idle1", "duration": 400, "x": 0, "y": 0, "width": 32, "height": 32}, "…"],
 "animations": {"idle": {"loop": 0, "total_duration": 800,
                         "frames": [{"name": "idle1", "duration": 400}, {"name": "idle2", "duration": 400}]}}}
```

## Editing every frame at once

A frame is a full snapshot, so a shared change (a recoloured coat, a hidden prop, a new effect) used to mean loading each frame, editing it and saving it back. `frames-edit` runs a list of ordinary operations against every saved frame in one step:

```json
{"type": "frames-edit", "operations": [
  {"type": "pixel-palette", "target": "upper", "colors": {"Y": "#d93a2b", "y": "#9c2320", "h": "#f58a6e"}}]}
{"type": "frames-edit", "animation": "walk", "operations": [{"type": "hide", "target": "lantern"}]}
{"type": "frames-edit", "frames": ["idle1", "idle2"], "scene": true, "operations": [{"type": "opacity", "target": "shadow", "value": 0.6}]}
```

```bash
vixl frames-edit --operations '[{"type":"pixel-palette","target":"upper","colors":{"Y":"#d93a2b"}}]'
vixl frames-edit --animation walk --scene --operations '[{"type":"hide","target":"lantern"}]'
```

- `operations` (1–200) are normal operations, and any type works: a palette swap, `pixel-draw`, `hide`, `move`, an effect, a swatch or variable edit. Layers are found by name or ID inside each frame, so a frame that lacks the target layer fails the edit; list the frames that have it with `frames`, or use `animation`.
- Targets: every saved frame by default, an `animation` (that named animation's distinct frames), or the listed `frames`. Not both.
- `scene: true` also applies the operations to the working scene (default false). Use it to keep the scene in step, so the next `frame-save` does not bring the old colors back.
- Atomic: any failure (a missing layer, an invalid value, or a later operation in the same batch) leaves the document and every frame untouched. The error names the frame and the nested operation, for example `frames-edit on frame 'walk3', operations[0] (hide): Layer 'lantern' does not exist`. It combines with other operations in one `vixl_operations_apply` batch, previews with `dry_run`, and undoes as one history step. Compact results list the changed frame names.
- Not allowed inside it: animation operations (`frame-*`, `animation-set`, `frames-edit`), `layout-apply`, `template-apply`, `page`, and filesystem fields (`path`, `linked`, `font`), the same restriction services apply to every operation. AI planners cannot propose `frames-edit`.
- Per-frame differences are untouched: each frame keeps its own pose layers, visibility and offsets, and only what the operations change is changed. The work is bounded: operations × frames ≤ 20 × the batch operation limit.

### Why frames are still snapshots

The storage model did not change: a frame holds the complete scene state, not references to shared layers plus per-frame differences. Snapshots keep each frame self-contained (it renders without the working scene or its neighbours, `frame-apply` restores it exactly, and archives from earlier versions load unchanged), keep operations, validation and history deltas simple, and cost little on disk because the archive is compressed and frames mostly repeat each other: a 32×32 document with seven pixel layers of random pixels (a worst case for compression) is 6.3 KB with one frame, 8.5 KB with eight and 39.8 KB with sixty-four (about 0.5 KB per frame), and a `frames-edit` over those sixty-four frames takes about 0.2 s. The cost is that a shared edit must reach every frame, which `frames-edit` now does in one step, and that a shared layer you redraw must be redrawn with the same operations in each frame. Named animations and `frames-edit` address frames by name, so they would keep working if a later version adds shared layers with per-frame overrides.

Run `python examples/build_sprite.py --output DIR` for an editable animated potion, GIF/APNG previews and a game-ready sprite sheet.
