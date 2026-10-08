# CLI reference

Vixl is headless and designed for autonomous AI agents; humans can use the same interfaces. See [new resources and SVG](resources.md) for 0.11 additions.

```text
vixl [GLOBAL OPTIONS] COMMAND [ARGS]
vixl                      # interactive shell (don't use from an agent; use commands)
vixl COMMAND --help       # exact argument syntax for any editing command
```

**Global options** (before or after the command): `--project/-p FILE`, `--json` (structured
errors on stderr), `--allow-linked` (trust linked file references), `--plugins` (enable installed
filter/provider entry points — trusted code), `--max-pixels N`, `--version`.

Agent conventions:

- Always pass `-p FILE.vixl`. Without it Vixl uses the project recorded by `vixl open` in
  `./.vixl-session.json`.
- Add `--json` so errors are machine-readable: `{"error":"layer_not_found","message":…,"suggestions":[…]}`, exit 1.
- Editing commands autosave and print a full before/after diff — redirect it if you don't need it.
- Quote `#` colors (`'#ff8800'`), JSON arguments, and text.
- A target is a unique layer name or `lyr_…` ID; most commands default to the active layer when it is omitted.
- Every editing command below compiles to a canonical operation (see `operations.md`), so
  `vixl apply ops.json` can replace any sequence of them atomically.

## Finding vixl

If `vixl --version` fails with "command not found", check the standard locations before asking
the user where Vixl is:

| Install | Location | Check |
| --- | --- | --- |
| Windows installer | `%LOCALAPPDATA%\Programs\Vixl\bin\vixl.exe` | Git Bash: `"$LOCALAPPDATA/Programs/Vixl/bin/vixl.exe" --version`; PowerShell: `& "$env:LOCALAPPDATA\Programs\Vixl\bin\vixl.exe" --version`; cmd: `"%LOCALAPPDATA%\Programs\Vixl\bin\vixl.exe" --version` |
| Windows installer alias | `%LOCALAPPDATA%\Microsoft\WindowsApps\vixl.exe` | Same launcher; that folder is on PATH by default on Windows 10/11, so terminals opened before installation usually find `vixl` through it |
| pip / source | the Python environment | `python -m vixl --version` (use `python -m vixl` wherever this page says `vixl`) |

The installer adds `%LOCALAPPDATA%\Programs\Vixl\bin` to the user PATH, but processes that were
already running (a desktop app and the terminals or agents it spawns) keep their old PATH until
restarted. Prepend the folder for the current session instead:

```bash
# Git Bash (PATH uses /c/... form there, so convert the C:\ path with cygpath)
export PATH="$(cygpath -u "$LOCALAPPDATA")/Programs/Vixl/bin:$PATH"
```

```powershell
$env:Path = "$env:LOCALAPPDATA\Programs\Vixl\bin;$env:Path"   # PowerShell
```

```bat
rem cmd
set "PATH=%LOCALAPPDATA%\Programs\Vixl\bin;%PATH%"
```

## Documents and inspection

| Command | Effect |
| --- | --- |
| `new 1920x1080 -o F.vixl [--background COLOR]` | Create (refuses to overwrite); also selects it |
| `open F.vixl` | Select as default project for this directory |
| `save [COPY.vixl]` | Save / save-as |
| `status` | Canvas, active layer, head, branch, transaction flag |
| `inspect [LAYER]` | Full JSON state (or one layer) incl. `resolved_bounds` |
| `layers [--full]` | Layer list (long path data abbreviated unless `--full`) |
| `describe` | Document description |
| `effects [LAYER]` | Effect stack with IDs/indices |
| `manifest`, `dependencies`, `reproduce --check` | Assets, fonts, providers; can it re-render? |
| `schema` | JSON Schema of all operations |
| `pixels [LAYER]` | Pixel layer as rows + palette |
| `animation` | Frame names, sizes, durations |

## Creating layers

