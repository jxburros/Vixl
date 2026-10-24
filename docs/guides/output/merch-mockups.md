# Merch mockups and print-ready art

One call shows a design printed on a tee, a hoodie, a tote bag, a sticker, an enamel pin or a cap, and a second call
writes the files a printer needs for the same design: each area at its physical size, in spot-colour separations,
with a white underbase for dark garments. It is the `mockup` workflow of the `brand_kit` plugin (the
[linked documents](linked-documents.md#mockups) page explains the device mockups it started with) and the
`print-art` action that goes with it.

```json
{"mockup": "tee", "output": "tee.vixl", "place": {"front-chest": "logo.vixl", "back": "poster.vixl"},
 "garment_color": "#14161c", "finish": "screen", "export": ["png"]}
```

Every product is drawn as vector paths from a few measurements (`src/vixl/plugins/brand_kit/products.py`), so it is
licence-clean, crisp at any export scale and editable like any document. The garment is a flat lay, front and back in
one scene, with seams, stitching, ribbing and soft folds as separate shading layers over the base layers. Designs are
placed as live [links](linked-documents.md), so editing a design updates every mockup on its next render.

## Products

| Template | Scene | Areas (print size, mm) |
| --- | --- | --- |
| `tee` | Crew-neck t-shirt, front and back | `front-chest` (254 × 254), `full-front` (305 × 406), `back` (305 × 406), `sleeve-l` and `sleeve-r` (76 × 76), `hem-tag` (51 × 38), `inside-neck` (76 × 44) |
| `long-sleeve` | Long-sleeve tee with ribbed cuffs, front and back | the same seven areas |
| `crewneck` | Sweatshirt with ribbed collar, cuffs and waistband | the same seven areas |
| `hoodie` | Pullover with hood, drawstrings, kangaroo pocket and ribs; the hood lies flat behind the neck | the same seven areas; `inside-neck` is the lining of the hood |
| `tote` | Canvas tote bag with a double handle | `front` (280 × 330) |
| `sticker` | Die-cut sticker: the artwork with a white border and a soft shadow | `face` (76 × 76) |
| `sticker-kiss-cut` | Kiss-cut sticker on its backing sheet, the cut line showing around the artwork | `face` (76 × 76) |
| `enamel-pin` | Enamel pin on its backing card; a gold rim follows the artwork's outline | `face` (35 × 35), default finish `enamel` |
| `patch` | Embroidered patch with a merrow border, sewn on denim | `face` (76 × 76), default finish `embroidery` |
| `button` | Pin-back button under a glossy dome | `face` (57, round) |
| `cap` | Baseball cap seen from the front | `front-panel` (90 × 54) |
| `beanie` | Knitted beanie with a folded cuff | `cuff` (90 × 50) |
| `socks` | A pair of crew socks, flat | `sock-l` and `sock-r` (50 × 94) |
| `poster-wall` | Framed A3 poster on a wall (the slot also has a print size) | `poster` (297 × 420) |

`vixl_apply(workflow='mockup-list')` shows each template with its areas, their print sizes and its default garment
colour. An area's corners keep the aspect ratio of its print size, so a design looks on the product as it prints.
`sleeve-l` is the wearer's left sleeve, which is on the right of the front view.

## Placing designs

`place` maps area names to designs. Each entry is a workspace `.vixl` path, or `{design, fit, finish, source_page,
artboard}` to give that area its own settings. The design is clipped to the area's clip path (the torso, the sleeve,
the round face of a button) and fitted by `fit` as in any mockup: `fill` crops to cover the area (the default), `fit`
shows all of it and `stretch` distorts it. A bare `design` fills every slot of a template, or the first area of one that
has only areas (the front chest of a tee, the front of a tote, the face of a sticker; both socks), as the template's
`main` list says. An unknown area is refused with
the template's areas and the nearest names.

## Garment colour

`garment_color` (any colour: a name, `#hex`, `oklch(...)`) recolours the template's base layers, the garment, bag or
cap itself, and nothing else. Shading, seams and highlights are other layers (multiply and screen blends) above the
base, so the same drawing reads on white, on navy and on black; a dark garment keeps its form through soft light layers.
The area surfaces under the prints take the colour too. `mockup-list` shows each default colour, and a template without
one (a phone, a sticker) refuses the field. The mockup records the colour in its `mockup` record.

## Finishes

`finish` (for every placed design, or per area in `place`) gives the print the look of how it was made. A finish is an
ordinary stack on the placed design layer: effects and layer styles on the linked design, plus a few helper layers
(a thread hatch, a weave, a sheen) clipped to the design's own shape, so everything stays editable.

| Finish | What it adds |
| --- | --- |
| `screen` | ink that spreads a little into the weave (a soft blur and grain) and a fine dot-screen texture |
| `puff` | raised foam ink: emboss, more saturation, a soft shadow and a lift highlight |
| `embroidery` | diagonal stitch hatch, emboss, a satin sheen and a thread shadow |
| `enamel` | flat, saturated colour in a metal line, with a hard gloss |
| `woven` | a fine warp and weft over the art, a soft edge and a slight relief |
| `none` | leaves the print flat, even where the product has a default finish (the pin and the patch) |

The finishes are mockup looks: they are not in the general `look` operation and do not change the print files.

## Stickers, patches and pins

The sticker, kiss-cut, pin and patch templates have no fixed outline. After the design is placed they run
[`die-cut`](../../reference/operations.md) around its ink: a white vinyl border for the die-cut sticker, a thin cut line
on the backing sheet for the kiss-cut one, a gold gradient rim for the pin and a dark merrow border for the patch.
The cut shape sits under the design (`face-cut`) with a soft shadow. A design with a transparent background gives a
contour-following shape; one with a background gives a rounded rectangle.

## Print-ready art

`print-art` writes the files for a printer, from the same request as the mockup: the template, the designs (`place`, or
a bare `design`), and a new `output` folder.

```json
{"mockup": "tee", "output": "print", "place": {"front-chest": "logo.vixl", "sleeve-l": "badge.vixl"},
 "dpi": 300, "spot_colors": 3, "underbase": true, "garment_color": "#14161c"}
```

For each placed area it writes:

- `AREA.png` the design at the area's print size and `dpi` (default 300; `print_size_mm / 25.4 × dpi` pixels, so the
  254 mm chest print is 3000 px), with the resolution recorded and transparency kept, exported through the same path as
  `vixl_export`, so the call limits and the refusal to overwrite apply;
