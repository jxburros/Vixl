# Forms

![Registration form generated from real field layers](assets/generated/registration.png)

Start with the [forms and decks tutorial](tutorials/forms-and-decks.md), or try the
[editable master](assets/generated/registration.vixl) and
[fillable PDF](assets/generated/registration.pdf). This reference explains all field settings.

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

A form is a page with named places where someone writes. In Vixl those places are **field
layers**: they move, align, group and check like any other layer, and one document produces both
the blank **fillable PDF** (fill it in Acrobat, a browser, Preview or a phone) and any number of
**filled copies** from JSON values or CSV rows, as PDF, PNG, JPEG, TIFF or SVG.

```json
[
  {"type": "canvas", "size": "letter"},
  {"type": "text", "name": "title", "text": "Event registration", "x": 225, "y": 225, "size": 96},
  {"type": "text", "name": "name-label", "text": "Full name", "x": 225, "y": 520, "size": 42},
  {"type": "field", "name": "full_name", "kind": "text", "label_layer": "name-label",
   "x": 225, "y": 580, "width": 2100, "height": 125, "required": true, "max_length": 80},
  {"type": "field", "name": "email", "kind": "text", "format": "email", "label": "Email address",
   "x": 225, "y": 840, "width": 2100, "height": 125, "required": true},
  {"type": "field", "name": "plan-annual", "key": "plan", "kind": "radio", "option": "annual",
   "label": "Annual", "group_label": "Membership plan", "x": 225, "y": 1100, "width": 60, "height": 60},
  {"type": "field", "name": "plan-monthly", "key": "plan", "kind": "radio", "option": "monthly",
   "label": "Monthly", "x": 225, "y": 1200, "width": 60, "height": 60},
  {"type": "field", "name": "newsletter", "kind": "checkbox", "label": "Send me the newsletter",
   "x": 225, "y": 1400, "width": 60, "height": 60},
  {"type": "field", "name": "signature", "kind": "signature", "label": "Signature",
   "x": 225, "y": 2900, "width": 1200, "height": 160}
]
```

```bash
vixl check --checks form --sample worst      # also fills every field with worst-case values
vixl render --out preview.png --show-fields  # outlines, keys and tab numbers over the page
vixl export registration.pdf --fillable      # the blank fillable PDF

vixl form fill --set full_name='Ada Lovelace' --set email=ada@example.com --set plan=annual \
  --set newsletter=yes --out ada.pdf
vixl form fill --data attendees.csv --dry-run                        # validate every row, write nothing
vixl form fill --data attendees.csv --out filled/ --name '{full_name}-{row}'
vixl form fill --data attendees.csv --combine attendees.pdf          # one PDF, a page per row
```

Start from a paper size (`letter`, `a4` …): fields need a physical size to become PDF fields of
the right size. Letter at 300 dpi is 2550 × 3300 px, so 125 px is 30 pt.

## Field kinds

| Kind | Typed as | Value |
| --- | --- | --- |
| `text` | a single line | text (`format`: `email` or `digits`; `max_length`; `comb` for one character per cell, as for postal codes) |
| `multiline` | wrapped lines | text |
| `number` | a single line | a number (`format`: `{decimals, min, max}`) |
| `date` | a single line | `YYYY-MM-DD`, drawn with `format.display` tokens `YYYY`, `MM`, `M`, `DD`, `D` |
| `checkbox` | a box to tick | `yes`/`no`, `true`/`false`, `1`/`0`, `x` (exported as `on_value`, default `Yes`) |
| `radio` | one of a group | buttons share a `key`; each has its own `option`; the value is the chosen option |
| `dropdown` | a list | one of `options` (strings or `{value, label}`); `editable` allows other values |
| `signature` | an empty box | none — a viewer can sign it |

Aliases: `input` and `form-field` are `field`; kinds `textbox` → `text`, `textarea` →
`multiline`, `select`/`combo` → `dropdown`, `tickbox` → `checkbox`.

## Settings

| Setting | Meaning |
| --- | --- |
| `key` | Data key and PDF field name: 1–64 letters, digits, `_` or `-`, no dots. Defaults to the layer name. Unique, except that radio buttons of one group share it. It cannot also be a variable name. |
| `label` / `label_layer` | The accessible name (the PDF tooltip a screen reader announces): text, or a text layer whose text names the field. Every field needs one. For a radio button, the option's own label. |
| `group_label` | A radio group's question. |
| `required`, `read_only` | PDF Required and ReadOnly flags. Filling rejects an empty required field. |
| `default` | The initial value, validated like any value. Radio groups set it on one button. |
| `max_length`, `comb`, `format`, `options`, `editable`, `option`, `on_value` | As above. |
| `tab` | Position in the tab order when the form uses explicit order. |
| `overflow` | When a value does not fit: `shrink` (default, down to `min_size`, never breaking a word), `clip`, or `error`. |
| `font`, `size`, `color`, `align`, `padding` | How values are drawn (as on text layers). |
| `appearance` | The box drawn into the artwork: `style` (`box`, `underline`, `none`), `fill`, `stroke`, `stroke_width`, `radius`, `mark` (`check`, `cross`, `dot`) and `mark_color`. A top-level `fill` or `stroke` on the operation goes here. |

