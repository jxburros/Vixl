# T04 Logo kit: Tidewick Café (lane W, claude)

Timing: started Mon Oct 5 22:18:22 UTC 2026, ended Mon Oct 5 22:20:12 UTC 2026 (by `date`; the system clock shows about 2 minutes, which looks short to me). I made 16 tool calls.

## Concept
The mark is an amber flame, leaning slightly to the right, with four short amber light rays (a lamp or lighthouse glow). Under it are two bold navy wave strokes. This plays on the name: a wick's flame above the tide. There are no anchors or ship wheels. Each version of the mark uses at most two colors: amber + navy, navy only, amber + cream reversed, or cream only.
Lettering: "Tidewick" is set in DejaVu Serif Bold. The tagline "COFFEE BY THE HARBOR" is DejaVu Sans in all caps, tracked +0.16 em. All lettering is converted to outlines.

## Files
| File | How it was made |
| --- | --- |
| `logo-horizontal.svg` | 606×160 viewBox, transparent background. The mark is on the left; the navy wordmark and tagline are on the right, with the tagline under the wordmark. Hand-written SVG built by `build/make.py`, with glyphs outlined into `<path>` using fontTools (SVGPathPen). |
| `logo-stacked.svg` | 484×330 viewBox, transparent. The mark is centered above the centered wordmark and tagline. Same method. |
| `mark.svg` | 64×64. Amber flame and rays, navy waves. |
| `mark-mono.svg` | 64×64. Everything is navy `#14263b`. |
| `favicon.ico` | Contains 16, 32 and 48 px RGBA images (checked with Pillow). Each one is the color mark on an opaque cream square (`build/icon-tile.svg`), rendered in headless Chromium (Playwright) and packed into the ICO with Pillow. |
| `app-icon-1024.png` | 1024×1024, RGB with no alpha channel, square corners. Navy background with the reversed mark (amber flame and rays, cream waves) at 640 px. Source: `build/app-icon.svg`, rendered with Chromium and flattened to RGB with Pillow. |
| `logo-sheet.png` | 1600×1200, RGB. The top half is cream and shows horizontal, stacked, mark and mark-mono. The bottom half is navy and shows the reversed version of each. Both halves show the color and mono marks at real 16, 32 and 64 px, drawn as 1:1 PNGs (`build/px/`) shown at their natural size. Laid out in `build/sheet.html` and screenshotted with Playwright. |

The `build/` folder holds the sources and scripts that rebuild everything: `make.py` writes the SVGs, and `render.py` writes the PNGs, ICO and sheet. It also holds the extra reversed SVGs (`*-reverse.svg`) used on the navy half of the sheet.

## Checks
- The SVGs contain no `<image>`, `<text>` or `font-family`; all lettering is paths, so they need no fonts on the viewing machine.
- I looked at the 16 px renders: the flame-over-waves shape still reads at that size. The four rays blur into soft dots at 16 px but don't hurt it.

## Deviations and choices
- **On navy, the logos are reversed** (cream lettering and waves, amber flame). Navy waves on a navy background would disappear. These reversed files are extras in `build/`; the required deliverables are the navy/amber versions for light backgrounds.
- **The app icon uses three colors in total:** a navy background behind the two-color reversed mark (amber + cream). The mark itself stays within two colors. I read "at most two colors" as a rule for the mark, not for the background tile.
- **The favicon uses a cream background tile** instead of transparency, so the navy waves stay visible on dark browser tabs. I did not draw a separate pixel-hinted 16 px version.
- **Fonts:** downloading Google Fonts was blocked (403), so I used the DejaVu fonts installed on the system (free license). A more characterful serif would be a nice upgrade later.
- **Kerning:** I placed glyphs using their advance widths only, without the GPOS kerning table. At this size the spacing looks even.
- "Café" with the accent is not part of the wordmark, because the brief gives the name as "Tidewick".

## Unsure about
- Whether three colors on the app icon, counting the background, are acceptable.
- Whether the reversed logos needed to be separate top-level deliverables. I kept them in `build/`.
