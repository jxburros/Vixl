# T01 · A picture — Lane C (claude-C)

## Files
| File | What it is | How it was made |
| --- | --- | --- |
| `picture.png` | 2400 × 1600 px, RGB (8-bit, no alpha) | Made by `make_picture.py` |
| `make_picture.py` | Editable source (Python, Pillow + NumPy) | Written by hand. Run `python3 make_picture.py` in this folder to rebuild `picture.png` |
| `REPORT.md` | This report | Written by hand |

## Method
- The script draws at 2× size (4800 × 3200) and scales down to 2400 × 1600 with LANCZOS, which smooths the edges. There are no outlines or textures: every element is a flat polygon, ellipse or rounded rectangle, and translucent shapes are stacked with alpha-compositing.
- **Sky:** a smooth gradient made with NumPy interpolation, one value per row, through these colours: deep navy `(12,20,52)` at the top, then indigo, dusky rose and orange, ending in warm amber `(250,182,92)` at the horizon (y = 1000). There are no hard steps in it.
- **Sea:** its own vertical gradient from muted blue-violet down to deep navy, with flat rounded wave dashes and a stack of amber reflection streaks below the sun.
- **Lighthouse:** on the left half (centred at x ≈ 560 px). The tower is white with red bands, a flat shaded right half, a door, a window, a gallery, a glowing lantern with a soft halo, and a red roof. It stands on layered, faceted rocks that run from the left edge down to the waterline.
- **Beam:** three stacked translucent warm wedges that start at the lantern (560, 452) and widen to the right edge, covering y ≈ 380–1060 there. The lower edge crosses the horizon, so the beam passes over the sea on the right.
- **Sailboats:** exactly 2, at about (1560, 1180) and (2080, 1360). Each has a red hull, a mast, two sails and a faint reflection.
- **Stars:** 14 small stars in the upper sky (y ≤ 400). 6 are four-point sparkles and the rest are dots. One small dot at (2150, 320) sits just under the top edge of the beam.

## Additions and choices not in the brief
- I added a half-set sun on the horizon right of centre, with glow rings, plus two low distant headlands on the horizon. They support the dusk mood and the travel-poster look.
- I added one small boulder and some foam dashes at the foot of the cliff.
- No text, letters or logos appear anywhere.

## Things I'm unsure about
- The sun's soft glow rings are translucent circles that overlap, so the sky around the sun has a few faint concentric bands. This is intentional (a flat-poster look), but a strict check for a "smooth gradient" might notice it near the horizon on the right.
- The beam is a translucent overlay, so it partly covers the sky gradient and the sun's glow on the right side.
- The left edge of the waterline boulder is cut straight where it meets the cliff. It is a minor visual detail.

## Timing
Start 22:16:24 UTC, end 22:17:46 UTC (2026-10-05), about 1.5 minutes of wall-clock time. Tool calls: 7 (not counting the final handback).
