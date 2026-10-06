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
| `grain` | fine film grain | raster fallback |
| `paper` | warm tint, fibre grain and soft edge darkening (use on a full-canvas background) | raster fallback |
| `film` | sepia, grain and vignette | raster fallback |
| `duotone` | map to two tones of `color` | raster fallback |
| `risograph` | one ink on warm paper with grain | raster fallback |
| `sketch` | pencil-sketch rendering | raster fallback |
| `watercolor` | soft watercolor wash | raster fallback |
| `halftone` | print-style dot screen | raster fallback |

The raster looks split in two. `grain`, `paper` and `film` suit anything, flat shapes included. `duotone`, `risograph`, `sketch`, `watercolor` and
`halftone` render tone and edges, so they are for photographs and illustrations: on a flat fill there is only one tone, so `duotone` turns it gray
and `sketch` fades it out.

## Behaviour

- **`amount`** (0-1, default 0.5) moves a look between subtle and strong. Sizes scale with the layer (blur and offsets follow its smaller side), so the
  same look suits an icon and a poster. `color` is the main color of the look (glow color, shadow color, ink); it may be an `@swatch`.
- **Replace, don't stack.** Applying a look again replaces it. A style belongs to one look: `hard-shadow` after `soft-shadow` takes the
  `drop-shadow` over. Looks never remove styles or effects you added by hand; `remove: true` takes off exactly what that look added.
- **Records.** The layer keeps `looks` (`{name: {styles, effects, amount, color}}`). The styles and effects themselves are the normal ones: `layer-style`
  and `effect-*` operations edit them, and `inspect` shows them.
- **PNG and SVG.** Styles (`drop-shadow`, `outer-glow`, `stroke`, `gradient-overlay`) and blur-like effects are native SVG filters. Grain, sepia, vignette,
  duotone, halftone and the artistic filters are raster effects: SVG export embeds a raster fallback under `svg_policy: appearance` and
  rejects it under `strict`, exactly as for a hand-added effect. The table above says which looks are native.
- **Not for form fields.** Fields are upright PDF rectangles; looks reject them.

Radial symmetry has its own operation, `radial-repeat` (see [design tools](design-tools.md#radial-repeat)); mandalas, rosettes and
sunbursts are one petal, `radial-repeat`, then `look glow`.
