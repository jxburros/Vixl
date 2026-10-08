# Field notes: AI packet animations (Vixl 0.23.0)

Running log, written while building `build.py`. Python API (`from vixl import Project`) plus the `vixl` CLI
for checks; MCP server was not available this session.

## Setup / reading
- Docs read: skills/vixl/SKILL.md, references/brushes-timeline.md, docs/animation-authoring.md,
  docs/brushes-and-animation.md, docs/media-craft.md, `vixl guide looping-motion|natural-motion|character-rigging`.
- Docs are dense but complete; the timeline reference in brushes-timeline.md is the most useful single page.
- `vixl schema` has no per-operation filter (`vixl schema pen` prints the whole 10k-line batch schema);
  I wrote a 15-line helper to print one operation's fields. A `vixl schema OP` would save agents a lot of tokens.
- Schema oddity: `motion.phase` is "Cycle offset in turns (radians for wiggle)" - one field, two units.
- `keyframes` (array form) takes no `targets`, unlike `keyframe`/`animate`/`animate-preset`.

## 1. Neural network loop (`neural-network.*`)

Built from ~60 pen wires, 26 trimmed "signal" pens (`trim_start`/`trim_end` worms), and halo/ring/core ellipses per
node, all keyed with explicit `keyframe` ops (hold easing between firings). 4.8 s seamless loop, two waves.

Worked well
- Trim-path worms (animate `trim_end` then `trim_start` 170 ms later, `line_cap: round`) look exactly like
  After Effects trim paths. Equal trim values draw nothing, so a worm can sit "parked" invisibly at 100/100.
- `hold` easing + `timeline-set close: true` closed ~300 tracks in one op.
- `layer-style outer-glow` with `targets` over 26 layers in one op.
- Warnings when keys extend the timeline are clear and name the layer (`timeline duration changed 4400 -> 4450 ms:
  a keyframe on 'n3-1-halo' sits at 4450 ms, past the end...`). Caught my own maths errors twice.

Rough edges / bugs
- **`stroke_color` is listed as animatable but fails on shapes**: `keyframe property: "stroke_color"` on an ellipse
  with a stroke -> `Layer 'n1-1-halo' has no 'stroke_color' to animate`. The shape stores `stroke`; using
  `property: "stroke"` works. The property list (docs + schema) offers both with no hint which layer types use which.
- `gradient` has no centre/radius for radial (`Unknown field(s) 'center', 'kind', 'radius'`); I positioned an
  oversized radial gradient layer instead. `text` has no tracking/letter-spacing field.
- **Misleading motion check: 93 `loop-seam-speed` findings for invisible jumps.** A worm parks at
  trim 100/100 with `easing: hold`, then `close: true` appends 0 at the loop end. The check reports
  `trim_end on 's0-n0-0-n1-1' matches at the seam but its speed changes from 35.7 to -2500 units/s there`.
  The segment leaving the last real key is a `hold`, so there is no motion to kink, and trim 100/100 and 0/0
  both draw nothing. Two problems: a hold-into-close is treated as a 2500 u/s ramp, and the check does not know
  equal trims are invisible. 93 identical informational lines bury anything real; no grouping/dedup.
- **GIF `colors=64` drops the accent hues entirely.** On this navy piece, cyan (93,232,210) nodes and signals came
  out grey (170,193,204) and violet became white-ish. Sampled one pixel at t=780 ms: colors 64 -> (170,193,204),
  96 -> (134,165,178), 128 -> (92,158,165), 192 -> (135,207,205), 256 -> (86,210,195). The shared palette is
  median cut over a frame montage (animation.py:271), so small saturated accents lose to large dark areas.
  The docs recommend `colors=64` to shrink GIFs; on dark UI-style art that wrecks the colour. Had to go back to 256.
  The export warning then said "band in 256 colors" even though I had passed `colors=64`.
