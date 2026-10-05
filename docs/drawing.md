# Hand drawings

Bring in a photo or scan of a hand drawing and build on it: clean it up, trace it into editable
strokes, straighten what should be straight, close gaps, colour the shapes, add new lines in the
same hand — while keeping as much of the original drawing as possible, and measuring how much was
kept.

![A photographed sketch, cleaned, straightened and coloured, and compared with the original](drawing-pipeline.png)

```bash
vixl drawing import sketch.jpg --name house          # clean lines over a hidden copy of the photo
vixl drawing vectorize house                         # editable strokes house/s001 … (ink hidden)
vixl drawing straighten house --settings '{"close_gaps": 30}'
vixl drawing report house                            # how much is kept, stroke kinds, regions to fill
vixl drawing fill house --points '[[1324, 211, "#ffd23f"], [916, 675, "#9ad1f5"]]'
vixl drawing stroke house --points '[[960, 330], [960, 230], [1010, 230], [1010, 360]]'
vixl drawing compare house --out compare.png         # the original in red under the result in blue
vixl check --checks drawing                          # warns when original lines were lost
vixl ai drawing-color house --prompt "soft watercolour, late afternoon light"   # optional, with a provider
```

```json
{"type": "drawing", "action": "import", "asset": "assets/…png", "name": "house"}
{"type": "drawing", "action": "straighten", "target": "house", "strokes": ["house/s003"], "settings": {"angles": [0, 90]}}
```

Through MCP, import the photo with `vixl_import_image` and pass its `asset`; `vixl_workflow`
actions `drawing-report` and `drawing-compare` return the report and write the comparison image.

## What a drawing is

`drawing import` creates a group (named by `name`) whose content is the cleaned drawing's pixel
grid. It holds:

| Layer | What it is |
| --- | --- |
| `NAME/original` | The photo, tilted and cropped like the cleaned lines; hidden. Show it to trace over the original. |
| `NAME/ink` | The cleaned lines. Hidden once the drawing is vectorized (`keep_ink` keeps it). |
| `NAME/s001` … | Strokes: editable path layers along the centre of each line, longest first. Each records its points, width and what was done to it (`traced`, `added`, `line`, `polyline`, `circle`, `smoothed`). |
| `NAME/fill-1` … | Colour under the lines. |
| `NAME/color` | An AI colouring under everything else (`ai drawing-color`). |

The group moves, scales and checks like any group; the photo as imported stays in the document
so the drawing can be cleaned again with other settings. `x`, `y`, `width` or `height` on import
place and size it (default: centred, at most 90% of the canvas).

## Actions

| Action | Does | Settings |
| --- | --- | --- |
| `import` | Cleans a photo or scan into lines: divides out the paper's lighting and shadows, separates ink from paper, removes dust, corrects a tilted page, crops to the drawing, and keeps the pencil's own grain and anti-aliasing. | `threshold` (`auto` or 0–1), `sensitivity` (−1–1: higher finds fainter lines), `despeckle` (`auto` or the smallest mark in pixels), `weight` (−10–10 pixels thinner or bolder), `deskew` (true), `crop` (true), `margin` (24), `soft` (true), `ink` (a colour, or `original` to keep the pencil's own colour), `flatten` (true), `max_size` (2400) |
| `clean` | Cleans again with other settings. Once there are strokes or fills, the tilt and crop stay as they are so everything stays aligned. | as `import` |
| `vectorize` | Traces each line along its centre into a stroke with the line's width (`centerline`), or the lines' outlines into one filled shape that keeps every change of pressure (`outline`). | `mode`, `min_length` (6), `detail` (0.75 px of simplification), `max_strokes` (240; the rest share `NAME/detail`), `keep_ink`, `color` |
| `straighten` | Lines that are nearly straight become straight; shapes made of straight sides keep their corners where they were drawn but get sharp corners and straight sides; nearly round closed shapes become circles; sides snap to `angles` when close; ends that nearly meet are joined. | `tolerance` (4 px: how far a line may wander and still count as straight), `angles` ([0, 45, 90, 135], `guides` for the document's guide angles, or `none`), `angle_tolerance` (6°), `circles` (true), `polylines` (true; false keeps everything but single lines and circles as drawn), `corner` (24 px: shorter sides are rounded corners), `close_gaps` (0: join ends this close) |
| `smooth` | Evens out shaky strokes, keeping their ends. | `amount` (0–1) |
| `fill` | Colours the region around each point, under the lines. Small breaks in an outline are bridged; the fill reaches into every corner without crossing a line. | `points` [[x, y, colour], …] (canvas positions), `gap` (6 px of break to bridge), `min_area`, `under` (true) |
| `stroke` | Adds a stroke in the drawing's hand: its width and colour, smoothed through the points. | `points` [[x, y], …] (canvas positions), `width`, `smooth` (true), `closed`, `color`, `name` |
| `restyle` | Recolours strokes or changes their width. | `color`, `width` or `width_scale` |

`straighten`, `smooth` and `restyle` take `strokes` (layer names, or `all`, the default) so a
direction such as "straighten the walls but leave the tree alone" touches only those strokes.
Stroke layers are ordinary path shapes: move, remove, recolour or reorder them like any layer.

## Keeping the drawing

The cleaned lines at import are the reference. `drawing report` (and the `drawing-report`
workflow action) returns:

- `preserved` — the share of the original lines the current drawing still covers (within about
  a line's width);
- `added` — the share of the current lines that is new;
- `stroke_kinds` — how many strokes were straightened, rounded into circles, smoothed or added;
- `regions` — the closed regions with a point inside each, ready for `fill`.

The `drawing` check (opt-in: `check --checks drawing`) warns when a drawing keeps less than 90% of
its original lines (an error below 70%) or when more than a third of it is new. `drawing compare`
draws the original lines in red under the current ones in blue — purple where they agree — so the
change is visible at a glance.

## AI colouring

`vixl ai drawing-color DRAWING --prompt TEXT [--strength 0.6] [--provider NAME]` sends the drawing
as drawn so far (fills and lines on white) to an image-to-image provider and places the result as
`NAME/color` under the drawing's own fills and lines, so every line stays exactly as drawn and the
preservation report is unchanged. Python: `vixl.drawing.ai_color(project, "house", prompt,
backend)`. It needs a configured provider that supports image-to-image (see
[providers](providers.md)).
