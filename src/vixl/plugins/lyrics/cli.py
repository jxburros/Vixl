"""Workspace lyric timing and review commands."""

import json
from pathlib import Path

from ...commands import Parser
from ...errors import VixlError


def command(cmd, args, options, limits):
    if cmd != "lyrics":
        return None
    parser = Parser(prog="vixl lyrics")
    commands = parser.add_subparsers(dest="action", required=True)
    align = commands.add_parser("align", help="Align plain/LRC lyrics using a configured provider")
    align.add_argument("audio")
    align.add_argument("lyrics")
    align.add_argument("--provider")
    align.add_argument("--replace-lines", action="store_true")
    align.add_argument("--confidence", type=float, default=0.7)
    edit = commands.add_parser("timing-edit", help="Edit timing without another provider call")
    edit.add_argument("timing")
    edit.add_argument("--edits", required=True, help="JSON array: {line, word?, shift?, start?, end?}; milliseconds")
    export = commands.add_parser("timing-export", help="Export reviewed timings as enhanced LRC")
    export.add_argument("timing")
    preview = commands.add_parser("preview", help="Preview one built cue")
    preview.add_argument("build")
    preview.add_argument("--cue", type=int, required=True)
    preview.add_argument("--output", dest="output", required=True)
    review = commands.add_parser("review", help="Record human review of the current lyric build")
    review.add_argument("build")
    choices = review.add_mutually_exclusive_group(required=True)
    choices.add_argument("--approve", action="store_true")
    choices.add_argument("--changes-requested", action="store_true")
    review.add_argument("--findings", default="[]", help="JSON array of review findings")
    for item in (align, edit, export):
        item.add_argument("--output", "--out", "-o", dest="output", required=True)
        item.add_argument("--replace", action="store_true")
    for item in (align, edit, export, review, preview):
        item.add_argument("--workspace", default=".")
    request = vars(parser.parse_args(args))
    action, root = request.pop("action"), Path(request.pop("workspace")).resolve()
    try:
        for key in ("edits", "findings"):
            if key in request:
                request[key] = json.loads(request[key])
    except ValueError as exc:
        raise VixlError("usage_error", f"{key} must be valid JSON") from exc
    if action == "preview":
        from .compositions import preview as preview_cue
        return preview_cue(request, root, limits)
    if action == "review":
        from .verification import review as review_build
        return review_build(request, root, limits)
    from . import timing
    return {"align": timing.align, "timing-edit": timing.edit, "timing-export": timing.export}[action](request, root, limits)
