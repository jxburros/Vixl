# T13 round 2: claude-V (Vixl lane)

Changes asked for: make the raincoat red, and add a 2-frame `wave` animation (250 ms per frame) after the walk frames. The sheet becomes 256x32, the JSON lists the new frames, and there is a new `keeper-wave.gif`. Everything is in `round2/`. Nothing outside it was changed: `keeper.vixl` was copied in with `cp` and edited there.

Tool calls: 21 in total, counting this REPORT write and the handback. One `vixl_operations_apply` call timed out on the MCP side after 60 s. Its edit had still been saved, and I confirmed that by reading the file.

## Files
| File | How it was made |
| --- | --- |
| `keeper.vixl` | A copy of the round-1 master, edited with one atomic `vixl_operations_apply` batch of 29 operations. For each of the 6 existing frames the batch did `frame-apply`, then `pixel-palette` on the `upper` layer, then `frame-save` under the same name and duration. The palette change was Y #f5c518 to #d93a2b (coat), y #c88a12 to #9c2320 (shade) and h #fff08a to #f58a6e (highlight). The batch then restored idle1 and added two `pixel-art` layers, `wave-a` and `wave-b` (7x14 at x=21, y=2), each with `reorder` below `upper`. It saved `wave1` (wave-a showing) and `wave2` (wave-b showing) at 250 ms, and set `animation-set` to the order idle1, idle2, walk1-4, wave1, wave2 with loop 0. |
| `keeper-sheet.png` / `keeper-sheet.json` | `vixl_export_animation(format="sheet", columns=8, scale=1, sampling="nearest")`. The sheet is 256x32. The JSON adds wave1 at x=192 and wave2 at x=224, each 32x32 with 250 ms. |
| `keeper-idle.gif`, `keeper-walk.gif`, `keeper-wave.gif` | `vixl_export_animation(format="gif", scale=8, sampling="nearest")`, each from its own per-animation copy. |
| `keeper-idle-anim.vixl`, `keeper-walk-anim.vixl`, `keeper-wave-anim.vixl` | `cp` copies of the new master. In each copy the other animations' frames were removed with `frame-delete`, then `animation-set` set the order. The round-1 workaround was needed again: `animation-set` must list every saved frame. |

## Wave design
The keeper keeps the idle1 body, legs and lantern, and raises the far arm, which sits behind the body layer. The arm is a red sleeve with an outline and a skin-toned mitten hand above the hood. In wave1 the hand leans out to the right (x 24-27). In wave2 the arm is upright and the hand is 2 px further left (x 22-25), so the hand swings side to side. The wave arm uses only colors already in the palette.

## Checks (PIL, reading outputs only)
- Sheet: 256x32. Alpha values are only {0, 255}. There are 15 opaque colors; the red coat replaces the 3 yellows, so the count is unchanged.
- Recolor: in the first 192 columns, the alpha mask is identical to the round-1 sheet. The only color changes are the 3 coat remaps listed above, so the poses are unchanged.
- Baseline: the bounding-box bottom is row 30 in all 8 frames.
- GIFs: idle has 2 frames at 400 ms, walk 4 at 120 ms, wave 2 at 250 ms. All are 256x256 with loop=0. Each GIF frame downsampled by 8 equals its sheet frame exactly, and scaling it back up 8x with nearest-neighbor reproduces it exactly, so nothing was smoothed.
- I viewed the sheet at 4x.

## Unsure about
- The raised arm is thin (2 px of sleeve), and the hand is a small 2x3 mitten, so at 1x the wave reads mainly as a stick-like arm swinging.
- The lantern base (#b5402e) is now close in hue to the red coat. They do not touch: the lantern sits below the coat hem.
