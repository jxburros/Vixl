# Moving from a template-rendering API

[Documentation home](../../README.md) · [Checked production](production.md) · [Sizes and layouts](../layout/sizes-and-layouts.md)

Hosted template-rendering services work the same way: you design a template with named layers, send the values for
one image (a headline, a price, a photo URL) in an API call, and get a rendered image back, one call and one charge
per image. Vixl does that job on your own machine. The template is a document or a short recipe, the values come
from a CSV or from `--set`, and rendering a thousand rows is one command.

This guide rebuilds a typical product-card template, fills it from a CSV, makes it in three sizes, checks it and
exports every row. Every command runs offline.

## How the ideas map

| In a template API | In Vixl |
| --- | --- |
| A template in the service's editor | A `.vixl` document, or a JSON recipe you keep in Git and apply to a blank document |
| A named layer you can modify | A layer name (`title`, `image`), in any document |
| A text modification | A `${variable}` in the layer's text, with filters such as `${badge\|upper}` |
| An image modification | An image layer bound to a variable: the value is a file beside the CSV |
| One API call per image | `vixl render --set name=VALUE --out one.png` |
| A batch or a spreadsheet integration | `vixl render --data rows.csv --out folder` |
| One template per size | One recipe applied at each size, or `vixl adapt-layout --sizes` on a finished document |
| Looking at each result | `vixl check`: overflow, contrast, safe areas and leftover placeholders are measured per row |
| A returned image URL | Files in a folder you choose: PNG from a data merge, and PDF, SVG, JPEG, WebP or PPTX from `vixl export` |

## 1. The data

Save the rows as `products.csv`. Headers are variable names; the `photo` column names an image file beside the CSV.
(The same file is in this folder as [`products.csv`](products.csv).)

<!-- docs-test: save products.csv -->
```csv
name,badge,price,benefit,photo
Field Notebook,New,$14,"Lies flat, takes ink, fits a jacket pocket.",photo.jpg
Enamel Camp Mug,Restocked,$22,Keeps coffee hot through the first hour of the trail.,image.png
Canvas Tote,Sale,$36,Carries a week of groceries and still folds into a drawer.,replacement.jpg
```

## 2. The template

Save this recipe as `product-card.json`. It declares the variables with sample values, lays the card out with the
built-in `product-card` layout, then puts a picture in the layout's image slot and binds that slot to the `photo`
variable.

<!-- docs-test: save product-card.json -->
```json
[
  {"type": "variable", "name": "name", "value": "Enamel Camp Mug"},
  {"type": "variable", "name": "badge", "value": "Restocked"},
  {"type": "variable", "name": "price", "value": "$22"},
  {"type": "variable", "name": "benefit", "value": "Carries a week of groceries and still folds into a drawer."},
  {"type": "layout-apply", "name": "product-card", "seed": 7, "palette": "cream-marigold",
   "title": "${name}", "body": "${benefit}", "label": "${badge}", "caption": "${price}", "cta": "Shop now"},
  {"type": "replace-contents", "target": "image", "path": "photo.jpg", "variable": "photo"}
]
```

Two things to carry over from template work elsewhere:

- **Use your longest values as the samples.** The layout sizes each text box for the text it is given, so the sample
  name, badge and benefit above are the longest in the CSV. A row that still does not fit is reported by the check in
  step 4, not silently cut off.
- **The image slot keeps a default.** Binding a layer to a variable that does not exist yet creates the variable
  with the layer's current picture, so the template renders on its own and each row replaces the picture.

A design you placed by hand works the same way: any text layer may contain `${variables}`, and
`replace-contents --variable NAME` binds any image layer. A layout is used here because it re-composes itself for
each size in the next step. To pin your brand's fonts and colours instead of the layout's choices, see
[brands](../layout/brands.md).

## 3. Three sizes from one recipe

Create a blank document per size and apply the same recipe. `--seed` keeps the same font pairing in all three.

```bash
vixl new instagram-post --seed 7 -o card-post.vixl
vixl -p card-post.vixl apply product-card.json
vixl new instagram-story --seed 7 -o card-story.vixl
vixl -p card-story.vixl apply product-card.json
vixl new og-image --seed 7 -o card-link.vixl
vixl -p card-link.vixl apply product-card.json
```

The square post stacks the picture above the copy, the story gives the picture more height, and the link preview
puts picture and copy side by side: the layout decides per canvas, so there is no second and third template to keep
in step. `vixl sizes` lists the 150 or so named sizes; `WIDTHxHEIGHT` works too.

## 4. Check, then look

