# Safe variety from sparse briefs

Sparse layouts, templates, guides and document creation choose fresh seeds by
default. Results report their seed and chosen values. Pass that seed to reproduce
the direction; explicit seeds ignore workspace roll history. Explicit choices and
brand palettes/fonts take precedence over random choices.

`vixl_guide(brief="safe-pools")` lists safety tags across palettes, font pairings,
layouts, styles, looks, templates and containers. The broad-use pool includes 20
new restrained palettes, 15 editorial/centered/asymmetric compositions, 18 curated
font pairings and quiet finishing looks. Specialized neon, handwriting and display
options remain available by explicit name.

`vixl_roll(variety="low"|"medium"|"high"|"fixed")` varies the font pairing,
palette, layout, scale, density, margin, accent motif, corner style, background
treatment, color-role assignment, style, finish and recommended container/variant.
Editorial directions avoid pill corners. Weight contrast describes the actual
heading/body weights in the chosen pairing. Higher variety expands the background
and finishing choices while staying in the curated pools.

## New documents

Every surface creates documents the same way: `vixl new`, Python `Project()`, `Project.sized()` and
`Project.new()`, `vixl_document_create`, `vixl_compose` and REST compose. Each new document:

- **Size.** Uses the given size. Without one, it uses the purpose's size (`purpose`: social 1080×1350,
  story 1080×1920, poster 18×24 in, print/document/form/flyer Letter or A4 by locale, slides and diagram
  1920×1080, web 1200×630, motion 1920×1080, logo 1000×1000, icon 1024×1024, favicon 512×512). With neither,
  it is 1080×1080.
- **Design defaults.** Rolls and stores `design_defaults` (seed, variety, purpose and the whole direction).
  `--seed`/`--variety` on the CLI, and `seed`/`variety` in Python and MCP, reproduce them exactly.
- **Background.** Without `background`, the canvas takes the rolled palette's background role. Logo, icon and
  favicon sizes and mark purposes (logo, mark, emblem, badge, monogram, icon, app-icon, favicon) stay
  transparent. `background="transparent"` (`--background transparent`) keeps the old default.
- **Fonts.** Embeds the workspace default fonts (`brand.json`). Otherwise it installs the rolled pairing, from
  the font cache first and then the network. Offline, creation stays fast: it reports the pairing under
  `creation.fonts` with a `next_step`, warns once, and does not retry the network in that process.
  `workspace_fonts=false` (`--no-fonts`) embeds no fonts. The environment variable `VIXL_AUTO_FONTS=cache`
  never downloads, and `VIXL_AUTO_FONTS=off` skips the pairing.

The result's `creation` says what was chosen and why (`size_from`: argument, purpose or default;
`background_from`: argument, palette or mark). `Project(width, height)` on its own is still a plain
transparent canvas with no `design_defaults`; pass `seed`, `variety` or `purpose` (or leave out the size) for a
design document, and `Project.sized(size, design=False)` for a plain named-size canvas.

A `layout-apply` without `seed` on such a document uses the whole stored direction, as
`vixl_roll(apply=true)` does: the layout seed, palette, mode, type scale, density and accent, and the
margin, corner, look, style, motif and background treatment. Fields you pass win one by one. Passing
`seed` asks for a fresh choice instead of the stored direction.

The rolled density changes the result: airy widens and dense tightens the rolled margin (×1.25 and ×0.75)
and the spacing unit behind gaps, and both the roll and the builder choose balanced twice as often as airy
or dense. The rolled accent (rule, bar, dot, block or outline) is drawn in the safe compositions next to
their own device.

`vixl_roll(apply=True, slots={"title": "Launch"})` installs its selected fonts,
builds the editable design in one undo step, and returns contrast/legibility checks.
Ordinary layout/template calls do not download fonts: their `font_choice` result
names the selected pairing and the explicit installation command. Existing fonts
and brand choices remain authoritative.

Locking a component applies it, including its named variant, while preserving
supplied copy that does not map to its slots:

```python
from vixl.typefaces import roll_document

result = roll_document(project, seed=42, apply=True,
    locks={"container": "feature-icon", "container_variant": "centered"},
    slots={"title": "Our feature", "body": "A useful benefit", "subtitle": "More detail"})
```

Without a component lock, the roll's component is a recommendation for subsequent
`container-place` calls; a text composition does not gain unrelated placeholder
content. Document defaults also supply compatible variants when placing containers.

Unseeded workspace rolls keep at most 32 entries in `.vixl/rolls.json`. Recent
palette/layout choices receive lower selection weights, and consecutive rolls
avoid repeating either when another choice is available. Set the workspace policy
in `.vixl/variety.json` for repeatable tests or production:

```json
{"variety": "fixed", "seed": 29}
```

The acceptance matrix renders every new safe palette and composition at Open Graph,
portrait social, and slide sizes, then checks contrast and text legibility at their
reading widths. Longer copy and custom overrides can still require adjustment;
the applied roll returns the measured findings.
