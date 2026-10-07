# House style: decisions for general defaults

[Documentation home](README.md) · [Safe design variety](safe-variety.md) · [Brands](brands.md) · [Typography](typography.md)

This is a **decision record**. It covers what Vixl produces when a brief gives little or no information about
fonts, colour, spacing, layout, finishing, motion or output. Each decision lists today's behaviour (with the code
location), the options, a recommendation and a checkbox to record the choice. The open bugs that stop today's
defaults from working as designed are listed at the end.

The inventory was taken at 0.22.0 (commit fb8b92f).

## The problem in one paragraph

Sameness does not come from having rules. Today it comes from **narrow pools**:
- **Layouts:** every unspecified roll picks from 15 "safe" layouts, all of them quiet compositions.
- **Palettes:** the 20 safe palettes are all light and low-chroma, and light backgrounds are mixed 82% toward white.
- **Mode:** two out of three rolls are light mode.
- **Looks:** the rolled finishing look is applied at amount 0.1, which is nearly invisible.

At the same time, some basic defaults contradict the checks:
- text is white on a canvas whose contrast is measured over white;
- the plain `text` operation ignores the document's fonts and falls back to the proofing font;
- line spacing follows four different conventions.

## Proposed principle

**Fix the craft, vary the taste, weight both by purpose.**

- **Craft (fixed, the same everywhere):** contrast floors, one spacing scale, one leading rule, line length,
  minimum sizes, safe areas, alignment to a grid.
- **Taste (varied by seed):** palette, font pairing, layout, light or dark mode, accent device, corner style,
  finishing look, background treatment.
- **Purpose (biases the taste):** a poster, a slide, a form, a diagram, a logo and a social card each weight the
  taste pools differently. An explicit brief or a brand always wins.

---

## A. Philosophy and precedence

These set the frame for everything else, so decide them first.

### A1. Should Vixl have a recognisable house look?
Today the taste is neutral and "safe", with no stated identity.
- [ ] Neutral: no identity; quiet, safe defaults (today)
- [X] Signature: a recognisable Vixl look (typeface, palette, accent device)
- [X] Purpose-driven: no signature, but defaults chosen from what is being made

**Recommendation:** purpose-driven. A signature look makes every agent's output identifiable as "made by Vixl",
which users of a design engine rarely want.

Decision: craft signature (clarified). The signature lives only in the fixed craft (sharp corners, thin part lines, offset shadows, uppercase labels, the line-height rule); fonts, palettes and layouts vary by purpose.

### A2. What varies between unspecified runs, and what never varies?
Today every taste dimension is rolled, and the craft rules are scattered across modules (see C5 and E1).
- [X] Split into fixed *craft* and varied *taste*, as above
- [ ] Vary everything (today)
- [ ] Vary nothing without an explicit seed

**Recommendation:** the craft/taste split.

Decision:

### A3. Order of precedence
Today: explicit field > brand (`brand.json`) > document `design_defaults` > a fresh seeded roll
(`src/vixl/variety.py:149`, `docs/safe-variety.md`).
- [ ] Keep it as it is
- [x] Add a **purpose** tier: explicit > brand > purpose profile > document defaults > roll

**Recommendation:** add the purpose tier. The brief kinds in `src/vixl/briefs.py` already name the purpose.

Decision:

### A4. Safe versus expressive pools
Today rolls are safe-only, while brief recommendations name expressive options such as brutalist, hard-shadow and
risograph (`src/vixl/briefs.py:30-339`).
- [ ] Safe only (today)
- [X] Gated by variety level: low = safe; medium = safe plus a curated bold set; high = full catalogue
- [X] Weighted by purpose only

**Recommendation:** gate by variety level, then weight by purpose.

Decision:

### A5. Variety levels and the default level
Today the levels are `low`, `medium` (default), `high` and `fixed`. Low and medium differ only in the look pool
(`src/vixl/variety.py:102-119`).
- [ ] Keep the current levels
- [X] Redefine them so each level visibly differs (pool breadth, look amount, layout boldness, colour intensity)

**Recommendation:** redefine the levels and keep `medium` as the default.

Decision:

