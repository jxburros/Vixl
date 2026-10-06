"""CLI for the guide, looks and styles catalogs (``vixl guide``, ``vixl looks``, ``vixl styles``)."""

from .errors import require


def standalone(cmd, args):
    """Commands that need no document: ``guide [BRIEF…]``, ``looks``, ``styles [list [QUERY…] | show NAME]``."""
    if cmd == "guide":
        from .briefs import guide

        return guide(" ".join(args) if args else None)
    if cmd == "looks":
        from .looks import catalog

        return {"looks": catalog(), "apply": "{type: look, target: LAYER, look: NAME [, color, amount 0-1, remove]}; "
                                             "vixl look LAYER NAME [--color C] [--amount A] [--remove]"}
    from . import styles

    action = args[0] if args and args[0] in ("list", "show", "get", "apply", "check") else "list"
    rest = args[1:] if args and args[0] == action else args
    if action in ("show", "get"):
        require(len(rest) == 1, "Use styles show NAME")
        return styles.describe(rest[0])
    require(action == "list", "styles apply and check need a document: vixl -p FILE styles apply NAME")
    return styles.listing(" ".join(rest) or None)


def bound(project, args):
    """``styles apply NAME [--palette] [--no-guidance]`` and ``styles check [NAME…]`` on an open document."""
    from .commands import Parser
    from . import styles

    p = Parser(prog="vixl styles", description="Style catalog: list | show NAME | apply NAME | check [NAME…]")
    p.add_argument("action", choices=["apply", "check"])
    p.add_argument("names", nargs="*")
    p.add_argument("--palette", action="store_true", help="apply: also define and apply the style's first palette")
    p.add_argument("--no-guidance", action="store_true", help="apply: only tag the document")
    a = p.parse_args(args)
    if a.action == "apply":
        require(len(a.names) == 1, "Use styles apply NAME")
        return project.apply(styles.apply_operations(a.names[0], palette=a.palette, guidance=not a.no_guidance)), True
    return project.check(checks=["style"], style=a.names or None), False
