# T01 round 2 · Lane C (claude-C)

## Files (all in `round2/`, nothing outside it changed)
| File | What it is | How it was made |
| --- | --- | --- |
| `picture.png` | 2400 × 1600 px, RGB | Made by `make_picture.py` (run `python3 make_picture.py` in this folder) |
| `make_picture.py` | Editable source (Python, Pillow + NumPy) | Copied from `../make_picture.py`, then edited with small scripted string replacements |
| `REPORT.md` | This report | Written by hand |

## What I changed and how
1. **Night sky.** I replaced the five sky gradient stops. The sky still uses NumPy per-row interpolation, so it is still a smooth gradient with no hard steps. It now runs from near-black navy `(3,5,16)` at the top, through deep navy `(9,13,38)`, dark indigo `(24,26,64)` and dim violet `(44,38,82)`, to a faint plum `(70,56,96)` at the horizon. Before, it ran from `(12,20,52)` to amber `(250,182,92)`.
2. **Brighter beam.** The beam is still three stacked wedges. I made each one more opaque and warmer:
   - outer: alpha 46 → 100, colour `(255,222,120)`
   - middle: alpha 46 → 135, colour `(255,230,140)`
   - core: alpha 40 → 175, colour `(255,240,170)`

   A sampled pixel in the beam core, at the left edge, now reads about `(183,173,137)`. My first try (alpha 70/85/110) came out grey against the dark sky, so I raised the values.
3. **Lighthouse and rocks moved to the right half, beam sweeping left.**
   - I flipped the scene horizontally around the canvas width, x → 2400 − x. The point helper `P()` now mirrors, and a new helper `B()` mirrors rectangle and ellipse boxes and re-sorts their corners.
   - The lighthouse is now centred at x ≈ 1840 and the lantern is at (1840, 452). The rocks fill the right side.
   - The beam now runs from the lantern to the left edge, covering y ≈ 380–1060 there, so it crosses the sea on the left.
   - **I mirrored more than the lighthouse and rocks.** If they had moved alone, the rocks would have covered the sun, a headland and both boats. So the sun (now x ≈ 700), its reflection streaks, both headlands, the wave dashes, the foam and both boats were mirrored too, and keep the same positions relative to each other. The two boats are now at about (840, 1180) and (320, 1360).
   - The stars were **not** mirrored. They use a new unmirrored helper `P0()` and are exactly where they were.
4. **Third sailboat.** I added a smaller, more distant boat (scale 0.6) at about (520, 1110), drawn with the same `sailboat()` function. There are now exactly 3 boats.

Everything else is unchanged: shapes, colours, the sea gradient, the 14 stars, the lighthouse details and the 2× supersampling with LANCZOS downscaling.

## Things I'm unsure about
- **The sun is still there**, unchanged apart from being mirrored. You asked to keep everything else, so I didn't remove it, but a half-set sun with amber glow and reflection is odd in a night scene. It now reads a bit like a rising moon. You may want it removed or recoloured.
- The rock "lit facets" and the sea colours are unchanged, so they are somewhat brighter than a real night would be.
- The lantern's translucent halo shows up as faint grey rings against the darker sky. It is the same shape as before, but more visible now.
- The brighter beam covers part of the sun's glow rings and the left headland.

## Tool calls
7 tool calls in this round, including writing this report and not counting the final handback.
