# T02 · Social post — claude-W (web code + headless Chromium)

## Files
| File | What it is / how it was made |
| --- | --- |
| `post.png` | Final post, 1080 × 1350 px, RGB PNG. Screenshot of `post.html` at a 1080×1350 viewport, device scale factor 1, taken by `render.py` using Python Playwright + the pre-installed headless Chromium. |
| `post.html` | Editable source. HTML + CSS for the text, inline SVG for the art (festoon string of café lights, a microphone, sea-foam water bands with amber lamp reflections, cream shore band). A short inline script places the light bulbs evenly along the SVG string path. |
| `render.py` | Render script. Waits for fonts, measures the tight box of every text run, prints its distance to the nearest edge, and writes `post.png`. Run with `python3 render.py`. |
| `fonts/` | `Fraunces-800.ttf` (headline) and `DMSans-500.ttf` / `DMSans-700.ttf` (all other text). Downloaded from Google Fonts (OFL) and stored locally so the source renders the same offline. Checked with fontTools that each file has É, · (U+00B7) and – (U+2013). |
| `REPORT.md` | This file. |

## Copy and hierarchy
The six lines of copy are used exactly as given, with nothing added:
1. `TIDEWICK CAFÉ PRESENTS`: small kicker, DM Sans Bold 34 px, letter-spaced, amber, at the top.
2. `Open Mic Night`: headline, Fraunces ExtraBold 176 px, cream. It is set on two lines ("Open Mic" / "Night") because one line would not fit the safe width at a size that dominates. In the DOM it is one `<h1>` with two `<span>`s, so the text is still exactly "Open Mic Night".
3. `Thursday, November 12 · 7–10 pm`: second level, DM Sans Bold 52 px, amber.
4. `12 Quay Street, Port Ellery`: DM Sans Medium 40 px, cream.
5. `Free entry · Sign up at the counter`: DM Sans Bold 36 px, navy on a coral pill.
6. `tidewick.example`: DM Sans Bold 36 px, navy, on the cream shore band at the bottom.

Colors are only the five brand colors (navy background, amber, sea-foam, coral, cream), plus transparent tints of them for glows and water. No anchors, ship wheels or other nautical clichés: the coastal feel comes from the harbor water and lamp reflections, and the café feel from the string lights.

## Safe area (measured by render.py)
Every text run is at least 60 px from every edge. Nearest edge per line, in px: kicker 96, "Open Mic" 137, "Night" 301, date/time 122.5, address 301, pill (whole coral shape) 200, URL 89 (from the bottom edge). The decorations (lights, waves) do run to the edges. The brief limits only the text, so I treated that as allowed.

## Choices and deviations
- Pill text was cream at first. I changed it to navy because cream on coral is only about 2.9:1 contrast, and navy on coral is about 4.7:1.
- Fonts came from Google Fonts over the network once and are bundled. The system fonts would also have worked as a fallback.
- No other deviations from the brief.

## Unsure about
- Whether a checker will accept the headline on two lines. The words and their order are unchanged.
- Contrast figures above are my approximate WCAG estimates, not measured with a tool.

## Timing
Start 22:17:55 UTC, end 22:19:31 UTC (2026-10-05), about 2 minutes by the clock. About 14 tool calls.
