# Recipes

Vixl is headless and designed for autonomous AI agents; humans can use the same interfaces. See [new resources and SVG](resources.md) for 0.11 additions.

Each recipe is a single atomic batch where possible. Use them with MCP `vixl_operations_apply`,
`vixl apply ops.json`, REST `POST /operations`, or `Project.apply`. Always preview afterwards.

## Poster / social graphic with responsive layout

```json
[
  {"type":"gradient","name":"bg","direction":"angled","angle":35,
   "stops":[{"offset":0,"color":"#152235"},{"offset":0.5,"color":"#b36881"},{"offset":1,"color":"#e8885c"}]},
  {"type":"swatch","name":"ink","color":"#f6ecd7"},
  {"type":"text","name":"title","text":"AFTER HOURS","size":110,"color":"@ink","align":"center"},
  {"type":"text","name":"subtitle","text":"Live jazz · Fridays","size":40,"color":"@ink"},
  {"type":"constrain","target":"title","constraints":{"center-x":"canvas.center-x","center-y":"canvas.center-y-40"}},
  {"type":"constrain","target":"subtitle","constraints":{"center-x":"canvas.center-x","top":"title.bottom+24"}},
  {"type":"layer-style","target":"title","name":"drop-shadow","settings":{"dy":6,"blur":10,"opacity":0.5}}
]
```

Then retarget sizes without re-layout: `{"type":"canvas","preset":"story"}` (constraints reflow), or
keep one document with `artboard` ops (`{"type":"artboard","name":"story","preset":"story"}`) and
export each via `artboard=` / `vixl export-screens`.

QA: `vixl_check(safe_area="5%")` (overlap, contrast, cut-off content, thumbnail legibility; for
YouTube add `avoid=[["85%","85%","15%","15%"]]` for the timestamp), then
`vixl_validate(profile="instagram-post")`. `vixl_measure(target="title")` gives the exact contrast.

## Photo cleanup (non-destructive)

```json
[
  {"type":"select","shape":"none"},
  {"type":"auto-tone","target":"photo"},
  {"type":"contrast","target":"photo","amount":8},
  {"type":"saturation","target":"photo","amount":-5},
  {"type":"sharpen","target":"photo","amount":1.2},
  {"type":"vignette","target":"photo","strength":0.3,"radius":0.8}
]
```

Tweak later with `effect-set` (`effect` = index or `fx_` ID from `inspect`), toggle with
`effect-disable`. Save the stack as a preset (`preset-save`) and reuse it (`preset-apply`) — or for
a folder: `vixl batch './in/*.jpg' --run cleanup.vixlscript --output ./out`.

## Local edit through a selection

```json
[
  {"type":"select","shape":"ellipse","x":300,"y":120,"width":400,"height":400,"feather":30},
  {"type":"brightness","target":"photo","amount":15},
  {"type":"select","shape":"invert"},
  {"type":"blur","target":"photo","amount":6},
  {"type":"select","shape":"none"}
]
```

The effects keep their captured selections; clearing at the end prevents surprises in later edits.

## Cut-out with a mask

```json
[
  {"type":"select","shape":"color","color":"#ffffff","tolerance":20},
  {"type":"select","shape":"invert"},
  {"type":"mask","target":"product","action":"from-selection"},
  {"type":"select","shape":"none"}
]
```

Or with a provider: `vixl_ai_remove_background(layer="product")`.

## Template with variables and image slots

```json
[
  {"type":"variable","name":"headline","value":"Summer Sale"},
  {"type":"variable","name":"accent","value":"#ff5a36"},
  {"type":"text","name":"headline","text":"${headline}","size":96,"color":"${accent}"},
  {"type":"frame","name":"hero","asset":"assets/<sha256>.png","width":800,"height":600,"fit":"fill"},
  {"type":"variable","name":"hero_asset","value":"assets/<sha256>.png"},
  {"type":"replace-contents","target":"hero","variable":"hero_asset"}
]
```

Variants: `vixl_render_preview(variables={"headline":"Winter Sale"})`,
`vixl_export_file(path="winter.png", variables={...})`, or CSV in the CLI:
`vixl render --data rows.csv --out campaign` (headers = variable names; image columns may hold asset
IDs or file paths relative to the CSV). Get embedded asset IDs from
`vixl_document_inspect(detail="full")` / `vixl manifest`.

## Evenly spaced row of cards

```json
[
  {"type":"shape","shape":"rounded-rectangle","name":"card","width":300,"height":400,"radius":24,"fill":"#1f2a3d","y":200},
  {"type":"duplicate","target":"card","name":"card2"},
  {"type":"duplicate","target":"card","name":"card3"},
  {"type":"distribute","targets":["card","card2","card3"],"axis":"horizontal","gap":40},
  {"type":"group","name":"cards","targets":["card","card2","card3"]},
  {"type":"align","target":"cards","alignment":"center"}
]
```

Verify: `vixl_measure_spacing(targets=["card","card2","card3"], axis="horizontal", expected=40, tolerance=0)`.
(Spacing targets must be siblings — they still are, inside the group.)

## Pattern: stripes clipped to a shape

```json
[
  {"type":"shape","shape":"ellipse","name":"sun","width":640,"height":640,"x":220,"y":40,"fill":"#e8885c"},
  {"type":"shape","shape":"rectangle","name":"stripe","width":700,"height":6,"x":190,"y":360,"fill":"#152235"},
  {"type":"repeat","target":"stripe","count":8,"dy":37,"dh":2},
  {"type":"group","name":"stripes","targets":["stripe"]},
  {"type":"clip","target":"stripes","base":"sun"}
]
```