### A6. The same defaults on every surface
Today MCP `vixl_document_create` and REST/session creation roll and store `design_defaults`, while CLI `vixl new`,
`Project()` and `Project.sized()` do not. The CLI has no `--seed` or `--variety`
(`src/vixl/interfaces.py:205-207`, `src/vixl/cli.py:423-468`).
- [X] Unify: one creation path for every surface
- [ ] Keep the CLI and Python minimal

**Recommendation:** unify.

Decision:

---

## B. Single-property defaults (a field left out)

### B1. Text colour
Today plain `text` and rich text default to `white` (`src/vixl/operations.py:603`, `src/vixl/richtext.py:338`), while
text-flow picks `#111111` or `#ffffff` from the background (`src/vixl/textflow.py:499-509`). Issue #283.
- [ ] Palette `@ink` when the document has a palette, else the contrast pick against the background
- [X] Always the contrast pick
- [ ] Keep white

**Recommendation:** `@ink`, else the contrast pick.

Decision:

### B2. Text font
Today plain `text` resolves to the bundled DejaVu Sans even when the document has typography
(`src/vixl/render.py:114-115`). The fonts check then raises a must-fix finding.
- [X] The `body` role when typography exists; `heading` for text at or above the title step of the type scale
- [ ] Always `body`
- [ ] Keep the fallback

**Developer Addition:** We should have multiple stages of text like h1, h2, h3, subtitles, body, citation, etc.  But they shouldn't all have to be used, and most of the time, it will only be 2-4 fonts spread out across different stages, but we want to give users the options.

**Recommendation:** `body`, with `heading` above the title size.

Decision:

### B3. Text size
Today plain `text` is a fixed 48 px on any canvas, and rich-text spans fall back to 48.
- [x] The document's body size from its type scale (proportional to the canvas)
- [ ] A fixed size

**Recommendation:** proportional to the canvas.

Decision:

### B4. Shape fill
Today the fill is `white`; open stroked shapes are transparent (`src/vixl/geometry.py:76-82`). Solids are white, and
the gradient default is black → white (`src/vixl/operations.py:588-594`).
- [x] `@accent` (shapes) and `@surface` (solids) when a palette exists, else a mid-neutral
- [ ] Keep white

**Recommendation:** derive from the palette, else a neutral grey rather than pure white.

Decision:

### B5. Canvas background
Today the background is transparent on every surface (`src/vixl/cli.py:427`, `src/vixl/mcp_tools.py:575`,
`src/vixl/project.py:92,119`), while contrast is measured over white (`src/vixl/measure.py:17-42`).
- [X] The palette `@background` for design documents; transparent for logo, icon and favicon sizes
- [ ] White
- [ ] Transparent (today)

**Recommendation:** `@background`, with transparent for marks.

Decision:

### B6. Stroke, brush and outline defaults
Today strokes are width 1 when set (`src/vixl/design_render.py:65-90`) and the brush is round, 12 px and black
(`src/vixl/brushes.py:492-495`).
- [X] Width proportional to the shape (for example 1.5% of its short side) and colour from `@ink`
- [ ] Keep them fixed

**Recommendation:** proportional width and palette colour.

Decision:

### B7. Corner radius for new rounded shapes
Today primitives use radius 0. The rolled `direction.corner` reaches layouts only (`src/vixl/variety.py:202-207`).
- [X] New rounded shapes inherit the document's corner style
- [ ] Keep primitives explicit

**Recommendation:** inherit.

Decision:

### B8. Default document size when none is given
Today CLI and MCP require a size, and Python `Project()` uses 1920×1080 (`src/vixl/project.py:92`).
- [ ] Keep a size required, with 1920×1080 for Python only
- [X] A purpose default (for example 1080×1350 for social, letter or A4 for print)

**Recommendation:** keep it required. It is an explicit choice that agents handle well.

Decision: purpose default sizes; with neither a size nor a purpose, 1080×1080 (clarified).

---

## C. Typography

### C1. Font pairing when unspecified
Today one pairing is drawn uniformly from 18 safe pairings, filtered by mood (`src/vixl/typefaces.py:213-223`,
`src/vixl/safe_catalog.py:27-36`).
- [ ] One house pairing for everything
- [ ] Rolled from the safe pool (today)
- [x] Rolled and weighted by purpose (editorial serifs for long text, UI sans for slides and forms, display faces for posters)

