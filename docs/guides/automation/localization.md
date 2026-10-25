# Localization

[Guides](../README.md) · [Production workflows](production.md) · [Check designs in CI](ci.md)

One master document, many languages. The localization plugin keeps each locale's text as variable values, checks
every locale on a candidate copy before anything is written, and builds one checked variant per locale: derived
documents, exports or a whole campaign. A locale whose text does not fit, has characters no font can draw or lacks
a translation is held with its findings instead of being shipped.

## Locale tables

Text that changes per language reads a variable (`${headline}`). The document's `locales` record gives each locale's
values; `locales-set` merges into it (a `null` value removes a key, a `null` table removes a locale). The source
locale (`source`, default `en`) takes its values from the document's own variables unless the table lists it.

```json
[
  {"type": "variable", "name": "headline", "value": "Summer sale"},
  {"type": "variable", "name": "cta", "value": "Shop now"},
  {"type": "text", "name": "headline", "text": "${headline}", "size": 32, "x": 20, "y": 20},
  {"type": "text-layout", "target": "headline", "width": 300, "height": 50},
  {"type": "text", "name": "cta", "text": "${cta}", "size": 18, "x": 20, "y": 120},
  {"type": "locales-set", "locales": {
    "de": {"headline": "Sommerschlussverkauf mit riesigen Rabatten", "cta": "Jetzt kaufen"},
    "fr": {"headline": "Soldes d'été", "cta": "Acheter"},
    "ar": {"headline": "تخفيضات الصيف", "cta": "تسوق الآن"}},
   "same_ok": ["Vixl"], "fit": "shrink", "min_size": 14}
]
```

`locales-set` also stores the options the check and `localize` use (`locale_options`); a request can override each:

| Option | Meaning |
| --- | --- |
| `source` | The locale the others are compared with (default `en`). |
| `same_ok` | Keys or values that may stay equal to the source (brand and product names). |
| `fonts` | `{code: [font names]}`: registered fonts tried first for that locale, ahead of the document's `font-fallbacks`. |
| `fit` | `shrink` (run `fit-text` down to `min_size`) or `flag` (report only; the default), for every text layer or `{layer name: policy, "*": default}`. |
| `min_size` | Smallest size `shrink` may set, in pixels (default 12). |
| `rtl` | Locales laid out right to left (default the `ar`, `he` and `fa` locales). |
| `mirror` | `false` keeps right-to-left locales unmirrored. |

**Strings CSV.** Translations usually arrive as a spreadsheet: one row per key and one column per locale. Pass it as
`strings` (with `key_column`, default `key`, and optionally `languages`, the columns to read). Columns whose header is
not a locale code (notes, context) are ignored, `pt_BR` reads as `pt-BR`, and an empty cell is a missing key. CSV
values win over the document's.

**Group locales.** A project group can hold a locale table for all its members:
`group-locales {name, locales, replace}`. A document's own values win over its groups'; redefining the group with
`group-define` keeps the table.

## The locale check

`vixl check --locales all` (or `de,ja`) checks each locale on a candidate copy: its values applied, its font
fallbacks, and for a right-to-left locale the mirrored layout. Nothing is saved. The source is checked the same way
first, and a locale's row lists only what it adds over the source. The workflow `check` takes the same `locales`
field (with `suite`, `suites` and `variables`), and the `locale-check` action takes every option above plus
`strings`, `fail_on` (error, warning or never), `format: markdown` and an `output` file.

| Finding | When |
| --- | --- |
| `overflow` | Text cut off by its box or running off the canvas, or a failed `text-fit` rule. |
| `fonts` | Characters no font can draw (an error), or fallback glyphs (a warning). |
| `untranslated` | A value equal to the source's and not in `same_ok` (a warning). |
| `missing-key` | A key the other locales have and this one lacks (an error: the source text would show). |
| `line-count` | A text layer sets in a different number of lines and a `hierarchy` rule that passes in the source fails. |
| `design`, `suites` | Any other new design finding or failed rule of the attached suites. |

The report holds `matrix` (locale x finding counts), `results` per locale (status, findings, `missing`, changed
`lines`, `mirrored` layers) and `passed`. `--format markdown` prints the matrix, then each locale's findings in the
same table as `vixl check --all`; the command exits with 1 when a locale fails.

```bash
vixl new 400x300 -o master.vixl
vixl -p master.vixl apply locales.json
vixl -p master.vixl check --locales all --format markdown
vixl -p master.vixl check --locales de,fr --strings strings.csv --json
```

<!-- docs-test: save locales.json -->
```json
[
  {"type": "variable", "name": "headline", "value": "Summer sale"},
  {"type": "text", "name": "headline", "text": "${headline}", "size": 32, "x": 20, "y": 20},
  {"type": "text-layout", "target": "headline", "width": 300, "height": 50},
  {"type": "locales-set", "locales": {"de": {"headline": "Sommerschlussverkauf"}, "fr": {"headline": "Soldes"}},
   "fit": "shrink"}
]
```

<!-- docs-test: save strings.csv -->
```text
key,de,fr,notes
headline,Sommerschlussverkauf mit riesigen Rabatten,Soldes d'été,hero line
```

## Building the locales: localize

`localize` builds every locale that passes and holds the rest:

<!-- docs-test: continue -->
```bash
vixl -p master.vixl workflow localize --request localize.json
```

<!-- docs-test: save localize.json -->
```json
{"locales": "all", "strings": "strings.csv", "output_dir": "localized", "formats": ["png"], "fit": "shrink",
 "min_size": 14}
```

- **Outputs.** Each passing locale writes `<master>.<code>.vixl` (a copy of the master with that locale's values, its
  fonts and layout, without the locale table) unless `documents: false`, and one export per `formats` entry
  (`png`, `jpg`, `webp`, `svg`, `pdf`) into `output_dir` (default `localized`).
- **Campaigns.** With `spec` (the `run` action's campaign spec), each localized document runs the campaign into
  `<output_dir>/<code>/`: rows x matrix x locales. Production's own fingerprints make those runs resumable too.
- **Fit.** `shrink` fits overflowing boxed text with `fit-text` between `min_size` and its size; the repair is listed
  under the locale's `repairs`. Text that cannot fit even at `min_size`, or text under a `flag` policy, is an
  `overflow` finding.
- **Right to left.** For `ar`, `he` and `fa` (or `rtl`), each top-level layer is anchored the way `adapt-layout`
  infers it and moved to the mirrored position (a top-left logo becomes top-right; a layer spanning the canvas stays),
  layout constraints swap sides and text alignment swaps left and right. Glyph order is the shaper's (bidi) job.
- **Held locales.** A missing key, or a finding at `fail_on` (default error), holds the locale: nothing is written for
  it, `held` names it with its findings, and the run's `status` is `needs_review`.
- **Re-runs.** `localize.json` records each locale's fingerprint: its localized state, fonts, links, the renderer and
  the build settings. Running again rebuilds only the locales whose fingerprint changed (a new German translation
  rebuilds German; a change to shared artwork rebuilds all) and reports the rest as `reused`. A file in `output_dir`
  that the record did not write is refused unless `overwrite: true`.

## Limits

- Mirroring moves top-level layers and flips constraints and alignment; layers inside a group keep their place in it.
- Per-locale fonts are fallbacks for the characters the main font lacks; they do not replace the main font.
  Register them first (`font import`, `font-cover`), as `font-fallbacks` needs.
- The check covers the still document; `localize` with `spec` runs the campaign's own checks per output.
