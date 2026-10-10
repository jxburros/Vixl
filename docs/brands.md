# Workspace brands

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Put `brand.json` in the MCP workspace root. CLI commands use the current working directory as the workspace. Python uses an explicit workspace when supplied and otherwise resolves resources beside the saved document; commands without a document use the current directory. With `-p DOC` or a current session document, `roll` previews read that document's canvas
and brand, so a preview picks the same direction as `roll --apply`. Use `create_template(..., workspace=...)` in Python to select it explicitly.
The file is read on each operation/check, so a policy change takes effect without a restart.

```json
{
  "name": "Example",
  "palette": {
    "background": "#ffffff",
    "surface": "#eeeeee",
    "ink": "#111111",
    "muted": "#444444",
    "accent": "#0044aa",
    "accent-text": "#0044aa",
    "on-accent": "#ffffff"
  },
  "pairing": "source-serif-sans",
  "minimum_contrast": 4.5,
  "required_elements": ["logo"],
  "logos": [{"name": "logo", "data_base64": "BASE64_PNG_BYTES", "x": 24, "y": 24}]
}
```

Replace the logo placeholder with actual base64 image bytes, or omit `logos` and its required
element. Logos embed in the document and stay above generated backgrounds. They are added once
by layer name. Place/resize them to suit the composition after applying the layout.

`layout apply`, template creation/application, and `roll` use the brand palette and typography
by default. Explicit layout palette/color/font options and roll locks take precedence. Unspecified
color roles are derived by the normal layout system; specifying all seven roles avoids unexpected
colors. `check` warns about colors outside the supplied palette and fonts outside the configured
pairing, errors on missing required layer names, and enforces `minimum_contrast` even if a caller
asks for a lower threshold. `check --checks brand` isolates policy findings.

A colour matches the palette by its RGB, so a translucent brand colour (`#d4241c80`) is still on brand, and a
translucent black or white layer style or effect colour (a `#00000066` drop shadow, a white glow) darkens or
lightens what is under it without counting as a colour of its own. An opaque or tinted shadow outside the palette
is still reported, with the `color` it used.

`minimum_contrast` is one ratio for all text, or a floor per text size, so a display colour can pass at
WCAG's large-text 3:1 while small text keeps 4.5:1:

```json
{"minimum_contrast": {"text": 4.5, "large_text": 3.0, "large_text_px": 24}}
```

`text` is required; `large_text` defaults to `text`, `large_text_px` to 24 and `large_bold_text_px` to 18.66
(scaled with `large_text_px` when only that is given). Sizes are rendered canvas pixels, after group scaling. The
`contrast` and `color_vision` checks apply the tier, and a caller's `min_contrast` raises both tiers but cannot go
below the brand's. A bare number such as `4.5` is the floor for both tiers, as before.

Pairings download/cache fonts as usual. For an offline or proprietary pairing, replace `pairing`
with embedded fonts:

```json
{
  "fonts": {
    "heading": {"name": "brand-heading", "data_base64": "BASE64_TTF_BYTES"},
    "body": {"name": "brand-body", "data_base64": "BASE64_TTF_BYTES"}
  }
}
```

