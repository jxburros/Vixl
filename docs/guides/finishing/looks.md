# Looks: finishing flat shapes in one operation

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Visual gallery](../../gallery.md)

A flat shape reads as a draft. A soft shadow, a gradient or a little grain makes it read as finished. `look` applies a named
finish to one or more layers in a single operation. Looks are recipes over what the engine already renders (layer styles and
the non-destructive effect stack), so they stay editable, undo cleanly and export like anything added by hand.

```json
{"type": "look", "target": "badge", "look": "glow", "color": "#fde047"}
{"type": "look", "targets": ["card", "button"], "look": "soft-shadow", "amount": 0.7}
{"type": "look", "target": "background", "look": "paper"}
{"type": "look", "target": "badge", "look": "glow", "remove": true}
```

CLI: `vixl look LAYER NAME [--color C] [--amount A] [--remove]`, `vixl looks` for the catalog. MCP: the `look` operation and
`vixl_reference("looks")`.

| Look | What it adds | SVG export |
| --- | --- | --- |
| `glow` | outer glow from the layer's own color (or `color`); see *Glow and shadow colors* below | native filter |
| `neon` | bright outline plus a wide glow | native |
| `soft-shadow` | small, light blurred drop shadow in the color of what it falls on | native |
| `hard-shadow` | solid offset shadow, no blur (sticker, neo-brutalist), a dark shade of what it falls on unless `color` is given | native |
| `outline` | clean stroke around the shape or text | native |
| `gradient` | vertical light-to-dark gradient from the layer's color (or `color`) | native |
| `soft-halo` | on a gradient layer: a radial fade from its first color (or `color`) to transparent with a `gaussian` falloff, ending at the inscribed ellipse so the box never shows; on other layers a wide soft glow | native |
| `clean-flat` | restrained flat colour, no effects | native |
| `subtle-grain` | quiet grain for broad-use backgrounds | raster fallback |
| `light-paper` | quiet paper finish with minimal tint and texture | raster fallback |
| `grain` | fine film grain | raster fallback |
| `paper` | warm tint, fibre grain and soft edge darkening (use on a full-canvas background) | raster fallback |
| `film` | sepia, grain and vignette | raster fallback |
| `duotone` | two tones of one ink: `color`, else the layer's own hue, else the palette's `@accent`; the ink's own brightness maps back to the ink | raster fallback |
| `risograph` | one ink (chosen like `duotone`'s) on warm paper with grain; lighter tones print as tints of it | raster fallback |
| `sketch` | graphite: edge lines and hatching that follows the tone, plus a pencil `stroke` on shapes, text and groups | raster fallback |
| `watercolor` | a lighter, blotchy wash with pigment pooled in a darker rim inside every edge (canvas edges stay open; `edges: box` on the effect restores a rim there) | raster fallback |
| `halftone` | print-style dot screen | raster fallback |
| `hand-made` | hand-drawn wobble of a vector layer's outlines and line weight (`irregular`, seeded from the layer's name) | native |
| `plush` | fur tufts along a shape's edge (behind it), inner flicks (above it) and a soft gradient | native |

`grain`, `paper` and `film` suit anything, flat shapes included. `duotone`, `risograph`, `sketch`, `watercolor` and `halftone` render tone and
edges, so they show most on photographs and illustrations, but they also read on a flat vector shape: `duotone` and `risograph` keep a flat
fill in its own hue when no `color` is given, `sketch` draws a pencil outline and hatches the fill by its tone, and `watercolor` pools pigment
along the shape's edge. Pixels outside a layer's box count as paper, so a shape that fills its box still gets its edge.

## Behaviour

- **`amount`** (0-1, default 0.5) moves a look between subtle and strong. Sizes scale with the layer (blur and offsets follow its smaller side), so the
  same look suits an icon and a poster. `color` is the main color of the look (glow color, shadow color, ink); it may be an `@swatch`.
