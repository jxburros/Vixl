"""CLI syntax for color, sizes, layouts, brushes and timelines.

``standalone`` answers discovery commands without a document; ``compile_feature`` turns
editing commands into canonical operations; ``project_feature`` handles document commands
that inspect or export instead of editing.
"""

import json

from .commands import Parser, pairs
from .errors import require

STANDALONE = ("color", "colors", "sizes", "layouts", "brushes", "easings", "organics")
EDITING = (
    "paint-layer",
    "paint",
    "paint-clear",
    "brush-define",
    "keyframe",
    "keyframe-remove",
    "animate",
    "animate-preset",
    "marker",
    "palette-generate",
    "type-scale",
)
DOCUMENT = ("timeline", "export-timeline", "timeline-sheet", "export-icons", "layout", "guides")


def _value(text):
    """Keyframe values: numbers, true/false, otherwise the text itself (colors, strings)."""
    if text in ("true", "false"):
        return text == "true"
    try:
        number = float(text)
        return int(number) if number.is_integer() and "." not in text else number
    except ValueError:
        return text


def _time(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return text


def standalone(cmd, args):
    if cmd in ("color", "colors"):
        return color_command(args)
    if cmd == "sizes":
        from . import sizes

        p = Parser(prog="vixl sizes")
        p.add_argument("action", nargs="?", default="list", choices=["list", "show"])
        p.add_argument("name", nargs="?")
        p.add_argument("--category", choices=sizes.CATEGORIES)
        p.add_argument("--search")
        p.add_argument("--dpi", type=float)
        p.add_argument("--landscape", dest="orientation", action="store_const", const="landscape")
        p.add_argument("--portrait", dest="orientation", action="store_const", const="portrait")
        p.add_argument("--bleed", action="store_true")
        a = p.parse_args(args)
        if a.action == "show":
            require(a.name, "Use sizes show NAME")
            return sizes.resolve(a.name, dpi=a.dpi, orientation=a.orientation, bleed=a.bleed)
        return sizes.catalog(a.category, a.search)
    if cmd == "layouts":
        from .layouts import catalog

        return catalog()
    if cmd == "brushes":
        from .brushes import catalog

        return catalog()
    if cmd == "organics":
        from .organic import catalog

        return catalog()
    from .timeline import EASINGS, PRESETS

    return {"easings": list(EASINGS), "presets": list(PRESETS)}


def color_command(args):
    from . import colors

    actions = ("info", "convert", "harmony", "scale", "mix", "contrast", "names")
    p = Parser(prog="vixl color", description="Inspect and transform colors. Actions: " + ", ".join(actions))
    p.add_argument("values", nargs="*")
    p.add_argument("--to", choices=["hex", "rgb", "hsl", "hsv", "hwb", "cmyk", "lab", "lch", "oklab", "oklch", "css"])
    p.add_argument("--scheme", choices=colors.HARMONIES, default="complementary")
    p.add_argument("--count", type=int)
    p.add_argument("--amount", type=float, default=0.5)
    p.add_argument("--space", default="oklab")
    p.add_argument("--ink-limit", type=float)
    p.add_argument("--black-generation", type=float, default=1.0)
    a = p.parse_args(args)
    values = list(a.values)
    action = values.pop(0) if values and values[0] in actions else "info"
    if action == "names":
        require(values, "Use color names QUERY")
        return {"query": values[0], "names": colors.search_names(values[0])}
    require(values, f"Use color {action} COLOR")
    if action == "info":
        limit = a.ink_limit / 100 if a.ink_limit else None
        items = [colors.describe(v, ink_limit=limit, black=a.black_generation) for v in values]
        return items[0] if len(items) == 1 else items
    if action == "convert":
        require(a.to, "Use color convert COLOR --to SPACE")
        result = []
        for value in values:
            info = colors.describe(value)
            result.append({"input": value, a.to: info["css"] if a.to == "css" else info[a.to]})
        return result[0] if len(result) == 1 else result
    if action == "harmony":
        return {"base": values[0], "scheme": a.scheme, "colors": colors.harmony(values[0], a.scheme, a.count)}
    if action == "scale":
        return {"base": values[0], "scale": colors.scale(values[0])}
    if action == "mix":
        require(len(values) == 2, "Use color mix A B [--amount 0.5] [--space oklab]")
        mixed = colors.mix(colors.parse(values[0]), colors.parse(values[1]), a.amount, a.space)
        return {"mix": colors.hex_of(mixed), "space": a.space, "amount": a.amount}
    require(len(values) == 2, "Use color contrast FOREGROUND BACKGROUND")
    ratio = colors.contrast_ratio(colors.parse(values[0])[:3], colors.parse(values[1])[:3])
    return {
        "foreground": values[0],
        "background": values[1],
        "ratio": round(ratio, 2),
        "aa_normal": ratio >= 4.5,
        "aa_large": ratio >= 3,
        "aaa_normal": ratio >= 7,
        "aaa_large": ratio >= 4.5,
    }


def compile_feature(cmd, args):
    if cmd in ("layout-apply", "timeline-set"):
        # Operation names work as commands too: layout-apply NAME ≡ layout apply NAME.
        cmd, args = cmd.split("-")[0], [cmd.split("-")[1], *args]
    if cmd not in EDITING and not (cmd == "timeline" and args and args[0] == "set") and not (cmd == "layout" and args and args[0] == "apply"):
        return None
    p = Parser(prog=f"vixl {cmd}")
    if cmd == "layout":
        p.add_argument("action", choices=["apply"])
        p.add_argument("name")
        p.add_argument("--seed", type=lambda v: v if v == "random" else int(v), help="Integer or 'random'")
        p.add_argument("--set", action="append", help="Fill a slot: title=…, label=…, image=ASSET (vixl layout show NAME lists the slots)")
        p.add_argument("--unfilled", choices=["blank", "omit"], help="Show unfilled slots as [Label] blanks (default) or leave them out")
        p.add_argument("--palette")
        p.add_argument("--colors", type=json.loads)
        p.add_argument("--mode", choices=["inherit", "light", "dark"])
        p.add_argument("--predictable", action="store_true", default=None)
        p.add_argument("--type-scale")
        p.add_argument("--base-size", type=float)
        p.add_argument("--density", choices=["airy", "balanced", "dense"])
        p.add_argument("--align", choices=["left", "center", "right"])
        p.add_argument("--accent", choices=["rule", "bar", "dot", "block", "outline", "none"])
        p.add_argument("--mark")
        p.add_argument("--font")
        p.add_argument("--display-font")
        p.add_argument("--transparent", action="store_true", default=None)
        p.add_argument("--prefix")
        p.add_argument("--replace", action="store_true", default=None)
        data = vars(p.parse_args(args))
        data.pop("action")
        content = pairs(data.pop("set"))
        if data.get("palette") and data["palette"].startswith("["):
            data["palette"] = json.loads(data["palette"])
        ratio = data.pop("type_scale")
        if ratio is not None:
            data["type_scale"] = float(ratio) if ratio.replace(".", "", 1).isdigit() else ratio
        return {"type": "layout-apply", **{k: v for k, v in data.items() if v is not None}, **content}
    if cmd == "timeline":
        p.add_argument("action", choices=["set"])
        p.add_argument("--duration", type=_time)
        p.add_argument("--fps", type=float)
        p.add_argument("--loop", type=int)
        p.add_argument("--clear", action="store_true", default=None)
        data = vars(p.parse_args(args))
        data.pop("action")
        if data.get("fps") is not None and float(data["fps"]).is_integer():
            data["fps"] = int(data["fps"])
        return {"type": "timeline-set", **{k: v for k, v in data.items() if v is not None}}
    if cmd == "paint-layer":
        p.add_argument("--name")
        for key in ("width", "height"):
            p.add_argument("--" + key, type=int)
        for key in ("x", "y"):
            p.add_argument("--" + key, type=float)
    elif cmd == "paint":
        p.add_argument("target", nargs="?")
        p.add_argument("--brush", default="round")
        source = p.add_mutually_exclusive_group(required=True)
        source.add_argument("--points", type=json.loads, help="JSON [[x, y], [x, y, pressure], …] in canvas pixels")
        source.add_argument("--path", help="SVG path such as 'M10 10 C40 0 60 80 90 40'")
        p.add_argument("--pressure", type=json.loads)
        p.add_argument("--size", type=float)
        p.add_argument("--color")
        p.add_argument("--opacity", type=float)
        p.add_argument("--erase", dest="mode", action="store_const", const="erase")
        p.add_argument("--seed", type=int)
        p.add_argument("--space", choices=["canvas", "layer"], help="canvas (default): document pixels; layer: local stroke surface pixels")
        p.add_argument("--settings", type=json.loads, help="Brush overrides as JSON, e.g. '{\"hardness\": 0.3}'")
        data = vars(p.parse_args(args))
        return {"type": "paint", **{k: v for k, v in data.items() if v is not None}}
    elif cmd == "paint-clear":
        p.add_argument("target", nargs="?")
        p.add_argument("--last", type=int)
    elif cmd == "brush-define":
        p.add_argument("name")
        p.add_argument("--base")
        p.add_argument("--description")
        p.add_argument("--settings", type=json.loads)
    elif cmd == "keyframe":
        p.add_argument("target", help="Layer, or several comma-separated layers (arm-left,arm-right) that share the same keys")
        p.add_argument("property")
        p.add_argument("time", type=_time)
        p.add_argument("value", type=_value)
        p.add_argument("--easing")
    elif cmd == "keyframe-remove":
        p.add_argument("target")
        p.add_argument("--property")
        p.add_argument("--time", type=_time)
    elif cmd == "animate":
        p.add_argument("target", help="Layer, or several comma-separated layers (arm-left,arm-right) that share the same keys")
        p.add_argument("property")
        p.add_argument("--from", dest="from_", type=_value)
        p.add_argument("--to", type=_value, required=True)
        for key in ("start", "end", "duration"):
            p.add_argument("--" + key, type=_time)
        p.add_argument("--easing")
        data = vars(p.parse_args(args))
        if data.get("from_") is not None:
            data["from"] = data.pop("from_")
        data.pop("from_", None)
        return _targets({"type": cmd, **{k: v for k, v in data.items() if v is not None}})
    elif cmd == "animate-preset":
        p.add_argument("target", help="Layer, or several comma-separated layers (arm-left,arm-right) that share the same keys")
        p.add_argument("preset")
        for key in ("start", "duration"):
            p.add_argument("--" + key, type=_time)
        p.add_argument("--easing")
        p.add_argument("--amount", type=float)
        p.add_argument("--distance", type=float)
        p.add_argument("--to")
        p.add_argument("--no-fade", dest="fade", action="store_false", default=None)
    elif cmd == "marker":
        p.add_argument("name")
        p.add_argument("time", nargs="?", type=_time)
        p.add_argument("--delete", action="store_true", default=None)
    elif cmd == "palette-generate":
        p.add_argument("name")
        p.add_argument("color")
        p.add_argument("--scheme")
        p.add_argument("--count", type=int)
    else:
        p.add_argument("--base", type=float)
        p.add_argument("--ratio")
        p.add_argument("--prefix")
        p.add_argument("--color")
        data = vars(p.parse_args(args))
        ratio = data.get("ratio")
        if ratio and ratio.replace(".", "", 1).isdigit():
            data["ratio"] = float(ratio)
        return {"type": cmd, **{k: v for k, v in data.items() if v is not None}}
    op = {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
    return _targets(op) if cmd in ("keyframe", "animate-preset") else op


def _targets(op):
    if "," in op.get("target", ""):
        op["targets"] = [name.strip() for name in op.pop("target").split(",") if name.strip()]
    return op


def project_feature(project, cmd, args):
    """Document commands that inspect or export (no edit). Returns (result, changed) or None."""
    if cmd == "timeline" and (not args or args[0] != "set"):
        from .timeline import inspect_timeline

        require(not args, "Use timeline to inspect, or timeline set --duration 3s --fps 30")
        return inspect_timeline(project), False
    if cmd == "layout" and args and args[0] == "preview":
        op = compile_feature("layout", ["apply", *args[1:]])
        return project.apply(op, dry_run=True, detail="compact"), False
    if cmd == "layout" and (not args or args[0] in ("list", "show")):
        from .layouts import LAYOUTS, catalog

        if len(args) == 2:
            require(args[1] in LAYOUTS, f"Unknown layout {args[1]!r}")
            from .layouts import describe

            item = describe(args[1])
            return {"name": args[1], **item, "last_applied": project.state.get("layout")}, False
        return catalog(), False
    if cmd == "export-timeline":
        from .timeline import export_timeline

        p = Parser(prog="vixl export-timeline")
        p.add_argument("--out", required=True)
        p.add_argument("--format", choices=["gif", "apng", "webp", "sheet", "frames", "mp4", "webm"])
        p.add_argument("--fps", type=float)
        p.add_argument("--scale", type=float, default=1.0)
        p.add_argument("--start", type=_time)
        p.add_argument("--end", type=_time)
        p.add_argument("--background")
        p.add_argument("--columns", type=int)
        p.add_argument("--quality", type=int, default=90)
        p.add_argument("--colors", type=int, default=256, help="GIF palette size 2–256 (fewer colors = smaller file)")
        p.add_argument("--overwrite", action="store_true")
        p.add_argument("--progress", action="store_true", help="Write frame progress to stderr")
        a = p.parse_args(args)
        fps = int(a.fps) if a.fps and a.fps.is_integer() else a.fps
        return export_timeline(
            project,
            a.out,
            format=a.format,
            fps=fps,
            scale=a.scale,
            start=a.start,
            end=a.end,
            background=a.background,
            columns=a.columns,
            quality=a.quality,
            colors=a.colors,
            overwrite=a.overwrite,
            progress=(lambda event: print(json.dumps({"progress": event}), file=__import__("sys").stderr, flush=True)) if a.progress else None,
        ), False
    if cmd == "timeline-sheet":
        from pathlib import Path

        from .timeline import contact_sheet

        p = Parser(prog="vixl timeline-sheet")
        p.add_argument("--out", required=True)
        p.add_argument("--count", type=int, default=8)
        p.add_argument("--columns", type=int)
        p.add_argument("--times", nargs="+", type=_time)
        a = p.parse_args(args)
        require(not Path(a.out).exists(), "Output already exists")
        sheet = contact_sheet(project, a.count, a.columns, times=a.times)
        sheet.save(a.out, format="PNG")
        return {"output": a.out, "size": list(sheet.size)}, False
    if cmd == "guides":
        from .guides import describe

        require(not args, "Use guides to list guides and grids")
        return describe(project), False
    if cmd == "export-icons":
        from .exports import export_icons

        p = Parser(prog="vixl export-icons")
        p.add_argument("--out", required=True)
        p.add_argument("--set", dest="icon_set", choices=["web", "apple", "android", "windows", "all"], default="web")
        p.add_argument("--sampling", choices=["smooth", "nearest"], default="smooth")
        a = p.parse_args(args)
        return export_icons(project, a.out, icon_set=a.icon_set, sampling=a.sampling), False
    return None

