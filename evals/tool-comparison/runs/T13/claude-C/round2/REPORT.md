# T13 round 2: Lane C (Python + Pillow + NumPy)

**Tool calls:** 10 in total, counting this report and the final hand-off. No Vixl, no browser, no image generator.

## What changed
1. **The raincoat is red.** In the copied script I changed only the three coat palette entries:
   - `Y` (coat) went from (244,196,48) to (206,42,46).
   - `y` (shade) went from (196,140,28) to (138,22,38).
   - `L` (highlight) went from (255,240,130) to (246,104,92).

   The hood, the coat and the lantern arm's sleeve all use these entries, so they all turn red. Nothing else changed in the first six frames. A script checked that their alpha mask matches round 1 exactly and that only those three colors were swapped.
2. **I added a 2-frame `wave` animation at 250 ms per frame**, placed after the walk frames as `wave_1` (x=192) and `wave_2` (x=224):
   - The keeper keeps the idle stance and the body doesn't bob. The near arm keeps holding the lantern.
   - The far arm, which the earlier frames don't draw, comes up from behind the body. It is a 2 px dark-red (`y`) sleeve with a skin-colored open hand (2×3 palm plus a thumb pixel) above the hood. It is drawn before the coat and head, so it goes behind them.
   - In `wave_1` the hand is tilted back, with the wrist at (8,6). In `wave_2` it is forward over the hood, with the wrist at (17,4). The lantern also sways 1 px in `wave_2`.
   - The new `wave_arm()` function and an optional `wave` argument to `frame()` do this. Each frame is one new row in the `FRAMES` table.
3. **Sheet and JSON:** `keeper-sheet.png` is now 256 × 32. `keeper-sheet.json` has `size` set to {w:256,h:32}, two new frame entries (`wave_1` and `wave_2`, 32×32 each, with `duration` 250) and `animations.wave` set to ["wave_1","wave_2"].
4. **`keeper-wave.gif` is new.** It is 256 × 256, 2 frames at 250 ms each, and loops forever (loop=0). It is made the same way as the other GIFs: an 8× NumPy `repeat` (nearest-neighbor), palette index 0 as the transparent color, and disposal 2.

## Files in round2/
- `make_keeper.py`: copied from round 1, then edited as described above. Running `python3 make_keeper.py` writes all the files below into round2/.
- `keeper-sheet.png` and `keeper-sheet.json`: updated as described above.
- `keeper-idle.gif` and `keeper-walk.gif`: rebuilt from the script. The frames and timing are the same as round 1. Only the coat is red now.
- `keeper-wave.gif`: new.

Nothing outside round2/ was changed.

## Checks I ran (with a script)
- The sheet is 256 × 32 RGBA, and every alpha value is 0 or 255.
- It uses 13 opaque colors. That is the same count as round 1, because the red tones replace the yellow ones. None of the old yellows remain.
- The lowest opaque row is y=31 in all 8 frames: the boot outline sits under boots on the y=30 baseline.
- Every GIF frame, sampled back down by 8, matches its sheet frame once transparent pixels are normalized. Every 8×8 block in the GIFs is a single color.
- The durations read back as 400/400, 120×4 and 250/250 ms, and all three GIFs have loop=0.

## Unsure
- In `wave_2` the outline of the hand reaches the top row of the frame (y=0), so the sprite has no headroom in that frame. It is still fully inside the 32 × 32 frame.
- The far arm is mostly hidden behind the hood, so the wave reads mainly from the hand moving between back and front. At 1× it is a small movement.
- The brief doesn't name the wave frames, so I called them `wave_1` and `wave_2` to match the existing names.
