# T03 Print poster: Harbor Lights (lane V, Vixl)

All visual work was done with the Vixl MCP tools (`vixl_document_create`, `vixl_font_pair`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview`, `vixl_export_file`). No pixels, SVG or HTML were written by hand. A small Python script wrote Vixl operation JSON (positions along the lantern strings, seeded ripple placement), and Vixl drew it. Other small scripts only read and checked the outputs (PIL, `pdfinfo`, `pdfimages`, `pdftotext`, `pdftoppm`).

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `poster-print.pdf` | 1 page, 810 × 1242 pt = **11.25 × 17.25 in** (MediaBox = BleedBox), **TrimBox 9 9 801 1233** (11 × 17 in). CMYK. | `vixl_export_file(color_space="cmyk", ink_limit=300)`. Text is live, with 2 embedded fonts. Shapes are vector in DeviceCMYK. The 34 translucent glow gradients are CMYK images at 300 ppi with gray soft masks. `pdfimages` lists no RGB images, and the file has no DeviceRGB. |
| `poster-preview.png` | **1650 × 2550 px, RGB**, dpi tag 150. The trimmed poster without bleed. | I added a `trim` artboard over the trim box (x/y 37.5, 3300 × 5100 px), then exported it with `scale=0.5, dpi=150, alpha=flatten`. |
| `poster.vixl` | Editable Vixl source: 238 layers, live text, a `brief` check suite and the `trim` artboard. | Made with `vixl_document_create(size="tabloid", bleed=true)`. That gives 3375 × 5175 px at 300 dpi with 37.5 px of bleed. |
| `build_scene_ops.py` | A generator for the artwork operations. | Python. It writes only JSON operations. |
| `scene-ops.json` | The artwork operations: sky, water, quay, lantern strings, lanterns and reflections. | Output of the script. The document was built from an earlier draft of this file, then corrected with `reflection-ops.json`, so applying the current file to a new document gives the same picture but not the same layer IDs. |
| `reflection-ops.json` | The second-pass batch. It removes the first-draft reflections, which read like a lit skyline, lightens the string colour and adds the final reflections. | Output of the script. Applied with `operations_path`. |

## Design

- The scene is a night sky shading into a gradient harbor. Two strings of paper lanterns sag across the top: a back row of 6 and a front row of 7, in amber, orange, red and pale gold. Each lantern has a cap, a body, a rib, a lit core, a base, a tassel and a soft gaussian glow. A low dark quay silhouette with a few lit windows sits on the horizon. Below it the water holds broken ripple-dash reflections under each front lantern, fading with depth, plus faint surface lines.
- Type is Fraunces 700 for the title and date and Atkinson Hyperlegible Next for the rest (the `fraunces-atkinson` pairing). Text colours are cream (#fbf1dc) and gold (#f4c56a) on the dark navy.
- The copy is used exactly as given; `pdftotext` returns every line. "Port Ellery Quay" is the kicker above the title. The stored text is mixed case and is drawn in capitals with `text_transform: uppercase`, so PDF text extraction returns "PORT ELLERY QUAY". The four highlights are a bulleted Markdown list in one `rich-text` layer. The bullets are drawn list markers, not characters in the copy.

## Checks run

- `vixl_check` with bounds, overlap, contrast, safe_area (113 px, which is 0.25 in inside the trim plus the 37.5 px bleed), legibility, placeholders, fonts and print (`min_ppi=300`): **passed**, with no fix or review findings. Intentional bleed layers are marked `allow_crop` and are listed only as informational.
- The suite `brief` has 19 rules and **passed**. It covers:
  - contrast of at least 4.5:1 for every text layer;
  - every text layer at least 113 px from the canvas edge (0.25 in inside trim);
  - the kicker above the title;
  - the title dominating at 1.25×: 390 px against date 140, list 104 and details 80, and against the subtitle at 108;
  - at most 2 fonts, and images at 300 ppi or more.
- The smallest text is "Presented by…" at 66 px, about 16 pt.
- The outputs were checked with scripts: the PNG size and mode, the PDF boxes, the image colour spaces and ppi, and the extracted text. I also rasterized the PDF and looked at it; it matches the PNG.

## Deviations, choices and uncertainties

- **No ICC profile.** The printer named none, so the CMYK conversion is Vixl's GCR approximation with a 300 % ink limit, and Vixl warns that colours may shift. For an exact press match, re-export with the printer's profile (`icc_profile=`). This is the main open point for the printer.
- **The PDF has no crop marks.** It is sized to trim plus bleed exactly, with TrimBox and BleedBox set, as the brief asked.
- **The suite's hierarchy rule was rewritten once.** The first version chained title, date, subtitle, list and details at 1.25× each. That was not what I meant, because the subtitle and the date are peers. I redefined it before the final layout as title > date > list > details, plus title > subtitle, at the same 1.25 ratio, and resized the text to pass. I did not loosen any tolerance.
- **Kicker letter spacing was dropped (a possible Vixl bug).** With `tracking` 22 or 12 at 300 dpi, the rendered kicker was about 3× wider than its reported `bounds`: at tracking 22, `bounds` gave 1142 px wide but it drew about 1900 px and ran off-centre toward the right edge. The ratio is close to 300/96. To keep the measurements and the output consistent, I set tracking to 0. This is worth reporting to the Vixl maintainers.
- The preview PNG uses Vixl's raster renderer, and the PDF uses its vector and CMYK path. The colours in the PDF are a CMYK conversion, so they will look slightly duller on screen than the RGB preview.
- The lanterns, water and reflections are stylized vector illustration, not a photo or an AI-generated image. I chose this to fit the "festive but calm" mood and so the PDF stays mostly vector.