**Recommendation:** rolled and weighted by purpose.

Decision:

### C2. The safe pairing pool
Today there are 18 pairings, all plain serif and sans families at moderate weights.
- [ ] Keep the 18
- [x] Add 3–5 characterful but robust pairings at medium variety (for example a slab, a geometric display and a humanist serif)

**Developer Addition:** Add 4 new safe pairings, and 8 character and robust parings, and 4 much more avant-garde/unique pairings

**Recommendation:** add a few.

Decision:

### C3. Install real fonts automatically
Today new documents embed fonts only from a workspace `brand.json`. Otherwise every layout records a `font_choice`
next step and renders in the fallback font (`src/vixl/variety.py:16-24`).
- [X] At document creation, install the rolled pairing when the font cache or network is available
- [ ] Keep it opt-in

**Recommendation:** install automatically. Shipping the fallback font should be impossible by default.

Decision:

### C4. The bundled fallback font
Today the fallback is DejaVu Sans, documented as "proofing only". It has no emoji or CJK coverage.
- [ ] Keep it as a proofing-only font
- [X] Bundle a broad-coverage open font (larger package, better first renders)

**Recommendation:** keep DejaVu once C3 makes it rare. Decide separately whether to add a CJK fallback.

Decision: bundle Latin, Greek, Cyrillic and symbols coverage (for example Noto Sans plus Symbols); CJK and emoji come from the font cache on demand (clarified).

### C5. Line spacing (leading)
Today there are four conventions:
- plain text: a fixed +4 px;
- rich text: line height 1.2;
- layouts: +0.45 × size for body and +0.1 × size for headings, added to the font's own pitch (`src/vixl/layouts.py:171-172`);
- text-flow: no default.

Guidance says about 1.4 for body and 1.1 for headlines. Issue #282 reports layout leading of about 1.9×.
- [X] One rule everywhere, as a line-height multiple: body 1.45, lead 1.35, headings 1.1, display 1.0, captions 1.3
- [ ] Keep the per-feature conventions

**Recommendation:** one rule.

Decision:

### C6. Type scale and base size
Today the `type-scale` operation defaults to the perfect fourth (1.333) at base 16. Layouts derive the base from the
canvas, `short × 0.026` on screen (`src/vixl/layouts.py:84-99`), and rolls use any ratio except the augmented fourth.
- [ ] Keep the current rule
- [X] By purpose: 1.2–1.25 for UI, slides and forms; 1.333–1.5 for social; 1.5–1.618 for posters and editorial

**Recommendation:** by purpose.

Decision:

### C7. Line length
Today guidance says 45–75 characters per line, but nothing enforces it.
- [X] Layouts cap body measure at 75 characters, and a soft `review` check reports longer lines
- [ ] Guidance only

**Recommendation:** enforce in layouts and add a soft check.

Decision:

### C8. Heading weight and label case
Today heading weights are 600–800 over body 400, and layouts uppercase labels by default
(`src/vixl/layouts.py:369`).
- [X] Keep both
- [ ] Use title case for labels by default

**Recommendation:** keep the weights and uppercase labels. The uppercasing is a common taste signature, so revisit it if outputs look alike.

Decision:

### C9. Minimum text sizes
Today:
- thumbnail text must be 10 px at a 320 px thumbnail (600 for OG and X images), a warning only for social, icons and app-store (`src/vixl/checks.py:669-694`);
- "large" text for the 3:1 contrast rule starts at 24 px;
- print text must be at least 6 pt;
- deck text must be at least 18, 14 or 12 by profile.

The font principles ask for 24 px minor text on a 1080 canvas.
- [X] Reconcile on one scale-aware rule (minimum minor text ≈ 2.2% of the short side for social and posters)
- [ ] Keep the current rules

**Recommendation:** reconcile, and make the large-text threshold weight-aware (≥ 18.66 px bold counts as large, as in WCAG).

Decision:

---

## D. Colour