## Pixel sprite with a 2-frame animation

```json
[
  {"type":"canvas","width":16,"height":16,"background":"transparent"},
  {"type":"pixel-art","name":"coin","width":16,"height":16,
   "palette":{".":"transparent","g":"#ffc44d","s":"#9c5f22","w":"#fff3bd"}},
  {"type":"pixel-draw","target":"coin","tool":"rect","x":4,"y":3,"width":8,"height":10,"color":"s"},
  {"type":"pixel-draw","target":"coin","tool":"rect","x":5,"y":4,"width":6,"height":8,"color":"g"},
  {"type":"frame-save","name":"idle","duration":150},
  {"type":"pixel-draw","target":"coin","tool":"line","x":6,"y":5,"x2":9,"y2":5,"color":"w"},
  {"type":"frame-save","name":"glint","duration":100},
  {"type":"animation-set","order":["idle","glint"],"loop":0}
]
```

Inspect as text with `vixl_pixels_inspect("coin")`; preview `vixl_animation_preview("glint", scale=8)`;
export `vixl_export_animation(path="coin.gif", format="gif", scale=8)` or `format="sheet"` for a game
engine (writes `coin.png` + `coin.json`). Static enlargements: `sampling="nearest"`.

## Explore alternatives safely

```text
vixl_history(action="checkpoint", ref="base")
… edits …                     → vixl_history(action="branch", ref="warm")
vixl_history(action="checkout", ref="base")
… other edits …               → vixl_history(action="branch", ref="cool")
```

MCP: `vixl_render_compare(before="warm", after="cool")` returns both side by side (or
`mode="diff"` to highlight changes). CLI: `vixl compare warm cool --out compare.png`. Use a transaction
(`begin` … `commit`/`rollback`) when a multi-call change should be a single undo step.

## Brand system

```json
[
  {"type":"swatch","name":"brand","color":"#e8885c"},
  {"type":"style-define","name":"Heading","settings":{"size":80,"color":"@brand"}},
  {"type":"style-define","name":"Centered","kind":"paragraph","settings":{"align":"center","spacing":8}},
  {"type":"style-apply","target":"title","name":"Heading"},
  {"type":"style-apply","target":"title","name":"Centered","kind":"paragraph"},
  {"type":"symbol","target":"logo","name":"Brandmark"},
  {"type":"symbol-instance","symbol":"Brandmark","name":"footer-logo","x":40,"y":980,"width":80,"height":80}
]
```

Redefining `brand` or `Heading` later updates every linked layer; editing `logo` updates instances.

## Open brief → structured design (layouts)

```text
vixl_document_create(path="talk.vixl", size="slide")
vixl_layouts_list()                                              # pick by medium and intent
vixl_operations_apply(operations=[{"type":"layout-apply","name":"slide-title",
  "title":"Designing for agents","subtitle":"Jordan Lee · Product Design","caption":"Conf 2026","seed":2}])
vixl_check() ; vixl_render_preview()
# Not right? Try another seed or pin choices, replacing the previous layout:
vixl_operations_apply(operations=[{"type":"layout-apply","name":"slide-title","replace":true,"seed":9,
  "title":"Designing for agents","subtitle":"Jordan Lee · Product Design","mode":"dark","type_scale":"golden"}])
# Retint everything by editing one role swatch:
vixl_operations_apply(operations=[{"type":"swatch","name":"accent","color":"oklch(0.68 0.17 35)"}])
```

## Print-ready flyer

```bash
vixl new letter --bleed -o flyer.vixl
vixl -p flyer.vixl layout apply event-poster --set title='Summer Night Market' --set label='Sat · June 21' \
  --set body=$'6 pm – 11 pm\nRiverside Park\nFree entry' --set cta='RSVP' --palette sunset --seed 5
vixl -p flyer.vixl check --checks bounds overlap contrast print
vixl -p flyer.vixl export flyer-proof.png --proof --scale 0.25
vixl -p flyer.vixl export flyer.pdf --cmyk --ink-limit 300        # add --icc PRINTER.icc when supplied
```

## Logo and icon set

```bash
vixl new logo-horizontal -o logo.vixl
vixl -p logo.vixl layout apply logo-horizontal --set title='Harbor' --set subtitle='Coffee roasters' --seed 2
vixl -p logo.vixl export logo.svg --svg-policy strict
vixl new favicon -o icon.vixl
vixl -p icon.vixl layout apply app-icon --set title='Harbor' --palette ocean
vixl -p icon.vixl export-icons --out icons --set all
```

## Hand-drawn accent

```text
vixl_operations_apply(operations=[
  {"type":"paint-layer","name":"marks"},
  {"type":"paint","target":"marks","brush":"marker","points":[[120,610],[420,600],[700,615]],"size":26,"color":"alpha(@accent, 0.7)"},
  {"type":"paint","target":"marks","brush":"brush-pen","path":"M760 540 C820 470 900 520 860 600","size":10,"color":"@ink"}])
```

## Animated social post

```text
vixl_operations_apply(operations=[
  {"type":"timeline-set","duration":"3s","fps":24},
  {"type":"animate-preset","target":"label","preset":"fade-in","duration":"0.4s"},
  {"type":"animate-preset","target":"headline","preset":"slide-in-up","start":"0.2s","duration":"0.7s"},
  {"type":"animate-preset","target":"cta","preset":"pop-in","start":"0.9s","duration":"0.5s"},
  {"type":"animate-preset","target":"cta","preset":"pulse","start":"2s","duration":"0.6s"}])
vixl_timeline_preview(count=8)
vixl_export_timeline(path="post.mp4")          # needs ffmpeg; otherwise post.webp or post.gif
```
