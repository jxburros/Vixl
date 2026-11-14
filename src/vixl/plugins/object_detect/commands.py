"""``vixl object detect``: the command-line shorthand of the object-detect workflow, through the ``cli-command``
hook. ``vixl object detect --kind KIND`` still declares a group that is itself named detect."""

from pathlib import Path


def command(cmd, args, options, limits):
    if cmd != "object" or args[:1] != ["detect"] or "--kind" in args:
        return None
    from ...cli import current_path
    from ...commands import Parser
    from ...interfaces import Session
    from ...workflows import dispatch
    from .detect import DEFAULT_CONFIDENCE, DEFAULT_TOLERANCE

    p = Parser(prog="vixl object detect", description="Propose which layers form which objects, and of what kind; "
               "changes nothing without --apply")
    p.add_argument("targets", nargs="*", help="Layers or groups to look at (default: the whole page)")
    p.add_argument("--apply", action="store_true", help="Apply the proposals at or above --min-confidence as one "
                   "undo step")
    p.add_argument("--min-confidence", type=float, default=DEFAULT_CONFIDENCE)
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                   help="Pixels of gap across which loose layers still touch")
    p.add_argument("--provider", nargs="?", const=True, help="Also offer a configured AI provider's detections on "
                   "raster images (the default provider when no name follows)")
    a = p.parse_args(args[1:])
    request = {"apply": a.apply, "min_confidence": a.min_confidence, "tolerance": a.tolerance,
               **({"targets": a.targets} if a.targets else {}),
               **({"provider": a.provider} if a.provider is not None else {})}
    session = Session(current_path(options.project), limits, workspace=Path.cwd())
    return dispatch(session, "object-detect", request)