- `export_timeline(start=780, end=850, fps=15)` -> `Frame rate exceeds the animation format timing resolution;
  lower fps`. Real cause: the range is not a multiple of the frame step, so the last frame is ~3 ms long. The
  message points at the wrong knob.
- GIF at 15 fps stores 70 ms frames: 72 x 70 = 5040 ms for a 4800 ms loop (5% slow). It's a GIF centisecond limit,
  but it isn't reported anywhere; 20 fps (50 ms) or 10 fps (100 ms) would keep the timing exact.

Times
- Contact sheet of 16 frames at 1080: ~10.5 s. MP4 export 1080x1080, 144 frames: **79.5 s** (0.55 s/frame,
  ~300 vector layers with glow); 251 KB. GIF 540 px 15 fps: 18 s.

## 2. Kinetic type "Ask. Iterate. Verify." (`kinetic-ask-iterate-verify.*`, instagram-portrait 1080x1350)

text-animate `typewriter` (kicker), `pop` (Ask), `slide-left` (Iterate), `fade-up` (Verify, tagline per word),
`color-sweep` per word colour; `draw-on` icons (speech-bubble shape, open arc path, ellipse ring, check pen),
`pop-in` arrowhead, staggered `pulse` over three icon groups (`targets` + `stagger`), markers used as `start`
times, one group-level fade-out, WebP with `poster: "5.5s"`.

Worked well
- text-animate is excellent: one editable text layer, crisp per-char motion, markers as start times, stagger in
  ms. `pop` with `ease-out-back` and `slide-left` look professional with no tuning.
