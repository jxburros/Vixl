# Field notes: AI literacy packet, professional documents (Vixl 0.23.0)

Slice: professional documents. Everything is rebuilt by `python explorations/11-ai-packet/documents/build.py`
from the repository root (about 78 s; parts can be built alone: `build.py deck handout form policy certificate`).
I used the Python API for building and the CLI for exports, `form fill`/`workflow form-fill` and `merge`, because the CLI
prints the export report (Python `Project.export` returns only bytes). The MCP server was not available.

## What was produced (`out/`)

| Piece | Sources | Exports |
| --- | --- | --- |
| AI 101 deck: 9 shown slides plus 1 hidden backup, 2 masters, `${page} / ${pages}`, notes on every page, native chart, flowchart, quote slide | `ai-101-deck.vixl` | `.pdf` (vector, 13.33 x 7.5 in), `.pptx` (10 slides, 1 hidden, native chart), `.html` presenter (9 slides) |
| "What is AI, really?" 2-page Letter handout: rich text, a text flow through 2 columns x 2 pages, glossary, diagram, vector QR to elementsofai.com | `what-is-ai-handout.vixl` | `what-is-ai-handout.pdf` (vector) |
| "My first AI experiment" fillable worksheet: 14 fields (text with pattern, date, editable dropdown, multiline, radio group, numbers with ranges, 3 checkboxes), explicit tab order, embedded entry font | `first-ai-experiment-form.vixl`, `form-responses.csv` | `first-ai-experiment-form.pdf` (fillable), `form-responses-filled.pdf` (3 rows) |
| "Responsible AI use at work" A4 checklist with 3 mm bleed | `responsible-ai-checklist.vixl` | `responsible-ai-checklist-cmyk.pdf` (vector, DeviceCMYK, TrimBox/BleedBox) |
| Certificate "AI Literacy — Completed", 4 names, 2-up on Letter with crop marks and slug | `certificate-template.vixl`, `certificate-names.csv`, `certificates-sheet.vixl` (live links) | `certificates-print.pdf` |

`out/_inspect/` holds the previews I looked at: contact sheets, PDF pages rendered with pypdfium2, the form field overlay.
Total output is 4.6 MB. The deck HTML is 0.97 MB of that.

