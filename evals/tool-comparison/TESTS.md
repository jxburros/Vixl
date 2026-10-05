# Judging notes

**For the person running the comparison. Don't give this file to the agents.** It holds the
lanes to run for each test, the hard checks, the round-2 change requests and the answer keys.
Lane codes and the scoring rubric are in the [README](README.md).

`inspect_outputs.py` reports most of the measurable facts below (sizes, modes, colors, PDF boxes,
fonts, color spaces and form fields, PPTX text and notes, video length and audio, tile seams).
Use it first, then look.

Frames from a video, for timing checks:

```bash
ffmpeg -ss 3.75 -i intro.mp4 -frames:v 1 at-3.75s.png
ffmpeg -i intro.mp4 -vf "fps=2,scale=270:-1,tile=4x3" contact-sheet.png
```

---

## T01 · A picture

**Probes** whether Vixl's shapes, brushes and organic forms can make an illustration that holds up
next to an image model, and how each tool takes a precise change.
**Lanes:** V · W (SVG) · C · G

**Hard checks**

- [ ] `picture.png` is 2400 × 1600, RGB
- [ ] Exactly two sailboats
- [ ] Lighthouse on the left half; beam sweeps right across the sea
- [ ] At least five stars
- [ ] No text, letters or logos (image models often add a signature or gibberish)
- [ ] Flat style: no outlines, no photographic texture

**Round 2**

> Make it night: darken the sky but keep it a gradient, and make the beam brighter. Move the
> lighthouse and its rocks to the right half, with the beam now sweeping left across the sea. Add a
> third sailboat. Keep everything else exactly as it was.

Put round 1 and round 2 side by side. The stars, the two original boats and the shoreline should
be where they were. Image generators usually repaint the whole scene, so check what drifted.

---

## T02 · Social post with exact copy

**Probes** exact text, hierarchy and legibility at phone size.
**Lanes:** V · W · G · D (optional X)

**Hard checks**

- [ ] `post.png` is 1080 × 1350
- [ ] All six lines exact: `CAFÉ` with É, the en dash in `7–10 pm`, both middle dots, nothing missing or added
- [ ] "Open Mic Night" is the most prominent element
- [ ] All text at least 60 px from every edge
- [ ] Every line readable with the image shown at 25 %

**Round 2**

> The date moved: the third line is now "Thursday, November 19 · 7–10 pm". Add the line
> "Hosted by Mara Quinn" directly under the headline. Then make a 1080 × 1920 story version,
> `story.png`, with the same content, keeping all text out of the top 250 px and bottom 250 px.

Check that nothing else moved in `post.png`, and that the story is a real re-layout, not a stretched
or letterboxed post.

---

## T03 · Print poster

**Probes** print production (trim, bleed, safe area, CMYK, resolution) against a design tool and
the web stack. This is the "poster vs Claude Design" test.
**Lanes:** V · D · W (Chromium print-to-PDF; Ghostscript allowed for CMYK) · G · X

**Hard checks**

- [ ] `poster-print.pdf`: one page, `page_size_in=11.25×17.25`
- [ ] CMYK: `image_colorspaces` only DeviceCMYK or ICC-CMYK, and no RGB in `vector_color_ops`
- [ ] Raster content at 300 dpi or more (a page-wide raster needs at least 3375 px across)
- [ ] TrimBox and BleedBox present (`print_boxes`). Nice to have; printers cope without them.
- [ ] Background and edge artwork reach the PDF's edges (the bleed)
- [ ] All text at least 0.25 in inside the trim, which is ≥ 38 px from every edge of the 150 dpi preview
- [ ] `poster-preview.png` is 1650 × 2550, RGB
- [ ] All ten lines of copy exact; the highlights presented as a list

Watch the REPORT. Chromium prints RGB PDFs, and image models make RGB images at a few fixed sizes.
An agent that says "CMYK" when `inspect_outputs.py` finds RGB has failed the honesty check.

**Round 2**

> Change the kicker to "Old Customs House Square". Replace "Live brass band" with "Fire dancers
> at 8 pm". Add a 1 × 1 in white square with the letters "QR" centered in it, inside the bottom-right
> corner of the safe area. Same print spec as before.

---

## T04 · Logo and icon kit

**Probes** vector output, small-size legibility and the icon formats.
**Lanes:** V · W (hand-written SVG, rendered with resvg, cairosvg or ImageMagick) · D · G

