# T03 Print poster — lane W (web code + headless Chromium)

**Timing:** start 22:16:24 UTC, end 22:22:08 UTC (2026-10-05), about 6 minutes. 18 tool calls (including this report).

## Files

| File | What it is / how it was made |
| --- | --- |
| `poster-print.pdf` | The print file. One page, 810 × 1242 pt = **11.25 × 17.25 in** (trim plus 0.125 in bleed). TrimBox `[9 9 801 1233]` (11 × 17 in), BleedBox = MediaBox. Made in three steps. (1) Chromium `page.pdf()` of `poster.html` through Python Playwright (RGB, vector text). (2) Ghostscript `pdfwrite` with `-sColorConversionStrategy=CMYK -sProcessColorModel=DeviceCMYK`, image downsampling off, Flate (lossless) encoding for images. (3) pypdf to set TrimBox, BleedBox and ArtBox. All colour is DeviceCMYK. Background art is one 3375 × 5175 px CMYK image, which is **300 ppi** across the full bleed page. Text is live vector type, with Jost and Cormorant Garamond embedded as subsets (CID TrueType). |
| `poster-preview.png` | The trimmed poster: **1650 × 2550 px**, 8-bit RGB (truecolor, no alpha). Made with a Playwright screenshot of `poster.html` at device scale 150/96, clipped to the trim box (bleed removed). ImageMagick then forced RGB truecolor PNG; the resize to 1650 × 2550 changes nothing. |
| `poster.html` | **Editable source** for the layout and type. The page is 1080 × 1656 CSS px (= 11.25 × 17.25 in at 96 px/in). The trim is inset 12 px, and all text sits at least 84 px from the page edge, which is 72 px or 0.75 in inside the trim. |
| `art.html` | **Editable source** for the artwork: procedural canvas drawing, seeded so it comes out the same every run. It draws the night sky and stars, three strings of paper lanterns with glow, a quay skyline with lit windows, the water with blurred and broken lantern reflections and ripples, and a dark gradient at the bottom so the text reads clearly. It draws at 3375 × 5175 px (300 dpi over the full bleed). |
| `art.png` | Raster output of `art.html` (300 dpi, full bleed). `poster.html` uses it as its background. |
| `fonts/` | Cormorant Garamond Italic 500/600 and Jost 400/500 as TTF files, downloaded from Google Fonts (SIL OFL). They are loaded with `@font-face` from local files. |
| `build.py` | Rebuilds everything: `python3 build.py` (takes about 20 s). |

## Design
- Dark navy night sky and harbor water. Warm amber, coral and red paper lanterns hang on three sagging strings across the full width (into the bleed). Their reflections in the water are soft and broken up.
- Top: kicker "PORT ELLERY QUAY" in letter-spaced Jost caps (amber), then the title "Harbor Lights" in large Cormorant Garamond semibold italic with a faint warm glow, then the tagline in italic.
- Bottom: the date line, a rule, the four highlights as a 2 × 2 list with small lantern-dot bullets, a rule, the "Free entry · All ages · portellery.example" line, and "Presented by Tidewick Café".
- The copy is used exactly as given, including the en dash in "4–10 pm" and the "·" separators.

## Checks run
- `pdfinfo -box`: page is 810 × 1242 pt, TrimBox is inset 9 pt on every side, and BleedBox is the full page.
- `pdfimages -list`: main image is 3375 × 5175, CMYK, 300 × 300 ppi. A small grey soft mask at 300 ppi comes from the title's glow (CSS text-shadow). There are also tiny CMYK images at 720 ppi (the gradient bullets).
- `pdffonts`: all fonts are embedded and subset.
- Ghostscript tiff32nc render at 30 dpi: maximum total ink is about **293%** (mean about 253%).

## Deviations and uncertainties
- **CMYK conversion uses Ghostscript's default ICC profiles** (sRGB to its default CMYK, which is SWOP-like). It is not converted to a printer-specific profile such as GRACoL or FOGRA, and the PDF has no PDF/X OutputIntent. If the printer needs PDF/X-1a/X-4 or a specific profile, the PDF would need to be re-converted. The total ink limit of 300% was not set explicitly. It measured about 293%, which is close to the limit, so a printer with a lower limit (for example 260–280%) may want to reduce the rich navy and black.
- Text and rules came out as 4-colour CMYK builds (cream and amber on navy) rather than a single ink. That is normal for coloured text on a dark background, but small text (about 24 pt CSS, which is 18 pt) can show misregistration on a press.
- The glow behind the title is rasterised by Chromium as a 300 ppi soft-mask image. The text itself stays vector.
- No crop or registration marks were added. The brief didn't ask for them, and TrimBox/BleedBox carry the trim information.
- The intermediate RGB PDF is deleted after the conversion. Only the CMYK PDF is delivered.
- `art.png` is about 15 MB, and `poster-print.pdf` is about 12 MB (the 300 ppi image uses lossless Flate compression).
