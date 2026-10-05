# T12 round 2 · 8-second version — lane W (web code + headless Chromium)

**Timing:** start 22:27 UTC, end about 22:30 UTC (2026-10-05). **7 tool calls** in total: 6 before handing back (3 Bash, 2 image Reads of rendered frames, 1 Bash that removed the preview stills and wrote this file), plus the final hand-back call.

## What was asked
Make it 8 s: slow the beam to half speed, change the tagline to "Open daily from 7 am", and extend the final hold to 3 s. Keep the same files and specs otherwise.

## What changed (all in `round2/`, nothing outside it touched)
I copied `intro.html` and `render.py` from the round 1 folder into `round2/` and edited the copies:

| Change | How |
| --- | --- |
| Beam at half speed | `PERIOD` changed from 2.8 s to **5.6 s**. The sweep is the same sine swing between 8° and 136°, so the angular speed is half of round 1's at every point in the cycle. It still starts (and fades in) at 2.0 s and keeps sweeping to the last frame. |
| Tagline | `TAG` is now **"Open daily from 7 am"**. It has 20 characters, the same as the old line, so the typing rate (1.5 s / 20 = 75 ms per letter, each fading in over about 2 frames) and the layout (centred at x = 680, same font, size and colour) are unchanged. |
| Tagline timing | The tagline now types on over **3.5–5.0 s** instead of 3.0–4.5 s (new `TAG_T0 = 3.5`). |
| 3 s final hold | Hold is **5.0–8.0 s**: everything is visible, the beam keeps sweeping and the waves keep drifting. |
| Length 8 s | `render.py`: `DURATION` 6.0 → **8.0**, so **240 frames** (t = i/30). The live preview loop in `intro.html` now wraps at 8 s instead of 6 s. The header comment says 8 s. |

**Why the tagline moved by 0.5 s:** keeping every other beat where it was and only lengthening the hold gives 4.5 + 3.0 = 7.5 s, not 8 s. The extra 0.5 s had to go somewhere. I put it in front of the tagline, so it now starts when the wordmark finishes landing (3.5 s). The other two options were to slow the typing, which nobody asked for, or to make the hold 3.5 s, which would go against the stated 3 s. Nothing else moved: waves 0–1.5 s, lighthouse 1.0–3.0 s, beam from 2.0 s, wordmark 2.0–3.5 s.

## Files (the same names as round 1)

| File | Spec (checked with ffprobe / identify) | How it was made |
| --- | --- | --- |
| `intro.html` | Editable source (SVG + `renderAt(t)`) | The round 1 source with the edits above. `?t=6.5` freezes it at a given time. |
| `render.py` | Render script | Python Playwright with headless Chromium, 1080×1080 at DPR 1. It takes one screenshot per frame (240 PNGs), then runs ffmpeg. The encode settings are unchanged from round 1. |
| `intro.mp4` | 1080×1080, H.264, yuv420p, 30 fps, 240 frames, **8.000 s**, +faststart, 438 KB | ffmpeg libx264 crf 18, preset slow |
| `intro.gif` | 540×540, 240 frames, 8.0 s, loops forever, **2.18 MB** (under 5 MB) | ffmpeg palettegen (128 colours) + paletteuse (bayer), the same as round 1 |
| `intro-last-frame.png` | 1080×1080 PNG, frame 239 (t = 7.967 s) | A copy of the last rendered frame |

I deleted the intermediate frames and the preview stills after encoding. `python3 render.py` regenerates everything.

## Checks
I looked at stills at t = 2.0, 4.9 and 5.0 s and at the final frame. At 4.9 s the tagline reads "Open daily from 7 a" with the last letter still to come. At 5.0 s and in the last frame the full tagline is set, centred under the wordmark. The beam is visibly mid-sweep in the last frame.

## Carried over from round 1 (unchanged)
- The fonts are P052 Bold and URW Gothic.
- The background has a subtle radial lift instead of flat navy.
- The waves draw in with a vertical leading edge.
- The GIF is 30 fps, which browsers round to 3–4 cs per frame.
- The "final frame" is t = 7.967 s, because an 8.0 s clip at 30 fps ends one frame before 8.0 s.

## Unsure about
- Where the extra 0.5 s should go (see above).
- At half speed one full back-and-forth takes 5.6 s, so the beam completes only about 1.07 cycles between 2.0 s and 8.0 s. It never sits still, but viewers see roughly one sweep up and one sweep back.