```bash
vixl add photo.jpg --name hero [--x 0 --y 0] [--linked]         # alias: layer add
vixl solid --name panel --width 400 --height 200 --color '#26344e' [--x --y]
vixl gradient --name sky --start '#152641' --end '#635e83' --direction vertical|horizontal|radial|angled [--angle 35]
vixl gradient --name sky --direction angled --angle 35 --stops '[{"offset":0,"color":"#152235"},{"offset":1,"color":"#e8885c"}]'
vixl text add 'Hello' --name title --size 96 --color white [--font path.ttf] [--align center] [--spacing 8 | --line-height 1.1] [--x center --y 120]
vixl shape rectangle|rounded-rectangle|ellipse|polygon|star|arc|line --name s --width W --height H [--x --y] \
     [--fill C] [--stroke C] [--stroke-width N] [--radius N] [--sides N] [--inner-radius 0.4] \
     [--line-cap butt|round|square] [--trim-start PCT] [--trim-end PCT]
     [--start-angle -90 --end-angle 70]   # arc: pie wedge / donut segment (0 = 3 o'clock, clockwise)
vixl frame --path portrait.jpg --name photo --width 400 --height 500 --fit fill|fit [--asset ID]
vixl pixel-art --name sprite --width 16 --height 16 [--palette '{".":"transparent","g":"#ffc44d"}'] [--background .]
vixl pixel-art --name spark --rows '[".w.","www",".w."]' --palette '{".":"transparent","w":"#fff"}'
vixl adjustment warmth --effects '[{"name":"temperature","amount":40},{"name":"contrast","amount":10}]'
vixl symbol-instance Brandmark --name footer-logo --x 100 --y 800 --width 100 --height 100
vixl irregular hero eyes --seed 7 [--strength subtle|natural|rough] [--only wobble color] [--remove]  # opt-in imperfection
vixl tear photo --seed 3 --edges bottom [--as mask|clip|path] [--strength rough] [--rim-width 5]      # torn edge
```

## Layer management and transforms

```bash
vixl select-layer hero
vixl layer rename hero portrait          # 'layer' namespace optional: vixl rename …
vixl duplicate portrait copy
vixl hide copy ; vixl show copy ; vixl remove copy   # rm = remove
vixl raise|lower|top|bottom portrait
vixl reorder logo --above portrait       # or --below
vixl move portrait 100 200 ; vixl move portrait --x 100 ; vixl move portrait 20 0 --relative   # mv = move
vixl scale portrait 80%                  # or 0.8
vixl resize portrait 800x600 ; vixl resize portrait --width 800 [--keep-aspect]   # one side alone leaves the other (images scale proportionally); --no-keep-aspect to stretch
vixl rotate portrait 15                  # clockwise degrees about the pivot (default: center)
vixl pivot arm 0.5 0.05                  # fractions of the box; pivot arm top | pivot arm 8 2 --px | pivot arm 410 300 --canvas | pivot arm --clear
vixl flip portrait horizontal|vertical
vixl scale beam --x -1                   # negative factors mirror (--x/--y per axis, or a bare -1 for both)
vixl crop portrait 0 0 300 400           # X Y W H in the source raster
vixl opacity portrait 0.75               # or 75% (0–1 scale; a bare 75 is an error)
vixl blend portrait multiply             # normal multiply screen overlay darken lighten difference add subtract
vixl rasterize title                     # bakes effects, styles and clipping into pixels
vixl merge-layers back disc --name art   # one raster layer at the topmost's slot ; vixl flatten [--keep-hidden]
vixl group stripes stripe1 stripe2 [--above LAYER|--below LAYER] ; vixl ungroup stripes
vixl reparent tail --into dog [--above L|--below L|--index N] [--keep appearance|local] [--no-fit] ; vixl reparent tail --into page
vixl stack names --targets first last company --gap 20 --align center --justify center --width 1000 --height 400   # auto-layout; empty hide_if_empty text collapses
vixl stack names --direction horizontal --gap 8 ; vixl stack names --remove ; vixl text first --hide-if-empty
vixl shape --target bar --fill '#6b3f69'    # solid/gradient/shape/text add --target edit a layer in place
vixl clip TARGET BASE ; vixl clip TARGET --release
```

## Text

```bash
vixl text title --text 'Good evening' --size 80 --align center --color '#fff' --spacing 6
vixl text title --stroke-width 2 --stroke-color black
vixl text-layout title --width 600 --height 180 [--fit] [--warp arc|flag|bulge|none --amount 0.15] [--path '[[10,90],[300,20],[590,90]]']
vixl swatch brand '#e8885c'
vixl style-define Heading --settings '{"size":80,"color":"@brand","stroke_width":1}'
vixl style-define Caption --kind paragraph --settings '{"align":"center","spacing":8}'
vixl style-apply title Heading ; vixl style-apply title Caption --kind paragraph
```

## Layout

