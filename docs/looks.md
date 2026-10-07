# Looks: finishing flat shapes in one operation

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

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
`vixl_guide(brief="looks")`.

| Look | What it adds | SVG export |
| --- | --- | --- |
| `glow` | outer glow in the layer's own color (or `color`) | native filter |
| `neon` | bright outline plus a wide glow | native |
| `soft-shadow` | gentle blurred drop shadow | native |
| `hard-shadow` | solid offset shadow, no blur (sticker, neo-brutalist) | native |
| `outline` | clean stroke around the shape or text | native |
| `gradient` | vertical light-to-dark gradient from the layer's color (or `color`) | native |
| `soft-halo` | on a gradient layer: a radial fade from its first color (or `color`) to transparent with a `gaussian` falloff, ending at the inscribed ellipse so the box never shows; on other layers a wide soft glow | native |
| `grain` | fine film grain | raster fallback |
| `paper` | warm tint, fibre grain and soft edge darkening (use on a full-canvas background) | raster fallback |
| `film` | sepia, grain and vignette | raster fallback |
| `duotone` | two tones of one ink: `color`, else the layer's own hue, else the palette's `@accent`; the ink's own brightness maps back to the ink | raster fallback |
| `risograph` | one ink (chosen like `duotone`'s) on warm paper with grain; lighter tones print as tints of it | raster fallback |
| `sketch` | graphite: edge lines and hatching that follows the tone, plus a pencil `stroke` on shapes, text and groups | raster fallback |
| `watercolor` | a lighter, blotchy wash with pigment pooled in a darker rim inside every edge | raster fallback |
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
- **Replace, don't stack.** Applying a look again replaces it. A style belongs to one look: `hard-shadow` after `soft-shadow` takes the
  `drop-shadow` over. Looks never remove styles or effects you added by hand; `remove: true` takes off exactly what that look added.
- **Records.** The layer keeps `looks` (`{name: {styles, effects, amount, color}}`; `soft-halo` on a gradient also keeps the `fields` it changed, which `remove` puts back). The styles and effects themselves are the normal ones: `layer-style`
  and `effect-*` operations edit them, and `inspect` shows them.
- **PNG and SVG.** Styles (`drop-shadow`, `outer-glow`, `stroke`, `gradient-overlay`) and blur-like effects are native SVG filters. Grain, sepia, vignette,
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

Radial symmetry has its own operation, `radial-repeat` (see [design tools](design-tools.md#radial-repeat)); mandalas, rosettes and
sunbursts are one petal, `radial-repeat`, then `look glow`.
