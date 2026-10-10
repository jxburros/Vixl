# Marketing builds

The [Vixl marketing pack](../marketing/README.md) is a complete example of programmatic creative
production: social graphics, a carousel, a presentation, print handouts, a fillable brief, data and
workflow graphics, checked campaign variants, a motion teaser and an app animation family.
Its masters include embedded content and fonts. Build with `python marketing/build.py`, then run
`python marketing/verify.py` to inspect the delivered formats and source roundtrip.

## Reading profiles

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

The pack's deck uses the screen profile; use the projected profile and adjust type/word counts
before using it on a distant screen. Its carousel uses the phone profile. The builder refuses
exports with `fix` findings or failing saved suites, and retains the full reports next to the masters.
Public copy comes from [`marketing/copy.json`](../marketing/copy.json). Installed registry counts
are recorded automatically in the pack manifest as metadata.

## Decorative crops and embedded images

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

## Measuring layers

The pack places captions and code against other layers with `Project.bounds(name)`, the layer's
`(x, y, width, height)` on the canvas even when it sits in a group (what `inspect()` reports as
`canvas_bounds`). `Project.bounds(name, space="parent")` gives the box in its group's own
coordinates instead. Do not measure with `vixl.render.resolve_layout`: it is internal, and its boxes
for grouped layers are relative to the group, so a layer placed against them lands in the wrong
place without an error.