```bash
vixl align logo top-right --margin 40
vixl align title left --relative-to logo
vixl align title center-y --targets title logo badge      # relative to the selection's union
vixl distribute horizontal a b c [--gap 24]
vixl constrain title --center-x canvas --center-y canvas
vixl constrain logo --right canvas.right-40 --top canvas.top+40
vixl constrain caption --center-x canvas --below title 24  # top = title.bottom+24
vixl guide left-margin x 64                               # a vertical guide at x = 64
vixl constrain badge --left guide:left-margin.left        # one constraint per axis: unconstrain to switch
vixl unconstrain logo
vixl canvas resize 1080x1080 ; vixl canvas preset story ; vixl canvas background transparent
vixl grid editorial --columns 3 --rows 2 --margin 64 --gutter 24
vixl artboard story --preset story ; vixl artboard banner --width 1600 --height 600
```

## Selections, masks, effects

```bash
vixl select rect X Y W H [--mode add|subtract|intersect|replace] [--feather 5]
vixl select ellipse X Y W H
vixl select color '#ffffff' --tolerance 15
vixl select alpha LAYER
vixl select all|none|invert
vixl mask create|from-selection|invert|enable|disable|delete LAYER
vixl mask import LAYER --path mask.png

# Effects: vixl EFFECT [LAYER] AMOUNT
vixl brightness portrait +20 ; vixl contrast -10 ; vixl saturation +15 ; vixl hue 30
vixl exposure 0.5 ; vixl gamma 1.1 ; vixl temperature 30 ; vixl tint 10 ; vixl white-balance photo --neutral '#a08070'
vixl shadows 15 ; vixl highlights -10 ; vixl blur 8 ; vixl sharpen 2 ; vixl denoise photo --luminance 40 --chroma 60
vixl grayscale ; vixl invert ; vixl posterize 6 ; vixl threshold 128
vixl auto-tone photo ; vixl auto-color photo ; vixl auto-contrast photo
vixl filter noise --amount 0.08 --seed 42
vixl filter vignette --radius 0.7 --strength 0.4
vixl filter levels --black 15 --white 240
vixl filter blur --radius 4 --target photo
vixl effect disable|enable|remove LAYER EFFECT        # EFFECT = 1-based index, fx_ ID or unique name
vixl effect move LAYER EFFECT --to top|bottom|N       # or --before EFFECT / --after EFFECT
vixl effect set LAYER EFFECT --amount 20
vixl preset save gritty portrait ; vixl preset show gritty ; vixl preset apply gritty other --set noise=0.03
vixl lookup photo look --amount 0.8                  # LUT (from a `lut` operation) added to the effect stack
vixl layer-style title drop-shadow|stroke|outer-glow|color-overlay|gradient-overlay --settings '{...}'
vixl layer-style title drop-shadow --remove
```

Curves have no dedicated CLI flags; use `apply` with `{"type":"curves","points":[[0,0],[128,160],[255,255]]}`.

## Design production

```bash
vixl repeat stripe --count 16 --dy 37 [--dx 0 --dw 0 --dh 1]
vixl repeat-blend stripe --count 16 --dy 37 --end '{"height":21,"fill":"#4853a4"}'
vixl pathfinder badge outer inner --mode union|subtract|intersect
vixl symbol logo Brandmark
vixl comp-save with-logo ; vixl comp-apply with-logo
vixl replace-contents photo --path new.jpg [--fit fit] | --asset assets/HASH.png | --variable photo_asset
vixl variable set title 'Night Shift' ; vixl variable delete title
```

## Measurement and QA (read-only)

```bash
vixl sample 100 150                                  # RGBA + hex at a point
vixl histogram --region X Y W H
vixl info --region X Y W H --foreground '#ffffff' [--background white]   # WCAG contrast vs a color
vixl info --target title                             # contrast of a rendered layer vs what's beneath
vixl spacing --targets heading body footer --axis vertical --tolerance 1 [--expected 24] [--check]
vixl spacing --around body --before heading --after footer
vixl check [--safe-area 5%] [--avoid X Y W H] [--thumbnail-width 320|off] [--checks overlap contrast] [--strict]
vixl validate [instagram-post|instagram-square|story|youtube-thumbnail] [--rules rules.json]
vixl assert canvas.width == 1920
vixl assert layer.logo.exists
vixl assert layer.logo.bounds within canvas
vixl assert text.title.font-size '>=' 48
vixl diff before.vixl after.png [--out diff.png] [--mode diff|side-by-side] [--threshold 8] [--max-fraction 0.01]
```

