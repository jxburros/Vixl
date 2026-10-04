# 08 · Data-driven infographic: "The Great Green Switch"

A tall (1600 × ~4300 px) magazine-style infographic poster that `build.py` generates entirely from
Python data structures: a header with three KPI cards, a horizontal bar chart (2025 share with
2015 markers and a reference line), an area/line chart drawn with `shape: path` and the `pen`,
a donut built from annular-sector paths, a 10 × 10 isotype "hundred homes" chart made of
repeated house paths, annotations with leader lines, a legend, and a footnote. The same code
regenerates a second edition from a different dataset, renders a variables-only title variant,
and exports a 1080 × 1080 social crop of the donut through an artboard + comp. It then runs a
QA pass (spacing assertions, validate rules, `check` including `color_vision`, a deuteranopia
render and a custom chart-colour separation test) and exports PNG, SVG (appearance and strict),
HTML and PDF (RGB and CMYK).

> **The data is illustrative.** "Renewable share of electricity by country/region, 2015–2025"
> numbers were invented to look plausible for a layout exploration. Do not cite them.

Run from the repository root (needs network once for Google Fonts; full run takes ~8 min, mostly
the contrast check):

```bash
python explorations/08-infographic/build.py           # everything
python explorations/08-infographic/build.py --draft   # world PNG only, ~25 s, for layout iteration
```

## Output

| World edition | Europe edition (regenerated from a second dataset) |
| --- | --- |
| ![World](output/infographic-world-preview.png) | ![Europe](output/infographic-europe-preview.png) |

| Social crop (artboard + comp) | Deuteranopia simulation | Variables-only re-render |
| --- | --- | --- |
| ![Social](output/social-donut-1080.png) | ![Deuteranopia](output/infographic-world-deuteranopia.png) | ![Variant](output/infographic-world-variant-title.png) |

Files in `output/`: `infographic-{world,europe}.vixl` (editable), `infographic-{world,europe}.png`
(full size) plus `-preview.png` (½ scale), `infographic-world-deuteranopia.png`,
`infographic-world-variant-title.png`, `social-donut-1080.png`, `social-donut-europe-1080.png`,
`infographic-world.svg` (appearance policy, 16 raster fallbacks), `infographic-world-strict.svg`
(strict policy, from the repeat-expanded variant), `infographic-world.html`,
`infographic-world.pdf`, `infographic-world-cmyk.pdf`, `qa-report.json`, `qa-rules.json`.

## Vixl features exercised

- `Project` Python API, atomic batches, `checkpoint`, `save`, `export(...)` with `scale`, `variables`, `artboard`, `comp`, `simulate`, `svg_policy`, `color_space="cmyk"`, `ink_limit`.
- Typography: `pair_fonts("dm-serif-dm-sans")` (heading/body roles), `install_font` for DM Sans 700 and DM Mono 500, `font: "heading"|"body"|registered name`.
- `type-scale` (perfect-fourth from 21 px) + custom `style-define` character/paragraph styles, `style-apply` on every text layer.
- Colour: `palette-define` + `palette-apply roles:false` with the Okabe–Ito palette, role swatches (`@background`, `@ink`, `@muted`, `@accent-text`, `@on-accent` …) and semantic data swatches (`@solar` → `@oi-1` …), colour expressions `alpha()` and `mix()`.
- Layout: 12-column `grid` guides, named `guide`s per section, `constrain` to guides (`guide:g-x1-start.left`, `guide:sec-a.top+170`), to other layers (`title.bottom+40`, `kpi0-card.bottom-30`) and to canvas offsets; `distribute` with `gap` (KPI cards, legend rows); nested `group`s; `resize` with **percentage widths of the parent group** (each bar is `"{share}%"` of the plot group, so the data *is* the geometry); `canvas` resize at the end to trim to content (constraints reflow).
- Shapes: `rectangle`, `rounded-rectangle`, `ellipse`, `shape: path` with `A` arc commands (donut sectors, isotype houses, area fills), `pen` with straight segments (lines, leader lines, reference line), `repeat` (gridlines, decorative rays, isotype runs), `clip` (rays clipped to the sun).
- `text-layout` boxes for the deck and footnotes; `variable`s (`${title}`, `${eyebrow}`) for render-time variants.
- `comp-save`/`comp-apply` + `artboard` with `targets` for the 1080 × 1080 social crop; `unconstrain` to re-anchor.
- QA: `measure_spacing` (expected gaps, equal gaps, artboard+comp), `validate` rules, `check` (bounds, overlap, safe_area, legibility with `thumbnail_width`, contrast with `targets`, `color_vision`, artboard+comp), `simulate="deuteranopia"`, CLI `vixl validate --rules` and `vixl spacing --check`, plus a custom series-separation test using `vixl.colors.simulate_vision`.

## QA results (from `qa-report.json`)

