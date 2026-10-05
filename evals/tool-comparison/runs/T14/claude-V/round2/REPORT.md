# T14 · Lyric video — claude-V, round 2

Changes asked for: every lyric 0.25 s earlier (the title card still starts at 0), and chorus lines 25 % larger.
Nothing outside `round2/` was changed. The fixtures (`lighthouse.wav`, `lighthouse.lrc`) were not edited.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `lighthouse.mp4` | 1280×720 H.264 + AAC (192 kb/s), 24 fps, 32.000 s (ffprobe: video 32.000, audio 32.000, container 32.000) | Vixl `vixl_export_timeline` (mp4, silent) from `round2/lighthouse-lyrics.vixl`, then ffmpeg mux with the fixture WAV (`-c:v copy -c:a aac -b:a 192k`). The picture was not re-encoded. |
| `lighthouse-lyrics.vixl` | Editable timeline document | Rebuilt with `vixl_workflow lyric-video-build` (same settings as round 1 plus `offset: 250`), then the round-1 hand edit was redone and the chorus-size keys added (see below). |
| `lyric-style.vixl` | Template | Copied unchanged from round 1. The size change depends on time, so it lives in the built timeline, not in the template. |

## 1. Lyrics 0.25 s earlier

- Rebuilt from the template with `offset: 250` (in Vixl a positive offset shows lyrics earlier), keeping `lead: 0`, fps 24 and 250 ms fade in/out. The LRC file was not touched.
- New line show times: 1.75, 5.25, 8.75, 12.25, 17.75, 21.25, 24.75, 28.25 s (were 2.0, 5.5, 9.0, 12.5, 18.0, 21.5, 25.0, 28.5). The instrumental-break clear moved from 16.0 to 15.75 s.
- Everything tied to lyric timing moves with the lines: section label, background switches (chorus 8.75–17.75 s and 24.75 s to the end, verse 2 17.75–24.75 s), the lighthouse cue (8.75–12.25 s and 24.75–32.0 s), and the markers.
- Title card: still visible from 0, now until 1.75 s, when the first lyric fades in (the build ends `intro` at the first lyric's show time).
- I redid round 1's hand edit at the shifted times: `lyric-next` `visible` = false at 15750 ms and true at 17750 ms, so the screen is clear during the break.
- The video still ends at 32.0 s. The last line now stays up 0.25 s longer (28.25–32.0 s).

## 2. Chorus lines 25 % larger

- I added stepped (`hold`) keyframes to the `lyric` layer's `size`: 50 px at 0, 62.5 px at 8750 ms, 50 px at 17750 ms, and 62.5 px at 24750 ms. That makes all four chorus lines (lines 3, 4, 7, 8) 1.25× the verse size.
- The text box is 1160 px wide and set to fit, and at 62.5 px the chorus lines are too wide for one line. My first export showed the box shrinking them to only about 1.10–1.15×. To fix this I also keyframed the box `height`: 120 px outside choruses and 170 px during them. The chorus lines now wrap onto two lines at the full 62.5 px instead of being shrunk. `lyric-next` sits lower by about 26 px while a chorus line is up. The size keys change only while the lyric is hidden between lines, so nothing jumps on screen.
- Only the current-line `lyric` layer changes size. `lyric-next` stays at 30 px even when the line it previews is a chorus line. That is how I read "chorus lines": the large current line.

## Checks

- `lyric-video-build`: 8 lines, 3 sections, no warnings.
- Previewed the timeline at 7.0 s (verse) and 13.5 s (chorus). I also pulled frames from the final MP4 at 1.0, 1.70, 1.80, 5.10, 5.40, 7.0, 8.60, 9.2, 10.5, 13.5, 15.9, 17.9, 20.0, 26.5, 28.4 and 30.0 s and measured the white text rows with a small PIL script:
  - The title card still shows at 1.70 s. At 1.80 s it is gone and the first lyric is fading in; round 1 started it at 2.0 s. The screen is empty at 5.10 s (fade-out before 5.25 s) and at 15.9 s (the break).
  - Chorus glyph height for "Turn your golden eye…" is 57 px, against 46 px in round 1, so 1.24×. Verse frames at 7.0 s are pixel-identical in layout to round 1 (same text row: 47 px tall, 784 px wide).
- I did not re-run the round-1 `vixl_check` contrast pass. Colours and styles are unchanged.

## Unsure

- The larger chorus lines now wrap onto two lines; for example "Lighthouse, lighthouse, sweep across the / sea". Keeping them on one line at 1.25× would need about 1240–1300 px, which is wider than the 1280 px frame for the longest line.
- Section changes and background cuts moved 0.25 s earlier along with the lyrics, since they are timed by the same LRC timestamps. They are not anchored to the original music times.

## Tool calls

21 tool calls in this round: Vixl MCP 12 (one `lyric-video-build` timed out on the shared server, then the retry succeeded), Bash 7, ToolSearch 1, plus the final hand-back.
