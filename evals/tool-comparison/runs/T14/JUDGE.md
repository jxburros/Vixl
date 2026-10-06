# T14 · Lyric video — judge notes

Two judging dates are on this page:

- **V lane: re-run on Vixl 0.20.0, judged 2026-10-06.** Judge: Claude (claude-opus-5-5) subagent.
- **T lane: run and judged 2026-10-05.** Its notes and scores are unchanged from that judging.

The judge is the same model family as the makers, so take the craft scores as one opinion.

Only T's sources are committed (`build.py`, `lighthouse.ass`), not its MP4s. For the 2026-10-06 blind look, both T
rounds were rebuilt from `build.py` in a scratch copy, with the fixtures copied next to it. The regenerated
`lighthouse.ass` files are byte-identical to the committed ones. Evidence frames, contact sheets and scripts are in the
session scratchpad (`judge/T14/`).

## 1. Blind scores

### V re-run (2026-10-06), written before opening `key.csv`

Method: I pulled frames at 0.5, 1.0, 2.2, 5.6, 9.2, 12.6, 16.5, 18.2, 21.6, 25.2, 28.7 and 31.5 s, plus frame strips
around 5.5, 16.0 and 28.5 s, and cropped the top-left corner to read the labels. I found every change frame by frame
with a frame-difference pass (320×180 grey). The blind set had four codes. Both T codes were easy to spot, because the
regenerated runs carry an `assets/` folder.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| FVK7 | 5 | 4 | **Title card:** "Lighthouse" over "The Vixl Examples" for 0–2 s, no label.<br>**Lines:** the current line is large Playfair over a smaller Lato next line. Changes land on their exact frames, with a 250 ms fade out and in.<br>**Labels and backgrounds:** no label before 9 s, then Chorus / Verse 2 / Chorus top-left. Night-blue verses (a moon in Verse 2) against a plum-to-orange chorus dusk.<br>**Break:** empty 16–18 s.<br>**Repeat:** the 28.5 s repeat is held on screen, and the next slot empties at 28.500.<br>**Beam:** sweeps from the illustrated lighthouse only on Lighthouse lines.<br>**Craft deductions:** "sake" is left alone on a second line; the corner label is small; between lines the main slot sits empty for about 0.3 s while the next slot has already changed. |
| C4W1 | 5 | 4 | (Read blind as a revision of FVK7.) Every change is exactly 6 frames (0.25 s) earlier, and the title card still starts at 0. Chorus lines are larger and wrap into balanced pairs. Verse frames are unchanged. |

### T lane (2026-10-05, unchanged)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| N21H | 4 | 3 | Every change falls on its exact frame (30 fps). Labels are present, the chorus look is clearly different, and the glow shows only on Lighthouse lines. But the small "next" line ("The gulls are sleeping…") stays on screen through the 16–18 s break, so the screen is not cleared. The type is generic DejaVu with heavy outlines and shadows, the lighthouse is a plain black bar, and the beam is a vague diagonal haze. |
| N4GW | 4 | 3 | (Read blind as a revision of N21H.) Every change is about 0.25 s earlier (the first 30 fps frame at or after t − 0.25). Chorus lines are larger. The next-line preview still shows during the break. |

Key: FVK7 = claude-V (round 1), C4W1 = claude-V/round2 (2026-10-06); N21H = claude-T, N4GW = claude-T/round2
(2026-10-05). In the 2026-10-06 blind set, the regenerated T videos came up as 0E31 (round 1) and EEPA (round 2). I
scored them again at fidelity 4 and craft 3, which matches the 2026-10-05 scores.

## 2. Hard checks (round 1)

**inspect_outputs:**

- V is h264 1280×720 at 24 fps, with AAC at 24000 Hz (stereo per ffprobe). It runs 32.0 s.
- T (regenerated) is h264 1280×720 at 30 fps, with AAC at 44100 Hz mono. It runs 32.0 s.

Video, audio and container all read 32.000 s. volumedetect gives a mean of −18.8 dB and a max of −9.6 dB in both. The
fixture WAV gives −18.8 / −9.7 dB, so the song is in each file and intact.