- Spacing: KPI cards 32/32 px, 12 bar gaps all exactly 18 px, legend rows 18 px, social eyebrow→title 18 px — all pass (tolerance 0–1).
- `check`: 0 errors; 7 warnings, all from the intentional sun/rays bleed and the full-bleed header band. Contrast on 12 representative text layers passes. `color_vision` passes (text only, see findings). The social artboard passes clean.
- `validate`: all custom rules pass; overall `valid: false` only because of the bleeding decorations (see findings).
- Chart-colour separation (min RGB distance between donut swatches): normal 57.5 (nuclear/fossil), deuteranopia 37.3 (nuclear/fossil), protanopia 51.5, tritanopia 42.2. Nuclear vs fossil is the weakest pair under deuteranopia — visible in the simulation; direct labels and the legend values carry the meaning.

## Findings

**Bugs**

1. **`artboard` silently drops `x`/`y`.** The schema and docs list `x`, `y` on `artboard`, but `design.py` only stores width/height/background/variables/targets, so a board can't crop a region:
   ```python
   p = Project(400, 400, "white")
   p.apply([{"type":"shape","shape":"rectangle","name":"a","width":100,"height":100,"x":300,"y":300,"fill":"red"},
            {"type":"artboard","name":"crop","width":100,"height":100,"x":300,"y":300}])
   p.state["artboards"]            # {'crop': {'width':100,'height':100,...}}  -- no x/y
   p.render(artboard="crop").getpixel((50, 50))   # white, not red
   ```
   No error or `normalized` note. I worked around it with a comp that re-anchors the donut group to the board centre.
2. **`text.NAME.font-size` assertions ignore linked character styles.** After `style-apply` of a 150 px style, `layer["size"]` is still 48, so `validate --rules 'text.title.font-size >= 120'` fails even though the title renders at 150 px (`font_size_style_mismatch` in the report). Same for validate's built-in "font size >= 24" warnings.

**Rough edges / surprises**

3. **`check` contrast is very slow on a large poster:** ~12–15 s per text layer at 1600 × 4300 (each `measure(target=...)` re-renders; a plain `render()` takes ~9 s here). Checking all ~90 text layers would take ~20 min, so the build checks 12 representative ones via `targets` (141 s). The other checks together take ~6 s.
4. **`validate` adds a "bounds within canvas" rule for every layer**, with no way to exempt intentional bleed. The decorative sun/rays make `validate` (and CLI `vixl validate`, exit 1) fail, though `check` correctly treats the same thing as a warning.
5. **`vixl validate --rules` wants a JSON file path**, but `--help` shows only `--rules RULES`; passing an assertion string gives `ERROR: [Errno 2] No such file or directory: 'layer.kpis.bounds within canvas'`.
6. **`color_vision` only checks text against its background.** It can't see that two chart fills collapse together (nuclear vs fossil under deuteranopia), so I measured that myself.
7. **`repeat` always rasterizes in SVG.** The default SVG embeds 16 PNG fallbacks (gridlines, rays, every isotype run); `svg_policy="strict"` fails with `svg_raster_required` and lists them clearly (good). Expanding repeats into plain shapes (198 → 330 layers) makes strict export pass.
8. **"Constraints must reference sibling layers" doesn't name the layers.** Grouping a layer that other top-level text is constrained to fails the whole batch with only that message, so you have to bisect.
9. **`constrain` merges into existing constraints**, so moving a group from `left` to `center-x` fails with "Use one constraint per axis" until you `unconstrain`. Reasonable, but the error doesn't name the conflicting key.
10. **Line `spacing` can't be negative** (minimum 0), so display headlines can't get tighter-than-default leading; the two-line DM Serif title looks a bit loose.
11. **`pen` strokes are clipped at the layer box.** A stroke through a point on the box edge loses half its width (seen in a prototype), so the build pads every pen layer by the stroke width.
12. Text with no `color` renders **white**, and the type-scale styles carry no colour, so text that isn't explicitly coloured disappears on a light background.
13. Legibility defaults to a 320 px thumbnail, which gives 85 warnings on a tall poster. Passing `thumbnail_width=1080` makes it meaningful.
14. `resize` with only `width` keeps the aspect ratio, so percentage-width bars must also pass `height`.

**Worked well**

- **Percentage sizes inside groups** are a natural fit for charts: an invisible plot frame defines 100 % and every bar is `resize width:"71.3%"`. Spacing measurement then confirmed exact 18 px rhythm.
- **SVG path arcs** (`A` with large-arc flags) made exact donut sectors. Paths, pen lines and outlined text all exported as vectors.
- **Grid guides + named guides + constraints** kept the build readable and let the second dataset reflow (different row counts, different y-axis max, different canvas height) without touching layout code.
- **Comp + artboard** reused the live donut group for the social crop with no duplicated layers, and `check`/`measure_spacing` accept `artboard` + `comp` too.
- Font pairing and installs were quick and cached. Okabe–Ito through `palette-define` plus role and semantic swatches made recolouring a one-line change. Atomic batches meant failed experiments never left half-built documents.
