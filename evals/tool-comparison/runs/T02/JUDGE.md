# T02 · Social post with exact copy: judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Lanes run: V, W (claude). Round-1 blind codes: V=4058, W=HF3D. Round 2: XQHG (V), O4UN (W).

## 1. Blind scores (written before opening key.csv)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 4058 | 4 | 4 | Clean, with clear hierarchy. The separators render as large bullet-like dots (later verified to be U+00B7 in Rubik). Big gap between "Open Mic" and "Night"; generic string lights. |
| HF3D | 5 | 5 | Strong hierarchy with a Fraunces headline, mic and string lights, a coral pill for the CTA and a cream footer. Publishable as is. |

## 2. Hard checks (round 1)

| Check | V | W |
| --- | --- | --- |
| `post.png` 1080×1350 | PASS (RGBA; mode not specified for T02) | PASS (RGB) |
| Six lines exact (É, en dash, middle dots) | PASS. `post.vixl` text checked code point by code point: U+00C9, U+00B7 ×2, U+2013. Headline stored as "Open Mic\nNight" (line break) | PASS. HTML text has U+00C9, U+00B7, U+2013. Headline is two spans in one h1 |
| "Open Mic Night" most prominent | PASS | PASS |
| All text ≥ 60 px from the edges | PASS (`vixl_check` safe_area=60; nearest about 110 px at the sides) | PASS (measured: nearest 89 px, the URL from the bottom) |
| Readable at 25 % (270×338) | PASS | PASS |
| **Total** | **5/5** | **5/5** |

## 3. Report honesty

- **V: yes.** It says RGBA, gives the font sizes and positions, and admits the kicker spacing may have had no effect.
- **W: yes.** Its measured margins and font coverage match the files.

## 4. Round 2 (date → Nov 19, host line under the headline, 1080×1920 story)

- **V.** A pixel diff of r1 against r2 `post.png` shows changes only in rows 820–1099: the host line is inserted, and the divider, date, address and details are shifted down. The kicker, headline, lamps, URL and waves are unchanged (0 changed pixels above y=780 or below y=1100). The copy in `post.vixl` is exact. The story is a real re-layout: canvas resized, waves moved, headline enlarged, URL moved off the band and recoloured. All text sits in y 440–1567, inside the 250/250 bands. **Editability 5, revision 5.**
- **W.** The date and host are correct. The headline was nudged up 18 px (61k changed pixels above y=780), which is small collateral; the lower block moved down to make room. The story is a real re-layout, with text in y 300–1653. **Editability 5, revision 4.**
