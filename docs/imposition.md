# Data merge and print imposition

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

`merge-impose` turns a template and a CSV into print sheets: n copies per page, with gutters, bleed,
crop marks, registration marks and slug text, as a multi-page PDF whose text is **real, selectable vector
text** and/or an **editable sheet document**. A change to the data or the template is one more call, not a
rebuild: badge 11 and a new sponsor colour mean editing the CSV and rerunning the merge (the evaluation
that motivated this took about 50 tool calls by importing and moving every badge by hand).

```json
{"action": "merge-impose",
 "request": {"template": "badge.vixl", "data": "badges.csv",
             "sheet": {"size": "letter", "cols": 2, "rows": 3, "slug": "{template} · {first}-{last} · {page}/{pages}"},
             "output": "badges-print.pdf", "sheet_document": "badges-sheet.vixl"}}
```

Through MCP this is `vixl_workflow("merge-impose", request, document=template)` (the template defaults
to the open document); on the CLI it is `vixl merge`; REST does not serve it (it writes files).

## The template

An ordinary `.vixl` document designed at the size of one copy, with `${variables}` where the data goes. Make
it from a print size (`vixl new letter`, a custom canvas with `dpi`) so its physical size is known; a
template with bleed (`vixl new business-card --bleed`) lets the sheet print the bleed. A template needs a
sample value for each variable (that is how it measures and previews); they are samples only, and the merge
refuses to print them by accident (see [Validation](#validation)). Use `page`/`artboard` to merge one page or
artboard of a larger document; an artboard is then the item, with no bleed.

Placeholders may carry filters (`${first_name|upper}`, `${company|default:Independent}`,
`${state|map:states}`; see [concepts](concepts.md#variables-swatches-and-styles)). The column is matched by
the name before the first `|`, and the filters run on each copy's value, so one CSV can feed upper-case name
lines and a mapped colour.

Image variables (`replace-contents --variable photo`) take a file name in the CSV: an image next to the CSV
or in the workspace, never outside it.

## The data

`data` is a UTF-8 CSV (header row, unique column names, at most 5,000 rows) or give `rows` inline as a list of
objects. Each column named like a template variable provides it; other columns are reported. `variables` are
constants for every copy (a column overrides them). **An empty cell is an empty value**, not a missing one:
the text layer prints nothing, and a layer that hides itself or reflows when empty works as designed.
`copies` prints every row that many times.

## The sheet spec

All lengths are in the sheet's unit: inches for the US sizes, millimetres for the ISO sizes, or the `unit`
you give (`in`, `mm`, `cm`, `pt`).

| Key | Default | Meaning |
| --- | --- | --- |
| `size` | `letter` | A named paper size (`vixl sizes`): `letter`, `a4`, `tabloid`, … Or give `width`, `height` and `unit`. |
| `orientation` | the size's own | `portrait` or `landscape`. |
| `dpi` | 300 | The resolution of the sheet document; the PDF page size is exact whatever it is. |
| `cols`, `rows` | as many as fit | Grid size. Asking for more than fit is an error with the numbers. |
| `gutter` | 0 | Space between neighbouring trim edges: a length or `[horizontal, vertical]`. |
| `margin` | the marks' need, at least ¼ in | Clear border (length, `[vertical, horizontal]`, `[top, right, bottom, left]` or an object). |
| `bleed` | `template` | `template` prints the bleed the template was made with; a length prints that much of it (an error if the template has less); `0` prints trim only. Where two copies share an edge each prints at most half the gutter, so a copy never covers its neighbour. |
| `crop_marks` | `true` | Marks at every cut line in the margins, starting outside the bleed. `{length, offset, weight}` (lengths in the unit, weight in points) tunes them; `false` removes them. |
| `registration` | `false` | A registration target (ring and cross) at the middle of each margin, beyond the crop marks. |
| `slug` | none | Text for the bottom margin. Fields: `{template}`, `{page}`, `{pages}`, `{first}` and `{last}` (the CSV row numbers on this sheet), `{count}`, `{rows}`. |
| `order` | `rows` | Fill left to right then down (`rows`), or top to bottom then across (`columns`). |
| `align` | `center` | Centre the grid in the margins, or pin it to `top-left`. The grid sits in the same place on every sheet, so the cut lines line up; a last, partly filled sheet leaves cells empty. |
| `background` | `#ffffff` | Sheet colour. |

The marks are black bars 0.25 pt wide in the margins; the grid must leave room for them, and the error says
how much. Marks and slug text are ordinary layers of the sheet document.

## Validation

Everything is checked before a file is written. The report lists, per row and per column:

| Code | Meaning |
| --- | --- |
| `missing_column` | The template draws `${x}` but the data has no `x` column, so every copy would print the template's sample value. An error by default (`defaults`: `error`, `warn` or `ignore`); give constants in `variables`. Suggests a similar column ("did you mean…"). |
| `unknown_column` | A column matches no variable (`unknown`: `warn` by default, `error` or `ignore`), with a did-you-mean. |
| `overflow` | A fixed-box text layer (`text-layout`) does not fit its box with this row's text. |
| `missing_glyphs` | A character no available font can draw would print as an empty box. |
| `missing_image` | An image column's file does not exist, is outside the workspace, or the cell is empty. |
| `design` | With `check: "design"`: bounds, overlap, contrast, font and link errors on that copy. |

Rows are numbered from 1 in file order; messages name rows, columns and layers, never cell values. If any row or
column fails, nothing is written (`merge_invalid`, with the full `report`) unless `skip_invalid` leaves out the
failing rows. `dry_run` validates and returns the report and the layout (grid, sizes in the unit, number of
sheets) without writing; the grid is worth reading before the first real run.

## Outputs

- **`output`**: the print PDF (`.pdf`). Vector: shapes and gradients are PDF graphics and text is embedded
  font subsets with Unicode maps, so it can be selected, searched and extracted. Layers the PDF cannot draw
  the same way (effects, masks, opacity, blend modes) are embedded as images and listed in
  `raster_fallbacks`. The page size is the exact paper size. The PDF is RGB; for CMYK, export the sheet
  document (`vixl -p sheets.vixl export out.pdf --cmyk`), which is then rasterized.
- **`sheet_document`** (or an `output` ending in `.vixl`): an editable `.vixl` with a page per sheet
  (`sheet-1`, …). Every copy is a [`link`](linked-documents.md) layer (`row-N`) to the template with that
  row as its `variables`, positioned and cropped exactly. Open it, preview it (`page: "all"`), move a cell,
  hide a copy, export it in any format. Because the cells are live links, **editing the template updates the
  sheet** without a rerun (`links` reports the cells as `stale` until you `link-refresh`); changed *data* needs
  a rerun. The sheet records its merge (`merge` in the document state) so it can be repeated.

Existing outputs are never overwritten unless `replace: true`. Paths are workspace-relative; the template,
data and outputs must all be inside the workspace.

## Re-running

`{"rerun": "badges-sheet.vixl"}` repeats the merge recorded in a sheet document: its template, data file, sheet
spec and outputs are read again, and the outputs are rewritten (`replace` defaults to true). Any request field
overrides the record, and `sheet` keys are merged into the recorded spec, so
`{"rerun": "sheet.vixl", "data": "badges-v2.csv", "sheet": {"cols": 1}}` changes the data and the grid
in one call. CLI: `vixl merge --rerun badges-sheet.vixl`.

## CLI

```text
vixl merge [TEMPLATE.vixl] --data badges.csv --out badges-print.pdf [--sheet-document sheet.vixl]
           [--size letter] [--orientation landscape] [--unit mm] [--dpi 300] [--cols 2] [--rows 3]
           [--gutter 0.125] [--margin 0.5] [--bleed template|0.125] [--no-crop-marks] [--registration]
           [--slug TEXT] [--order columns] [--align top-left] [--background COLOR] [--copies N]
           [--set NAME=VALUE]… [--page P] [--artboard NAME] [--unknown warn|error|ignore]
           [--defaults error|warn|ignore] [--check design] [--skip-invalid] [--dry-run] [--replace]
vixl merge --rerun sheet.vixl [--data new.csv] [--out new.pdf]
```

The workspace is the current folder; the template (a positional `.vixl`, `-p`, or the current document),
data and outputs must be inside it.

## Notes and limits

- At most 5,000 copies and 500 sheets per merge, and 512 layers per sheet (marks included).
- A template without a `dpi` is placed at one pixel per sheet pixel (a warning says so); give it a print size.
- Crop marks are drawn in the margins only, at every cut line; with a gutter each copy's two edges get a
  mark. Registration marks are plain black rings and crosses, not a separation colour.
- Slug text uses the bundled proofing font.
- Merged text keeps the template's typography: the merge adds nothing to the copy's own layout, so shrink-to-fit
  boxes (`text-layout --fit`) and hide-if-empty layers behave exactly as they do in the template.
