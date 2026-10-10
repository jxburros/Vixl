# Marketing build options

Use `p.check(checks=["deck"], deck={"profile": "phone"})` for a carousel,
`profile="screen"` for a PDF read on a laptop, and `profile="projected"` for
slides shown to an audience. Instagram named sizes infer `phone`; other documents
default to `projected`. Explicit settings always take precedence.

| Profile | Minimum text | Word limit | Reading width |
| --- | --- | --- | --- |
| projected | 18 points on the slide | 60 | 320 px thumbnails |
| screen | 14 px at reading width | 250 | 1280 px |
| phone | 12 px at reading width | 150 | 540 px |

`deck.min_font` overrides the minimum in the profile's units. Screen and phone
profiles omit the projected type-scale advice unless requested explicitly. When
`legibility` is requested, phone covers use a 320 px grid preview and inner pages
use 540 px. Explicit `thumbnail_width` and `min_thumbnail_text` reach every page.
Single-page `og-image` and `x-post` checks default to 600 px previews.

Gradients that fade to transparency at an edge are inferred as decoration for
bounds/overlap checks (radial gradients use their outside edge). Explicit
`layer-intent role=content` opts back into those findings. Intentional clipping is
still reported as information.

To reduce embedded image size while preserving placement, use `downsample="placed@2x"`
or `max_pixels` on `add` and `frame` operations:

```python
p.apply({"type": "frame", "path": "photo.jpg", "name": "photo",
         "width": 490, "height": 255, "downsample": "placed@2x"})
```

`placed@2x` retains enough resolution for the frame's fill/fit mode and never
upscales. `max_pixels` caps the embedded pixel area and may reduce that resolution
further. The source path, checksum, original size and embedded size are recorded
in provenance; the original file remains untouched. Saving drops unreferenced
assets, while assets referenced by retained history stay available for undo.

**Sources above the pixel limit.** With `max_pixels` or `downsample`, the source may be up to four times the pixel
limit (160 MP under the default 40 MP `--max-pixels`, so a 108 MP camera file imports); it is shrunk while it is
decoded. Without a `width` and `height` such a layer takes the embedded size. `vixl import`, `vixl_import_image` and
the REST import downsample a source above the limit to fit it on their own and report `downsampled` and a warning.
A plain `add` of such a file fails with `resource_limit`, naming the size and both remedies (`max_pixels`, or a higher
`--max-pixels`).

## Example: the marketing kit

[`marketing/build.py`](../marketing/build.py) builds Vixl's own marketing kit with Vixl 0.21.0
in about a minute on a 4-core machine. It checks the 1080 × 1350 carousel with
`deck={"profile": "phone"}` and the pitch deck, which is read on screen rather than projected,
with `deck={"profile": "screen"}`. Its dot grids are marked `layer-intent role=decoration`, and
the strikethrough bars on its timing slide use `allow_overlap`, so the remaining findings are
informational or deliberate. Its copy quotes counts taken from the 0.21.0 registries:
180 operation types, 150 named sizes, 53 layouts, 40 templates, 19 containers, 28 styles,
17 looks and 17 brushes. [`marketing/README.md`](../marketing/README.md) says how to recount them.

The kit places captions and code against other layers with `Project.bounds(name)`, the layer's
`(x, y, width, height)` on the canvas even when it sits in a group (what `inspect()` reports as
`canvas_bounds`). `Project.bounds(name, space="parent")` gives the box in its group's own
coordinates instead. Do not measure with `vixl.render.resolve_layout`: it is internal, and its boxes
for grouped layers are relative to the group, so a layer placed against them lands in the wrong
place without an error.
