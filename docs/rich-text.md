# Rich text

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
| `- item`, `* item`, `+ item` | bullet; indent two spaces (or a tab) per level |
| `1. item` | numbered; the first number sets the start, levels count 1. / a. / i. |
| `# `, `## `, `### ` | bold heading at 1.6×, 1.3× or 1.15× the size |
| `\*` | a literal marker character |

## Character styles

Spans override the layer's own font, size and color; anything a span leaves out follows the
layer, so `text-set --color` or `--size` restyles the whole box and keeps the emphasis.

| Style | Values |
| --- | --- |
| `bold`, `italic`, `underline`, `strike` | true or false |
| `color`, `highlight` | any color, including `@swatch` |
| `size` | pixels |
| `font` | a registered font name, `heading`, `body` or a font file |
| `baseline` | `super`, `sub` or `normal` |
| `tracking` | extra pixels between letters (negative tightens) |

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
| `line_height` | Multiple of the line's natural height for this paragraph. |

Box-wide settings: `line_height` (1.2), `paragraph_spacing` (pixels after each paragraph, 0) and
`list_indent` (pixels per list level and for the marker column, 1.4 × the size). Wrapped list
lines hang under the text, not the marker.

## Boxes and fitting

`width` wraps lines; `height` fixes the box (leaving it out sizes the height to the text). With
`fit: true` every size, indent and spacing shrinks together until the text fits both dimensions.
Without a width the layer sizes itself to its longest line. The `bounds` check reports rich text
that overflows a box without `fit`.

## Editing

`text-style` styles part of a text layer (plain text layers become rich the first time):

- `match` with `occurrence` (a number, or `all`, the default), or `start`/`end` character offsets;
  without either, the whole text.
- Character styles as above; `false` or `normal` removes one; `clear: true` removes them all.
- Paragraph settings for `paragraphs` (a list of indices, or `all`).

`rich-text --target` replaces a layer's content. `text-set --text` with new text replaces the
styled spans with plain text; restyle it afterwards. Variables (`${name}`) work inside spans. A
timeline that keyframes `text` draws those frames as plain text.

Warped text (`text-layout --warp`) and text on a path draw plain text only.
