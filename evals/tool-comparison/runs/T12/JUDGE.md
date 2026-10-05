# T12 · Animated intro — judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Lanes: V (Vixl timeline), W (SVG/JS + Playwright + ffmpeg).

## 1. Blind scores (before key)

Round 1 codes were identified by their 6.0 s duration. CXLN and WI90 are the 8 s round-2 files.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 2K8Y | 5 | 4 | All beats present. Soft-edged wave wipe; the lighthouse rises from behind the waves (visible from about 1.5 s); horizontal beam sweep; big centred serif wordmark. Clean but a little static. |
| F95K | 5 | 4 | All beats present. Asymmetric layout with a striped lighthouse and a wide beam sweep. The wave reveal shows a hard rectangular wipe edge at 1.0 s. |

Key: 2K8Y = V, F95K = W.

## 2. Hard checks (round 1)

Frames were taken at 1.0, 1.25, 1.6, 2.0, 2.5, 3.75 and 4.5 s, with frame-to-frame differences over all 180 frames.

| Check | V | W |
| --- | --- | --- |
| mp4 6.0 s, h264 1080², 30 fps, yuv420p | PASS (180 frames, 6.000 s) | PASS (180 frames, 6.000 s) |
| gif 540², loop=0, ≈6000 ms, ≤5 MB | PASS (147 frames, 25 fps with duplicate frames merged, 6000 ms, 0.70 MB) | PASS (180 frames, 6000 ms, 1.71 MB) |
| last-frame PNG 1080², exact wordmark and tagline | PASS | PASS |
| Beats: waves part-drawn at 1.0; beam moving at 2.5; tagline part-typed at 3.75 ("Coffee by"); everything visible and beam moving from 4.5 to 6.0 | PASS: beam changes every frame through the hold, with brief stops at the reversal points | PASS |
| Easing, no jumps or flicker | PASS: diff curve is smooth, no spikes | PASS |
| **Total** | **5/5** | **5/5** |

Both lighthouses start rising at 1.0 s from behind the waves, so they only show from about 1.4–1.5 s. That is acceptable for "rises into view".

## 3. Report honesty

- **V — yes.** Timings, easings, the two-wedge beam workaround, the 25 fps GIF and the merged frames all check out.
- **W — yes.** Layout, the vertical wipe edge, the radial background lift and the GIF frame count all check out.

## 4. Round 2 (8 s, beam at half speed, tagline "Open daily from 7 am", 3 s final hold)

Both runs met the spec: 8.000 s, 240 frames, GIF 8000 ms and loop=0. In both, the new tagline is complete at 5.0 s and the beam still moves through the 5–8 s hold.

| | V | W |
| --- | --- | --- |
| Method | Edited a copy of `intro.vixl` with operations. Removed the old 21-key text track, set the new text, and keyed a new typewriter track by hand (one key per 100 ms, 3.0–5.0 s). Replaced both beam `scale-x` tracks with doubled quarter-phases. A key placed past the end stretched the timeline to 8.667 s, so the agent set it back to 8 s. The MP4 export timed out on the client side, but the file was complete. | Changed `PERIOD` from 2.8 to 5.6, `TAG`, a new `TAG_T0 = 3.5`, and `DURATION` to 8. |
| How the extra 0.5 s was used | Typing slowed to 2.0 s; start kept at 3.0 s | Tagline start moved to 3.5 s; typing speed kept |
| Drift | None besides the typing-speed choice | None besides the start-time choice |
| Editability / revision | 4 / 5 | 5 / 5 |

Vixl gaps seen: `scale-x` cannot go negative, so the beam needed two mirrored wedges; there is no stroke-length animation for drawing a path; the `typewriter` preset was not reapplied, so the track was re-keyed by hand; a key past the end silently extends the duration; the MP4 export timed out after 60 s.
