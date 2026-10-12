# T14 · Lyric video — judge notes

Two judging dates are on this page:

- **V lane: re-run on Vixl 0.26.0, judged 2026-10-12.** Judge: Claude (claude-opus-5-5) subagent.
- **T lane: run and judged 2026-10-05.** Its notes and scores are unchanged from that judging.

The judge is the same model family as the makers, so take the craft scores as one opinion.

Only T's sources are committed (`build.py`, `lighthouse.ass`), not its MP4s. For the 2026-10-12 blind look, both T
rounds were rebuilt from `build.py` in a scratch copy, with the fixtures copied next to it. The regenerated
`lighthouse.ass` files are byte-identical to the committed ones. Evidence frames, contact sheets, measurement scripts
and the written-down blind scores are in the session scratchpad (`judge-T14/`).

## 1. Blind scores

### V re-run (2026-10-12), written before opening `key.csv`

Method: I pulled frames at 0.5, 1.0, 2.2, 5.6, 9.2, 12.6, 16.5, 18.2, 21.6, 25.2, 28.7 and 31.5 s as contact sheets,
plus full-size frames in the middle of each line (3, 7, 10.5, 14, 20, 23 s) and crops where the lyric meets the
lighthouse. I found every change frame by frame with a frame-difference pass (320×180 grey) over the lyric, next-line
and label regions, and timed the lamp halo from the brightness of a patch beside the lamp. The blind set had four
codes. Both T codes were easy to spot, because the regenerated runs carry an `assets/` folder.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| ENW0 | 5 | 4 | **Title card:** "Lighthouse" over "The Vixl Examples" for 0–2 s, no label.<br>**Lines:** the current line is large Marcellus over a smaller Lato next line. Changes land on their exact frames (30 fps), with a 250 ms fade out before and in after each timestamp.<br>**Labels and backgrounds:** no label before 9 s, then Chorus / Verse 2 / Chorus top-left. Night-blue verses with a moon against a plum-to-orange chorus dusk.<br>**Break:** both lyric slots empty 16–18 s (the Chorus label and sky stay).<br>**Repeat:** the 28.5 s repeat is held on screen, and the next slot empties at 28.500.<br>**Beam:** sweeps from the lamp only on Lighthouse lines.<br>**Craft deductions:** greedy wraps leave ragged second lines ("…the cold / waves break", "…the silver / stone", "…a song / alone", "…bring the / ships to me"); the 1040 px lyric box spans the lighthouse column, so long first lines end about 20 px above its roof; the corner label is small. |
| 2PNO | 5 | 4 | (Read blind as a revision of ENW0.) Every change moves to the first frame at or after t − 0.25 s (7 frames at 30 fps), and the title card still starts at 0. Chorus lines are larger and wrap into balanced pairs. Verse frames are unchanged. The larger second chorus line sits close to the lighthouse roof. |

### T lane (2026-10-05, unchanged)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| N21H | 4 | 3 | Every change falls on its exact frame (30 fps). Labels are present, the chorus look is clearly different, and the glow shows only on Lighthouse lines. But the small "next" line ("The gulls are sleeping…") stays on screen through the 16–18 s break, so the screen is not cleared. The type is generic DejaVu with heavy outlines and shadows, the lighthouse is a plain black bar, and the beam is a vague diagonal haze. |
| N4GW | 4 | 3 | (Read blind as a revision of N21H.) Every change is about 0.25 s earlier (the first 30 fps frame at or after t − 0.25). Chorus lines are larger. The next-line preview still shows during the break. |

Key: ENW0 = claude-V (round 1), 2PNO = claude-V/round2 (2026-10-12); N21H = claude-T, N4GW = claude-T/round2
(2026-10-05). In the 2026-10-12 blind set, the regenerated T videos came up as PLL9 (round 1) and 1G3B (round 2). I
scored them again at fidelity 4 and craft 3, which matches the 2026-10-05 scores.

## 2. Hard checks (round 1)

**inspect_outputs:**

- V is h264 1280×720 at 30 fps, with AAC at 22050 Hz mono (about 67 kb/s). It runs 32.0 s.
- T (regenerated) is h264 1280×720 at 30 fps, with AAC at 44100 Hz mono. It runs 32.0 s.

