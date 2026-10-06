# T02 · Social post with exact copy: judge notes

- **V lane:** re-run on Vixl 0.20.0 and judged 2026-10-06 by a claude-opus-5-5 subagent.
- **W lane:** run and judged 2026-10-05. Its scores and notes below are unchanged.
- Only W's sources are committed, so for the blind look I rebuilt W's PNGs in a scratch copy outside the repo. I used its `render.py` with Playwright 1.56 and the bundled Chromium 1194. Its `fonts/` folder was not committed, so I downloaded the same Google Fonts files again (Fraunces 800, DM Sans 500 and 700). The rebuilt render printed the same text positions that W's REPORT lists (kicker 96, "Open Mic" 137, URL 89 px from the edge), so it matches what was judged.
- **Blind codes for this pass:** V r1 = BWGN, V r2 = K8DY, W r1 = DHH2, W r2 = PYYD (rebuilt). On 2026-10-05, the codes were V = 4058 and W = HF3D (round 1), and XQHG (V) and O4UN (W) for round 2.

## 1. Blind scores (written before opening key.csv)

| Code | Run | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| BWGN | V r1 (2026-10-06) | 5 | 4 | The Fraunces headline is set left on two lines, with a coral pendant lamp and glow and sea-foam wave lines at the foot. All six lines are exact, and the hierarchy is clear. The lamp bulb sits tight above "Mic", and the right half under the headline is empty. Clean but a little sparse. |
| K8DY | V r2 (2026-10-06) | 5 | 4 | Same design with the host line and the new date. The story is a real re-layout (left column, lamp hung lower, more air). It leaves a lot of empty navy above the waves. |
| DHH2 | W r1 (rebuilt, reference only) | 5 | 4 | The art is the richest of the runs (string lights, mic, harbour band). The leading is tight: the "p" in "Open" nearly touches "Night". |
| PYYD | W r2 (rebuilt, reference only) | 5 | 4 | A real re-layout. The cream band at the bottom of the story is large and empty. |
| 4058 | V r1 (2026-10-05, Vixl 0.18.0) | 4 | 4 | Clean, with clear hierarchy. The separators render as large bullet-like dots (later verified to be U+00B7 in Rubik). Big gap between "Open Mic" and "Night"; generic string lights. |
| HF3D | W r1 (2026-10-05) | 5 | 5 | Strong hierarchy with a Fraunces headline, mic and string lights, a coral pill for the CTA and a cream footer. Publishable as is. |

W keeps its 2026-10-05 scores (5/5). My blind look at the rebuilt W gave craft 4 because of the tight headline leading. I list it only to show that this pass scored a little harder than the last one, not to change W's scores.

## 2. Hard checks (round 1)

| Check | V (0.20.0, 2026-10-06) | W (2026-10-05) |
| --- | --- | --- |
| `post.png` 1080×1350 | PASS (RGB) | PASS (RGB) |
| Six lines exact (É, en dash, middle dots) | PASS. I checked the text layers in `post.vixl` code point by code point: U+00C9, U+00B7 ×2, U+2013. There is one text layer per line, with nothing added. The headline is the single string "Open Mic Night" and wraps in a 900 px box. | PASS. HTML text has U+00C9, U+00B7, U+2013. Headline is two spans in one h1 |
| "Open Mic Night" most prominent | PASS. The headline is Fraunces 700 at 176 px; the next largest line is the date at 54 px. | PASS |
| All text ≥ 60 px from the edges | PASS. I measured the text pixels with the decoration masked out: left 90, top 130, right about 115 (the date line ends at x 964), bottom 204. `vixl check` with safe_area=60 is clean. | PASS (measured: nearest 89 px, the URL from the bottom) |
| Readable at 25 % (270×338) | PASS. Every line is readable, including the 36 px kicker. | PASS |
| **Total** | **5/5** | **5/5** |

## 3. Report honesty

