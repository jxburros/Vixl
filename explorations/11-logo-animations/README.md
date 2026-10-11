# Logo builds: seven ways to assemble the Vixl mark

Seven short animations that build the [Digital Shift logo](../../assets/brand/digital-shift/START-HERE.md) out of nothing or out of something simpler. Each one opens the editable master `horizontal-color.vixl`, adds keyframes and some temporary helper layers, and ends on the exact logo, which then holds for 1.4 s before the loop restarts.

Rebuild everything with `python explorations/11-logo-animations/build.py`, or rebuild a subset by name: `... build.py 03 glitch`. Each build writes a 720 × 300 GIF, a full-size 1200 × 500 MP4 and a contact sheet of the build phase to `output/`.

| | Build | Technique |
| --- | --- | --- |
| ![](output/01-slide-lock.gif) | **01 Slide and lock** (2.8 s) | The V's drop in from the top and bottom (`translate-y`, ease-out-quart), and the grouped mark squashes to 94% when they lock. The detached pixels shoot out of the stair corners with `ease-out-back`, and the wordmark slides in letter by letter (`text-animate slide-left`). |
| ![](output/02-pixel-swarm.gif) | **02 Pixel swarm** (3.8 s) | The V's are cut into 14.4 px cells (half the stair step, so the grid follows the stairs) with a point-in-polygon test. About 220 cells fly in from random directions, spinning as they come, then cross-fade into the vector V's. |
| ![](output/03-ripple-pop.gif) | **03 Ripple pop** (3.4 s) | The same cells pop in (`scale` 0 → 1, `ease-out-back`), each delayed by its distance from where the V's meet, so the mark ripples outward. The pixels pop with `elastic-out`, then each letter of the wordmark pops in. |
| ![](output/04-break-apart.gif) | **04 Break apart** (3.8 s) | Two plain offset bars grow in (`scale-x` on a group with a left or right pivot), and a cover wipe turns the lower bar blue. Everything outside the V's then cracks off, with 2 × 2 chunks where possible, and falls away from the centre line, so the logo is carved out of the bars. |
| ![](output/05-draw-on.gif) | **05 Draw-on** (3.6 s) | Outline copies of the V's trace themselves (`trim_end` 0 → 100), the fills flood in under them, and the wordmark types itself out (`text-animate typewriter`). |
| ![](output/06-seed-grow.gif) | **06 Seed grow** (3.6 s) | A single pixel pops in, pulses and splits into a charcoal half and a blue half. Each half moves to its V's tip, where the V stretches up (`scale-y`) and then unfolds sideways (`scale-x`, ease-out-back) about a pivot on the tip. |
| ![](output/07-glitch-shift.gif) | **07 Glitch shift** (3.4 s) | A nod to the kit's "Digital Shift" name. Cyan and magenta `multiply` ghosts of each part jitter on `hold` keys every other frame, with offsets that shrink to zero, and they flicker until each part snaps into register. |

## Notes

- **The timeline has a track limit.** A timeline holds at most 1,024 tracks (`MAX_TRACKS`). The first version of *Break apart* gave each of its 480 cells four tracks plus a colour track and failed at operation 1024. The fix uses fewer animated things: debris breaks off in 2 × 2 chunks, one cover layer replaces 240 per-cell `fill` animations, and the two slab groups fade out instead of their cells. Plan a particle-style build around this limit, or use `particles`.
- **Cells overlap to hide seams.** Each cell is 0.6 px larger than its grid step, so the anti-aliased edges of neighbouring cells overlap and no hairlines show. Faint grid lines are still visible on the solid bars in *Break apart*, and they read as pixels.
- **The pixel scaffold always cross-fades to the vector.** Cells whose centre is inside a V stick out slightly past its diagonal edges. The real vector V's sit above the cells and fade in as the cells fade out, so the final frames match the master exactly.
- **The legacy master needs `loop_mode: "off"`.** These are one-shot reveals followed by a hold, not seamless loops, so each build sets this mode explicitly. With it, the motion check does not ask for matching start and end values.