Video, audio and container all read 32.000 s (960 frames). volumedetect gives a mean of −18.8 dB in both; the max is
−9.5 dB in V and −9.7 dB in T. The fixture WAV (22050 Hz mono) gives −18.8 / −9.7 dB. V's decoded audio
cross-correlates with the fixture at lag 0 (r = 0.9998), so the song is in the file, intact and in sync, at its own
rate and channel count.

| # | Check | claude-V (0.26.0) | claude-T |
| --- | --- | --- | --- |
| 1 | 32.0 ± 0.1 s, h264 1280×720, AAC | PASS (32.000 s) | PASS (32.000 s) |
| 2 | Spot frames at 1.0 / 2.2 / 9.2 / 16.5 / 18.2 / 28.7 s | PASS: the title / line 1 + next / the Chorus line with the beam / empty / the Verse 2 line / the repeated chorus line with the beam | FAIL at 16.5 s: the key says the screen is cleared, but "The gulls are sleeping…" shows in the next slot. The other five match. |
| 3 | "[Chorus]"/"[Verse 2]" never shown as lyrics | PASS: they appear only as top-left labels. No layer or keyframe text in the template or the build contains a bracketed label. | PASS (shown only as top-left small-caps labels) |
| 4 | Line at 28.50 present; screen clears at 16.00 | PASS. **28.50:** there is no text key at 28.5 because the line is held (opacity 1 from 25.25 to 31.75 s), and `lyric-next` empties on frame 855 (28.500). **16.00:** the lyric and the next line both fade out over 15.75–16.00 and stay empty until 18.000. **Workflow:** the build cleared the break itself, with no hand edit. | FAIL: the 28.50 line is present (event 28.5–32, change on frame 855). At 16.00 the big line clears on frame 480, but the next-line preview fades in from 16.0 s and stays until 18 s. |
| 5 | Chorus looks different; beam only on Lighthouse lines | PASS: sunset vs night. The lamp halo patch reads 82 grey (no halo) before 9.0 s, rises over 9.0–9.3 s to 141, falls over 12.1–12.5 s, and rises again from 25.0 s to the end; it stays off on "Turn your golden eye…" and on the 5.5–9 s verse line whose next-line preview is a Lighthouse line. | PASS: sunset vs teal night. Glow, beam and lit lamp show 9–12.5 and 25–32 s; the 12.5–16 chorus line uses an orange variant without the glow. |
| | **Total** | **5/5** | **3/5** (checks 2 and 4 fail for the same reason: the screen is not cleared during the break) |

### LRC edge cases in V, frame by frame (30 fps)

**Timestamps:**

- The intro cuts on frame 60 (2.000).
- The next-line slot switches on frames 60, 165, 270, 645, 750 and 855 (2.0 / 5.5 / 9.0 / 21.5 / 25.0 / 28.5).
- The label and background change on frames 270, 540 and 750 (9.000 / 18.000 / 25.000).

**Fades:** each line's opacity runs 0 → 1 from its timestamp to +250 ms. It holds, then fades 1 → 0 over the last
250 ms before the next timestamp. The text key switches exactly on the timestamp. The last line fades out over
31.75–32.00 s.

**Section markers:** the build has 8 lyric text keys and 4 label keys ("", Chorus, Verse 2, Chorus), with 91 keyframes
and 11 markers in all.

## 3. Report honesty

- **claude-V (0.26.0): yes.**
  - These claims all match the files:
    - 30 fps and AAC at 22,050 Hz mono, 32.000 s;
    - Marcellus 110 px title, Marcellus 64 px lyric in a 1040 × 190 fit-to-box frame, Lato 30 px next line, 22 px label;
    - `lead: 0` and the 250 ms line fades;
    - no label before 9 s;
    - the break cleared until 18 s, with the Chorus sky kept (disclosed);
    - the repeat held without a fade, with the repeat previewed in the next slot during 25–28.5 s;
    - the beam windows (9.0–12.5, 25–32), the 400 ms cue fades and the ±10°, 3.5 s sweep;
    - 91 keyframes and the per-section and per-line markers (11);
    - the end-of-song fade-out over 31.75–32.0 s.
  - It discloses that the design check was run on the template with every layer visible at once and not on the built
    frames, which is true (see section 5).