Content: dates and names are checkable facts (1956 Dartmouth, 1997 Deep Blue, 2012 AlexNet, 2016 AlphaGo, 2017
Transformer paper, 2022 ChatGPT; the closing line of Turing's 1950 paper). The only chart numbers are made-up
next-word probabilities, labelled "illustrative" in the chart subtitle, in a note on the slide and in the speaker notes.
A suite rule checks that the note is there.

---

## What worked well

1. **Unknown-field errors are excellent.** `text` with `width` failed with: *"Unknown field(s) 'width' for 'text'. Allowed: align, … A
   text box's size is set with text-layout (target, width, height: text then wraps inside it), or use rich-text, which takes
   width and height"*. I fixed it on the first retry. Batches are atomic, so nothing was half-applied.
2. **Purpose-based default sizes (new in 0.23)** did the right thing: `Project.new(purpose="slides")` gave 1920x1080 (`size_from:
   purpose`), `purpose="document"`, `"form"` and `"print"` gave Letter 2550x3300 at 300 dpi with a 75 px safe area. A custom
   `width=2400, height=1500, dpi=300` got the new 5% safe area (75 px), and `creation` reported every choice.
3. **Masters plus `${page}/${pages}`** worked in render, PDF, PPTX and HTML. The hidden page is skipped in the count (1/9 … 9/9),
   it is left out of PDF and HTML, and it is a hidden slide in PPTX (`show="0"`). One edge case is wrong; see bug 6.
4. **The deck check groups master findings**: a footer problem on 9 pages is one finding with `pages: [...]`, not nine.
   `words`, `min_font` (in projected points) and `type_scale` found real problems on my first draft (68-word pages, 32 px
   timeline text = 16 pt, 13 different text sizes).
5. **Exports are honest.** Every export reported `raster_fallbacks: {}` and `content: vector`. PPTX listed
   `fonts_not_embedded` with fsType and OFL licence and the fix ("install it on the presenting machine … or share the PDF").
   PPTX `charts: {"5": [{"layer": "probs", "native": true}]}`. HTML reported `slides: 9, notes: 9`, with aria labels such as
   `Slide 5 of 9: “The cat sat on the …”`.
6. **PPTX fidelity is high once the fonts are installed.** I copied the cached Lexend and Atkinson TTFs into `~/.fonts` and converted
   the PPTX to PDF with LibreOffice. The slides match the Vixl render apart from the native chart's own label layout (see below).
   Without the fonts, LibreOffice substituted faces: the curly quote mark became a straight one, and one list overflowed its card.
7. **Forms are the strongest part.** Fillable PDF fields carry real actions (`AFDate_KeystrokeEx("mm/dd/yyyy")`,
   `AFNumber_Keystroke`, a pattern-validate script). `"Full name *"` became the tooltip "Full name". The catalog has `/Lang en-US`
   and a title. `entry_font: "embed"` embedded Atkinson Hyperlegible Next for typing. `check --checks form --sample worst` was
   clean, and `render --show-fields` showed keys and tab numbers. The CSV dry run named rows and keys, never values:
   `Row 1, team_code: The value does not match the field's pattern`, `Row 2, rating: The number is outside the allowed range`,
   `Row 3, full_name: This required field is empty`. An editable dropdown accepted "Bard", as designed.
8. **`merge-impose` worked first time.** It placed 4 rows 2-up on Letter with crop marks and a slug. The dry run's `layout` (grid,
   origin, margins in inches) was useful to read before printing. `text-layout fit` shrank "Dr. Oluwaseun Adebayo-Whitfield" to fit
   the name box. The `${cohort|default:Open cohort}` filter and `constrain right` alignment worked per copy, and the sheet `.vixl`
   is only 1.9 KB of links.
9. **CMYK PDF is vector.** The page content has 96 `k`/`K` operators and 0 `rg`. TrimBox is exactly A4 (595.3 x 841.9 pt) inside the
   bleed MediaBox, and the text stays selectable. `check --checks print` was clean.
10. **QR codes are one vector path in every export**, and the `codes` check passes without being asked for.
11. **Text flow reporting** (`frames[].chars`, `remaining_chars`, `overflow`) made it easy to size the page-2 frame.
12. **Charts:** horizontal bar with `number_format: "0%"` and `colors: ["@accent"]`. A bar chart in one operation, native in PowerPoint.
13. Speed of edits: building a whole 10-slide deck is 0.5–0.6 s; each export about 1 s.

---

## Bugs and wrong results (with repros)

### 1. `vixl compact` changes the design: it drops the bold/italic fonts that rich text resolves automatically
Rich text in `font: "body"` (= `atkinson-hyperlegible-next-400`) correctly draws `**bold**` with the installed
`atkinson-hyperlegible-next-700` and `*italic*` with `…-400-italic` (a render identical to giving `font_variants` explicitly).
But the `fonts` check lists those two fonts as *"registered but unused"*, and `vixl compact` deletes them. Its result says
*"the current design is unchanged"*, but after it the bold is synthetic (wider, heavier) and the italic is a slanted roman. Before and after differ:
`ImageChops.difference(...).getbbox() == (54, 70, 812, 132)`.
```python
p = Project.new(purpose="slides", seed=101, workspace_fonts=False)
pair_fonts(p, "lexend-atkinson"); install_font(p, "Atkinson Hyperlegible Next", 700)
install_font(p, "Atkinson Hyperlegible Next", 400, italic=True)
p.apply([{"type": "rich-text", "name": "t", "markdown": "**Bold words** and *italic*", "size": 80, "font": "body", "x": 50, "y": 50}])
p.save("boldtest.vixl"); p.export("before.png")
# $ vixl -p boldtest.vixl compact && vixl -p boldtest.vixl render --out after.png   -> bold/italic change
```
Workaround: pass `font_variants` explicitly. The check then counts the fonts as used. Every document in this packet carries the
false "unused" message (informational).

