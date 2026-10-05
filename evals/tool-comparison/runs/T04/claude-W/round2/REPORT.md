# T04 Logo kit, round 2: renamed to "Tidewick & Co." (lane W, claude)

## What changed
- **Business name:** the wordmark now reads **"Tidewick & Co."** (it was "Tidewick").
- **Tagline:** now **"COFFEE · BAKERY · HARBOR"** (it was "COFFEE BY THE HARBOR"). I kept the round-1 tagline style: DejaVu Sans in all caps, tracked +0.16 em, with U+00B7 middle dots between the words. The text is the requested "Coffee · Bakery · Harbor" set in capitals.
- The mark, the colors and the fonts did not change. The wordmark is still DejaVu Serif Bold at the same 84-unit size, and the tagline is still 19.5 units. All lettering is still outlined to `<path>`, so there is no `<text>`, `<image>` or `font-family` in any SVG (I checked).

## Files in round2/ (same names as round 1)
| File | Change |
| --- | --- |
| `logo-horizontal.svg` | New wordmark and tagline. The longer name makes the viewBox wider: 893×160, up from 606×160. Title: "Tidewick &amp; Co. logo, horizontal". |
| `logo-stacked.svg` | New wordmark and tagline, still centered under the mark. The viewBox is now 771×330, up from 484×330. |
| `mark.svg`, `mark-mono.svg` | Same artwork. Only the `<title>` changed, to "Tidewick & Co. mark" and "Tidewick & Co. mark, navy". |
| `favicon.ico` | Rebuilt from the updated `build/icon-tile.svg` (only its title changed). It still holds 16, 32 and 48 px RGBA images, so the pixels match round 1. |
| `app-icon-1024.png` | Rebuilt from `build/app-icon.svg` (only its title changed). Still 1024×1024 RGB, opaque, square corners. The icon has no lettering, so it looks the same as before. |
| `logo-sheet.png` | Re-rendered at 1600×1200 RGB using the new logos, on cream and on navy, with the marks at real 16, 32 and 64 px. |
| `build/` | A copy of the round-1 sources with my edits. The scripts write into round2/. The reversed SVGs were regenerated too. |

## How
1. I copied `build/` into `round2/build/`. The scripts write to the parent of `build/`, so their output goes to round2/ and nothing outside round2/ changed.
2. In `round2/build/make.py` I replaced the wordmark string with "Tidewick & Co." and the tagline string with "COFFEE · BAKERY · HARBOR". I also updated every `<title>` string, and made `svg()` escape `&` as `&amp;` in titles, because a bare `&` is invalid XML. I parsed every SVG with xml.dom.minidom to confirm they are valid.
3. In `round2/build/sheet.html` I changed the horizontal logo's display width from 600 px to 700 px, so the wider logo isn't drawn too small.
4. I ran `make.py`, which writes the SVGs, and then `render.py`, which uses headless Chromium (Playwright) for the PNGs and Pillow for the ICO and the RGB flattening. I checked the sizes and modes with Pillow and looked at the sheet.

## Notes and unsure points
- The horizontal lockup is now much wider (about 5.6:1). For tight spaces, the stacked version or the mark alone may suit better.
- In the stacked version the name is now wider than the mark, so it looks top-light, although it is centered correctly.
- If "Coffee · Bakery · Harbor" should appear in mixed case rather than all caps, change the tagline strings in `build/make.py` and rerun both scripts.

## Tool calls
8 tool calls in this round, including the final hand-back.