An embedded font wins for its role and the pairing supplies the other, so a kit can embed only a
heading font. `vixl_font_pair`/`vixl_font_install` with `scope: "workspace"` write these fields for you,
and new documents embed the workspace fonts at creation (see [Typography](typography.md#workspace-default-fonts)).

### Font roles, text stages and extra colours

`fonts` takes any lowercase role name, not only `heading` and `body`: a brand with four type voices lists
four roles. A role is either embedded (`name` + `data_base64`) or fetched like a pairing (`family`, optional
`weight` and `name`). Every role is registered in the document typography, so `text`, templates and layouts
can name it (`"font": "hand"`), and the brand check accepts text set in any of them.

`stages` maps the text stages (display, h1, h2, h3, subtitle, lead, body, caption, citation, label; see
[Typography](typography.md#text-stages)) onto those roles, optionally with a type-scale `step`, a
`line_height` and a `case`. Unmapped stages inherit: display and h1–h3 take `heading`, the rest `body`.

`palette.extra` lists approved colours that have no layout role (a material ink, an optional secondary).
They become swatches by name (`@wood`), the brand check accepts them, and `max_fraction` caps how much of a
design one may cover. A list of colours is named `extra-1`, `extra-2` …

```json
{
  "name": "JXG",
  "palette": {
    "background": "#f4efe6", "surface": "#e8e0d2", "ink": "#1d1a16", "muted": "#5b5249",
    "accent": "#c8102e", "accent-text": "#a10d25", "on-accent": "#ffffff",
    "extra": {"wood": {"color": "#d2a465", "max_fraction": 0.15}, "ballpoint": "#1f3a93"}
  },
  "fonts": {
    "heading": {"family": "Anton", "weight": 400},
    "body": {"family": "Special Elite", "weight": 400},
    "hand": {"family": "Caveat", "weight": 500},
    "allowed": ["Anton", "Special Elite", "Caveat"]
  },
  "stages": {"display": "heading", "citation": "hand", "label": {"font": "heading", "case": "upper"}}
}
```

### Presets

One workspace can hold several looks of one brand (an album era, a campaign) as named `presets`. A preset
is a partial brand: `palette`, `fonts`, `stages`, `colors` and `logo` merge key by key over the base, any
other field (`minimum_contrast`, `logos`, `required_elements`, `pairing`) replaces it, and `extends` builds
on another preset. A document selects one with the `brand-preset` operation; layouts, templates, rolls and
the brand check then use the preset, and `{"type": "brand-preset", "name": "none"}` returns to the base.
Selecting a preset installs its swatches, fonts and stages at once.

```json
{"type": "brand-preset", "name": "flames"}
```

<!-- docs-test: save brand.json -->
```json
{
  "name": "Example",
  "palette": {
    "background": "#ffffff", "surface": "#eeeeee", "ink": "#111111", "muted": "#444444",
    "accent": "#0044aa", "accent-text": "#0044aa", "on-accent": "#ffffff",
    "extra": {"wood": "#d2a465"}
  },
  "stages": {"label": {"font": "heading", "case": "upper"}},
  "colors": {"strict": true, "tolerance": 4},
  "logo": {"clear_space": 0.5, "min_size": "10mm"},
  "presets": {
    "flames": {"palette": {"background": "#1a0f0a", "surface": "#2a1a12", "ink": "#f6e7d2", "muted": "#c9b8a3",
                           "accent": "#e8562a", "accent-text": "#f08a5d", "on-accent": "#1a0f0a"},
               "minimum_contrast": 3},
    "embers": {"extends": "flames", "palette": {"accent": "#d2a465"}}
  }
}
```

### Compliance rules

`check --checks brand` (and the default checks) enforce what the brand states. Every finding is a must-fix
(`action: fix`), and the rules also run inside a check suite as a `design` rule with
`options: {"checks": ["brand"]}`, so a group of documents can share them.

| Field | Finding |
| --- | --- |
| `fonts.allowed` | A text layer (or rich-text span) whose font family is not listed and is not a brand font: an error naming the layer, the family and the allowed families. |
| `colors.strict` | A fill, stroke, text or gradient colour further than `colors.tolerance` (maximum channel difference, 0–255; default 0) from every palette role and extra colour is an error naming the nearest distance. Without `strict` an off-palette colour stays a warning. |
| `palette.extra[].max_fraction` | An extra colour covering more of the rendered design than allowed (warning). |
| `logo.clear_space` | Another layer closer to a logo than this fraction of the logo's height: an error with the measured `gap` and the `required` distance. A backdrop that contains the whole clear-space zone (the ground the logo sits on) and layers marked as background do not count. |
| `logo.min_size`, `logo.min_width` | A logo shorter or narrower than the minimum: pixels, or a length such as `12mm`, `0.5in` or `24pt` converted with the canvas dpi (96 without one). |

Logo layers are the names in `logo.layers`, else the embedded `logos` names, else layers named `logo`
(`logo`, `logo-mark`, `brand logo` …); a logo group counts as one logo. Approved logo variants on approved
backgrounds are not checked yet.

```json
{"colors": {"strict": true, "tolerance": 4}, "logo": {"clear_space": 0.5, "min_size": "10mm", "layers": ["logo"]}}
```

### Validate and show

`vixl brand validate [--preset NAME]` checks `brand.json` without changing anything: the file and every
preset must be valid; a stage that names a font role the brand does not define, an embedded font or logo
that does not decode, and `colors.strict` without a palette are errors; palette roles left to derivation,
missing heading or body fonts, `logo.layers` that name no embedded logo, and workspace guidance texts that
name hex colours the palette does not approve are warnings. `vixl brand show [--preset NAME]` prints the
resolved brand: roles, extra colours, fonts, the stage map, logos and rules.

### Brand board

The `brand-board` workflow draws the brand as a guidelines document, one slide-sized page per topic: a
cover (name, preset, first logo), colour (role swatches with hex values, extra colours and the text contrast
pairs judged against `minimum_contrast`), typography on two pages (every text stage set in its own font, size
and line height, labelled with its role and face), logos (on the light and dark brand colours, with the
clear-space zone outlined) and do/don't rules built from whatever the brand constrains. `output` is a `.pdf`,
`.pptx` or `.html` (or `.vixl` for the editable document only); `document` also saves the editable board,
`preset` draws a preset, and nothing is overwritten unless `overwrite` is true.

<!-- docs-test: save board.json -->
```json
{"output": "brand-guidelines.pdf", "document": "brand-guidelines.vixl"}
```

```bash
vixl brand validate
vixl brand show --preset embers
vixl workflow brand-board --request board.json
```

MCP: `vixl_workflow(action="brand-board", request={"output": "brand-guidelines.pdf"})`. Python:
`vixl.brand_board.build_document(workspace, preset=None)` returns the editable board and a report.

Only data is accepted; brand files cannot name server filesystem paths. JSON is limited to 16 MiB.
The policy stays in the workspace while fonts, logos and colors are embedded in each document.
Moving a document without `brand.json` preserves its appearance but stops workspace policy checks.

```bash
vixl -p poster.vixl roll --apply --for poster --seed 42 \
  --lock layout=event-poster --set title='Launch' --set label='Friday' \
  --set body='Doors at 6' --set cta='example.com' --set caption='All ages'
```

MCP uses `vixl_roll(apply=true, slots={...})`. Font downloads and the layout commit together as
one undo step; failures leave the document unchanged. Layout application returns `unfilled_slots`
and full layout notes immediately, including for compact responses and dry runs.

## Copy rules and shared suites

Three optional fields hold the brand's copy policy and its contract:

```json
{
  "words": {"forbid": ["cheap", "world-class"], "prefer": {"utilize": "use", "e-mail": "email"}},
  "placeholders": ["\\bCOPY TK\\b", "\\[\\[.*?\\]\\]"],
  "suites": ["delivery"]
}
```

`words.forbid` phrases (whole words, any case) are `brand` errors in `check`; a `words.prefer` word is a
`review` finding that names the preferred one; a `text` suite rule with `brand: true` also forbids them.
Spelling against a dictionary is not checked. `placeholders` adds regular expressions to the
`placeholders` check (leftover template copy). `suites` names library suites that every document in the
workspace inherits by reference (see [library suites](production.md#library-suites-shared-by-a-group-or-the-workspace)).

## One brand across several documents

Create all documents from the same workspace containing `brand.json`. Pin the pairing (or embed heading/body fonts) and all seven palette roles there. Keep those brand settings unchanged while rolling different layouts: the brand wins over the rolled pairing and palette, while explicit operation fields win over the brand. Use the same `mode`, font and palette overrides on `layout-apply` when an exact campaign direction matters; a shared seed alone is insufficient across different purposes and aspect ratios. `roll` previews report the selected direction before applying it. Check each result with the default checks and `check --checks brand`.

Fresh documents install their selected colour roles as swatches. `palette-apply` updates a canvas that still uses its previous background role, while preserving a deliberately different canvas colour. Primitive and diagram operations can therefore resolve the same palette roles without applying a full layout first.
