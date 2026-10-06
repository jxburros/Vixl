# T14 Lyric video: Vixl lane (claude-V)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `lighthouse.mp4` | The lyric video. 1280x720 H.264 (yuv420p, 24 fps, 768 frames) with AAC audio (24 kHz). The container, video and audio each last 32.000 s, the same as `lighthouse.wav`. | Rendered by Vixl's `lyric-video-export` workflow (MCP `vixl_workflow`, run as a job). The song was muxed in as the audio track. |
| `lighthouse-template.vixl` | The editable design template. It holds the backgrounds, the lighthouse, the beam cue, the text layers and the fonts. | Built with Vixl MCP operations (`gradient`, `shape`, `group`, `text`, `text-layout`, `constrain`, `pivot`, `effect`, `look`, `variable`) plus `vixl_font_install`. |
| `lighthouse-lyrics.vixl` | The editable keyframed timeline document the video was rendered from (91 keyframes, with markers per section and per line). | `lyric-video-build`, run from the template and the LRC. Export reused it as is (`build_reused: true`). |
| `request.json` | The workflow request used for plan, build and export. | Written by hand. It points at the fixtures in `evals/tool-comparison/fixtures/`, which were not copied. |
| `REPORT.md` | This file. | |

## How the brief maps onto the build

- **Title card from 0 to 2 s:** the `intro` group shows `${title}` ("Lighthouse", Playfair Display 700) over `${artist}` ("The Vixl Examples", Lato), with a short amber rule between them. The variables come from the LRC `[ti:]` and `[ar:]` tags. The intro is visible until the first line shows at 2.000 s.
- **Line timing:** `lead: 0`, so each line appears exactly at its timestamp and stays until the next timestamp. Lines fade in and out over 250 ms. The current line (`lyric`) is Playfair Display 64 px, centred in a fitted 1000x190 box. The next line (`lyric-next`) is Lato 30 px, centred beneath it.
- **Section labels:** `[Chorus]` and `[Verse 2]` were treated as section markers, not lyrics. `section-label` sits small in the top-left corner (Lato 24 px, amber). It is blank from 0 to 9 s, because the first section marker is at 9 s. After that it reads Chorus, Verse 2, then Chorus.
- **Instrumental break:** the empty timestamp at 16 s clears the lyric and the next-line preview until 18 s. The section stays "Chorus" until Verse 2 begins.
- **Line sung at two times:** `[00:25.00][00:28.50]` became two lines. Because the line repeats straight after itself, Vixl holds it on screen without fading it out and back in. From 25 to 28.5 s the "next" line shows that same text, which is correct for this LRC.
- **Backgrounds:**
  - Verses (`bg-verse`, and `bg-default` for the unlabelled opening lines from 2 to 9 s) are a cool blue-navy night sky. Verse 2 also has a moon.
  - Choruses (`bg-chorus`) are a warm plum-to-orange dusk with a sun glow on the horizon.
  - A silhouetted sea and the lighthouse are on screen throughout.
- **"Lighthouse" glow:** the `cue-lighthouse` group holds a warm radial glow, a soft blurred beam and a bright lamp flare. It is visible only while the current line contains "Lighthouse": 9.0 to 12.5 s and 25.0 to 32.0 s. It fades in and out over 300 ms. While it is up, the beam sweeps ±10 degrees about the lamp (pivot at the lamp, 3.5 s period). Outside those times the lamp is dark.

## Choices and deviations

- **No section label from 0 to 9 s.** The LRC has no section marker before `[Chorus]` at 9 s, so I read "once the first section begins" literally and invented no "Verse 1" label. Those lines use the `bg-default` night background, which is styled like the verses.
- **Audio sample rate.** The AAC track is 24 kHz mono, while the source WAV is 22.05 kHz. Vixl's exporter resampled it. The duration is unchanged.
- **Last frame.** At 32.00 s (the very end) the lyric has faded out, because the last line hides at the end of the song.
- **Wrapping.** At 64 px, "A single light is burning for my sake" wraps with "sake" alone on the second line. I left it, because widening the text box would collide with the lighthouse on the right.

## Checks done

- **Container and streams (ffprobe):** h264 1280x720 and aac, both 32.000 s.
- **Audio level (volumedetect):** mean -18.8 dB, max -9.6 dB, so the track is not silent.
- **Visual review:**
  - A 16-frame contact sheet (`vixl_timeline_preview`) shows: the title card; the verse and chorus backgrounds; the beam on the "Lighthouse" lines only; the cleared break at 16 to 18 s; the section labels.
  - A frame grabbed from the MP4 at 10 s matched.

## Unsure about

- **Chorus contrast.** The lighter lower part of the chorus background, plus the beam, sits behind the small next-line text. It looked readable to me (I added a soft shadow), but I did not run a formal contrast measurement on every frame.