| # | Check | claude-V (0.20.0) | claude-T |
| --- | --- | --- | --- |
| 1 | 32.0 ± 0.1 s, h264 1280×720, AAC | PASS (32.000 s) | PASS (32.000 s) |
| 2 | Spot frames at 1.0 / 2.2 / 9.2 / 16.5 / 18.2 / 28.7 s | PASS: the title / line 1 + next / the Chorus line with the beam / empty / the Verse 2 line / the repeated chorus line with the beam | FAIL at 16.5 s: the key says the screen is cleared, but "The gulls are sleeping…" shows in the next slot. The other five match. |
| 3 | "[Chorus]"/"[Verse 2]" never shown as lyrics | PASS: they appear only as top-left labels. No layer or keyframe text in the build contains a bracketed label. | PASS (shown only as top-left small-caps labels) |
| 4 | Line at 28.50 present; screen clears at 16.00 | PASS. **28.50:** there is no text key at 28.5 because the line is held, and `lyric-next` empties on frame 684 (28.500). **16.00:** the lyric and the next line both fade out by 16.000 and stay empty until 18.000. **Workflow:** the build cleared the break itself, with no hand edit. | FAIL: the 28.50 line is present (event 28.5–32, change on frame 855). At 16.00 the big line clears on frame 480, but the next-line preview fades in from 16.0 s and stays until 18 s. |
| 5 | Chorus looks different; beam only on Lighthouse lines | PASS: sunset vs night. The lamp halo is on 9.08–12.46 and 25.08–31.96 s (300 ms fades) and off everywhere else, including "Turn your golden eye…" and the 5.5–9 s verse line whose next-line preview is a Lighthouse line. | PASS: sunset vs teal night. Glow, beam and lit lamp show 9–12.5 and 25–32 s; the 12.5–16 chorus line uses an orange variant without the glow. |
| | **Total** | **5/5** | **3/5** (checks 2 and 4 fail for the same reason: the screen is not cleared during the break) |

### LRC edge cases in V, frame by frame (24 fps)

**Timestamps:**

- The intro cuts on frame 48 (2.000).
- The label appears on frame 216 (9.000).
- The background changes on frames 216, 432 and 600 (9.000 / 18.000 / 25.000).

**Fades:** each line's opacity runs 0 → 1 from its timestamp to +250 ms. It holds, then fades 1 → 0 over the last
250 ms before the next timestamp. The text key switches exactly on the timestamp.

**Section markers:** the build has 8 lyric text keys and 4 label keys ("", Chorus, Verse 2, Chorus), with 91 keyframes
and 11 markers in all.

## 3. Report honesty

- **claude-V (0.20.0): yes.**
  - These claims all match the files:
    - the design and fonts;
    - `lead: 0` and the 250 ms line fades;
    - no label before 9 s;
    - the break cleared until 18 s;
    - the repeat held without a fade;
    - the beam windows (9.0–12.5, 25–32) and the ±10° sweep;
    - 91 keyframes;
    - `build_reused`;
    - the end-of-song fade-out;
    - the orphan "sake".
  - One slip: it calls the AAC track "24 kHz mono", but ffprobe reads 24 kHz **stereo**. The mono 22.05 kHz WAV was
    resampled and upmixed.
- **claude-T: yes.** It discloses openly that the next-line preview stays during the break, and says plainly that this
  is a deviation if "clears the screen" means every line. The 150 ms fades, the sine-swept beam, the fonts and the
  durations all check out. It states 160 kb/s; the stream measures about 140 kb/s, which is the usual ABR spread.
- **Round-2 reports:**
  - **V (2026-10-06):** accurate.
    - The template is a byte copy.
    - `offset: 250` is the only change to the request besides the paths.
    - The size keys are 64 → 80 px at 8.75, 17.75 and 24.75 s, as stated.
    - The glyphs measure 61 → 76 px, against the claimed 60 → 75.
    - The verse frames match.
  - **T (2026-10-05):** the report says the assets were "regenerated … so the content is unchanged". In fact the star
    field in `bg_verse.png` uses unseeded `+noise Random` and differs (29,411 px at fuzz 5%). This is cosmetic only.

## 4. Round 2 (0.25 s earlier, title still at 0, chorus lines 25% larger)

