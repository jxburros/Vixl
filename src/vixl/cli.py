"""Headless CLI and interactive shell. Project changes autosave after every successful command."""

from copy import deepcopy
import glob
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile

from .fileio import file_lock

from . import __version__
from .assets import read_bounded
from .commands import Parser, compile_command, compile_script, dimensions, normalize, pairs
from .errors import VixlError, for_surface, friendly, require
from .model import Limits

HELP = """Vixl — headless design engine for autonomous AI agents

Usage: vixl [--project FILE] [--json] COMMAND ...
       vixl                         Interactive editing shell

Documents: new SIZE|NAME [-o FILE] [--background COLOR] [--dpi N] [--landscape] [--bleed],
           open FILE, save [FILE]   (NAME: letter, a4, business-card, instagram-portrait, favicon …)
           upgrade FILE [--report] [--pin-fills]   (a document saved before 0.21: what renders differently)
Inspect:   status, inspect [LAYER], describe, layers, effects [LAYER], manifest,
           dependencies, reproduce --check, schema
Layers:    add FILE --name NAME, solid --color COLOR, gradient --start A --end B,
           text add TEXT --name NAME --size N, text NAME --text TEXT,
           remove, rename, duplicate, hide, show, raise, lower, top, bottom, reorder
Organic:   organics (presets, generators, rules), organic PRESET [--set petals=8] [--color petals=#fff] [--seed N],
           organic --parts JSON, organic --target NAME --seed N (regrow)
Imperfect: irregular TARGET --seed N [--strength subtle|natural|rough] (wobble, stroke weight, color drift, micro placement),
           tear TARGET --seed N [--edges bottom] (torn edge as a mask; --as path for layers), --remove undoes either
Charts:    chart bar|stacked-bar|percent-bar|horizontal-bar|line|area|pie|donut --name N (--csv FILE | --categories JSON --series JSON)
           [--title T] [--legend bottom] [--value-labels true] [--number-format '#,##0'], chart line --target N (restyle, resize, change kind),
           chart-data --target N --set DEC=3330 | --append 'JAN=1,2' | --remove-category C | --reload; exports to .pptx as a native chart
Design:    pen, shape, shape-place, container-place, container-swap, container-reflow, group, ungroup, clip, layer-style, distribute, style-define,
           style-apply, swatch, artboard, frame, replace-contents, repeat, repeat-blend,
           adjustment, lut, lookup, comp-save, comp-apply, text-layout, pathfinder, symbol, symbol-instance,
           stack GROUP [--direction vertical|horizontal] [--gap N] [--align A] [--justify J] [--hide-if-empty] (auto-layout)
Guides:    guide NAME x|y POS | guide NAME --kind line|ray|segment|point|circle|path …, guides,
           grid NAME [--kind columns|baseline|thirds|golden|armature|golden-spiral|polar|isometric|triangular|hex|oblique|perspective],
           place LAYER… --guide NAME [--at F | --start F --end F | --spacing PX | --with GUIDE] [--orient tangent],
           snap LAYER… [--tolerance 8], check --checks guides alignment, render --out F --show-guides
Pages:     page add NAME [--master M] [--after P] [--duplicate P] [--notes TEXT], page select|remove P, page move P --index N,
           page set P [--rename N] [--notes TEXT] [--hidden] [--transition fade], master add NAME [--from P], pages,
           render --page 2 | --page all (contact sheet), export deck.pdf|deck.pptx [--pages 1-3,5] [--pdf-content raster],
           export deck.html [--presenter-theme dark|light|auto] [--slide-images svg|png] [--start-slide N] [--no-notes],
           check --checks deck [--min-font 18] [--max-words 60]; any operation accepts "page": P
Diagrams:  diagram-from-text "A -> B -> C" --name NAME [--layout layered|tree|radial|mindmap|grid] [--direction TB|LR] [--routing orthogonal|curved|straight],
           diagram NAME --nodes JSON --edges JSON, diagram-set NAME [--text TEXT] [--nodes JSON] [--remove-nodes ID…] [--delete], check --checks diagram
Text flow: text-flow create NAME --text TEXT --x N --y N --width N --height N [--columns 2 --gutter 24] [--keep-together --orphans 2 --widows 2],
           text-flow add-frame|link|unlink|reflow|set|style|delete NAME …, check --checks flow
Forms:     field add KEY --kind text|multiline|number|date|checkbox|radio|dropdown|signature --label TEXT [--required] …,
           field set LAYER …, field list, form settings [--tab-order reading|explicit] [--title T] [--lang en-US],
           check --checks form [--sample worst|rows.csv], render --out F --show-fields [--set KEY=VALUE],
           export form.pdf --fillable, form fill --set KEY=VALUE --out filled.pdf | --data rows.csv (--out DIR | --combine all.pdf)
Drawings:  drawing import sketch.jpg --name house [--settings '{"ink": "original"}'], drawing clean|vectorize|straighten|smooth house,
           drawing fill house --points '[[x, y, "#fc0"]]', drawing stroke house --points '[[x, y], …]', drawing restyle house,
           drawing report house, drawing compare house --out c.png, check --checks drawing, ai drawing-color house --prompt TEXT
Linked:    link FILE.vixl [--name N] [--width W] [--fit fill|fit|stretch] [--position top-left] [--crop X,Y,W,H] [--artboard A] [--page P]
           [--set NAME=VALUE], link-set LAYER … (changes a link), link-refresh [LAYER], link-embed LAYER, links-relink FROM TO, links (each link: ok, stale or missing)
Merge:     merge [TEMPLATE.vixl] --data rows.csv --out sheets.pdf [--sheet-document sheets.vixl] [--size letter] [--cols 2 --rows 3]
           [--gutter 0.125] [--margin 0.5] [--bleed template|0.125] [--no-crop-marks] [--registration] [--slug TEXT] [--copies N]
           [--dry-run] [--skip-invalid] [--unknown warn|error|ignore] [--replace], merge --rerun sheets.vixl [--data new.csv]
Measure:   info, sample X Y, histogram [--region X Y W H], info --target TEXT,
           spacing --targets A B C --axis vertical [--expected N] [--tolerance N] [--check],
           spacing --around BODY --before HEADER --after FOOTER,
           check [--safe-area 5%] [--avoid X Y W H] [--thumbnail-width 320] [--strict]
           check --checks print color_vision [--ink-limit 300] [--min-ppi 200]
Pixels:    pixel-art, pixel-draw, pixel-palette, pixels [LAYER],
           frame-save NAME [--duration MS], frame-apply NAME, frame-delete NAME,
           animation, animation-set --loop N --order FRAME FRAME,
           animation-set --name walk --order FRAME FRAME [--duration MS | --durations MS MS] [--loop N] | --name walk --delete,
           frames-edit --operations JSON [--animation NAME | --frames FRAME FRAME] [--scene],
           export-animation --out FILE --format gif|apng|webp|mp4|webm|sheet [--animation NAME] [--scale N]
                            [--sampling nearest|smooth] [--colors N] [--quality N]
Editing:   move, resize, scale, rotate, pivot, flip, crop, opacity, blend, align,
           select-layer, select wand|lasso|path|rect|ellipse|color, mask, filter, effect, rasterize,
           merge-layers LAYER LAYER… [--name N], flatten [--keep-hidden] [--name N]
Effects:   brightness, contrast, saturation, hue, exposure, gamma, temperature,
           tint, white-balance, shadows, highlights, blur, sharpen, denoise, grayscale, invert,
           posterize, threshold, noise, grain, vignette, auto-tone, auto-color, auto-contrast;
           effect disable|enable|remove|set|move LAYER EFFECT, lookup LAYER LUT
Layout:    canvas resize SIZE, canvas size NAME [--landscape] [--bleed], canvas dpi N, constrain, unconstrain,
           variable set NAME VALUE
History:   undo [N], redo [N], history, checkpoint NAME, branch NAME,
           checkout REF, branches, compare REF REF --out FILE [--isolate LAYER…], diff A B [--out D.png] (two documents or images)
Automate:  apply FILE|- [--dry-run] [--check [CHECK…]] [--preview PNG [--isolate LAYER…]], run SCRIPT, batch GLOB --run SCRIPT --output DIR,
           workflow ACTION --request FILE [--workspace DIR] (workflow schema lists actions; proof, logo-package …),
           compose --request FILE [--preview P.png] (create → layout → look → operations → check → exports, atomic),
           each layer --name PATTERN -- COMMAND, preset save|apply|show NAME,
           transaction begin|commit|rollback, assert RULE, validate [PROFILE]
Resources: commands, shapes, sizes [--category print], palette list|show|add|apply,
           template list|show|add|new|apply, layout list|show|apply NAME [--seed N|random] [--set title=…],
           guidance list|show|add|apply|import|remove, providers, models
Type:      fonts [--category serif] [--mood M], font show FAMILY, font pairings [--mood M] [--for poster],
           font pairing NAME, font principles, font install FAMILY [--weight 700] [--role heading|body], font pair NAME|random,
           font use NAME --role heading|body, font list|import, --scope workspace (install/pair: brand.json default for new documents)
Finish:    look LAYER NAME [--color C] [--amount 0-1] [--remove]  (glow, neon, soft-shadow, hard-shadow, outline, gradient, grain,
           paper, film, duotone, risograph, sketch, watercolor, halftone, hand-made, plush), looks (catalog),
           radial-repeat LAYER --count N [--cx 50%] [--cy 50%] [--sweep 360] [--start-angle D] [--mirror] [--name N]
           [--rotation-step D] [--scale-step F] [--opacity-step F] [--rotation-jitter D] [--seed N] [--merge],
           scatter LAYER --source MOTIF… | --preset fur [--count N|--spacing PX] [--placement inside|along] [--merge],
           pattern-scatter --source MOTIF… --width W --height H [--count N] [--seed N] [--pattern NAME],
           guide [BRIEF|GUIDANCE] (what to make: icons, characters, scenes, patterns … with the operations, layouts and looks that
           suit it; or a guidance text such as natural-motion), capabilities [TOPIC] (fields, gotchas and guidance per topic)
Styles:    styles [list [QUERY] | show NAME | apply NAME [--palette] | check [NAME]], style-set NAME… [--options JSON],
           check --checks style [--style NAME…] (premade rules for swiss, brutalist, minimalist, art-deco …)
Dice:      roll [--apply] [--set title=…] [--for poster] [--mood M] [--size NAME] [--seed N|random] [--lock palette=sage]
           [--unfilled omit|blank]
Color:     color [info] COLOR…, color convert COLOR --to oklch|cmyk|…, color harmony COLOR --scheme triadic,
           color scale COLOR, color mix A B, color contrast FG BG, color names QUERY,
           palette-generate NAME COLOR [--scheme scale|triadic|…], type-scale --base 16 --ratio golden
Paint:     brushes, paint-layer [--name N], paint [LAYER] --brush ink --points JSON | --path SVG
           [--size N] [--color C] [--erase], paint-clear [LAYER] [--last N], brush-define NAME --base B
Motion:    timeline, timeline set --duration 3s --fps 30 [--loop N], keyframe LAYER PROP TIME VALUE,
           animate LAYER PROP --to V [--from V] [--start T] [--duration T] [--easing E],
           animate-preset LAYER PRESET [--start T] [--duration T], marker NAME TIME, easings,
           text-animate TEXT PRESET [--unit char|word|line] [--stagger T] [--direction D] [--mode in|out|in-out],
           export-timeline --out FILE.gif|.webp|.png|.zip|.mp4 [--fps N] [--scale N] [--colors N],
           timeline-sheet --out FILE [--count 8], render --time 1.5s --out FILE
Output:    export FILE [--quality N] [--title T] [--max-bytes N] [--scale 2x] [--profile NAME] [--dpi N]
           [--cmyk [--icc PROFILE.icc] [--ink-limit 300]] [--proof] [--simulate deuteranopia],
           export FILE.html | FILE.pdf | FILE.ico [--icon-sizes 16 32 48], export-icons --out DIR [--set web|apple|android|all],
           render [PROJECT] --out FILE [--set NAME=VALUE] [--artboard NAME] [--comp NAME],
           render --data rows.csv --out DIR, export-screens --out DIR --scales 1 2,
           convert --grayscale
AI:        ask PROMPT [--apply], generate --prompt TEXT --provider NAME,
           detect objects|faces, ocr, ai describe|info|regenerate|background-remove|upscale|extend,
           select object LABEL --provider NAME, ai remove|content-aware-fill|select-subject
Updates:   update [--check | --rollback], updates [on | off | status]
Services:  serve | view [--host 127.0.0.1] [--port 8765], notes list|add|resolve
           mcp [--workspace DIR] [--http] [--tools core|ai|compact|all] [--schema slim|full] [--planner] [--require-document]
Import:    import FILE.svg [--svg-mode editable|appearance|auto] | FILE.pdf [--page 1] [--dpi 144]
           import PHOTO.jpg | https://HOST/photo.jpg [--name N] [--credit TEXT] [--license TEXT]

Options: --project/-p FILE, --json, --allow-linked, --plugins, --max-pixels N, --detail brief|compact|full, --version
Use vixl commands --json for a complete inventory; vixl COMMAND --help works without a document. See docs/commands.md.
"""


