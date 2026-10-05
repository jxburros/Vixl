# T14 · Lyric video — judge notes

Judge: Claude (claude-opus-5-5) subagent, 2026-10-05. Same model family as both makers, so take the
craft scores as one opinion. Evidence frames and contact sheets are in the session scratchpad (`judge/T14/`).

## 1. Blind scores (written before opening `key.csv`)

Method: for each code I pulled frames at 0.5, 1.0, 1.95, 2.05, 2.2, 5.45, 5.55, 8.95, 9.05, 9.2, 12.6, 15.95, 16.05,
16.5, 17.95, 18.05, 18.2, 21.6, 24.95, 25.05, 28.45, 28.55, 28.7 and 31.9 s, and made contact sheets of them. I cropped the
top band to read the section labels, and found every scene change frame by frame with a frame-difference pass
(320×180 grey, mean abs diff).

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 8F4V | 5 | 4 | Every change falls on its exact frame (2.000, 5.500, 9.000, 12.500, 16.000, 18.000, 21.500, 25.000, 28.500 at 24 fps), with a 250 ms crossfade. Title card runs 0–2 s. The screen is empty during 16–18 s. Chorus and Verse 2 labels sit top-left. Night verses and sunset choruses look clearly different. The beam and glow show only on Lighthouse lines. Good serif/sans pairing and an illustrated lighthouse scene. Minus one point because the lyric text runs over the lighthouse lamp on the left. |
| N21H | 4 | 3 | Every change falls on its exact frame (30 fps). Labels are present, the chorus look is clearly different, and the glow shows only on Lighthouse lines. But the small "next" line ("The gulls are sleeping…") stays on screen through the 16–18 s break, so the screen is not cleared. Type is generic DejaVu with heavy outlines and shadows, the lighthouse is a plain black bar, and the beam is a vague diagonal haze. |
| 5ZX0 | 5 | 3 | (Read blind as a revision of 8F4V.) Every change is exactly 6 frames (0.25 s) earlier, including the clear at 15.75 s. Chorus lines are larger, but they now wrap and leave an orphan "sea" on the second line. |
| N4GW | 4 | 3 | (Read blind as a revision of N21H.) Every change is about 0.25 s earlier (the first 30 fps frame at or after t − 0.25). Chorus lines are larger. The next-line preview still shows during the break. |

Key: 8F4V = claude-V (round 1), 5ZX0 = claude-V/round2, N21H = claude-T (round 1), N4GW = claude-T/round2.
I had guessed the pairing correctly from the frame rates and looks; it did not change the scores.

## 2. Hard checks (round 1)

`inspect_outputs.py runs/T14`: V is h264 1280×720 at 24 fps with AAC 22050 Hz mono, 32.0 s. T is h264 1280×720 at 30 fps with AAC 44100 Hz mono, 32.0 s.
In ffprobe, video, audio and container all read 32.000 s. volumedetect gives mean −18.8 dB and max −9.6/−9.7 dB for both, matching the fixture WAV (−18.8 / −9.7), so the song is in each file and intact.

| # | Check | claude-V | claude-T |
| --- | --- | --- | --- |
| 1 | 32.0 ± 0.1 s, h264 1280×720, AAC | PASS (32.000 s) | PASS (32.000 s) |
| 2 | Spot frames at 1.0 / 2.2 / 9.2 / 16.5 / 18.2 / 28.7 s | PASS: title / line 1 + next / Chorus line with beam / empty / Verse 2 line / repeated chorus line with beam | FAIL at 16.5 s: the key says the screen is cleared, but "The gulls are sleeping…" shows in the next slot. The other five match. |
| 3 | "[Chorus]"/"[Verse 2]" never shown as lyrics | PASS (shown only as top-left labels) | PASS (shown only as top-left small-caps labels) |
| 4 | Line at 28.50 present; screen clears at 16.00 | PASS: the change is on frame 684 (28.500), where the line dips and fades back in. Frame 384 (16.000) has no text. `lyric-next` was hand-hidden 16–18 s. | FAIL: the 28.50 line is present (event 28.5–32, change on frame 855). At 16.00 the big line clears on frame 480, but the next-line preview fades in from 16.0 s and stays until 18 s. |
| 5 | Chorus looks different; beam only on Lighthouse lines | PASS: sunset vs night. Beam and glow show 9.0–12.5 and 25–32 s, and are off on "Turn your golden eye…". | PASS: sunset vs teal night. Glow, beam and lit lamp show 9–12.5 and 25–32 s; the 12.5–16 chorus line uses an orange variant without the glow. |
| | **Total** | **5/5** | **3/5** (checks 2 and 4 fail for the same reason: the screen is not cleared during the break) |