<!-- docs-test: continue -->
```bash
vixl -p card-post.vixl check
vixl -p card-post.vixl render --out card-post-preview.png
```

`check` measures the design: text that overflows its box, contrast, content outside the safe area, unfilled slots
and leftover `${placeholders}`. Open the preview as well; a check does not replace looking.

## 5. Export every row

<!-- docs-test: continue -->
```bash
vixl -p card-post.vixl render --data products.csv --out cards-post
vixl -p card-story.vixl render --data products.csv --out cards-story
vixl -p card-link.vixl render --data products.csv --out cards-link
```

Each folder receives `0001.png`, `0002.png` … in row order, and the result lists each row's output with its check
findings (`check.passed` and the issues, when a row has any). Every row is rendered and checked before anything is
published, and existing files are never overwritten: use a new folder per run.

Add `--strict` to make the checks a gate. The template must pass first, and a row that fails a check then stops the
whole batch and names the row, so a card with a cut-off title never reaches the folder:

<!-- docs-test: skip a strict export needs the document's real typefaces; the offline test workspace has only the proofing font, which the fonts check refuses -->
```bash
vixl -p card-post.vixl render --data products.csv --out cards-post-final --strict
```

One image, the equivalent of a single API call, takes its values on the command line:

<!-- docs-test: continue -->
```bash
vixl -p card-post.vixl render --set name='Wool Blanket' --set price='$58' --out blanket.png
```

## A finished design in more sizes

When the master is a finished document rather than a recipe (a design you placed by hand, or imported from SVG, PDF
or Figma), `adapt-layout --sizes` writes one adapted copy per size and runs the document's check suites on each:

<!-- docs-test: continue -->
```bash
vixl -p card-post.vixl adapt-layout --sizes facebook-post pinterest-pin --directory more-sizes
```

Each copy is an editable `.vixl`; run the same `render --data` on it. Review extreme changes of shape by eye
([sizes and layouts](../layout/sizes-and-layouts.md)).

## Layouts and templates for the common jobs

| Job | Start from |
| --- | --- |
| Link preview (Open Graph) image | `split-screen`, `golden-section`, `bento-grid` or `banner` at the `og-image` size |
| Product card | `product-card` |
| Certificate | the `print-certificate` template, or the `framed` and `centered-axis` layouts at the `certificate` size |
| Quote card | `quote-card`, or the `social-quote` template |
| Event ticket | `event-poster` at the `ticket` size (1650×600): name, date block, details, an admission line and a number; there is no dedicated ticket layout with a stub yet |

`vixl layout show NAME` lists a layout's slots, and `vixl template list` the templates.

## Beyond a CSV and a folder

- **Named outputs, several formats, a colour matrix, held failures:** the `run` workflow takes rows, artboards and
  variation axes in one spec and writes a `production.json` report ([variant production](production.md#variant-production-and-draftfinal)).
- **A price list that changes:** `data-sync` re-renders only the documents whose rows changed.
- **A delivery zip with checksums and a proof page:** [delivery packages](production.md#delivery-packages).
- **Sheets of cards, badges or labels for print:** [imposition and merge](../output/imposition.md).
- **An HTTP endpoint inside your own app:** `vixl serve` and `vixl host` expose the same operations over REST
  ([interfaces](../../reference/interfaces.md)), and `vixl mcp` gives them to an agent.
- **Pull requests:** check documents in CI with the [GitHub Action](ci.md).

## What you take on, and what you get

Moving the rendering onto your machine changes who does what. This comparison is about the kind of tool, not about
any one service.

| | A hosted template API | Vixl, run locally |
| --- | --- | --- |
| Cost model | Usually metered per render or per month | No per-render charge; you supply the machine |
| Where files go | The service stores them and returns URLs | A folder you choose; you host and serve them |
| Template editor | A visual editor in the browser | No editor: an agent, the CLI or a recipe builds the template, and people review in the live viewer |
| Your data | Sent to the service with each call | Stays on your machine; nothing is uploaded |
| Operations | The service runs and scales it | You run it: fonts, storage, scheduling and retries are yours |
| Output | Images, often PDF and video | PNG, JPEG, WebP, SVG, PDF and PPTX, plus the editable `.vixl` master |
| Quality control | You look at the results | Measured checks per row, and suites you write once and keep |
| Sizes | Usually one template per size | One recipe at many sizes, or adapted copies |

If you need a browser editor for non-technical colleagues, public image URLs generated on request, or someone else
to run the service, a hosted API remains the better fit. Vixl's own limits are listed under
[Is Vixl a fit?](../../getting-started.md#is-vixl-a-fit), and the licence under [licensing](../../reference/licensing.md).
