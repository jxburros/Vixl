# T11 hand drawing to clean art (lane T, claude-T)

Tools I used: Python 3 with OpenCV and NumPy for analysis and fitting, Inkscape 1.x CLI to render the SVGs, and ImageMagick `convert` for the grayscale conversion and side-by-side. I did not use Vixl or any image generator. I didn't need potrace, autotrace, GIMP or ffmpeg; the reasons are at the end of the Method section.

## Files

| File | What it is / how it was made |
| --- | --- |
| `sketch-clean.png` | 2000x1485, 8-bit grayscale. Black lines on white, rendered from `sketch-lines.svg` with `inkscape -w 2000 -b white`, then `convert ... -colorspace gray`. The edges are antialiased, so it is not pure 1-bit. |
| `sketch-lines.svg` | Vector lines only, no `<image>` elements. There is a white `<rect id="paper">` background, then one layer `lines`: 29 `<line>` elements (roof, walls, wall top, window frames and muntins, door, trunk, 8 sun rays), one `<circle id="sun">`, one closed `<polygon id="canopy">` (the tree) and one `<polyline id="ground">`. All are strokes: black, 5.5 px wide, round caps and joins. Each element has a readable id. |
| `sketch-color.svg` | **Editable source.** An Inkscape-layered SVG. The layer "Color" holds flat filled shapes (sky, sea-foam ground, walls, roof, door, two windows, sun, trunk, canopy). The same "Lines" layer sits on top. |
| `sketch-color.png` | 2000x1485, rendered from `sketch-color.svg` with Inkscape. |
| `compare.png` | 2000x750: the original photo (left) and the colored result (right), each resized to 1000 px wide with ImageMagick `+append`. The original's 4:3 frame is slightly taller than the result, so the right half has a thin white strip above and below it. |
| `scripts/s1.py` | Perspective deskew and binarisation, writes `scripts/bin.png`. |
| `scripts/s2.py` | Geometry fitting, writes `scripts/geom.json`. |
| `scripts/gen.py` | Writes both SVGs from `geom.json`. |
| `scripts/run.sh` | The command order I used. It expects to run from a folder that contains the scripts, and its compare step uses a relative path to the fixture, so that path may need adjusting. |

Colors used, exactly as specified: roof #e2725b, walls #f7f1e5, door and window panes #14263b, sun #f2a541, canopy #5a8f5a, trunk #7a5236, sky #d9ecf2, ground #a8d5c8.

## Method

1. **Paper, desk and tilt** (`s1.py`): I found the paper as the largest bright contour and took its four corners: (0,34), (1973,0), (1999,1465), (26,1499). The tilt was about 1 degree. A perspective warp maps those corners to a 2000x1485 rectangle, which keeps the paper's aspect ratio. Shadows were removed by dividing by a blurred morphological-closing background estimate, then thresholding at 150. Specks under 40 px were dropped, and a 15 px border was cleared to remove the leftover desk edge.
2. **Straight lines** (`s2.py`): I placed a rough guide segment by eye for each line that was clearly meant to be straight. The ink near each guide was then fitted with a robust (Huber) line, first within a 14 px band and then within 6 px. The ends come from the contiguous run of ink along the fitted line, so the drawn lengths are kept, including the crossed overshoot at the roof apex and the wall bottoms that pass below the ground line. Note that the positions and endpoints come from the ink, but the list of which lines exist was entered by hand.
3. **Gap closing**: one pass of a rule. An unattached endpoint is extended (never trimmed) up to 22 px along its own direction to meet a non-parallel line. Four ends were extended:
   - the wall top's left end, by 9 px to the left wall;
   - the left wall's top, by 16.5 px up to the wall top;
   - the door top's left end, by 5.5 px;
   - the left door jamb's top, by 10 px.

   The tree trunks were clipped where they enter the canopy.
4. **Circle**: a least-squares (algebraic) circle fitted to the ink in an annulus around the sun: centre (1550.0, 307.0), r = 121.5. It is drawn as a true `<circle>`, which also closes the drawn gap at the sun's upper right.
5. **Tree canopy (organic, kept hand-drawn)**: a polar profile around (1435,790). It takes the median ink radius per 0.5-degree bin, smoothed over 4.5 degrees, and is output as a closed polygon. It keeps the scalloped outline.
6. **Ground (organic, kept wavy)**: the centre of the thin ink run in each column. Thick runs where a wall or trunk crosses are ignored, and the result is smoothed over 15 samples. It is drawn from x=146 to x=1866, as in the sketch.
7. **Color**: these are vector polygons built from the fitted geometry, not flood fills:
   - roof: the triangle between the two roof lines and the wall-top line (extended);
   - walls: from the wall top down to the ground curve;
   - windows: each frame's quadrilateral (panes navy, muntins drawn on top);
   - door: down to the ground;
   - trunk: between the trunk lines;
   - sky and ground: split by the ground curve.

   I traced the strokes directly instead of using potrace or autotrace: those output outline (filled-area) paths, and the brief wanted editable strokes.

## Deviations and judgement calls

- **The canopy's left gap is not small.** It is about 65 px, between the stroke end near (1278,782) and the restart near (1315,848). I closed it anyway so the canopy could be filled green. The closure is the interpolated polar profile, a smooth bulge, and the small outward "tail" of the stroke end is not kept exactly. This is the biggest change from the drawing.
- **Canopy outline is resampled.** It follows the drawn scallops, but it is a smoothed polar approximation, so small wiggles and pen texture are gone.
- **The ground line is shorter than the fills.** It stops where the sketch's line stops, about 146 px from the left edge and 134 px from the right. The sky/sea-foam boundary is continued flat to the image edges so the background is filled across the whole width.
- **Roof fill covers a little undrawn area.** The coral triangle is closed by the wall-top line extended to the roof lines, so it runs about 15–20 px past each wall corner, where no line was drawn under the eaves.
- **Slants kept.** The windows and door are not forced to exact rectangles or to vertical/horizontal; each side keeps its drawn slant (for example, the walls lean about 1 degree). I read "straighten" as removing wobble, not as squaring the drawing.
- **Overshoots kept.** The crossed apex, the window muntins poking past their frames and the walls below the ground line are all kept as drawn.
- **Image height.** The output is 2000x1485, not the photo's 1500, because the paper itself is roughly 1973x1465 in the photo.
- **Stroke weight.** All strokes use one uniform 5.5 px width, measured as the median ink width with a distance transform. Pen pressure variation is not reproduced.

## Unsure about

- **Gap-closing threshold.** The 22 px limit is my own choice. Gaps longer than that would not be closed automatically, apart from the canopy, which was handled separately.
- **Hand-placed guides.** These guides decide which strokes count as "meant to be straight". On a different photo the guides in `s2.py` would need to be placed again; this is not a general automatic method.

## Timing

Start: Mon Oct 5 22:20:09 UTC 2026. End: Mon Oct 5 22:24:29 UTC 2026 (about 4.5 minutes). Tool calls: 16.
