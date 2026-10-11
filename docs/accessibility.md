# Accessibility

[Documentation home](README.md) · [Export guide](exporting.md) · [Slides](slides.md) · [Objects](objects.md)

Public-sector, education and enterprise readers often need decks, PDFs and web graphics that work with a
screen reader. Vixl keeps the information a reader needs in the document (alternative text, language, a
reading order) and writes it into every export, and the `accessibility` check finds what is missing.

## Describe images and mark ornaments

`layer-intent` sets `alt` on any image, frame, chart, link, object group or other non-text layer (text is read
as its own text), or `decorative: true` on an ornament a reader should skip. Layers with role `decoration` or
`background` count as decorative too.

```json
[
  {"type": "shape", "shape": "star", "name": "sparkle", "x": 40, "y": 40, "width": 60, "height": 60, "fill": "#fc0"},
  {"type": "layer-intent", "target": "sparkle", "decorative": true}
]
```

For an image: `{"type": "layer-intent", "target": "photo", "alt": "A fern in a clay pot on a windowsill"}`. An
empty `alt` removes it; `alt-text` is accepted as the operation name and `alt_text` or `description` for the
field. A group's alt text covers the layers inside it.

## Language, title, page description and reading order

```json
{"type": "accessibility", "lang": "en-GB", "title": "Field notes", "page_alt": "A poster about native ferns"}
```

- `lang` is the document language (any BCP 47 tag). Without one, HTML says `lang="en"` and PowerPoint
  `en-US`, and the check asks for it. The `form` operation's `lang` still works as a fallback.
- `title` is the document title of HTML, PDF, SVG and PowerPoint exports (default: the page's title layer).
- `page_alt` describes the active page as one picture (the whole artwork of a one-page document) and
  `page_lang` gives a page in another language. Both are kept per page.
- `reading_order: [layers…]` sets the order a reader meets the active page's text and described images; an
  empty list returns to top-to-bottom order. The HTML presenter's reading text follows it. PowerPoint and PDF
  readers follow the stacking order, so reorder the layers when those exports matter.

## What each export carries

| Export | Alt text | Language and title |
| --- | --- | --- |
| HTML (single image) | `alt` of the image: `page_alt`, else the title; the text layers and alt texts in a hidden caption | `<html lang>`, `<title>` |
| HTML presenter | Each slide's hidden reading text: its title as `<h2>`, `page_alt`, then text and image descriptions in reading order; the deck title is an `<h1>` | `<html lang>`, a slide `lang` for `page_lang` |
| SVG | `<title>` and `role="img"` on described layers, `aria-hidden="true"` on decorative ones; the document `<title>` and `page_alt` as `<desc>` | `xml:lang` |
| PowerPoint | `descr` on pictures, shapes, groups and native charts; decorative shapes carry PowerPoint's decorative flag | text runs, notes and charts in the document language (a slide's `page_lang` for its text); `dc:language` |
| PDF | `/Figure` marked content with `/Alt`, decorative layers as `/Artifact` | `/Lang`, document title |

A full tagged PDF (a structure tree with headings, paragraphs and figures in reading order) is not written
yet, so PDF reading order follows the stacking order and assistive technology that needs tags ignores the
marked content.

## The accessibility check

`vixl_check(checks=["accessibility"])` (CLI `vixl check --checks accessibility`) bundles:

| Finding | Action | What it means |
| --- | --- | --- |
| `contrast` | fix | WCAG contrast by text size (4.5:1, 3:1 for large text). |
| `color_vision` | fix / review | Text, chart series and legends that merge for protanopia, deuteranopia or tritanopia. |
| `language` | fix | The document has no language. |
| `missing-alt` | fix | A meaningful image, frame, link or chart has no alt text and is not decorative (a deck's untagged chart image is the classic case). |
| `text-size` | review | Text below 12 px on screen documents, or below 8 pt when the canvas has a dpi (print). |
| `color-only-chart` | review | A chart with two or more series and no value labels, unless marked `color_vision_safe`. |
| `reading-order` | review | Text whose stacking (export) order jumps against the visual order, on a page without an explicit `reading_order`. |

Each finding names its layers; `fix` findings fail the check.

```bash
vixl new 800x600 -o card.vixl
vixl text add "Field notes" --name title --size 48
vixl accessibility --lang en-GB --title "Field notes"
vixl check --checks accessibility
```