| | claude-V (0.20.0) | claude-T |
| --- | --- | --- |
| How | Added `"offset": 250` to the request and re-ran `lyric-video-build`. Then added four hold keys on `lyric.size` (64 → 80 px in choruses, back to 64 for Verse 2), placed while the lyric is fully transparent, and exported with `build_reused`. The template is untouched. | Added `LYRIC_OFFSET = -0.25` and `CHORUS_SCALE = 1.25` constants and two ASS styles (`CurrentChorus` 72.5 px, `NextChorus` 40 px), and made the title end follow the first lyric; then re-ran `build.py`. |
| Timing | Every change is exactly 6 frames earlier (1.750 … 28.250; clear at 15.750). The title runs 0–1.75 s, and its 1.0 s frame is identical to round 1. The end-of-song fade at 31.83 s stays where it was. | Every change at the first frame at or after t − 0.25 (1.767, 5.267, 8.767 … 28.267; clear at 15.767); title from 0 to 1.75 |
| Chorus size | 1.25×: the glyph rows measure 61 → 76 px. They still fit the 1000×190 box, and the next line below is not overlapped. | 58 → 72.5 px = 1.25×; the measured text-block width goes from 719 to 899 px (1.25×) |
| Unchanged parts | Each round-2 frame was compared with the round-1 frame 6 frames later. They differ only during the four chorus lines. Outside the lyric box the mean difference is 0.1–0.3 grey levels (beam phase), and the next line is unchanged. | Verse text boxes are the same (7.0 s 1016×48; 20.0 s 615×96/95) |
| Collateral | None found. The chorus lines now wrap into balanced pairs. | Chorus line raised from y=320 to 305; the small preview of chorus lines also grew 25% (a disclosed reading of the brief); verse star field re-randomised |
| Break clear | Still empty, with no hand edit needed. | Preview still shows during the break (unchanged from round 1) |
| **editability** | **5**: one request field and four keyframes, changed in place, nothing else moved. One caveat: the size change is hand-placed time keys, because the template contract has no per-section lyric style. A later rebuild would drop them, though the `build_stale` guard warns before that happens. | **5**: two constants and two style lines, changed in place, nothing else moved |
| **revision** | **5**: everything asked for, and nothing else changed. | **4**: right, with small side effects (preview size, y lift, star noise) |

## Changes since the Vixl 0.18.0 run

| | 0.18.0 run (2026-10-05, code 8F4V/5ZX0) | 0.20.0 run (2026-10-06, code FVK7/C4W1) |
| --- | --- | --- |
| Hard checks | 5/5 | 5/5 |
| Fidelity / craft | 5 / 4 (the lyric ran over the lighthouse lamp) | 5 / 4 (the lighthouse moved to the right, clear of the text; minus one for the "sake" orphan, a small label and a ~0.3 s empty slot between lines) |
| Break clear | The workflow kept the next line through the break, so the agent hid `lyric-next` by hand | The build clears both the lyric and the next line itself |
| Repeated line at 28.5 s | It dipped and faded back in | It is held on screen; only the next slot empties |
| Audio | AAC 22050 Hz mono (about 69 kb/s, against the 192 kb/s the report claimed) | AAC 24000 Hz stereo (the report says mono) |
| Report honest | yes (bitrate slip) | yes (channel-count slip) |
| Round 2 | Full rebuild plus redoing the hand edit by memory; the larger chorus wrapped with an orphan "sea"; `lyric-next` moved about 26 px | `offset: 250` plus four size keys; no hand edit to redo; balanced wraps; nothing else moved |
| Editability / revision | 4 / 4 | 5 / 5 |

## Summary

- V is ahead on round-1 fidelity (5/5 hard checks against 3/5) and on craft (4 against 3). The deciding fidelity point
  is still the break. On 0.20.0 the lyric-video build clears the next-line preview at an empty timestamp by itself.
  T kept the preview there on purpose, and said so in its report.
- Timing data handling (LRC labels, the clear, the double timestamp) is exact in both lanes.
- Round 2 is now level on editability (5 and 5). V's revision is the cleaner one (5 against 4): the `offset` request
  field moved every time, and four size keys did the chorus. In 0.18.0 the same revision needed a rebuild and a redone
  hand edit.