- `draw-on` on a closed `speech-bubble` shape and on an ellipse just works (starts at top / 12 o'clock as documented).
- `poster: "5.5s"` on WebP rotated the frames correctly (frame 0 = the finished card); WebP frame durations
  summed to exactly 7500 ms; identical frames merged (114 frames for 150 rendered).
- Grouping text-animated layers into a group and fading the group works (nested motion composes).

Rough edges / bugs
- **Seamless default makes a messy exit.** In `loop_mode: seamless` every entrance automatically played back
  ("in-out" default for text-animate, hold-and-play-back for draw-on/slide presets). With mixed presets the
  last 0.6 s became a jumble (kicker typing backwards, half-erased icons, words sliding out in different
  directions; see first contact sheet). I wanted one shared exit; that needed `mode: "in"` on every text-animate
  and `close: false` on every preset (an undocumented-but-working opt-out) plus a group opacity fade.
- **The loop-seam check ignores parent opacity.** With the whole card faded to 0 by its group at the end, the
  check still reports 15 `loop-seam` findings for children (`trim_end on 'icon-ask' ends at 100 but starts at 0`,
  `the text animation on 'ask' poses its letters differently at the loop end...`) and the export repeats them
  as warnings. The rendered comparison (`loop-seam-render`) would have shown the seam is clean, but per the docs
  it only runs "when no track reports loop-seam". Same result with `loop_mode` off and `loop: 0`.
- Warning wording: `text-animate color-sweep on 'ask' ends at rest but starts hidden` - colour-sweep never hides
  the text (it starts at the given `from` colour).
- **`empty-poster` missed an empty frame 0.** With the seamless in-out default, frame 0 *and* the last frame
  are blank, so "frame 0 shows under 10% of the layers visible at the end" never fires. A blank poster is exactly
  what the check is for; comparing against the busiest frame (or the middle) would catch it.
- `marker_size` is pixels (default 4 x stroke width) but the schema just says "Marker size." I passed 2.2
  thinking "multiplier" and got an invisible 2 px arrowhead.
- **Markers don't follow the trim.** With `marker_end` and `trim_end: 60` the arrowhead stays at the full path's
  end, floating detached from the visible stroke (repro: a pen line with `marker_end: triangle`, then
  `shape target: b trim_end: 60`). So draw-on with an arrowhead doesn't work; I drew the head as a separate pen
  and `pop-in`'d it when the arc finished.
- The marker on an `A` (arc) path end points along a wrong-looking direction (sits askew on the arc end).
- Editing a pen in place with `{"type":"pen","target":"b","trim_end":60}` fails with the unhelpful
  `{'type': 'pen', ...} is not valid under any of the given schemas`; `{"type":"shape","target":"b",...}` works
  (pen layers are shapes). `pen` also refuses `opacity` (`Unknown field(s) 'opacity' for 'pen'`) though `shape` takes it.
- A `shape: path` with `x: 0, y: 0` and canvas-coordinate path data gets a layer box from the origin to the path's
  far corner, so `moving-over-text` flagged it as crossing the kicker and two words it never touches. Fixed by
  writing the path in local pixels and placing it with x/y; the check's box-vs-ink test is coarse for paths.
- `text-mostly-hidden` (tagline hidden 56% of loop) is fair for a loop; I lengthened the hold to 7.5 s.

Times: contact sheet 3 s; MP4 225 frames 1080x1350: 34 s; WebP 540x675 20 fps: 14.5 s, 626 KB.

## GIF colour (affects every GIF here) - the biggest quality problem I hit

The shared GIF palette loses small saturated accents even at 256 colours. Robot GIF at default settings
(`colors=256`, `dither="auto"` -> ordered): the amber antenna light (255,196,35) came out as (241,220,208)
grey-beige, the coral heart as (175,140,190) mauve, cyan eyes as (128,216,214). The palette simply had no
colour near amber (checked `getpalette()` of the exported GIF).
Cause (animation.py ~265): the palette is median cut over a montage of at most 16 sampled frames that are
first box-reduced (`image.reduce(step)`), so a 15 px light is averaged into its dark surroundings before
quantizing, and median cut weights by pixel count anyway.
Repro: any dark scene with a small bright accent; `export_timeline(p, "x.gif", scale=0.5)`; sample the accent.
- `dither="none"` with 256 colours skips the shared palette (per-frame palettes) and keeps the hues
  (238,188,105 here; much closer), at about 2.2x the bytes (2 s clip: 233 KB ordered vs 524 KB none).
- WebP of the same clip: right colours, 199 KB.
- The banding warning steers you towards `ordered`, which is the setting that destroys the accents.
I export every GIF here with `dither="none"`.

## 3. Robot helper (`robot-helper.*`) - own artwork bound with `character parts`, front-view walk, baked wave

Own robot artwork (rounded rects, ellipses, an SVG smile; torso and head are groups) bound to the standard
part names, `character-rig` bones, `character-cycle walk view: front` toward the camera (wrapper group
scales 0.62 -> 1 with the shadow), then a wave, blinking eyes (`scale-y` keys), antenna `pulse` with
`repeat`, `speech-bubble` anchored to the antenna, caption text-animate.

Worked well
- Front-view walk (new in 0.23) reads right: feet lift alternately, body bobs, arms open a little. Combined
  with a scale-up it looks like the robot walks toward you. No `front-view-leg-swing` finding.
- Parts can be groups (torso = neck+body+panel+heart; head = antenna+ears+shell+visor) and they ride along
  with the body bob.
- `speech-bubble` is lovely: wraps, pads, and the tail tracks the anchor through the walk/scale.
- `character` check clean.

Rough edges / bugs
- **Bound artwork needs a full `character-rig` before any cycle** (`Character needs a rig before applying a
  cycle`), and **bone `origin` is in the character group's local frame**, which is not the frame you drew in:
  after `character` groups the parts, the group box starts at the top-left of the union (my ears/antenna), so
  origins in drawing coordinates put the arms 20-70 px off the shoulders (first contact sheet: arms floating
  beside the torso). Not documented ("root origin:[x,y]"). Workaround: read each upper limb's `x/y/width`
  back from the grouped layer and build origins from that.
- `character-rig` silently resets every bone layer's pivot to `[0.5, 0]`; I set the hands' pivot afterwards
  and re-posed with `character-pose angles: {}`.
- **No way to keyframe a pose / no gesture cycle.** Walk/run/idle/ride/react exist, but "wave" doesn't, and
  `character-pose` only changes the static rest pose. I baked the wave myself: `character-pose` at a time,
  read x/y/rotation of three arm parts, write keys, restore.
- **Baked chains come apart between keys.** The rig is flattened into independent x, y and rotation keys per
  part. With 10 baked poses (~220 ms apart, eased) the hand and forearm slid along chords instead of arcs and
  visibly detached from the elbow/wrist mid-wag (verified: at 4800 ms the hand was ~15 px off the wrist).
  Had to bake every frame (66 samples x 3 parts x 3 props). character-cycle avoids this by sampling ~24
  keys/period, but anyone keying a rig by hand will hit it.
- The cycle bobs the body with **absolute `y` keys** on the torso/head/face parts, so any later `y` animation
  of those parts collides with it; I moved the whole figure with a wrapper group instead.
- Loop/seam findings again flagged tracks hidden under a group fading to 0 (see piece 2).

Times: contact sheet 10 s; MP4 1080x1080 210 frames: **119 s**; GIF 540 px 20 fps: 33 s (999 KB, before the
dither change).

## 4. "How a chatbot predicts the next word" (`next-word-prediction.*`, 1920x1080, 10 s MP4)

Token chips (rounded rect + text placed with `within`) pop in with one staggered `animate-preset pop-in`;
a caret blinks (hold keys); four probability bars grow with `scale-x` from a left pivot (staggered,
ease-out-cubic); the winner's percentage turns cyan (`color` key); the chosen word's chip flies from the
winning row into the sentence (translate/scale keys, `top` so it passes over the rows); bars drain; round 2
swaps words and percentages with stepped `text` keys; outro caption with text-animate. Markers for rounds.

Worked well
- `text` keys (stepped) make it easy to reuse four rows for two rounds of candidates.
- `within` centres a word in its chip in one field; `pivot: left` + `scale-x` is a clean bar-grow.
- The `moving-over-text` check caught a real stacking mistake: the flying chip passed *under* the next
  row's label (`'cand0' moves over the text 'tok5-word' between 3.542s and 3.542s`). Fixed with `top`.
- `text-hidden-at-poster` caught that the title faded in from 0 (bad MP4 thumbnail). Fixed.

Rough edges
- Pitfall (documented, but bit me): a track holds its first key's value *before* that key, so adding round-2
  `text` keys at 5.4 s replaced the round-1 words from t=0 (first contact sheet showed `.`, `and`, `while`
  for round 1). For stepped `text` this is particularly surprising; it needs an explicit key at 0.
- No measure-text helper before creating a layer; I measured words in a throwaway Project with
  `inspect()["width"]` to size the chips (inspect has `width`, `ink_bounds` - useful once you find them).
- **Loop-seam check depends on `loop: 0` only.** With `loop: 0` the one-shot explainer got 17 `loop-seam`
  findings (chips "end at 1 but start at 0"); with `loop: 1` (which still plays twice in a GIF) they all
  vanish. There's no "play once / not a loop" setting, so a non-looping MP4 has to pretend `loop: 1`.

Times: contact sheet 4 s; MP4 300 frames 1920x1080: 53 s, 247 KB.

## 5. "AI-curious" sticker (`ai-curious-badge.*`, 800x800 transparent, 2.4 s seamless)

18-lobe `seal` shape with `motion spin symmetry: 18`, word group `wiggle` on rotation, `line-boil` on a
cyan ring, four `sparkle` shapes pulsing via one `animate-preset` with `targets`, `repeat: 2`, `stagger: 300`.

Worked well (all new-in-0.23 loop features behaved exactly as the changelog says)
- `wiggle` without `duration` lasted the loop and closed it, with a clear warning:
  `wiggle frequency 0.6 -> 0.416667 per second, so 1 whole cycle(s) close the 2400 ms loop`.
  (It rounds *down* to 1 cycle; 1.44 cycles -> 1, so the rock got slower than asked. Nearest might be kinder.)
- `line-boil` lasted the loop: `line-boil holds each drawing 133 ms (7.50 redraws per second, not 8) so 6 whole
  cycle(s) of 3 drawings close the 2400 ms loop`.
- Staggered repeat wrapped instead of lengthening: `spark1.scale: the 300 ms stagger would run past the
  2400 ms loop, so its keys wrap around the loop instead` (reported under `normalized`).
- `spin` + `symmetry` seamless. `vixl check --checks motion`: 0 findings; the GIF loops cleanly.

Rough edges
- **Transparent WebP is 2-3x bigger than opaque and `quality` barely helps it**: 480 px, 58 frames:
  q90 2227 KB transparent vs 1102 KB on a background; q75 1807 vs 716; q60 1719 vs 633. Alpha seems to be
  stored losslessly. The GIF size warning quoted "WebP 776,144 bytes for these frames", but that trial is
  not comparable with what a transparent WebP export actually writes.
- `target_bytes=600000` on the GIF worked (chose `colors: 64, fps: 12`, 4 tries, 4 s) but: (a) dropping to 64
  shared colours brings back the accent-loss problem above, (b) 12 fps = 83.3 ms frames, which GIF can't
  store exactly, (c) the warning then still says "band in 256 colors ... pass dither: 'ordered'".
- `drop-shadow` style on a spinning layer: fine, the shadow stays below (applied after the transform).

Times: sheet 5 s; WebP 400 px q75: 14 s (1.47 MB); GIF 320 px: 9 s (1.1 MB).

## Crash: GIF export with merged frames + size warning (IndexError)

Full rebuild died in the robot GIF export:
```
File "src/vixl/animation.py", line 339, in webp_trial
    return len(save_webp(images, durations, loop, quality=75, method=0))
File ".../PIL/WebPImagePlugin.py", line 263, in _save_all
    timestamp += duration[frame_idx]
IndexError: list index out of range
```
Minimal repro (64x64, 1 s, 10 fps, a ball that stops moving at 400 ms so trailing frames are identical):
```python
p = Project(64, 64, "#ffffff")
p.apply([{"type": "timeline-set", "duration": 1000, "fps": 10},
         {"type": "shape", "name": "b", "shape": "ellipse", "width": 20, "height": 20, "x": 0, "y": 20, "fill": "#f00"},
         {"type": "animate", "target": "b", "property": "x", "from": 0, "to": 40, "start": 0, "duration": 400}])
export_timeline(p, "rep.gif", max_bytes=10)   # IndexError; same with duration 1000 (no merged frames) -> ok
```
Cause: timeline.py ~1494 replaces `durations` with the merged frame durations (`durations = written`) but the
size warning's `webp_trial(images, durations, loop)` still gets the unmerged `images`; `webp_trial` only catches
OSError/ValueError. Any GIF > 1 MB (or over `max_bytes`) with a hold (identical consecutive frames) crashes
instead of exporting. My earlier robot GIF was 999 KB, so it slipped under the threshold; switching to
`dither="none"` pushed it over. Workaround in build.py: pass a large `max_bytes` (the gradient warning path
does not call the WebP trial).

## Final verification
- Seams measured on the MP4s (mean abs RGB diff of last vs first frame at 270 px, against the median
  frame-to-frame step): neural 0.46 vs 0.79, robot 0.84 vs 1.35, kinetic 0.00 vs 0.48. No jumps; the largest
  steps are the intended pop-ins and fades.
- GIF durations exact at 20 fps (neural 96 frames = 4800 ms, robot 7000 ms, badge 2400 ms); WebP 7500 ms.
- Output total 8.8 MB (`out/`), including five .vixl sources.

## Features looked at but not used (and why)
- `camera`, `layer-depth`, `lighting`, `particles`: nice, but every piece here is flat UI-style
  graphics; particles would have fought the readable text, and lighting is rasterized on vector export.
- `audio-track` / synth score: the MP4s are meant for slides and social autoplay (muted); skipped.
- `character-lipsync`: the robot has a fixed smile on a visor; viseme mouths didn't fit the design.
- `cut-paper`: wrong look for this packet.
- `keyframes sample` (sin/noise waves): `motion wiggle` and `pulse` with `repeat` covered it. Briefly tested
  `motion bounce`: contact keys landed on the frame grid (550, 1250, 1750, 2050 ms at 20 fps), as 0.23 says.
- `vixl_timeline_preview(thumbnail=360)` is MCP-only; via Python I used `contact_sheet(times=...)`.
- `preset: chat|web|email` and `target_bytes`: tested target_bytes (works, see badge notes); presets skipped
  because they reduce colours, which damages accent colours (see GIF colour section).
- APNG and sprite-sheet export: not needed.

## Render/export times (this machine, Python API, single process)
| step | time |
| --- | --- |
| neural MP4 1080x1080, 144 frames (~300 vector layers + glow) | 80-105 s |
| robot MP4 1080x1080, 210 frames | 119-157 s |
| next-word MP4 1920x1080, 300 frames | 53-78 s |
| kinetic MP4 1080x1350, 225 frames | 34-55 s |
| neural GIF 432 px 20 fps | 37 s |
| robot GIF 432 px 20 fps | 40 s |
| badge WebP 320 px, transparent | 21 s |
| 16-frame contact sheet at 1080 | 3-19 s |
| whole build.py | about 9-10 min |
MP4 export is ~0.4-0.75 s per 1080p frame; nothing seems cached between the contact sheet and the MP4 render
of the same document, and nothing runs in parallel. For iterating, `QUICK=1` in build.py skips exports.

## Summary: what worked well overall
- Trim-path draw-on, text-animate kinetic type, `speech-bubble`, front-view walk, and the 0.23 seamless-loop
  helpers (wiggle/line-boil closing the loop, stagger wrapping) all did what the docs say, first try.
- Warnings are specific and actionable (timeline lengthened by which layer, wiggle frequency rounded to what).
- One-op multi-target animation (`targets` + `stagger` + `repeat`) saves a lot of code.
- The motion check found two real problems (stacking order of a flying chip; a hidden title on the poster).

## Summary: what needs work (priority order)
1. GIF crash: IndexError in the size-warning WebP trial when frames merge (repro above).
2. GIF shared palette drops small saturated accents even at 256 colours; `colors=64` makes it much worse,
   and the warnings recommend `ordered`, which is the setting that causes it.
3. Loop-seam check noise: ignores parent-group opacity and invisible equal trims; treats hold-into-close as a
   speed kink; 93 identical informational lines; only runs for `loop: 0`; `empty-poster` misses a blank
   frame 0 when the last frame is blank too.
4. Rig ergonomics: bone origins in an undocumented group-local frame; no keyable pose/gesture; baked
   chains separate between keys unless baked per frame.
5. Markers (`marker_end`) ignore stroke trim; `marker_size` units undocumented; arc-end marker angle.
6. `stroke_color` listed as animatable but shapes need `stroke`.
7. Seamless default turns every entrance into an automatic exit (jumbled ending with mixed presets);
   needs `mode: in` / `close: false` everywhere to opt out.
8. Transparent WebP sizes 2-3x opaque, `quality` barely affects it.
9. Smaller: `vixl schema` without per-op filter; pen in-place edit error message; `text` has no tracking;
   radial gradient has no centre; misleading "lower fps" error for a range that isn't a frame multiple.
