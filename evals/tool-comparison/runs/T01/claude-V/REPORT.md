# T01 · A picture — lane V (Vixl)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `picture.png` | 2400 × 1600 px, 8-bit RGB PNG (no alpha) | Exported from `lighthouse.vixl` with the Vixl MCP tool `vixl_export_file` (`alpha=flatten`). |
| `lighthouse.vixl` | Editable Vixl source document, 2400 × 1600, 55 named layers | Built through Vixl MCP calls: `vixl_document_create`, three `vixl_operations_apply` batches (plus one rejected batch, see below), checked with `vixl_check` and `vixl_render_preview`. |
| `REPORT.md` | This file | Written by hand. |

All the artwork is Vixl layers: `gradient` layers (sky, sea, lamp halo) and `shape` layers (stars, ellipses, capsules, rectangles, and `path` shapes with straight-line `M/L/Z` geometry for the rocks, tower, roofs, beam and boats). I wrote no SVG, HTML or pixels myself. The only script I ran was a small Pillow check that read the exported PNG's size, mode and a few sky pixel values.

## How it matches the brief

- **Sky:** one vertical gradient layer (`sky`, y 0–1010) with five stops that go from deep navy `#0b1636` at the top, through indigo and mauve, to warm amber `#f6b04e` at the horizon (y ≈ 1000). Sampled from the PNG at x=1200: y=5 → (11,22,55), y=300 → (31,42,92), y=600 → (97,66,113), y=900 → (221,138,86), y=995 → (243,171,79).
- **Lighthouse on the left:** the tower is centred at x=560 (base 470–650, lamp room 518–602) on a layered rocky headland (`rock-back`, `rock-lit`, `rock-front`, `rock-front-lit`). It is a white tower with red bands, a lit lamp room, a red roof and a small keeper's house. All rock geometry lies within x ≤ 1180, the left half of the 2400 px canvas.
- **Beam to the right:** two translucent wedge shapes (`beam-outer` at 20 % opacity, `beam-inner` at 30 %) start at the lamp (x=585) and widen to the right edge of the canvas (x=2400), passing over the sea.
- **Exactly two sailboats:** `boat1-*` (centred ~x 1550, waterline y 1110, smaller and further away) and `boat2-*` (centred ~x 2000, waterline y 1270). Each has a hull, a mainsail, a jib and a faint wake line. There are no other boat-like shapes.
- **Stars:** 8 five-point star shapes (`star-1`…`star-8`) and 5 small dot stars (`dot-star-1`…`5`), all between y 30 and y 340, so they sit in the upper sky and above the beam.
- **Style:** flat, layered shapes with solid fills and no strokes or outlines. I applied no grain, paper or other texture look. The lamp halo is a soft radial gradient. The other soft-looking parts are only translucent flat fills: the beam, the amber water glints and the foam.
- **No text:** the document has no text layers (`vixl_check` reports `text_layers: 0`).

## Choices and deviations

- I added things the brief did not ask for, to fit the travel-poster look: a far headland silhouette on the right horizon, amber glints on the water, two foam marks at the foot of the rocks, a keeper's house beside the tower, and a soft halo around the lamp.
- I did not draw a sun. At dusk it has just set, and the amber horizon of the gradient stands in for it.
- I chose the canvas size and all the coordinates myself. No layout template was used, because the brief has no text.

## Process notes and things I'm unsure about

- One `vixl_operations_apply` batch was rejected and changed nothing. I had written the `edit-layers` sub-operation under the key `operation` instead of `do`. I fixed the key and sent the batch again.
- When I edited the `path` of the existing `rock-front` and `rock-front-lit` layers in place (by `target`), Vixl warned "path is only drawn for shape 'path', not None". The re-render shows that the new paths were applied, so the warning looks spurious.
- `vixl_check` passed with no issues, but it reported `layers: 36`, while the document has 55 layers (3 from the first batch and 52 from the second). I don't know why the counts differ.
- At full size the beam reads as a pale, warm, translucent light. On the navy sky it can look slightly greyish rather than golden. That is a matter of taste, not a missing requirement.
