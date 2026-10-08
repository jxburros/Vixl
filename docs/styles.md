# Design styles: guidance and premade checks

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

A brief that names a look ("make it brutalist", "something Art Deco") needs more than a mood word: principles,
palettes, type, layout and imagery to aim for, and a way to tell whether the result got there. Vixl keeps a curated
catalog of 28 design styles, tags a document with one, and evaluates optional, parameterised **rules** against the
rendered document. Everything is advisory: a rule is a finding with a measurement and a fix, never a refusal.

```text
vixl styles                         # list (also: styles list swiss, styles list neon)
vixl styles show art-deco           # principles, palettes, type, layout, imagery, do/don't, rules
vixl -p poster.vixl styles apply art-deco --palette    # tag + store the brief (+ palette)
vixl -p poster.vixl check --checks style               # one finding per failed rule
vixl -p poster.vixl check --checks style --style brutalist swiss   # try other styles without tagging
```

MCP: `vixl_styles(action="list|get|apply|check", name, query, palette)` and `vixl_check(checks=["style"], style=...)`.
Operation: `{"type": "style-set", "style": "swiss"}` (a name, up to three names, or `null` to clear), with
optional `options` (below). Python: `vixl.styles` (`listing`, `describe`, `guidance_text`, `apply_operations`).

## What each style provides

| Field | Content |
| --- | --- |
| `summary`, `era`, `keywords`, `best_for` | What it is, where it comes from, how to find it, what it suits |
| `principles` | 3-5 rules of the style |
| `palettes` | 1-3 named swatch lists with a note (first swatch is the background); `palette_names` lists built-in palettes that fit |
| `type` | Categories (from the font catalog), families, curated pairings (from `vixl_fonts`), weights, case, what to avoid |
| `layout` | Grid, alignment, negative space, suggested `layout-apply` layouts |
| `imagery` | Advice, suggested [looks](looks.md) and effects, what to avoid |
| `do`, `dont` | Short lists |
| `checks` | The premade rules, each with `id`, `kind`, `severity`, `summary`, `fix` and `params` |

`styles apply NAME` (MCP `action="apply"`) is guidance as operations: it tags the document (`style-set`), stores a compact
brief as design guidance (`guidance` with `style: "style"`, visible in `inspect`), and with `palette` also defines and applies
the style's first palette, mapping background, ink and accent from its swatches. Nothing is downloaded: install the
suggested fonts with `vixl_font_pair` or `vixl_font_install`.

## The catalog

| Style | In one line |
| --- | --- |
| `swiss` | grid-built, flush-left sans, scale contrast, black/white plus one accent |
| `brutalist` | raw and blunt: heavy type, hard edges, maximum contrast |
| `neo-brutalist` | thick outlines, hard offset shadows, flat saturated fills |
| `minimalist` | most of the canvas empty, 2-3 colors, one typeface |
| `scandinavian` | warm minimalism: muted natural palette, friendly sans, air |
| `bauhaus` | circle/square/triangle, primaries, asymmetric dynamism |
| `art-deco` | symmetry, gold on dark, tall capitals, fans and sunbursts |
| `mid-century-modern` | dusty warm colors, organic shapes, slab type, print grain |
| `memphis` | clashing brights, squiggles, confetti, tilted overlap |
| `retro-futurism` | space-age gradients, glowing suns, wide geometric type |
| `vaporwave` | pink-cyan gradients, glitch, grids, wide-spaced type |
| `y2k` | chrome, gloss, bubbles, silver and baby blue |
| `editorial` | magazine hierarchy, serif headlines, columns, captions |
| `corporate-flat` | flat vectors, trustworthy blue, 4.5:1 contrast |
| `material` | elevation shadows, rounded cards, Roboto-style type |
| `glassmorphism` | frosted translucent cards over vivid gradients |
| `grunge-zine` | photocopy, collage, halftone, rotated and torn |
| `japanese-minimal` | ma: half the canvas empty, one red seal accent |
| `vintage-letterpress` | cream paper, two inks, serif and slab, frames |
| `hand-drawn` | sketchy, imperfect, handwriting, natural color |
| `maximalist` | dense layered patterns, rich saturated color |
| `cyberpunk` | neon on near-black, glow, mono and condensed type |
| `kawaii` | pastel, rounded, sparkles and faces |
| `line-art` | one stroke weight, outlines not fills, one ink |
| `risograph` | 2-3 spot inks, overprint, grain and halftone |
| `data-viz` | restrained palette, direct labels, tabular type, no chart junk |
| `art-nouveau` | whiplash curves, botanical ornament, earthy gold and sage |
| `pixel-art` | tiny fixed palette, crisp edges, bitmap type |

## Premade checks

