# Brushes and animation timelines (0.13)

## Painting

Strokes live on paint layers as data (points, pressure, brush, size, color, seed), so they stay editable, undoable and resolution-independent.

```text
vixl_brushes_list()
vixl_operations_apply(operations=[
  {"type":"paint-layer","name":"sketch"},
  {"type":"paint","target":"sketch","brush":"ink","points":[[80,400],[240,300,0.5],[420,380,1],[600,320]],"size":10,"color":"@ink"},
  {"type":"paint","target":"sketch","brush":"watercolor","path":"M60 700 C300 560 700 820 1000 660","size":90,"color":"alpha(@accent, 0.8)","seed":3},
  {"type":"paint","target":"sketch","brush":"round","points":[[500,0],[500,900]],"size":40,"mode":"erase"}
])
```

- Brushes: `round`, `soft-round`, `airbrush`, `pencil`, `ink`, `fineliner`, `brush-pen`, `marker`, `highlighter`, `calligraphy`, `chalk`, `charcoal`, `crayon`, `watercolor`, `dry-brush`, `spray`, `splatter`.
- Points are canvas pixels `[x, y]` or `[x, y, pressure]`; or give `path` (SVG M/L/H/V/Q/C/Z). Points are smoothed (Catmull–Rom) and resampled; a few well-placed points make a smooth curve.
- `settings` overrides a preset for one stroke: `{"hardness":0.3,"taper":[0.2,0.4],"texture":"paper","texture_strength":0.6,"jitter":0.05,"flow":0.3,"build":"accumulate"}`. Unknown keys are rejected with the allowed list.
- `brush-define` saves a custom brush: `{"type":"brush-define","name":"my-ink","base":"ink","settings":{"hardness":0.5}}`.
- `paint-clear` with `last: N` undoes strokes on one layer; `undo` works too. Without `target`, `paint` continues the active paint layer or creates `paint`.
- Same `seed` = same texture/jitter. Keep separate layers for line art, color and texture so they can be reordered, masked and blended.

## Timelines

```text
vixl_operations_apply(operations=[
  {"type":"timeline-set","duration":"4s","fps":30,"loop":0},
  {"type":"animate-preset","target":"headline","preset":"slide-in-up","duration":"0.8s"},
  {"type":"animate-preset","target":"cta","preset":"pop-in","start":"0.7s","duration":"0.5s"},
  {"type":"animate","target":"logo","property":"rotation","to":360,"start":0,"duration":"4s","easing":"linear"},
  {"type":"keyframe","target":"badge","property":"fill","time":"2s","value":"@accent"},
  {"type":"animate-preset","target":"canvas","preset":"color-shift","to":"#1e1b4b","duration":"4s"},
  {"type":"marker","name":"reveal","time":"1.5s"}
])
vixl_timeline_preview(count=8)          # contact sheet: check motion before exporting
vixl_timeline_preview(time="reveal")
vixl_export_timeline(path="promo.webp", scale=0.5)     # .gif .png(APNG) .webp .zip(frames) .mp4/.webm (ffmpeg)
vixl_export_timeline(path="sprites.png", format="sheet", columns=6)
```

