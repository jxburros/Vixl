# Pages, slides and decks

A document can hold several pages: slides in a deck, frames of a social carousel, the pages of a
booklet or a multi-page form. Each page has its own layers; the canvas size, fonts, swatches,
styles, palettes, brushes, guides and variables are shared. Master pages hold layers drawn under
every page that uses them (a footer band, a logo, a page number). Pages carry speaker notes, and
the whole document exports as a multi-page vector PDF with selectable text or as an editable
PowerPoint deck.

```bash
vixl new 1920x1080 -o deck.vixl --background '#ffffff'
vixl master add std --background '#f6f4ef'                     # edit the master …
vixl shape --shape rectangle --name band --width 1920 --height 24 --x 0 --y 1056 --fill '#1d3557'
vixl text add '${page} / ${pages}' --name num --size 24 --x 1780 --y 1010
vixl page add cover --master std                               # … then the pages
vixl text add 'Quarterly Review' --name title --size 120 --x 140 --y 380
vixl page add results --master std --notes 'Revenue up 42%; mention Brazil.'
vixl text add Results --name title --size 80 --x 120 --y 90
vixl rich-text 'Revenue grew **42%**\n- Faster *checkout*\n- New markets' --name body --size 44 --width 900 --x 120 --y 240
vixl pages                                                     # list pages and masters
vixl render --page all --out sheet.png                         # every page on one contact sheet
vixl check --checks deck                                       # every page + deck-wide checks
vixl export deck.pdf                                           # vector PDF, one page per page
vixl export deck.pptx                                          # editable slides with speaker notes
```

```json
{"type": "page", "action": "add", "name": "results", "master": "std", "notes": "Revenue up 42%"}
{"type": "text", "text": "Results", "name": "title", "size": 80, "page": "results"}
```

## How pages work

A document starts as one canvas. The first `page add` turns it into a page list: whatever the
document already holds becomes `page-1` (a blank document's untouched starting page simply takes
the new page's name and settings instead), and the new page is added after the active page.

Exactly one page — or one master — is *active*, and every operation edits it, so all the usual
operations work on pages unchanged. `page select` switches, and **any operation accepts a `page`
field** (a name or a 1-based number) that selects that page first. Layer IDs are unique across
the whole document.

| Action | Fields | |
| --- | --- | --- |
| `add` | `name`, `after` / `before` / `index`, `duplicate`, `master`, `notes`, `background`, `variables`, `hidden`, `transition`, `select` (true) | `duplicate` copies a page's layers (with new IDs), notes and settings. A new page uses the master named `default` when there is one. |
| `select` | `page` | |
| `remove` | `page` | A document keeps at least one page. |
| `move` | `page`, `index` / `after` / `before` | |
| `set` | `page`, `rename`, `notes`, `master` (`none` detaches), `background`, `variables`, `hidden`, `transition` | |

Page settings:

- `notes` — speaker notes (plain text, up to 50,000 characters). They are exported to PowerPoint
  notes and counted by the deck checks, never drawn.
- `background` — overrides the canvas (or master) background for this page.
- `variables` — page-specific values for `${name}` text, on top of the document's variables.
- `hidden` — left out of PDF export, previews of `all` pages, the deck checks and per-page image
  export; exported to PowerPoint as a hidden slide.
- `transition` — `fade`, `push`, `wipe`, `cover`, `split` or `zoom` in PowerPoint.

Built-in variables: `${page}` (the page number), `${pages}` (the page count) and `${page_name}`.

## Masters

`master add NAME` creates a master and selects it, so the next operations draw its layers;
`--from PAGE` starts it from a copy of a page. `master set NAME --rename … --background …`,
`master select NAME` and `master remove NAME` (pages using it lose their master). A page with a
master draws the master's layers first, underneath its own, and uses the master's background
unless it has its own. When a master layer and a page layer share a name, the master's is shown
as `master:NAME/layer` in renders and checks.

## Seeing pages

- `vixl render --page 2 --out p2.png` (a number or name); `--page all` renders a labelled contact
  sheet of every page (`--columns N`). Through MCP, `vixl_render_preview(page=…)`, where
  `page="all"` returns the sheet — the quickest way for an agent to review a whole deck.
- `vixl pages` / `inspect` list every page with its layer and word counts, master and notes.
- `vixl export slide.png --pages all` writes one numbered file per page (`slide-01.png` …) — a
  carousel; `--pages 1-3,5,intro` picks pages.

## PDF

`export deck.pdf` writes every shown page (or `--pages …`) to one PDF:

- **Vector content** (default, for every document and also with `--cmyk`): solids, shapes and paths, gradients (PDF shadings), plain groups
  and text become PDF graphics. Text — plain and rich — is real text in embedded TrueType subsets
  with Unicode maps, so it can be selected, searched and read aloud. Synthetic bold and italic
  are drawn as stroked and slanted text. Image layers are images. Anything PDF cannot draw the
  same way (effects, layer styles, masks, clipping, blend modes, adjustment layers, paint and
  pixel art, warped text) is embedded as an image of exactly what Vixl renders and listed under
  `raster_fallbacks` with the reason, so nothing changes appearance silently.
- `--pdf-content raster` writes each page as one image. The export result says which mode was
  written: `content` (`vector` or `raster`) and `content_reason` (`default…` or `requested with
  pdf_content`; scaled, proofed and profile exports are raster, with that as the reason). The
  default never depends on the kind of document, so re-exporting an edited copy gives the same kind
  of PDF as the first export.
- **Page size.** Pages of a multi-page document are the size of its PowerPoint slides: a canvas
  with a `dpi` keeps its physical size, a screen canvas is 7.5 inches tall, so 1920×1080 is
  13.33 × 7.5 in in both formats (`page_size` in the result shows it). `dpi` (`--dpi 96`) sets the
  pixels per inch of the PDF and of the slides alike (1920×1080 at 96 is 20 × 11.25 in). A single
  screen page is not a deck: its PDF keeps 1 pixel = 1 point unless `dpi` is given.
- Documents with bleed get a TrimBox and BleedBox. The file is byte-for-byte deterministic: the
  same document always produces the same PDF.

## PowerPoint

`export deck.pptx` writes one slide per page (`--pages` to choose; hidden pages become hidden
slides) that opens in PowerPoint, Keynote, Google Slides and LibreOffice:

- Text layers become text boxes with real runs: font family, size, colour, bold, italic,
  underline, strikethrough, highlight, superscript and subscript, paragraph alignment, spacing and
  line spacing, bullets and numbering with indent levels. Each slide's title (a text layer named
  `title`, `heading` or `headline`, else the largest text near the top) becomes the slide's title
  placeholder, so it shows in the outline and in accessibility tools.