All accept `--artboard NAME` / `--comp NAME` where relevant. `--check` (spacing), `check --strict`
and failing `validate`/`assert` exit nonzero with details (`--json` shows every check). `diff` needs no open
document: it compares two `.vixl` documents or images (PNG, JPEG, WEBP, TIFF, SVG, PDF) and reports `changed_pixels`,
`changed_fraction` and `changed_region`; `--max-fraction` makes it exit nonzero above that share.

## Output

```bash
vixl export out.png|.jpg|.webp|.tiff|.avif [--quality 90] [--title T] [--max-bytes N] [--scale 2x] [--profile instagram|discord|print] \
     [--format PNG] [--background white] [--sampling nearest] [--set var=value] [--artboard NAME] [--comp NAME]
#   --quality: JPEG/WEBP/AVIF (default 90) and PDF images (omitted: lossless PDF images). --title: PDF title (default: the
#   title layer or role=title text, then the file name). --max-bytes: warns when a raster file is larger; a PNG over 1 MB warns and names texture looks.
vixl render [F.vixl] --out preview.png [--set title=Hello]      # same options; never persists overrides
vixl render --data rows.csv --out campaign_dir [--no-check]     # one PNG per CSV row: 0001.png …; rows with design problems carry a "check" report
vixl export-screens --out screens --scales 1 2 [--artboards square story]   # NAME@2x.png
vixl export-animation --out sprite.gif --format gif|apng|webp|mp4|webm|sheet [--scale 8] [--columns 3] [--colors 64] \
     [--sampling nearest|smooth] [--animation NAME] [--quality 90]
     # smooth: any scale (0.5, 1.5 …) re-rendered crisply; format follows the extension; --animation exports one
     # named animation (default: every saved frame); mp4/webm need ffmpeg
vixl export - --format PNG > preview.png                        # to stdout
cat photo.png | vixl convert --grayscale [--format PNG] > gray.png
vixl compare REF_A REF_B --out comparison.png                   # side-by-side history states
```

`export-screens` requires at least one artboard; `export-animation` requires saved frames.
`render --data`, `export-screens` and `export-animation` never overwrite existing outputs.
`export --scale` above 1 re-renders text, shapes and vectors at the larger size (images resample);
`--sampling nearest` enlarges pixels instead. `inspect` takes `LAYER` or `--target LAYER`.
Profiles *contain* (never crop/stretch): `instagram` 1080² JPEG, `discord` 512² PNG, `print` TIFF @300 DPI.
JPEG flattens transparency onto `--background` (white).

## Automation

```bash
vixl apply ops.json [--dry-run]          # or: cat ops.json | vixl apply -
vixl apply ops.json --check --preview p.png   # also check the result and write a 512 px preview
vixl apply ops.json --check --suites         # also run every attached check suite (or name them)
vixl run script.vixlscript               # one editing command per line, # comments; atomic
vixl compose --request req.json [--preview p.png] [--workspace DIR]   # vixl_compose: create → … → exports, atomic
vixl batch './photos/*.jpg' --run cleanup.vixlscript --output ./processed [--format png]
vixl each layer --type raster --name 'card-*' -- saturation -10
vixl transaction begin ; …edits… ; vixl transaction commit   # or rollback; one undo step
```

`.vixlscript` lines are editing commands without the `vixl` prefix (no new/open/export/AI/history
commands; no shell). Paths resolve relative to the script.

## History

```bash
vixl undo [N] ; vixl redo [N]
vixl history ; vixl branches
vixl checkpoint before-color             # fixed reference
vixl branch vivid                        # movable tip
vixl checkout before-color               # detaches; create a branch to continue
vixl compare vivid before-color --out cmp.png
```

## Pixel art and animation

```bash
vixl pixel-draw sprite pixel 5 5 --color g
vixl pixel-draw sprite line 6 5 --x2 9 --y2 5 --color w
vixl pixel-draw sprite rect 4 4 --width 8 --height 8 --color s
vixl pixel-draw sprite fill 0 0 --color .
vixl pixel-palette sprite --colors '{"g":"#ffdd66"}'
vixl frame-save idle [--duration 150] ; vixl frame-apply idle ; vixl frame-delete idle
vixl animation-set --order idle blink --loop 0       # default animation: lists every saved frame
vixl animation-set --name walk --order w1 w2 w3 w2 [--duration 100 | --durations 100 100 100 100] [--loop 0]
vixl animation-set --name walk --delete              # named animations are subsets; the frames stay
vixl frames-edit --operations '[{"type":"pixel-palette","target":"upper","colors":{"Y":"#d93a2b"}}]' \
     [--animation walk | --frames w1 w2] [--scene]   # same edit on every saved frame, atomically
vixl export-animation --out walk.gif --animation walk --scale 8
```

