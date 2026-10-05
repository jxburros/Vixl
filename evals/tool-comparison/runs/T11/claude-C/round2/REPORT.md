# T11 round 2 · Red roof and a chimney (lane C: Python, OpenCV, NumPy, Pillow)

**Tool calls:** 9 in total for this round (including writing this report and the final hand-back).

To run it from this folder: `python3 step4_chimney.py && python3 step3_color.py`. The first script reads round 1's `../strokes.json`. Nothing outside `round2/` was changed.

## What changed
1. **Roof color.** It is now red `#c0392b` instead of coral `#e2725b`. The only change is the `roof` entry in the palette in `step3_color.py`, which I copied from round 1 into `round2/`. A sample pixel in the roof is RGB (192, 57, 43), which is #c0392b.
2. **Chimney.** I added one new stroke on the right slope of the roof. It is an open polyline with a left side, a flat top and a right side: (958.0, 530.5) → (958.0, 468.0) → (1022.0, 468.0) → (1022.0, 593.0). Both feet sit exactly on the fitted right roof line, (841.4, 416.6)–(1133.3, 701.7). The chimney runs from 40% to 62% of the way from the apex to the eave, and it is 64 px wide. Its top is 62 px above the roof at its left side, so the right side is taller (125 px) because the roof slopes down.
   - **Same line weight and character.** The chimney goes through the same renderer as every other stroke: the round 1 stroke width of 6.0 px, OpenCV anti-aliased polylines drawn at 3x and scaled down, and round caps. In the SVG it is `<path id="s26-chimney">` inside the same `<g id="lines">` group, so it gets the same `stroke-width="6.0"` and round caps and joins. Like the house walls, its sides are exactly vertical and its top exactly horizontal.
   - **Fill.** The chimney is a closed region made by its three sides and the roof line. The brief has no chimney color, so I filled it with the same roof red `#c0392b` to read as brick. The script finds the region and checks with an assert that it is closed and was not already assigned to another color. The roof line still runs across the chimney's base, so the chimney sits on the roof.

## Files (all in round2/)
| File | What it is and how I made it |
| --- | --- |
| `sketch-clean.png` | 2000 x 1485, black lines on white. It is round 1's 26 strokes plus the chimney, drawn by the same render function as round 1. |
| `sketch-lines.svg` | 2000 x 1485 with no raster images. It has 27 vector elements: 26 `<path>` and 1 `<circle>`. The new one is `s26-chimney`. |
| `sketch-color.png` | 2000 x 1485 RGB. Every color is the same as round 1 except the roof, which is now `#c0392b`. The chimney is also `#c0392b`. Region assignment found 2 roof regions (the roof and the chimney) and left nothing unassigned. |
| `compare.png` | 2799 x 1080. The original photo and the new colored result side by side, laid out the same way as round 1. |
| `strokes.json` | The editable source. It is round 1's strokes plus the chimney stroke, which is tagged `"added": "round2-chimney"`. `gap_log` has a new entry that records the addition. |
| `step4_chimney.py` | New script. It finds the right roof line in `../strokes.json` and adds the chimney on it. It then writes the PNG, SVG and JSON with the same render and SVG code as round 1's `step2_vectorize.py`. |
| `step3_color.py` | A copy of round 1's script with three edits: the roof color, a rule that assigns the chimney region the roof red, and the fixture path, which needs one more `../` because the script is now one folder deeper. |

## Notes and judgment calls
- The chimney's position (on the right slope, about the middle of it), its size and its red fill were my own choices, because the request does not set them.
- The brief from round 1 said not to add objects. This round, the chimney was asked for directly, so it is the only addition.