### 2. A text flow given Markdown sets about 2x leading (the 0.23 line-height table is not applied)
The same paragraph at 44 px has these baseline pitches:

| how | pitch |
| --- | --- |
| `rich-text` (markdown) | 63.8 px (1.45x) |
| `text-flow` with `text` (plain) | 64.2 px |
| `text-flow` with `markdown` | **87.3 px** (1.98x); the frame's rich record has `line_height: 1.45` but no `line_basis`, plus `spacing: 13` |
| `text-flow` markdown + `line_height: 1.45` | 87.3 px (no effect) |
| `text-flow` markdown + `spacing: 0` | 61.5 px |
| `text-flow` markdown + `line_height: 1.06` | 49.3 px (and `spacing` becomes -5) |

The changelog says flows use the line-height table (body 1.45). With Markdown they seem to use the pre-0.23 rule (1.2 x natural pitch
x line_height) plus a pixel spacing. My first handout draft looked double-spaced. Workaround: `"spacing": 2` (about 1.45x). The
semantics of `spacing` and `line_height` on a rich flow are hard to predict.

### 3. Text flow with Markdown and `paragraph_spacing > 0` overfills its frames
The flow puts more text into a frame than the frame holds, and the `bounds` check then fails on the flow's own frame:
`'article-3' does not fit its 1013×700 text box at 44 px and is cut off (it needs 1009×709)`. I ran the handout article in a
2-column frame at heights 600–754 px (step 7):

| story | `paragraph_spacing` | heights that overfill |
| --- | --- | --- |
| markdown | 0 | 0/23 |
| markdown | 18 | **10/23** |
| plain | 0 | 0/23 |

The docs say a slice is measured "the measure the bounds check uses", so the two should agree. Workaround: `paragraph_spacing: 0`.

### 4. `space_before` on a flow paragraph also applies at the top of a column
`text-flow action=style paragraphs=[2,4,…] format={space_before: 26}` (to open up the headings) also pushed a heading down when it
started a column or page. That column's first line then sat about 26 px below its neighbour's. Typesetters drop space-before at a
frame top. I removed it, so the headings stay tight.

### 5. Chart value-axis ticks collapse to one tick when `max` and a large `font_size` are set
In a `horizontal-bar` 1002 x 580 with values 0.05–0.41 and `number_format: "0%"`:

| options | scale |
| --- | --- |
| `font_size` 24–28, any `max` | step 0.1, ticks 0–50% |
| `font_size` 30–38, `max: 0.5` | step 0.2, ticks 0/20/40% |
| `font_size` 34–40, no `max` | step 0.5, ticks [0, 0.5] |
| **`font_size: 40`, `max: 0.5`** | **step 5.0, ticks [0.0]**: the axis shows only "0%" and no gridlines |
| **integers 41,18,… with `max: 50`, `font_size: 40`** | **step 500, ticks [0]** |
| `max: 0.6`, `font_size: 42` | ticks [0, 0.5] (the 0.6 end is unlabelled) |

A step larger than the whole range is clearly a bug in the tick-thinning step search. Thinning is also aggressive: six short labels
("0%"…"50%") at 40 px fit easily on a ~700 px axis. I used `font_size: 42` with no `max` (axis 0% and 50%).

### 6. A trailing hidden page shows a number past the page count
With pages a, b, c(hidden), d(hidden) and `${page} / ${pages}` on the master, the hidden pages read **"3 / 2"** in the render and
in the PPTX hidden slides. My deck's hidden backup slide reads "10 / 9". The docs say a hidden page "shows the number the next shown page
has". When no shown page follows, it should probably show the last shown number, or nothing.