- Properties: `x`, `y`, `translate-x`, `translate-y`, `opacity`, `rotation`, `scale`, `scale-x`, `scale-y`, `width`, `height`, `size`, `spacing`, `color`, `fill`, `start`, `end`, `stroke_color`, `stroke`, `trim_start`, `trim_end`, `text`, `visible`, `effect:ID` (or `effect:1`), and canvas `background` (`target: "canvas"`).
- Draw-on: `trim_start`/`trim_end` (0–100 %) trim the stroke of a `shape`/`pen` layer along its outline. `{"type":"animate-preset","target":"wave","preset":"draw-on","duration":"1.2s"}` draws a line on (`draw-off` erases it); animate `trim_start` and `trim_end` together for a travelling worm. Set `line_cap: "round"` on the layer for round ends; only the stroke is trimmed, the fill stays. Works in stills, GIF/WebP/MP4 and SVG (PDF/PPTX rasterize the layer).
- Mirroring: `scale`, `scale-x`, `scale-y` accept negative values (`-1` mirrors that axis about the pivot, center by default). Animate `scale-x` from `1` to `-1` to swing a layer over (a beam that sweeps back and forth, a card flip); it is edge-on at 0. Works in stills, GIF/WebP/MP4 and SVG. Static: `{"type":"scale","target":"beam","x":-1}`.
- Characters: one layer per part, `{"type":"pivot","target":"arm","value":[0.5,0.05]}` at each joint (or `"top"`, or `units:"px"`), then rotate/animate `rotation` — the joint stays fixed. Group parts (`group`, nested for limbs) and animate the group's `translate-x/y`, `rotation`, `scale` to move the whole figure about its pivot; groups do not clip, so swinging limbs stay visible. `targets:["arm-l","arm-r"]` on `animate`/`animate-preset`/`keyframe` gives several parts the same keys.
- Prefer `translate-x/y` and `scale` for motion: they offset/scale from the layer's laid-out position, so constrained layouts keep working. Absolute `x`/`y` keys pin the position.
- Time: ms number, `"1.5s"`, `"250ms"`, `"50%"`, or a marker name. A key's `easing` shapes the segment *after* it. Default for `animate` is `ease-in-out`.
- Easings: `linear`, `hold`, `ease`, `ease-in`, `ease-out`, `ease-in-out`, `ease-{in,out,in-out}-{sine,quad,cubic,quart,expo,back}`, `bounce-in`, `bounce-out`, `elastic-out`, `spring`, `cubic-bezier(a,b,c,d)`, `steps(n)`.
- Presets: `fade-in/out`, `slide-in-{left,right,up,down}`, `slide-out-{…}`, `pop-in/out`, `zoom-in/out`, `spin`, `pulse`, `shake`, `bounce`, `float`, `blink`, `typewriter`, `color-shift` (`to`), `draw-on`/`draw-off`. Tune with `amount`, `distance`, `easing`, `fade:false`.
- `animate` without `from` starts at the current value. A key placed past the end lengthens the timeline; the apply result's `warnings` report it (`timeline duration changed 8000 -> 8400 ms`) and only keys the operation just set count, so a duration set back with `timeline-set` stays. Pass `extend: false` (CLI `--no-extend`) to keep the duration and leave the key past the end, where it shapes the last frames but is not played. Removing a layer removes its tracks; `keyframe-remove` deletes a track or one key.
- The document itself is the frame at rest: rendering without `time` shows untouched layers. Use `time=` on previews/exports to see a moment.
- Motion craft: entrances 300–800 ms with ease-out, exits faster with ease-in, stagger related items by 80–150 ms, keep a strong final frame. Check with the contact sheet.
- In-memory formats (GIF/APNG/WebP/sheet) are bounded; use `scale`, lower `fps` or `start`/`end`, or export `frames`/MP4 for long, large animations.
- `scale` (0.05–16) renders frames at the target size, so `scale=2` is crisp, not upscaled.
- Loops: `timeline-set loop_mode:"seamless"` warns about tracks that end differently from how they start; `close:true` (timeline-set/keyframe/animate/animate-preset/motion) appends the t=0 value at the end (entrances hold, then play back; rotation closes mod 360). `motion recipe:"spin"` with `symmetry:12` turns one ray period over the timeline for a seamless rotating sun; whole `turns` only. Matched speed at the seam holds for linear or ease-in-out segments only.
- `animate`/`animate-preset` take `repeat` or `until`, `period`, and with `targets` a `stagger` (ms between targets): one operation for a typing-dots loop. Hold keys: `easing:"hold"`.
- `vixl_check` adds the `motion` check when a timeline exists: `loop-seam`, `empty-poster`, `text-hidden-at-poster`, plus legibility of frame 0.
- Poster frame: `vixl_export_timeline(poster="end")` puts that frame first in GIF/WebP/APNG (loop stays seamless) and warns when it is empty. `vixl_timeline_preview(thumbnail=360)` shows poster/middle/last at phone width; `times=[...]` picks frames; frame 0 is labelled "poster".
- Export results report the written file: sheet `size`, and GIF/WebP/APNG `frames` after identical frames merged (`rendered_frames` = rendered).
- GIF: `dither` auto/none/ordered/floyd (shared palette; ordered never shimmers), `max_bytes` soft target. Results include `bytes` and a `warnings` entry above 1 MB or max_bytes that suggests MP4/WebP with a measured WebP size (gradient GIFs get it at any size). `target_bytes` fits timeline GIF/WebP/APNG to a size (colors or WebP quality, then fps, then scale; reports `chosen`), and `preset` `chat`/`web`/`email` sets fps, width, colors and target_bytes. `colors=64` (2–256) plus lower `fps` shrink GIFs a lot (728×90, 4 s banner: 190 KB default → 41 KB with `colors=32, fps=10`); prefer WebP/MP4 where accepted.
- Frame snapshots (`frame-save`, `vixl_export_animation`) work at any canvas size within the pixel budget; `sampling="smooth"` allows scales like 0.5 or 1.5 for illustrated (non-pixel-art) frames.
