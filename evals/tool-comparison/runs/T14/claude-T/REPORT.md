# T14 Lyric video — lane T (ffmpeg + ImageMagick + Python glue)

## Timing
Start 2026-10-05 22:20:34 UTC, end 22:39:41 UTC (about 19 min). 20 tool calls. About 12 of those minutes were spent waiting on a first render that was too slow (a 1800×1800 RGBA rotate on every frame); fixing that cut a render to about 1.5 min.

## Files
| File | What it is / how it was made |
| --- | --- |
| `lighthouse.mp4` | Final video: 1280×720, H.264 (High, yuv420p, 30 fps, CRF 20), AAC-LC 44.1 kHz 160 kb/s. Video and audio both 32.000 s, the same as `lighthouse.wav`. The song's audio was resampled from 22.05 kHz mono to AAC 44.1 kHz mono. |
| `build.py` | The editable source. Running `python3 build.py` rebuilds everything: it parses the LRC, writes `lighthouse.ass`, makes the PNGs in `assets/` with ImageMagick `convert`, then runs one ffmpeg `filter_complex` (background switching, glow and beam overlays, a drawn lighthouse silhouette, and ASS subtitle burn-in). |
| `lighthouse.ass` | Generated ASS subtitle script: the title card, the current and next lines, and the section labels. You can edit it by hand, but `build.py` overwrites it. |
| `assets/bg_title.png` | Title-card background: navy dusk gradient with an amber horizon line (ImageMagick). |
| `assets/bg_verse.png` | Verse background: cold teal/navy night gradient with noise stars and a dark sea band. |
| `assets/bg_chorus.png` | Chorus background: warm purple-to-red sunset gradient with an amber radial glow and a horizon line. |
| `assets/beam.png` | Warm light cone with a lamp halo, transparent, fading along its length. ffmpeg rotates it on a sine to make the sweep. |
| `assets/glow.png` | Warm radial wash. ffmpeg screen-blends it over the frame at 30% opacity. |

## How the brief is implemented
- **LRC parsing:** `[ti:]` is used as the title ("Lighthouse") and `[ar:]` as the artist ("The Vixl Examples"). `[al:]` is parsed but not shown. Bracket-only text (`[Chorus]`, `[Verse 2]`) is a section marker. A timestamp with no text (16.00) clears the screen. The double-timestamp line (25.00 and 28.50) becomes two lyric events.
- **Title card:** 0–2 s, with the title in large serif type and the artist in spaced small caps.
- **Lyrics:** each line shows from its timestamp until the next lyric or clear timestamp; the last one runs to the end of the song (32 s). The current line is DejaVu Sans Bold 58 px, centred around y=320; long lines wrap onto two lines. The next lyric line is shown beneath it at 32 px italic and semi-transparent, around y=450.
- **Section label:** shown top-left in small caps, from the first section marker (Chorus at 9.00) onwards. It stays until the next marker: Chorus 9–18, Verse 2 18–25, Chorus 25–32.
- **Backgrounds:** chorus sections (9–18 and 25–32) use the warm sunset background. Everything else after the title (2–9 and 18–25) uses the cold teal night background.
- **"Lighthouse" glow:** while the current line contains the word "lighthouse" (case-insensitive, whole word: 9–12.5, 25–28.5 and 28.5–32), three things happen. A warm radial wash is screen-blended over the frame, a warm beam sweeps from the lighthouse lamp, and the lamp square turns bright amber (it is dim brown otherwise).

## Choices and differences from the brief
- **2–9 s:** this comes before any section marker, so no section label is shown, as the brief asks. It uses the verse background because it reads as an unlabelled first verse.
- **Instrumental break (16–18 s):** the lyrics are cleared. The section label stays "CHORUS" and the background stays the chorus one, because the LRC hasn't started a new section yet. During the break I still show the upcoming line ("The gulls are sleeping…") in the small "next" slot as a cue; only the large current line is cleared. If "clears the screen" means every line, this is a deviation.
- **"Next line":** this is always the next *lyric* line. It skips section markers and the clear. At 25–28.5 the next line is the same chorus line, because it repeats at 28.5. After the last line (28.5–32) no next line is shown.
- **Lighthouse silhouette:** a small dark tower with a lamp is drawn at the lower left in every scene, including the title card, so the glow has a source. This is my own addition.
- **Transitions:** lines fade in over 150 ms. Backgrounds cut hard at the section timestamps.
- **No editable source beyond the script:** this toolchain has no project file, so `build.py` together with `lighthouse.ass` is the editable source.

## Things I'm unsure about
- The beam is soft and fairly low-contrast against the warm chorus background; the warm wash and the lit lamp carry most of the "glow". I checked it in frames at 10, 11, 26, 27.5 and 31.5 s.
- Long lines wrap onto two lines rather than shrinking to fit one; I think this is acceptable for "large and centered".
- The fonts are DejaVu Sans and DejaVu Serif from the system (the ASS renderer finds them through fontconfig). Rendering on another machine depends on those fonts being installed.
