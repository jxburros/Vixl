# Rebuild log: T01-T04 (all runs except claude-V)

Rebuilt on 2026-10-12 in this scratch mirror. Renderer: Playwright for Python with the pre-installed Chromium 141.0.7390.37 at `/opt/pw-browsers/chromium`. The default `chromium.launch()` fails here because the expected headless-shell build 1243 is not installed.

## Edits common to the browser-based runs
For every script edited below, the only change was this one line:
`chromium.launch()` → `chromium.launch(executable_path="/opt/pw-browsers/chromium")`.
No design values, copy, sizes or logic were changed.

## Fonts downloaded
Fonts came from the Google Fonts css2 API, which returned TrueType files. Each file was checked with fontTools: the family, the weight, and that it contains É, U+00B7 and U+2013.

| Saved as | Family / weight | URL |
| --- | --- | --- |
| `Fraunces-800.ttf` | Fraunces ExtraBold 800 | https://fonts.gstatic.com/s/fraunces/v38/6NUh8FyLNQOQZAnv9bYEvDiIdE9Ea92uemAk_WBq8U_9v0c2Wa0K7iN7hzFUPJH58nib1603gg7S2nfgRYIcNxyjDg.ttf |
| `DMSans-500.ttf` | DM Sans Medium 500 | https://fonts.gstatic.com/s/dmsans/v17/rP2tp2ywxg089UriI5-g4vlH9VoD8CmcqZG40F9JadbnoEwAkJxhTg.ttf |
| `DMSans-700.ttf` | DM Sans Bold 700 | https://fonts.gstatic.com/s/dmsans/v17/rP2tp2ywxg089UriI5-g4vlH9VoD8CmcqZG40F9JadbnoEwARZthTg.ttf |
| `CormorantGaramond-Italic500.ttf` | Cormorant Garamond Medium Italic 500 | https://fonts.gstatic.com/s/cormorantgaramond/v21/co3smX5slCNuHLi8bLeY9MK7whWMhyjYrGFEsdtdc62E6zd5wDDOjw.ttf |
| `CormorantGaramond-Italic600.ttf` | Cormorant Garamond SemiBold Italic 600 | https://fonts.gstatic.com/s/cormorantgaramond/v21/co3smX5slCNuHLi8bLeY9MK7whWMhyjYrGFEsdtdc62E6zd5LDfOjw.ttf |
| `Jost-400.ttf` | Jost Regular 400 | https://fonts.gstatic.com/s/jost/v20/92zPtBhPNqw79Ij1E865zBUv7myjJQVG.ttf |
| `Jost-500.ttf` | Jost Medium 500 | https://fonts.gstatic.com/s/jost/v20/92zPtBhPNqw79Ij1E865zBUv7myRJQVG.ttf |

Google serves the current font versions (Fraunces v38, DM Sans v17, Cormorant Garamond v21, Jost v20). The original agents downloaded theirs on 2026-10-05 and may have received an earlier version. Metrics could therefore differ slightly; see the T02 measurement notes.

---

## T01

### claude-C: rebuilt yes
- Source edits: none. Ran `python3 make_picture.py`.
- Produced `picture.png`: 2400 × 1600, RGB. Matches the report.

### claude-C/round2: rebuilt yes
- Source edits: none. Ran `python3 make_picture.py`.
- Produced `round2/picture.png`: 2400 × 1600, RGB. Matches the report.

### claude-W: rebuilt NO
- `picture.svg` is the editable source of the picture, and it was never committed. It is absent from this mirror: the only files are `REPORT.md` and `render.py`. A read-only `git log --all` in the repository shows no history for that path.
- `render.py` only puts `picture.svg` into an HTML page and screenshots it. There is nothing to rebuild from, so `picture.png` was not produced and nothing was invented.
- `render.py` was not edited.

### claude-W/round2: rebuilt NO
- This round has the same problem. `round2/picture.svg` was never committed, and `round2/render.py` is an unchanged copy of the round-1 script that only renders that SVG.
- `picture.png` was not produced. No source was edited.

---

## T02

### claude-W: rebuilt yes
- Source edit: `render.py`, the Chromium executable path only.
- Fonts placed in `claude-W/fonts/`: `Fraunces-800.ttf`, `DMSans-500.ttf`, `DMSans-700.ttf` (the URLs are in the table above). Chromium reported all three as "loaded".
- Produced `post.png`: 1080 × 1350, RGB. Matches the report.
- Differences in the measured margins from the report. All are still ≥ 60 px, and all checks are OK:
  - date/time: 121.5 measured, 122.5 claimed
  - address: 298.4 measured, 301 claimed
  - The other lines match: kicker 96, "Open Mic" 136.6, "Night" 300.8, pill 200.6, URL 89.
  - The likely cause is a different font version from Google Fonts.

