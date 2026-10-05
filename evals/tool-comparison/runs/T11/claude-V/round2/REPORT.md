# T11 round 2: red roof and chimney (lane V, Vixl MCP)

**Timing:** start 22:30:43 UTC, end about 22:36 UTC (about 6 min). **Tool calls: 44 in total** (Vixl MCP, Bash, ToolSearch together, plus the final hand-back call). This includes 5 Vixl calls that returned a validation error, 1 call to a tool name that wasn't loaded, and 2 `document_close` calls that reported the documents were already closed.

All visual edits were made with Vixl MCP tools. Bash/Python was only used to copy the sources, read stroke widths from the `.vixl` JSON, and check the outputs (sizes, sampled colours, SVG element counts). Nothing outside `round2/` was changed. The round-1 files in the parent folder are untouched.

## What changed

1. **Roof is now red `#c0392b`.** I removed the old coral roof fill (`house/fill-4`, `#e2725b`) and refilled the same closed roof region with `drawing fill` in `#c0392b`. The new layer is `house/fill-roof`. The region is the same because the chimney sits above the roof line and doesn't split it. Sampled in `sketch-color.png`: roof = `#c0392b`.
2. **Chimney added on the right side of the roof** (`house/chimney`). It is one open polyline made with `drawing stroke`: it starts on the right roof line, goes up, across the top and back down to the roof line (group coordinates (880,509.5) to (880,430) to (940,430) to (940,569.5); canvas = group + (130,60)). The bottom edge is the existing roof line, as it would be in a pen drawing. Then I ran `drawing straighten` on it so it is made of straight segments like the house walls and roof. `drawing stroke` had smoothed it into curves at first.
   - **Line weight:** 3 px black (`#000000`), round caps. This matches the two roof sides it joins (`s006`/`s007`, both 3 px). Note that round 1's strokes are a mix of 3 px and 5 px: the walls, windows and door are 5 px. I matched the roof because the chimney meets it directly.
   - **Fill:** `house/fill-chimney` in the same red `#c0392b` (brick chimney). The brief gives no colour for a chimney, so this is my choice.
3. Re-exported every deliverable that the change affects, in the same way as round 1:
   - `sketch-color.png`: 2000×1450, full document.
   - `sketch-clean.png`: 2000×1450, with all fill and `bg-*` layers hidden, black strokes on white. Visibility was restored afterwards, so `sketch.vixl` is saved in its coloured state.
   - `sketch-lines.svg`: `svg_policy: strict`. 35 `<path>` elements (34 from before plus the chimney) and 0 `<image>`.
   - `compare.png`: 4040×1500. In `compare.vixl` I replaced the `colored` layer with the new `sketch-color.png`, at the same position (2040,25).
4. `vixl_check` (drawing, bounds) passed with no issues.

## Files in round2/

| File | Notes |
| --- | --- |
| `sketch.vixl` | Copy of the round-1 source with the edits above (`house/fill-4` removed; `house/fill-roof`, `house/fill-chimney` and `house/chimney` added). |
| `sketch-color.png`, `sketch-clean.png`, `sketch-lines.svg` | Re-exported from it. |
| `compare.vixl`, `compare.png` | Copy of the round-1 compare source with the coloured image swapped in. |

Round-1 working and extra files (`photo-crop.vixl`, `work-photo-crop.png`, `drawing-overlay.png`) did not change and were not copied. The overlay compares against the original photo, which has no chimney.

## Unsure about

- **Line weight.** I chose 3 px to match the roof. If "the rest" means the heavier 5 px house-body lines, the chimney is lighter than those.
- **Chimney colour.** It is the same red as the roof, so the two read as one red mass with a black line between them.
- **It adds an object.** The original brief said not to add objects. Round 2 asks for one explicitly, so the chimney does not appear in the original photo on the left of `compare.png`.