**Hard checks**

- [ ] All seven files exist
- [ ] Every SVG has `embedded_images=0`, and either `text_elements=0` (outlined) or an embedded `@font-face`
- [ ] SVGs render the same on another machine (open them in a browser on a computer without the fonts)
- [ ] `favicon.ico` sizes include 16, 32 and 48
- [ ] `app-icon-1024.png` is 1024 × 1024 with mode RGB (no alpha) and square corners
- [ ] `logo-sheet.png` is 1600 × 1200 and shows every version on cream and on navy, plus real-size 16/32/64 px marks
- [ ] The mark is recognizable at 16 px; the mark uses at most two colors; `mark-mono.svg` is navy only
- [ ] Wordmark and tagline spelled exactly

The G lane can't make SVG or ICO files; record those checks as failed. That gap is the finding.

**Round 2**

> Rename the business "Tidewick & Co." and change the tagline to "Coffee · Bakery · Harbor".
> Update every file.

The mark should come through unchanged. Compare it with round 1.

---

## T05 · Slide deck

**Probes** editable PowerPoint output, speaker notes, consistent masters and a data chart.
**Lanes:** V · K (Claude's PowerPoint skill in claude.ai, or Google Slides through the Drive
connector) · C (python-pptx) · D · W (HTML slides, for example Marp or reveal.js, printed to PDF)

**Hard checks**

- [ ] `deck.pptx`: `slides=6`, 16:9 (`slide_size_in` such as `13.33×7.5`)
- [ ] `picture_only_slides=0`. Marp's PPTX export is pictures of slides by default.
- [ ] `slides_without_notes=0`
- [ ] All copy exact, including "—", "·" and "★"
- [ ] Chart: four bars labeled 8,560 · 8,830 · 8,990 · 8,900, drawn to scale, with a zero baseline
- [ ] Footer with the café name and slide number on content slides; title position and type sizes consistent
- [ ] `deck.pdf` has 6 pages and matches the PPTX
- [ ] The PPTX opens cleanly in PowerPoint or Google Slides (upload it to Drive to check)

**Round 2**

> Q4 was under-counted: it is 9,250, so the year's total is 35,630 cups. Update the chart and every
> place the total appears. Then add a slide after "By the numbers", titled "Our regulars", with the
> quote “Best flat white on the coast.” — Jo, regular since 2019. Use the same style, and give it
> speaker notes.

Answer: 7 slides; the slide-2 statistic reads 35,630; the Q4 bar reads 9,250 and is taller than Q3.

---

## T06 · Fillable PDF form

