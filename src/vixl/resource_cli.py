"""Project-independent resource discovery and explicit user-library imports."""

from pathlib import Path

from .assets import read_bounded
from .commands import Parser, pairs
from .errors import require
from . import resources

CATEGORIES = {"palette": "palettes", "template": "templates", "guidance": "guidance"}


def resource_options(cmd, args):
    p = Parser(prog=f"vixl {cmd}")
    p.add_argument(
        "action",
        choices=["list", "show", "add", "apply", "new", "import", "remove"],
        nargs="?",
        default="list",
    )
    p.add_argument("name", nargs="?")
    p.add_argument("source", nargs="?")
    p.add_argument("--style", default="overall")
    p.add_argument("--prefix")
    p.add_argument("--set", action="append")
    p.add_argument("--out", "-o")
    return p.parse_args(args)


def standalone(cmd, args, limits):
    a = resource_options(cmd, args)
    kind = CATEGORIES[cmd]
    if a.action == "list":
        return {"kind": kind, "names": sorted(resources.catalog(kind))}, False
    require(a.name, "Provide a resource name")
    if a.action == "show":
        return {"name": a.name, "value": resources.get(kind, a.name)}, False
    if a.action == "add":
        require(a.source, "Provide a resource file")
        import json

        data = read_bounded(a.source, 1024 * 1024).decode("utf-8")
        return resources.register(kind, a.name, data if kind == "guidance" else json.loads(data)), False
    if cmd == "template" and a.action == "new":
        require(a.out, "Use template new NAME -o FILE")
        require(not Path(a.out).exists(), "Project already exists")
        p = resources.create_template(a.name, pairs(a.set), limits=limits, workspace=Path.cwd())
        p.save(a.out)
        from .cli import remember

        remember(a.out)
        record = {k: v for k, v in p.state.get("template", {}).items() if k != "name"}
        return {"created": a.out, "template": a.name, "layers": len(p.state["layers"]), **record}, False
    return None, True


FONT_STANDALONE = ("show", "pairings", "pairing", "principles")


def _seed(value):
    return value if value == "random" else int(value)


def font_standalone(cmd, args, project=None):
    """Catalog, pairing and roll commands that need no document."""
    from . import typefaces

    if cmd == "fonts":
        p = Parser(prog="vixl fonts")
        p.add_argument("--category", help="sans-serif, serif, monospace, display, handwriting or a classification")
        p.add_argument("--role", help="display, heading, text, ui, caption, code or accent")
        p.add_argument("--mood")
        p.add_argument("--query")
        a = p.parse_args(args)
        return typefaces.list_fonts(a.category, a.role, a.mood, a.query)
    if cmd == "roll":
        from .sizes import resolve

        p = Parser(prog="vixl roll")
        p.add_argument("--for", dest="purpose", help="What it is for: poster, social, slides, logos …")
        p.add_argument("--mood")
        p.add_argument("--size", help="Named size or WxH, so the layout suits the canvas")
        p.add_argument("--seed", type=_seed, help="Integer or 'random' (default)")
        p.add_argument("--apply", action="store_true", help="Apply the direction and fonts to the current document")
        p.add_argument("--set", action="append", help="Fill a layout slot: title=…")
        p.add_argument("--lock", action="append", help="Keep a choice: layout=…, pairing=…, palette=…, mode=…")
        a = p.parse_args(args)
        canvas = None
        if a.size:
            if "x" in a.size and a.size.replace("x", "").isdigit():
                canvas = tuple(int(v) for v in a.size.split("x"))
            else:
                size = resolve(a.size)
                canvas = (size["width"], size["height"])
        locks = pairs(a.lock)
        if "layout_seed" in locks:
            locks["layout_seed"] = int(locks["layout_seed"])
        return typefaces.roll_document(project, seed=a.seed, purpose=a.purpose, mood=a.mood, canvas=canvas, locks=locks, apply=a.apply, slots=pairs(a.set))
    p = Parser(prog="vixl font")
    p.add_argument("action", choices=FONT_STANDALONE)
    p.add_argument("family", nargs="?")
    p.add_argument("--mood")
    p.add_argument("--for", dest="purpose")
    p.add_argument("--family", dest="with_family")
    p.add_argument("--relationship", choices=["contrast", "superfamily", "concord"])
    a = p.parse_args(args)
    if a.action == "show":
        require(a.family, "Use font show FAMILY")
        return typefaces.show_font(a.family)
    if a.action == "principles":
        return {"principles": typefaces.principles()}
    if a.action == "pairing":
        require(a.family, "Use font pairing NAME")
        return typefaces.get_pairing(a.family)
    return typefaces.list_pairings(a.mood, a.purpose, a.with_family, a.relationship)


def project_command(project, cmd, args):
    if cmd == "font":
        p = Parser(prog="vixl font")
        p.add_argument("action", choices=["list", "import", "install", "pair", "use"])
        p.add_argument("source", nargs="?", help="File/HTTPS URL (import), family (install), pairing or 'random' (pair), font name (use)")
        p.add_argument("--name")
        p.add_argument("--weight", type=int, default=400)
        p.add_argument("--italic", action="store_true")
        p.add_argument("--role", choices=["heading", "body"])
        p.add_argument("--seed", type=_seed)
        p.add_argument("--mood")
        p.add_argument("--for", dest="purpose")
        a = p.parse_args(args)
        if a.action == "list":
            return {"fonts": project.state.get("fonts", {}), "typography": project.state.get("typography", {})}, False
        from . import typefaces

        if a.action == "install":
            require(a.source, "Use font install FAMILY [--weight 700] [--italic] [--role heading|body]")
            return typefaces.install_font(project, a.source, a.weight, a.italic, a.name, a.role), True
        if a.action == "pair":
            return typefaces.pair_fonts(project, a.source, seed=a.seed, mood=a.mood, best_for=a.purpose), True
        if a.action == "use":
            require(a.source and a.role, "Use font use NAME --role heading|body")
            return project.apply({"type": "font-register", "name": a.source, "role": a.role}, detail="compact"), True
        require(a.source and a.name, "Use font import FILE_OR_HTTPS_URL --name NAME")
        from .fonts import import_font

        return import_font(project, a.source, a.name), True
    a = resource_options(cmd, args)
    require(a.name, "Provide a resource name")
    if a.action == "apply":
        if cmd == "guidance":
            op = {"type": "guidance", "name": a.name, "style": a.style}
        elif cmd == "palette":
            op = {"type": "palette-apply", "name": a.name}
            if a.prefix:
                op["prefix"] = a.prefix
        else:
            op = {"type": "template-apply", "name": a.name, "variables": pairs(a.set)}
    elif cmd == "guidance" and a.action == "import":
        require(a.source, "Provide a guidance text file")
        op = {
            "type": "guidance",
            "name": a.name,
            "text": read_bounded(a.source, 100000).decode("utf-8"),
            "style": a.style,
        }
    elif cmd == "guidance" and a.action == "remove":
        op = {"type": "guidance", "name": a.name, "style": a.style, "delete": True}
    else:
        require(False, "Unsupported resource action")
    return project.apply(op, detail="compact"), True
