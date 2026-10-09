# Safe variety from sparse briefs

[Documentation home](README.md) · [House style](house-style.md) · [Sizes and layouts](sizes-and-layouts.md)

Sparse layouts, templates, guides and document creation choose fresh seeds by
default. Results report their seed and chosen values. Pass that seed to reproduce
the direction; explicit seeds ignore workspace roll history.

## Where the choices come from

The choices come from Vixl's **house style** (`src/vixl/data/house-style.json`), a built-in
default brand. Precedence, highest first:

1. an explicit field or `--lock`;
2. the workspace `brand.json` (palette, pairing, fonts);
3. the **purpose profile** (poster, social, slides, document, form, diagram, logo, motion);
4. the document's stored `design_defaults`;
5. a fresh seeded roll.

The purpose comes from an explicit `purpose` (`vixl roll --for slides`, `vixl_roll(purpose=…)`), else
the brief kind (`vixl_guide("social-card")`), else the purpose stored in the document, else its
named size (`instagram-post` is social, `letter` is document, `favicon` is logo). Roll and creation
results report `purpose` and `purpose_source` (`explicit`, `brief kind`, `document` or `size`).

Creation (`vixl new --purpose`, `vixl_document_create(purpose=…)`, `Project(purpose=…)`) and rolls
(`vixl roll --for`, `vixl_roll(purpose=…)`) accept the same names: the eight purposes and their aliases
(`story`, `web`, `email`, `flyer`, `print`, `invitation`, `deck`, `video`, `icon`, `mark`, `emblem`,
`favicon` …), as well as brief kinds, named sizes and size categories. Each name maps to one purpose
profile; creation refuses an unknown name with suggestions, while a roll treats one as a free-text hint.
Each purpose weights the taste:

| Purpose | Dark mode | Type scale | Pairings it favours | Density | Finishing look |
|---|---|---|---|---|---|
| poster | about half | 1.5–1.618 | display and slab faces | balanced | visible (amount 0.25) |
| social | about half | 1.333–1.5 | bold sans and display | balanced | visible (amount 0.25) |
| motion | about half | 1.333–1.618 | display sans | balanced | visible (amount 0.25) |
| slides | 1 in 4 | 1.2–1.25 | UI sans | balanced | none |
| diagram | 1 in 5 | 1.2–1.25 | UI and data faces | dense | none |
| document | 1 in 10 | 1.2–1.333 | editorial serifs | airy | none |
| form | 1 in 10 | 1.2–1.25 | civic and UI faces | balanced | none |
| logo | light only | 1.333–1.5 | geometric sans and display | balanced | none |

Density follows the purpose seven rolls in ten and deviates the rest of the time (decision E4); without
a purpose the roll picks balanced twice as often as airy or dense.

`vixl house show PURPOSE` (MCP `vixl_resource_get(kind="house-style", name=PURPOSE)`) prints a
profile; `vixl house` prints the craft rules, the tiers and the levels.

## Tiers and variety levels

Every palette, pairing, layout, style and look has a **tier**: `safe` (broad use), `bold`
(characterful but robust), `avant-garde` (unusual and expressive) or `explicit` (specialised
entries such as scripts, memes and image layouts, available by name only). Catalog rows carry
`tier`; `safe` stays as an alias for tier safe. A roll first draws a tier, then picks every
dimension from that tier's pool, weighted by purpose and mood:

| Level | Tiers (safe / bold / avant-garde) | Finishing look | Backgrounds |
|---|---|---|---|
| `low` | 100 / 0 / 0 | the purpose amount × 0.8 | flat or gradient |
| `medium` (default) | 75 / 20 / 5 | the purpose amount | flat or gradient; also split and pattern for posters and social, split for motion |
| `high` | 45 / 35 / 20 | the purpose amount × 1.5 | flat, gradient, split or pattern |
| `fixed` | as medium, with a fixed seed | | |

Results report the drawn `tier` and the tier of each choice (`tiers`). Lock a tier to explore
within it: `vixl roll --lock tier=bold`. An expressive `mood` (playful, bold, loud, energetic …)
shifts the odds toward the bold tiers and favours entries with that mood; a quiet mood (calm,
minimal, corporate …) shifts them toward safe.

The safe palette pool holds light, dark, saturated, duotone and earthy palettes, each checked with
the role-assignment contrast pass in every mode it rolls in (ink 7:1, muted and accent text 4.5:1).
Dark palettes roll only in dark mode. The curated legacy palettes (midnight, nordic, sunset, neon
…) joined the tiers and keep their names. `vixl_guide(brief="safe-pools")` lists every entry with
its tier, moods and modes.

## What a roll chooses

