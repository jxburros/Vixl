# Design: fillable forms and form filling

| | |
| --- | --- |
| **Status** | Proposal. Nothing described here exists in Vixl 0.17.0. |
| **Scope** | (1) Designing a form that exports as a fillable PDF. (2) Filling a Vixl-designed form with data and exporting flattened copies. |
| **Not in scope** | Filling or importing PDF forms that Vixl did not create. See [non-goals](#2-goals-and-non-goals). |
| **Date** | 2026-10-05 |

## 1. Summary

A Vixl document is a fixed-layout page made of positioned layers. A paper form is the same
thing plus named places where someone writes. This proposal adds one layer type, `field`,
and builds two features on it:

1. **Fillable PDF export.** A document with fields exports as a PDF whose fields can be
   filled in Acrobat, browsers, Preview and mobile viewers.
2. **Filling.** The same document renders with values filled in and the fields flattened
   into the artwork: one copy from a JSON object, or hundreds from a CSV file, to
   PNG/JPEG/TIFF/PDF.

One source document produces both the blank fillable form and every filled copy.

The design follows rules the rest of Vixl already keeps:

- Every change is a structured operation, validated before it is committed.
- The PNG preview is the truth. What an agent sees in `vixl_render_preview` is what the PDF
  shows.
- Agents cannot look at a PDF viewer, so checks must catch what a person would notice.
- Output is deterministic and contains no executable content.

## 2. Goals and non-goals

**Goals**

- Field kinds that cover most paper forms: single-line text, multiline text, number, date,
  checkbox, radio group, dropdown and an empty signature box.
- Fields that move, align, constrain and group like any other layer.
- A fillable PDF with generated appearances, an accessible name on every field and a
  predictable tab order, behaving the same across the common viewers ([§11](#11-testing)).
- Filling with validation. Required fields, allowed options, types, length limits and
  overflow are reported per row before any output is written.
- Batch filling from CSV to one file per row, or to a single combined PDF.
- A `form` check family.

**Non-goals**

- Filling, editing or importing fields from PDF forms Vixl did not create. PDF import stays
  a raster import (`src/vixl/imports.py:277`).
- PDF JavaScript: calculated fields, format and keystroke actions, show/hide logic.
- Submit, reset, URI or any other PDF action. Vixl PDFs contain no actions at all.
- Digital signing. A signature field is an empty box a viewer can sign.
- XFA forms, list boxes, file-attachment fields, button/image fields and rich-text fields.
- Interactive HTML forms. HTML and SVG exports show fields as static artwork.
- Full PDF/UA tagging. The baseline is an accessible name on every field, a document title
  and language, and a deliberate tab order ([§6.6](#66-tab-order-and-accessibility)).
- Multi-page forms before Vixl has a pages model ([open question 3](#13-open-questions)).

## 3. Background: what exists today

| Need | Today |
| --- | --- |
| Paper sizes with physical units | `letter`, `a4` and other print sizes store dpi, bleed and safe area (`src/vixl/sizes.py:37`, `apply_size` at `:384`). |
| Positioning, alignment, constraints, groups | Ordinary layer operations. |
| Each layer's bounds in canvas space, through group transforms | `check_design` already projects them (`src/vixl/checks.py:61`). |
| Shaped text in any embedded font, fitted to a box | `text.plan` (`src/vixl/text.py:265`). Fitting has known bugs ([§10](#10-implementation-plan), Phase 0). |
| Render-time values that never touch the document | Variables (`${name}`) are substituted in `resolved_layers` (`src/vixl/render.py:211`) on a copy of the state. |
| CSV batch rendering | `render_data` (`src/vixl/exports.py:41`): 10,000 rows, 8 MiB, staged publishing, per-row checks. PNG only. |
| PDF export | Pillow writes one raster page (`src/vixl/render.py:898`). Vixl has no PDF writer of its own and no PDF-writing dependency. |

Today an agent can approximate filling with text layers that contain `${name}` and
`render --data`. It cannot validate values (required, allowed options, types), draw a
checked box or a selected radio button, detect a value overflowing its box, or produce the
blank fillable version from the same document. Fillable PDFs are impossible today because
nothing writes PDF fields.

## 4. Walkthrough

Design a registration form as one atomic batch. Letter at its default 300 dpi is
2550 × 3300 px, so 125 px is about 30 pt. The visible labels for the radio and checkbox
options are left out to keep the example short.

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

Check it, look at it, export the blank fillable PDF:

```bash
vixl check --checks form --sample worst      # also fills every field with worst-case values
vixl render --out preview.png --show-fields  # outlines, keys and tab numbers drawn over the page
vixl export registration.pdf --fillable
```

Fill it:

```bash
vixl form fill --set full_name='Ada Lovelace' --set email=ada@example.com \
  --set plan=annual --set newsletter=yes --out ada.pdf
vixl form fill --data attendees.csv --dry-run                      # validate every row, write nothing
vixl form fill --data attendees.csv --out filled/ --name '{full_name}-{row}'
vixl form fill --data attendees.csv --combine attendees.pdf        # one PDF, one page per row
```

## 5. Field layers

### 5.1 Why fields are layers

Fields are layers with `type: "field"`, not entries in a separate registry. Move, align,
distribute, constrain, group, layouts, measurement and checks already work on layers, and
z-order and visibility already mean the right thing. A registry would duplicate geometry and
lose all of those tools.

### 5.2 Stored shape

```json
{
  "id": "lyr_…", "name": "full_name", "type": "field",
  "x": 225, "y": 580, "width": 2100, "height": 125, "rotation": 0,
  "field": {
    "key": "full_name", "kind": "text", "label_layer": "lyr_…",
    "required": true, "read_only": false, "default": "", "max_length": 80,
    "overflow": "shrink", "min_size": 30
  },
  "font": "fonts/…", "font_role": "body", "size": 42, "color": "@ink", "align": "left", "padding": 16,
  "appearance": {"style": "box", "fill": "@surface", "stroke": "@muted", "stroke_width": 3, "radius": 8}
}
```

The other common layer fields (`opacity`, `visible`, `constraints`, `parent` and so on) are
present as on every layer.

### 5.3 Field settings

| Setting | Kinds | Meaning |
| --- | --- | --- |
| `key` | all | Data key and PDF field name. Uses the variable-name rule (`[\w-]`, 1–64 characters) and allows no dots, because PDF uses dots for field hierarchy. Defaults to the layer name. Radio buttons in one group share a key. |
| `kind` | all | `text`, `multiline`, `number`, `date`, `checkbox`, `radio`, `dropdown`, `signature`. |
| `label` | all | Accessible name, written as the PDF field tooltip (`/TU`). For a radio button, the option's own label. At most 500 characters. |
| `label_layer` | all | A text layer whose resolved text is the label. A field needs `label` or `label_layer`. |
| `group_label` | radio | Accessible name for the whole group (the question). At least one button in a group sets it; any that set it must agree. |
| `required` | all but signature | PDF Required flag. Filling rejects empty values. |
| `read_only` | all | PDF ReadOnly flag. Mainly useful with prefilled PDFs ([§7.6](#76-prefilled-editable-pdfs-later-phase)). |
| `default` | all but signature | Initial value. It must pass the same validation as filled values. |
| `max_length` | text, number | PDF MaxLen. Filling rejects longer values. |
| `comb` | text | Evenly spaced character cells, as for postal codes and IDs. Requires `max_length`. |
| `format` | text, number, date | text: `email` or `digits`. number: `{decimals, min, max}`. date: `{display}` ([§7.3](#73-values-coercion-and-validation)). Vixl enforces it only when filling; PDF viewers cannot enforce it without JavaScript. |
| `options` | dropdown | 1–200 entries, each a string or `{value, label}`. |
| `editable` | dropdown | Allows values outside `options` (PDF combo box with editing). |
| `option` | radio | This button's export value, unique within its group. |
| `on_value` | checkbox | Export value when checked. Defaults to `Yes`. |
| `tab` | all | Position in the tab order when the form uses explicit order ([§6.6](#66-tab-order-and-accessibility)). |
| `overflow` | text, multiline, number, date | When filling: `shrink` (down to `min_size`, then fail), `clip`, or `error`. Defaults to `shrink`. |
| `min_size` | text, multiline, number, date | Smallest size `shrink` may use. Defaults to 70% of `size`, and never below 6 pt. |

**Value text.** `font`, `size`, `color`, `align` and `padding` mean the same as on text
layers. `font` resolves like a text layer's font and defaults to the `body` role. These
properties draw flattened values, and they also draw typed text when the entry font is
embedded ([§6.5](#65-fonts-for-typing)).

**Appearance.** `style` is `box`, `underline` or `none`. `fill`, `stroke`, `stroke_width`
and `radius` accept swatches, like shapes. `mark` is `check`, `cross` or `dot`; checkboxes
default to `check` and radio buttons to `dot`. `mark_color` sets the mark's color.

### 5.4 Document settings

A new optional `state["form"]` object. It is added to change tracking (`src/vixl/changes.py`)
and to state validation.

| Setting | Values | Meaning |
| --- | --- | --- |
| `tab_order` | `reading` (default), `explicit` | See [§6.6](#66-tab-order-and-accessibility). |
| `entry_font` | `standard` (default), `embed` | The font viewers use for typing ([§6.5](#65-fonts-for-typing)). |
| `title` | string | PDF document title. Defaults to the first visible text layer, the same rule HTML export uses. |
| `lang` | BCP 47 tag | Document language for the PDF catalog, for example `en-US`. |

### 5.5 Operations

- **`field`** creates a field layer. Settings are flat fields on the operation, as on
  `shape`. A top-level `fill`, `stroke` or `radius` is normalized into `appearance` and
  reported under `normalized`. Default sizes depend on kind: a text field is `size × 1.5 +
  2 × padding` tall, and checkboxes and radio buttons are 14 pt squares (converted with the
  canvas dpi).
- **`field-set`** changes any settings of an existing field (`target` plus the settings).
- **`form`** sets the document settings in [§5.4](#54-document-settings).
- **Existing operations** work unchanged on fields: move, resize, align, distribute,
  constrain, group, opacity, hide/show, reorder, remove and effects. The exceptions are:
  - `rotate`, `flip` and `pivot` fail on a field, because PDF fields are axis-aligned
    rectangles. A field inside a rotated or flipped group fails the `form` check and fillable
    export. Group scaling is fine.
  - `duplicate` gives the copy a unique key (`full_name-2`). Duplicating a radio button keeps
    the group key and assigns a unique option (`annual-2`), since one button on its own is
    useless.
  - Removing a layer that a field names in `label_layer` clears that reference, the same way
    removal prunes clip and artboard references today. The `form` check then reports the
    missing label.
  - Symbol masters, `repeat` and containers cannot contain fields in this version, because
    copies would duplicate keys. Repeating rows of fields is listed under
    [future work](#15-future-work).
- **Aliases** in `normalize.py`: `input` and `form-field` become `field`. For kinds,
  `textbox` becomes `text`, `textarea` becomes `multiline`, `select` and `combo` become
  `dropdown`, and `tickbox` becomes `checkbox`.

### 5.6 Validation

These rules run when a document loads and on every commit:

- Keys are unique, except within a radio group. Buttons that share a key are all radios and
  agree on `required` and `read_only`.
- A key cannot equal a variable name ([§7.2](#72-values-and-variables)).
- Dropdown options are unique, and a default must be one of them unless `editable` is set.
- `comb` requires `max_length`, and a default cannot exceed `max_length`.
- Limits: at most 500 fields per document, 200 options per dropdown, 500 characters per
  label or option, and 10,000 characters per value.

## 6. Fillable PDF export

### 6.1 Who draws the field

**Vixl draws each field's visible box or underline into the page artwork, exactly as in the
PNG. The PDF field on top is transparent and draws only the value:** the typed text, the
check mark, the radio dot or the selected option.

- The preview matches the PDF, because they are the same pixels.
- Fields get the full styling vocabulary: swatches, radius, effects.
- Viewers differ in how they draw a field's own border and background (the PDF `/MK`
  dictionary), so the design does not rely on them for either.

Viewers can still add their own highlight, such as Acrobat's blue tint. That is a viewer
preference that a PDF cannot control.

**Page content.** At first the page is a single image: the same pixels the current PDF
export writes, at the canvas dpi (or an explicit `dpi`). Compression is lossless by default
so form text and rules stay crisp, with JPEG available on request for photo-heavy forms.
When a vector PDF exporter exists it replaces only the page content; the fields do not
change. Fillable export is RGB only for now. Asking for `color_space="cmyk"` together with
`fillable` fails with a clear error.

### 6.2 Coordinates

- One pixel is `72 / dpi` points. `dpi` is the canvas dpi, or 72 when the canvas has none,
  which is the current PDF export's default.
- PDF puts the origin at the bottom left, so with `k = 72 / dpi` and page height `H` in
  points, a field's rectangle is `[x·k, H − (y + h)·k, (x + w)·k, H − y·k]`.
- Bounds come from the canvas-space projection that `check_design` already performs. It is
  extracted into a shared helper so checks and export cannot disagree.
- On a canvas with bleed, MediaBox is the full canvas, and TrimBox and BleedBox are written,
  with TrimBox inset by the bleed. This also resolves the explorations finding that print
  PDFs have no TrimBox or BleedBox, at least for this path.
- The `form` check warns when a form's canvas has no physical size. A pixel canvas maps one
  pixel to one point, which gives odd page sizes.

### 6.3 Mapping field kinds to PDF

| Kind | Field type | Flags | Value and appearance |
| --- | --- | --- | --- |
| text | `Tx` | Comb when `comb` | `/V` string. The appearance draws the value. |
| multiline | `Tx` | Multiline | As text. |
| number, date | `Tx` | none | As text. Formatting is applied only when Vixl fills. |
| checkbox | `Btn` | none | Appearance states `/<on_value>` (the mark) and `/Off`. `/AS` selects one. |
| radio | `Btn` | Radio, NoToggleToOff | A parent field with one widget per option. Each widget has states `/<option>` and `/Off`. |
| dropdown | `Ch` | Combo, plus Edit when `editable` | `/Opt` holds `[value label]` pairs. The appearance draws the selected label. |
| signature | `Sig` | none | No value and an empty appearance. |

Every field also gets `/T` (the key) and `/TU` (the label, or `group_label` on a radio
parent). It also gets the Required and ReadOnly flags, `/Q` for alignment, and a `/DA`
default appearance string such as `/Helv 11 Tf 0.1 0.1 0.1 rg`. Each widget is marked
printable. Checkboxes and radio buttons also carry a ZapfDingbats caption in `/MK`, as a hint
for viewers that redraw appearances themselves.

### 6.4 Appearance streams

Vixl generates an appearance for every widget and does not set `NeedAppearances`. With
`NeedAppearances` set, Acrobat redraws every field and asks to save changes when the file
closes, and some viewers ignore the flag and show empty fields (macOS Preview is the one most
often reported).

- **Empty text fields** get an empty appearance. The viewer draws typed text from `/DA`.
- **Defaults** (and prefilled values, [§7.6](#76-prefilled-editable-pdfs-later-phase)) are
  laid out by Vixl with Helvetica metrics: line breaks, alignment and padding, clipped to the
  box. Vixl bundles the Helvetica WinAnsi width table from Adobe's Core 14 AFM files, which
  Adobe licenses for free redistribution.
- **Check marks and radio dots** are vector paths matching `appearance.mark`, so they do not
  depend on any font.

### 6.5 Fonts for typing

The viewer, not Vixl, draws what a person types, using the font named in `/DA`. Vixl's
HarfBuzz shaping does not apply.

- **`entry_font: standard`** (the default) uses Helvetica, unembedded. Every viewer has it
  and it adds nothing to the file, but it covers only WinAnsi (Western European) characters.
  Each viewer handles other characters in its own way.
- **`entry_font: embed`** (a later phase) embeds each field's font in full as a TrueType
  font in the form resources. It is not subset, because the person may type any character.
  Typed text then matches the design and covers the font's scripts, at the cost of file size
  and less consistent viewer support. Complex scripts such as Arabic and Indic still depend
  on the viewer's own shaping. The `form` check reports the added size and refuses fonts
  above a cap, for example 8 MiB; CJK fonts often exceed it.
- **Flattened filling ([§7](#7-filling)) always uses Vixl's own text engine with the
  field's font.** This limitation affects only interactive typing.

### 6.6 Tab order and accessibility

- **`reading` order** (the default) sorts fields into rows by vertical center. Two fields
  share a row when their centers are within half the smaller field's height. Rows go top to
  bottom and fields within a row go left to right. A radio group is one stop, at its first
  option. The algorithm is documented so agents can predict it, and
  `render --show-fields` draws the resulting numbers.
- **`explicit` order** requires every field to have a unique `tab`.
- The order is written as the order of the page's `/Annots` array. Whether to also set the
  page's `/Tabs` entry is settled by the viewer matrix ([open question 4](#13-open-questions)).
- The catalog gets `/Lang` and `/ViewerPreferences << /DisplayDocTitle true >>`, and the
  document info gets `/Title`.
- The PDF has no structure tree (it is not tagged) in this version.

### 6.7 Determinism and safety

- The same document and options produce a byte-identical PDF: object order is stable, no
  timestamps are written, and `/ID` is derived from a hash of the content.
- **No actions anywhere.** There is no `/OpenAction`, `/AA`, `/A`, `/JavaScript`, `/URI`,
  `/SubmitForm` or `/Launch`. Tests walk every object to prove it.
- **Strings are always hex.** Text strings (`/T`, `/TU`, `/V`, `/Opt`, `/Title`) are written
  as hex UTF-16BE with a byte-order mark, `<FEFF…>`. Appearance text is written as hex
  `<…> Tj`. Nothing is written as a literal `(…)` string, so user text cannot escape into PDF
  syntax and there is no escaping code to get wrong.
- Option values that become appearance-state names are encoded with PDF `#xx` name escaping.
- The writer streams to a staging file, publishes with the existing atomic replace, and
  enforces Vixl's resource limits.

### 6.8 The PDF writer

A new module, `pdf_writer.py`, is a small deterministic object writer. It handles indirect
objects, Flate streams, the cross-reference table, the trailer, string and name encoding,
image XObjects and form XObjects. It should be a few hundred lines.

Why not use a library:

| Option | Why not |
| --- | --- |
| Pillow (current) | Cannot write annotations or fields. |
| pikepdf | Robust, but adds a native qpdf dependency to the Windows installer, and its output bytes vary with its version. |
| reportlab | Has AcroForm helpers, but brings its own text model, which conflicts with drawing HarfBuzz-shaped glyphs for the future vector exporter. |
| pypdf | Good for reading and verifying PDFs. Building documents from scratch with it is lower level than a purpose-built writer. It is proposed as a dev-only test dependency. |

The same writer becomes the base of the future vector PDF exporter. Fields do not care
whether the page content is an image or vectors.

## 7. Filling

### 7.1 Inputs and modes

Values come from a JSON object (Python dict, MCP `values`, or repeated CLI `--set`) or from
CSV rows (`--data`). There are two modes:

- **`flatten`** (the default) draws the values into the artwork with Vixl's renderer. The
  output can be any raster format, SVG, or a PDF with no interactive fields.
- **`editable`** (a later phase) writes a fillable PDF with the values already set
  ([§7.6](#76-prefilled-editable-pdfs-later-phase)).

### 7.2 Values and variables

Field keys and variable names share one namespace, and a key cannot equal a variable name.
During any render, each field's current value (its default, or the filled value) is
available as `${key}` in text layers. A certificate sentence such as "This certifies that
${full_name}" and a field can therefore share one value.

In a fillable PDF, a text layer that references a field key shows the default and does not
update as the person types, because there is no JavaScript. The `form` check warns about
this.

Each input key must name a field or a variable:

- A key that names a field fills it.
- A key that names a variable sets it.
- An unknown key is an error by default (`unknown: "error"` or `"ignore"`). A misspelled CSV
  header that silently produces blank fields is the classic mail-merge failure.

### 7.3 Values: coercion and validation

| Kind | Accepted | Drawn as |
| --- | --- | --- |
| text | A string. Numbers are converted to strings. Newlines are rejected. | The text. |
| multiline | A string. `\r\n` becomes `\n`. | Wrapped text. |
| number | A JSON number or a numeric string, checked against `min` and `max`. | Formatted with `decimals`. |
| date | ISO 8601 `YYYY-MM-DD`. | Formatted with `format.display` tokens: `YYYY`, `MM`, `M`, `DD`, `D`. Numeric only for now; no localized month names. |
| checkbox | `true`/`false`, or `yes`, `no`, `true`, `false`, `1`, `0`, `x` or empty, in any case. | The mark when true. |
| radio | Exactly one option value of the group. | The mark on that option. |
| dropdown | An option value, or any string when `editable`. | The option's label. |
| signature | Nothing. Supplying a value is an error. | An empty box. |

- A missing key uses the field's default. An empty required field is an error.
- `max_length` limits length. `digits` allows only 0–9. `email` checks for one `@` with a
  non-empty part on each side and no spaces; it is deliberately loose.
- Errors are structured as `{row, key, code, message}`. Codes are `missing_required`,
  `unknown_key`, `invalid_option`, `invalid_number`, `invalid_date`, `too_long`,
  `invalid_format` and `overflow`. Messages name the row and key but never repeat the value.

### 7.4 Drawing values

- **Text kinds** are drawn as a synthetic text layer that uses the field's font, size, color
  and alignment inside the box minus `padding`, through `text.plan`. They get the same
  shaping, fallback fonts and SVG outlines as any text layer. Single-line values are
  vertically centered; multiline values wrap from the top.
- **Overflow:**
  - `shrink` reduces the size, down to `min_size`, without breaking inside a word. If the
    value still does not fit, it is an `overflow` error.
  - `clip` draws the value clipped and reports a warning.
  - `error` reports an error without shrinking.
- Today's text fitting broke a word in the middle ("SOLSTI / CE" in `explorations/README.md`).
  It must be fixed first ([§10](#10-implementation-plan), Phase 0).
- **Checkboxes and radio buttons** draw the same mark path as the PDF appearance.
  **Dropdowns** draw the option's label. **Comb fields** put one character in each cell,
  centered.

### 7.5 Batch filling

- CSV reading uses the same reader and limits as `render --data`: UTF-8 with an optional
  byte-order mark, unique non-empty headers, at most 10,000 rows and 8 MiB. The reader is
  factored out of `render_data` and shared.
- **Preflight.** Every row is validated before anything renders. One bad row fails the
  batch, unless `--skip-invalid` is given; then valid rows are written and skipped rows are
  reported. `--dry-run` runs the preflight only.
- **One file per row.** `--out DIR` with a `--name` template made of `{key}` placeholders and
  `{row}`. Names are sanitized to `[\w.-]`, capped at 120 characters, and collisions are
  errors found before rendering. The default name is `0001.pdf`, as in `render_data`.
  Existing files are never overwritten.
- **One combined PDF.** `--combine FILE.pdf` writes one page per row, streamed through the
  PDF writer. It is limited to 1,000 rows and 512 MiB. Raster pages at 300 dpi are roughly
  1–3 MB each, so the preflight estimates the output size and, when it is over the limit,
  suggests a lower `--dpi`.
- **Per-row checks.** Value validation and overflow always run. Full design checks are
  opt-in (`--check design`), because the current contrast check costs seconds per text layer
  for every row.
- **Large batches** run through the durable job system as the workflow action `form-fill`.
- **Publishing.** Output is staged and published atomically, as `render_data` does. Nothing
  is published unless every row rendered, or with `--skip-invalid`, every valid row.

### 7.6 Prefilled editable PDFs (later phase)

`mode: "editable"` writes the fillable PDF with `/V` and appearances for the supplied
values. For example, name and member ID are prefilled and read-only, and the person ticks the
boxes and signs. Values must be encodable in the entry font ([§6.5](#65-fonts-for-typing)).
With the standard font, a value outside WinAnsi is an error that suggests `flatten` or
`entry_font: embed`.

### 7.7 Personal data

Filled values are usually personal data.

- Filling never writes to the `.vixl` document, its history or its review notes. Each row
  renders from a clone, as in `render_data`.
- Renders that contain field values bypass the persistent render cache
  (`src/vixl/render_cache.py`), for both whole-document and per-layer entries. Otherwise
  cached PNGs would keep personal data on disk.
- Error messages name rows and keys, never values.
- Staging directories are temporary and removed afterwards.
- Durable jobs freeze their inputs (`src/vixl/jobs.py`). A `form-fill` job deletes its copy
  of the data when it completes or is cancelled, unless the request sets
  `retain_inputs: true`.

## 8. The `form` check family

`form` joins the default checks and does nothing in a document without fields. Issues use
the existing structured format.

**Errors**

- Invalid or duplicate keys, or a key that equals a variable name.
- A radio group with fewer than two options or with mismatched settings.
- A dropdown without options, or a default that is not allowed.
- `comb` without `max_length`, or an explicit tab order that is incomplete or repeats.
- A field that is rotated or flipped, or sits inside a rotated or flipped group.
- A field outside the page, or crossing the trim line on a canvas with bleed.
- Fields that overlap each other.
- A missing accessible name: no `label`, `label_layer` or radio `group_label`, or one that
  resolves to empty text.
- Defaults, options or labels the standard entry font cannot encode.

**Warnings**

- A box too small for its content: inner height under 1.2 × `size`, a checkbox or radio
  button under 10 pt, or a value size under 8 pt.
- A border or underline below 3:1 contrast against what is behind it (WCAG 1.4.11, non-text
  contrast). This is sampled from one render without the field layers, not the
  per-text-layer re-render the current contrast check performs.
- `style: none` with nothing drawn under the field, so people cannot see where to write.
- A `label_layer` more than twice the field's height away from the field.
- An explicit tab order that jumps back up the page.
- An opaque layer above a field, so the artwork and the PDF field disagree.
- A field with opacity below 1, a blend mode, or effects that extend past its box.
- A text layer that references a field key; it stays static in the fillable PDF.
- A canvas without a physical size.
- Radio option values that are not readable words, because some viewers announce them.

**Sample fills.** `vixl check --checks form --sample rows.csv` runs the overflow logic
against real rows. `--sample worst` fills every field with worst-case values instead:
`max_length` copies of "W", the longest option label and the largest allowed number.

Saved check suites can include `form`, so suite-gated group publishing works for forms too.

## 9. Interfaces

**CLI**

```text
vixl field add KEY --kind KIND [--label TEXT | --label-layer LAYER] [--x --y --width --height] [settings…]
vixl field set LAYER [settings…]
vixl field list [--json]                 # keys, kinds, tab order, rectangles in points
vixl form settings [--tab-order reading|explicit] [--entry-font standard|embed] [--title T] [--lang L]
vixl form fill (--set KEY=VALUE … | --data rows.csv) (--out FILE|DIR | --combine FILE.pdf)
               [--name TEMPLATE] [--mode flatten|editable] [--skip-invalid] [--dry-run] [--check design]
vixl export FILE.pdf --fillable
vixl render --out FILE.png --show-fields [--set KEY=VALUE …]
vixl check --checks form [--sample rows.csv|worst]
```

**Python**

`project.export("registration.pdf", fillable=True)`, plus `vixl.forms.fill(project, values,
path, mode="flatten")` and `vixl.forms.fill_data(project, csv_path, directory, **options)`.

**MCP.** No new tools are added, so the compact profile stays at 12.

- `vixl_operations_apply` accepts `field`, `field-set` and `form`.
- `vixl_export_file` gains `fillable`, `values` and `fill_mode`. A key in `variables` that
  names a field is an error that suggests using `values`.
- `vixl_check` accepts `"form"` in `checks`, and `sample`.
- `vixl_render_preview` gains `values` and `show_fields`.
- `vixl_document_inspect` (compact) adds a field summary: key, kind, required, tab position
  and rectangle in points.
- `vixl_workflow` gains the `form-fill` action, with `data`, `output`, `name`, `format`,
  `combine`, `mode`, `skip_invalid`, `dry_run` and `check`.

**REST.** `POST /export` gains `fillable` and `values`. The fixed-project workflow subset
includes `form-fill`.

**Documentation.** A user guide (`docs/forms.md`), a row in [coverage](../coverage.md), the
`skills/vixl` references, and one sentence in the MCP server instructions.

## 10. Implementation plan

### Modules

| Module | Change |
| --- | --- |
| `forms.py` (new) | Field operations, schemas, validation, tab order, value coercion and validation, fill orchestration. |
| `pdf_writer.py` (new) | Deterministic, streaming PDF object writer ([§6.8](#68-the-pdf-writer)). |
| `pdf_forms.py` (new) | Field and widget dictionaries, appearance streams, Helvetica metrics. |
| `render.py`, `design_render.py` | Draw `field` layers (appearance plus value), bypass the disk cache for valued renders, add the `fillable` export path. |
| `svg.py`, `html_export.py` | Static field appearance. |
| `checks.py` | The `form` family. The canvas-bounds projection moves into a shared helper. |
| `operations.py`, `design.py`, `validation.py`, `changes.py` | Dispatch, the `rotate`/`flip`/`duplicate`/`remove` rules, and `state["form"]`. |
| `schema.py`, `normalize.py` | Operation schemas and aliases. |
| `exports.py` | Shared CSV reader. |
| `cli.py`, `feature_cli.py`, `interfaces.py`, `mcp_tools.py`, `workflows.py` | Interfaces in [§9](#9-interfaces). |
| `pyproject.toml` | `pypdf` in the `dev` extra, for tests only. |

### Phases

Fields come first because both features need them. Flattened filling comes next because it
needs only the field model and the existing renderer, so it ships value early and tests the
field model before the PDF work begins.

**Phase 0: prerequisites (small)**

- Fix text fitting: no breaks inside words, and shrinking that actually converges.
- Extract the canvas-space bounds projection from `check_design` into a shared helper.
- Factor the CSV reader out of `render_data`.

**Phase 1: field model (medium)**

- The `field`, `field-set` and `form` operations, with schemas, aliases, validation and
  change tracking.
- Field appearance in PNG, SVG and HTML, the `--show-fields` preview overlay, and the field
  summary in inspect.
- The `form` checks, except sample fills.
- *Done when* an agent can build the [§4](#4-walkthrough) form through MCP, the checks pass,
  the preview shows the fields, and documents without fields are unaffected.

**Phase 2: flattened filling (small to medium)**

- Value coercion, validation and drawing, overflow handling, and `${key}` in text layers.
- Single fills to any format, and batches with preflight, naming, `--skip-invalid` and
  `--dry-run`.
- `pdf_writer.py` with image pages only, for streamed combined PDFs.
- Sample-fill checks, the personal-data rules in [§7.7](#77-personal-data), and the
  `form-fill` workflow action.
- *Done when* a 200-row CSV produces 200 files or one combined PDF, a CSV with a bad row
  fails preflight naming the row and key, and no personal data reaches a cache.

**Phase 3: fillable PDF (medium to large)**

- Fields and widgets for every kind, appearance streams, Helvetica metrics, tab order,
  catalog metadata, determinism and the no-actions guarantee.
- `--fillable` across the CLI, Python, MCP and REST.
- A pass of the manual viewer matrix ([§11](#11-testing)).
- *Done when* the [§4](#4-walkthrough) form fills correctly in every viewer in the matrix
  and repeated exports are byte-identical.

**Phase 4: extensions (medium each, independent)**

- Prefilled editable PDFs.
- Embedded entry fonts.
- Multi-page forms, together with the pages model.
- Vector page content, together with the vector PDF exporter.

## 11. Testing

**Automated**

- **Operations and validation:** every error in [§5.6](#56-validation), the `duplicate`,
  `remove` and `rotate` rules, and the aliases.
- **Rendering:** golden PNGs for each kind and appearance style, and SVG appearance.
- **Filling:**
  - Every row of the coercion table.
  - The `shrink`, `clip` and `error` overflow modes.
  - Preflight, naming collisions and `${key}` substitution.
  - An assertion that valued renders write nothing to the render cache.
- **PDF structure** (pypdf):
  - Field names, types, flags, rectangles to 0.01 pt, options, `/TU`, `/Annots` order,
    `/Lang` and `/Title`.
  - No action keys anywhere, found by walking every object.
  - Hostile strings in keys, labels, options and values (parentheses, backslashes, `>>`,
    `endstream`, non-Latin text, emoji) round-trip exactly.
  - Two exports are byte-identical.
- **Visual parity** (pypdfium2, already an optional dependency):
  - Render the fillable PDF with forms initialized and compare it with Vixl's PNG of the
    same document.
  - Render a prefilled PDF and confirm the value pixels fall inside each field's rectangle.
- **Interoperability:** fill a Vixl PDF with pypdf, a different producer, then render it with
  pdfium. The values must appear in their boxes, which proves `/DA` and the form resources
  work for other tools.
- **Interfaces:** CLI subprocess, MCP stdio and REST tests, following the existing ones.

**Agent evaluations** (`evals/tasks`)

- `form-registration`: build a letter-size registration form with named fields. Checks pass,
  and the fillable export lists the expected fields.
- `form-batch-fill`: given a CSV where one row is missing a required value, produce the
  filled set and report the bad row.

**Manual viewer matrix** (each release that touches forms)

Viewers: Adobe Acrobat Reader on Windows and macOS, Chrome, Edge, Firefox, macOS Preview, iOS
Files, and the Android Chrome or Google Drive viewer.

For each viewer, confirm that:

- fields line up with the artwork;
- typing uses the expected font and size;
- checkboxes toggle, radio buttons are exclusive and dropdowns list their options;
- required fields are marked and tab order follows [§6.6](#66-tab-order-and-accessibility);
- values survive save and reopen, and printing includes them;
- opening the file does not prompt to save changes.

## 12. Risks

| Risk | Mitigation |
| --- | --- |
| Viewers behave differently | Generated appearances, a conservative feature set and the viewer matrix. `comb` is documented as unevenly supported. |
| Text fitting bugs make overflow handling unreliable | Phase 0 fixes them first. |
| Personal data leaks into caches, jobs or logs | [§7.7](#77-personal-data), with tests for each path. |
| Raster pages make large files | Lossless compression by default, a size estimate in preflight, an explicit `dpi`, and vector page content later. |
| Scope creeps into JavaScript, submission or third-party forms | Listed as non-goals, and enforced by the no-actions test. |
| A future pages model changes the document structure | Fields are layers, so they move with pages. Widgets and tab order become per page. |
| People type non-Latin text into a standard-font field | The `form` check warns, and `entry_font: embed` is available. |

## 13. Open questions

1. **Default entry font.** Standard Helvetica is robust and adds nothing to the file.
   Embedding the field's font matches the design. This proposal defaults to Helvetica.
2. **Phase order.** Flattened filling ships before the fillable PDF because it needs only the
   field model and the existing renderer. If the fillable PDF matters more, Phases 2 and 3
   can swap; the writer's image-page support then moves into Phase 3.
3. **Multi-page forms.** Wait for the pages model, or use artboards as interim pages?
   Artboards share one coordinate space, so their contents overlap in plain previews.
4. **Tab order mechanism.** Is the `/Annots` order enough, or should pages also set `/Tabs`?
   The viewer matrix decides.
5. **Physical units in coordinates.** Accepting `12pt`, `0.75in` and `6mm` in coordinates and
   sizes when the canvas has a dpi would help forms and all print work. It may deserve its
   own small proposal.
6. **Image values.** Should flattened fills accept images, such as photos or signature
   images? This proposal says not yet.
7. **CMYK.** This proposal makes fillable export RGB only. Is CMYK needed for printed forms
   that are also filled on screen?

## 14. Alternatives considered

- **A separate field registry** instead of layers. Rejected in [§5.1](#51-why-fields-are-layers).
- **Viewer-drawn borders and backgrounds through `/MK`.** Rejected in
  [§6.1](#61-who-draws-the-field): rendering varies by viewer and would not match the
  preview.
- **`NeedAppearances` instead of generated appearances.** Rejected in
  [§6.4](#64-appearance-streams).
- **Filling with text layers and variables only.** This cannot validate values, draw checked
  states or detect overflow, and it cannot produce the fillable version.
- **An existing PDF library.** Discussed in [§6.8](#68-the-pdf-writer).
- **HTML forms.** Out of scope. Inputs laid over artwork do not reflow on phones, and Vixl has
  nowhere to submit the data.

## 15. Future work

- Repeating rows of fields for order-form line items, with numbered keys
  (`item-1`, `item-2`, …).
- Multi-page forms with the pages model, including one field shown on several pages (one
  field with several widgets).
- Vector page content from the vector PDF exporter.
- Image values for photos and signature images.
- Form layouts and templates, such as `form-single-column` and a registration template.
- Reading completed copies of a Vixl-made form back into CSV, matched by key. This closes
  the loop while still never touching third-party forms.
