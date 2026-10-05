# Workspace brands

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Put `brand.json` in the MCP workspace root. CLI/Python document edits look beside the document;
commands without a document, including template creation and standalone roll, use the current
directory. With `-p DOC` or a current session document, `roll` previews read that document's canvas
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