- Rectangles, rounded rectangles, ellipses and lines become preset shapes; polygons, stars and
  paths become custom geometry; solid and linear/radial gradient fills and outlines carry over.
  Plain groups become groups.
- Image layers become pictures. Layers PowerPoint cannot draw the same way become pictures of
  exactly what Vixl renders and are listed under `raster_fallbacks`.
- Master layers are drawn on each slide (as ordinary shapes, so every slide matches the
  render). Speaker notes become the slide notes; transitions carry over.
- Slide size: canvases with a `dpi` keep their physical size; screen canvases become 7.5 inches
  tall (PowerPoint's standard height), so 1920×1080 is the usual 13.33 × 7.5 in 16:9 slide. The
  PDF of the same deck has the same page size; `dpi` overrides both (see [PDF](#pdf)).
- **Fonts are referenced by family name, not embedded.** PowerPoint embeds fonts as Embedded
  OpenType parts (`ppt/fonts/*.fntdata`); only PowerPoint itself can confirm such a part is
  acceptable, and a malformed one makes it offer to repair the file, so Vixl does not write them.
  The result lists every family under `fonts` and, for each one that is not a font every Office
  installation has (Arial, Calibri, Times New Roman …), a `warnings` entry and the family under
  `fonts_not_embedded`: install those fonts wherever the deck is opened or presented (PowerPoint,
  Keynote and Google Slides otherwise substitute another font and the layout shifts), or share the
  PDF, which embeds its fonts. In PowerPoint, *File → Options → Save → Embed fonts in the file*
  embeds them once they are installed.

## Deck checks

`check --checks deck` runs the design checks on every page (findings that repeat on several pages,
usually from a master, are reported once with every page listed) plus checks no single page can
see:

| Check | Finds |
| --- | --- |
| `title_position` | Titles on pages sharing a master that sit at a different left edge or height from the rest. The deck's first titled page (the cover) is exempt. |
| `type_scale` | Text sizes that are not on the document's type scale (its character styles, e.g. from `type-scale`), near-duplicate sizes (30 and 32 px), and more than six sizes in total. |
| `words` | Pages with more than `max_words` (60) words, excluding master layers and notes. |
| `min_font` | Page text smaller than `min_font` (18) points on the exported slide. Master layers and layers named footer, footnote, source, credit, page-number and the like are exempt. |
| `notes` | Some pages with speaker notes and some without. |
| `empty` | Pages with nothing of their own. |

`check --checks deck` uses the standard checks except `legibility` (which judges social-media
thumbnails; `min_font` replaces it). Name design checks alongside `deck` to choose them, or name
deck checks alone (`--checks words min_font`). Options: `--min-font`, `--max-words`, `--pages`,
`--include-hidden`; `--page` checks one page with the ordinary checks. Through MCP pass
`deck={"min_font": 24, "max_words": 40}` to `vixl_check`.
