# T13 Pixel-art sprite: claude-V (Vixl lane)

Timing: started 22:20:09 UTC, finished 22:25:01 UTC on 2026-10-05 (about 5 minutes). 23 tool calls, including the REPORT write and the handback.

## Files

| File | How it was made |
| --- | --- |
| `keeper.vixl` | Editable Vixl source, created with `vixl_document_create` (32x32, transparent). It has 7 pixel-art layers, all written with `pixel-art` `rows` operations: `upper` (hood, face, raincoat, arm), `lantern`, and the leg layers `legs-idle`, `legs-a`, `legs-b`, `legs-c`, `legs-d`. Six frames were saved with `frame-save`: idle1 and idle2 at 400 ms, walk1 to walk4 at 120 ms. Between saves, layers were moved, shown and hidden. The animation order lists all six frames, with loop 0. |
| `keeper-sheet.png` | `vixl_export_animation(format="sheet", columns=6, scale=1, sampling="nearest")` from `keeper.vixl`. It is 192x32 RGBA: idle1, idle2, walk1, walk2, walk3, walk4 from left to right. |
| `keeper-sheet.json` | Written by the same sheet export. It has a `frames` list giving each frame's name, x, y, width, height and duration in ms, plus the sheet's width and height and `loop: 0`. |
| `keeper-idle.gif` | `vixl_export_animation(format="gif", scale=8, sampling="nearest")` from `keeper-idle-anim.vixl`. It is 256x256 and loops forever (loop=0). It has 2 frames at 400 ms each. |
| `keeper-walk.gif` | Same export, from `keeper-walk-anim.vixl`. It is 256x256 and loops forever. It has 4 frames at 120 ms each. |
| `keeper-idle-anim.vixl`, `keeper-walk-anim.vixl` | Copies of `keeper.vixl`, made with `cp`. In each copy, the other animation's frames were removed with `frame-delete`, and `animation-set` was then used to set the order. |

## Design
- Side view, facing right. The keeper wears a yellow raincoat with the hood up; the face shows in the hood opening and has one eye. A sleeve reaches forward to the hand. The navy trousers are mostly hidden by the coat, the boots are dark brown, and the lantern (metal frame, glowing glass, red base) hangs below the hand.
- Palette: 15 opaque colors plus transparency, so the 16-color limit holds even if transparency is counted. There is one dark outline color, #1e1b2e, and every part is outlined in it.
- Idle: in frame 2 the upper body drops 1 px (the breathing bob), and the lantern moves 1 px right and 1 px down (the sway).
- Walk: walk1 is a stride with the near leg forward, walk2 is a passing pose with the far boot lifted, walk3 is a stride with the far leg forward, and walk4 is a passing pose with the near boot lifted. The body rises 1 px in the passing frames, and the lantern swings between x=18, 19 and 20.
- Baseline: the boot soles sit on row 30 in every frame (bbox bottom = 31 in all six), and row 31 is empty.

## Checks (Python/PIL, reading the outputs only)
- Sheet alpha values are only {0, 255}, there are 15 unique opaque colors, and the sheet is 192x32.
- I downscaled each GIF frame to 32x32 with nearest-neighbor. Each one matches its sheet frame exactly, and scaling it back up 8x matches the GIF frame exactly. That shows the GIFs are crisp 8x nearest-neighbor copies with no smoothing. The frame durations read 400/400 and 120x4, and both GIFs have loop=0.
- I viewed the sheet at 8x to check it looks right. I also looked at a `vixl_render_preview`, but that tool smooths its preview image; this does not affect the exported files.

## Deviations and choices
- Vixl's `animation-set` requires the order to list every saved frame, so one document cannot export idle and walk as separate GIFs. I made the two per-animation copies of the source (listed above) for the GIF exports. `keeper.vixl` remains the master source.
- The GIFs use GIF transparency (index 0) for the background. GIF has only 1-bit transparency, so there are no partly transparent pixels.
- The JSON also has extra top-level keys (width, height, loop) besides the per-frame fields the brief asks for.

## Unsure about
- At 32 px the face is tiny and the eye reads somewhat like goggles. The arm is mostly suggested by outline lines on the coat.
- In walk1 (lantern x=18) the lantern's handle sits 1 px left of the hand. I meant this as sway, but it may look slightly detached.
