# Text flow frames

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

A long text can flow through a chain of linked text frames: columns inside one frame, a frame per page of a
multi-page document, or frames that follow a shape. When a frame is full the text continues in the next one. Edit
the text or resize a frame and the whole chain re-flows. Plain and [rich text](rich-text.md) both work, and rich
styling survives the split.

```bash
vixl text-flow create article --markdown "$(cat article.md)" --size 16 --x 60 --y 80 --width 1000 --height 700 --columns 2 --gutter 40
vixl page add page-2 && vixl text-flow add-frame article --x 60 --y 80 --width 1000 --height 700 --columns 2 --page page-2
vixl check --checks flow
```

```json
{"type": "text-flow", "name": "article", "markdown": "# Title\nBody …", "size": 16, "keep_together": true, "orphans": 2, "widows": 2,
 "frames": [{"x": 60, "y": 80, "width": 1000, "height": 700, "columns": 2, "gutter": 40},
            {"x": 60, "y": 80, "width": 1000, "height": 700, "columns": 2, "page": "page-2"}]}
{"type": "text-flow", "name": "article", "action": "set", "text": "A shorter story."}
```

## Design: frames hold the laid-out slice

Every frame is an **ordinary text layer** (`text-layout` box, fixed size) whose `text` (and `rich` record) is the slice of
the story that fits it. The story itself, the chain and the paragraph rules live in `state.flows`. Flowing is a
step Vixl performs when the story or a frame changes; it does not add a new kind of layer.

Why this design: PNG, SVG, PDF and PowerPoint export already draw text layers from their own text and layout code.
With one text layer per frame, every exporter produces the frames exactly as it produces any other text boxes (selectable
PDF text, real PowerPoint text frames, SVG outlines) with no flow-specific code in any of them, and every other
operation keeps working: `move`, `resize`, effects, `layer-style`, timelines, checks. The alternative (a single layer that
draws text into several boxes) would have needed changes in the renderer and in each exporter.

The slices are computed with the same engine that draws them: for each frame Vixl finds the longest run of whole words
that the frame's font, size, width and height lay out within its height (the measure the `bounds` check uses). A slice
starts at the start of a line of the continuous text and ends at the end of one, so the frames wrap exactly like the
unbroken text would, and every character of the story lands in exactly one frame (the whitespace at a break is dropped).
`flows[name].ranges` records `[start, end]` per frame.

## Operations

`text-flow` takes an `action` (default `create`, or `set` when the flow exists) and a flow `name`.

| `action` | Fields | What it does |
| --- | --- | --- |
| `create` | the story, the frame(s), the style, rules | Creates frames named `<flow>-1`, `<flow>-2`… and fills them. |
| `set` | any of the story, style or rule fields; `frame` plus `x`/`y`/`width`/`height`/`columns`/`gutter` to reshape a frame | Changes the flow and re-flows. |
| `add-frame` | frame fields, `frames`, or `layers`; `after`/`before` | Adds frames to the chain (default: the end). |
| `link` | `layers` (existing text layers), `after`/`before`; `width`/`height` for one unboxed layer | Joins existing text layers to the chain. |
| `unlink` | `frame` (a number, or a layer ID/name) or `layers`; `delete_frames` | Takes frames out of the chain. They keep the text they hold; the rest re-flows around the gap. |
| `reflow` | | Re-flows now (this also happens automatically, see below). |
| `style` | `match`/`start`/`end`/`paragraphs`, `format` | Styles words or paragraphs of the story (the `text-style` fields: bold, italic, color, list …). |
| `delete` | `delete_frames` | Removes the flow. The frames stay as plain text layers holding their text, or are removed. |

**The story**: `text` (plain), `markdown` or `spans` + `paragraphs` (rich, same syntax as `rich-text`), or `target`: an
existing text layer whose text and style become the story and which becomes the first frame. Tabs become spaces.
`${variables}` are not expanded while flowing, so write literal text. The story holds up to 100,000 characters.

**Frames**: `{x, y, width, height}` makes one frame. Add `columns` and `gutter` (default 1.5× the font size) to split the
frame into equal columns; each column is a text layer and one link in the chain. `page` puts the frame on another page of a
multi-page document (the active page is restored afterwards). `layer` uses an existing text layer. `shape` follows a shape
layer: with `mode: "bands"` (default) one-line frames follow the outline top to bottom (a circle gets short lines at the top,
long ones in the middle), with `mode: "inscribed"` one frame fills the largest rectangle that fits inside the shape;
`inset` keeps text away from the edge. At the top level of the operation, `x`, `y`, `width`, `height`, `columns`, `gutter`
and `page` are a shorthand for one frame.

**Style**: `font`, `size`, `color`, `align` (`left`, `center`, `right`, or `justify`, which makes the story rich), `spacing` (extra
leading in px) or `line_height` (a factor), `stroke_width`, `stroke_color`, and for rich text `paragraph_spacing`, `list_indent`.
A flow's frames share the style; a frame layer's own font or size, if you change them, are respected by the flow.

**Paragraph rules**: `keep_together` (a paragraph that fits one frame is never split between two), `orphans` and `widows` (the
fewest lines of a split paragraph left at the bottom of a frame, or carried to the top of the next; default 1, so no rule),
and `keep_with_next` (default true for rich text: a heading is never the last thing in a frame).

## Re-flow and overflow

The chain re-flows at the end of any batch in which the story, a frame's `width`, `height`, `font`, `size`, `spacing`, `align`
or the text of a frame changed, or a frame layer was removed. Moving a frame does not re-flow it. Re-flows
caused by other operations (`resize`, `text-layout`, `text-set`, `remove`) are reported like the flow's own.

**The flow owns its frames' text.** To edit the story use `text-flow set` or `style`; a `text-set` on a frame is overwritten
at the next re-flow (and `check --checks flow` warns about it).

Text that does not fit the last frame is **overflow**. The operation result carries, per flow:

```json
"text_flow": {"article": {"overflow": true, "remaining_chars": 532, "remaining_words": 83, "from": 2142,
  "frames": [{"layer": "article-1", "chars": 702, "page": "page-1"}, …], "empty_frames": [], "rich": false}},
"warnings": ["Text flow 'article' overflows its last frame: 532 characters (83 words) do not fit. …"]
```

`vixl check` (the `flow` check, on by default) reports overflow as an **error** with `remaining_chars`, a frame too small to hold
a line as an error, and frames that stay empty because the story ended, or that were edited by hand, as warnings.

## Rich text through the split

Spans are cut at the break and keep every style. Paragraph settings (alignment, spacing, indents, lists) follow their
paragraph. A paragraph that continues in the next frame shows no bullet or number again and keeps its indent, and
numbered lists carry on counting where they left off. Justified text does not stretch the last line of a frame, because
that is the end of the slice, not of the paragraph.

## Limits

* One flow holds at most 200 frames. Frames of different widths and sizes work; orphan and widow lines are counted at the
  width of the frame the split paragraph starts in.
* Band frames hold one line each and never split a word that is wider than the band; the word moves to the next band.
* A word wider than an ordinary frame is broken across lines as plain text does.
* Frames of a flow on pages the checked page does not show are only checked when their page is checked.
