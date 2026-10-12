# T01 · A picture: report (lane V, Vixl)

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `picture.png` | 2400 × 1600 px, RGB (no alpha), 161 KB | `vixl_export_file` from `picture.vixl` with `alpha="flatten"`. Checked with PIL: size (2400, 1600), mode RGB. |
| `picture.vixl` | Editable Vixl source: 54 layers, all vector shapes and gradients, no raster images | Built with the Vixl MCP tools (`vixl_document_create`, then `vixl_operations_apply` batches) |
| `REPORT.md` | This report | |

## How it was built

- **Sky** (`sky`): a vertical gradient from 0 to 1060 px. It runs from navy `#0b1638` at the top through `#36386a` and `#a15f63` to amber `#e48c4a` / `#f6b14a` at the horizon. A soft radial `horizon-glow` (amber, Gaussian falloff) warms the horizon on the right. Sampled in the PNG: (1200,5) = rgb(11,22,57) and (1200,1045) = rgb(244,174,76).
- **Stars**: ten small 5-point star shapes, `star-1` to `star-10`, 14 to 30 px, in the top ~320 px of the sky.
- **Sea** (`sea`): a vertical gradient from y=1050 down. It has a thin amber reflection at the horizon and darkens toward the bottom. Four faint amber shimmer strokes sit on the water, and a low purple `far-headland` silhouette lies on the right horizon.
- **Rocky point**: on the left, out to about x=1080. It is flat faceted path shapes: `rock-main`, lighter facets `rock-light-1` to `rock-light-4`, a dark foreground `rock-front` and a small `rock-islet`.
- **Lighthouse** (group `lighthouse`, declared as object kind `tower`): x 345 to 515, in the left half. It has a tapered cream tower with three red bands, a flat shade on its right half, a door, a window, a gallery, a glowing lantern with mullions, a roof and a finial. A radial `lantern-glow` sits behind it.
- **Beam**: two translucent cream wedges, `beam-outer` (opacity 0.16) and `beam-inner` (opacity 0.2). They run from the lantern (about x 440, y 400) to the right edge, angled down toward the sea.
- **Sailboats**: exactly two groups. `sailboat-1` spans x 1480 to 1610. `sailboat-2` spans x 1960 to 2136 and is larger, so it reads as nearer. Each has a hull, a mast, a mainsail, a jib and a faint wake.
- **Style**: flat fills only. There are no outlines or strokes, no texture, grain or photos, and no text layers.

## Checks

A check suite named `brief` is attached to the document with these rules:
- no text layers;
- exactly 2 layers named `sailboat-*`;
- at least 5 layers named `star-*`;
- the top of the sky is navy;
- the lighthouse is drawn to the left of `sailboat-1`;
- `sailboat-2` is drawn to the right of the lighthouse;
- the beam reaches the right edge.

All 7 rules pass. `vixl_check` has no fix or review findings. The safe-area notices on full-bleed layers are marked as intentional crops (`layer-intent allow_crop`), so they are informational only. I also checked the preview by eye.

## Deviations and choices

- **Beam position**: the beam crosses the sky above the sea, angled down toward the water, and ends just above the horizon at the right edge. It does not lie on the water itself. I read "sweeps out to the right, across the sea" as the direction it points.
- **Beam shape**: it is two flat translucent wedges rather than a smooth fade, to keep the flat poster look.
- **Sky colours**: the gradient passes through a muted mauve between navy and amber. I chose that so the blend stays smooth instead of going grey-green.
- **Star count**: there are 10 stars, more than the minimum of five.

## Process notes and things I'm unsure about

- **Group bounds**: I first drew the path layers with absolute coordinates at x=0, y=0. That gave them boxes starting at the canvas origin, and the groups kept a stale [0,0,…] box. I re-based each path into a tight box, then ungrouped and regrouped the lighthouse and the boats so the position rules could measure them. The rendering did not change. The temporary ops file I used for this was deleted.
- **Beam visibility**: at low opacity the beam may look subtle on some screens. That was a judgement call.
- **No text**: Vixl adds no text or watermark and there are no text layers, but I did not inspect every pixel for text.
