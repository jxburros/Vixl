# T12 round 2 · Tidewick Café intro at 8 s (lane V, Vixl)

**Changes asked for:** make it 8 s long, run the beam at half speed, change the tagline to "Open daily from 7 am", and make the final hold 3 s. All other files and specs stay the same.

**Timing:** started 22:27 UTC, ended about 22:33 UTC on 2026-10-05. **Tool calls: 21**, counting this report and the handback (4 Bash, 1 ToolSearch, 1 Read, 15 Vixl MCP).

## How it was made

I copied `../intro.vixl` to `round2/intro.vixl` and made every edit in the copy with `vixl_operations_apply`. Nothing outside `round2/` was changed.

1. **Tagline.** I removed the old 21-key `text` track (`keyframe-remove`) and ran `text-set` with "Open daily from 7 am". The new text is 465 px wide, so I moved the layer to x = 308 to keep it centred (the old layer was 454 px wide at x = 313). It is still left-aligned, so it types on from the left edge as before. I added a new typewriter track by hand: 21 keys (`""` and then one more character per key), every 100 ms from 3.0 s to 5.0 s.
2. **Duration.** I set the timeline to 8000 ms (`timeline-set`). It is still 30 fps, now 240 frames.
3. **Beam at half speed.** I replaced both `scale-x` tracks and kept the same easings and pattern, but each quarter-phase now takes 1333 ms instead of 667 ms. One full back-and-forth cycle now takes 5.33 s instead of 2.67 s.
   - beam-right: 1 at 2.0 s (ease-in-sine), 0 at 3.333 s (hold), 0 at 6.0 s (ease-out-sine), 1 at 7.333 s (ease-in-sine), 0 at 8.667 s.
   - beam-left: 0 at 3.333 s (ease-out-sine), 1 at 4.667 s (ease-in-sine), 0 at 6.0 s (hold).
   - The 8.667 s key is past the end of the timeline. Adding it stretched the duration to 8667 ms, so I set it back to 8000 ms afterwards. The key stays, so the beam is mid-sweep at the end, as it was in round 1 (scale-x about 0.71, pointing right).
4. The fade-in of the beam, glow and lamp (2.0–2.5 s), the waves, the lighthouse and the wordmark are unchanged.

## New schedule

| Time | What happens |
| --- | --- |
| 0.0–1.5 s | Waves wipe in (unchanged) |
| 1.0–3.0 s | Lighthouse rises; from 2.0 s the beam sweeps at half the old speed until the end |
| 2.0–3.5 s | Wordmark slides up and fades in (unchanged) |
| 3.0–5.0 s | "Open daily from 7 am" types on, one character every 0.1 s |
| 5.0–8.0 s | Hold (3 s) with the beam still moving |

To get a 3 s hold inside 8 s, the content has to finish by 5.0 s. I spread the extra 0.5 s over the tagline: it now types over 2.0 s instead of 1.5 s, and it still starts at 3.0 s.

## Files (in round2/)

| File | How | Verified |
| --- | --- | --- |
| `intro.vixl` | Edited copy of the round-1 source | `vixl_check` passed with 0 errors. The 3 warnings are the reveal masks, which are deliberately wider than the canvas (the same as round 1). |
| `intro.mp4` | `vixl_export_timeline` (mp4, 30 fps, scale 1) | ffprobe: h264, yuv420p, 1080×1080, 30/1, 240 frames, 8.000 s, 154 KB. The MCP call timed out on the client side after 60 s, but the server finished writing the file, and I probed it after that. |
| `intro.gif` | `vixl_export_timeline` (gif, scale 0.5, 25 fps, 256 colours) | Pillow: 540×540, loop=0 (loops forever), frame durations add up to 8000 ms, 838 KB (well under 5 MB). Vixl wrote 200 frames; Pillow reads 196 because identical consecutive frames were merged. |
| `intro-last-frame.png` | `vixl_export_file` with `time=7.967s` (frame 240/240) | 1080×1080. Its average difference from the MP4's actual last frame, extracted with ffmpeg, is about 1.5/255 (H.264 compression). I looked at it: the full tagline and wordmark are visible and the beam points right. |
| `REPORT.md` | this file | |

## Unsure about

- At half speed the beam sweeps only about one and a half times across the 6 s it is visible. It now spends about 2.7 s at a time pointing to one side, with the other wedge at 0.
- The "Unsure about" notes from round 1 (the soft wave-mask edge, and the beam disappearing when it faces the viewer) still apply. I checked the motion on a 16-frame contact sheet and in the final frame, not frame by frame.
