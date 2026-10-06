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