`vixl_roll(variety="low"|"medium"|"high"|"fixed")` chooses the font pairing, palette, light or dark
mode, layout, type scale, density, margin, accent motif, background treatment, style, finishing look
and its amount, a headline treatment, and a recommended container/variant. Corners follow the house
craft (sharp) unless the rolled style has its own (material and glassmorphism round, kawaii and y2k
pill), and layout buttons, panels and placed containers take the document's corner style. A bold or
avant-garde roll, or one with an expressive mood (playful, bold, loud …), sets `headline: large`: the
headline holds about 8 characters a line instead of 14, so it fills the canvas; quiet rolls keep
`headline: measured`. Lock it like any other choice (`--lock headline=measured`). From house style 3,
alignment is weighted by purpose: design purposes roll left three times in four and right otherwise, diagram
and form purposes left or centre 75/25, and marks stay centred; an
explicit `align` wins. Saturated palette backgrounds are washed only as far as the ink contrast
target needs. The rolled
look lands where it shows: texture looks on the background, the house offset shadow and other
shadow, outline and glow looks on the solid shapes (buttons, panels, blocks), never on hairline
rules. Weight contrast describes the actual heading/body weights in the chosen pairing. A roll
applied with `slots` only picks layouts that place all of the supplied copy and leaves out layouts
whose image slot nobody fills.

## New documents

Every surface creates documents the same way: `vixl new`, Python `Project()`, `Project.sized()` and
`Project.new()`, `vixl_document_create`, `vixl_compose` and REST compose. Each new document:

- **Size.** Uses the given size. Without one, it uses the purpose's size, from the purpose profile's `size`
  and its aliases' `sizes` in the house-style data (social 1080×1350, story 1080×1920, poster 18×24 in,
  print/document/form/flyer Letter or A4 by locale, slides and diagram 1920×1080, web 1200×630, email
  600×300, motion 1920×1080, logo 1000×1000, icon 1024×1024, favicon 512×512). A named size given as the
  purpose (`purpose: "a4"`) is used as is. With neither, it is the general profile's 1080×1080.
- **Design defaults.** Rolls and stores `design_defaults` (seed, variety, purpose and the whole direction).
  `--seed`/`--variety` on the CLI, and `seed`/`variety` in Python and MCP, reproduce them exactly.
- **Background.** Without `background`, the canvas takes the rolled palette's background role. Logo, icon and
  favicon sizes and mark purposes (the `logo` profile is flagged `mark`; its aliases mark, emblem, badge,
  monogram, icon, app-icon and favicon with it) stay transparent. `background="transparent"` (`--background transparent`) keeps the old default.
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
and the spacing unit behind gaps (half the body size, craft `spacing.unit`). The roll weights density by
purpose (above); the builder, given no density, chooses balanced twice as often as airy or dense. The rolled accent (rule, bar, dot, block or outline) is drawn in the safe compositions next to
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

`vixl_guide` attaches a roll to a brief kind. That roll favours the kind's recommended layouts,
looks and styles where the variety level allows their tier, and the answer's `recommendations`
says, for each list, what was rolled, whether it is one of the recommendations and which
recommendations are opt-in alternatives (with their tiers).

## Reproducing and pinning

Unseeded workspace rolls keep at most 32 entries in `.vixl/rolls.json`. Recent
palette/layout choices receive lower selection weights, and consecutive rolls
avoid repeating either when another choice is available. Set the workspace policy
in `.vixl/variety.json` for repeatable tests or production:

```json
{"variety": "fixed", "seed": 29}
```

New documents store `house_style_version` in `design_defaults`, and later rolls in that document
use the same version, so a change to the house style never reaches an existing document. The
current version is 3 (0.24). To replay 0.23 rolls (no house-style-3 pairings, alignment weighting or
reduced background washing), pin version 2; to roll the 0.20–0.22 directions (safe pools only, two
light rolls in three, looks at amount 0.1), pin version 1: `vixl roll --house-style 2`,
`roll(..., house_style_version=2)`, or `{"house_style": 2}` in `.vixl/variety.json` for every surface.
Version-3 geometry defaults (stack gaps of `2u`, chart padding, text-flow gutters, seamless short
timelines) apply only to documents that record version 3.

## Measuring it

`python -m evals.house_style` rolls 48 sparse briefs across the eight purposes at each level, applies
them, and scores diversity (entropy of palette, layout, mode, pairing, look and style, and the mean
pairwise distance of renders) and quality (no `fix` findings, fonts installed, contrast). See
[the eval README](../evals/README.md#house-style-eval). The acceptance matrix also renders every safe
palette and composition at Open Graph, portrait social, and slide sizes, then checks contrast and text
legibility at their reading widths, and every layout a social roll can pick is applied at every named
social and web size and must pass its own safe-area check: text and buttons stay inside the canvas
safe area (on a 3:1 banner a safe composition sets its copy in two columns), while decoration and
full-bleed pictures are marked as such. Longer copy and custom overrides can still require adjustment; the
applied roll returns the measured findings.
