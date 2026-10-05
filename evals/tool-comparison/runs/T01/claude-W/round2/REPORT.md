# T01 round 2 · night version (lane W, claude)

Tool calls: 8 (including this one and the final hand-off).

## Files (all in round2/)
| File | What it is | How it was made |
| --- | --- | --- |
| `picture.png` | 2400 x 1600 px, 8-bit RGB (TrueColor, no alpha) | `python3 render.py` (Playwright, headless Chromium, 2400x1600 viewport, scale 1) then `convert _raw.png -alpha off -define png:color-type=2 picture.png` |
| `picture.svg` | Editable source, copied from round 1 and edited | Changes were made with a short Python string-replace script (each replacement checked to match exactly once) |
| `render.py` | Unchanged copy of the round-1 render script | Copied |

Nothing outside round2/ was changed.

## What changed
- **Night sky**: the same 5-stop vertical linear gradient, with darker colours: #02040c (top), #060c22, #0f1a3c, #1c2a55, #2e3c6c (horizon). It is still a smooth gradient from near-black navy to a lighter navy.
- **Sun removed**: I took out the setting sun disc and its four reflection streaks on the water, because a sun doesn't fit a night scene.
- **Brighter beam**: start opacity raised from 0.85 to 1.0 with a whiter colour (#fffbe6). I added a middle stop at 0.6 opacity 0.55, and the beam now ends at 0.12 opacity, where before it faded to 0. The lantern glow is now opacity 1.0 with a whiter centre, and its radius went from 110 to 140.
- **Lighthouse and rocks moved right**: the whole rocky point, the lighthouse, the keeper's house and the rock lip are wrapped in `<g transform="translate(2400,0) scale(-1,1)">`. That mirrors them into the right half, so the tower is now centred at x~1930. Because they are mirrored, the keeper's house now sits to the right of the tower and the tower's shaded side is on the left.
- **Beam sweeps left**: the polygon is now `1930,402 0,430 0,1060` with the gradient reversed. It runs from the lantern out to the left edge, and its lower edge meets the sea at the left edge.
- **Third sailboat**: I added a new boat at translate(700,1400) scale(0.8). It uses the same hull and two-sail shapes and colours as the others. There are now exactly three boats.

## Things I had to move that weren't asked for
- **Far sailboat (boat 2)**: it was at x=2050, which is now behind the moved rocks. I mirrored it to x=350 (same y and scale) so it stays visible.
- **Two small sea rocks**: I left them where they were rather than mirroring them, because mirroring put one on top of near boat 1. I moved them earlier in the draw order (after boats 1 and 2, before boat 3). They don't overlap any boat.

## Kept as before
Stars (same 10), distant headlands (same colours, though now partly behind the rocks), sea gradient, wave dashes, near boat 1 (same position), lighthouse shapes and colours, and the flat style with no text. Some wave dashes on the right are now hidden behind the moved rocks.

## Uncertainties
- The headlands keep their dusk mauve colours, which look a little warm against the night sky. I left them alone because the instructions said to keep everything else the same.
- Removing the sun was my own call.
