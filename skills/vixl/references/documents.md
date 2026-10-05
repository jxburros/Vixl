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
`text-set --text` replaces styled text with plain text. Full syntax: `docs/rich-text.md`.

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
- Export `deck.pdf` (vector, selectable text) or `deck.pptx` (editable slides, notes);
  `pages: "1-3,intro"` picks pages; `export slide.png --pages all` writes numbered files.
  The deck's PDF pages and PPTX slides are the same size (7.5 in tall for a screen canvas, so
  1920×1080 is 13.33 × 7.5 in); `dpi` sets both. The result's `page_size` shows it.
- Name each slide's title layer `title` so it becomes the PowerPoint title placeholder.

Full reference: `docs/slides.md`.

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
- Check with `vixl_check(checks=["form"], sample="worst")`; preview with
  `vixl_render_preview(show_fields=true, values={...})`.
- Export the fillable PDF with `vixl_export_file(path="form.pdf", fillable=true)`; fill one copy
  with `values={...}` (flatten draws them in; `fill_mode="editable"` prefills fields) or many with
  `vixl_workflow("form-fill", {"data": "rows.csv", "combine": "all.pdf"})` (`combine: true` writes
  `rows-filled.pdf`; `dry_run`, `skip_invalid`; field types in `vixl_workflow_schema`).
- Filled values never touch the document; errors name rows and keys, never values.

Full reference: `docs/forms.md`.
