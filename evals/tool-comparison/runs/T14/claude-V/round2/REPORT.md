# T14 Lyric video, round 2: Vixl lane (claude-V)

## What changed

1. **Every lyric is 0.25 s earlier.** Each line, the section labels, the backgrounds, the "Lighthouse" beam cue and the instrumental-break clear now start 250 ms sooner:
   - lines at 1.75, 5.25, 8.75, 12.25, 17.75, 21.25, 24.75 and 28.25 s;
   - the break clears the screen from 15.75 to 17.75 s.

   The title card still starts at 0 s. It now runs to 1.75 s, where the first line appears. The video is still 32.000 s long, with the song unchanged.
2. **Chorus lines are 25 % larger.** The current-line text (`lyric`) is 80 px during the four chorus lines (8.75–15.75 s and 24.75–32 s), up from 64 px. Verse lines stay at 64 px. The small next-line preview, the section labels and the title card are unchanged.

## How

All of this was done through the Vixl MCP tools. No pixels were drawn by hand.

- `round2/lighthouse-template.vixl` is a byte copy of the round-1 template. The size change depends on time, so it belongs in the timeline, not the template.
- `round2/request.json` is the round-1 request with two changes: the paths point into `round2/`, and it adds `"offset": 250`. In Vixl, as in the LRC convention, a positive offset shows lyrics earlier.
- `round2/lighthouse-lyrics.vixl` was produced in two steps:
  - `vixl_workflow lyric-video-build` built it from that request. The plan reports the shifted times and no warnings.
  - `vixl_operations_apply` then added four hold keyframes on `lyric.size`: 64 at 0 s, 80 at 8.75 s, 64 at 17.75 s and 80 at 24.75 s. Each size switch lands while the lyric is fully transparent (between lines, or during the break), so a size jump never shows on screen.
- `round2/lighthouse.mp4` was rendered by `vixl_workflow lyric-video-export` as a job. It reused the edited build (`build_reused: true`).

The round-1 build had no hand edits that needed redoing: the build itself clears both the lyric and the next-line preview at the empty timestamp.

## Checks

- **ffprobe:** h264 1280x720 at 24 fps, plus AAC. Video, audio and container are each 32.000 s. volumedetect gives mean -18.8 dB and max -9.6 dB, the same as round 1.
- **Timing (frame-difference pass on both MP4s):**
  - Every scene change is exactly 6 frames (0.250 s) earlier: 2.0/9.0/18.0/25.0 s became 1.75/8.75/17.75/24.75 s.
  - Round-2 verse frames match round-1 frames from 6 frames later (mean grey difference 0.00–0.03).
  - The title frame at 1.0 s is identical in both rounds.
  - The fade at the very end (31.83 s) is unchanged, because the last line hides when the song ends.
- **Size:** I measured rendered frames.
  - "Turn your golden eye and bring the ships to me": the glyph height from ascender to descender went from 60 px to 75 px (1.25x), and the line pitch from 89 to 110 px.
  - The two wrapped lines (descenders reaching y=427) still fit inside the 1000x190 fitted box at y=240. The box's fit-to-box therefore did not shrink the text back down, and the next-line preview below is not overlapped.
  - Verse frames (20.0 s) are pixel-identical to round 1 at 20.25 s.
- **Visual check:** a 16-frame contact sheet. At 80 px the chorus lines wrap into balanced pairs, with no orphaned word:
  - "Lighthouse, lighthouse, / sweep across the sea"
  - "Turn your golden eye and / bring the ships to me"

## Files

| File | |
| --- | --- |
| `lighthouse.mp4` | The updated video |
| `lighthouse-lyrics.vixl` | The updated editable timeline (offset build plus the chorus size keys) |
| `lighthouse-template.vixl` | Unchanged copy of the template |
| `request.json` | Round-1 request plus `offset: 250`, with paths pointing into `round2/` |
| `REPORT.md` | This file |

Nothing outside `round2/` was modified.