- `source/AREA.vixl` the editable print document: the design linked into a canvas of that size;
- with `spot_colors: N`, `AREA-spot.png`, the art posterized to at most N flat inks (merged by the least perceptual
  loss, in OKLab; a pixel prints where its alpha is at least half), and the separations: one film positive per ink,
  `AREA-ink1.png` and on, in the order they print (light inks first). A film is 8-bit grey, black where the ink prints,
  and the inks never overlap. `separations: "pdf"` writes them as the pages of `AREA-separations.pdf` instead, the page
  being the print size;
- with `underbase: true` on a dark garment, `AREA-underbase.png`, a white choke layer: the art's footprint pulled in by
  `choke_mm` (default 0.2) so the white never shows at an edge. A garment is dark below a WCAG relative luminance of 0.4
  (black, navy, red, royal blue; not a light heather or yellow); the garment colour is `garment_color`, else the
  template's. On a light garment, or a product that is not a garment, no underbase is written and the result's `notes`
  say why.

The result lists every area with its pixel size, files, inks (colour and coverage) and underbase. Nothing is written if
a file exists (`overwrite: true` replaces them), a request that exceeds the pixel limit (40 million pixels, 16384 on a
side) is refused before anything is written, and a failure removes the files the call wrote. A 305 × 406 mm print at
600 dpi is 69 megapixels: choose a lower `dpi`.

## Your own templates

`mockup-save` stores a template in the workspace library. Besides `slots` (a screen, a sheet: four corners each) it takes
named `areas`, and the fields that make a product:

```json
{"name": "mini-tee", "value": {
  "width": 800, "height": 800, "background": "#e6e9ee",
  "operations": [{"type": "shape", "shape": "rounded-rectangle", "name": "body", "x": 100, "y": 100, "width": 600,
                  "height": 600, "radius": 40, "fill": "#f1efe9"}],
  "areas": {"front-chest": {"corners": [[250, 200], [550, 200], [550, 500], [250, 500]],
                            "print_size_mm": [100, 100], "surface": "base", "finish": "screen",
                            "clip_path": "M120 120 L680 120 L680 680 L120 680 Z"}},
  "base": ["body"], "garment_color": "#f1efe9"}}
```

- `areas`: `{name: {corners, print_size_mm, clip_path?, surface?, radius?, shade?, gloss?, finish?, cut?}}`. The corners are
  the four corner points the design is warped into (a quad in perspective works); `clip_path` is the SVG path, in canvas
  pixels, the design is clipped to (the quad when absent); `surface` is the colour under the design, `base` for the
  garment colour or `none` for no surface at all; `finish` the default finish; `cut` is `{mode: die|kiss|pin|patch,
  border_mm?, color?}`, a cut shape around the artwork. Names are lowercase with hyphens. Slots may carry a
  `print_size_mm` too.
- `base` names the operations' layers a garment colour recolours (their `fill`), and `garment_color` is the default.
  `main` lists the placements a bare `design` fills when it is not the first area.
- Scenes are drawn with operations or taken from a workspace document, and may place a pack image: an `asset-place` of an
  `assets` resource (a product photo, a woven label) is allowed in `operations` and `overlay`, because it reads no file
  the caller names. A missing resource fails the mockup with `missing_asset` and the names that exist.

## Related

[Linked documents](linked-documents.md) explains the link layer a placed design is; [exporting](exporting.md) covers the
formats and print options of the files; [imposition](imposition.md) lays copies out on press sheets.
