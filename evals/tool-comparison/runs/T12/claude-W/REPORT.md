# T12 · Animated intro — lane W (web code + headless Chromium)

**Timing:** start 22:16:25 UTC, end 22:19:14 UTC (2026-10-05), about 3 minutes of wall time. 18 tool calls in total, this file included.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `intro.html` | Editable source. One inline SVG scene plus a `renderAt(t)` function that sets every element for time `t`, so the output is deterministic. Opened directly in a browser it plays a live 6 s loop; `?t=4.2` freezes it at a given time. | Written by hand (plain SVG and JS, no libraries). |
| `render.py` | Render script | Python Playwright with the pre-installed headless Chromium. Viewport 1080×1080, DPR 1. It calls `renderAt(i/30)` and takes a screenshot for each frame i = 0…179 (180 PNG frames), then runs ffmpeg. `python3 render.py 2.5 4.0` renders only those stills. |
| `intro.mp4` | 1080×1080, H.264 (libx264, crf 18, preset slow), yuv420p, 30 fps, 180 frames, 6.000 s, +faststart. 368 KB. | ffmpeg from the PNG frames. ffprobe confirms the specs above. |
| `intro.gif` | 540×540, 30 fps, 180 frames, 6.0 s. Loops forever (NETSCAPE loop count 0). 1.71 MB, under the 5 MB limit. | ffmpeg two-pass: lanczos scale, then palettegen (128 colours, diff stats), then paletteuse (bayer dither, diff rectangles). |
| `intro-last-frame.png` | 1080×1080 PNG, the final frame (frame 179, t = 5.967 s) | A copy of the last rendered frame. |

## How the timeline maps to the brief

- **0.0–1.5 s, waves:** There are three layered waves in the bottom third: back `#4f6c73`, middle `#7ca19d` (navy/sea-foam tints) and front sea-foam `#a8d5c8`, with a cream crest line on the front wave. Each wave's path is built from left to right with easeInOut. The starts are staggered: 0–1.0, 0.25–1.25 and 0.5–1.5 s. After that the waves keep drifting slowly, so the hold isn't static.
- **1.0–3.0 s, lighthouse:** It rises 460 px with easeInOut and fades in over 1.0–1.8 s. It is clipped at y = 800, so it comes up from behind the sea. It is a cream tower with sea-foam stripes and an amber lamp.
- **From 2.0 s, beam:** An amber wedge with a gradient. It fades in over 2.0–2.6 s and swings sinusoidally between 8° and 136° above horizontal, with a 2.8 s period. A sine swing slows to zero at each end, so there is no jerk at the turns. It runs until the last frame. A soft lamp glow fades in with it.
- **2.0–3.5 s, wordmark:** "Tidewick Café" slides up 60 px and fades in, with easeInOut. It sits above the waves, to the right of the lighthouse.
- **3.0–4.5 s, tagline:** "Coffee by the harbor" types on one character at a time, evenly spaced over the 1.5 s. Each letter fades in over about 2 frames rather than popping. Every character is its own tspan inside a centred text element, so the line doesn't shift as letters appear.
- **4.5–6.0 s, hold:** Everything is visible. The beam keeps sweeping and the waves keep drifting.

## Choices and deviations

- **Fonts:** The wordmark uses **P052** Bold (a URW Palatino clone) and the tagline uses **URW Gothic** (a Century Gothic/Avant Garde clone). Both are installed locally, so I didn't depend on web fonts. The brief named no typeface. In other browsers the source falls back to Palatino, Georgia and Century Gothic.
- **Layout:** I put the lighthouse on the left and the text on the right, so the rising tower and sweeping beam don't collide with the wordmark. The beam's lowest angle (8° above horizontal) keeps it above the text.
- **Background:** It is navy `#14263b`, with a very subtle radial lift to `#1c3550` near the horizon. Every pixel stays a navy shade, but it isn't one flat colour. Strictly, the brief says "navy background", so if a flat fill is required, this is a small deviation.
- **Wave draw-in:** "Draw in" is done by extending the filled wave shape from left to right. The leading edge is a vertical cut while each wave is growing. That edge is visible only during 0–1.5 s.
- **Last frame:** At 30 fps a 6.0 s clip has frames at t = 0 … 5.967 s, so the "final frame" PNG is t = 5.967 s, not t = 6.0 s.
- **GIF frame rate:** The GIF keeps the full 30 fps. Browsers round GIF frame delays to 1/100 s, so they show 3–4 cs per frame and the timing is very slightly uneven.
- **Intermediate frames:** I deleted the 180 PNG frames (36 MB) after encoding. `python3 render.py` regenerates them and all the outputs.

## Unsure about

- **Accent:** The "é" depends on P052 having the glyph. It does, and it rendered correctly.
- **Front wave colour:** The front wave is light sea-foam over a large area at the bottom. That fits the palette, but it is a lot of light colour in the bottom quarter.