### D1. Palette pool breadth (the biggest sameness lever)
Today the roll draws from 20 safe palettes, all light and low-chroma (`src/vixl/safe_catalog.py:3-24`).
- [ ] Keep the 20
- [X] Add dark, saturated, duotone and earthy-rich palettes to the safe pool, each verified with the role-assignment contrast pass
- [ ] Generate palettes procedurally (OKLCH harmony around a seeded hue) with the same contrast pass

**Recommendation:** add curated dark and saturated palettes now. Consider procedural generation as a high-variety option.

Decision: Add medium and avantgarde palettes

### D2. Light/dark ratio
Today `light, light, dark`, so two thirds of rolls are light (`src/vixl/layouts.py:398`).
- [X] By purpose: documents, forms and slides mostly light; event posters, social and motion about half dark
- [ ] Keep 2/3 light

**Recommendation:** by purpose.

Decision:

### D3. Background washing
Today light-mode backgrounds with luminance below 0.6 are mixed 82% toward white, and dark-mode backgrounds are
mixed 75% toward black (`src/vixl/layouts.py:375-488`).
- [X] Reduce the mix, so saturated colour fields can be backgrounds when ink contrast holds
- [ ] Keep it

**Recommendation:** reduce it. Contrast is already enforced on ink, muted and accent text.

Decision:

### D4. Contrast targets
Today text needs 4.5:1 (3:1 for large text), and ink is nudged to 7.1:1 while muted and accent text are nudged to
4.6:1.
- [X] Keep WCAG AA as the floor and ink nudged toward AAA (today)
- [ ] AA floor without the ink nudge (allows softer ink)
- [ ] AAA floor

**Recommendation:** keep as it is.

Decision:

### D5. How the accent is used
Today the accent is rolled, but in safe compositions it is often never drawn (see the bugs below).
- [ ] Rule: one accent colour, on 1–3 elements (a call to action, a rule or a key number)
- [ ] Free

**Recommendation:** the rule. It reads as intentional.

Decision: Not free, not just one either.  It should be most likely to have one accent color, second most likely to have two, and least likely to have zero or three.  Accent colors can either be equally represented or skewed towards one color

### D6. Chart colours
Today charts take colours from the document palette first, then colour-blind-safe defaults
(`src/vixl/charts.py:34,475-486`).
- [X] Palette first (brand consistency, today)
- [ ] Colour-blind-safe first for more than two series, with the palette accent for the highlight

**Recommendation:** colour-blind-safe for more than two series.

Decision:

### D7. Diagram colours
Today diagrams use a fixed light theme that ignores the palette and dark mode (`src/vixl/diagrams.py:35,60-79`).
- [X] Follow the palette and mode, like charts
- [ ] Keep the fixed themes

**Recommendation:** follow the palette.

Decision:

### D8. The 32 legacy palettes
Today they are never picked by a roll, and `PALETTE_MOODS` describes only them (`src/vixl/typefaces.py:27-60`).
- [X] Curate the good ones into the safe pool
- [ ] Retire them
- [ ] Keep them available by name only

**Recommendation:** curate, then keep the rest available by name.

Decision:

---

## E. Spacing and layout

### E1. One spacing system
Today the spacing unit is `max(2, round(base/2))` (`src/vixl/layouts.py:99`). Margins are 5–9.5% of the short side
by density, or 7–10% when rolled. Stacks default to gap 0, chart padding is 0.8 × font size, and the text-flow gutter
is 1.5 × size.
- [X] One scale: unit = half the body size; gaps of 1, 2, 3, 4, 6 and 8 units; margins in whole units; used by layouts, stacks, charts and templates
- [ ] Keep per-feature spacing

**Recommendation:** one scale.

Decision:

### E2. Safe area when the size defines none
Today pixel sizes without a safe area get 0 (`src/vixl/sizes.py:54-57`).
- [X] 5% of the short side
- [ ] 0

**Recommendation:** 5%. Issue #370 shows layouts failing their own safe-area check, so fix both together.

Decision:

### E3. Layout pool
Today rolls draw from 15 quiet "safe compositions" (`src/vixl/layouts.py:1511-1527`). Issue #285 reports that
`mood: playful` still gives quiet results.
- [ ] Keep the 15
- [X] Add expressive layouts at medium variety (big-type, full-bleed, asymmetric, split, typographic poster), weighted by purpose

