# T02 round 2 · claude-W (web code + headless Chromium)

Nothing outside `round2/` was changed. I copied `post.html`, `render.py` and `fonts/` from the parent folder into `round2/` and edited only the copies.

## Files
| File | What it is / how it was made |
| --- | --- |
| `post.png` | Updated post, 1080 × 1350 px RGB PNG. Screenshot of `round2/post.html` taken by `render.py` (Python Playwright, pre-installed headless Chromium, device scale factor 1). |
| `post.html` | Copy of the round-1 source, edited (see below). |
| `story.png` | New story version, 1080 × 1920 px RGB PNG. Screenshot of `story.html` taken by the same `render.py` run. |
| `story.html` | New source for the story, made from the updated `post.html` with a taller canvas and re-placed elements. |
| `render.py` | Copy of the round-1 script, extended to render both pages and to check each page's own safe area. Run with `python3 render.py`. |
| `fonts/` | Unchanged copy of the round-1 fonts (Fraunces 800, DM Sans 500/700). |
| `REPORT.md` | This file. |

## Changes to the post
- Third line now reads `Thursday, November 19 · 7–10 pm` (was November 12). Same style: DM Sans Bold 52 px, amber.
- New line `Hosted by Mara Quinn` directly under the headline: DM Sans Medium 38 px, sea-foam (a brand color), so it reads as a byline below the headline and above the date.
- To make room I moved the headline up 18 px (top 410 → 392) and moved the date, address and pill down (date 790 → 834, address 866 → 906, pill 958 → 988). The pill now ends at y = 1073, above the water. The kicker, lights, mic, water and URL did not move. I checked a zoomed crop to make sure the "g" descender in "Night" does not touch the new line.
- The copy is now the six given lines plus the new host line. Nothing else was added.

## Story (story.png, 1080 × 1920)
- Same seven lines of text, same fonts, colors and artwork (string lights, microphone, sea-foam water, cream shore band with the URL).
- Layout: kicker at y 300, string lights and mic below it, headline at 188 px (176 px in the post) on two lines, then host, date, address, pill. The water and cream band were moved so the URL sits on the cream band at y 1606–1653. The cream band carries on to the bottom edge, so the bottom 250 px have only decoration in them.
- Safe area, measured by `render.py` from the text line boxes (pill: the whole coral shape): the highest text box top is y = 300 (kicker), 50 px below the 250 px zone. The lowest text box bottom is y = 1653 (URL), 17 px above the 1670 line. All text is at least 60 px from the sides (narrowest: "Open Mic" at 109 px from the left). No text falls in the top 250 px or bottom 250 px.

## Safe-area check for the post (render.py, line boxes)
All text is still at least 60 px from every edge. Nearest edge per line: kicker 96, "Open Mic" 137, "Night" 301, host 334, date 121, address 301, pill 200, URL 89 (bottom).

## Unsure about
- The story has an open band of navy between the pill (ends y 1401) and the water (starts about y 1460–1490). I kept it as breathing room instead of stretching the type.
- The checks use CSS line boxes, which are a little larger than the ink. That makes them conservative.

## Tool calls
11 tool calls in this round, counting the final hand-off.
