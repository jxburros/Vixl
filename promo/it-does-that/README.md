# It does that?

**Nine things you might not expect from a design engine.** A one-minute video about Vixl's less obvious
features. Each shot runs the real feature inside the scene, so the art on screen is that feature's output,
not a mock-up of it. The soundtrack is a Vixl document too.

**[`vixl-it-does-that.mp4`](vixl-it-does-that.mp4)** · 57.5 s · 1920×1080 · 30 fps · AAC stereo 48 kHz · 6.1 MB

![Contact sheet, one frame from the middle of each shot](contact-sheet.jpg)

## The cut

| Time | Shot | Feature | What runs in the build |
| --- | --- | --- | --- |
| 0:00 | `01-hook` | | "You know Vixl makes posters. Here are nine things you might not expect." |
| 0:05 | `02-sketch` | Sketch → vectors | A synthesized phone photo of a pen sketch goes through `drawing import`, `vectorize`, `straighten`, `fill` and `stroke`; the stat line quotes `drawing report` (lines kept, strokes, tilt corrected) |
| 0:11 | `03-badges` | Spreadsheet → print run | A badge template with `${name}`, `${org}` and a `qr` of `${id}` is merged from a 200-row CSV with `merge-impose`: 25 letter sheets, crop and registration marks, every QR code different. The three sheets on screen are renders of the sheet document it writes |
| 0:17 | `04-emoji` | Emoji masters | The bundled 🦄 master (`vixl emoji get`) comes apart into its 12 layers and is recoloured. The count (3,953) is read from `vixl emoji list` |
| 0:22 | `05-mandala` | One petal → mandala | Three asymmetric petals and a dot, each through `radial-repeat` with `mirror: true` |
| 0:27 | `06-pixel` | Pixel art that walks | A robot drawn as `pixel-art` rows (shown on the left in their own colours), four walk frames stepped with `visible` keys, a looping tile ground and the frames as a sheet |
| 0:32 | `07-forms` | Fillable forms | Real `field` layers (text, email, date, dropdown, checkbox, signature) on a paper card; the email rule catches a typo before it is fixed |
| 0:37 | `08-diagram` | Text → diagram | `diagram-from-text` lays out and routes `idea -> sketch -> layers -> check -> ship` / `check -> fix -> layers`; nodes and edges animate as ordinary layers |
| 0:42 | `09-garden` | Seeded plants | Five `organic` presets (tree, sunflower, fern, rose, pine) grow from their seeds, then regrow from the next seed |
| 0:47 | `10-score` | The soundtrack | A piano roll of every note in `score.vixl`, eight `audio-track` layers; the playhead marks where the shot actually sits in the film |
| 0:53 | `11-end` | | The Ripple wordmark builds letter by letter and its reflection ripples in: "It does that, too." · github.com/jxburros/Vixl |

## The soundtrack

`build/score.py` writes the music as Vixl operations: one `audio-track` per instrument (kick, snare, hihat,
bass, piano, bell, whoosh, pop) using the built-in synthesizer, 120 BPM in A minor over Am–F–C–G. The
drums enter on the first cut, a whoosh leads into every cut, and the end card holds an Am(add9) chord.
`score.vixl` is saved next to this README; `export_audio` mixes it to `audio/score.wav`, and
`film-export` muxes that WAV into the MP4. Shot 10 draws its piano roll from the same note lists.

## What is in this folder

| Path | What it is |
| --- | --- |
| `vixl-it-does-that.mp4` | The finished video |
| `scenes/*.vixl` | Eleven editable 1920×1080 masters with keyframe timelines; images and fonts embedded |
| `score.vixl` | The soundtrack as an editable Vixl document |
| `film-spec.json` | The `film-export` request: shot order, durations and the audio track |
| `build/film.py` | Points the shared promo kit (`promo/build/kit.py`) at this folder, plus a few helpers |
| `build/assets.py` | Runs the drawing pipeline, the badge merge and the emoji export into `work/` (not committed) |
| `build/scenes.py` | The eleven shots |
| `build/score.py` | The score as `audio-track` operations |
| `build/make_video.py` | Builds everything and runs `film-export` |
| `build/preview.py` | Writes contact sheets of sampled frames for quick review |

## Rebuild

You need Python 3.11+, ffmpeg on `PATH`, and network access the first time, when Vixl downloads
Inter Tight, Inter and JetBrains Mono.

```bash
python -m pip install -e .
python promo/it-does-that/build/make_video.py            # assets, scenes, score and the MP4
python promo/it-does-that/build/make_video.py --scenes   # rebuild only the masters
python promo/it-does-that/build/preview.py /tmp 04 06    # contact sheets for selected shots
```

To change one shot, edit its master directly instead, for example
`vixl -p promo/it-does-that/scenes/05-mandala.vixl render --time 3s --out frame.png`, and then re-run
`film-export` with `film-spec.json`. Re-running `make_video.py` overwrites the masters.

## Credits

The unicorn in shot 4 is from [OpenMoji](https://openmoji.org) 17.0.0 by Sofie Ascherl, licensed
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); the credit is also on screen. Names on the
badges are invented.
