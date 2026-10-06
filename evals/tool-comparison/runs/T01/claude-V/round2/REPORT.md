# T01 · round 2 — lane V (Vixl)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `picture.png` | 2400 × 1600 px, 8-bit RGB PNG | Exported from `round2/lighthouse.vixl` with `vixl_export_file` (`alpha=flatten`). |
| `lighthouse.vixl` | Editable source, 2400 × 1600, 59 layers (55 from round 1 + 4 new) | A byte copy of the round-1 `lighthouse.vixl`, then edited in place through Vixl MCP calls: `vixl_operations_apply` (one 38-operation batch, one blend/opacity batch, one layer-intent batch), checked with `vixl_check` and `vixl_render_preview`. |
| `REPORT.md` | This file | Written by hand. |

I did not draw pixels or write SVG/HTML. The only shell work was `cp` of the round-1 `.vixl` into `round2/` and a Pillow script that read pixel values from the old and new PNGs to compare them. Nothing outside `round2/` was changed.

## What changed

1. **Night sky, still a gradient.** I changed the stops of the existing `sky` gradient layer in place. It is still a vertical 5-stop gradient, now running from near-black navy `#03061a` at the top through `#081030`, `#121a44` and `#1f2456` to a dim indigo `#2c2c62` at the horizon. The amber/mauve dusk stops are gone. Sampled at x=1200 (old → new): y=5 (11,22,55) → (3,6,26); y=300 (31,42,92) → (7,14,45); y=600 (97,66,113) → (16,24,64); y=900 (221,138,86) → (32,37,87); y=995 (243,171,79) → (42,43,97).
2. **Brighter beam.** On `beam-outer` the fill went `#ffd98a` → `#ffe6a6`, opacity 0.20 → 0.45 and blend normal → screen. On `beam-inner` the fill went `#ffe9b0` → `#fff5d6`, opacity 0.30 → 0.70 and blend normal → screen. A pixel in the beam core reads (143,128,128) in round 1 and (214,209,196) now.
3. **Lighthouse and rocks moved to the right half, beam sweeping left.** I mirrored the whole lighthouse group across the canvas centre line (x → 2400 − x):
   - The full-canvas path layers were flipped horizontally with one `edit-layers` + `flip` operation (`expect: 13`): `rock-back`, `rock-lit`, `rock-front`, `rock-front-lit`, `tower`, `band-1`, `band-2`, `tower-shade`, `roof`, `house-roof`, `beam-outer`, `beam-inner`, `far-headland`. They keep their path data and get `flip_x: true`.
   - The box layers were moved with `move` to `x = 2400 − x − width`: `house`, `house-window`, `door`, `window`, `lamp-halo`, `lamp-room`, `mullion-1/2`, `gallery`, `finial`, and the foam marks at the foot of the rocks (`foam-1`, `foam-2`).
   - The tower is now centred at x=1840 and the lamp at x≈1815. All rock geometry is at x ≥ 1220. The beam wedge runs from the lamp to the left edge (x=0).
4. **Third sailboat.** I added `boat3-hull`, `boat3-main`, `boat3-jib` and `boat3-wake`. It is boat 2's geometry scaled ×1.25 and uses the same fills and the same wake opacity (0.45). It sits closest to the viewer: centred at x≈1000, waterline y=1440.

## Things I moved that the brief did not name, and why

The brief says to keep everything else exactly as it was. Moving the headland to the right would have buried several existing elements under the rocks, so I moved those elements to the matching spot on the left. I changed their positions only, not their shape, colour, size or opacity:

- **Boats 1 and 2** were at x≈1550 and x≈2000, where the rocks are now. I moved them sideways to the positions mirrored across the centre line (boat 1 centre x≈850, boat 2 x≈400), using `move` with `relative: true` (−700 and −1600 px). They keep their waterlines, their shapes and the way they face. I did not flip them.
- **Water glints 1–7** were mirrored to `x = 2400 − x − width` so they stay on open water rather than under the rock.
- **Far headland** on the right horizon would have been fully hidden behind `rock-back`, so I flipped it to the left horizon.

These elements are unchanged: the stars (all 13, same positions), the `sea` gradient, every fill colour other than the sky and beam, and all layer names and order. The glints and the boat-2-style wakes are still amber `#f6b04e`. I left them alone because they were not part of the request, even though the amber dusk horizon they reflected is gone.

## Checks and caveats

- `vixl_check` reports 0 errors and 0 warnings. Moving the full-canvas boat path layers shifted their layer boxes partly off canvas (for example `[-700, 0, 2400, 1600]`), although the drawn boats are fully inside the canvas. The check flagged this, so I marked those six layers `allow_crop` with `layer-intent`, and they now show as informational only.
- One batch was rejected and changed nothing: `opacity` is not a field of the `shape` operation. I resent it with a separate `opacity` operation.
- The beam sits in the sky band (y 150–600 at the left edge), as it did in round 1. It points left over the sea instead of right. Even with screen blending, the outer wedge reads as a warm pale grey rather than golden on the dark sky.
- `vixl_check` reports `layers: 43` while the document has 59 layers. The same mismatch appeared in round 1.
