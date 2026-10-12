# T11 round 2 · Red roof and a chimney (lane V, Vixl MCP)

I did all the visual work with Vixl MCP tools: `vixl_document_open`, `vixl_document_inspect`, the `drawing-report` action of `vixl_workflow`, `vixl_operations_apply` with `drawing` operations, `vixl_check`, `vixl_render_preview`, `vixl_import_image` and `vixl_export_file`. I used Python/PIL and grep only to read the exported files back.

## What changed

1. **The roof is red `#c0392b`.** I edited the existing roof fill layer in place (`house/fill-2`, `#e2725b` → `#c0392b`), so the region and its layer ID stay the same.
2. **There is a chimney on the right slope of the roof.** It is a new stroke layer, `chimney`, made with `drawing stroke`. It is an open polyline of three straight segments, a left side, a flat top and a right side, and both ends land exactly on the right roof line (`house/s006`).
   - I worked out the points in the drawing group's own coordinates (`space: group`) from the roof line's two endpoints, (878.15, 464.85) and (1159.52, 749.47).
   - Group-space points: (1020, 608.3) → (1020, 545) → (1080, 545) → (1080, 669). On the canvas that is about 58 px wide, sitting about 60 px above the roof line on its left side and about 120 px above it on its right side.
   - **Line weight and character:** the stroke is pure black `#000000`, 3.7 px wide (the same as the roof lines it meets) with round caps. It is straight-edged with no smoothing, which matches how the straightened walls, roof and windows look.
3. **The chimney is filled.** `drawing fill` added `house/fill-17` under the lines in `#c0392b`. That is the chimney region bounded by the new stroke and the roof line. I used the roof's red because the brief gives no colour for the chimney, and that adds no new colour to the palette.

Nothing else in the drawing changed. Every other stroke and fill is as in round 1.

## Files (all in `round2/`, same names as round 1)

| File | How it was made |
| --- | --- |
| `drawing.vixl` | A copy of the round-1 source with the edits above. It now has 37 strokes and 17 fills. |
| `sketch-clean.png` | 2000 × 1532 RGB, exported with all 17 fill layers hidden. It shows black lines on white, chimney included. |
| `sketch-lines.svg` | Exported with the fills hidden and `svg_policy: strict`. It has 37 `<path>` strokes, all `rgb(0,0,0)`, one white background `<rect>` and no `<image>` elements. |
| `sketch-color.png` | 2000 × 1532 RGB with the fills shown. Sampled colours: roof `#c0392b`, chimney `#c0392b`, walls `#f7f1e5`, sky `#d9ecf2` and door `#14263b`. The other colours are unchanged from round 1. |
| `compare.vixl` / `compare.png` | A copy of the round-1 compare document. I swapped the `result` layer's image for the new `sketch-color.png` with `replace-contents`. The output is 4060 × 1572, about 3.0 MB, with the original sketch on the left and the new colour version on the right. |

## Checks

- `vixl_check` with the `drawing` and `bounds` checks passes with no `fix` findings.
- The only `review` findings are the deliberate edge runs from round 1: the ground fill and the two ground-line extensions, which run to the canvas edges.
- A zoomed preview shows that the chimney's sides meet the roof line cleanly, with no gaps or overshoot.

## Judgement calls

- **Chimney colour:** I filled it with the roof red rather than inventing a brick colour. If a different colour is wanted, it is a one-field change on `house/fill-17`.
- **Line weight:** I matched the roof strokes it attaches to (3.7 px). The walls in the original drawing are slightly heavier (up to 6.6 px). The chimney deliberately follows the roof lines, the strokes nearest to it.
- **The chimney is an added element, not traced from the sketch.** `drawing-report` will count it under `added`.
