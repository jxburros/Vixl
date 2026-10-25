# Safe variety from sparse briefs

[Documentation home](../../README.md) · [House style](../../project/house-style.md) · [Sizes and layouts](sizes-and-layouts.md)

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

The purpose comes from an explicit `purpose` (`vixl roll --for slides`, `vixl_reference('roll')`), else
the brief kind (`vixl_reference("social-card")`), else the purpose stored in the document, else its
named size (`instagram-post` is social, `letter` is document, `favicon` is logo). Roll and creation
results report `purpose` and `purpose_source` (`explicit`, `brief kind`, `document` or `size`).

Creation (`vixl new --purpose`, `vixl_document(action='create', purpose=…)`, `Project(purpose=…)`) and rolls
(`vixl roll --for`, `vixl_reference('roll')`) accept the same names: the eight purposes and their aliases
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

`vixl house show PURPOSE` (MCP `vixl_reference('house-style', name=PURPOSE)`) prints a
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
…) joined the tiers and keep their names. `vixl_reference("safe-pools")` lists every entry with
its tier, moods and modes.

## What a roll chooses

`vixl_reference('roll')` chooses the font pairing, palette, light or dark
mode, layout, type scale, density, margin, accent motif, background treatment, style, finishing look
and its amount, a headline treatment, and a recommended container/variant. Corners follow the house
craft (sharp) unless the rolled style has its own (material and glassmorphism round, kawaii and y2k
pill), and layout buttons, panels and placed containers take the document's corner style. A bold or
avant-garde roll, or one with an expressive mood (playful, bold, loud …), sets `headline: large`: the
headline holds about 8 characters a line instead of 14, so it fills the canvas; quiet rolls keep
`headline: measured`. Lock it like any other choice (`--lock headline=measured`). Alignment is weighted by purpose: design purposes roll left three times in four and right otherwise, diagram
and form purposes left or centre 75/25, and marks stay centred; an
explicit `align` wins. Saturated palette backgrounds are washed only as far as the ink contrast
target needs. A roll also sets `cta` (`pill` or `button`) and `date` (`highlight` or
`plain`): how a layout's call to action and date line look (see [layouts](sizes-and-layouts.md)); they come
from a separate stream of the seed, so they never change the other choices for a seed. Lock them like any
choice (`--lock cta=button --lock date=plain`, or `direction: {"cta": "button", "date": "plain"}` on `layout-apply`). The rolled
look lands where it shows: texture looks on the background, the house offset shadow and other
shadow, outline and glow looks on the solid shapes (buttons, panels, blocks), never on hairline
rules. Weight contrast describes the actual heading/body weights in the chosen pairing. A roll
applied with `slots` only picks layouts that place all of the supplied copy and leaves out layouts
whose image slot nobody fills. When no layout places all of it, the roll keeps the layout the same seed
previews without slots, so applying it fails with the layout's `unused_slot` error, whose `suggestions` list
the slots it does use; drop those it leaves out and apply again. The roll's `direction.pool` says which pool
the layout came from (`content`, or `preview` for that fallback). If no layout fits at all (locks rule every
one out), the error's `suggestions` name up to three layouts with the supplied slots each places.

## Accent colours

A roll also sets how many accent colours the page draws, `accent_count`: one usually (55%), two often (30%),
none or three rarely (7.5% each); a mark (the logo purpose) rolls one, sometimes none or two. With two or three,
`accent_representation` says how they share the page: `equal` deals the accent-bearing layers (rules, bars, dots,
the margin motif, labels, big numbers) out in turn, so each accent carries large and small ones; `skewed` gives the
first accent the larger share (70/30 for two, 60/25/15 for three) and the most prominent layers. A shape with text
on it, such as the call to action or a highlighted date, keeps the first accent. Both come from a separate stream of
the seed, so a seed keeps the palette, layout and first accent it rolled before.

The extra accents are the palette roles `@accent-2` and `@accent-3`, each with a `-text` variant for small text:
the palette's next most colourful entry whose OKLCH hue is at least 30° from the accents before it, else the first
accent turned in hue at the same lightness and chroma (a grey accent, which has no hue to turn, gives lighter or
darker tones of itself). Each is nudged until it reads 3:1 as a fill on the background
and surface, and its text variant 4.5:1. Colours you fix (a brand palette, `colors`) get no invented companion: the
second accent then comes from the palette, or from `accent-2` and `accent-3` in the brand palette or `colors`. With
no accent, the accent layers take the ink colour and accent text the muted one.

