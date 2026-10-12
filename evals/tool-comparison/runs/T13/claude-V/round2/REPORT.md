# T13 round 2: red raincoat and wave animation (lane V, Vixl)

I made every visual change with the Vixl MCP tools (`vixl_document_open`, `vixl_operations_apply`, `vixl_export_animation`, plus previews). I did not draw any pixels by hand outside Vixl or use an image generator. I copied `keeper.vixl` into `round2/` and then edited only the copy. The files in the parent folder are unchanged. I used one small Pillow script, and it only read the exported files to check them.

## What changed
1. **The raincoat is now red.** The coat's three colours sit only in the palette of the `upper` pixel layer. I changed that palette with one `frames-edit` operation (`scene: true`) that runs `pixel-palette` on all six saved frames and on the working scene:
   - main `#f4c430` became `#d63a2f`
   - shadow `#c98d1a` became `#962231`
   - hood highlight `#fff08a` became `#f2765e`

   The outline, skin, beard, trousers, boots and lantern did not change.
2. **There is a new 2-frame `wave` animation.** I restored the `idle1` pose with `frame-apply`. Then I added two new `pixel-art` layers, `arm-wave1` and `arm-wave2`, placed under `upper`. Each is the raised far arm in a red sleeve with a dark-red cuff and a skin-toned hand. The hand leans left in `wave1` and right in `wave2`, a 2 px swing. The near hand still holds the lantern. I saved the frames `wave1` and `wave2` with `frame-save` (`duration: 250`), showing one arm layer in each. Then I defined `animation-set name: "wave", order: [wave1, wave2], loop: 0`. The two arm layers do not appear in the older frames.

## Deliverables (round2/)
| File | Notes |
| --- | --- |
| `keeper.vixl` | Now has 9 layers, 8 saved frames and the animations `idle`, `walk` and `wave`. The working scene is left in the `wave2` pose. |
| `keeper-sheet.png` | `format: sheet, columns: 8, scale: 1, sampling: nearest`. It is 256×32, in the order idle1, idle2, walk1–4, wave1, wave2. |
| `keeper-sheet.json` | Written by the same export. It now lists `wave1` (x 192) and `wave2` (x 224), each at 250 ms, and has a `wave` entry under `animations`. `width` is 256. |
| `keeper-idle.gif`, `keeper-walk.gif` | Exported again with the same settings as before (scale 8, nearest, no dither), so they show the red coat. |
| `keeper-wave.gif` | New. 256×256, 2 frames of 250 ms each, loops forever. |

## Checks run on the outputs
- **Sheet:** It is 256×32 RGBA. The only alpha values are 0 and 255. It has 13 opaque colours, and none of the old yellows are left.
- **Old frames:** I applied the yellow-to-red colour map to the round-1 sheet and compared it with the first six frames of the new sheet. 0 pixels differ, so the colour is the only change to those frames.
- **Placement:** The baseline (the lowest opaque row) is y = 30 in all 8 frames. In the wave frames the raised hand reaches y = 1 and x = 27, so it stays inside the 32×32 cell.
- **GIFs:** Every frame of all three GIFs matches its sheet frame scaled up 8× with nearest-neighbour, with 0 pixels different. The durations are 400/400 for idle, 120×4 for walk and 250/250 for wave, and every GIF loops forever (loop 0).

## Unsure about
- The waving arm is 3 px wide and starts beside the face, so at 1× it partly merges with the edge of the hood. It reads clearly in the 8× GIF.
- In the wave frames the body does not bob. Only the hand moves.
