# T11 round 2: red roof and chimney (lane T, claude-T)

Tools: Python 3 (plain string edits, no new libraries), Inkscape 1.x CLI and ImageMagick `convert`. No Vixl, no image generator. Nothing outside `round2/` was changed. The round-1 SVGs were read from the parent folder, and the edited copies were written here.

## What changed

1. **Roof colour.** In `sketch-color.svg` the `roof` polygon fill is now `#c0392b` instead of the coral `#e2725b`. No coral is left in the file, and the rendered PNG samples (192,57,43) on the roof.
2. **Chimney on the right roof slope**, added to both `sketch-lines.svg` and `sketch-color.svg`:
   - `chimneyL`, `chimneyR` and `chimneyTop` are `<line>` elements in the same "Lines" layer. They inherit its style: black, 5.5 px, round caps and joins, the same as every other stroke.
   - To match the drawing's character, the sides lean about 1 degree, like the walls. The top edge tilts slightly (1.6 px over 76 px) and overshoots each side by 6 px, like the crossed roof apex and the muntins. Each side ends exactly on the roof line, so there are no gaps.
   - The chimney spans x of about 982–1048, and its top is at y=478, about 65 px below the apex (843,421). The sides run down to the roof at y=557 (left) and y=620 (right).
   - Because the chimney stands in front of the roof, the original `roofR` line is split in two. `roofR` now runs from the apex to the chimney's left side, and a new `roofR2` runs from the right side to the eave. The endpoints at the apex and the eave did not move.
   - In the colour version, a `chimney` polygon in the "Color" layer is filled with the same red `#c0392b`. The brief gives no chimney colour, so I took it from the roof. The polygon reaches 4 px below the roof line, under the roof fill, to hide a faint antialiasing seam.
3. **Re-rendered everything** with the round-1 commands:
   - `inkscape -w 2000 -b white` followed by `convert -colorspace gray` for `sketch-clean.png`;
   - `inkscape -w 2000` for `sketch-color.png`;
   - `convert ... +append` with `fixtures/sketch.jpg` for `compare.png`.

## Files (round2/)

| File | Notes |
| --- | --- |
| `sketch-lines.svg` | Vector strokes only. There are now 32 `<line>` elements (29 + roofR2 + 3 chimney), plus the circle, the canopy polygon and the ground polyline. |
| `sketch-color.svg` | The editable layered source, with a red roof, the chimney fill and the chimney lines. |
| `sketch-clean.png` | 2000x1485, grayscale. |
| `sketch-color.png` | 2000x1485. |
| `compare.png` | 2000x750: the original photo next to the new colour result. |
| `scripts/round2.py` | The edit script. Run it from `round2/`; it reads `../sketch-*.svg` and writes the copies here. |

## Notes / judgement calls

- The chimney is a new object, so `compare.png` no longer matches the original sketch one-to-one. That was requested.
- I chose the chimney's position and size by eye. It sits on the upper-middle part of the right slope, clear of the apex and the eave, and is about 64 px wide and 80–140 px tall.
- I did not re-run the round-1 fitting scripts (`s1.py`, `s2.py`, `gen.py`), so all other geometry is byte-identical to round 1.

Tool calls: 11 (including writing this report and the final hand-back).
