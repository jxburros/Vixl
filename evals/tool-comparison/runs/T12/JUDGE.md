# T12 · Animated intro — judge notes

Lanes: V (Vixl timeline), W (SVG/JS + Playwright + ffmpeg).

- **V:** re-run on Vixl 0.20.0 by fresh agents, judged 2026-10-06 by a claude-opus-5-5 subagent.
- **W:** run and judged on 2026-10-05 (claude-opus-5-5 subagent). Its scores and notes are unchanged.
  On 2026-10-06 its deliverables were regenerated from the committed `intro.html` and `render.py`
  (both rounds rendered without errors) so it could sit in the blind set again.

## 1. Blind scores (before key)

**2026-10-06 blind set** (V's new run plus W regenerated). The round-1 codes were the 6.0 s files;
EY9V and O1GW were the 8 s round-2 files.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| PF28 | 4 | 3 | Three line waves draw left to right; the lighthouse surfaces at about 1.6 s; the beam starts at about 2.1 s as a flat, blurred trapezoid that swings through the lantern and vanishes edge-on; the wordmark and typing are on time. Clean and centred but generic; the beam reads brownish and crude, and the middle of the frame is empty. |
| Z1NM | 4 | 4 | Filled wave bands revealed by a hard-edged rectangular wipe; the lighthouse emerges from the sea; the beam sweeps an arc across the sky; strong asymmetric layout with glow and an amber tagline. |

Key: PF28 = V (Vixl 0.20.0), Z1NM = W (regenerated).

On the same files, this judge scored W one point lower on fidelity than the 2026-10-05 judge did
(4 against 5) for the same timing quirks: a lighthouse that only shows from about 1.5 s, and a
beam that starts by fading in. V has the same quirks, so V's final fidelity is 5, on the
2026-10-05 scale. Craft was scored the same as before for W (4), so V's 3 is on the same scale.

**2026-10-05 blind set** (unchanged):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 2K8Y | 5 | 4 | All beats present. Soft-edged wave wipe; the lighthouse rises from behind the waves (visible from about 1.5 s); horizontal beam sweep; big centred serif wordmark. Clean but a little static. |
| F95K | 5 | 4 | All beats present. Asymmetric layout with a striped lighthouse and a wide beam sweep. The wave reveal shows a hard rectangular wipe edge at 1.0 s. |

Key: 2K8Y = V (Vixl 0.18.0), F95K = W.

## 2. Hard checks (round 1)

V was measured on all 180 frames: wave, lighthouse, beam, wordmark and tagline pixels per frame,
plus frame-to-frame differences. W's column is from 2026-10-05.

| Check | V (0.20.0) | W |
| --- | --- | --- |
| mp4 6.0 s, h264 1080², 30 fps, yuv420p | PASS (180 frames, 6.000 s) | PASS (180 frames, 6.000 s) |
| gif 540², loop=0, ≈6000 ms, ≤5 MB | PASS (88 frames at 15 fps, with identical frames merged; 6000 ms; 0.27 MB) | PASS (180 frames, 6000 ms, 1.71 MB) |
| last-frame PNG 1080², exact wordmark and tagline | PASS | PASS |
| Beats: waves part-drawn at 1.0; beam moving at 2.5; tagline part-typed at 3.75 ("Coffee by"); everything visible and beam moving from 4.5 to 6.0 | PASS: at 1.0 s the waves are 82% drawn and the third is half done; the beam is moving at 2.5 s; the tagline reads "Coffee by" at 3.75 s and is complete at 4.5 s. The beam passes edge-on at 2.5, 3.5, 4.5 and 5.5 s and is invisible for about 3 frames each time, but it is moving through those frames. | PASS |
| Easing, no jumps or flicker | PASS: smooth difference curve with no spikes; only the typewriter steps | PASS |
| **Total** | **5/5** | **5/5** |

Measured V timings: the waves draw from 0.0 to 1.43 s; the lighthouse rises from 1.0 s behind a
navy water mask, shows from about 1.5 s and settles at 2.9 s; the beam fades in from 2.0 to 2.4 s;
the wordmark fades in from 2.03 to 3.4 s; the tagline types from 3.0 to 4.5 s.

## 3. Report honesty

- **V — yes.** The keyframes in `intro.vixl` match the report: waves `trim_end` at 0–1.1, 0.2–1.3
  and 0.4–1.5 s; lighthouse `translate-y` 520 → 0 over 1.0–3.0 s; beam opacity 2.0–2.4 s and
  `scale-x` 1/−1 keys each second from 2 to 6 s; wordmark rising 90 px over 2.0–3.5 s; a typewriter
  track of 21 keys over 3.0–4.5 s. Fonts (Fraunces 700, Work Sans 400), file sizes, the 88/90 GIF
  frame count and the edge-on beam are all stated correctly. One small slip: the report says the
  wordmark fades with ease-in-out-cubic, but its opacity track uses ease-out (the cubic easing is
  on the movement).
- **W — yes** (2026-10-05). Layout, the vertical wipe edge, the radial background lift and the GIF
  frame count all check out.

## 4. Round 2 (8 s, beam at half speed, tagline "Open daily from 7 am", 3 s final hold)

All runs met the spec: 8.000 s, 240 frames, GIF 8000 ms and loop=0. In each, the new tagline is
complete at 5.0 s and the beam still moves through the 5–8 s hold.

| | V (0.20.0, 2026-10-06) | V (0.18.0, 2026-10-05) | W (2026-10-05) |
| --- | --- | --- | --- |
| Method | Edited a copy of `intro.vixl` with 7 operations: removed the old text keys, `text-set` the new tagline, moved it 8 px left so it stays centred, set the duration to 8 s, re-applied the `typewriter` preset over 3.0–5.0 s, and re-keyed the beam `scale-x` at 2, 4, 6 and 8 s. No workarounds and no export problems. | Edited a copy of `intro.vixl`. Re-keyed the 21-key typewriter track by hand; replaced both beam `scale-x` tracks with doubled quarter-phases; reset the duration after a key past the end stretched it to 8.667 s; the MP4 export timed out on the client side. | Changed `PERIOD` from 2.8 to 5.6, `TAG`, a new `TAG_T0 = 3.5`, and `DURATION` to 8. |
| How the extra 0.5 s was used | Typing slowed to 3.0–5.0 s (100 ms per letter); start kept at 3.0 s | Typing slowed to 2.0 s; start kept at 3.0 s | Tagline start moved to 3.5 s; typing speed kept |
| Drift | None. The `project.json` diff touches only the tagline's text, x and width, the text and beam tracks, and the duration. The first 2 s of the video match round 1 frame for frame. | None besides the typing-speed choice | None besides the start-time choice |
| Editability / revision | 5 / 5 | 4 / 5 | 5 / 5 |

Measured: the beam's edge-on points moved from every 1.0 s (2.5, 3.5, …) to every 2.0 s (3.0, 5.0,
7.0 s), which is exactly half speed. The round-1 files were not touched (their timestamps are
earlier than round 2's). The 2026-10-05 judging accepted slower typing as the way to fit 8 s with a
3 s hold, and V's new run does the same, with the reason given in its report, so revision stays 5.

**V round-2 report honesty: yes.** The operations, timings, file facts and the ending beam
direction (pointing left at 8 s) all match the files.

## 5. Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 5/5 | 5/5 |
| Fidelity / craft | 5 / 4 | 5 / 3 |
| Report honest | yes | yes |
| Editability / revision | 4 / 5 | 5 / 5 |

- **Fixed in Vixl:** `scale-x` now accepts negative values, so the beam is one mirrored wedge instead
  of two. A path stroke can be drawn on with `trim_end`, so the waves really draw in instead of being
  wiped. The `typewriter` preset can be re-applied to new text. No key stretched the duration, and
  no export timed out. Round 2 needed no workarounds, so editability goes from 4 to 5.
- **Weaker look:** the new agent chose thin stroke waves, a blurred flat trapezoid beam that reads
  brownish over the navy, and a centred layout with a lot of empty space. The 0.18.0 run had
  filled, layered waves and a fuller frame. Craft drops from 4 to 3, now below W's 4. This is the
  agent's design choice, not a tool limit.
- **Still open:** `vixl_check` reports the waves as cut off at the canvas edges, although bleeding
  off the edge is the usual intent for a full-width wave; the agent had to mark each one
  `allow_crop`. Vixl said it wrote 90 GIF frames, but the file has 88, because identical frames were
  merged. The total duration is correct, but the reported count doesn't match the file.