Timing is exact in both lanes: every change lands on the first frame at or after its timestamp. Neither lane misses by a frame.

## 3. Report honesty

- **claude-V: yes.** What it says about the design, timing, beam windows (9.0–12.5, 25–32), the 28.5 s dip, the hand-hidden next line during the break, the labels, the fonts and the export path all matches the files. One small slip: it gives the AAC as "192 kb/s", but the stream measures about 69 kb/s (22 kHz mono, so the encoder caps the rate; 192k was the requested setting).
- **claude-T: yes.** It discloses openly that the next-line preview stays during the break, and says plainly that this is a deviation if "clears the screen" means every line. The 150 ms fades, the sine-swept beam, the fonts and the durations all check out. It states 160 kb/s; the stream measures about 140 kb/s, which is the usual ABR spread.
- Round-2 reports: both are accurate on times and sizes. The T round-2 report says the assets were "regenerated … so the content is unchanged". In fact the star field in `bg_verse.png` uses unseeded `+noise Random` and differs (29,411 px at fuzz 5%). This is cosmetic only.

## 4. Round 2 (0.25 s earlier, title still at 0, chorus lines 25% larger)

| | claude-V | claude-T |
| --- | --- | --- |
| How | Re-ran `lyric-video-build` with `offset: 250`, redid the round-1 hand edit (next line hidden 15.75–17.75), added hold keys on `lyric` size (50 → 62.5 px in choruses) and keyed the box height 120 → 170 px | Added `LYRIC_OFFSET = -0.25` and `CHORUS_SCALE = 1.25` constants plus two ASS styles (`CurrentChorus` 72.5 px, `NextChorus` 40 px), and made the title end follow the first lyric; then re-ran `build.py` |
| Timing | Every change exactly 6 frames earlier (1.750 … 28.250; clear at 15.750); title from 0 to 1.75 | Every change at the first frame at or after t − 0.25 (1.767, 5.267, 8.767 … 28.267; clear at 15.767); title from 0 to 1.75 |
| Chorus size | 1.25× (the author measured glyphs at 1.24×) | 58 → 72.5 px = 1.25×; the measured text-block width goes from 719 to 899 px (1.25×) |
| Unchanged parts | Verse frames and the title card are pixel-identical to round 1 (verse text box 784×178 in both; 1.0 s frame identical) | Verse text boxes are the same (7.0 s 1016×48; 20.0 s 615×96/95) |
| Collateral | Chorus lines now wrap and leave an orphan "sea"; `lyric-next` drops about 26 px during choruses | Chorus line raised from y=320 to 305; the small preview of chorus lines also grew 25% (a disclosed reading of the brief); verse star field re-randomised |
| Break clear | Still empty (hand edit redone) | Preview still shows during the break (unchanged from round 1) |
| **editability** | **4**: done, but it meant a full workflow rebuild plus redoing a hand edit by memory; the template itself could not hold a time-based size change | **5**: two constants and two style lines, changed in place, nothing else moved |
| **revision** | **4**: right, with small layout side effects and a weaker wrap | **4**: right, with small side effects (preview size, y lift, star noise) |

## Summary

- V is ahead on round-1 fidelity (5/5 hard checks against 3/5) and on craft. The deciding fidelity point is the break: V noticed that the workflow's default keeps showing the next line through the break and hid it by hand. T kept the preview there on purpose, and said so in its report.
- Timing data handling (LRC labels, the clear, the double timestamp) is exact in both lanes.
- T's script-based source was easier to revise in place. V's revision meant a rebuild and redoing a hand edit, because the export workflow regenerates the timeline from the template.
