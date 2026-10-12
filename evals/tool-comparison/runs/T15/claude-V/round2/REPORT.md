# T15 round 2: all shells amber, about a third fewer motifs (Lane V, Vixl)

All the visual work was done with the Vixl MCP tools (`vixl_document_open`, `vixl_operations_apply`, `vixl_export_file`). I didn't draw any pixels or write SVG or HTML myself. My scripts only copied the three round-1 `.vixl` sources into `round2/` as a starting point and read the exported files to check them. I changed nothing outside `round2/`.

## What changed

1. **All shells are amber now.**
   - The round-1 tile had two shell motifs: coral `#e2725b` (90 px) and amber `#f2a541` (70 px).
   - In `tile.vixl` I changed the fill of the hidden coral shell source (`shape` with `target` set to that shell's layer ID and `fill: "#f2a541"`).
   - I renamed that group `shell-amber-l` (with its children `shell-amber-l/shell` and `shell-amber-l/shell-chambers`) so no layer is still called coral. It stays as the large size variant.
   - The navy outline and chamber lines are unchanged.
   - Coral is still in the pattern, but only on some of the small scattered dots. The shells no longer use it.
2. **About a third fewer motifs.**
   - I re-ran the two existing `pattern-scatter` groups in place (`target: motifs` and `target: dots`). The sources, seeds, scale, jitter and rotation are the same as round 1. Only the target count is lower.
   - **Large motifs** (kelp, shells, waves): the count went from 18 to 12. 16 copies were placed before and 12 are placed now, which is 25 % fewer.
     - I also tried a count of 11. It placed only 10 copies (37.5 % fewer) and dropped both navy waves, leaving one wave in the tile, so I kept 12.
     - The 12 copies are 7 shells, 2 kelp fronds (1 navy, 1 sea-foam) and 3 waves (2 navy, 1 amber).
   - **Dots**: the count went from 48 to 32, so 45 dots became 30. That is exactly a third fewer.
   - **Altogether**, 61 scattered elements became 42, which is 31 % fewer.
   - Because the seeds are unchanged, the dots keep a similar feel to round 1. The layout is not identical, because Poisson-disc spacing widens when the count drops.
3. **Preview and mug wrap.**
   - Their `link` layers point at `tile.vixl` relative to the document, so the copies in `round2/` already read `round2/tile.vixl`.
   - I ran `link-refresh` on all 9 + 6 links and re-exported. The label, wordmark, offsets and 300 dpi are unchanged.

## Files (same names as round 1)

| File | Notes |
| --- | --- |
| `tile.vixl` | Editable source. The motif sources are hidden and editable. Re-run `pattern-scatter` on `motifs` or `dots` to rebuild a group. |
| `tile.png` | 1024 × 1024, RGB |
| `tile.svg` | 1024 × 1024, exported with `svg_policy: strict` (no embedded rasters, 0 `<image>` elements) |
| `preview-3x3.vixl` / `.png` | 3072 × 3072, nine live links to `round2/tile.vixl` |
| `mug-wrap.vixl` / `.png` | 2550 × 1050 at 300 dpi, six links plus the cream label with the navy "Tidewick" wordmark |

## Checks
- **Seam:** Vixl reported `seamless: true` for both scatter groups (motifs: edge 0.83 vs interior 1.16; dots: 0.014 vs 0.074). My own pixel check of `tile.png` gave these mean differences:

  | Comparison | Mean difference |
  | --- | --- |
  | Wrap, left/right | 0.68 |
  | Wrap, top/bottom | 0.91 |
  | Neighbouring columns/rows inside the tile | 1.11 / 1.17 |

  The edges differ no more than the inside does, so the wrap doesn't show.
- **Preview:** `preview-3x3.png` equals `tile.png` tiled 3 × 3 pixel for pixel (largest difference 0).
- **Colours:** in order of pixel count, the main colours are cream `#f7f1e5`, amber `#f2a541`, navy `#14263b`, sea-foam `#a8d5c8` and coral `#e2725b`. Only about 1,200 coral pixels remain, all from the small dots.
- **Mug wrap:** `vixl_check` found no `fix` findings. The two `review` items are the expected overlap of the wordmark with the pattern links underneath the label.

## Notes
- **Layer names:** the regenerated scatter copies got names with a " 2" suffix (for example `motifs/3 2`), because Vixl keeps names unique while it rebuilds a group. This doesn't affect any output.
- **Shell-heavy mix:** shells are now 7 of the 12 large motifs because `pattern-scatter` picks sources at random. If a more even mix is wanted, try another `seed` on the `motifs` group.