### 7. Diagram labels wrap at a fixed width that ignores the label size and the node size
- At `size: 44` the handout diagram broke **"parameters" mid-word** ("paramete / rs") and "Huge set / of / examples".
- At `size: 40` on a slide, "Score every possible next token" wrapped to 4 lines and the text touched the box edges.
- Explicit `\n` in a label is ignored. A node `size: [320, 200]` makes a bigger box but the label still wraps at the same width.
- The workaround is unintuitive: ask for a **smaller** `size` (30) so more words fit per line, and let `fit: contain` scale the
  whole diagram up (scale 1.08, labels 36 px). The docs mention "Labels longer than about 170 px wrap", but not that the
  limit is in unscaled pixels and applies at any font size.
- "Finished?" wrapped as "Finished / ?", with the question mark alone on the second line of the diamond.

### 8. Swimlane diagram overruns its area and draws an ungrouped node outside every lane
`diagram lanes: true direction: LR width: 1980` returned `size: [2065, 340]`, wider than the area it was asked to fit with `fit:
contain`. The node with no `group` (the shared "Trained model") was drawn below both lanes. Clusters (`lanes` off) gave the
check warning *"Group 'use' … covers node 'adjust', which is not a member"*. I dropped the groups and explained the two rows in a caption.

### 9. `palette-apply` does not recolour the canvas
After `palette-define` + `palette-apply roles={background: "#f6f4ee", …}`, the canvas kept the rolled colour (`#d8dee9`), and
every slide master needed `background: "@background"`. I added `{"type": "canvas", "background": "@background"}`. A fresh
`Project.new(purpose=…)` also has a palette-coloured canvas but **no role swatches**, so a diagram made straight away gets the
`light` theme, not the documented `palette` theme.

---

## Confusing, poorly documented, or many retries

- **`diagram` schema text is stale.** `theme` says *"Colors: light (default), dark or mono"*, but docs/diagrams.md and the changelog say
  `palette` is the default in 0.23 and is a fourth value.
- **Slide safe area vs footers.** The slide size has a 96 px safe area, so a conventional footer and page number at y = 1012 are
  `fix` errors (`'page-number' extends outside the safe area`). The deck check exempts footer-named layers from `min_font` but not
  from `safe_area`. I moved the footer up to y = 940.
- **`type-scale` vs the deck `min_font`.** `type-scale base 40 ratio 1.25` makes `caption` 32 px, and the deck check then flags every
  32 px label as 16 pt (< 18 pt). Explicit chart `font_size` and diagram label sizes are not snapped to the scale, so the
  `type_scale` review always lists 31/36/42 px from them.
- **`title_position` flags a deliberate layout.** The quote slide's `title` (the quote, set lower on the dark master) gets *"sits
  at y 350 where the other titles sit at 330"*. Reasonable as a review, but it fires on every intentional variation.
- **`overlap` reviews are mostly noise.** Text inside its own card is reported as *"'light-red-card' and 'light-red-text' overlap
  by 22198 px (99.7%)"*. The one time it mattered (text running past the card bottom), the message did not say so.
- **The chart's value labels are smaller than asked.** At `font_size: 42` the value labels are 32 px (0.85x, then shrunk to fit),
  which fails the deck `min_font` (6 reviews). `value_labels: true` does not change their size.
- **`vixl form --help`** shows only `{settings}` and *"(form fill is a document command)"*, but `vixl form fill --help` exists and
  is what docs/forms.md uses.
- **The form-fill validation message ignores the field's own `message`.** The PDF viewer gets "Two capital letters, a hyphen and
  three digits, e.g. OP-114", but a fill reports the generic "The value does not match the field's pattern".
