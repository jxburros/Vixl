# T12 · Animated intro — judge notes

Lanes: V (Vixl timeline), W (SVG/JS + Playwright + ffmpeg).

- **V:** re-run on Vixl 0.26.0 by fresh agents, judged 2026-10-12 by a claude-opus-5-5 subagent.
  Round 1 took 4.7 min and 27 tool calls; round 2 took 2.3 min and 19 tool calls (subagent wall
  time and tool uses), with no nudges.
- **W:** run and judged on 2026-10-05 (claude-opus-5-5 subagent). Its scores and notes are unchanged.
  On 2026-10-12 its deliverables were regenerated in a scratch copy from the committed `intro.html`
  and `render.py` (both rounds rendered without errors, with Playwright's default Chromium) so it
  could sit in the blind set again. Nothing was written to its run folder.

## 1. Blind scores (before key)

**2026-10-12 blind set** (V's new run plus W regenerated). The round-1 codes were the 6.0 s files;
27FL and 50B8 were the 8 s round-2 files. Contact sheets were pulled with ffmpeg at 0.5, 1.0, 1.5,
2.0, 2.5, 3.0, 3.5, 3.75, 4.0, 4.5 and 5.0 s, plus the last-frame PNGs.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| HTSM | 5 | 3 | All beats present. Three thin stroke waves draw left to right and are part-drawn at 1.0 s; the lighthouse fades up and rises onto a small island bar from 1.0 s; the beam is a blurred amber cone that flips through the lantern and reads brownish over the navy; the tagline is part-typed at 3.75 s. A tidy centred lockup (lighthouse, bold serif wordmark, small tracked tagline, waves) but generic: the lighthouse floats mid-frame on its bar instead of standing in the sea, the band between the tagline and the waves is empty, and the beam is crude. |
| VCBU | 5 | 4 | All beats present. Filled wave bands revealed by a hard-edged rectangular wipe; the lighthouse emerges from the sea; the beam sweeps an arc across the sky; asymmetric layout with glow and an amber tagline. |

Key: HTSM = V (Vixl 0.26.0), VCBU = W (regenerated).

This judge's blind scores for W (5 / 4) match the 2026-10-05 scores, so no adjustment is needed;
the 2026-10-06 judge had scored W's fidelity one point lower on the same files. V is scored on the
2026-10-05 scale: 5 / 3.

**2026-10-06 blind set** (previous V run):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| PF28 | 4 | 3 | Three line waves draw left to right; the lighthouse surfaces at about 1.6 s; the beam starts at about 2.1 s as a flat, blurred trapezoid that swings through the lantern and vanishes edge-on; the wordmark and typing are on time. Clean and centred but generic; the beam reads brownish and crude, and the middle of the frame is empty. |
| Z1NM | 4 | 4 | Filled wave bands revealed by a hard-edged rectangular wipe; the lighthouse emerges from the sea; the beam sweeps an arc across the sky; strong asymmetric layout with glow and an amber tagline. |

Key: PF28 = V (Vixl 0.20.0), Z1NM = W. V's final fidelity was 5 on the 2026-10-05 scale.

**2026-10-05 blind set** (unchanged):

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 2K8Y | 5 | 4 | All beats present. Soft-edged wave wipe; the lighthouse rises from behind the waves (visible from about 1.5 s); horizontal beam sweep; big centred serif wordmark. Clean but a little static. |
| F95K | 5 | 4 | All beats present. Asymmetric layout with a striped lighthouse and a wide beam sweep. The wave reveal shows a hard rectangular wipe edge at 1.0 s. |

Key: 2K8Y = V (Vixl 0.18.0), F95K = W.

## 2. Hard checks (round 1)

V was measured on all 180 decoded MP4 frames: wave, lighthouse, beam (amber pixels left and right
of the lantern), wordmark and tagline pixels per frame, plus the mean frame-to-frame difference.
W's column is from 2026-10-05.

| Check | V (0.26.0) | W |
| --- | --- | --- |
| mp4 6.0 s, h264 1080², 30 fps, yuv420p | PASS (H.264 High, 180 frames, 6.000 s, 130 KB) | PASS (180 frames, 6.000 s) |
| gif 540², loop=0, ≈6000 ms, ≤5 MB | PASS (176 frames, 30/40 ms delays averaging 30 fps, the five blank opening frames merged into one 170 ms frame; 6000 ms; 1.09 MB) | PASS (180 frames, 6000 ms, 1.71 MB) |
| last-frame PNG 1080², exact wordmark and tagline | PASS ("Tidewick Café", "Coffee by the harbor"; mean difference from the MP4's last frame 1.5/255) | PASS |
| Beats: waves part-drawn at 1.0; beam moving at 2.5; tagline part-typed at 3.75; everything visible and beam moving from 4.5 to 6.0 | PASS: at 1.0 s the waves are 84% drawn and the front wave about half; the beam is widening at 2.5 s; the tagline reads "Coffee by th" at 3.75 s and is complete at 4.43 s; the beam keeps moving to the last frame. The beam goes edge-on at 3.2, 4.4 and 5.6 s (every 1.2 s) and is invisible for one frame and a sliver for two more each time, but it is moving through them. | PASS |
| Easing, no jumps or flicker | PASS: largest frame difference 1.25/255 (wordmark fade plus beam), no spikes; only the typewriter steps. The beam sits behind the tower, so it never flashes over it at the crossings. | PASS |
| **Total** | **5/5** | **5/5** |

Measured V timings: the waves show from 0.17 s and look complete by about 1.3 s (the last 10% of
each `trim_end` runs past the canvas edge, since the paths bleed off both sides); the lighthouse
group fades in over 1.0–2.0 s and rises 180 px over 1.0–3.0 s behind a navy horizon cover; the beam
fades in over 2.0–2.4 s; the wordmark rises 50 px over 2.0–3.5 s and fades in over 2.0–3.2 s; the
tagline types from 3.0 to 4.5 s.

## 3. Report honesty

- **V — yes.** The keyframes in `intro.vixl` (`project.json`, written by 0.26.0) match the report:
  waves `trim_end` 0–100 at 0–1.1, 0.2–1.3 and 0.4–1.5 s with ease-in-out-sine; lighthouse
  `translate-y` 180 → 0 over 1.0–3.0 s and opacity over 1.0–2.0 s; island opacity 1.0–1.6 s; beam
  opacity 2.0–2.4 s and a sampled `scale-x` sine (period 2.4 s) from 2.0 to 6.0 s; wordmark keys as
  stated; the `typewriter` preset at 3.0 s for 1.5 s. 21 layers, Fraunces 700 and Work Sans 400,
  the unused embedded fonts, file sizes and the 176-frame GIF all check out, and the edge-on beam,
  empty first frame and loop-seam warnings are disclosed. Small slips: five blank frames were
  merged into the 170 ms opening frame, not four (the frame count 176 is right); "points left at
  scale-x ≈ −0.87" is the value at 6.0 s, while the last frame (5.967 s) is −0.82; I measured the
  PNG-to-MP4 difference as 1.53/255, not 1.24 (decoder-dependent, same conclusion).
- **W — yes** (2026-10-05). Layout, the vertical wipe edge, the radial background lift and the GIF
  frame count all check out.

## 4. Round 2 (8 s, beam at half speed, tagline "Open daily from 7 am", 3 s final hold)

All runs met the spec: 8.000 s, 240 frames, GIF 8000 ms and loop=0. In each, the new tagline is
complete at 5.0 s and the beam still moves through the 5–8 s hold.

| | V (0.26.0, 2026-10-12) | V (0.20.0, 2026-10-06) | V (0.18.0, 2026-10-05) | W (2026-10-05) |
| --- | --- | --- | --- | --- |
| Method | Edited a copy of `intro.vixl`: `timeline-set` duration 8000; `keyframe-remove` the beam `scale-x` and re-sample it with one `keyframes` operation (`sample: {fn: sin, period: 4800, …}`, 182 keys); `text-set` the new tagline and `align center-x`; remove and re-apply the `typewriter` preset at 3.5 s. No workarounds and no export problems. | 7 operations: removed the old text keys, `text-set`, moved the tagline 8 px, set the duration, re-applied `typewriter` over 3.0–5.0 s, re-keyed the beam at 2, 4, 6 and 8 s. | Re-keyed the 21-key typewriter track by hand; replaced both beam tracks; reset the duration after a key stretched it to 8.667 s; MP4 export timed out client-side. | Changed `PERIOD`, `TAG`, a new `TAG_T0 = 3.5`, and `DURATION`. |
| How the extra 0.5 s was used | Tagline start moved to 3.5 s (when the wordmark lands); typing speed kept (1.5 s) | Typing slowed to 3.0–5.0 s | Typing slowed to 2.0 s | Tagline start moved to 3.5 s; typing speed kept |
| Drift | None. The `project.json` diff touches only the tagline's text, x and width, the beam `scale-x` track, the text animation's start and the duration. The decoded frames match round 1 to 2.2 s (largest mean difference 0.02/255 over the first 2 s); the beam is the first thing to differ. | None | None besides the typing-speed choice | None besides the start-time choice |
| Editability / revision | 5 / 5 | 5 / 5 | 4 / 5 | 5 / 5 |

Measured: the beam's edge-on points moved from every 1.2 s (3.2, 4.4, 5.6 s) to every 2.4 s (4.4,
6.8 s), exactly half speed. The tagline is hidden until 3.5 s, part-typed through 4.9 s and
complete from 5.0 s, so the hold is 5.0–8.0 s. The round-1 files were not touched (their
timestamps are earlier than round 2's). Moving the start rather than slowing the typing is the
same choice W made, and the report explains it.

**V round-2 report honesty: yes.** The operations, the 182 sampled keys, the re-centred box
[307.5, 662, 465, 47], timings, file facts (240 frames, GIF 236 frames and 1.45 MB, PNG difference
1.53/255) and the ending beam direction (right, scale-x ≈ 1.0) all match the files.

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 5/5 | 5/5 | 5/5 |
| Fidelity / craft | 5 / 4 | 5 / 3 | 5 / 3 |
| Report honest | yes | yes | yes |
| Editability / revision | 4 / 5 | 5 / 5 | 5 / 5 |

The scores hold at the 0.20.0 level, and the run was quick (7 minutes for both rounds). Two of
0.20.0's open issues are fixed. `vixl_check` now accepts waves that bleed off two edges as
intentional (`bounds.bleed`, informational), so the agent didn't need `allow_crop`. The export
result now reports `frames` (176, the frames written) beside `rendered_frames` (180) and the
per-frame `frame_durations`, so the merged count matches the file; a scratch re-export of
round 1 reproduced the same 1,085,274-byte GIF. The new `keyframes` `sample` option let round 2
re-time a 121-key sine sweep in one operation. The look is a tidier centred emblem than 0.20.0's,
with a bold Fraunces wordmark and a striped tower, but it keeps the same weaknesses: a blurred,
brownish flip-style beam, thin stroke waves, a lighthouse floating above the water and an empty
band. Craft stays at 3, below W's 4; that is the agent's design choice, not a tool limit.

Still open:

- `vixl_check` and every timeline export treat a looping GIF as a seamless loop. A play-once intro
  that the brief says to loop gets 10 review warnings (`motion.loop-seam` on every entrance track
  plus the tagline), and `outcome.state` stays `needs_review`.
- Fonts from the first `vixl_roll` (Atkinson Hyperlegible Next, Source Serif 4; 241 KB) stay
  embedded in `intro.vixl` after the agent replaced them, because undo history keeps them. The
  check reports it but nothing prunes them.
- A continuous sweep ends up as baked keys (121 in round 1, 182 in round 2). Both `keyframes`
  `sample` and `animate` `repeat`/`until` expand into keys when applied, and there is no live
  oscillating track, so changing the speed means regenerating the track. It took one operation
  here, so this is a gap in the source's readability, not a blocker.
