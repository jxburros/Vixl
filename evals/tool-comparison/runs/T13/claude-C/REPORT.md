# T13 Pixel-art sprite: Lane C (code: Python + Pillow + NumPy)

**Timing:** started 22:20:09 UTC, finished 22:22:30 UTC on 2026-10-05 (about 3 minutes of wall-clock time). 11 tool calls.

## Files
| File | How it was made |
| --- | --- |
| `make_keeper.py` | The editable source. A Python script, run as `python3 make_keeper.py`, that writes all the other files. The head, coat and lantern are ASCII pixel maps. The legs and the arm are drawn as pixel lines from pose numbers. Each frame is one row of the `FRAMES` table. |
| `keeper-sheet.png` | 192 × 32 RGBA, unscaled. Frames left to right: idle_1, idle_2, walk_1, walk_2, walk_3, walk_4. |
| `keeper-sheet.json` | `frames[]` holds `name`, `x`, `y`, `width`, `height` and `duration` (ms) for each frame: idle 400, walk 120. It also has `image`, `size` and an `animations` map (idle → 2 frames, walk → 4 frames). |
| `keeper-idle.gif` | 256 × 256, 2 frames at 400 ms each, loops forever (loop=0). Scaled 8× with NumPy `repeat`, which is pure nearest-neighbor. Uses palette transparency (index 0) and disposal 2. |
| `keeper-walk.gif` | 256 × 256, 4 frames at 120 ms each, loops forever. Made the same way as the idle GIF. |

## Character and animation
- A keeper in a yellow raincoat and hood, facing right. The face shows in the hood opening, the coat has dark toggles, the trousers are blue and the boots are dark purple-grey. The near arm holds a lantern with a glowing glass and an orange flame.
- Every part is drawn with its own 1 px dark outline (#1A1420), using 4-neighbor outlines and painted back to front.
- **Idle:** in frame 2 the body (head, coat and arm) drops 1 px as a breathing bob, and the lantern sways 1 px right.
- **Walk:** contact (near leg forward), then passing (body up 1 px, far foot lifted), then contact (far leg forward), then passing (near foot lifted). The arm and lantern swing 1 px against the legs.

## Checks I ran (with a script)
- Sheet is 192 × 32. Alpha values are only 0 and 255.
- 13 opaque colors, so 14 including transparency. That is under 16.
- In every frame the supporting boot's bottom row is y = 30, and the outline under it is y = 31. The lifted foot in the passing frames is higher, but the planted foot always stands on that baseline.
- Each GIF frame, sampled back down by 8, matches its sheet frame pixel for pixel. The frame durations read back as 400 and 120 ms.
- No resampling filter is used anywhere. The 8× upscale is integer array repetition.

## Choices and differences from the brief
- The frame names are `idle_1`, `idle_2` and `walk_1` to `walk_4`, because the brief doesn't name them.
- The JSON has two extra keys, `animations` and `size`, besides the per-frame fields the brief asks for.
- I counted the 16-color limit as opaque colors and stayed well under it.
- The far arm is not drawn: the body hides it in side view.

## Unsure
- The legs are short, which suits the chibi proportions. Even so, the contact frames show the stride only 3–4 pixels wide, so the walk reads best when animated.
- The coat toggles are single dark pixels. At 1× they may look like noise.
- Some GIF viewers ignore disposal 2 and show leftover pixels from the previous frame on transparent areas. I set disposal 2 explicitly.
