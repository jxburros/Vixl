# T15 round 2 — claude, lane W (web code + headless Chromium)

Changes asked for: make all the shells amber, and cut the number of motifs by about a third. Every file was regenerated.

## What changed
- **All shells amber.** In `make_pattern.py` the shell palette was `[(CORAL, NAVY), (AMBER, NAVY), (FOAM, NAVY), (CORAL, AMBER)]`. It is now just `[(AMBER, NAVY)]`. Every shell body is amber `#f2a541`, and its spiral line and ridges are navy `#14263b` so they still show up against the amber. I checked `tile.svg`: all 9 shell bodies use fill `#f2a541`.
- **About a third fewer motifs (158 down to 106, -33%).**

  | Motif | Round 1 | Round 2 |
  | --- | --- | --- |
  | kelp fronds | 7 | 5 |
  | curling waves | 8 | 5 |
  | spiral shells | 13 | 9 |
  | dots (large / small) | 70 / 60 | 47 / 40 |
  | **total** | **158** | **106** |

  Each motif keeps its old size range. I widened the minimum spacing in the toroidal dart-throwing (kelp and waves 18 to 40 px, shells 16 to 34, dots 14/10 to 26/18) so the smaller set still spreads evenly over the tile and does not clump. The seed is still 15, but with fewer throws the placement is a new arrangement and not a subset of round 1. All requested counts were placed. 6 motifs cross an edge and are drawn again on the opposite side.
- The colours of kelp, waves and dots did not change.

## Files (all in this folder)
| File | How it was made |
| --- | --- |
| `make_pattern.py` | Copied from round 1. Edited only the placement counts and gaps and the shell palette. Run `python3 make_pattern.py tile.svg`. |
| `render.py` | Copied from round 1 without changes. It reads `tile.svg` from its own folder. Run `python3 render.py`. |
| `tile.svg` | 1024 × 1024 vector tile written by `make_pattern.py`. |
| `tile.png` | 1024 × 1024 px, screenshot of the SVG in Chromium (Python Playwright). |
| `preview-3x3.png` | 3072 × 3072 px, the tile as a repeating CSS background, rendered in Chromium. |
| `mug-wrap.png` | 2550 × 1050 px. Same layout as round 1: repeating pattern centred, cream 600 × 300 label at x 975–1575, y 375–675, 40 px radius, 6 px navy border, "Tidewick" in navy P052 Bold at 118 px. |

## Checks
- `identify` reports these sizes: 1024×1024, 3072×3072 and 2550×1050.
- Seam pixel check on `tile.png`, as mean abs RGB difference. Column 0 against column 1023 is 3.68, and adjacent interior columns 0/1 are 2.76. Row 0 against row 1023 is 1.22, and rows 0/1 are 1.85. The values across the wrap match those between neighbouring columns or rows, so there is no visible seam.
- I looked at `tile.png` and `mug-wrap.png`: all shells are amber, there are fewer motifs, and the spread is still even with more cream between motifs.

## Deviations / unsure
- I carried over the same choices as round 1: the label has a navy outline, and the mug wrap's two ends do not join seamlessly, because 2550 is not a multiple of 1024.
- On the cream ground the amber shells are less bold than the old coral ones. The navy spiral line keeps them readable.
- Because the motifs are sparser, the open cream gaps are a little larger than in round 1. That is expected with a third fewer motifs.

## Tool calls
8 tool calls in total, counting this report and the final handback.
