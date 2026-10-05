# T09 · Tidewick Café winter campaign (lane W, web code + headless Chromium)

## Files
| File | Size | How it was made |
| --- | --- | --- |
| `instagram-square.png` | 1080 × 1080 | Rendered from `campaign.html#instagram-square` |
| `instagram-story.png` | 1080 × 1920 | `campaign.html#instagram-story`; all text sits between y≈741 and y≈1549 (outside top 250 / bottom 250 px). The lamp graphic and waves enter the margins; no text does. |
| `x-post.png` | 1600 × 900 | `campaign.html#x-post` |
| `facebook-event.png` | 1920 × 1005 | `campaign.html#facebook-event` |
| `leaderboard.png` | 728 × 90 | `campaign.html#leaderboard`, headline + line 3 only |
| `email-header.png` | 600 × 200 | `campaign.html#email-header`, headline + line 3 only |
| `campaign.html` | editable source | One HTML/CSS/inline-SVG/JS file. Each size has its own layout function (text placement, sizes, lamp position, wave parameters). Open it with no hash to see all six at once. |
| `render.py` | script | Python Playwright with the pre-installed Chromium. For each size it opens the page at that viewport (device scale 1), waits for fonts to load, checks that both web fonts loaded, and screenshots the ad element. |
| `fonts/Fraunces-latin.woff2`, `fonts/DMSans-latin.woff2` | | Latin subsets of Google Fonts (OFL), downloaded once so the render does not need the network |

To rebuild: `python3 render.py` in this folder.

## The shared look
- Palette is only the five brand colours: navy #14263b background, cream text, amber headline accent and lamp, sea-foam menu items, coral URL pill and item separators. The one extra colour is a darker navy (#0d1b2b) for the lowest wave band.
- Type: Fraunces 800 for the headline, with "Winter Menu" in amber. DM Sans 500/700 for everything else.
- Motif: a harbour "lamp", which is an amber disc with three steam curls and faint amber halo rings, plus stacked rolling wave bands (sea-foam, coral, amber, dark navy) and faint cream star dots. There are no stars on the two banners, and the leaderboard's waves fill only its right-hand strip.
- Every size has its own layout, with nothing stretched or letterboxed. Square: text top-left, lamp top-right, waves along the bottom. Story: lamp up top, centred text stack, waves at the bottom. X and Facebook: text column on the left, big lamp on the right, waves along the bottom. Leaderboard: lamp, then a one-line headline over line 3, then a wave strip. Email: two-line headline and line 3 on the left, lamp on the right, thin waves along the bottom.

## Copy
- The four large sizes use all four lines word for word. Line 2 keeps its "·" separators, coloured coral.
- The leaderboard and email header drop lines 2 and 4, as the brief allows.
- Markup inside the lines (colour spans, and no-wrap spans so menu items and "at Tidewick Café" don't split across lines) does not change the text. The email headline has a forced line break after "Menu".
- I added no other copy: no wordmark, no logo text.

## Choices and deviations
- The fonts are Google Fonts I picked myself, because the brief names no typefaces. They are stored locally.
- The lamp-and-steam mark is my own invented motif. Tidewick has no logo.
- On the square, X and Facebook layouts, a line of menu items can end with a "·" separator just before a wrap. I left it as is.
- On the leaderboard, the wave strip starts with a hard vertical edge at x=600, which is intentional.

## Unsure about
- I have not checked the Facebook event cover against Facebook's mobile crop. The important content sits in the left and central area, but the lamp on the far right may be cropped on some devices.
- I checked text against the canvas edges and the story safe zones using DOM bounding boxes (printed by render.py) and by looking at the renders. I did not run any automated contrast check.

## Timing
Start: Mon Oct  5 22:19:25 UTC 2026 · End: Mon Oct  5 22:21:26 UTC 2026 · About 15 tool calls.
