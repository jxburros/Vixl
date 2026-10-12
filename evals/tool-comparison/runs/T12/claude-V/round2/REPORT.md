# T12 round 2 · Animated intro, 8-second cut (lane V, Vixl)

All visual changes were made with the Vixl MCP tools (`mcp__vixl__*`). The shell was used only to copy round 1's `intro.vixl` into `round2/` as the starting point, and ffprobe, ffmpeg and PIL were used only to check the outputs. Nothing outside `round2/` was changed.

## What changed

| Request | Round 1 | Round 2 | How |
| --- | --- | --- | --- |
| Total length 8 s | 6000 ms, 180 frames | 8000 ms, 240 frames at 30 fps | `timeline-set` with `duration: 8000`, `fps: 30` and `loop: 0` |
| Beam at half speed | `scale-x` sine, period 2.4 s, keys 2.0–6.0 s | Same sine, amplitude 1, with the period doubled to **4.8 s**. Keys run from 2.0 to 8.0 s, sampled every 33.3 ms (182 keys) | `keyframe-remove` on `beam` `scale-x`, then `keyframes` with `sample: {fn: sin, period: 4800, start: 2000, duration: 6000, step_ms: 33.333}` |
| Tagline "Open daily from 7 am" | "Coffee by the harbor" | "Open daily from 7 am", still a single editable text layer in Work Sans 400 at 40 px, sea-foam, 2 px tracking | `text-set`. The new text is 19 px wider, so I re-centred it on the canvas with `align` `center-x`. Its centre is x = 540 as before, and the box is now [307.5, 662, 465, 47]. |
| Final hold 3 s | Hold 4.5–6.0 s (1.5 s) | Hold **5.0–8.0 s (3.0 s)** | The typewriter was re-applied (`text-animate` remove, then `typewriter`, `unit: char`) to start at **3.5 s** instead of 3.0 s. It still lasts 1.5 s, so it ends at 5.0 s. |

## Timing as built

| Time | What happens |
| --- | --- |
| 0.0–1.5 s | The three waves draw in (unchanged) |
| 1.0–3.0 s | The lighthouse rises from behind the horizon, and the island fades in (unchanged) |
| 2.0 s → end | The beam fades in over 2.0–2.4 s, then sweeps at half speed: one full right–left–right cycle every 4.8 s, until the last frame |
| 2.0–3.5 s | The wordmark slides up and fades in (unchanged) |
| 3.5–5.0 s | The tagline types on, one letter at a time |
| 5.0–8.0 s | Hold for 3 s. The beam keeps moving, and on the last frame it points right at scale-x ≈ 1.0 |

**The choice I made:** a 3 s hold in an 8 s piece means the motion has to finish at 5.0 s. In round 1 it finished at 4.5 s. The brief changed nothing else, so I filled the 0.5 s gap by starting the tagline when the wordmark lands (3.5 s) instead of while it is still settling (3.0 s). The typing speed is unchanged (1.5 s for 20 characters, the same length as the old tagline). The other option was to slow the typing to 2 s starting at 3.0 s. I avoided it because it changes the typing speed, which you didn't ask for.

## Files (same names and specs as round 1)

| File | Spec, checked with ffprobe and PIL |
| --- | --- |
| `intro.vixl` | Editable source, 21 layers, timeline of 8000 ms at 30 fps |
| `intro.mp4` | 1080×1080, H.264 High, yuv420p, 30 fps, 240 frames, 8.000 s, 137,068 bytes. Exported with `vixl_export_timeline` (fps 30, quality 90) |
| `intro.gif` | 540×540, loops forever (loop=0), 236 frames, total 8000 ms, 1,454,751 bytes (about 1.45 MB, under 5 MB). Exported with `vixl_export_timeline` (scale 0.5, fps 30, 256 colours, no dither). Vixl merged the four identical blank opening frames into one 170 ms frame, as in round 1 |
| `intro-last-frame.png` | 1080×1080 RGB, the frame at t = 7966.667 ms (frame 240 of 240), from `vixl_export_file` with `time=7966.667`. The mean absolute difference from the MP4's decoded last frame is 1.53/255, which is H.264 noise |
| `REPORT.md` | This file |

## Checks

- **`vixl_check`** ran with the edit batch. It found no `fix` findings. The review items are the same ones as in round 1, and they are expected for a play-once intro in a looping GIF: loop-seam warnings on every entrance track, the empty first frame (`motion.empty-poster`), and the waves bleeding past the edges on purpose.
- **Contact sheet** at 0, 1, 2, 2.6, 3.2, 3.5, 4, 4.5, 5, 6, 7 and 7.97 s:
  - The tagline is still hidden at 3.5 s.
  - It reads "Open da" at 4.0 s, "Open daily fr" at 4.5 s, and is complete from 5.0 s.
  - The beam swings visibly slower than in round 1. It points right at about 3.2 s, flips through zero width near 4.4 s, points left at about 5.6–6.0 s, and is back to the right at 8.0 s.
- **Timeline inspect** confirms that the beam keys end at 8000 ms with value 1.0.

## Not changed

Everything else is the same as round 1: artwork, colours, fonts, layer names, the wave, lighthouse and wordmark timing, and the export settings. The notes in round 1's report still apply: the flip-style beam, the empty first frame, the loop seams and the GIF frame merging. The GIF is about 0.37 MB larger than in round 1 because it has 2 s more frames.