### claude-W/round2: rebuilt yes
- Source edit: `round2/render.py`, the Chromium executable path only.
- Fonts: the same three files were placed in `round2/fonts/`.
- Produced:
  - `round2/post.png`: 1080 × 1350, RGB
  - `round2/story.png`: 1080 × 1920, RGB
  - Both match the report.
- Differences in the measured boxes from the report:
  - In the post, the date line's left edge is 120 measured against 121 claimed, and the address is 298 measured against 301 claimed.
  - In the story, the kicker top is at y 300 and the URL spans y 1606–1653, which matches the report. "Open Mic" is 109 px from the left, which also matches.
  - The safe-area checks pass for both pages.

---

## T03

### claude-W: rebuilt yes
- Source edit: `build.py`, the Chromium executable path only.
- Fonts placed in `claude-W/fonts/`: `CormorantGaramond-Italic500.ttf`, `CormorantGaramond-Italic600.ttf`, `Jost-400.ttf`, `Jost-500.ttf`. The `.ttf` names match what `poster.html` expects.
- Produced:
  - `poster-print.pdf`: 1 page, 810 × 1242 pt. TrimBox is [9 9 801 1233] and BleedBox is the full page. The main image is 3375 × 5175 CMYK at 300 ppi. There is a gray soft mask at 300 ppi and a 105 × 128 CMYK image at 720 ppi. All fonts are embedded and subset (Cormorant Garamond Medium/SemiBold Italic and Jost Regular). The file is about 12.0 MB.
  - `poster-preview.png`: 1650 × 2550, RGB truecolor.
  - `art.png`: 3375 × 5175, about 15.4 MB.
- Everything matches the report. `pdffonts` lists no Jost-Medium in round 1, which is consistent with `poster.html` not using weight 500 in that round.

### claude-W/round2: rebuilt yes
- Source edit: `round2/build.py`, the Chromium executable path only.
- Fonts: the same four files were placed in `round2/fonts/`.
- Produced:
  - `round2/poster-print.pdf`: 1 page, 810 × 1242 pt, with the same boxes and images as round 1. Jost-Medium is now embedded for the "QR" label.
  - `round2/poster-preview.png`: 1650 × 2550, RGB.
  - `round2/art.png`: 3375 × 5175. It is byte-size identical to round 1, as the report says.
- The QR square appears at the bottom right. Everything matches the report.

---

## T04
No downloaded fonts are needed. `make.py` outlines the system DejaVu fonts, which are present at `/usr/share/fonts/truetype/dejavu/`, exactly as the report says.

### claude-W: rebuilt yes
- Source edit: `build/render.py`, the Chromium executable path only. `build/make.py` was not edited.
- Ran `python3 build/make.py`, then `python3 build/render.py`.
- Produced:
  - `logo-horizontal.svg` (viewBox 606 × 160)
  - `logo-stacked.svg` (484 × 330)
  - `mark.svg` (64 × 64)
  - `mark-mono.svg` (64 × 64)
  - `favicon.ico` (16/32/48 px, RGBA)
  - `app-icon-1024.png` (1024 × 1024, RGB)
  - `logo-sheet.png` (1600 × 1200, RGB)
  - Build extras: `build/*-reverse.svg`, `build/icon-tile.svg`, `build/app-icon.svg`, `build/app-raw.png` and `build/px/*.png`
- No SVG contains `<text>`, `<image>` or `font-family`. Everything matches the report.

### claude-W/round2: rebuilt yes
- Source edit: `round2/build/render.py`, the Chromium executable path only.
- Ran `python3 build/make.py`, then `python3 build/render.py`, from `round2/`.
- Produced:
  - `logo-horizontal.svg` (viewBox 893 × 160)
  - `logo-stacked.svg` (771 × 330)
  - `mark.svg` (64 × 64)
  - `mark-mono.svg` (64 × 64)
  - `favicon.ico` (16/32/48 px, RGBA)
  - `app-icon-1024.png` (1024 × 1024, RGB)
  - `logo-sheet.png` (1600 × 1200, RGB)
  - The same build extras as round 1
- Everything matches the report.