def emit(value, machine=False):
    if value is None:
        return
    if machine or isinstance(value, (dict, list)):
        # ASCII JSON is also valid UTF-8 and survives redirected legacy Windows
        # streams. Never turn a successfully saved edit into an encoding error.
        print(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False))
    else:
        print(value)


def session_path():
    return Path.cwd() / ".vixl-session.json"


def remember(path):
    fd, temporary = tempfile.mkstemp(dir=Path.cwd())
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"project": str(Path(path).resolve())}, stream)
        os.replace(temporary, session_path())
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def current_path(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    try:
        return Path(json.loads(session_path().read_text())["project"])
    except (OSError, ValueError, KeyError):
        raise VixlError("no_project", "No current project. Use vixl new SIZE -o FILE or vixl open FILE.")


def has_document(explicit=None):
    """Whether a command has a document to read: ``-p`` or a session's existing current file."""
    try:
        return current_path(explicit).is_file()
    except VixlError:
        return False


def read_json(path):
    text = sys.stdin.read(1024 * 1024 + 1) if path == "-" else read_bounded(path, 1024 * 1024).decode()
    require(len(text) <= 1024 * 1024, "JSON input exceeds limit", "resource_limit")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise VixlError("invalid_json", str(exc)) from exc


def output_options(args, command):
    p = Parser(prog=f"vixl {command}")
    p.add_argument("path", nargs="?")
    p.add_argument("--out", "--preview", dest="out")
    p.add_argument("--overwrite", action="store_true", help="Replace existing export files")
    p.add_argument("--quality", type=int, default=None)
    p.add_argument("--title", help="PDF document title (default: the page's title layer, then the file name)")
    p.add_argument("--max-bytes", type=int, help="Size budget: warn when a raster export is larger")
    p.add_argument("--scale", default="1")
    p.add_argument("--profile")
    p.add_argument("--format", choices=["PNG", "JPEG", "WEBP", "TIFF", "AVIF", "SVG", "JPG", "PDF", "ICO", "HTML", "PPTX", "PSD"])
    p.add_argument("--background", default="white")
    p.add_argument("--set", action="append")
    p.add_argument("--artboard")
    p.add_argument("--comp")
    p.add_argument("--data")
    p.add_argument("--no-check", action="store_true", help="skip the per-row design check with --data")
    p.add_argument("--sampling", choices=["smooth", "nearest"], default="smooth")
    p.add_argument("--svg-policy", choices=["appearance", "strict"], default="appearance")
    p.add_argument("--color-space", "--colorspace", choices=["rgb", "cmyk"], default="rgb")
    p.add_argument("--cmyk", dest="color_space", action="store_const", const="cmyk")
    p.add_argument("--icc", "--icc-profile", dest="icc", help="CMYK ICC profile for separation or proofing")
    p.add_argument("--intent", choices=["perceptual", "relative", "saturation", "absolute"], default="relative")
    p.add_argument("--black-generation", type=float, default=1.0)
    p.add_argument("--ink-limit", type=float, help="Total area coverage limit in percent, e.g. 300")
    p.add_argument("--proof", action="store_true", help="Soft-proof the CMYK separation as RGB")
    p.add_argument("--simulate", choices=["protanopia", "deuteranopia", "tritanopia", "achromatopsia"])
    p.add_argument("--dpi", type=float)
    p.add_argument("--icon-sizes", type=int, nargs="+")
    p.add_argument("--time", help="Render a timeline frame: ms, 1.5s, 50%% or a marker")
    p.add_argument("--show-guides", action="store_true", help="Draw the document's guides over a raster render")
    p.add_argument("--page", help="Page name or number of a multi-page document; 'all' renders a contact sheet")
    p.add_argument("--pages", help="PDF/PowerPoint pages: numbers, ranges and names, e.g. 1-3,5,intro")
    p.add_argument("--pdf-content", choices=["vector", "raster"], help="PDF pages as vector text and shapes (default, also CMYK) or one image per page")
    p.add_argument("--presenter", action="store_true", default=None,
                   help="HTML: a self-contained slide presentation (the default for multi-page documents)")
    p.add_argument("--no-presenter", dest="presenter", action="store_false", help="HTML: one static image, not a presentation")
    p.add_argument("--presenter-theme", choices=["dark", "light", "auto"], help="Presentation surround and controls")
    p.add_argument("--slide-images", choices=["svg", "png"], help="Presentation slides as inline vectors (default) or PNGs")
    p.add_argument("--start-slide", help="Presentation: slide number or page name shown first")
    p.add_argument("--no-notes", action="store_true", help="Presentation: leave the speaker notes out of the file")
    p.add_argument("--columns", type=int, help="Contact sheet columns with --page all")
    p.add_argument("--fillable", action="store_true", help="PDF with fillable form fields")
    p.add_argument("--fill-mode", choices=["flatten", "editable"], default="flatten",
                   help="With field values in --set: draw them into the artwork, or prefill a fillable PDF")
    p.add_argument("--show-fields", action="store_true", help="Outline form fields with their keys and tab order")
    p.add_argument("--alpha", choices=["auto", "keep", "flatten"], default="auto",
                   help="PNG/WEBP/TIFF/AVIF: RGB when opaque (auto), always RGBA (keep), or RGB on --background (flatten)")
    return p.parse_args(args)


def presenter_options(a):
    """``--presenter``/``--no-presenter`` and the presenter flags as the export's ``presenter`` option."""
    options = {"theme": a.presenter_theme, "slide_images": a.slide_images,
               "start": int(a.start_slide) if a.start_slide and a.start_slide.isdigit() else a.start_slide,
               "notes": False if a.no_notes else None}
    options = {key: value for key, value in options.items() if value is not None}
    return a.presenter if options == {} or a.presenter is False else options


def print_options(a, limits):
    """Shared CMYK/proof/vision/dpi export arguments from parsed output options."""
    return {
        "color_space": a.color_space,
        "icc_profile": read_bounded(a.icc, limits.max_asset_bytes) if a.icc else None,
        "intent": a.intent,
        "black_generation": a.black_generation,
        "ink_limit": a.ink_limit,
        "proof": a.proof,
        "simulate": a.simulate,
        "dpi": a.dpi,
        "icon_sizes": a.icon_sizes,
        "time": (float(a.time) if a.time.replace(".", "", 1).isdigit() else a.time) if a.time else None,
    }


def dispatch(argv):
    global_parser = Parser(add_help=False, allow_abbrev=False)
    global_parser.add_argument("--project", "-p")
    global_parser.add_argument("--json", action="store_true")
    global_parser.add_argument("--allow-linked", action="store_true")
    global_parser.add_argument("--plugins", action="store_true")
    global_parser.add_argument("--max-pixels", type=int, default=40_000_000)
    global_parser.add_argument("--detail", choices=["brief", "compact", "full"], default="compact")
    global_parser.add_argument("--version", action="store_true")
    global_parser.add_argument("--runtime-info", action="store_true")
    options, tokens = global_parser.parse_known_args(argv)
    if options.runtime_info:
        return {"version": __version__, "python": sys.executable, "module": __file__,
                "managed_root": os.environ.get("VIXL_MANAGED_ROOT")}, options.json
    if options.version:
        return __version__, options.json
    if not tokens:
        shell(options)
        return None, options.json
    if tokens[0] in ("--help", "-h", "help"):
        return HELP, options.json
    from . import Project

    if options.plugins:
        from .plugins import enable_plugins

        enable_plugins()
    require(options.max_pixels > 0, "Pixel limit must be positive")
    limits = Limits(max_pixels=options.max_pixels)
    tokens = normalize(tokens) if tokens[0] != "text" else tokens
    cmd, args = tokens[0], tokens[1:]
    if cmd == "workflow":
        from .workflows import cli
        return cli(args, options, limits), options.json
    if cmd == "merge":
        from .imposition import cli as merge_cli
        return merge_cli(args, options, limits), options.json
    if cmd == "diff":
        from .image_diff import cli as diff_cli
        return diff_cli(args, limits), options.json
    if cmd == "compose":
        from .compose import cli as compose_cli
        return compose_cli(args, options, limits), options.json
    if cmd in ("open", "schema", "upgrade") and any(arg in ("--help", "-h") for arg in args):
        return command_help(cmd, args), options.json
    if cmd in ("commands", "shapes"):
        from .operations import OPERATION_TYPES
        from .design_schema import SHAPES
        from .render import EFFECTS

        return (
            {"shapes": list(SHAPES)}
            if cmd == "shapes"
            else {
                "commands": sorted(
                    (
                        set(OPERATION_TYPES)
                        - {
                            "palette-apply",
                            "template-apply",
                            "font-register",
                            "effect-set",
                            "effect-disable",
                            "effect-enable",
                            "effect-remove",
                            "effect-move",
                            "preset-save",
                            "preset-apply",
                        }
                    )
                    | set(EFFECTS)
                    | {"filter"}
                    | {"workflow"}
                    | set(
                        "new session open upgrade save status inspect describe layers effects manifest dependencies reproduce schema check batch convert render export export-screens export-animation spacing pixels animation info sample histogram apply run each undo redo checkpoint branch checkout branches history transaction compare assert validate preset ai ask generate detect ocr serve view notes import mcp update updates commands shapes palette template guidance font fonts roll providers models color sizes layout layouts brushes organics easings timeline export-timeline timeline-sheet export-icons pages guides links merge styles looks guide diff compose".split()
                    )
                )
            }
        ), options.json
    if "--help" not in args and "-h" not in args and (
        cmd in ("guide", "looks", "capabilities") or (cmd == "styles" and not (args and args[0] in ("apply", "check")))
    ):
        from .finishing_cli import standalone as finishing_standalone

        return finishing_standalone(cmd, args), options.json
    # A roll preview reads the document --apply would use (its canvas and brand), so both pick
    # the same direction; without a document it rolls standalone.
    standalone_roll = cmd == "roll" and "--apply" not in args and not has_document(options.project)
    if cmd == "fonts" or standalone_roll or (cmd == "font" and args and args[0] in ("show", "pairings", "pairing", "principles")):
        from .resource_cli import font_standalone

        return font_standalone(cmd, args), options.json
    if cmd in ("color", "colors", "sizes", "layouts", "brushes", "easings", "organics") or (
        cmd == "layout" and (not args or args[0] in ("list", "show"))
    ):
        from .feature_cli import standalone as feature_standalone

        if cmd == "layout":
            from .layouts import catalog

            items = catalog()
            if len(args) == 2:
                require(args[1] in items["layouts"], f"Unknown layout {args[1]!r}; see vixl layout list")
                from .layouts import describe

                return {"name": args[1], **describe(args[1]), "options": items["options"]}, options.json
            return items, options.json
        return feature_standalone(cmd, args), options.json
    from .resource_cli import workspace_scope

    if workspace_scope(cmd, args) and "--help" not in args and "-h" not in args:
        from .resource_cli import project_command as resource_command

        return resource_command(None, cmd, args)[0], options.json
    if cmd in ("palette", "template", "guidance"):
        from .resource_cli import standalone

        result, needs_project = standalone(cmd, args, limits)
        if not needs_project:
            return result, options.json
    if cmd in ("providers", "models"):
        from .models import discovery_command

        return discovery_command(cmd, args), options.json
    if cmd in ("update", "updates"):
        from . import updater

        p = Parser(prog=f"vixl {cmd}")
        if cmd == "update":
            flags = p.add_mutually_exclusive_group()
            flags.add_argument("--check", action="store_true")
            flags.add_argument("--rollback", action="store_true")
        else:
            p.add_argument("action", nargs="?", choices=["on", "off", "status"], default="status")
        a = p.parse_args(args)
        try:
            root = updater.root_path()
            if cmd == "updates":
                return (
                    updater.status(root)
                    if a.action == "status"
                    else updater.preference(root, a.action == "on")
                ), options.json
            return (
                updater.rollback(root) if a.rollback else updater.update(root, check_only=a.check)
            ), options.json
        except updater.UpdateError as exc:
            raise VixlError("update_error", str(exc)) from exc
    if cmd == "new":
        p = Parser(prog="vixl new", description="SIZE is WIDTHxHEIGHT or a named size (vixl sizes)")
        p.add_argument("size")
        p.add_argument("--overwrite", action="store_true", help="Replace an existing document explicitly")
        p.add_argument("--background", default="transparent")
        p.add_argument("--out", "-o", default=options.project or "untitled.vixl")
        p.add_argument("--dpi", type=float)
        orientation = p.add_mutually_exclusive_group()
        orientation.add_argument("--landscape", dest="orientation", action="store_const", const="landscape")
        orientation.add_argument("--portrait", dest="orientation", action="store_const", const="portrait")
        p.add_argument("--bleed", nargs="?", const=True, type=float, help="Add standard bleed, or an amount in the size's unit")
        p.add_argument("--no-workspace-fonts", dest="workspace_fonts", action="store_false",
                       help="Do not embed the workspace default fonts (brand.json pairing/fonts beside the document)")
        negative = next((arg for arg in args if re.fullmatch(r"-\d+(\.\d+)?[xX×]-?\d+(\.\d+)?", arg)), None)
        require(negative is None, f"Dimensions must be 1–16384 pixels; got {negative}", "resource_limit", field="size")
        a = p.parse_args(args)
        require(not Path(a.out).exists() or a.overwrite, "Project already exists; use --overwrite to replace it")
        require(not Path(a.out).is_dir(), "Output must be a file")
        named_size = not re.fullmatch(r"\d+[xX×]\d+", a.size.strip())
        require(named_size or not (a.orientation or a.bleed), "orientation and bleed need a named size")
        if named_size:
            project = Project.sized(
                a.size, a.background, limits=limits, dpi=a.dpi, orientation=a.orientation, bleed=a.bleed or False
            )
        else:
            project = Project(*dimensions(a.size), a.background, limits=limits)
            if a.dpi is not None:
                require(36 <= a.dpi <= 2400, "dpi must be 36–2400", field="dpi")
                project.state["canvas"]["dpi"] = a.dpi
                project.nodes, project.head, project._head_state, project.branches = {}, None, None, {}
                project._record([], "Create document")
        fonts = None
        if a.workspace_fonts:
            from .brand import apply_workspace_fonts

            fonts = apply_workspace_fonts(project, Path(a.out).resolve().parent)
        project.save(a.out, overwrite=a.overwrite)
        remember(a.out)
        return (
            project.inspect()
            if options.detail == "full"
            else {
                "path": str(project.path),
                "canvas": project.state["canvas"],
                "layers": len(project.state["layers"]),
                "head": project.head,
                **({"workspace_fonts": fonts} if fonts else {}),
            }
        ), options.json
    if cmd == "open":
        require(len(args) == 1, "Use open FILE")
        from .upgrade import report

        project = Project.load(args[0], limits=limits, allow_linked=options.allow_linked)
        remember(args[0])
        notice = report(project.state, project.upgraded_from) if project.upgraded_from else None
        return (
            project.inspect()
            if options.detail == "full"
            else {
                "path": str(project.path),
                "canvas": project.state["canvas"],
                "layers": len(project.state["layers"]),
                "head": project.head,
                **({"upgrade": notice} if notice else {}),
            }
        ), options.json
    if cmd == "upgrade":
        from .upgrade import upgrade

        p = Parser(prog="vixl upgrade")
        p.add_argument("file", nargs="?", help="Document (default: the current one)")
        p.add_argument("--report", action="store_true", help="Only list what renders differently; change nothing")
        p.add_argument("--pin-fills", action="store_true",
                       help="Give open stroked shapes the explicit white fill they rendered with before 0.21")
        a = p.parse_args(args)
        require(not (a.report and a.pin_fills), "--report changes nothing; leave out --pin-fills")
        path = current_path(a.file or options.project)
        with file_lock(str(path)):
            project = Project.load(path, limits=limits, allow_linked=options.allow_linked)
            result = upgrade(project, pin_fills=a.pin_fills, accept=not a.report)
            if not a.report and result["upgraded_from"]:
                project.save()
        return {"path": str(project.path), **result}, options.json
    if cmd == "schema":
        from .schema import operation_schema

        return operation_schema(), options.json
    if cmd == "batch":
        return batch(args, limits, options.allow_linked), options.json
    if cmd == "convert":
        p = Parser(prog="vixl convert")
        p.add_argument("--grayscale", action="store_true")
        p.add_argument("--format", default="PNG")
        a = p.parse_args(args)
        from .assets import add_image, decode

        project = Project(1, 1, limits=limits)
        image = decode(sys.stdin.buffer.read(limits.max_asset_bytes + 1), limits)
        asset = add_image(project, image)
        project.apply(
            [
                {"type": "canvas", "width": image.width, "height": image.height},
                {"type": "add", "asset": asset},
            ]
        )
        if a.grayscale:
            project.apply({"type": "grayscale"})
        sys.stdout.buffer.write(project.export(format=a.format))
        return None, options.json
    if cmd == "render" and args and args[0].endswith(".vixl"):
        options.project = args.pop(0)
    if cmd == "validate" and args and args[0].endswith(".vixl"):
        options.project = args.pop(0)
    if cmd == "mcp":
        from .interfaces import mcp_server

        p = Parser(prog="vixl mcp")
        p.add_argument("--workspace", help="Directory containing documents, imports and exports")
        p.add_argument(
            "--schema",
            choices=["full", "slim"],
            default=os.environ.get("VIXL_MCP_SCHEMA", "slim"),
            help="slim (default) advertises operation names only; fields come from vixl_operation_schema; "
            "full inlines every operation schema",
        )
        p.add_argument("--planner", action="store_true", help="Expose the provider-backed vixl_ai_plan tool")
        p.add_argument(
            "--tools",
            choices=["all", "core", "ai", "compact"],
            default=os.environ.get("VIXL_MCP_TOOLS", "core"),
            help="core (default): all editing tools; compact: 13 document/workflow tools; ai: provider-backed tools; "
            "all: core and ai from one server",
        )
        p.add_argument(
            "--require-document",
            action="store_true",
            default=None,
            help="Every document tool call must pass document= (no shared active document); "
            "also VIXL_REQUIRE_DOCUMENT=1",
        )
        p.add_argument("--http", action="store_true", help="Serve Streamable HTTP at /mcp")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8766)
        p.add_argument("--token-env", default="VIXL_API_TOKEN")
        a = p.parse_args(args)
        # Explicit workspaces can start empty. Existing --project configurations still work.
        path = current_path(options.project) if options.project or not a.workspace else None
        server = mcp_server(path, limits, workspace=a.workspace, schema=a.schema, planner=a.planner, tools=a.tools,
                            require_document=a.require_document)
        if a.http:
            from .interfaces import serve_mcp
            serve_mcp(server, a.host, a.port, os.environ.get(a.token_env))
        else:
            server.run()
        return None, options.json
    if "--help" in args or "-h" in args:
        return command_help(cmd, args), options.json
    path = current_path(options.project)
    if cmd in ("serve", "view"):
        from .interfaces import serve

        p = Parser(prog="vixl serve")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--token-env", default="VIXL_API_TOKEN")
        a = p.parse_args(args)
        serve(path, a.host, a.port, os.environ.get(a.token_env), limits, open_browser=cmd == "view")
        return None, options.json
    with file_lock(str(path)):
        project = Project.load(path, limits=limits, allow_linked=options.allow_linked)
        project._workspace = Path.cwd()
        if cmd == "session":
            require(not args, "Use session --project FILE; send NDJSON requests on stdin")
            from .session import run
            run(project, detail=options.detail)
            return None, options.json
        result, changed = project_command(project, cmd, args, detail=options.detail)
        if changed:
            project.save()
    return result, options.json


