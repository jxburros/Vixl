# T11 · Hand drawing to clean art (lane C: Python, OpenCV, scikit-image, SciPy, NumPy, Pillow)

**Timing:** start Mon Oct 5 22:22:41 UTC 2026, end Mon Oct  5 22:28:48 UTC 2026 (about 7 minutes). About 20 tool calls.

To run it: `python3 step1_rectify.py && python3 step2_vectorize.py && python3 step3_color.py` from this folder. I installed scikit-image and scipy with pip.

## Files
| File | What it is and how I made it |
| --- | --- |
| `sketch-clean.png` | 2000 x 1485, grayscale, black lines on white. Drawn from the fitted strokes in `strokes.json` with OpenCV anti-aliased polylines at 3x size, then scaled down. Stroke width is 6.0 px, taken from the median ink width. |
| `sketch-lines.svg` | 2000 x 1485 vector file with no raster images. It has a white `<rect>` background, then one `<g id="lines">` group that holds 25 strokes (6.0 px wide, round caps and joins). Straight strokes are `<path>` with M/L commands. The sun is a single `<circle>`. The canopy and the ground line are smooth cubic Bézier `<path>`s (Catmull-Rom converted to C commands). |
| `sketch-color.png` | 2000 x 1485 RGB. Flat colors fill the closed regions, and the line art is multiplied on top. Colors used: roof #e2725b, walls #f7f1e5, door and all 8 window panes #14263b, sun #f2a541, canopy #5a8f5a, trunk #7a5236, sky #d9ecf2, ground #a8d5c8. |
| `compare.png` | 2799 x 1080. The original photo on the left and the colored result on the right, both scaled to 1000 px high, with white gutters of 40 px. |
| `step1_rectify.py` | Finds the paper as the largest bright contour, reduces it to 4 corners, and does a perspective warp to 2000 px wide (height 1485 comes from the measured paper aspect ratio, inset 6 px so no desk shows). It then divides by a blurred background estimate to remove paper shading and shadow, and thresholds to get an ink mask. |
| `step2_vectorize.py` | Turns the ink mask into a skeleton and a pixel graph, merges paths that run straight through junctions, then fits each stroke: straight lines or polylines (total least squares per segment, corners at the line intersections), a circle (least-squares fit), or a free-hand curve (Gaussian smoothing). It closes gaps and writes the SVG, the clean PNG and `strokes.json`. |
| `step3_color.py` | Labels the connected regions, assigns each one a color using rules based on the geometry, fills the pixels under the lines, multiplies the lines on top, and builds the compare image. |
| `strokes.json` | The editable source: every stroke's geometry, the stroke width, and a log of every gap that was closed. |
| `work_ink.png`, `work_flat.png`, `work_rectify.json` | Intermediate files: the ink mask, the shading-corrected paper, and the corner coordinates and output size. (`work_warp.png` is also written by step 1, but I deleted it.) |

## Clean-up decisions
- **Tilt and perspective** are corrected by a 4-corner homography. The photo's top-left paper corner sits at the image edge (about x = 0), so that corner's position is slightly uncertain.
- **Straightening.** A stroke becomes straight when approxPolyDP (epsilon 7 px) splits it into segments that are all at least 35 px long, each fits a line with RMS ≤ 2.6 px, and each turns at least 30° from the next. Segments within 3.5° of horizontal or vertical are snapped exactly. That covers the house walls, the wall-top line, the door, the windows, the trunk and 3 of the sun rays. The roof lines and the diagonal rays keep their drawn angles. The top ray (about 4° off vertical) and the right ray (about 5° off horizontal) are straightened but not snapped.
- **Circle.** The sun was fitted as a full circle: centre (1552.1, 302.9), r = 122.1, fit RMS 1.4 px. This also closes the gap the drawing had at the top right of the circle.
- **Gaps closed** (all logged in `strokes.json`):
  - Canopy: the open left side (78 px) is bridged with a Hermite curve that follows both end tangents, so the canopy is a closed shape.
  - Ends extended along their direction until they meet a stroke (limit 38 px): the wall-top line to the left roof line (25 px), the left wall up to the wall-top line (19 px), the door jamb tops (10 and 2 px), the window crossbars (7 and 8 px), and the trunk foot (6 px).
  - The bottom-left corners of both windows were joined at the intersection of their lines.
  - The wall-top/right-wall corner stopped about 16 px short of the right roof line. I continued the wall up to meet it so that the roof becomes a closed shape. This adds a 16 px straight stroke that was not drawn.
- **Kept as drawn:** the composition, the roof eaves overhanging the walls, the gentle wave in the ground line (only smoothed, with sigma 12 px), the canopy lobes (smoothed, with sigma 5 px), the ray lengths and positions, and the stroke character (one uniform pen width).
- **Removed:** short skeleton spurs under 14 px. A side effect is that the small "x" overshoot where the roof lines cross at the apex is now only a few px.

## Coloring choices and deviations
- **Sky/ground boundary.** The drawn ground line stops about 140 px short of the left edge and about 125 px short of the right edge. To split the background "above/below the ground line", I extended it horizontally from each end to the paper edge as an **invisible** boundary used for color only. The two colors meet in a straight horizontal edge there, with no line drawn.
- **Region assignment** is automatic: sky is the region touching the top, ground the region touching the bottom, the sun is inside the circle, the canopy is at the canopy centroid, the trunk is between the two trunk lines, and the roof is just below the apex. Inside the house, the largest remaining region is the walls and every smaller one (9: 8 panes and the door) is navy. No region was left unassigned.
- The window crossbars and frames stay black lines on top of the navy panes, so they are dark on dark and fairly low contrast. That follows the brief.

## Unsure about
- Whether the brief means to snap near-vertical walls to exactly vertical. I did, because the lean is within 3.5°.
- The 16 px corner continuation under the right roof line, and the bridge across the canopy's left gap (78 px, which is larger than "small"), are both judgment calls I made so the regions could be filled.
- No editable source in a design tool. The editable sources are `strokes.json` plus the scripts, and the SVG is editable directly.
