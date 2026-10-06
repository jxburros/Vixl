# Sizes, layouts, color and print (0.13)

## Start from a named size

Never guess pixel dimensions for a known medium. Ask for the catalog, then create from a name:

```text
vixl_sizes_list(category="print")                       # or social, stationery, icons, logos, ads, email, video, slides …
vixl_document_create(path="flyer.vixl", size="letter", bleed=true)
vixl_document_create(path="card.vixl", size="business-card", bleed=true)
vixl_document_create(path="post.vixl", size="instagram-portrait")
vixl_document_create(path="icon.vixl", size="favicon")
```

```bash
vixl sizes --category icons
vixl new a5 --landscape --bleed -o flyer.vixl
vixl canvas size story              # resize an open document to a named size
```

Print sizes record `dpi`, `bleed` and `safe` (pixels) on the canvas and create guides `trim-left/right/top/bottom` and `safe-left/…`. Anchor content to them: `{"type":"constrain","target":"title","constraints":{"left":"guide:safe-left.left","top":"guide:safe-top.top"}}`. Keep text inside the safe guides and extend backgrounds to the canvas edge (into the bleed).

## Use a layout when the brief is open-ended

When asked for "a poster", "a post for X", "a logo for Y" with free rein, apply a layout first and refine it. Layouts encode principles (focal point, grid, thirds, golden section, reading pattern) and choose among sound variations by seed, so results are structured without all looking alike.

```text
vixl_layouts_list()                                     # names, principles, best_for, content keys
vixl_operations_apply(operations=[{"type":"layout-apply","name":"event-poster",
  "title":"Night Market","label":"Sat · June 21","body":"6 pm – 11 pm\nRiverside Park","cta":"RSVP",
  "palette":"sunset","seed":4}])
vixl_check() ; vixl_render_preview()
```

- Pick by medium: `hero-statement`, `split-screen`, `rule-of-thirds`, `asymmetric-balance` (social, posters); `editorial-grid`, `f-pattern`, `letterhead`, `framed` (documents); `banner`, `z-pattern` (wide ads); `story-vertical` (9:16); `thumbnail-bold` (YouTube); `slide-title`, `slide-content`; `logo-horizontal`, `logo-stacked`, `emblem`, `monogram`, `app-icon` (identity); `price-list`, `event-poster`, `product-card`, `big-number`, `quote-card`, `bento-grid`, `typographic-poster`, `minimal-mark`, `photo-caption`, `diagonal-band`, `golden-section`, `centered-axis`.
- Content keys: `title`, `subtitle`, `body`, `label`, `cta`, `caption`, `items` (newline-separated; `Name | $9` rows for price lists; `Heading: text` for f-pattern; bullets for slides), `image` (an embedded asset ID; otherwise a placeholder frame named `image` you fill with `replace-contents`).
- Variation: change `seed` to explore; pin `palette`, `mode` (light/dark), `type_scale` (`minor-third` … `golden` or a number), `density` (airy/balanced/dense), `align`, `accent` (rule/bar/dot/block/outline/none). The chosen system is in the result's `changes.layout` and in `state.layout`; a `notes` entry means type was shrunk to fit.
- Layouts create swatches `@background @surface @ink @muted @accent @accent-text @on-accent` (contrast-checked) and character styles `caption body lead subhead title headline display`. Edit a swatch to retint everything; use `@accent-text` (not `@accent`) for small accent-colored text.
- Second layout in the same document: pass `prefix` (e.g. `"b-"`) or `replace: true`.
- `type-scale` alone defines the styles: `{"type":"type-scale","base":18,"ratio":"golden"}`. Guidance resources `typography`, `color`, `layout`, `accessibility`, `print`, `icon`, `motion`, `brush` hold the principles in words (`{"type":"guidance","name":"print","style":"print"}`).

## Unfilled image slots

A layout with an image slot (`product-card`, `split-screen`, `photo-caption`, `story-vertical` …) draws a
placeholder frame when `image` is not given and returns `next_steps` with the slot's bounds and the four
ways to fill it: **import** (`vixl_import_image` → `replace-contents` or re-apply with `image=`),
**resource** (a saved shape or container), **draw** (shape/pen/organic/paint inside the bounds), or **AI**
(`vixl_ai_generate`, needs a provider). `check` reports the placeholder as a blank until it is replaced.

