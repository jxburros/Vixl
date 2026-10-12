# T11 · Hand drawing to clean art (lane V, Vixl MCP)

I did all the visual work with Vixl MCP tools: `vixl_document_create`, `vixl_import_image`, `vixl_operations_apply` with `drawing` operations, the `drawing-report` action of `vixl_workflow`, and `vixl_export_file`. I used Python/PIL only to read the exported files back and sample their colours.

## Files

| File | What it is and how it was made |
| --- | --- |
| `drawing.vixl` | The editable source: a 2000 × 1532 white canvas with one drawing group, `house`. It holds the hidden `house/original` (the photo, deskewed and cropped to the paper) and the hidden `house/ink` (the cleaned raster lines). On top are 33 traced strokes `house/s001…s033`, 3 strokes I added (`canopy-gap`, `ground-left`, `ground-right`) and 16 fill layers `house/fill-1…16` under the lines. |
| `sketch-clean.png` | 2000 × 1532 RGB, exported from `drawing.vixl` with the 16 fill layers hidden. Black (`#000000`) vector strokes on white; only greys appear, from anti-aliased edges. |
| `sketch-lines.svg` | 2000 × 1532, exported with the fills hidden and `svg_policy: strict`. It has 36 `<path>` strokes in `rgb(0,0,0)` and one white background `<rect>`. There are no `<image>` elements. |
| `sketch-color.png` | 2000 × 1532 RGB: the same document with the fills shown. Sampled colours match the brief exactly: roof `#e2725b`, walls `#f7f1e5`, door and all 8 window panes `#14263b`, sun `#f2a541`, canopy `#5a8f5a`, trunk `#7a5236`, sky `#d9ecf2` and ground `#a8d5c8`. |
| `compare.png` | 4060 × 1572 RGB, about 3.0 MB. The original `sketch.jpg` (2000 × 1500) is on the left and `sketch-color.png` on the right, on white with 20 px margins. It was built in a second Vixl document, `compare.vixl`. |
| `compare.vixl` | The editable source of `compare.png`. |

## Steps

1. Ran `drawing import` on `fixtures/sketch.jpg` with `color: #000000`. Vixl found the paper (`paper_found: true`), cut away the desk border and the paper's shading, and corrected a −2.2° tilt (`tilt_corrected: -2.2`). It applied no perspective correction (`perspective_corrected: false`), because the page was only rotated.
2. Ran `drawing vectorize`, which gave 33 centre-line strokes. Each keeps its drawn width: 3.7 to 6.6 px, median 5.1.
3. Ran `drawing straighten` with `close_gaps: "auto"` on every stroke except the two ground strokes (s001, s005).
   - Walls, roof, door, windows and sun rays became straight lines at their drawn angles.
   - The sun became a circle, and the tree canopy kept its lobes.
   - Gaps at corners and T-joints were closed.
4. Ran `drawing smooth` (amount 0.6) on the two ground strokes. The ground keeps its gentle wave but loses the pen jitter.
5. Added one short stroke, `canopy-gap`, in the drawing's line width. It closes the opening on the left of the tree canopy (about 60 px), which `close_gaps: auto` (about 41 px) did not reach.
6. Resized the canvas to the cleaned paper's aspect ratio (2000 × 1532) and scaled the drawing group to fill it, so the colour runs to the edges.
7. Added `ground-left` and `ground-right`, two short horizontal extensions of the ground line out to the paper's edges. Without them, the sky and the ground were one region.
8. Ran `drawing-report` to get a point inside each region, then filled under the lines with `drawing fill`. That covered 14 closed regions, plus the sky and the ground with `edge_closes: true`.
9. Exported the files listed above, with the fills hidden for the clean PNG and the SVG and shown for the colour PNG.

Final `drawing-report`: `preserved` 0.9999 (the share of the original lines kept) and `added` 0.058. `check drawing` passes with no findings.

## Deviations and judgement calls

- **The output height is 1532 px, not 1500.** The brief fixes only the width (2000 px), so the height follows the cleaned paper's aspect ratio (2058 × 1576 after removing the desk and correcting the tilt).
- **I added two lines to the ground (`ground-left`, `ground-right`).** The drawn ground line stops about 180 px short of each edge of the paper, so the sky and the ground were one connected region and could not get separate colours. These extensions are the only change to the composition. They are straight and horizontal, at the height of the line's ends.
- **I closed the canopy gap with an added stroke (`canopy-gap`).** I read the opening as a gap meant to be closed. It is bigger than "small", so the bridge is my own curve and its shape is approximate.
- **I did not straighten the ground line.** It looks deliberately wavy, like rolling ground, so I only smoothed it.
- **Some details stay as drawn:**
  - the little cross at the roof's peak, where the two pen strokes overshoot;
  - the roof eaves overhanging the walls;
  - the slightly skewed right window;
  - the right wall running a little below the ground line.

  Lines keep their drawn angles and were not snapped to horizontal or vertical, because the tilt was already corrected.
- **The line colour is pure black `#000000`.** Vixl's default would be `#1d1d1f`.

## Unsure about

- Whether the opening in the tree canopy was intentional. I closed it so the canopy could be filled.
- The kink where `canopy-gap` meets the bottom lobe is visible when zoomed in.
- `compare.png` is large (3.0 MB) because it holds both images at full resolution.
