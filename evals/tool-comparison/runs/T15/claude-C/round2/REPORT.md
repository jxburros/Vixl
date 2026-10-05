# T15 Seamless pattern, Lane C, round 2

The changes asked for: make every shell amber, and cut the number of motifs by about a third. Every file was regenerated.

## What changed
I copied `../make_pattern.py` into `round2/` and changed four lines in `layout()`. Nothing outside `round2/` was touched.

| Motif | Round 1 | Round 2 | Colours in round 2 |
| --- | --- | --- | --- |
| Kelp | 8 | 5 | navy / sea-foam (unchanged) |
| Waves | 8 | 5 | navy / coral / sea-foam (unchanged) |
| Shells | 12 | 8 | **amber #f2a541 only**. Before, they cycled amber, coral, amber. |
| Dots | 140 | 93 | navy / amber / coral / sea-foam (unchanged) |
| **Total** | 168 | 111 | 34% fewer |

The script's printout confirms the counts: `{'kelp': 5, 'wave': 5, 'shell': 8, 'dot': 93}`. Each large-motif type was cut by about a third. Coral still appears in one wave and in the dots, because the request was only about shells.

## Files (all in `round2/`, same names as round 1)
| File | Size | How it was made |
| --- | --- | --- |
| `make_pattern.py` | — | The edited generator (seed 15, pycairo + NumPy + Pillow). Run `python3 make_pattern.py` inside `round2/`. It writes into its own folder. |
| `tile.png` | 1024 × 1024 RGB | pycairo ImageSurface |
| `tile.svg` | 1024 × 1024 px | The same drawing calls sent to a cairo SVGSurface (vector paths, 197 `<path>` elements) |
| `preview-3x3.png` | 3072 × 3072 | `tile.png` pasted 3 × 3 with Pillow |
| `mug-wrap.png` | 2550 × 1050 | The tile repeated as a cairo pattern, plus the same centred 600 × 300 cream label (radius 36, navy outline and inner rule) with "Tidewick" in navy P052 Bold at 112 px. This part is unchanged. |

## Checks
- **Seam.** I compared the opposite edges of the tile, which is the same as the old-seam pair after a 512 px roll. The mean RGB difference was 1.78 for left/right and 0.24 for top/bottom. The same measure for all interior adjacent columns runs from 0.17 (10th percentile) to 0.76 (median) to 4.19 (99th percentile), with a maximum of 5.54. Rows are similar. So the edges look like ordinary interior pixels. Wrapping is still done by drawing each motif at its 9 torus offsets.
- **Shell colour.** I looked at a downscaled tile and the mug wrap: all 8 shells are amber, with cream spirals.
- **Sizes.** I checked all PNG pixel sizes against the brief.

## Notes
- **Layout.** The placement is a new arrangement, not round 1 with motifs taken out. The rejection sampler stops after fewer placements, so the shared random stream moves on to the next motif type at a different point. Kelp may share some early positions with round 1, but the rest differ. With fewer motifs the tile has more open cream space. It is still not a grid.
- These limits from round 1 still apply: kelp and wave rotation is limited, the SVG geometry runs past the viewBox (it is clipped on display), the mug-wrap PNG has no 300 dpi metadata, and the wrap's short ends do not meet seamlessly because 2550 is not a multiple of 1024.

## Timing and tool calls
Start 22:29 UTC, end about 22:31 UTC (2026-10-05). There were 9 tool calls in total: 5 Bash calls (2 to read the brief and script, 1 to edit and regenerate, 1 to check, and 1 to clean up and write this report), 2 image Reads, and 1 Bash call to correct this count, and the final handback.