**Probes** real AcroForm fields, field kinds, required flags, options, tab order and flattening.
**Lanes:** V · C (reportlab, pypdf or pdf-lib) · K (Claude's PDF skill in claude.ai).
The web stack is left out: Chromium flattens HTML form fields when it prints.

**Hard checks** (read `form_fields` and `widget_order`)

- [ ] 14 fields with the exact keys: `performer_name`, `email`, `phone`, `act_type`, `performers`,
      `needs_mic`, `needs_amp`, `needs_keyboard`, `needs_projector`, `pieces`, `slot`,
      `photo_consent`, `signature`, `date`
- [ ] Kinds: `act_type` radio with music/poetry/comedy/other; `pieces` multiline; `slot` dropdown; the
      `needs_*` fields and `photo_consent` checkboxes
- [ ] Required: `performer_name`, `email`, `act_type`, `slot`, `signature`, `date`, and only those
- [ ] `performer_name` `max_length=80`
- [ ] Dropdown options exact, **en dashes included**
- [ ] `widget_order` follows the reading order
- [ ] `signup-sample.pdf` has no `form_fields`, and every value is fully visible: the long performer
      name isn't cut off, and the pieces are on three lines

Known traps: reportlab's AcroForm code crashes on the en dash (`KeyError: 8211`), so agents swap
in hyphens; that's a fidelity miss unless the REPORT says so. reportlab also marks checkboxes and
radios required by default.

**Round 2**

> Add a required text field `instagram`, labeled "Instagram handle", right after Email. Change the
> slot options to 30-minute slots: 7:00–7:30, 7:30–8:00, 8:00–8:30, 8:30–9:00, 9:00–9:30,
> 9:30–10:00. Keep the tab order in reading order. Re-make the sample with slot 8:30–9:00 and
> instagram @driftwoodquartet.

---

## T07 · Name badges from a spreadsheet

**Probes** variable data: one template, many rows, awkward names, a print imposition.
**Lanes:** V · C (Pillow) · W (HTML template + Playwright) · G (expect drift; allow one generation per badge)

**Hard checks**

- [ ] 10 PNGs, 1200 × 900, in file order
- [ ] Names exact: row 2 `O'Brien`; row 3 `Zoë` / `Ångström-Okonkwo`; row 5 `花子` / `山田` (watch for
      tofu boxes); row 9 `Ana Lucía` / `Gómez`
- [ ] Row 4: the long name and long company fit without clipping or overlap
- [ ] Row 6 (no company): no empty gap and no placeholder such as `None` or `nan`
- [ ] Row 7: `VOLUNTEER` printed on the sea-foam (Attendee) bar
- [ ] Bar colors by role; readable text on the navy Staff bar
- [ ] `badges-print.pdf`: 2 Letter pages, 6 badges per page (2 × 3) at exactly 4 × 3 in, with crop marks

**Round 2**

> Add an 11th badge: Iris, Van der Berg, Speaker, Lowtide Labs. Change the Sponsor color to plum
> `#6b3f69`. Regenerate every badge and the print PDF.

Answer: 11 PNGs; badges 05 and 09 are plum; the PDF still has 2 pages, the second with 5 badges.

---

## T08 · Infographic from data

**Probes** correct numbers from a data file, charts drawn to scale, and propagating a data fix.
**Lanes:** V · C (matplotlib) · W (D3, Chart.js or hand SVG) · D · G

**Answer key** (2025 as given)

| Measure | Value |
| --- | --- |
| Total cups | **35,280** |
| Busiest month | **August, 3,030** |
| Cold brew peak | **August, 420** |
| Share by drink | flat white 44.6 % (15,720) · drip 33.7 % (11,880) · tea 14.7 % (5,180) · cold brew 7.1 % (2,500) |
| Monthly totals | Jan 2,880 · Feb 2,770 · Mar 2,910 · Apr 2,910 · May 2,950 · Jun 2,970 · Jul 2,980 · Aug 3,030 · Sep 2,980 · Oct 2,970 · Nov 2,950 · Dec 2,980 |

**Hard checks**

- [ ] `infographic.png` is 1200 × 1800
- [ ] Every number matches the key; the percentages sum to 100 %
- [ ] Bars to scale with a zero baseline: August's bar is about 1.09 × February's
- [ ] Each drink has the same color in every chart; legend present
- [ ] Title, subtitle and the footnote present

**Round 2**

> December's numbers were wrong. The correct values are flat_white 1480, drip 1120, cold_brew 90,
> tea 640. Update every chart and number, and change tea's color to plum `#6b3f69`.

Answer: total **35,630**; busiest month becomes **December, 3,330**; cold brew peak is still August,
420; shares flat white 44.6 % (15,900) · drip 33.6 % (11,960) · tea 14.8 % (5,260) · cold brew 7.0 %
(2,510). The trap is the busiest-month callout, which must switch from August to December.

---

## T09 · One campaign, six sizes

**Probes** adapting one design across aspect ratios from 16:9 to 8:1 while keeping it one family.
**Lanes:** V (layouts and adapt) · W (one template, six viewports) · D · G (optional X)

**Hard checks**

- [ ] Six files at the exact sizes
- [ ] Copy exact on the four larger sizes; the leaderboard and email header carry at least the
      headline and the third line
- [ ] Story: no text in the top 250 px or bottom 250 px
- [ ] Nothing stretched or letterboxed (circles stay circular)
- [ ] One family: the same palette, typefaces and motif
- [ ] The leaderboard is readable at 100 %

**Round 2**

> Change the headline to "Winter Menu: now pouring" and replace "Smoked maple latte" with "Spiced
> honey cortado" in all six.

---

## T10 · Photo correction

**Probes** faithful correction (an edit, not a repaint), plus crops and a caption.
**Lanes:** V · T (ImageMagick, darktable-cli or GIMP batch) · C (Pillow, OpenCV, NumPy) · G (ChatGPT image editing)

**Answer key.** The faults baked into the photo (`explorations/06-photo-lab/synth.py`): rotated
**2.2° clockwise** (so the fix is about 2.2° counter-clockwise); underexposed (gamma 1.35, then
× 0.82); a cool green cast (R × 0.86, G × 1.02, B × 1.08); Gaussian noise (σ ≈ 0.022); dark wedges in
the corners from the rotation. Scene content: a lighthouse on the left headland, one standing
figure with a raised arm on the right-hand rocks, **four birds**, and the sun right of center above
the horizon.

**Hard checks**

- [ ] Horizon level to within about 0.3°
- [ ] No dark rotation wedges left in the corners
- [ ] Exposure and color look natural; the noise is reduced without smearing
- [ ] Same scene: still four birds, the same figure pose and the same lighthouse shape (overlay on the source)
- [ ] `coast-instagram.jpg` is 1080 × 1350; `coast-caption.png` is 1600 × 900 with the exact caption, readable
- [ ] The original file is untouched

Image models regenerate rather than edit. Count the birds, check the figure and compare the
resolution.

**Round 2**

> Make it a little warmer, with slightly less contrast, and change the caption to "Port Ellery,
> October evening". Apply this to all three files.

Look for compounding damage: redoing the work from the source is clean; re-editing the edited
JPEG adds artifacts and noise.

---

## T11 · From hand drawing to clean art

**Probes** keeping a person's drawing while cleaning it: tracing, straightening, gap closing and
fills under the lines.
**Lanes:** V (drawing pipeline) · T (potrace, autotrace or Inkscape trace) · C (OpenCV) · G (image editing)

**Answer key** for `fixtures/sketch.jpg`. The paper is turned about 2° counter-clockwise, with desk
showing in the corners. It holds a wavy ground line; a house body with a gap at its top-left corner
and an overshoot at the bottom-right; a roof whose two lines overshoot at the ridge, crossing in a
small X; a door open at the bottom, standing on the ground; two windows with crosses (one with a
small gap); a sun drawn as an unclosed circle (gap of about 24°) with eight rays; and a tree with a
bumpy, unclosed canopy and a two-line trunk. Nothing else. If you use your own sketch, write down
its contents the same way before you run it.

**Hard checks**

- [ ] `sketch-lines.svg` has `embedded_images=0` and paths (or lines) for the strokes
- [ ] `sketch-clean.png` is black on white, 2000 px wide, tilt corrected, paper and desk gone
- [ ] Straight lines straight, the sun round, and the gaps closed (sun, house corner, canopy)
- [ ] Nothing added or removed: overlay on the original
- [ ] Fills in the right regions and colors; `compare.png` present

**Round 2**

> Make the roof red `#c0392b` instead of coral, and add a chimney on the right side of the roof,
> drawn with the same line weight and character as the rest.

---

## T12 · Animated intro

**Probes** keyframed motion: timing, easing, exact text and the export formats.
**Lanes:** V (timeline) · W (CSS, GSAP or canvas, captured frame by frame with Playwright → ffmpeg) ·
C (Manim, or Pillow frames → ffmpeg) · G (a video model, only if your plan includes one; optional)

**Hard checks**

- [ ] `intro.mp4`: `duration_s` 6.0 ± 0.05, h264 1080 × 1080, 30 fps, yuv420p
- [ ] `intro.gif`: 540 × 540, `loop=0` (forever), `duration_ms` ≈ 6000, at most 5 MB
- [ ] `intro-last-frame.png` is 1080 × 1080, with "Tidewick Café" and "Coffee by the harbor" exact
- [ ] Beats on time: at 1.0 s the waves are part-drawn; at 2.5 s the beam moves; at 3.75 s the tagline is part-typed; from 4.5 s everything is visible and the beam still moves
- [ ] Easing, no jumps or flicker

**Round 2**

> Make it 8 seconds: slow the beam to half speed, change the tagline to "Open daily from 7 am", and
> extend the final hold to 3 seconds. Same files and specs otherwise.

---

## T13 · Pixel-art sprite

**Probes** a real pixel grid: exact frame sizes, a limited palette, hard alpha and nearest-neighbor
scaling.
**Lanes:** V (pixel art and frames) · C (Pillow, pixel by pixel) · G

**Hard checks**

- [ ] `keeper-sheet.png` is 192 × 32, RGBA, `partial_alpha_px=0`, `colors` ≤ 16 (transparent pixels aren't counted)
- [ ] `keeper-idle.gif` has 2 frames of 400 ms, `keeper-walk.gif` 4 frames of 120 ms; both 256 × 256, `loop=0`
- [ ] The GIFs use no more colors than the sheet (no smoothing in the scaling)
- [ ] `keeper-sheet.json` lists six frames with the right rectangles and durations
- [ ] Feet on the same row in every frame; the walk cycle reads as a walk

Image models fake pixel art: off-grid "pixels", hundreds of colors, soft edges and frames of
different sizes. The facts expose all of these.

**Round 2**

> Make the raincoat red, and add a 2-frame "wave" animation (250 ms per frame) after the walk
> frames: the sheet becomes 256 × 32, the JSON gains the frames, and add `keeper-wave.gif`.

---

## T14 · Lyric video

**Probes** timing from data (LRC parsing and its edge cases), audio muxing and section styling.
**Lanes:** V (`lyric-video` workflow) · T (ffmpeg with ASS or SRT subtitles and filters) ·
W (HTML/canvas frames → ffmpeg) · C (moviepy or Pillow frames)

**Answer key**

| Time (s) | On screen |
| --- | --- |
| 0.00–2.00 | Title card: "Lighthouse" / "The Vixl Examples"; no section label |
| 2.00 | "Out past the harbor where the cold waves break" (next: "A single light is burning for my sake") |
| 5.50 | "A single light is burning for my sake" |
| 9.00 | Section **Chorus** begins. "Lighthouse, lighthouse, sweep across the sea" with the beam |
| 12.50 | "Turn your golden eye and bring the ships to me" |
| 16.00 | Cleared: instrumental break |
| 18.00 | Section **Verse 2**. "The gulls are sleeping on the silver stone" |
| 21.50 | "The keeper sings the tide a song alone" |
| 25.00 | Section **Chorus**. "Lighthouse, lighthouse, sweep across the sea" with the beam |
| 28.50 | The same line again (the double timestamp), with the beam |
| 32.00 | End |

**Hard checks**

- [ ] `duration_s` 32.0 ± 0.1; h264 1280 × 720; AAC audio
- [ ] Spot-check frames at 1.0, 2.2, 9.2, 16.5, 18.2 and 28.7 s against the key
- [ ] "[Chorus]" and "[Verse 2]" never appear as lyrics
- [ ] The line at 28.50 is present (the double timestamp); the screen clears at 16.00
- [ ] Choruses look different from verses; the beam shows only on "Lighthouse" lines

**Round 2**

> Shift every lyric 0.25 s earlier (the title card still starts at 0), and make chorus lines 25 %
> larger.

---

## T15 · Seamless pattern

**Probes** repeat geometry (wrapping motifs across edges), even distribution and a print product.
**Lanes:** V (organic forms and repeats) · W (SVG or p5.js) · C (NumPy, Pillow or cairo) · G

**Hard checks**

- [ ] `tile.png` is 1024 × 1024; `seam_x` and `seam_y` close to 1 (≤ 1.5 is good; above 2 is a visible seam)
- [ ] `preview-3x3.png` is 3072 × 3072 and shows no seams or obvious grid
- [ ] `mug-wrap.png` is 2550 × 1050, with the cream rounded label and "Tidewick" in navy
- [ ] Only the five colors (anti-aliasing aside); varied sizes and rotations

**Round 2**

> Make all the shells amber, and reduce the number of motifs by about a third. Regenerate every file.

---

## T16 · Café menu

**Probes** long exact copy, tabular alignment and print typesetting, where image models are weakest.
**Lanes:** V · W (HTML/CSS print) · D · K (Google Docs through the Drive connector, or Claude's PDF
or Word skills) · G

**Hard checks**

- [ ] `menu.pdf` is one 8.5 × 14 in page with `text_chars` > 0 (real text)
- [ ] All 22 items, prices, three descriptions and the tags exact (search the PDF text)
- [ ] Prices right-aligned with decimal points lined up; leaders or another clear connection
- [ ] Nothing below 9 pt (at 150 dpi, 9 pt type is about 19 px from ascender to descender)
- [ ] Margins at least 0.5 in (75 px in the preview); everything on one page
- [ ] `menu-preview.png` is 1275 × 2100

**Round 2**

> Raise every coffee price by $0.25, remove "Drip refill", and add a note under the Coffee section:
> "Oat milk +$0.75".

Answer: Espresso $3.25 · Macchiato $3.75 · Cortado $4.25 · Flat white $5.00 · Cappuccino $5.00 ·
Latte $5.25 · Crème brûlée latte $6.00 · Drip coffee $3.00. Tea, Bakery and Seasonal prices must not
change, which is a common slip.