def command_help(cmd, args):
    from . import Project

    manual = {
        "open": "open FILE",
        "upgrade": "upgrade [FILE] [--report] [--pin-fills]",
        "schema": "schema",
        "canvas": "canvas resize SIZE | preset NAME | background COLOR",
        "save": "save [FILE]",
        "inspect": "inspect [LAYER]",
        "status": "status",
        "session": "session --project FILE (NDJSON operations or command argv requests on stdin)",
        "describe": "describe [image]",
        "layers": "layers",
        "effects": "effects [LAYER]",
        "manifest": "manifest",
        "dependencies": "dependencies",
        "reproduce": "reproduce --check",
        "pixels": "pixels [LAYER]",
        "animation": "animation",
        "undo": "undo [COUNT]",
        "redo": "redo [COUNT]",
        "checkpoint": "checkpoint NAME",
        "branch": "branch NAME",
        "checkout": "checkout REF",
        "branches": "branches",
        "history": "history",
        "compact": "compact [--dry-run] [--keep-fonts] (drop undo history and embedded files the design does not use)",
        "transaction": "transaction begin|commit|rollback",
        "assert": "assert RULE",
        "each": "each layer [--name PATTERN] [--type TYPE] -- COMMAND",
        "serve": "serve [--host HOST] [--port PORT] [--token-env ENV]",
        "preset": "preset save|apply|show NAME [--set KEY=VALUE]",
        "fonts": "fonts [--category serif] [--role heading] [--mood elegant] [--query TEXT]",
        "view": "view [--host HOST] [--port PORT] [--token-env ENV] (serve and open live review)",
        "roll": "roll [--apply] [--set title=TEXT] [--for poster] [--mood playful] [--size NAME|WxH] [--seed N|random] [--lock palette=sage] [--unfilled omit|blank]",
        "layout": "layout list | show NAME | preview NAME | apply NAME [--seed N|random] [--set title=TEXT] [--unfilled blank|omit] [--palette NAME] "
        "[--mode inherit|light|dark] [--predictable] [--type-scale golden] [--density airy|balanced|dense] [--align left|center|right] "
        "[--accent rule|bar|dot|block|outline|none] [--prefix P] [--replace]",
        "timeline": "timeline (inspect) | timeline set [--duration 3s] [--fps 30] [--loop N] [--clear]",
        "pages": "pages (list pages and masters of a multi-page document)",
        "styles": "styles [list [QUERY] | show NAME] | styles apply NAME [--palette] | styles check [NAME…]",
        "guide": "guide [BRIEF|GUIDANCE]  (e.g. guide a mascot for a coffee brand; guide operations; guide natural-motion)",
        "capabilities": "capabilities [TOPIC]  (e.g. capabilities animation: operations with fields, workflows, gotchas, guidance)",
        "looks": "looks  (the finishing looks; apply with look LAYER NAME)",
        "guides": "guides (list guides and grids)",
        "links": "links (list the linked documents and their state: ok, stale, missing, cycle)",
    }
    if cmd in manual:
        return "Usage: vixl " + manual[cmd]
    # Parsers handle --help before validation or execution, using a disposable document.
    return project_command(Project(1, 1), cmd, args)[0]


