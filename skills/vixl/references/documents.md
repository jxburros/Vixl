# Rich text, pages and decks, forms

## Rich text

One text layer can mix bold, italic, colour, size, underline, highlight, super/subscript and
bullet or numbered lists. Write Markdown, then restyle parts:

```json
{"type": "rich-text", "name": "body", "markdown": "Revenue grew **42%** to [$1.2M]{color=#d33}\n- Faster *checkout*\n- New markets\n  - Brazil", "size": 28, "width": 900, "x": 80, "y": 120}
{"type": "text-style", "target": "body", "match": "42%", "color": "@accent", "bold": true}
{"type": "text-style", "target": "body", "paragraphs": [1, 2], "space_after": 8}
```

Bold/italic use installed variants (`font install Inter --weight 700`) or are synthesized.
`text-set` changes the whole layer (text, color, size, font); `text-style` styles parts of it. `text-set --text`
on a rich layer keeps bullets, spacing and span styles where the structure still applies and lists what it
dropped under `warnings`; `rich-text --target` rebuilds formatted content. Full syntax: `docs/rich-text.md`.

## Pages, masters and decks

A document becomes multi-page with the first `page add`; each page has its own layers, the rest
(canvas, fonts, swatches, guides) is shared. Masters draw underneath the pages that use them.

```json
{"type": "master", "action": "add", "name": "std", "background": "#f6f4ef"}
{"type": "text", "text": "${page} / ${pages}", "name": "num", "size": 24, "x": 1780, "y": 1010}
{"type": "page", "action": "add", "name": "results", "master": "std", "notes": "Speaker notes"}
{"type": "text", "text": "Results", "name": "title", "size": 80, "page": "results"}
```

- Any operation takes `"page"` (name or number) to edit that page; `page select` switches.
- Preview every page at once: `vixl_render_preview(page="all")` / `render --page all`.
- `vixl_check(checks=["deck"])` checks every page plus title placement, type scale, words per
  page, projected type size (points) and speaker notes.
- Export `deck.pdf` (vector, selectable text), `deck.pptx` (editable slides, notes; a `chart` becomes a native chart with its data table, see [charts](charts.md)) or `deck.html`
  (a self-contained presentation: keyboard/swipe/`#3` navigation, overview, the pages'
  transitions, speaker view with notes and timer on `S`, print one slide per page);
  `pages: "1-3,intro"` picks pages; `export slide.png --pages all` writes numbered files.
  HTML options (`presenter={"theme": "dark|light|auto", "slide_images": "svg|png", "notes": false,
  "start": 3}`; CLI `--presenter-theme --slide-images --no-notes --start-slide`). Notes are inside
  the file, so pass `notes: false` for a copy to share; `presenter: false` gives a single image.
  Details: `docs/presenter.md`.
  A PPTX does not embed fonts: its `warnings` name each font to install where the deck is shown
  (or send the PDF, which embeds them).
  The deck's PDF pages and PPTX slides are the same size (7.5 in tall for a screen canvas, so
  1920×1080 is 13.33 × 7.5 in); `dpi` sets both. The result's `page_size` shows it.
- Name each slide's title layer `title` so it becomes the PowerPoint title placeholder.

Full reference: `docs/slides.md` (HTML presentations: `docs/presenter.md`).

## Forms

Fields are layers: `field` (kinds `text`, `multiline`, `number`, `date`, `checkbox`, `radio`,
`dropdown`, `signature`), `field-set`, and `form` for tab order, title and language. Start from a
paper size (`letter`, `a4`).

```json
{"type": "field", "name": "full_name", "kind": "text", "label_layer": "name-label", "required": true, "max_length": 80, "x": 225, "y": 580, "width": 2100, "height": 125}
{"type": "field", "name": "plan-annual", "key": "plan", "kind": "radio", "option": "annual", "label": "Annual", "group_label": "Membership plan", "x": 225, "y": 1100, "width": 60, "height": 60}
```

Rules agents trip over:

- Every field needs `label` or `label_layer` (its accessible name); radio groups share `key`,
  each button has its own `option`, and one button sets `group_label`.
- Keys are 1–64 of `[A-Za-z0-9_-]` (no dots) and cannot equal a variable name.
- Fields cannot be rotated or flipped.
- `required` works on every kind (a required `signature` is signed in the viewer; fills never need
  it). `max_length` works on `text`, `multiline` and `number`.
- Validation rules reach the fillable PDF as standard field actions a viewer enforces: `format`
  `email`/`digits`, number `{decimals, min, max}`, the date `format.display`, and `pattern` (a
  regex the whole value must match; no flags, look-around, back-references or `(a+)+`), with
  `message` for the text a viewer shows. Pages with fields get `/Tabs /S`.
- Check with `vixl_check(checks=["form"], sample="worst")`; each overflow says what it measured
  (`measured`: sample, font, sizes, box and rendered width) and the `max_length_that_fits` to set.
  Preview with `vixl_render_preview(show_fields=true, values={...})`; it draws values exactly as
  the filled export does.
- Export the fillable PDF with `vixl_export_file(path="form.pdf", fillable=true)`; fill one copy
  with `values={...}` (flatten draws them in; `fill_mode="editable"` prefills fields) or many with
  `vixl_workflow("form-fill", {"data": "rows.csv", "combine": "all.pdf"})` (`combine: true` writes
  `rows-filled.pdf`; `dry_run`, `skip_invalid`; field types in `vixl_workflow_schema`).
- Filled values never touch the document; errors name rows and keys, never values.

Full reference: `docs/forms.md`.