## AI (needs a configured provider — see ai.md)

```bash
vixl ask 'Make the logo 20% smaller and align it top-right' [--apply] [--provider NAME]
vixl generate --prompt 'foggy forest' --provider comfy --size 1024x1024 --as forest [--seed 42] [--mode inpaint|img2img] [--negative-prompt …] [--strength 0.75] [--model …]
vixl select object 'the person' --provider vision
vixl detect objects|faces --provider NAME ; vixl ocr --provider NAME ; vixl ai describe --provider NAME
vixl ai background-remove LAYER ; vixl ai upscale LAYER --2x|--scale 4
vixl ai extend --right 500 --prompt '…' --as extension ; vixl ai regenerate LAYER [--prompt …] [--seed …]
vixl ai info LAYER                      # provenance
vixl ai remove --as removed ; vixl ai content-aware-fill --prompt '…' ; vixl ai select-subject
```

## Services and updates

```bash
vixl -p F.vixl serve [--host 127.0.0.1] [--port 8765] [--token-env VIXL_API_TOKEN]
vixl mcp --workspace DIR [--tools core|ai|compact|all] [--schema slim|full] [--require-document]   # MCP over stdio; default core + slim; core + ai run as two servers; --require-document (or VIXL_REQUIRE_DOCUMENT=1) makes document= mandatory
vixl update --check | vixl update | vixl update --rollback ; vixl updates status|on|off   # Windows installer only
vixl upgrade old.vixl [--report] [--pin-fills]   # document saved before 0.21: list layers that render differently; --pin-fills restores white open-shape fills
```

## Sizes, layouts, color, print, brushes and motion (0.13)

```bash
vixl sizes --category print                         # also: social stationery icons logos ads email video slides …
vixl new letter --bleed -o flyer.vixl               # named size; --landscape, --dpi 150
vixl new --purpose slides --seed 7 -o deck.vixl     # purpose size; --variety, --background, --no-fonts
vixl canvas size instagram-story                    # resize to a named size; canvas dpi 300
vixl layout list ; vixl layout show editorial-grid
vixl -p flyer.vixl layout apply editorial-grid --set title='Annual report' --set body='…' --palette slate --seed 3
vixl -p flyer.vixl type-scale --base 18 --ratio golden
vixl color 'oklch(0.6 0.15 250)' ; vixl color harmony tomato --scheme triadic ; vixl color contrast white '#2563eb'
vixl -p flyer.vixl palette-generate brand '#2563eb'          # @brand-50 … @brand-950
vixl -p flyer.vixl export flyer.pdf --cmyk [--icc press.icc] [--ink-limit 300]
vixl -p flyer.vixl export proof.png --proof --simulate deuteranopia
vixl -p flyer.vixl check --checks print color_vision
vixl -p icon.vixl export favicon.ico --icon-sizes 16 32 48 ; vixl -p icon.vixl export-icons --out icons --set all
vixl brushes
vixl -p art.vixl paint --brush ink --points '[[40,300],[200,220,0.5],[380,310]]' --size 8 --color '#222'
vixl -p art.vixl paint --brush watercolor --path 'M50 500 C200 380 400 620 600 480' --size 60 --color tomato
vixl -p art.vixl paint-clear paint --last 1
vixl -p promo.vixl timeline set --duration 3s --fps 30
vixl -p promo.vixl animate-preset headline slide-in-up --duration 0.8s
vixl -p promo.vixl animate logo rotation --to 360 --duration 3s --easing linear
vixl -p promo.vixl animate arm-left,arm-right rotation --from -20 --to 20 --duration 0.5s   # shared timing
vixl -p promo.vixl keyframe badge opacity 1.5s 0.4 --easing ease-out
vixl -p promo.vixl timeline ; vixl -p promo.vixl timeline-sheet --out motion.png
vixl -p promo.vixl render --time 1.5s --out frame.png
vixl -p promo.vixl export-timeline --out promo.gif --scale 0.5      # .png .webp .zip .mp4 .webm, --format sheet
vixl -p promo.vixl export-timeline --out banner.gif --colors 64 --fps 12   # smaller GIF; --scale 2 renders crisp @2x
```

Times: ms, `1.5s`, `250ms`, `50%`, or a marker (`vixl marker reveal 1.2s`).
