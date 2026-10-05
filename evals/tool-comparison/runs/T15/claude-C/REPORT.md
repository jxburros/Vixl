# T15 Seamless pattern — Lane C (code: pycairo + NumPy + Pillow)

## Files
| File | Size | How it was made |
| --- | --- | --- |
| `make_pattern.py` | — | The editable source. One deterministic Python script (seed 15) that writes all the files below. Run `python3 make_pattern.py`. `pycairo` was pip-installed for it (1.29.2). |
| `tile.png` | 1024 × 1024 RGB | Drawn with pycairo on an ImageSurface. |
| `tile.svg` | 1024 × 1024 px viewBox | The same drawing calls sent to a cairo SVGSurface, so it is true vector (paths), not an embedded bitmap. |
| `preview-3x3.png` | 3072 × 3072 | `tile.png` pasted 3 × 3 with Pillow. |
| `mug-wrap.png` | 2550 × 1050 | The tile used as a repeating cairo pattern, starting at (0,0), plus a centred 600 × 300 cream (#f7f1e5) rounded rectangle (corner radius 36 px) with a 4 px navy outline and a thin inner navy rule. It reads "Tidewick" in navy, P052 Bold (a URW Palatino clone) at 112 px, centred on the canvas. |

## Method
- **Motifs** (all hand-built vector paths): kelp fronds (a curved Bézier stem with 7 alternating leaf blades that get smaller toward the tip), spiral shells (a filled body with a lip and a cream logarithmic spiral), curling waves (a swell that rises into an inward spiral, with two trailing lines), and dots (radius 4–9 px).
- **Palette**: only the five brief colours. Navy #14263b, amber #f2a541, sea-foam #a8d5c8 and coral #e2725b are used for the motifs, on a cream #f7f1e5 background. Kelp is navy or sea-foam. Waves are navy, coral or sea-foam. Shells are amber or coral. Dots use all four colours.
- **Distribution**: random placement on a torus with rejection, where each new motif's bounding radius plus padding must clear every existing one, measured with wrap-around distance. Large motifs are placed first, then dots fill the gaps. This gives an even spread with no grid. The tile has 8 kelp, 8 waves, 12 shells and 140 dots. Sizes vary: kelp ×0.75–1.15, waves ×0.7–1.1, shells ×0.55–1.0, plus five dot sizes.
- **Seamless**: each motif is drawn at its 9 torus offsets (±1024 px in x and y), skipping copies that cannot reach the tile, and the result is clipped to the tile. Anything crossing an edge therefore continues exactly on the opposite edge. Per-motif randomness is seeded so every copy is identical.
- **Seam check**: the tile was rolled by 512 px so its old edges meet in the middle. The mean RGB difference across the old seam was 3.18 (columns) and 0.54 (rows). Ordinary adjacent interior pixel pairs gave 1.46–3.66. The seam is no different from interior pixels. I also looked at `mug-wrap.png`, where the tile repeats about 2.5 times across, and saw no seams.

## Deviations, choices and things I'm unsure of
- **Rotation**: shells and dots get any rotation. Kelp is limited to ±0.6 rad and waves to ±0.5 rad so fronds stay roughly upright and waves stay readable as waves. This is less "varied rotation" than full 360°.
- **Distribution**: a few areas are a little sparser than others, and several waves ended up in the middle band of the tile. It is not a grid, but evenness is a judgement call.
- **SVG**: the SVG contains the wrapped copies that run past the 0–1024 viewBox, and the background rect is oversized (cairo writes it that way). Viewers clip to the viewBox, so it displays as the same tile, but the raw geometry runs past the edges. Colours are written as rgb() percentages, not hex.
- **mug-wrap**: the pattern simply repeats horizontally. 2550 is not a multiple of 1024, so the two short ends of the wrap do not meet seamlessly when the print is wrapped around a mug. The brief did not ask for that. The label's outline and inner rule are my own additions; the brief only asked for a cream label with rounded corners.
- The mug-wrap PNG has no 300 dpi metadata (pycairo `write_to_png` does not write pHYs). Only the pixel size matches the spec.

## Timing
Start 22:23:17 UTC, end 22:24:31 UTC (2026-10-05). About 1.5 minutes of wall-clock time for the work, plus writing this report. 8 tool calls in total, including writing this report and the handback.