**Recommendation:** add expressive layouts.

Decision:

### E4. Density
Today the builder favours balanced (airy, balanced, balanced, dense), while rolls pick uniformly, and the rolled
density has no effect (see the bugs below).
- [x] Balanced by default, airy for documents and invitations, dense for data and price lists
- [ ] Uniform

**Recommendation:** by purpose, and make density actually change the output.

Decision: It should usually follow, but may deviate with a roll.

### E5. Default alignment
Today the default is left; each safe composition fixes its own alignment.
- [ ] Left by default; centred for invitations, emblems, covers and quotes
- [ ] Keep the current behaviour

**Recommendation:** left, with centred by purpose.

Decision: It should usually favor 75% left/25% right for design, 75% left/25% center for data.
Clarified: marks (logos, emblems, monograms, app icons) stay centred; invitations, quotes and covers follow the 75/25 rule.

### E6. Grid guides
Today only `editorial-grid` emits grid guides, although the layouts module promises them
(`src/vixl/layouts.py:9,511-517`).
- [X] Every layout emits its grid as guides (columns plus a baseline grid)
- [ ] Only where meaningful

**Recommendation:** every layout. It helps agents place additional content consistently.

Decision:

### E7. Simple templates
Today the title is 80 px and the subtitle 32 px at x=70 on every canvas (`src/vixl/resources.py:80-98`).
- [X] Make them proportional to the canvas
- [ ] Keep them fixed

**Recommendation:** proportional.

Decision:

### E8. Corner scale and button style
Today corners are sharp 0, soft 0.08, round 0.25 and pill 0.5 of the short side. "soft" is the default, and editorial
directions use sharp or soft only. Buttons are pill, rounded or square.
- [ ] Keep the scale, with soft as the house default
- [X] Default to sharp for a more editorial feel

**Recommendation:** keep it.

Decision:

---

## F. Finishing and illustration

### F1. Finishing look by default
Today rolls pick `none` or `soft-shadow` (plus subtle-grain and light-paper at medium and above) at amount 0.1
(`src/vixl/variety.py:225`), which is nearly invisible. The docs say "a flat shape reads as a draft".
- [ ] Off by default: honest flat
- [ ] Subtle but visible (amount about 0.25)
- [X] Varies by purpose (off for documents, forms, charts and logos; subtle for posters and social)

**Recommendation:** varies by purpose.

Decision:

### F2. Look amount when applied explicitly
Today the default amount is 0.5 (`src/vixl/looks.py:12`).
- [X] Keep 0.5
- [ ] Lower it

**Recommendation:** keep it.

Decision:

### F3. Styles in rolls
Today rolls pick editorial, minimalist or corporate-flat (3 of the 6 safe styles), and the style is a tag only; it
does not change the palette (`src/vixl/variety.py:113,226-227`).
- [ ] Roll all 6 safe styles, and let the style shape the palette, type and corners
- [ ] Keep the style as a tag

**Recommendation:** roll all six and let the style shape the result.

Decision: Add more safe styles, some more bold styles, and a couple avantgarde styles and roll all of them, usually safe, but not always.

### F4. Irregularity strength
Today `irregular` and `tear` default to `natural` (`src/vixl/irregular.py:362,653`), while the imperfection guidance
says "start subtle" and line-boil defaults to subtle.
- [X] subtle
- [ ] natural

**Recommendation:** subtle, to match the guidance.

Decision:

