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

## One brand across several documents

Create all documents from the same workspace containing `brand.json`. Pin the pairing (or embed heading/body fonts) and all seven palette roles there. Keep those brand settings unchanged while rolling different layouts: the brand wins over the rolled pairing and palette, while explicit operation fields win over the brand. Use the same `mode`, font and palette overrides on `layout-apply` when an exact campaign direction matters; a shared seed alone is insufficient across different purposes and aspect ratios. `roll` previews report the selected direction before applying it. Check each result with the default checks and `check --checks brand`.

Fresh documents install their selected colour roles as swatches. `palette-apply` updates a canvas that still uses its previous background role, while preserving a deliberately different canvas colour. Primitive and diagram operations can therefore resolve the same palette roles without applying a full layout first.