- **claude-T: yes.** It discloses openly that the next-line preview stays during the break, and says plainly that this
  is a deviation if "clears the screen" means every line. The 150 ms fades, the sine-swept beam, the fonts and the
  durations all check out. It states 160 kb/s; the stream measures about 140 kb/s, which is the usual ABR spread.
- **Round-2 reports:**
  - **V (2026-10-12):** accurate.
    - The template is a byte copy.
    - `offset: 250` and `section_styles: {"chorus": {"size": 80}}` are the only changes to the build options
      (`lyric_build.options` in both `.vixl` files differ only there).
    - The size keys are 64 at 0, 80 at 8.75, 64 at 17.75 and 80 at 24.75 s, as stated; 96 keyframes and 11 markers,
      as stated.
    - The glyph rows measure 62 → 78 px (1.26×).
    - The verse frames match, and the next-line preview keeps its size, as it says.
  - **T (2026-10-05):** the report says the assets were "regenerated … so the content is unchanged". In fact the star
    field in `bg_verse.png` uses unseeded `+noise Random` and differs (29,411 px at fuzz 5%). This is cosmetic only.

## 4. Round 2 (0.25 s earlier, title still at 0, chorus lines 25% larger)

| | claude-V (0.26.0) | claude-T |
| --- | --- | --- |
| How | Passed `offset: 250` and `section_styles: {"chorus": {"size": 80}}` to `lyric-video-export`, after a `lyric-video-plan` dry run. All other options were copied from the `lyric_build` record in round 1's `lighthouse.vixl`. The template is untouched. | Added `LYRIC_OFFSET = -0.25` and `CHORUS_SCALE = 1.25` constants and two ASS styles (`CurrentChorus` 72.5 px, `NextChorus` 40 px), and made the title end follow the first lyric; then re-ran `build.py`. |
| Timing | Every key is exactly 250 ms earlier in the timeline (1.75 … 28.25; clear at 15.75). In the video each change lands on the first frame at or after t − 0.25 s (frame 53 = 1.767 … 848 = 28.267; clear complete on frame 473 = 15.767). The title runs 0–1.75 s, and its 1.0 s frame is identical to round 1. The end-of-song fade at 31.75 s stays where it was. | Every change at the first frame at or after t − 0.25 (1.767, 5.267, 8.767 … 28.267; clear at 15.767); title from 0 to 1.75 |
| Chorus size | 1.25×: the glyph rows measure 62 → 78 px. They still fit the 1040×190 box, and the next line below is not overlapped (about 36 px gap). | 58 → 72.5 px = 1.25×; the measured text-block width goes from 719 to 899 px (1.25×) |
| Unchanged parts | Each round-2 frame was compared with the round-1 frame 7–8 frames later. They differ only during the chorus windows (8.80–15.70 and 24.80–31.70 s). Outside the lyric box the mean difference there is 0.06–0.21 grey levels (beam phase). | Verse text boxes are the same (7.0 s 1016×48; 20.0 s 615×96/95) |
| Collateral | None found. The chorus lines now wrap into balanced pairs. The beam's sweep now ends at −9.0° instead of −10° at 32 s, because its phase moved with the cue. | Chorus line raised from y=320 to 305; the small preview of chorus lines also grew 25% (a disclosed reading of the brief); verse star field re-randomised |
| Break clear | Still empty, with no hand edit needed. | Preview still shows during the break (unchanged from round 1) |
| **editability** | **5**: two request fields, changed in place, nothing else moved. The per-section size is now a build option (`section_styles`), so a later rebuild keeps it; in 0.20.0 it was four hand-placed time keys that a rebuild would drop. | **5**: two constants and two style lines, changed in place, nothing else moved |
| **revision** | **5**: everything asked for, and nothing else changed. | **4**: right, with small side effects (preview size, y lift, star noise) |

## 5. Vixl gaps seen in this run

- **`vixl check` on a lyric-video timeline is not time-aware.** On a scratch copy of the built `lighthouse.vixl`,
  `vixl check` reports `overlap.text-text` errors for `intro-title`/`lyric` (1384 px) and `intro-artist`/`lyric`, but
  the intro is hidden at 2.0 s, the moment the lyric starts to fade in, so the two are never on screen together. It
  also reports `lyric-next` contrast at 2.86:1 against a stack of all three skies. The template check, which is the one the agent
  ran, gives the same false findings; the agent raised the next line's opacity to answer the contrast one and did not
  re-check the built frames (it says so in its report).
