"""Command-line shorthands of the workspace QA actions, through the ``cli-command`` hook: ``vixl approve`` and
``vixl links impact``."""

from pathlib import Path


def command(cmd, args, options, limits):
    if cmd == "approve":
        return approve_cli(args, options, limits)
    if cmd == "links" and args[:1] == ["impact"]:
        from .link_impact import cli

        return cli(args[1:], options, limits)
    return None


def approve_cli(args, options, limits):
    from ...commands import Parser
    from ...interfaces import Session

    p = Parser(prog="vixl approve", description="Record how the document (or every member of a project group) looks "
               "now; the approval check then flags later changes for review")
    p.add_argument("--group", help="Approve every member of this project group (stored in .vixl-groups/)")
    p.add_argument("--clear", action="store_true", help="Remove the approval instead")
    p.add_argument("--author", help="Who approves (default: the VIXL_AUTHOR environment variable, else agent)")
    p.add_argument("--workspace", default=".", help="Workspace folder for --group (default: the current folder)")
    a = p.parse_args(args)
    request = {"clear": a.clear, **({"author": a.author} if a.author is not None else {})}
    if a.group:
        from .approval import run

        session = Session(None, limits, workspace=Path(a.workspace).resolve())
        return run(session, {**request, "group": a.group})
    from ...cli import current_path
    from ...project import Project
    from .approval import approve, clear, document_folder

    path = current_path(options.project)
    if a.clear:
        folder = document_folder(path)
        return {"document": path.name, "cleared": clear(folder), "folder": folder.name}
    project = Project.load(path, limits=limits, allow_linked=options.allow_linked)
    project._workspace = str(Path(a.workspace).resolve())
    return approve(project, who=a.author)