- **Glow and shadow colors.** Without `color`, a look reads what lies under the layer (the canvas and the layers
  painted before it, inside a group too) and builds its color from that, so it never reads as dirt:
  - a shadow (`soft-shadow`, `hard-shadow`) is the backdrop in shade: the same hue and chroma at about a third of its
    lightness, never neutral grey or black (black only on a transparent canvas). `soft-shadow` is small and light: offset
    1.5-4% and blur 3-8% of the layer's short side, opacity 0.14-0.30.
  - a glow (`glow`, `neon`, `soft-halo`) is a lighter tint of the layer's own color, screened over the backdrop, so it
    only adds light: over an even dark ground it is exactly a screen blend, and a warm glow on navy stays light instead
    of turning brown. Over a ground lighter than the tint the glow keeps the layer's own color. Its opacity is capped at
    0.6 (a `soft-halo` gradient's core at 0.7).
  An explicit `color` is used exactly as given. The values come from `craft.finish` in the house style.
- **Replace, don't stack.** Applying a look again replaces it. A style belongs to one look: `hard-shadow` after `soft-shadow` takes the
  `drop-shadow` over. Looks never remove styles or effects you added by hand; `remove: true` takes off exactly what that look added.
- **Records.** The layer keeps `looks` (`{name: {styles, effects, amount, color}}`; `soft-halo` on a gradient also keeps the `fields` it changed, which `remove` puts back). The styles and effects themselves are the normal ones: `layer-style`
  and `effect-*` operations edit them, and `inspect` shows them.
- **PNG and SVG.** Styles (`drop-shadow`, `outer-glow`, `stroke`, `gradient-overlay`, `inner-shadow`, `inner-glow`, `bevel`) and blur-like effects are native SVG filters. Grain, sepia, vignette,
  duotone, halftone and the artistic filters are raster effects: SVG export embeds a raster fallback under `svg_policy: appearance` and
  rejects it under `strict`, exactly as for a hand-added effect. The table above says which looks are native.
- **Not for form fields.** Fields are upright PDF rectangles; looks reject them.
- **Geometry looks.** `hand-made` and `plush` change geometry, so they are made from the layer as it is when the look is
  applied; apply them again after moving or reshaping it. `hand-made` runs `irregular` (wobble, vertex jitter and stroke
  weight, strength from `amount`) on a shape or on the shapes of a group; the pristine source stays in each layer's
  `irregular` record, so removing the look restores it exactly. It refuses text and raster layers and layers that already
  carry `irregular`. `plush` runs `scatter` with `preset: fur` and keeps the tuft and flick layers as helpers
  (`part_of` the layer, named `NAME-plush` and `NAME-plush-flicks`); removing or re-applying the look deletes them. Each
  look records what it changed (`irregular`, `parts`) next to its styles and effects. To animate hand-drawn lines, use the
  `line-boil` motion recipe.

Radial symmetry has its own operation, `radial-repeat` (see [design tools](../shapes/design-tools.md#radial-repeat)); mandalas, rosettes and
sunbursts are one petal, `radial-repeat`, then `look glow`.

## Layer styles inside the silhouette

Three `layer-style` names draw inside a layer's outline, on top of its content and overlays, and never outside it.
They are not looks: add them with `layer-style` on any layer (shape, text, image, group).

```json
{"type":"shape","shape":"star","name":"piece","x":40,"y":40,"width":160,"height":160,"fill":"#c0392b"}
{"type":"layer-style","target":"piece","name":"bevel","settings":{"angle":135,"size":4,"opacity":0.5}}
{"type":"layer-style","target":"piece","name":"inner-shadow","settings":{"color":"#1d1a16","dx":3,"dy":4,"blur":4,"opacity":0.5}}
{"type":"layer-style","target":"piece","name":"inner-glow","settings":{"color":"#fff6d5","blur":6,"opacity":0.6}}
```

| name | settings (defaults) | what it draws |
| --- | --- | --- |
| `inner-shadow` | `color` (black), `dx`, `dy` (2, 2), `blur` (4), `opacity` (0.5) | A soft shadow inside the edges the offset comes from: positive `dx`/`dy` shade the left and top edges, as a `drop-shadow` with the same offset would fall. |
| `inner-glow` | `color` (white), `blur` (6), `opacity` (0.6) | An even band of colour inside every edge. |
| `bevel` | `angle` (135), `size` (4), `highlight` (white), `shadow` (black), `opacity` (0.5) | A lit edge on the side facing the light and a shaded edge on the far side, in one call. `angle` is the direction towards the light in degrees: 0 right, 90 up, 135 up and left. |

- **The silhouette is the layer's own alpha**, holes included: a ring gets an edge inside its hole, text gets one
  inside every letter. Pixels outside the layer are never changed.
- **The light stays put when the layer turns.** Like `drop-shadow`, the offsets and the bevel's angle are directions
  on the canvas, so a rotating piece keeps its lit edge towards the light. (Effects such as `emboss` are different:
  they run in the layer's own frame and turn with it.)
- **A layer that runs off the canvas** is taken to continue past the canvas edge, so it gets no edge there.
- **Order:** content, then colour and gradient overlays, then `inner-glow`, `inner-shadow`, `bevel`.
- **Cut paper:** `cut-paper` with `edge_light: {"angle": 135}` adds a subtle bevel to every piece (see
  [animation authoring](../motion/animation-authoring.md)).

Exports:

| format | how the three styles are written |
| --- | --- |
| PNG and other images | Drawn by the renderer. |
| SVG | Native filters (`feGaussianBlur`, `feOffset`, `feComposite`) with the same steps as the renderer, so the layer stays vector and the pixels agree. |
| PDF | The styled layer is embedded as an image of what the renderer draws, listed under `raster_fallbacks` (reason `layer styles`), like every other layer style. |
| PPTX | `inner-shadow` alone on an unturned, unflipped shape without a stroke is PowerPoint's own inner shadow, so the shape stays editable; the report lists it under `native_effects` with a warning: PowerPoint's softness differs slightly and LibreOffice Impress does not draw inner shadows. Everything else (`inner-glow`, `bevel`, text, turned shapes, combinations with other styles) is a picture of the render, listed under `raster_fallbacks`. |
| PSD | Baked into the layer's pixels. |
