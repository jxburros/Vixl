# T15 · Seamless pattern — lane V (Vixl MCP)

**Timing:** start 2026-10-05 22:20:51 UTC, end 2026-10-05 22:33:47 UTC (~13 min). Tool calls: about 55 total (Vixl MCP, Bash, ToolSearch, Read/Skill).

## Files

| File | Spec check | How it was made |
| --- | --- | --- |
| `tile.vixl` | editable source, 1024×1024 | `vixl_document_create` (cream `#f7f1e5` background), then `vixl_operations_apply` batches. All motifs are live vector layers. |
| `tile.png` | 1024×1024 RGBA (fully opaque) | `vixl_export_file` from `tile.vixl`. |
| `tile.svg` | 1024×1024 viewBox, all vector (0 `<image>` elements) | `vixl_export_file` from `tile.vixl`. Motifs that hang off the edges sit outside the viewBox, so the SVG viewport clips them. |
| `preview-3x3.vixl` / `preview-3x3.png` | 3072×3072 | New document; `tile.png` imported once, `repeat` (count 3, dx 1024) for a row, duplicated to y=1024 and y=2048. Exported PNG. |
| `mug-wrap.vixl` / `mug-wrap.png` | 2550×1050, 300 dpi in the PNG metadata | `tile.png` imported and repeated 3 across, 2 rows down (cropped by the canvas, pattern anchored at the top-left). Centered 600×300 cream (`#f7f1e5`) rounded rectangle (corner radius 44 px) at (975,375). "Tidewick" in navy `#14263b`, Young Serif 100 px (pairing `young-serif-rubik` installed with `vixl_font_pair`), constrained to the label's center (text box 459×82 at 1046,484). |

## Motifs (in tile.vixl)
- **Kelp fronds** (K1–K4): custom `organic` forms with a wavy `tentacle` stipe and linear `leaf` blades placed `along` it with a wave warp. Three are navy, one sea-foam. Heights 250–320 px, rotations −22° to +32° (K1 is also mirrored).
- **Spiral shells** (S1–S7): `organic` preset `shell` in coral and amber, 55–110 px wide, rotated −40° to 200°.
- **Curling waves** (W1, W4, W5) and **ripple waves** (W2, W3): `shape` paths, stroke only, in sea-foam, navy and amber, 150–230 px, rotated slightly.
- **Dots** (D01–D23): ellipses 8–20 px in all four motif colors.
- Placement: a hand-placed, jittered layout (about one large motif per quarter-cell, with dots filling the gaps), so nothing lines up on a visible grid. Sizes and rotations vary. I moved K1 once after the first 3×3 preview because it formed a "twin" with K3.

## Seamlessness
Each motif that crosses an edge was `duplicate`d and moved by exactly ±1024 px: K3 (x), K4 (y), S4 (x, y and the corner, so 3 copies), W2 (x), W4 (x), D16 (x), D17 (y), D18 (y). Checks I ran with a script:
- `preview-3x3.png` equals `tile.png` tiled 3×3, pixel for pixel (max difference 0).
- The tile's wrap seams look like its interior: 26 strongly differing pixel pairs across the x seam (col 1023 vs col 0) against 5–19 for interior column pairs, and 10 across the y seam against 11–33 for interior rows. The leftover differences come from shapes' own outlines meeting the seam, not from breaks.
- I also checked a full-resolution zoom of the 3×3 at x=2048 / y=2048: kelp and shell continue cleanly.
- Note: the downscaled `vixl_render_preview` of the 3×3 at 1024 px showed faint hairlines at the tile boundaries. That was a preview-resampling artifact; the exported PNG has no such lines (it matches the exact tiling).

## Deviations / unsure
- **Shell outline color is off-palette:** the `shell` preset draws a 1.2–1.5 px outline and chamber lines in a brown (`#8a5a3b` / `#9b6b47`) that it derives itself. I tried to regrow the shells with `stroke: #14263b`. Vixl stored the setting but didn't apply it to the child outline layers, so the brown remains. Everything else uses only the five brief colors. Edge antialiasing adds in-between tones.
- **Kelp look:** the fronds are fairly bushy, closer to stylized seaweed than to long single-blade kelp.
- **Label:** I added a thin 4 px navy stroke around the cream label so it reads against the cream pattern background; the brief didn't ask for one.
- **Mug wrap:** the pattern there is the raster `tile.png` repeated (with no scaling, it is 1:1). The wrap is 2550 px wide, not a multiple of 1024, so the pattern doesn't join itself where the wrap's left and right ends meet on a mug.
- **Text font through MCP:** a `font` field in `vixl_operations_apply` is refused over MCP, and one `text-set` call timed out. I placed the text with `vixl_text_add(font="young-serif-400")` instead.
- The `.vixl` files embed `tile.png`, so `preview-3x3.vixl` and `mug-wrap.vixl` won't update by themselves if `tile.vixl` is edited. Their `tile.png` asset hash matches the delivered `tile.png` (sha256 4dbb0fe5…).
