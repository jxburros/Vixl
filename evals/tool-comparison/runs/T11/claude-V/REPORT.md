# T11 · Hand drawing to clean art (lane V, Vixl)

All visual work was done with Vixl through its MCP tools (`vixl_document_create`, `vixl_import_image`,
`vixl_operations_apply` with `drawing` operations, `vixl_workflow drawing-report`, `vixl_check`,
`vixl_render_preview`, `vixl_export_batch` / `vixl_export_file`). The only scripts I wrote read data. One
read the ground stroke's traced points out of the document (`vixl --json inspect`) so I could build a
Vixl path from them. The others checked the exported files' sizes, pixel colors and SVG contents.

## Files

| File | What it is / how it was made |
| --- | --- |
| `sketch.vixl` | **Editable source.** 2000×1500 document. Group `house`: hidden `house/original` (the photo after tilt correction), hidden `house/ink` (the cleaned raster lines), 34 editable stroke layers (`house/s001`…`s033` plus `house/added-1`), 14 fill layers `house/fill-1`…`fill-14` under the lines. Below the group are two shape layers, `ground-color` and `sky-color`. It has two saved comps: `color` (active) and `lines` (fills and background hidden). |
| `sketch-clean.png` | 2000×1500 RGB. Exported from comp `lines`: black (`#000000`) lines on white. |
| `sketch-lines.svg` | 2000×1500. Exported from comp `lines` with `svg_policy: strict`. It holds 34 `<path>` strokes, one per stroke layer, plus a white background `<rect>`. It has no `<image>` and no base64 data. |
| `sketch-color.png` | 2000×1500 RGB. Exported from comp `color`. I sampled the colors and they match the brief exactly: roof `#e2725b`, walls `#f7f1e5`, door and all 8 panes `#14263b`, sun `#f2a541`, canopy `#5a8f5a`, trunk `#7a5236`, sky `#d9ecf2`, ground `#a8d5c8`. |
| `compare.png` | 4040×1500. The original photo (left, unchanged) and `sketch-color.png` (right) with a 40 px white gutter between them. I built it in Vixl as `compare.vixl`. |
| `compare.vixl` | Vixl source for `compare.png`: two imported image layers. |

## Steps

1. **Import and clean.** `drawing import` of `fixtures/sketch.jpg` with `ink: #000000`. Vixl found the paper (`paper_found: true`) and removed the desk, the page edge and the shading. It also corrected the tilt by −2.2° (`tilt_corrected: -2.2`). It found no keystone to fix (`perspective_corrected: false`). I re-ran `clean` with `crop: false`, because the default crop cut the frame tight around the lines and threw away the paper's empty space below the ground line. That would have changed the composition. Then I set the canvas to 2000×1500 (the photo's size and 4:3 shape) and shifted the drawing by (−29, −38) so the de-rotated page fills the frame.
2. **Vectorize.** `drawing vectorize` made centre-line strokes. Each stroke keeps the width it was drawn with: 3.7 to 6.6 px, median 5.1 px.
3. **Straighten and close gaps.** I ran `drawing straighten` with `angles: "axes"` and `close_gaps: 25` on every stroke except the ground line (`s001`, `s005`) and the tree canopy (`s002`).
   - Walls, wall top, windows, door and trunk became straight and square.
   - The roof sides and the diagonal sun rays became straight lines at the angles they were drawn at. They were outside the 6° snap tolerance, so they stayed diagonal.
   - The sun outline became a closed, true circle, which also closed its gap at the upper right.
   - The rays stay separate from the sun.
   - Small corner gaps in the windows and door were closed.
4. **Tree canopy gap.** The canopy outline had a gap of about 78 px on its left side, too wide for the automatic setting. `close_gaps: 80` closed it, but with a straight bridge that looked out of place on the lobed outline, so I undid that. Instead I added one stroke (`house/added-1`, `drawing stroke`, smoothed, 5.5 px like the canopy) that finishes the outline as one more rounded lobe.
5. **Kept as drawn.** The wavy ground line, the lobed canopy, the small "x" at the roof peak, and the line widths. The right wall still runs a little past the ground line, as drawn. `drawing-report`: `preserved 0.9999` (essentially all of the original line work is kept) and `added 0.0157` (about 1.6% new line, which is the canopy lobe). `vixl_check` with the `drawing` and `bounds` checks passed with no issues.
6. **Color.** `drawing fill` with `gap: 12` placed 14 flat fills under the lines: roof, walls, 8 window panes, door, sun, canopy and trunk.
7. **Sky and ground.** These are separate shape layers, not drawing fills (see Deviations): `sky-color` is a full-canvas rectangle, and `ground-color` is a path that follows the traced ground line's points.

## Deviations and choices

- **Sky and ground are not `drawing fill` regions.** The ground line stops about 150 px short of both page edges, so the areas above and below it are not closed. Vixl's `fill` will not fill an area bounded by the canvas edge ("outside every closed shape"). I didn't want to draw new line extensions to the edges, so I made the two areas Vixl shape layers under the drawing instead. The sea-foam area follows the drawn ground line exactly. From each end of the line it runs straight and level to the page edge, where there is no ink line.
- **Roof eaves.** As drawn, the roof sides overhang the walls, and the wall's top line stops about 19 px short of the roof lines. I left these lines as drawn and did not lengthen them. The roof fill bridges the gap (`gap: 12` plus the fill's own reach into corners), so the roof color has an edge there with no black line.
- **Black lines** are pure `#000000`, not Vixl's default near-black `#1d1d1f`, because the brief says "black".
- **What straightening touched.** Only near-axis lines were snapped to horizontal and vertical. Roof sides and rays keep their drawn angles. The ground line was left wavy on purpose, because it reads as gently rolling ground rather than a line meant to be straight.
- **Framing.** The output frame is 2000×1500, a 4:3 crop of the de-rotated page. To fill the corners left empty by the rotation, the page is trimmed by about 29 px at the sides and 38 px at the top and bottom. The drawing keeps its original position on the page.

## Things I'm unsure about

- The added canopy lobe is my reading of how the outline was meant to close. Its exact curve is a guess.
- In `drawing-report`, the region "points" did not line up with my canvas coordinates after I moved the drawing group. For example, the wall point it gave sits on a line. So I picked every fill point myself from the strokes' traced coordinates and confirmed the fills by sampling `sketch-color.png`.
- The wall/roof corner gaps are covered by color rather than closed with ink. A strict reviewer may count this as gaps not closed.
