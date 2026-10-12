# T13 Pixel-art sprite: report (lane V, Vixl)

All artwork was made with the Vixl MCP tools (`vixl_document_create`, `vixl_operations_apply`, `vixl_export_animation`). I used no image generator, no SVG/HTML and no hand-written pixels outside Vixl. I wrote one small Pillow script, and it only read the exported files to check them.

## Files

| File | How it was made |
| --- | --- |
| `keeper.vixl` | The editable source. It is a 32×32 document with a transparent canvas and seven `pixel-art` layers: `upper` (hood, face, beard, coat and arm), `lantern`, `legs-stand` and `legs-walk1`–`legs-walk4`. It holds six saved frames (`idle1`, `idle2`, `walk1`–`walk4`, made with `frame-save`) and two named animations (`idle` and `walk`, made with `animation-set`, both `loop: 0`). |
| `keeper-sheet.png` | `vixl_export_animation(format="sheet", columns=6, scale=1, sampling="nearest")`. It is 192×32 with frames in the order idle1, idle2, walk1, walk2, walk3, walk4, unscaled. |
| `keeper-sheet.json` | Written by the same sheet export. Each entry in `frames` has `name`, `x`, `y`, `width`, `height` and `duration` (ms): 400 for each idle frame, 120 for each walk frame. Vixl also adds the top-level `width`, `height` and `loop` and an `animations` map, which are extra to what the brief asked for. |
| `keeper-idle.gif` | `vixl_export_animation(animation="idle", scale=8, sampling="nearest", dither="none")`. 256×256, 2 frames of 400 ms, loops forever. |
| `keeper-walk.gif` | `vixl_export_animation(animation="walk", scale=8, sampling="nearest", dither="none")`. 256×256, 4 frames of 120 ms, loops forever. |

## How the character was built
- **Look:** A side view facing right. He has a yellow raincoat with a hood (with a lighter top and a darker back edge), a skin-toned face with a white beard and a dark eye, navy trousers (the far leg is a darker navy), dark brown boots, and a grey metal lantern with an orange glass and a pale flame. Every part has a dark outline (`#1e1a2a`).
- **Palette:** 13 opaque colours plus transparency. The check script counted 13 unique opaque colours in the sheet.
- **Idle:** In `idle2` the upper body drops 1 px (the breath) and the lantern moves 1 px left and 1 px down (the sway). The legs stay put.
- **Walk:** The walk is contact, passing, contact (legs swapped), passing. On the contact frames the body drops 1 px, and the lantern swings by 1 px in time with the steps.
- **Making the frames:** Between `frame-save` calls I used `hide`/`show` to pick the leg layer and `move` to place the body and lantern.

## Checks run on the exported files
- **Sheet:** It is 192×32 RGBA. The only alpha values are 0 and 255, so there are no partly transparent pixels.
- **Colours:** 13 opaque colours, within the limit of 16.
- **Baseline:** The lowest opaque row is y = 30 in all six frames, so the baseline is the same everywhere. The rows from the top of the head down sit at y = 4 or 5 depending on the bob.
- **GIFs:** Every frame of both GIFs matches its sheet frame scaled up 8× with nearest-neighbour, with no differing pixels. This means the GIFs are crisp and have no smoothing or dithering. Their alpha is also only 0 and 255.
- **GIF timing:** The frame durations are 400/400 for idle and 120×4 for walk, and the loop value is 0 (forever).

## Choices and deviations
- The 32×32 frame leaves a margin: the character fills x 10–23 and y 4–30.
- The lantern hangs in front of the near leg, so it partly hides that leg's shin in some walk frames. The feet are still visible in every frame.
- The working scene in `keeper.vixl` is left in the `walk4` pose. Use `frame-apply` to restore any other frame.
- I did not run `vixl_check` or a check suite. Those checks cover layout and text, which this piece doesn't have, so I checked the pixel rules on the exported files with a script instead.

## Unsure about
- The walk cycle is only 4 frames at 32 px, with 1 px steps for the bob and the lantern swing. It reads as a walk when scaled up, but it is simple.
- The lighthouse-keeper idea is carried only by the raincoat, the beard and the lantern. There is no other prop, such as a cap badge.
