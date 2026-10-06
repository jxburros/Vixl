# T13 round 2: Vixl lane (claude-V)

Changes asked for: make the raincoat red, and add a 2-frame `wave` animation (250 ms per frame) after
the walk frames. The sheet becomes 256x32, the JSON lists the new frames, and there is a new
`keeper-wave.gif`. Everything here was made with the Vixl MCP tools. I did not draw any pixels outside
Vixl, and nothing outside `round2/` was changed.

## What I did

1. I copied `../keeper.vixl` to `round2/keeper.vixl` and opened the copy, so the round-1 source stays as it was.
2. **Red raincoat:** I ran one `frames-edit` (with `scene: true`) that wraps a `pixel-palette` on the
   `body` layer. This recolours the coat in all six saved frames and in the working scene, and the
   pixel grid stays the same.
   - coat `Y` #f4c430 -> **#d23a2c**
   - coat shadow `y` #c98e16 -> **#8e1f1c**
   - coat highlight `L` #fff09a -> **#f47a5e**
   - The outline, skin, trousers, boots and lantern colours are unchanged.
3. **Wave:**
   - I used `frame-apply idle1` to start from the standing pose.
   - I added two new `pixel-art` layers, `arm-wave-a` and `arm-wave-b`. Each one is a raised back arm
     (dark red sleeve and a skin-tone hand), and I used `reorder` to put both behind `body`.
     - In `a`, the arm angles up and out behind the hood.
     - In `b`, the arm is more upright.
   - Switching between the two layers makes the side-to-side wave. The keeper still holds the lantern
     in the front hand, and the legs stay in the standing pose.
   - I saved the frames with `frame-save` as `wave1` and `wave2`, each 250 ms. I then defined
     `animation-set name=wave order=[wave1,wave2] duration=250 loop=0`.
4. **Exports** (`vixl_export_animation`, sampling=nearest):
   - `keeper-sheet.png` + `keeper-sheet.json`: format=sheet, columns=8, scale 1. The sheet is 256x32.
     Frames from left to right are idle1, idle2, walk1-4, wave1 (x=192) and wave2 (x=224). The JSON
     lists all 8 frames with their durations, and its `animations` object now has `wave`
     (total 500 ms) next to `idle` and `walk`.
   - `keeper-wave.gif`: animation=wave, scale 8. It is 256x256, 2 frames of 250 ms each, and loops forever.
   - `keeper-idle.gif` and `keeper-walk.gif`: re-exported at scale 8 so they have the red coat. Their
     timing is the same as in round 1 (2x400 ms and 4x120 ms).
   - `keeper.vixl`: the updated editable source. It has the 2 new layers, frames wave1/wave2 and the named animation `wave`.

## Checks (read-only Pillow script plus an 8x preview I looked at)

- The sheet is 256x32 RGBA, and every alpha value is 0 or 255.
- The sheet has 13 opaque colours, and none of the old yellows are left.
- For each of the six old frames, the alpha mask is identical to the round-1 sheet. Only the colour changed.
- In all 8 frames the lowest opaque row is row 30, so the baseline is the same as before.
- I checked the three GIFs: loop=0, durations [400,400], [120x4] and [250,250]. When I downsample
  each GIF frame to 32x32, it matches the matching sheet frame exactly.

## Notes / unsure about

- At 32 px the wave is a simple two-pose flick of a raised back arm. In `wave2` the arm's outline
  sits next to the hood's outline for a few rows, so that part reads as a slightly thicker dark edge.
- The wave frames use the idle1 body position, so there is no breathing bob while waving.
- One Vixl detail: `pixel-art` refuses `width` when `rows` are given, because the rows set the size.
  The sheet export result again reports `"size":[32,32]` (the frame size), but the file itself is 256x32.
