# Rich text

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Visual gallery](../../gallery.md)

One text layer can mix styles: bold or italic words, a coloured number, an underlined term,
bullet and numbered lists with indent levels, and paragraph spacing. Rich text is shaped with the
same HarfBuzz pipeline as plain text, so it renders identically in PNG, SVG (as vector outlines),
and in the PDF and PowerPoint exports, where its spans become real text runs.

```bash
vixl rich-text '# Results\nRevenue grew **42%** to [$1.2M]{color=#d33}\n- Faster *checkout*\n- New markets\n  - Brazil' \
  --name body --size 28 --width 900 --x 80 --y 120
vixl text-style body --match 42% --color '@accent' --bold
vixl text-style body --paragraphs 2,3 --space-after 8
```

```json
{"type": "rich-text", "name": "body", "markdown": "Hello **world**", "size": 32, "width": 600, "x": 40, "y": 40}
{"type": "rich-text", "name": "quote", "spans": [{"text": "Make it "}, {"text": "simple", "italic": true, "color": "#c33"}],
 "paragraphs": [{"align": "center"}]}
{"type": "text-style", "target": "body", "match": "world", "underline": true}
```

## Markdown

Each line is one paragraph.

| Write | Get |
| --- | --- |
| `**bold**`, `*italic*` or `_italic_`, `***bold italic***` | bold, italic |
| `__underline__`, `~~strike~~`, `==highlight==` | underline, strikethrough, yellow highlight |
| `x^2^`, `H~2~O` | superscript, subscript |
| `[text]{color=#e33 size=40 font=heading bold italic underline highlight=#ff0 tracking=2}` | any combination of styles |
| `[Winter]{accent}`, `[Sale]{accent-bg}` | the palette's accent text color; accent ink on an accent highlight |
| `[note]{small-caps}` | small capitals |
| `- item`, `* item`, `+ item` | bullet; indent two spaces (or a tab) per level |
| `1. item` | numbered; the first number sets the start, levels count 1. / a. / i. |
| `# `, `## `, `### ` | bold heading at 1.6×, 1.3× or 1.15× the size |
| `\*` | a literal marker character |

## Character styles

Spans override the layer's own font, size and color; anything a span leaves out follows the
layer, so `text-set --color` or `--size` restyles the whole box and keeps the emphasis (spans that set
their own value keep it; `text-set` warns when that happens). The `fonts` check follows the font each run
of text is drawn in: rich text whose visible spans all set a registered `font` is not flagged as using the
bundled fallback, and fallback glyphs are checked against each span's own font.