### F5. Illustration defaults
Today none are defined. These matter for the object system (#257, #379).
- [ ] Rendering: flat vector, or soft shading (one light direction, top-left)
- [ ] Outlines: none, silhouette or parts (see #379)
- [ ] Shadows: none, soft contact shadow or flat offset
- [ ] Line weight: proportional to the object (for example 1.5–2% of its height)

**Recommendation:** flat vector, silhouette outline off, a soft contact shadow, light from the top left.

Decision: Flat vector, part lines, offset shadows, thin lines, sometimmes double and triple lines, slight imprefections/variations

### F6. Background treatment
Today rolls pick flat or gradient, and split and pattern only at high variety (`src/vixl/variety.py:181-200`).
- [X] Allow split and pattern at medium for social and posters
- [ ] Keep the current behaviour

**Recommendation:** allow them at medium for social and posters.

Decision:

---

## G. Data, motion and output

### G1. Charts
Today the font size is `clamp(min(w,h)/30, 10, 40)`, the legend sits at the bottom (right for pie charts), value labels
are automatic up to 60 values, and ink is `#1f2937`. Issue #366 reports uneven automatic labels.
- [X] Keep these, and fix #366
- [ ] Change them

**Recommendation:** keep them.

Decision:

### G2. Motion
Today timelines default to 3 s at 30 fps and `animate` uses ease-in-out. Presets last 600 ms with an ease-out style,
motion recipes last 1 s, and `loop` is 0 (infinite).
- [X] House easing: ease-out for entrances, ease-in for exits, ease-in-out for loops
- [X] Short-form loops are seamless by default
- [ ] Keep the current behaviour

**Recommendation:** the house easing table, and seamless short loops.

Decision:

### G3. Export
Today exports use a white background for JPEG, PDF and flattening, and quality 90. The PNG alpha setting is
`auto` in the CLI and MCP but `keep` in Python `render.export` (`src/vixl/render.py:1410`).
- [X] Unify alpha to `auto`, and keep quality 90
- [ ] Other

**Recommendation:** unify.

Decision:

---

## H. Governance

### H1. Where the house style lives
Today the values are spread over about a dozen modules (`layouts.py`, `typefaces.py`, `variety.py`,
`safe_catalog.py`, `operations.py`, `richtext.py`, `charts.py`, `diagrams.py`, `looks.py` and others).
- [X] One data file shaped like a brand: a built-in default brand plus purpose profiles (poster, social, slides, document, form, diagram, logo, motion), which a workspace `brand.json` overrides
- [ ] Leave the values in code

**Recommendation:** one data file. The brand system already has the precedence and the checks.

Decision:

### H2. Changing defaults over time
Today documents store their rolled `design_defaults`, so existing documents keep their direction.
- [X] Changing a default affects new documents only; record it in the changelog with a way to restore the old look
- [ ] Version the house style and pin each document to a version

**Recommendation:** new documents only, with changelog notes.

Decision:

### H3. Measuring sameness and quality
Today nothing measures either.
- [X] Add an eval that rolls about 50 unspecified briefs across purposes and scores *diversity* (spread of palette, layout, mode and pairing; pairwise image similarity) and *quality* (zero `fix` findings, fonts installed, contrast)
- [ ] Rely on review only

**Recommendation:** add the eval, and gate default changes on it.

Decision:


## Decisions → issues

Each decision above is tracked in #388.

| Decisions | Issue | Title |
|---|---|---|
| H1, A1, A2 | #401 | House style as data: a built-in default brand with purpose profiles, fixed craft rules and a craft signature |
| A3 | #403 | Add a purpose tier to the defaults precedence |
| A4, A5, C2, D1, F3 | #405 | Three-tier taste pools (safe, bold, avant-garde) gated by variety level and weighted by purpose |
| B2 (developer addition) | #406 | Text stage roles (display, h1–h3, subtitle, lead, body, caption, citation, label) mapped onto 2–4 fonts |
| B3 | #408 | Default text size comes from the document's type scale |
| B4, B6, B7, E8 | #410 | Primitive defaults derive from the document direction (fills, strokes, corners) |
| B5 | #411 | Canvas background defaults to the palette background; transparent for marks |
| B8 | #413 | Purpose-based default document size, with a 1080×1080 fallback |
| C1, C6 | #414 | Font pairing and type scale weighted by purpose |
| C2 | #416 | Expand the pairing pool: +4 safe, +8 bold, +4 avant-garde pairings |
| C3 | #418 | Install the rolled font pairing automatically at document creation |
| C4 | #419 | Replace the DejaVu fallback with a bundled broad-coverage open font (Latin, Greek, Cyrillic and symbols) |
| C5 | #421 | One line-height rule everywhere (body 1.45, lead 1.35, headings 1.1, display 1.0, captions 1.3) |
| C7 | #423 | Cap body line length at 75 characters in layouts, plus a soft check |
| C9 | #424 | One scale-aware minimum text size rule, with weight-aware large text |
| D1, D8 | #426 | Palette pools: dark, saturated, duotone and earthy safe palettes; new bold and avant-garde tiers; curate the legacy palettes |
| D2 | #400 | Light/dark mode chosen by purpose |
| D3 | #402 | Reduce background washing so saturated colour fields can be backgrounds |
| D5 | #404 | Accent count distribution: one accent usually, two often, zero or three rarely |
| E1 | #407 | One spacing scale used by layouts, stacks, charts and templates |
| E2 | #409 | Default safe area of 5% for sizes that define none |
| E3, E4 | #412 | Expressive layouts at medium variety; density follows purpose but may deviate |
| E5 | #415 | Alignment distribution: design 75% left / 25% right; data 75% left / 25% centre; marks centred |
| E6 | #417 | Every layout emits its grid as guides (columns plus a baseline grid) |
| F1 | #420 | Finishing look varies by purpose (off for documents, forms, charts and logos; subtle and visible for posters and social) |
| F3 | #422 | Style pools: more safe styles, plus bold and avant-garde styles, all rollable |
| F4 | #425 | Irregularity strength defaults to subtle |
| F5 | #427 | Illustration house style: flat vector, part lines, offset shadows, thin lines (sometimes double or triple), slight imperfections |
| F6 | #428 | Split and pattern background treatments at medium variety for social and posters |
| G2 | #429 | House easing table and seamless short-form loops by default |
| H2 | #430 | Default-change policy: new documents only, changelog notes with a restore path |
| H3 | #431 | Diversity and quality eval for sparse briefs, gating changes to defaults |
| A6 | #394 (comment) | Unify document creation across surfaces |
| B1 | #283 (comment) | Text without a colour always uses the contrast pick |
| D7 | #397 (comment) | Diagrams follow the palette and mode |
| E7 | #398 (comment) | Templates proportional to the canvas |
| G1 | #366 (comment) | Keep the chart defaults; fix uneven auto labels |
| G3 | #396 (comment) | Alpha  everywhere; quality 90 |
| C8, D4, D6, F2 | none | Kept as they are: heading weights and uppercase labels, the AA contrast floor with the ink nudge, palette-first chart colours, look amount 0.5 |

---

## Bugs that hide or contradict the current defaults

These are tracked in #388. Fix them whatever the decisions above turn out to be.

- #389: The rolled `accent` is never drawn in safe compositions (`src/vixl/layouts.py:1488-1508`).
- #390: The rolled `density` has no effect, because the rolled `margin` and `type_scale` override it (`src/vixl/layouts.py:65-80`).
- #391: The roll's aspect and purpose filters never match the safe pool, and palette moods describe only the legacy palettes (`src/vixl/typefaces.py:227-241`).
- #392: `layout-apply` inherits only part of the document's `design_defaults` (`src/vixl/layouts.py:1661-1666`).
- #393: Variety levels `low` and `medium` are nearly identical, the rolled look is applied at an invisible amount, and only 3 of the 6 safe styles are ever rolled (`src/vixl/variety.py:102-119,225`).
- #394: Document creation differs by surface: CLI `vixl new` and Python don't roll `design_defaults` (`src/vixl/cli.py:423-468`).
- #395: Plain `text` ignores the document's typography and renders in the fallback font (`src/vixl/render.py:114-115`).
- #396: Python `render.export` defaults to `alpha="keep"`; the CLI and MCP default to `auto` (`src/vixl/render.py:1410`).
- #397: Diagrams ignore the palette and dark mode (`src/vixl/diagrams.py:35,60-79`).
- #398: Simple templates use fixed text sizes and positions on every canvas (`src/vixl/resources.py:80-98`).
- #399: Brief recommendations name expressive options while the attached roll is safe-only (`src/vixl/briefs.py:414-419`).

Related issues already filed: #283 (white default text), #282 (loose layout leading), #285 (playful rolls stay quiet)
and #370 (layouts fail their own safe-area check).
