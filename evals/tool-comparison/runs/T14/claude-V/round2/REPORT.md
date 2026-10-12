# T14 Lyric video, round 2: Lane V (Vixl)

## What changed

1. **Every lyric is 0.25 s earlier.** I passed `offset: 250` to `lyric-video-export`. In Vixl, as in the LRC convention, a positive offset shows lyrics earlier. The fixture `lighthouse.lrc` is unchanged.
   - The title card still starts at 0 s. It now stays up until the first lyric at 1.75 s (before: 2.00 s).
   - Section markers move with their lines. The chorus background, the "Chorus"/"Verse 2" label and the lighthouse beam all start 0.25 s earlier too.
   - The instrumental break now clears the screen at 15.75 s.
2. **Chorus lines are 25 % larger.** I passed `section_styles: {"chorus": {"size": 80}}`, so chorus lines go from 64 px to 80 px.
   - The build writes hold keyframes on the `size` of the `lyric` layer: 64 at 0 s, 80 at 8.75 s, 64 at 17.75 s and 80 at 24.75 s.
   - Verse lines stay at 64 px. Font, colour and position are unchanged.

All other settings are the same as round 1: 30 fps, `quality final`, `lead 0`, 250 ms line fades and `next_line true`. The beam settings are also the same: 400 ms fade, `motion: sweep` ±10°, 3.5 s period. I copied these from the settings saved in round 1's `lighthouse.vixl`; none are guessed.

## New line times (video clock)

| Line | Round 1 | Round 2 | Size |
| --- | --- | --- | --- |
| Out past the harbor where the cold waves break | 2.00 | 1.75 | 64 px |
| A single light is burning for my sake | 5.50 | 5.25 | 64 px |
| Lighthouse, lighthouse, sweep across the sea | 9.00 | 8.75 | 80 px |
| Turn your golden eye and bring the ships to me | 12.50 (break 16.00) | 12.25 (break 15.75) | 80 px |
| The gulls are sleeping on the silver stone | 18.00 | 17.75 | 64 px |
| The keeper sings the tide a song alone | 21.50 | 21.25 | 64 px |
| Lighthouse, lighthouse, sweep across the sea (sung twice, stays on screen) | 25.00 / 28.50 | 24.75 / 28.25 | 80 px |

The lighthouse beam now shows over 8.75–12.25 s and 24.75–32.00 s.

## Files

| File | How it was made |
| --- | --- |
| `lighthouse-template.vixl` | A byte-for-byte copy of round 1's template. Both changes are settings on the export, so the design did not need to change. |
| `lighthouse.vixl` | The editable keyframed timeline (96 keyframes, 11 markers), written by `lyric-video-export` with the new settings. |
| `lighthouse.mp4` | Rendered by `vixl_workflow` `lyric-video-export` (run as an MCP job) from the template above, `fixtures/lighthouse.wav` and `fixtures/lighthouse.lrc`. |

## Verification

- **Plan first:** I ran `lyric-video-plan` with the new settings before the export. It returned the times above with no warnings.
- **Export's own check:** `verification: passed`. Video is h264 1280 × 720 at 30 fps, 960 frames, 32,000 ms. Audio is AAC at 22,050 Hz mono, 32,000 ms. The difference from the song's length is 0 ms.
- **Separate ffprobe:** h264 yuv420p 1280 × 720, AAC 22,050 Hz mono, duration 32.000000 s.
- **Keyframes:** `vixl_timeline_inspect` on `lyric` shows fade-ins starting at 1.75, 5.25, 8.75, 12.25, 17.75, 21.25 and 24.75 s, and the `size` keys listed above.
- **Frames:** I pulled frames from the old and new MP4s with ffmpeg at 1.7, 1.95, 10.5, 14, 20 and 27 s and compared them side by side.
  - At 1.95 s the new video already shows the first lyric, while the old one still shows the title card.
  - Chorus lines are visibly larger. They still wrap to two lines inside the 1040 × 190 box, and the box's shrink-to-fit did not visibly shrink them.
  - Verse frames match round 1.

## Notes

- Only the current line (`lyric`) is resized. The small next-line preview below it (`lyric-next`, 30 px) stays the same size, even when it previews a chorus line. I read "chorus lines" as the line being sung.
- At 80 px, the two-line chorus lyric sits closer to the preview line below it. They do not overlap.
- Nothing outside `round2/` was changed. The fixtures are untouched.
