# T03 round 2 — lane V (Vixl MCP)

## Files (all in round2/)

| File | What it is | How it was made |
| --- | --- | --- |
| `poster.vixl` | Editable source | Copied from `../poster.vixl`, then edited with Vixl MCP (`vixl_operations_apply`, `document=` always given) |
| `poster-print.pdf` | 1 page, MediaBox 810 × 1242 pt (11.25 × 17.25 in), one DeviceCMYK JPEG image 3375 × 5175 px at 300 ppi | `vixl_export_file(color_space="cmyk", ink_limit=300, dpi=300, quality=95)` — same settings as round 1 |
| `poster-preview.png` | 1650 × 2550 px, 150 dpi metadata, trimmed area only | `vixl_export_file(artboard="trim", scale=0.5, dpi=150)` — same as round 1 |

Nothing outside round2/ was changed.

## Changes
1. **Kicker** changed from "Port Ellery Quay" to "Old Customs House Square" with a `rich-text` operation. It keeps the same span tracking (30), font (Marcellus), size (120 px), gold colour and centred position. The layer is auto-sized, so it widened to 2187 px, which leaves an inset of about 594 px from the canvas edge.
2. **Highlight** "Live brass band" replaced with "Fire dancers at 8 pm". This also used a `rich-text` operation, which keeps the four-item bulleted list with the same line height, paragraph spacing and list indent.
3. **QR placeholder:** a new `qr-box` rectangle, 300 × 300 px (1 × 1 in at 300 dpi), white `#ffffff`, at x=2962, y=4762 on the bleed canvas.
   - Its right edge is at 3262 and its bottom edge at 5062. That is 113 px from the right and bottom canvas edges: 37.5 px of bleed plus 75 px (0.25 in), with 0.5 px to spare. So it sits in the bottom-right corner of the text safe area.
   - It has a text layer `qr-label` reading "QR": Lato, 140 px, navy `#0b1a2e`, made by duplicating the date layer and restyling it. It is centred on the box with `center-x`/`center-y` constraints, so it stays centred if the box moves. Its layout box centre is (3112, 4911.5) and the box centre is (3112, 4912).
   - It does not overlap the footer or credit line.
4. **Print spec:** unchanged from round 1 (11 × 17 in trim, 0.125 in bleed, 300 dpi, CMYK).

## Checks
- `vixl_check` (bounds, overlap, contrast, safe_area 113 px, print) passed with 0 errors. The only warnings are for the bleed artwork (sky, water, quay edges and the two end back-lanterns), which is meant to run outside the safe area, as in round 1.
- I looked at a full preview and a zoomed preview of the QR corner.
- I checked the outputs with a Python read: PNG size and dpi, PDF MediaBox, colour space and image size.

## Notes and problems
- My first try used `text-set` for the kicker and highlights. That **removed the rich-text data**: it dropped the bulleted list and the kicker's tracking. I undid that batch with `vixl_history(undo)` and redid it with `rich-text` operations. The final file has no trace of it apart from the history.
- The caveats from round 1 still apply:
  - The text is raster in the CMYK PDF.
  - There is no TrimBox or BleedBox.
  - The CMYK conversion is device-naive GCR with no ICC profile.
  - The PNG is RGBA (fully opaque), not 3-channel RGB.
  - The bleed is 38 px on the left and top and 37 px on the right and bottom.
- "QR" is a placeholder label, not a scannable code, as the request asked.

## Tool calls
25 tool calls in total, counting the final close and hand-off calls:

- 6 Bash calls (reading inputs, copying the source, one no-op, checking outputs, writing this report)
- 2 ToolSearch calls
- 16 Vixl MCP calls: open, 3 inspect, 3 operation_schema, 2 operations_apply, 1 history undo, 2 render_preview, 1 check, 2 export_file and 1 close
- 1 SubagentHandback