## Palette roles

`palette-apply` and `layout-apply palette=[…]` turn colors into `@background`, `@surface`, `@ink`, `@muted`, `@accent`,
`@accent-text` and `@on-accent` by luminance and chroma, following light or dark mode. That reassigns colors
passed in an order that looked like background, surface, accents. The result explains it: `palette_roles`
(palette-apply) and `layout.roles` (layout-apply) give each role's color, whether it is a palette entry
(`palette[2]`) or derived, and a one-line reason, plus `mode` and where it came from. To decide yourself, pass
`keep_order: true` (first color background, second surface, the rest accents; ink and muted are derived for 7:1 and
4.5:1 contrast), or set roles (`palette-apply roles: {background: 0, accent: "#e11d48"}`, values are palette
indexes or colors; `layout-apply colors: {…}`). `palette-generate` only adds numbered swatches (`brand-50` …).

## Finishing looks and styles

`look` applies a named finish in one operation (glow, neon, soft-shadow, hard-shadow, outline, gradient, grain,
paper, film, duotone, risograph, sketch, watercolor, halftone); `radial-repeat` makes rosettes and mandalas;
`vixl_styles` serves 28 design styles with premade checks. See [looks](../../../docs/looks.md) and
[styles](../../../docs/styles.md).

## Color language

Every color field accepts names (CSS + survey names like `dusty rose`), hex, `rgb()`, `hsl()`, `hwb()`, `lab()`, `lch()`, `oklab()`, `oklch()`, `color(display-p3 …)`, `cmyk(c m y k)`, `gray()`, `kelvin(2700)`, `color-mix(in oklab, a 30%, b)`, `@swatch`, and modifiers `lighten/darken(c, 10%)`, `saturate/desaturate`, `mix(a, b, 25%)`, `tint/shade/tone`, `alpha(c, 0.5)`, `rotate(c, 30deg)`, `complement`, `invert`, `grayscale`, `readable(bg)`. Swatches may reference swatches: `{"type":"swatch","name":"brand-soft","color":"mix(@brand, white, 70%)"}`.

Tools: `vixl_color(action="info"|"convert"|"harmony"|"scale"|"mix"|"contrast"|"names", colors=[…])`; CLI `vixl color …`. Palettes from one color: `{"type":"palette-generate","name":"brand","color":"#2563eb","scheme":"scale"}` (→ `@brand-50` … `@brand-950`) or a harmony scheme (`triadic`, `split-complementary` …).

Contrast rules the checks enforce: body text ≥ 4.5:1, text ≥ 24 px ≥ 3:1. Prefer OKLCH lightness differences over hue differences; `simulate` previews color blindness and `vixl_check(checks=["color_vision"])` finds text that fails for color-blind readers.

## Print and file formats

```text
vixl_export_file(path="flyer.pdf", color_space="cmyk", ink_limit=300)                 # GCR separation
vixl_export_file(path="flyer.pdf", color_space="cmyk", icc_profile="profiles/press.icc")  # printer profile
vixl_render_preview(proof=true)                                                       # soft proof
vixl_check(checks=["print"])                # ink coverage, low ppi images, < 6 pt type, live area, bleed
vixl_export_file(path="favicon.ico", icon_sizes=[16, 32, 48])
vixl_export_icons(directory="icons", icon_set="all")   # web/apple/android/windows sets + manifest
```

A CMYK PDF is vector like an RGB one (real text, paths and shadings with DeviceCMYK colours; effects and images become CMYK images, listed in `raster_fallbacks`); `pdf_content="raster"` flattens each page into one image, and every PDF export reports `content` and `content_reason`.

CLI: `vixl export flyer.pdf --cmyk [--icc press.icc] [--ink-limit 300]`, `--proof`, `--simulate deuteranopia`, `--dpi 300`, `vixl export-icons --out icons`. CMYK applies to JPEG, TIFF and PDF. Documents stay RGBA sRGB; CMYK values you type are converted to sRGB, so use the printer's ICC profile when exact separations matter. Vixl ships no press profiles.
