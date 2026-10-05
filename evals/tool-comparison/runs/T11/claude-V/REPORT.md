# T11 · Hand drawing to clean art — lane V (Vixl MCP)

**Timing:** start 22:20:09 UTC, end 22:29:54 UTC (about 10 min). About 52 tool calls in total (Vixl MCP, Bash, Read, ToolSearch together).

All visual work went through Vixl MCP tools. Bash/Python was only used to read the inputs and check the outputs (sizes, sampled colours, `<image>` count in the SVG).

## Files

| File | What it is / how it was made |
| --- | --- |
| `sketch.vixl` | **Editable source.** Group `house` made by `drawing import`: hidden `house/original` (the deskewed photo), hidden `house/ink` (cleaned raster lines), 34 editable stroke paths `house/s001…s033` + `house/canopy-close`, 16 vector fill paths `house/fill-1…16`. Below the group are 3 rectangles `bg-sky`, `bg-ground-left` and `bg-ground-right`. |
| `sketch-clean.png` | 2000×1450. The fill and background layers hidden, strokes exported in black on a white background. |
| `sketch-lines.svg` | Exported with `svg_policy: strict`: 34 `<path>` strokes and 0 `<image>` elements, plus a white background `<rect>`. |
| `sketch-color.png` | 2000×1450, the full coloured document. I sampled every region and each one exactly matches its brief hex (#d9ecf2, #a8d5c8, #f2a541, #e2725b, #5a8f5a, #f7f1e5, #14263b, #7a5236). |
| `compare.png` | 4040×1500. The original photo on the left and `sketch-color.png` on the right, put together in `compare.vixl`. |
| `compare.vixl` | Source for compare.png. |
| `drawing-overlay.png` | Extra: Vixl's `drawing-compare` output (original lines in red, result in blue). |
| `photo-crop.vixl`, `work-photo-crop.png` | Working files: the photo cropped inside the paper edge (see below). |

## Steps

1. My first `drawing import` of the full photo did **not** remove the desk or fix the tilt. The dark desk strips at the edges were traced as ink, so tilt detection returned 0° and the crop covered the whole frame. To fix this I cropped the photo inside the paper edge in Vixl (`photo-crop.vixl`: offset −45,−60, canvas 1910×1380) and exported `work-photo-crop.png`. Re-importing that removed the paper and its shading, corrected a −2.2° tilt and cropped to the drawing.
2. Canvas set to 2000×1450, with the drawing at 1:1 scale placed at (130,60). These margins roughly match where the drawing sat on the paper (a large empty area below the ground line), so the composition is kept. I avoided the import's tight 24 px crop, because that would have left almost no ground.
3. `vectorize` (centreline) traced the strokes. `straighten` with `close_gaps: 30` ran **only** on: house walls, roof sides, window frames and bars, door, trunk lines, the 8 sun rays and the sun circle (now a true circle). Left as drawn: the wavy ground line, the bumpy canopy outline and the small tick at the roof peak.
4. Fills (`drawing fill`, under the lines): roof, walls, 8 window panes, door, sun, canopy, trunk, sky and ground.
5. Report: `preserved` 0.9995, `added` 0.0127. `check drawing` and `check bounds` passed with no issues.

## Choices and things done differently

- **Canopy gap closed with one added stroke** (`house/canopy-close`, about 80 px, in the drawing's own line width). The canopy outline is open on the left in the sketch. This is larger than "small", but it had to be closed to fill the canopy green. It is the only line I added.
- **Sky and ground beyond the ground line.** The drawn ground line stops short of the paper edges, so sky and ground are one open region. To fill them, I added temporary helper strokes: horizontal extensions of the ground line out to the edges, and a frame around the drawing. I filled the two regions, then **deleted the helpers**, so they appear in no output. In the margins outside the drawing group, the colours come from the `bg-*` rectangles, with the boundary continuing horizontally from the ends of the ground line. A seam of up to about 1–2 px may show where these rectangles meet the group's fills at the left and right edges of the group.
- Line colour changed from Vixl's default ink (#1d1d1f) to pure black (#000000) with `restyle`, to match "black lines". The coloured version uses the same black lines.
- The output is 2000×1450, not 2000×1500. The brief fixes only the width, and the height follows from the paper area I kept.
- Lines are uniform-width vector strokes (centreline trace), so the pen's pressure variation is mostly flattened. The ground and canopy keep their hand-drawn wobble.

## Unsure about

- Whether the canopy gap counts as "small". Closing it is an interpretation.
- In the right window the horizontal bar stops a few px short of the frame, as drawn. The panes are filled navy anyway.
- `sketch-clean.png` is rendered from the vector strokes, not the cleaned raster ink, so the line texture is smoother than the photo's.