A layout that has fewer places for an accent than the roll asked for adds the direction's margin motif (a short
rule) where a corner is clear of the text, and leaves out the accents that still find no layer. The layout record's
`accents` lists the accents drawn (`drawn`) and why any is missing (`note`); only drawn accents get swatches, and
the composition check's `accent_unused` reports an extra accent that a later edit removed from the page. Lock the
count like any choice: `locks={accents: 1}` (`--lock accents=1`) restores one accent, `accents: 0` a page in ink,
and `accent_representation` picks the sharing. On `layout-apply` the same fields go in `direction`:

```json
{"type": "layout-apply", "name": "hero-statement", "title": "Night Market", "label": "Saturday", "seed": 7,
 "palette": "chalk-indigo", "direction": {"accent_count": 2, "accent_representation": "equal"}}
```

## Moods from the brief

`vixl_reference(brief)` reads a free-text brief for mood as well as for its kind of work: each motif theme it names
carries moods (coffee is warm, cozy, earthy, rustic and crafted; a night city is futuristic, tech, dramatic, bold
and edgy), and the house style's keyword table (`taste.moods.keywords`) adds the moods its other words imply
(`cozy` and `autumn` warm, `luxury` luxurious, `quarterly` corporate; a mood's own name counts too). The attached
roll weights the palettes with one of those moods three times (`taste.moods.brief_weight`) within the rolled tier: it
favours them and never filters, so a coffee brief still sees most of the palette pool. The direction reports
`mood_source: "brief"`, the `brief_moods` and the `mood_words` that implied them, and the best theme's first element
as `motif_suggestion` (what to draw, how and with which shapes; no layers are added, and the rolled `motif`
decoration is unchanged). A brief with no matching word rolls exactly as it did before. Lock the palette
(`locks={palette: NAME}`) to choose it yourself.

## New documents

Every surface creates documents the same way: `vixl new`, Python `Project()`, `Project.sized()` and
`Project.new()`, `vixl_document(action='create')`, `vixl_apply(create=…)` and REST compose. Each new document:

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
- **Fonts.** Embeds the workspace default fonts (`brand.json`). Otherwise it records the rolled pairing
  (`creation.fonts` and `design_defaults.fonts`: `{pairing, installed: false, pending: true}`) and the first batch
  that sets text installs it, from the font cache first and then the network, and reports it under the apply
  result's `font_install`. Creating a document never touches the network, and an empty document embeds no fonts
  (about 1 KB). A batch that chooses its own fonts (`font-pair`, `font-install`, `roll`) skips the pairing.
  Offline, the first text stays fast: `font_install` carries a `warning` and a `next_step`, the network is not
  retried for ten minutes in that process, and that document does not try again (run `font-pair` later).
  `workspace_fonts=false` (`--no-fonts`) embeds no fonts. The environment variable `VIXL_AUTO_FONTS=cache`
  never downloads, `VIXL_AUTO_FONTS=off` skips the pairing, and `VIXL_OFFLINE=1` keeps every download off.

**House style off.** `house_style: "off"` (`vixl new --house-style off`, `house_style="off"` in Python, MCP and
REST compose, or `{"house_style": "off"}` in `.vixl/variety.json`) skips the roll: the document gets a white
canvas (transparent for marks), the workspace default fonts else the bundled font, and `design_defaults` with
`house_style: "off"` and a neutral direction (mono palette, light mode, no accent, motif, look, style or
background treatment) that `layout-apply` follows. The craft rules still apply, and the default stays on. See
[house style](../../project/house-style.md#turning-the-house-style-off).

The result's `creation` says what was chosen and why (`size_from`: argument, purpose or default;
`background_from`: argument, palette, mark or neutral; `house_style: "off"` when it is off). `Project(width, height)` on its own is still a plain
transparent canvas with no `design_defaults`; pass `seed`, `variety`, `purpose` or `house_style` (or leave out the size) for a
design document, and `Project.sized(size, design=False)` for a plain named-size canvas.

A `layout-apply` without `seed` on such a document uses the whole stored direction, as
`the roll operation` does: the layout seed, palette, mode, type scale, density and accent, and the
margin, corner, look, style, motif and background treatment. Fields you pass win one by one. Passing
`seed` asks for a fresh choice instead of the stored direction.

The rolled density changes the result: airy widens and dense tightens the rolled margin (×1.25 and ×0.75)
and the spacing unit behind gaps (half the body size, craft `spacing.unit`). The roll weights density by
purpose (above); the builder, given no density, chooses balanced twice as often as airy or dense. The rolled accent (rule, bar, dot, block or outline) is drawn in the safe compositions next to
their own device. An outline frame insets the content two spacing units inside it. The pattern background's column of dots
and the direction motif are placed clear of the text (another margin, a shorter column, or left out), and
the overlap check reports decoration that runs through text as `overlap.decoration-text`.

`vixl_reference('roll')` and a plain `vixl roll` only preview a direction and change nothing. Applying one (the `roll`
step of `vixl_apply`, `vixl roll --apply`) installs its selected fonts,
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

`vixl_reference` attaches a roll to a brief kind. That roll favours the kind's recommended layouts,
looks and styles where the variety level allows their tier, and the answer's `recommendations`
says, for each list, what was rolled, whether it is one of the recommendations and which
recommendations are opt-in alternatives (with their tiers).

## Comparing variations

To choose between directions without trying them one by one, ask for variations of the open document. The `variations`
workflow rolls 2–4 seeds, applies each roll (palette, layout, fonts, look) to a copy of the document with the same copy,
and writes one labelled contact sheet; the document itself is not changed. The MCP tool returns the sheet as an image
beside the result.

```json
{"output": "options.png", "count": 3, "locks": {"palette": "ocean"}}
```

That is the request of `vixl_apply(workflow='variations', request=…)` (CLI: `vixl workflow variations --request FILE`).
`seeds` (2–4 different integers) replaces `count` fresh random seeds; `locks` fixes choices every tile keeps (lock the
palette to compare layouts, or the layout to compare palettes); `slots` gives the copy when the document has no layout
yet (otherwise the copy of its current layout is reused); `purpose`, `mood` and `variety` steer the rolls as they do
for the `roll` step; `width` and `columns` shape the sheet; `overwrite` replaces an existing `output`.

The result lists a tile per seed with its `layout`, `palette`, `pairing`, `mode` and `look`, its finding counts
(`fix` and `review`: a tile with a fix finding is a worse candidate) and `apply`, the `roll` step that makes it real.
Choose one and apply that step; it carries `replace: true`, so it takes the place of the layout the document has now,
and the same seed gives the same result as the tile (`{type: roll, seed: 12, replace: true, slots: {title: …}}` in the
operations of `vixl_apply`; `replace` also works on any `roll` step of a document that already has a layout).

## Reproducing and pinning

Unseeded workspace rolls keep at most 32 entries in `.vixl/rolls.json`. Recent
palette/layout choices receive lower selection weights, and consecutive rolls
avoid repeating either when another choice is available. Set the workspace policy
in `.vixl/variety.json` for repeatable tests or production:

```json
{"variety": "fixed", "seed": 29}
```

`variety.json` accepts `variety`, `seed` and `house_style` (`"on"`, the default, or `"off"`: new documents roll
no direction, see [New documents](#new-documents)); any other key is refused. Documents use the current house
style. A new document stores its rolled direction in `design_defaults`, and later rolls and layouts in that
document use it; an explicit roll still rolls the house style when the workspace turns it off.

## Measuring it

`python -m evals.house_style` rolls 48 sparse briefs across the eight purposes at each level, applies
them, and scores diversity (entropy of palette, layout, mode, pairing, look and style, and the mean
pairwise distance of renders) and quality (no `fix` findings, no `composition` findings, fonts installed, contrast). See
[the eval README](../../../evals/README.md#house-style-eval). The acceptance matrix also renders every safe
palette and composition at Open Graph, portrait social, and slide sizes, then checks contrast and text
legibility at their reading widths, and every layout a social roll can pick is applied at every named
social and web size and must pass its own safe-area check: text and buttons stay inside the canvas
safe area (on a 3:1 banner a safe composition sets its copy in two columns), while decoration and
full-bleed pictures are marked as such. Longer copy and custom overrides can still require adjustment; the
applied roll returns the measured findings.