`check --checks style` (opt-in, like `print`) evaluates the tagged style's rules, or `style=` names. The result gets one
issue per failed rule (check `style`, `rule` such as `swiss/max-typefaces`, the `measured` values, the `fix`, and an `action`
of review for warnings or fix for errors) and a `style` section listing **every** rule with its status
(`passed`, `failed`, `skipped` when it does not apply, or `disabled`), measurement and detail.

Rule kinds (each takes the parameters shown; the style fixes the values):

| Kind | Parameters | Measures |
| --- | --- | --- |
| `max_typefaces` | `max` | Distinct type families (from registered font names such as `inter-700`) |
| `type_categories` | `allowed`, `required` | Category (serif, sans-serif, display, monospace, handwriting) per the font catalog |
| `text_align` | `allowed`, `scope` (`all`, `body`) | Alignment of text layers (`body` skips the headline) |
| `min_weight`, `max_weight` | `weight`, `scope` | Weight of the headline (or all text) from the registered name; a weight word in the family (`Archivo Black`, `... Heavy`, `... ExtraBold`) wins over a lower registered weight, so a single-weight black display face counts as black |
| `type_scale_ratio` | `min`, `max` | Largest over smallest text size |
| `min_text_size` | `size` | Smallest rendered text size in pixels |
| `max_words` | `max` | Words across text layers |
| `edge_alignment` | `min_fraction`, `tolerance` | Share of elements sharing a left, right, center, top or bottom edge |
| `margins` | `min_fraction` | Smallest gap from content to the canvas edge, as a share of the short side |
| `min_negative_space`, `max_negative_space` | `fraction` | Share of the render that is still ground when content layers are hidden |
| `symmetry` | `axis`, `min` | How much of the design mirrors across the axis: the better of the rendered pixels and the arrangement (the area share of elements whose mirrored box holds an element of the same kind and color, or that are centred on the axis), so centred type counts as symmetric |
| `tilt` | `max_fraction`, `min_fraction` | Elements rotated off the 90-degree grid; copies in a `radial-repeat` group (a sunburst's rays) are ornament and do not count |
| `max_colors`, `min_colors` | `max`/`min`, `distance` | Distinct declared colors, merged within `distance` |
| `hue_count` | `min`, `max` | Distinct hue families among colorful colors |
| `hue_range` | `hues`, `min_fraction` | Share of colorful colors inside hue ranges |
| `saturation`, `lightness` | `min`, `max` | Average HSV saturation / HSL lightness of the colors |
| `dark_background` | `max_luminance` | Luminance of the ground |
| `shadows` | `mode` (`none`, `hard`, `soft`, `hard-or-none`, `soft-or-none`) | Drop shadows by blur: hard offsets vs soft |
| `glow`, `gradients` | `mode` (`none`, `required`) | Outer glows; gradient layers and gradient overlays |
| `effects` | `require_any`, `forbid` | Effect names on layers (grain, halftone …) |
| `no_rounded_corners`, `rounded_corners` | `allow_circles`, `min_fraction` | Corner radius of shapes |
| `min_stroke_width`, `stroke_style`, `uniform_stroke` | `width`, `mode`, `tolerance` | Outlines: width, outline-only shapes, one weight |
| `min_layers` | `min` | Number of elements |
| `design_check` | `checks`, `options` | Any existing design check with options, such as `contrast` at `min_contrast: 7`, relabelled as a style rule |

Examples: Swiss holds to two typefaces, left-aligned text, 70% of elements on shared edges, no tilt, no shadows and at most one accent hue;
brutalist wants 700+ weight headlines, 7:1 contrast (a `design_check` over the existing `contrast` check), square corners and no gradients;
minimalist wants 40% empty canvas, at most three colors, one typeface and 40 words; art deco wants 80% mirror symmetry and centered text.

Typeface checks read each text layer's registered font name (`family-weight`, as `vixl_font_pair` registers them) and look the family up in
the catalog. Fonts with other names, or the bundled fallback, make type rules `skipped`, not failed.

## Relaxing or tightening a rule

```json
{"type": "style-set", "style": "swiss", "options": {
  "max-typefaces": {"max": 3},
  "tilt": false,
  "shadows": {"severity": "error"},
  "hue-count": {"enabled": false}}}
```

Keys are rule ids (`max-typefaces`, or `swiss/max-typefaces` when several styles are tagged). `false` or `{"enabled": false}` disables a rule,
any parameter listed by `styles show` overrides it, and `severity` (`error`, `warning`, `info`) changes how it counts. Unknown rules,
parameters and severities are rejected with the allowed values. Rules only report; they never edit the document.

## Notes on the research

Entries summarize widely documented design movements and genres (the International Typographic Style of Müller-Brockmann and Hofmann,
Bauhaus, Art Deco, Memphis, Material Design guidance, Tufte on data-ink and others). They are starting points for choices, not a
substitute for taste; thresholds in the rules are deliberately round numbers.
