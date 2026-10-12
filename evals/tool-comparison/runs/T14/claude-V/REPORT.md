# T14 Lyric video: Lane V (Vixl)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `lighthouse.mp4` | The final video: 1280 × 720, H.264 (yuv420p) at 30 fps with AAC audio (22,050 Hz mono, the song's own rate and channels). It runs 32.000 s, exactly the song's length. | Made with `vixl_workflow` `lyric-video-export` (MCP, run as a job). It used the template below, `fixtures/lighthouse.wav` and `fixtures/lighthouse.lrc`. |
| `lighthouse-template.vixl` | The editable template that holds the design. | Made with `vixl_document_create` (1280 × 720, Marcellus + Lato font pairing) plus `vixl_operations_apply` batches. |
| `lighthouse.vixl` | The editable keyframed timeline that the export rendered: 91 keyframes, with markers per section and per line. | Written by the `lyric-video-build` step inside the export (`rebuild: true`). It can be reopened and exported again. |
| `REPORT.md` | This report. | |

Export settings: `fps 30`, `quality final`, `lead 0`, a 250 ms fade in and out for each line, `next_line true`. The cue settings were a 400 ms fade in and out plus `motion: sweep` (±10°, a 3.5 s period).

## How the brief maps to the template

- **Title card, 0–2 s:** the `intro` group shows `${title}` ("Lighthouse", Marcellus 110 px) and `${artist}` ("The Vixl Examples"), centred. Both values are filled from the LRC `[ti:]` and `[ar:]` tags. The card stays on screen until the first lyric shows at 2.00 s.
- **Current and next line:** the current line is in `lyric` (Marcellus 64 px, centred). It sits in a 1040 × 190 box that wraps and fits the text. The next line is in `lyric-next` (Lato 30 px, slightly muted), below it. Each line shows at its own timestamp (`lead: 0`) and stays until the next timestamp. The empty `[00:16.00]` timestamp clears both lines until 18.00 s. The line with two timestamps, at 25.0 s and 28.5 s, is shown at both times. Because the same line is sung again right after itself, it stays on screen as one continuous display instead of fading out and back in. During 25–28.5 s the next-line slot shows the repeat.
- **Section label:** `section-label` sits top-left in small type. It reads "Chorus" from 9 s, "Verse 2" from 18 s and "Chorus" from 25 s. It is empty before 9 s, because the first section only starts there.
- **Backgrounds:** the verse look is a navy night sky with a crescent moon. It is used by `bg-default`, for the two opening lines that have no section marker, and by `bg-verse`, for Verse 2. The chorus look (`bg-chorus`) is a purple-to-orange dusk gradient with a low sun glow, so it is clearly different. The sea and the striped lighthouse stay on screen throughout.
- **"Lighthouse" glow:** the `cue-lighthouse` group is a blurred warm beam plus a radial glow around the lamp. It pivots at the lamp. It fades in, sweeps back and forth, and fades out while the current line contains "Lighthouse". That happens at 9.0–12.5 s and 25.0–32.0 s. I checked frames at 10.5 s, 14 s, 17 s, 27 s and 30.5 s.

## Things done differently, or worth knowing

- **Chorus background during the break:** it stays on through the instrumental break (16–18 s). The break sits inside the first Chorus section, which runs until the `[Verse 2]` marker, so the section has not changed. Only the lyrics clear.
- **Fades instead of hard cuts:** each line fades in over its first 250 ms and out over its last 250 ms. The screen still changes at each timestamp. The last line fades out over the final 250 ms of the song (31.75–32.0 s), because the video ends with the song. There is no outro card.
- **Fit-to-box text:** the lyric box shrinks text to fit. With 64 px type, every line fits on at most two lines, and none shrank visibly.
- **Contrast check on the template:** the design check measured the template with every layer visible at once, including the chorus sky and the beam behind the text. On that stack it flagged the muted next line and the artist line as low contrast. I made both more opaque (the artist line now uses the full `@ink` colour). In the rendered frames all text sits on dark navy or dark purple. I did not re-run the check on the built timeline frames.

## Verification

- **Export self-check:** `lyric-video-export` reported `verification: passed`. Video: h264, 1280 × 720, 30 fps, 960 frames, 32,000 ms. Audio: AAC, 32,000 ms. Difference from the song's length: 0 ms.
- **Independent ffprobe:** h264 1280 × 720 yuv420p, AAC audio, file duration 32.000000 s. The song (`lighthouse.wav`) is also 32.000000 s.
- **Visual checks:** a contact sheet of the build at 1, 3, 7, 10.5, 14, 17, 19.5, 27 and 30.5 s, plus frames pulled from the final MP4 at 1, 4, 10.5, 17 and 30 s.

## Unsure about

- I did not watch the video with sound, so the audio sync is checked only by timestamps. The LRC timings were used as given, with no offset.
- The section label is small (22 px), as the brief asked. It may be hard to read on phone-sized screens.