def project_command(project, cmd, args, *, detail="compact"):
    from .validation import assert_rule, dependencies, validate

    if cmd == "styles":
        from .finishing_cli import bound as styles_bound

        return styles_bound(project, args)
    if cmd == "roll":
        from .resource_cli import font_standalone
        return font_standalone(cmd, args, project), "--apply" in args
    if cmd == "import":
        from .imports import import_document
        p = Parser(prog="vixl import")
        p.add_argument("path", help="an .svg or .pdf document, an image file, or an https:// image URL")
        p.add_argument("--name")
        p.add_argument("--svg-mode", choices=["editable", "appearance", "auto"], default="editable")
        p.add_argument("--page", type=int, default=1)
        p.add_argument("--dpi", type=int, default=144)
        p.add_argument("--credit", help="attribution kept with an image, e.g. 'Photo: Ana Ruiz / Unsplash'")
        p.add_argument("--license", help="license or usage terms of an image, e.g. 'CC BY 4.0'")
        a = p.parse_args(args)
        is_url = re.match(r"(?i)[a-z][a-z0-9+.-]*://", a.path)
        if is_url or Path(a.path).suffix.lower() not in (".svg", ".pdf"):
            from .image_import import import_image_from

            return import_image_from(project, url=a.path if is_url else None, path=None if is_url else a.path,
                                     name=a.name or "image", credit=a.credit, license=a.license), True
        require(a.credit is None and a.license is None, "--credit and --license apply to image imports",
                field="credit")
        return import_document(project, read_bounded(a.path, project.limits.max_asset_bytes),
                               Path(a.path).suffix.lstrip("."), a.name or "import", a.page, a.dpi, a.svg_mode), True
    if cmd == "notes":
        from .review import notes
        p = Parser(prog="vixl notes")
        p.add_argument("action", choices=["list", "add", "resolve"], default="list", nargs="?")
        p.add_argument("value", nargs="?")
        a = p.parse_args(args)
        return notes(project.path, a.action, text=a.value, note_id=a.value), False
    if cmd in ("palette", "template", "guidance", "font"):
        from .resource_cli import project_command as resource_command

        return resource_command(project, cmd, args)
    from .feature_cli import project_feature

    feature = project_feature(project, cmd, args)
    if feature is not None:
        return feature
    if cmd in ("inspect", "status", "describe"):
        if cmd == "describe" and args == ["image"]:
            from .ai import ai_command

            return ai_command(project, "ai", ["describe"])
        if args[:1] == ["--target"] or (args and args[0].startswith("--target=")):
            args = args[1:] if args[0] == "--target" else [args[0].split("=", 1)[1]]  # MCP spelling
        require(len(args) <= 1, f"Usage: vixl {cmd} [LAYER] (or --target LAYER)")
        return project.inspect(args[0] if args else None), False
    if cmd == "layers":
        return project.inspect()["layers"], False
    if cmd == "effects":
        return deepcopy(project.layer(args[0] if args else None)["effects"]), False
    if cmd == "manifest":
        return {
            "version": __version__,
            "canvas": project.state["canvas"],
            "layers": len(project.state["layers"]),
            "history_entries": len(project.nodes),
            "dependencies": dependencies(project),
        }, False
    if cmd in ("dependencies", "reproduce"):
        result = dependencies(project)
        if cmd == "reproduce":
            project.render()
            result["reproducible"] = True
            result["note"] = "Current rendering verified; remote model replay is not guaranteed."
        return result, False
    if cmd == "save":
        require(len(args) <= 1, "Use save [FILE]")
        if args:
            require(
                not Path(args[0]).exists() or Path(args[0]).resolve() == project.path,
                "Destination already exists",
            )
            project.save(args[0])
            remember(args[0])
        else:
            project.save()
        return {"saved": str(project.path)}, False
    if cmd in ("render", "export"):
        a = output_options(args, cmd)
        destination = a.out or a.path
        require(destination, "Provide output filename or --out FILE")
        require(destination == "-" or a.data or a.overwrite or not Path(destination).exists(),
                "Export output already exists; use --overwrite to replace it", "output_exists")
        require(
            destination == "-" or Path(destination).resolve() != project.path,
            "Cannot export over the project",
        )
        if destination != "-" and Path(destination).suffix.lower() == ".wav" and not a.data:
            from .audio import export_audio

            return export_audio(project, destination, overwrite=a.overwrite), False
        if a.data:
            require(a.svg_policy == "appearance", "Strict SVG policy requires SVG output")
            from .exports import render_data

            require(destination != "-", "Data rendering requires an output directory")
            require(a.format in (None, "PNG"), "Data rendering exports PNG files")
            return render_data(
                project,
                a.data,
                destination,
                variables=pairs(a.set),
                artboard=a.artboard,
                comp=a.comp,
                sampling=a.sampling,
                scale=float(a.scale.rstrip("x")),
                profile=a.profile,
                check=not a.no_check,
            ), False
        page = int(a.page) if a.page and a.page.isdigit() else a.page
        from .forms import split_values

        values, variables = split_values(project, pairs(a.set))
        if values or a.show_fields:
            from .forms import with_values

            project = (with_values(project, values, complete=False) if values and not (a.fillable or a.fill_mode == "editable")
                       else project)
        if a.show_fields or a.show_guides:
            require(destination != "-", "--show-fields and --show-guides write a file")
            image = project.render(variables, artboard=a.artboard, comp=a.comp, page=page).convert("RGBA")
            if a.show_guides:
                from .guides import draw_overlay

                draw_overlay(image, project)
            if a.show_fields:
                from .forms import draw_overlay as draw_fields
                from .render import view_page

                draw_fields(image, view_page(project, page))
            fmt = (a.format or Path(destination).suffix.lstrip(".") or "PNG").upper()
            require(fmt in ("PNG", "JPG", "JPEG", "WEBP"), "Overlays render PNG, JPEG or WebP")
            image.convert("RGB" if fmt in ("JPG", "JPEG") else "RGBA").save(destination, format="JPEG" if fmt == "JPG" else fmt)
            result = {"output": destination}
            if a.show_guides:
                result["guides"] = len(project.state.get("guides", {}))
            if a.show_fields:
                from .forms import all_fields

                result["fields"] = len(all_fields(project))
            return result, False
        if page == "all":
            from .deck import contact_sheet

            require(destination != "-", "--page all writes a file")
            fmt = (a.format or Path(destination).suffix.lstrip(".") or "PNG").upper()
            require(fmt in ("PNG", "JPG", "JPEG", "WEBP"), "--page all renders a PNG, JPEG or WebP contact sheet")
            sheet = contact_sheet(project, width=round(480 * float(a.scale.rstrip("x"))), columns=a.columns)
            sheet.convert("RGB" if fmt in ("JPG", "JPEG") else "RGBA").save(destination, format="JPEG" if fmt == "JPG" else fmt)
            return {"output": destination, "pages": len(project.state["pages"]), "size": list(sheet.size)}, False
        from .pages import parse_pages

        fmt = (a.format or Path(destination).suffix.lstrip(".")).upper()
        if a.pages and fmt not in ("PDF", "PPTX") and not (fmt in ("HTML", "HTM") and a.presenter is not False):
            # Raster and SVG pages export as numbered files: carousel.png → carousel-01.png …
            from .pages import find_page, page_list

            require(destination != "-" and project.state.get("pages"), "--pages with an image format writes one "
                    "numbered file per page of a multi-page document", field="pages")
            records = (page_list(project, include_hidden=False) if a.pages == "all" else
                       [find_page(project.state, ref, "pages") for ref in parse_pages(a.pages)])
            target = Path(destination)
            outputs = []
            for number, record in enumerate(records, 1):
                path = target.with_name(f"{target.stem}-{number:02d}{target.suffix}")
                project.export(path, overwrite=a.overwrite, quality=a.quality, scale=float(a.scale.rstrip("x")), profile=a.profile,
                               variables=variables, format=a.format, background=a.background, sampling=a.sampling,
                               svg_policy=a.svg_policy, page=record["id"], **print_options(a, project.limits))
                outputs.append({"page": record["name"], "output": str(path)})
            return {"outputs": outputs}, False
        report = {}
        data = project.export(
            None if destination == "-" else destination,
            overwrite=a.overwrite,
            quality=a.quality,
            scale=float(a.scale.rstrip("x")),
            profile=a.profile,
            variables=variables,
            format=a.format,
            background=a.background,
            artboard=a.artboard,
            comp=a.comp,
            sampling=a.sampling,
            svg_policy=a.svg_policy,
            page=page,
            fillable=a.fillable,
            fill_mode=a.fill_mode,
            alpha=a.alpha,
            values=values if (a.fillable or a.fill_mode == "editable") else None,
            pages=None if a.pages == "all" else parse_pages(a.pages),
            pdf_content=a.pdf_content,
            presenter=presenter_options(a),
            title=a.title,
            max_bytes=a.max_bytes,
            report=report,
            **print_options(a, project.limits),
        )
        if destination == "-":
            sys.stdout.buffer.write(data)
            return None, False
        result = {"output": destination, "bytes": len(data), **report}
        if (a.format or Path(destination).suffix.lstrip(".")).upper() == "SVG":
            import xml.etree.ElementTree as ET

            root = ET.fromstring(data)
            metadata = root.find("{*}metadata")
            fallbacks = json.loads(metadata.text)["vixl"]["raster_fallbacks"] if metadata is not None else []
            result["svg"] = {"vector_only": not bool(root.findall(".//{*}image")), "raster_fallbacks": fallbacks}
        return result, False
    if cmd == "spacing":
        p = Parser(prog="vixl spacing")
        p.add_argument("--targets", nargs="+")
        p.add_argument("--axis", choices=["horizontal", "vertical"], default="vertical")
        for key in ("around", "before", "after", "artboard", "comp"):
            p.add_argument("--" + key)
        p.add_argument("--expected", type=float)
        p.add_argument("--tolerance", type=float, default=1)
        p.add_argument("--check", action="store_true")
        options = vars(p.parse_args(args))
        check = options.pop("check")
        result = project.measure_spacing(**options)
        if check and not result["passed"]:
            raise VixlError("spacing_mismatch", "Requested spacing is inconsistent", measurement=result)
        return result, False
    if cmd == "check":
        p = Parser(prog="vixl check")
        p.add_argument(
            "--checks",
            nargs="+",
            choices=check_names(),
        )
        p.add_argument("--connect-tolerance", type=float, default=2,
                       help="connected check: pixels of gap still counted as touching (default 2)")
        p.add_argument("--style", nargs="+", help="style checks: evaluate this style (or styles) instead of the document's tag")
        p.add_argument("--page", help="Check one page of a multi-page document (default: the active page)")
        p.add_argument("--pages", help="deck checks: the pages to check, e.g. 1-3,5 (default: every shown page)")
        p.add_argument("--min-font", type=float, help="deck checks: smallest projected text in points (default 18)")
        p.add_argument("--max-words", type=int, help="deck checks: most words on one page (default 60)")
        p.add_argument("--include-hidden", action="store_true", help="deck checks: include hidden pages")
        p.add_argument("--sample", help="form checks: fill the fields with worst-case values (worst) or each row of a CSV")
        p.add_argument("--ink-limit", type=float, default=300)
        p.add_argument("--min-ppi", type=float, default=200)
        p.add_argument("--targets", nargs="+")
        p.add_argument("--safe-area", help="Inset from every edge: pixels or a percentage such as 5%%")
        p.add_argument(
            "--avoid", nargs=4, action="append", metavar=("X", "Y", "W", "H"), help="Reserved zone"
        )
        p.add_argument("--thumbnail-width", default="auto", type=lambda v: v if v == "auto" else None if v in ("off", "none", "null") else int(v),
                       help="judge text at this thumbnail width (default 320; 'off' disables; print sizes judge printed points instead)")
        p.add_argument("--min-thumbnail-text", type=float, default=10)
        p.add_argument("--min-contrast", type=float)
        for key in ("artboard", "comp"):
            p.add_argument("--" + key)
        p.add_argument("--strict", action="store_true", help="Exit with an error when any check fails")
        options = vars(p.parse_args(args))
        strict = options.pop("strict")
        from .pages import parse_pages

        deck = {"pages": parse_pages(options.pop("pages")), "min_font": options.pop("min_font"),
                "max_words": options.pop("max_words"), "include_hidden": options.pop("include_hidden") or None}
        options["deck"] = {k: v for k, v in deck.items() if v is not None} or None
        if options["page"] and options["page"].isdigit():
            options["page"] = int(options["page"])

        def number(value):
            return value if value.endswith("%") else float(value)

        if options["safe_area"] is not None:
            options["safe_area"] = number(options["safe_area"])
        options["avoid"] = [[number(v) for v in zone] for zone in options["avoid"] or []]
        result = project.check(**options)
        if strict and not result["passed"]:
            raise VixlError("design_check_failed", f"{result['errors']} design error(s)", report=result)
        return result, False
    if cmd == "pixels":
        require(len(args) <= 1, "Use pixels [LAYER]")
        return project.inspect_pixels(args[0] if args else None), False
    if cmd == "animation":
        require(not args, "Use animation to inspect frames")
        return project.inspect_animation(), False
    if cmd == "export-animation":
        p = Parser(prog="vixl export-animation")
        p.add_argument("--out", required=True)
        p.add_argument("--overwrite", action="store_true")
        p.add_argument("--format", choices=["gif", "apng", "webp", "mp4", "webm", "sheet"])
        p.add_argument("--animation", help="Export this named animation instead of every saved frame")
        p.add_argument("--scale", type=float, default=1.0, help="Integer 1–32 with nearest sampling; 0.05–32 with smooth")
        p.add_argument("--sampling", choices=["nearest", "smooth"], default="nearest")
        p.add_argument("--colors", type=int, default=256, help="GIF palette size 2–256")
        p.add_argument("--dither", choices=["auto", "none", "ordered", "floyd"], default="auto", help="GIF dithering (shared palette)")
        p.add_argument("--max-bytes", type=int, help="Soft size target: warn when the file is larger")
        p.add_argument("--quality", type=int, default=90, help="WebP (smooth) and MP4/WebM quality 1–100")
        p.add_argument("--columns", type=int)
        a = p.parse_args(args)
        scale = int(a.scale) if a.scale.is_integer() else a.scale
        return project.export_animation(a.out, format=a.format, scale=scale, columns=a.columns, sampling=a.sampling, colors=a.colors, animation=a.animation, quality=a.quality, overwrite=a.overwrite, dither=a.dither, max_bytes=a.max_bytes), False
    if cmd == "export-screens":
        from .exports import export_screens

        p = Parser(prog="vixl export-screens")
        p.add_argument("--out", required=True)
        p.add_argument("--scales", nargs="+", default=["1", "2"])
        p.add_argument("--artboards", nargs="+")
        p.add_argument("--comp")
        p.add_argument("--set", action="append")
        a = p.parse_args(args)
        return export_screens(
            project,
            a.out,
            scales=[float(s.rstrip("x")) for s in a.scales],
            boards=a.artboards,
            comp=a.comp,
            variables=pairs(a.set),
        ), False
    if cmd in ("info", "sample", "histogram"):
        from .measure import measure

        p = Parser(prog=f"vixl {cmd}")
        if cmd == "sample":
            p.add_argument("point", nargs=2, type=int)
        p.add_argument("--region", nargs=4, type=int)
        p.add_argument("--foreground")
        p.add_argument("--target")
        p.add_argument("--artboard")
        p.add_argument("--comp")
        p.add_argument("--background", default="white")
        return measure(project, **vars(p.parse_args(args))), False
    if cmd in ("apply", "run"):
        p = Parser(prog=f"vixl {cmd}")
        p.add_argument("file")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--check", nargs="*", metavar="CHECK",
                       help="also check the result (default checks, or these): fix findings and those on touched layers")
        p.add_argument("--preview", metavar="PNG", help="also write a small preview of the result to this PNG file")
        p.add_argument("--preview-width", type=int, default=512)
        p.add_argument("--isolate", nargs="+", metavar="LAYER", help="preview only these layers, zoomed to their ink")
        p.add_argument("--suites", nargs="*", metavar="SUITE",
                       help="also run the attached check suites (all, or these) and report rules that did not pass")
        a = p.parse_args(args)
        ops = read_json(a.file) if cmd == "apply" else compile_script(a.file)
        from .checks import apply_reviewed

        check = None if a.check is None else (a.check or True)
        preview = {"max_width": a.preview_width, **({"isolate": a.isolate} if a.isolate else {})}
        suites = None if a.suites is None else (a.suites or True)
        result, image = apply_reviewed(project, ops, dry_run=a.dry_run, detail=detail, check=check,
                                       preview=preview if a.preview else None, suites=suites)
        if image is not None:
            Path(a.preview).write_bytes(image)
            result["preview"] = a.preview
        return result, not a.dry_run
    if cmd == "each":
        import fnmatch

        require("--" in args, "Use each layer [--name PATTERN] [--type TYPE] -- COMMAND")
        split = args.index("--")
        p = Parser(prog="vixl each")
        p.add_argument("kind", choices=["layer"])
        p.add_argument("--name", default="*")
        p.add_argument("--type")
        a = p.parse_args(args[:split])
        base = compile_command(args[split + 1 :])
        ops = [
            {**deepcopy(base), "target": layer["id"]}
            for layer in project.state["layers"]
            if fnmatch.fnmatchcase(layer["name"], a.name)
            and (not a.type or layer["type"] == {"image": "raster"}.get(a.type, a.type))
        ]
        return project.apply(ops, detail=detail) if ops else {"operations": 0}, bool(ops)
    if cmd in ("undo", "redo"):
        require(len(args) <= 1, "Expected optional count")
        require(not args or args[0].isdigit(), f"{cmd} takes a whole number of steps; got {args[0] if args else ''!r}",
                field="count")
        requested = int(args[0]) if args else 1
        done = getattr(project, cmd)(requested)
        result = project.inspect()
        if done < requested:
            result["notes"] = [*result.get("notes", []), f"{cmd} {requested}: only {done} step(s) were available"]
        return {cmd: done, **result}, True
    if cmd in ("checkpoint", "branch", "checkout"):
        require(len(args) == 1, "Expected a history name")
        getattr(project, cmd)(args[0])
        return {"head": project.head, "branch": project.current_branch}, True
    if cmd == "branches":
        return {
            "branches": project.branches,
            "checkpoints": project.checkpoints,
            "current": project.current_branch,
        }, False
    if cmd == "compact":
        p = Parser(prog="vixl compact", description="Drop all undo history, branches and checkpoints, and the embedded "
                   "files the current design does not use. The design itself does not change.")
        p.add_argument("--dry-run", action="store_true", help="Report what would be dropped")
        p.add_argument("--keep-fonts", action="store_true", help="Keep registered fonts no text, role or fallback uses")
        a = p.parse_args(args)
        return project.compact(fonts=not a.keep_fonts, dry_run=a.dry_run), not a.dry_run
    if cmd == "history":
        return [
            {k: v for k, v in node.items() if k not in ("state", "delta")} for node in project.nodes.values()
        ], False
    if cmd == "transaction":
        require(
            len(args) == 1 and args[0] in ("begin", "commit", "rollback"),
            "Use transaction begin|commit|rollback",
        )
        getattr(project, args[0])()
        return {"transaction": args[0], "success": True}, True
    if cmd == "compare":
        from PIL import Image

        p = Parser(prog="vixl compare")
        p.add_argument("left")
        p.add_argument("right")
        p.add_argument("--out", required=True)
        p.add_argument("--isolate", nargs="+", metavar="LAYER", help="compare only these layers, cropped to their ink")
        a = p.parse_args(args)
        left, right = project.clone(), project.clone()
        left.checkout(a.left)
        right.checkout(a.right)
        if a.isolate:
            from .proxy import isolated_pair

            *views, (x, y, w, h) = isolated_pair(left, right, a.isolate)
            li, ri = (view.render().crop((x, y, x + w, y + h)) for view in views)
        else:
            li, ri = left.render(), right.render()
        project.limits.size(li.width + ri.width, max(li.height, ri.height))
        canvas = Image.new("RGBA", (li.width + ri.width, max(li.height, ri.height)))
        canvas.paste(li, (0, 0))
        canvas.paste(ri, (li.width, 0))
        require(Path(a.out).resolve() != project.path, "Cannot overwrite project")
        canvas.save(a.out)
        return {"output": a.out, "left": left.inspect(), "right": right.inspect()}, False
    if cmd == "assert":
        rule = " ".join(args)
        require(assert_rule(project, rule), f"Assertion failed: {rule}", "assertion_failed")
        return {"passed": True, "rule": rule}, False
    if cmd == "validate":
        p = Parser(prog="vixl validate")
        p.add_argument("profile", nargs="?")
        p.add_argument(
            "--rules",
            action="append",
            help="A JSON file holding a list of rules, or one rule such as 'text.title.font-size >= 120' (repeatable)",
        )
        a = p.parse_args(args)
        rules = None
        for value in a.rules or []:
            # A value naming a .json file (or an existing file) is a rules file; anything else is one rule.
            inline = not value.endswith(".json") and not Path(value).is_file()
            loaded = [value] if inline else read_json(value)
            require(isinstance(loaded, list), "A rules file must hold a JSON list of rules")
            rules = (rules or []) + loaded
        result = validate(project, a.profile, rules)
        if not result["valid"]:
            raise VixlError("validation_failed", "Project validation failed", **result)
        return result, False
    if cmd == "preset" and args and args[0] == "show":
        require(len(args) == 2 and args[1] in project.state["presets"], "Preset not found")
        return project.state["presets"][args[1]], False
    if cmd in ("ai", "ask", "generate", "detect", "ocr", "OCR") or (
        cmd == "select" and args and args[0] == "object"
    ):
        from .ai import ai_command

        return ai_command(project, cmd, args, detail=detail)
    return project.apply(compile_command([cmd, *args]), detail=detail), True


