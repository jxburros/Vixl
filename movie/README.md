# The Germ King

*A very small revenge.* A short animated film made entirely with Vixl (rebuilt with Vixl 0.21.0).

Wizard Pip is too short to be taken seriously by the Council of the Very Tall. So he shrinks
himself to microscopic size, discovers a world where he is finally the tall one, becomes
king of the germs, and marches them on the Council with a plan that is, frankly, nothing
to sneeze at.

**[`the-germ-king.mp4`](the-germ-king.mp4)** · 50.8 s · 1280×720 · 24 fps · 1,219 frames · AAC audio · 9.1 MB

## What is in this folder

| Path | What it is |
| --- | --- |
| `the-germ-king.mp4` | The finished film |
| `scenes/*.vixl` | Eight editable Vixl masters, one per shot. Open any of them to change a layer, a keyframe or a line of dialogue |
| `film-spec.json` | The `film-export` request: shot order, crossfades, camera moves and audio mix |
| `build/` | Python that generates the scenes, the score and the film |

`make_film.py` also writes the synthesised score and sound effects to `audio/` (not committed; they are regenerated each run).

Everything is regenerated from code. Nothing is hand-painted, imported or sampled.

## The scenes

| # | Master | Length | Story beat |
| --- | --- | --- | --- |
| 1 | `01-council` | 9.0 s | Pip walks into the Council of the Very Tall and is ignored |
| 2 | `02-shrink` | 6.0 s | "…I'll go SMALLER!": magic circle, spin, white-out |
| 3 | `03-arrival` | 7.0 s | Pip lands among the germs. They think he is *tall* |
| 4 | `04-coronation` | 7.0 s | The crown, the confetti, ALL HAIL KING PIP |
| 5 | `05-march` | 5.5 s | The army marches. A sleeping giant rises |
| 6 | `06-sneeze` | 5.2 s | Tickle, tickle… AH-CHOO!!! |
| 7 | `07-aftermath` | 9.5 s | The Council takes him *very* seriously now |
| 8 | `08-title` | 4.5 s | Title card |

Each master is an ordinary Vixl document (about 180–410 layers, built from 790–2,280 operations) with a keyframe timeline.
Characters are one layer per part, grouped so limbs pivot at joints (`pip_armL`), eyes blink
(`pip_eyeL`), mouths flap by stepped `visible` keys (`e2_mouth`), and speech bubbles pop in and
out as groups (`sayPip1`).

## Rebuild it

Requires Python 3.11+, ffmpeg on `PATH`, and network access the first time (Vixl downloads the
Fredoka Bold font from Google Fonts and caches it).

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e .            # Vixl itself (numpy and Pillow come with it)
cd movie/build
python build.py                       # scenes/*.vixl (add scene names to rebuild one)
python make_film.py                   # audio/*.wav, film-spec.json, ../the-germ-king.mp4
```

`make_film.py` renders 1,219 frames, so expect it to take a while. With Vixl 0.20.0 on a shared
4-core container, `build.py` took 19 s and `make_film.py` about 19 minutes (1,159 s).

To tweak a single scene in the real editor-style loop instead of regenerating it:

```bash
vixl -p movie/scenes/07-aftermath.vixl timeline-sheet --out sheet.png --count 12
vixl -p movie/scenes/07-aftermath.vixl render --time 7.2s --out frame.png
```

Or drive it over MCP: `vixl_timeline_preview`, `vixl_render_preview(time=…)` and `vixl_operations_apply`
all work on these documents. If you edit a master by hand, `make_film.py` will pick the change up
(it re-exports from `scenes/`), but `build.py` will overwrite it.

## How it is built

* `build/vixlkit.py` — a small helper that collects Vixl operations (`shape`, `pen`, `group`,
  `pivot`, `keyframe`, `layer-style`, …) and applies each scene as one atomic batch (up to 9,000
  operations per call; Vixl 0.20.0 allows 10,000, where 0.18.0 allowed 1,000).
* `build/characters.py` — Pip, the three council elders and the germs.
* `build/scenes.py`, `build/scenes_b.py` — the eight scene definitions.
* `build/score.py` — a numpy synthesiser for the score, sound effects and talking blips. The blips
  are generated from the same mouth-flap windows that animate the characters, so they stay in sync.
* `build/make_film.py` — assembles the shots with `vixl workflow film-export`
  (crossfades, slow camera moves, a two-track audio mix) and writes the MP4.

### Known limits (Vixl 0.20.0)

* The score is synthesised at 44.1 kHz, but 0.20.0's `film-export` premixes every audio track at
  24 kHz stereo (linear resampling), so the soundtrack has nothing above 12 kHz. The film made
  with 0.18.0 carried 44.1 kHz mono audio.
* The camera moves are crops that are enlarged with bicubic resampling, so the zoomed shots
  (most visibly `02-shrink`, up to 1.22×) are a little soft.
* Speech bubbles are hand-placed groups that pop in and out; 0.20.0's text-sized bubbles that
  follow their target are not used here.
