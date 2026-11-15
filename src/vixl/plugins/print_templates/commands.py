"""``vixl guides-import`` and ``vixl guide-set-save``: the workflow actions from the command line (``cli-command``)."""

from pathlib import Path

from ...errors import require


def command(cmd, args, options, limits):
    if cmd not in ("guides-import", "guide-set-save"):
        return None
    from ...cli import current_path
    from ...commands import Parser
    from ...interfaces import Session
    from .workflow import FIELD_TYPES, dispatch

    types = FIELD_TYPES[cmd]
    if cmd == "guide-set-save":
        p = Parser(prog="vixl guide-set-save", description="Save the document's role guides as a reusable guide set")
        p.add_argument("name")
        p.add_argument("--guides", nargs="+", help=types["guides"]["description"])
        p.add_argument("--description")
    else:
        p = Parser(prog="vixl guides-import", description="Read a printer's template (PNG or PSD) into role guides")
        p.add_argument("source", help="The template image or PSD")
        p.add_argument("--color", action="append", default=[], metavar="HEX=ROLE",
                       help="A line colour and its role (safe, keep-out, fold, trim, bleed); repeat per colour. "
                            "Without --color, --layer or --ruler-guides the template's colours are listed")
        p.add_argument("--layer", action="append", default=[], metavar="NAME=ROLE",
                       help="PSD: a guide layer and its role; repeat per layer")
        p.add_argument("--ruler-guides", dest="ruler_guides", choices=types["ruler_guides"]["enum"])
        for flag in ("tolerance", "gap", "min-length", "max-thickness"):
            p.add_argument(f"--{flag}", dest=flag.replace("-", "_"), type=int)
        p.add_argument("--fit", choices=types["fit"]["enum"])
        p.add_argument("--name", help=types["name"]["description"])
        p.add_argument("--replace", action="store_true", default=None)
        p.add_argument("--save", help=types["save"]["description"])
        p.add_argument("--description")
        p.add_argument("--dry-run", dest="dry_run", action="store_true", default=None)
    request = {key: value for key, value in vars(p.parse_args(args)).items() if value not in (None, [])}
    for flag, field in (("color", "colors"), ("layer", "layers")):
        pairs = request.pop(flag, None)
        if pairs:
            require(all("=" in pair for pair in pairs), f"--{flag} takes {flag.upper()}=ROLE", field=field)
            request[field] = dict(pair.rsplit("=", 1) for pair in pairs)
    path = current_path(options.project)
    session = Session(path, limits, workspace=Path.cwd())
    return dispatch(session, cmd, request)