- **V: yes.** Every claim I checked matches the files:
  - **Round 1:**
    - The text strings, fonts and sizes match `post.vixl`.
    - The lowest text ends at y 1146 (I measured 1145), and the widest line ends at x 969 (the layer box ends there; I measured the ink at 964).
    - It reports the RGB mode correctly.
    - It flags its own doubts: the headline breaks by wrapping, and it could not prove the margins from pixels alone.
  - **Round 2:**
    - It says the post's pixel diff is confined to x 90–967, y 674–1154. I measured x 90–966, y 674–1153.
    - The layer moves it lists (+17/+15/+12/+8 px) match `round2/post.vixl`.
    - The story's text range, y 420–1555, matches my measurement.
    - It says openly that `vixl_adapt_layout` left the kicker in the top band and that it re-placed the text by hand.
- **W: yes.** Its measured margins and font coverage match the files.

## 4. Round 2 (date → Nov 19, host line under the headline, 1080×1920 story)

- **V (0.20.0).**
  - **Post.** The agent copied `post.vixl`, changed the date with `text-set` on the existing layer, and added a `host` text layer at y 674, under the headline. To make room, it moved the lower block down a little: rule +17, date and address +15, pill and CTA +12, URL +8.
  - **Pixel diff, r1 against r2 `post.png`.** The only changes are inside x 90–966, y 674–1153, in these bands: host, rule, date, address, pill and URL. The kicker, headline, lamp, glow, waves and background are unchanged. That is the same kind of make-room shift the 0.18.0 run made, and it was accepted then. The copy is exact in both `.vixl` files.
  - **Story.** It is a real re-layout, not a stretch:
    - The canvas is 1080×1920.
    - The headline grew to 188 px.
    - The lamp hangs lower, the waves are re-anchored to the bottom, and the pill is wider.
    - All text sits in y 420–1555, clear of the top 250 px and the bottom 250 px. Sides are ≥ 90 px.
  - **Editability 5, revision 5.**
- **W.** The date and host are correct. The headline was nudged up 18 px (61k changed pixels above y=780), which is small collateral; the lower block moved down to make room. The story is a real re-layout, with text in y 300–1653. **Editability 5, revision 4.**

## 5. Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 5/5 | 5/5 |
| Fidelity / craft | 4 / 4 | 5 / 4 |
| Report honest | yes | yes |
| Editability / revision | 5 / 5 | 5 / 5 |

- **Better:**
  - The middle dots now read as normal separators. Before, they were big bullet-like dots in Rubik.
  - The headline leading is tight. Before, there was a big gap between "Open Mic" and "Night".
  - `vixl_font_pair` gave a fitting serif and sans pair (Fraunces and Work Sans).
  - The PNG is RGB. Before, it was RGBA.
  - The decoration is more specific to the brand than generic string lights.
- **Same:**
  - Craft stays at 4. The design is clean and publishable but sparse, with a lot of empty navy.
  - Round 2 was again an in-place edit of the `.vixl`, with only the make-room shift below the headline.
- **Product gaps that remain or are new in 0.20.0** (none of them changed a score, because the agent worked around each one):
  1. **The `event-poster` layout buries the headline.** I reproduced it with `layout-apply name=event-poster` on `instagram-portrait`. It sets the date at 82 px, wrapped onto 3 lines, in a large accent block. The headline gets 104 px on one line, so the date block dominates. The date also breaks after "12 ·", which leaves the middle dot at a line end. The agent removed the layout's text and rebuilt the composition by hand.
  2. **`adapt-layout` ignores the story's UI safe zones.** I reproduced it on `round2/post.vixl` with `size: "story"` (and `"instagram-story"`). The kicker stays at y 130 and the URL lands at y 1688–1724, both inside the 250 px bands. The size's own description says "keep text out of top/bottom 250px".
  3. **The default `check` ignores the canvas's own safe area.** After the adapt above, the canvas records `safe: 250`, yet `check()` and `check(checks=["safe_area"])` both report nothing. The safe-area check only runs when `safe_area=` is passed explicitly (`checks.py`, around line 469). The stored value is also one inset for all four sides: 250 px at the sides would be wrong for a story, which only needs top and bottom bands.
- **Gone:** the RGBA output and the bullet-like rendering of U+00B7 seen in 0.18.0.