- **The build leaves `loop: 0` (loop forever) on a song-length timeline.** The same check then raises four
  `motion.loop-seam` warnings (`section-label`, `bg-default`, `bg-chorus`, `intro`) and `text-mostly-hidden` warnings
  for the title card, none of which apply to a lyric video that plays once.
- **No balanced wrap for lyric lines.** `text-layout` offers width, height and fit, but no balanced or
  widow-avoiding wrap, so greedy wraps leave one-word second lines ("stone", "alone") in a 1040 px box.
- **Offset quantization.** A 250 ms offset at 30 fps is 7.5 frames, so changes land 7 frames (233 ms) earlier in the
  video, at the first frame at or after the shifted time. T does the same; this is inherent, not a bug.

## Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05, code 8F4V/5ZX0) | 0.20.0 (2026-10-06, code FVK7/C4W1) | 0.26.0 (2026-10-12, code ENW0/2PNO) |
| --- | --- | --- | --- |
| Hard checks | 5/5 | 5/5 | 5/5 |
| Fidelity / craft | 5 / 4 (the lyric ran over the lighthouse lamp) | 5 / 4 (minus one for the "sake" orphan, a small label and a ~0.3 s empty slot between lines) | 5 / 4 (minus one for ragged greedy wraps, the lyric box crowding the lighthouse roof and a small label) |
| Video | 24 fps | 24 fps | 30 fps |
| Audio | AAC 22050 Hz mono (about 69 kb/s, against the 192 kb/s the report claimed) | AAC 24000 Hz stereo: resampled and upmixed (the report says mono) | AAC 22050 Hz mono, the song's own rate and channels; lag 0 against the fixture |
| Break clear | The workflow kept the next line through the break, so the agent hid `lyric-next` by hand | The build clears both the lyric and the next line itself | Same as 0.20.0 |
| Repeated line at 28.5 s | It dipped and faded back in | It is held on screen; only the next slot empties | Same as 0.20.0 |
| Report honest | yes (bitrate slip) | yes (channel-count slip) | yes (no slips found) |
| Round 2 | Full rebuild plus redoing the hand edit by memory; the larger chorus wrapped with an orphan "sea"; `lyric-next` moved about 26 px | `offset: 250` plus four hand-placed size keys exported with `build_reused`; balanced wraps; nothing else moved | `offset: 250` plus `section_styles` in the request; the build writes the size keys itself; nothing else moved |
| Editability / revision | 4 / 4 | 5 / 5 | 5 / 5 |
| Effort (r1 / r2 minutes) | 8.8 / 5.7 | 6.4 / 5.4 | 3.4 / 2.5 (26 and 21 tool calls) |

**What changed.** The 0.20.0 audio bug is fixed: 0.26.0 muxes the song at its own 22050 Hz mono instead of
resampling it to 24 kHz and upmixing to stereo, and the report now states the format correctly. The chorus resize in
round 2 is a build option (`section_styles`) rather than hand-placed keys, so it survives a rebuild. Both rounds took
about half the time of the 0.20.0 run. The scores do not move: hard checks, fidelity and round 2 were already at the
top, and craft stays at 4 because the wraps are now ragged in four places (the 1040 px box replaced 0.20.0's 1000 px
one) and the lyric box overlaps the lighthouse column. The check gaps in section 5 are new findings, not regressions.

## Summary

- V is ahead on round-1 fidelity (5/5 hard checks against 3/5) and on craft (4 against 3). The deciding fidelity point
  is still the break. The lyric-video build clears the next-line preview at an empty timestamp by itself. T kept the
  preview there on purpose, and said so in its report.
- Timing data handling (LRC labels, the clear, the double timestamp) is exact in both lanes, and on 0.26.0 V's audio
  is the untouched song.
- Round 2 is level on editability (5 and 5). V's revision is the cleaner one (5 against 4): two request fields
  (`offset`, `section_styles`) did everything, and nothing else moved.