def batch(args, limits, allow_linked):
    from . import Project

    p = Parser(prog="vixl batch")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--run", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--format", choices=["png", "jpg", "webp", "tiff"], default="png")
    a = p.parse_args(args)
    paths = sorted({str(Path(f).resolve()) for pattern in a.inputs for f in glob.glob(pattern)})
    require(paths, "No batch inputs matched")
    require(len(paths) <= 10000, "Too many batch inputs")
    out = Path(a.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    destinations = [out / (Path(f).stem + "." + a.format) for f in paths]
    require(len(set(destinations)) == len(paths), "Input names collide in output folder")
    require(not any(d.exists() for d in destinations), "Batch output already exists; choose an empty folder")
    ops = compile_script(a.run)
    results = []
    for path, dest in zip(paths, destinations):
        try:
            from .assets import decode

            image = decode(read_bounded(path, limits.max_asset_bytes), limits)
            project = Project(*image.size, limits=limits)
            project.allow_linked = allow_linked
            project.apply({"type": "add", "path": path})
            project.apply(ops)
            project.export(dest)
            results.append({"input": path, "output": str(dest), "success": True})
        except (VixlError, OSError) as exc:
            results.append({"input": path, "success": False, "error": str(exc)})
    if not all(r["success"] for r in results):
        raise VixlError("batch_failed", "Some batch items failed", results=results)
    return results


def shell(options):
    try:
        import readline  # noqa: F401
    except ImportError:
        pass
    print(f"Vixl {__version__} · type help, exit, or a command")
    while True:
        try:
            line = input("vixl > ").strip()
            if line in ("exit", "quit"):
                break
            if not line:
                continue
            if line == "help":
                print(HELP)
                continue
            prefix = ["--project", options.project] if options.project else []
            if options.allow_linked:
                prefix.append("--allow-linked")
            result, machine = dispatch([*prefix, *shlex.split(line)])
            emit(result, machine)
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
        except (VixlError, OSError, ValueError) as exc:
            print(f"ERROR: {for_surface(str(friendly(exc)), 'cli')}", file=sys.stderr)


def check_names():
    """Every check the engine runs, from its own registries, so the CLI never falls behind them."""
    from .checks import CHECKS, OPTIONAL_CHECKS
    from .deck import DECK_CHECKS

    return list(dict.fromkeys([*CHECKS, *OPTIONAL_CHECKS, "deck", *DECK_CHECKS]))


def main(argv=None):
    # Frozen Python ignores PYTHONIOENCODING. Configure text output explicitly;
    # this does not change binary PNG/SVG/MCP writes through .buffer.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        result, machine = dispatch(argv)
        emit(result, machine)
        if "workflow" in argv and isinstance(result, dict):
            if result.get("passed") is False or result.get("success") is False or result.get("status") in ("failed", "needs_review", "cancelled"):
                return 1
        return 0
    except BrokenPipeError:
        # The reader (head, less) closed the pipe: stop quietly, as other command-line tools do.
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
    except (VixlError, OSError, ValueError, TimeoutError, MemoryError) as exc:
        payload = for_surface(friendly(exc).as_dict(), "cli")
        print(json.dumps(payload) if "--json" in argv else f"ERROR: {payload['message']}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
