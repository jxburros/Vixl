# T03 round 2 — lane W (web code + headless Chromium)

**Tool calls:** 9 in total for this round, counting the write of this report and the final hand-back.

## What I changed
All of the edits are in `round2/poster.html`. Nothing outside `round2/` was modified. I copied `poster.html`, `art.html`, `art.png`, `build.py` and `fonts/` into `round2/` first, then edited only the copy of `poster.html`.

1. **Kicker:** the text changed from "Port Ellery Quay" to "Old Customs House Square". The style is the same as before: Jost caps, letter-spaced, amber. Measured text span is x 229–862 px, centred, well inside the safe area.
2. **Highlight:** "Live brass band" was replaced with "Fire dancers at 8 pm". It stays the fourth item of the 2 × 2 list.
3. **QR placeholder:** I added a `.qr` div. It is a 96 × 96 CSS px white (#fff) square, which is **1 × 1 in** at 96 px/in, with "QR" in black Jost Medium 34 px (≈ 25.5 pt), centred with flexbox. It is positioned `right:36px; bottom:36px` on the 1080 × 1656 px bleed page. **"Safe area" here means the brief's text-safe zone: 0.25 in inside the trim**, which is 0.125 in bleed + 0.25 in = 36 px from the page edge. So the square's outer corner sits exactly on the bottom-right corner of that zone. Measured box is x 948–1044, y 1524–1620 px. In trim coordinates, that puts it 0.25 in from the right and bottom trim edges.
4. **Footer moved up 64 px** (`.foot` `bottom:84px` → `bottom:148px`). This keeps the full-width rule and the info line clear of the square. The footer now ends at y 1508 px, 16 px above the square's top (1524). Its horizontal centring is unchanged. The head block was not touched.

The artwork is unchanged. `build.py` regenerated `art.png` from `art.html` (seeded, so it is deterministic), and the file size is identical to the original.

## How it was built
I ran `python3 build.py` in `round2/`. It is the same pipeline as round 1:
- Chromium `page.pdf()` through Python Playwright
- Ghostscript `pdfwrite` to DeviceCMYK (lossless Flate images, no downsampling)
- pypdf to set the TrimBox, BleedBox and ArtBox
- a Playwright screenshot at scale 150/96, clipped to the trim, then ImageMagick to make an RGB truecolor PNG

## Deliverables (same names)
| File | Result |
| --- | --- |
| `poster-print.pdf` | 1 page, 810 × 1242 pt (11.25 × 17.25 in). TrimBox `[9 9 801 1233]`, BleedBox = MediaBox. DeviceCMYK. Background image 3375 × 5175 CMYK at 300 ppi. Fonts embedded as subsets. |
| `poster-preview.png` | 1650 × 2550 px, 8-bit sRGB truecolor, trimmed (no bleed). |
| `poster.html`, `art.html`, `build.py`, `fonts/`, `art.png` | Editable source and the inputs the build needs. |

## Checks
- `pdfinfo -box`: the boxes are as listed above.
- `pdfimages -list`: main art is 300 ppi CMYK. There is a 300 ppi grey soft mask for the title glow and a 720 ppi bullet image. `pdffonts`: everything is embedded and subset.
- Ghostscript tiff32nc renders:
  - Sampled at 72 dpi, the square's fill is **0/0/0/0 CMYK**, which means unprinted paper white, as expected for "white".
  - Maximum total ink at 30 dpi is ≈ 295% (mean ≈ 251%).
- Visual check of the preview: the square is at the bottom-right, the "QR" letters are centred, and nothing overlaps.

## Deviations and uncertainties
- **The "QR" letters are rich black, not 100% K.** Ghostscript's default sRGB→CMYK conversion turns #000 into about C72 M67 Y67 K88 (≈ 295%). At about 25 pt this could show slight misregistration on press. Chromium cannot write a K-only colour, so fixing it would need a separate PDF post-processing step. I didn't do that.
- "White" is unprinted paper (no white ink). If the poster goes on coloured or clear stock, the square won't be white.
- The square is a placeholder only. It contains the letters "QR" as asked, not a real QR code.
- I read "safe area" as the brief's 0.25 in-inside-trim text zone. The other text on the poster sits farther in (0.75 in inside trim, as in round 1), so the square sits closer to the edge than the rest of the text. That is intended.
- Same caveats as round 1: Ghostscript default (SWOP-like) CMYK profile, no PDF/X OutputIntent, no crop marks.