| Style | Values |
| --- | --- |
| `bold`, `italic`, `underline`, `strike` | true or false |
| `color`, `highlight` | any color, including `@swatch` |
| `size` | pixels |
| `font` | a registered font name, `heading`, `body` or a font file |
| `baseline` | `super`, `sub` or `normal` |
| `tracking` | extra pixels between letters (negative tightens) |
| `small_caps` | true or false: lowercase letters as small capitals ([typography](typography.md#small-caps)) |

**Accent words.** The `accent` flag sets a word in `@accent-text`, the palette color made for accent type that reads
on the background, and `accent-bg` sets it in `@on-accent` on an `@accent` highlight. Both name palette roles, so the
document needs them first (`palette-apply` with roles, `layout-apply` or a rolled direction); without them the
operation is refused and says so. To accent words of plain text without writing Markdown, give `text` or `text-set`
`accent_words`: whole words, matched without regard to case (`winter` matches "Winter" but not "winterland"), become
`@accent-text` spans of rich text, and words that are not found are listed in the warnings. A layer already set in an
accent color is left alone with a warning. `accent`, `accents` and `highlight_words` are accepted for `accent_words`.

```json
[{"type": "palette-apply", "name": "slate"},
 {"type": "text", "name": "headline", "text": "Winter warmers on the quay", "size": 64, "x": 60, "y": 60,
  "accent_words": ["winter"]},
 {"type": "rich-text", "name": "note", "markdown": "Doors at [seven]{accent}, [free entry]{accent-bg}", "size": 28,
  "x": 60, "y": 180}]
```

**Tracking goes between letters, not after the last one on a line.** A tracked line measures from its first
glyph to its last, so auto-sized boxes, wrapping, `center` and `right` alignment and centring the layer on the
canvas all follow the ink; PNG, SVG, PDF and PPTX draw it the same way (PPTX writes the line's last letter as a
run without `spc`). Scaled previews and linked documents scale tracking with the size. To letter-space a whole
layer, set the layer's `tracking` with `text` or `text-set` ([typography](typography.md#letter-spacing-and-edits)).
The first `text-style` on a plain layer turns it into rich text that keeps the plain text's box (its top at the
ink; `ink_box: true` in the record) and line pitch, so styling it does not move it. `spacing` on `text` is the
gap between lines, not letters.

**Glyphs are never cut off at the box.** Script swashes, italic and synthetic-oblique slants, synthetic bold and
outlines can reach past the advance widths and line boxes that size the layer. The layer box stays the layout
box (alignment, wrapping, `inspect` bounds and constraints use it), and the ink that reaches past it is drawn
on a padded canvas in PNG and previews and inside a widened viewport in SVG. Lines that overflow a fixed
`width`/`height` box below its bottom are still cut off at its edge (the `bounds` check reports them).
`inspect` reports the ink as `ink_bounds`.

**Bold and italic use real fonts when they are installed.** For a layer in `inter-400` (the
name `font install` gives), bold uses `inter-700` (or 800, 600, 900) and italic uses
`inter-400-italic`; set `font_variants: {"bold": NAME, "italic": NAME, "bold_italic": NAME}` for
other names. Without a variant, Vixl draws a synthetic bold (an outline in the text color) or a
synthetic oblique (a 12° slant). Install real styles for finished work:
`vixl font install Inter --weight 700`.

## Paragraphs and lists

`paragraphs` holds one object per line of the text:

| Setting | Meaning |
| --- | --- |
| `list` | `bullet`, `number` or `none` |
| `level` | 0–8. Bullets cycle •, ◦, ▪, ‣; numbers cycle 1., a., i. |
| `start` | The first number of a numbered list (`number_start` in `text-style`). |
| `align` | `left`, `center`, `right` or `justify` (every line but a paragraph's last). `paragraph_align` in `text-style`. |
| `space_before`, `space_after` | Pixels above and below the paragraph. |
| `indent` | Pixels the whole paragraph moves right. |
| `line_height` | Line height for this paragraph, as a multiple of the font size (see below). |

Box-wide settings: `line_height` (a multiple of the font size, the distance between baselines; by default the
line-height table in [typography](typography.md#default-size-and-leading): 1.45 for body text, 1.1 for headings), `paragraph_spacing` (pixels after each paragraph, 0) and
`list_indent` (pixels per list level and for the marker column, 1.4 × the size). Wrapped list
lines hang under the text, not the marker. Rich text made before 0.23 has no `line_basis` and keeps its
old rule (1.2 times the font's own line pitch, plus the layer's `spacing`), so saved documents look the same.

## Boxes and fitting

`width` wraps lines; `height` fixes the box (leaving it out sizes the height to the text). `wrap` chooses how the
lines break: `greedy` (default), `balance` (even line widths, the same line count; for headings) or `pretty` (no
one-word last line; for body text), as for plain text ([line breaking](typography.md#line-breaking)). With
`fit: true` every size, indent and spacing shrinks together until the text fits both dimensions.
Without a width the layer sizes itself to its longest line. The `bounds` check reports rich text
that overflows a box without `fit`.

## Editing

Which operation to use: **`text-set` changes the whole layer** (its text, color, size, font,
alignment, spacing, stroke) and **`text-style` styles parts of it** (a phrase, a character range,
paragraphs). `text-style` styles part of a text layer (plain text layers become rich the first time):

- `match` with `occurrence` (a number, or `all`, the default), or `start`/`end` character offsets;
  without either, the whole text. On a plain layer, a `text-style` with no range that only sets
  `color`, `size` or `font` acts as `text-set` (no spans are made; the result's `normalized` says so).
- Character styles as above; `false` or `normal` removes one; `clear: true` removes them all.
- Paragraph settings for `paragraphs` (a list of indices, or `all`).

Passing one operation the other's fields fails with a message that names the right operation.

`rich-text --target` replaces a layer's content and formatting. `text-set --text` on a rich layer
keeps what still applies: lines are matched, so bullets, numbering, alignment and spacing stay with
their line (a new line continues the list above it), and words are matched, so unchanged words keep
their styles while new words take the style of the words they replace or follow. The result's
`warnings` names what could not carry over (the style of a deleted phrase, the settings of a
deleted line) and whether spans keep their own color, size or font after `text-set --color`,
`--size` or `--font` (they override the layer; use `text-style` without a range to restyle all of
the text). Variables (`${name}`) work inside spans and keep the span's formatting, including page
numbers (`${page}`) on a master. A timeline that keyframes `text` draws those frames as plain text.

Warped text (`text-layout --warp`) and text on a path draw plain text only.
# Whitespace and inspectable metrics

Plain `text` and rich-text spans preserve authored leading spaces and nonbreaking
spaces. Tabs advance to four-character stops, including across adjacent styled spans.
Automatic wrapping may discard an ordinary separator at a line break. Markdown
still interprets indentation for nested lists; use spans for literal code samples.

`Project.inspect(target)` reports `ink_bounds`, `line_bounds`, `baseline`,
`baselines`, `ascent`, `descent`, `cap_height` and `x_height` for both text kinds.
Bounds are `[x, y, width, height]`; baselines are y coordinates. These metrics use
unrotated parent coordinates (`metrics_space="unrotated-parent"`) and pixels.
The historical `resolved_bounds` continues to describe the layer's own layout box.
Line boxes include font ascent/descent and line spacing, while ink boxes measure
glyph outlines. Brief apply results include the new text geometry as well.