`field-set` changes any of these on an existing field (`target` plus settings). `form` sets the
document's `tab_order` (`reading` or `explicit`), `title` and `lang` (written to the PDF).
Fields cannot be rotated or flipped (PDF fields are upright rectangles); duplicating a field
gives the copy a new key (`email-2`), or a radio button a new option in the same group; removing
a field's label layer clears `label_layer`. Fields cannot be inside repeats or symbols, nor on
master pages. A document holds up to 500 fields.

## The fillable PDF

`export form.pdf --fillable` (Python `project.export("form.pdf", fillable=True)`, MCP
`vixl_export_file(fillable=true)`) writes Vixl's page artwork — vector, with selectable text —
with a transparent PDF field over each field layer, so the PDF looks exactly like the preview.

- Text kinds are text fields, checkboxes and radio groups are buttons, dropdowns are combo boxes
  and signatures are signature fields; defaults are set and drawn.
- Every widget has a generated appearance, so viewers show it as designed and never ask to save
  on close. People type in Helvetica (Western European characters); values Vixl draws itself
  (defaults, flattened fills) use the field's own font.
- Tab order is the order of the page's fields: **reading** order sorts fields into rows by their
  vertical centre (two fields share a row when their centres are within half the smaller
  field's height), top to bottom, left to right, with a radio group as one stop; **explicit**
  order follows `tab`. `render --show-fields` draws the numbers.
- The catalog carries the title and language and asks viewers to show the title.
- The file contains no actions, JavaScript or links, every string is hex-encoded, and the same
  document always produces the same bytes. Multi-page documents ([pages](slides.md)) get fields
  on every page.

Viewers can add their own field highlight; that is a viewer preference. Fillable PDFs are RGB.

## Filling

`form fill` (Python `vixl.forms.fill(project, values, path)` and `fill_data(project, csv,
directory, …)`, MCP `vixl_export_file(values=…)` or the `form-fill` workflow) never changes the
document: each copy renders from a throwaway copy, and **filled values never reach the render
cache**, the document, its history or error messages (which name rows and keys, never values).

- Each input key names a field or a document variable; anything else is an `unknown_key` error
  (`--unknown ignore` to allow extra CSV columns). Every field's current value is also a
  `${key}` variable, so "This certifies that ${full_name}" follows the field.
- Every row is validated before anything renders. Errors are `{row, key, code, message}` with
  codes `missing_required`, `unknown_key`, `invalid_option`, `invalid_number`, `invalid_date`,
  `too_long`, `invalid_format` and `overflow`. One bad row fails the batch unless
  `--skip-invalid`; `--dry-run` only validates. `--check design` also runs the design checks per
  row.
- `--out DIR --name '{column}-{row}'` writes one file per row (names are sanitized, collisions
  are errors, existing files are never overwritten); `--combine FILE.pdf` writes one PDF with a
  page per row (up to 1,000 rows). `--format` picks PDF (default), PNG, JPEG, WebP, TIFF or SVG.
- `--mode editable` writes fillable PDFs with the values already set (prefilled, still
  editable); values must then be Western European characters.
- Big batches can run as durable jobs: submit `{"kind": "form-fill", "source": "form.vixl",
  "output": "filled.zip" or "all.pdf", "request": {"data": "rows.csv", …}}`. The job freezes the
  form and the data, and deletes its copy of the data when it completes or is cancelled (unless
  `retain_inputs`).

Previews show values too: `render --set KEY=VALUE` and `vixl_render_preview(values=…)` draw the
values you pass without requiring the rest.

## Checks

`form` is one of the default checks and does nothing without fields. **Errors:** radio groups
with fewer than two options, an incomplete or repeated explicit tab order, rotated or flipped
fields, fields off the page or across the trim line, overlapping fields, a missing accessible name
(or radio group question), and defaults or options Helvetica cannot show. **Warnings:** boxes too
small for their text, checkboxes under 10 pt, values under 8 pt, a border or underline below 3:1
contrast with its surroundings (sampled from one render without the fields), `style: none` with
nothing drawn under it, a label layer far from its field, an explicit tab order that jumps back up
the page, layers drawn above a field, fields with opacity, blend modes or effects, text layers
showing a field value (they stay static in the fillable PDF), a canvas with no physical size, and
radio option values that are not words.

`--sample worst` fills every field with worst-case values (`max_length` W's, the longest option,
the largest number) and reports values that would not fit; `--sample rows.csv` uses real rows.

`inspect`, `field list` and `vixl_document_inspect` list each field's key, kind, required flag,
tab stop and rectangle in PDF points.