- **Text `tracking` exists only on rich-text spans.** Plain `text` has no letter-spacing field, so tracked uppercase eyebrows need
  `rich-text` with `[TEXT]{tracking=3}`.
- **Python `inspect(target)` cannot see layers on other pages** (`Layer 't' does not exist` until `page select`). I needed
  `resolved_bounds` (not `bounds`) to size panels to their text.
- **Creation installs the rolled pairing even when you pick your own next.** That is about 300 KB of unused embedded fonts per document.
  `Project.new` has no `font_pairing` (compose has). `workspace_fonts=False` avoids it.
- **The rolled background for `purpose="document"` was peach `#ffd6a5`** (seed 202). A strong colour for a print handout; I overrode it.
- **The suites are per active page.** The built-in `slide-deck` starter suite is a single rule wrapping `check deck`. For per-slide
  rules I cloned the project and ran `page select` + `check_suite` for each page.
- **Python `Project.export` returns bytes**, with no `raster_fallbacks`, `warnings` or `fonts_not_embedded`. I shelled out to
  `vixl export` to see the report.
- **The merge report's `variables.defaults`** listed every variable (`["cohort","date","name"]`) even though the CSV supplied all
  of them. I could not tell what it means.
- **PDF text order:** extracted text starts with the master's footer ("AI literacy packet · … Page 1 of 2") before the page's
  title, because master layers are drawn first. That may matter for screen-reader order in the PDFs (the HTML presenter handles
  it: masters are excluded from its hidden text).

## Export differences (PDF / PPTX / HTML)

- **PDF** (pypdfium2 render) matched the Vixl render exactly; text is selectable.
- **PPTX in LibreOffice, fonts installed:** the native chart dropped every other category label (floor, bed, "anything else"), from
  LibreOffice's own auto layout at 42 px. Headings look slightly heavier: Lexend SemiBold is referenced as family "Lexend" plus a
  bold flag, I believe. Everything else matched. **Without the fonts:** a font fallback changed the line breaks and the quote glyph,
  as the export warning predicted.
- **HTML presenter:** I could not view it (no browser in the container, and LibreOffice would not convert the extracted SVGs). I
  verified it structurally instead: 9 `<section class="slide">` with inline SVG, aria labels from the `title` layers, hidden
  backup slide absent, notes present, 0.97 MB.
- **CMYK:** the accent blue `#2f55c9` and the amber print noticeably duller through the GCR approximation with no ICC profile
  (expected and documented). Nothing in `check --checks print` points it out. A soft proof (`render --proof`) is the way to see it.

## Slow steps (this container)

| Step | Time |
| --- | --- |
| `check --checks deck` (9 shown pages) | 7–9 s |
| `check` on a 2-page Letter handout | 5–7 s |
| `check --checks form --sample worst` | 4–6 s |
| `check --checks print` (A4 + bleed) | 5.5–7 s |
| `merge` with `--check design` (4 copies) | **10–12 s** (dry run alone 9–10 s); without `--check design` 0.5 s |
| All exports | 0.7–1.1 s each |
| Whole build | 78 s, about 55 s of it in checks |

## Features I looked at but did not use

- **`layout-apply` / `roll` / `compose`**: I wanted one controlled brand across five documents (one palette, the lexend-atkinson
  pairing), and the rolled directions differed per document (Inter, Libre Franklin/Baskerville, peach backgrounds). Hand
  layout with a shared palette was more predictable.
- **`look` finishes**: the house style says none for documents and slides, and I agree for this content.
- **Signature fields, `comb`, `--mode editable` prefills**: a worksheet does not need them. I tested the pattern, date, number range,
  editable dropdown, radio and checkbox kinds.
- **Proof page workflow and `vixl diff`**: they would suit a review hand-off. I compared PNGs with Pillow instead.
- **The `vixl_*` MCP tools**: not available in this session.
- **The `stack` auto-layout** for the checklist columns: fixed offsets were enough for a one-pager.
