# T13 · Pixel-art sprite

A game character sprite with two animations.

**Character.** A small lighthouse keeper in a yellow raincoat and hood, with dark boots, carrying a
lantern. Side view, facing right.

**Pixel rules.**

- Every frame is exactly **32 × 32** pixels.
- At most **16 colors**, with dark outlines.
- Background fully transparent; every pixel is either fully transparent or fully opaque.
- Crisp pixels only: no anti-aliasing, blur or smooth scaling anywhere.
- The character stands on the same baseline in every frame.

**Animations.**

- `idle`: 2 frames, 400 ms each (a small breathing bob; the lantern sways).
- `walk`: 4 frames, 120 ms each (a readable walk cycle).

## Deliverables

| File | Spec |
| --- | --- |
| `keeper-sheet.png` | 192 × 32 px: idle 1, idle 2, walk 1–4, left to right, unscaled |
| `keeper-sheet.json` | Each frame's name, x, y, width, height and duration in ms |
| `keeper-idle.gif` | Scaled 8× (256 × 256) with nearest-neighbor, looping |
| `keeper-walk.gif` | Scaled 8× (256 × 256) with nearest-neighbor, looping |
| your editable source | if your tool has one |

## When you're done

Put every file in the run folder you were given. Then write `REPORT.md` there, listing each file
and how you made it, anything in this brief you didn't do or did differently and why, and anything
you're unsure about. Be exact: the report is checked against the files.
