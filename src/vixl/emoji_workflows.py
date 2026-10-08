"""Emoji workflows shared by CLI, MCP and REST, with workspace-bounded paths."""

import base64
from pathlib import Path

from . import emojis
from .errors import require, VixlError


def S(description):
    return {"type": "string", "description": description}


def B(description):
    return {"type": "boolean", "description": description}


FIELDS = {
    "emoji": S("Unicode emoji, hex sequence or :custom_name:."),
    "query": S("Search names, Unicode sequences and tags."),
    "group": S("Group name from emoji-list, including VIXL Faces, VIXL Reactions and VIXL Everyday."),
    "offset": {"type": "integer", "minimum": 0, "description": "Zero-based result offset."},
    "limit": {
        "type": "integer",
        "minimum": 1,
        "maximum": 500,
        "description": "Results per page; default 100.",
    },
    "output": S("Workspace-relative output file (.vixl, .svg, .png or .zip, depending on action)."),
    "source": S("Workspace-relative input file (.vixl, .svg, .png or pack .zip)."),
    "format": {
        "type": "string",
        "enum": ["vixl", "svg", "png"],
        "description": "Emoji source export format; default vixl.",
    },
    "mode": {
        "type": "string",
        "enum": ["vixl", "font"],
        "description": "Prefer VIXL art or the font; custom overrides always win.",
    },
    "destination": {
        "type": "string",
        "enum": list(emojis.DESTINATIONS),
        "description": "Export destination: images, discord or slack.",
    },
    "emojis": {
        "type": "array",
        "items": S("Unicode emoji, hex sequence or registered shortcode."),
        "minItems": 1,
        "maxItems": 5000,
        "uniqueItems": True,
        "description": "Subset to export or check; omitted means the whole set.",
    },
    "sources": B("Include available editable VIXL masters; default true."),
    "size": {
        "type": "integer",
        "minimum": 16,
        "maximum": 1024,
        "description": "Image-pack PNG size; platform profiles fix it at 128.",
    },
    "overwrite": B("Explicitly replace an existing output; default false."),
    "kind": {
        "type": "string",
        "enum": ["blank", "face", "symbol", "sheet"],
        "description": "Editable starting point; default blank.",
    },
    "name": S("Optional custom emoji name for destination exports."),
    "license": S("Artwork license; defaults to unspecified for original user art."),
}
ACTIONS = {
    "emoji-list": ({"query", "group", "offset", "limit"}, set()),
    "emoji-get": ({"emoji", "output", "format", "overwrite"}, {"emoji"}),
    "emoji-destinations": (set(), set()),
    "emoji-requirements": ({"destination", "emojis"}, set()),
    "emoji-export": ({"output", "destination", "emojis", "sources", "size", "overwrite"}, {"output"}),
    "emoji-template": ({"output", "kind", "destination", "overwrite"}, {"output"}),
    "emoji-replace": ({"emoji", "source", "name", "license"}, {"emoji", "source"}),
    "emoji-pack-install": ({"source"}, {"source"}),
    "emoji-settings": ({"mode"}, set()),
    "emoji-reset": ({"emoji"}, set()),
}
SUMMARIES = {
    "emoji-list": "Search Unicode 17 artwork, 100 VIXL originals and document custom emojis, with pagination.",
    "emoji-get": "Inspect an emoji or extract its editable VIXL source, SVG or PNG.",
    "emoji-destinations": "List destination constraints and upload instructions for emoji packs.",
    "emoji-requirements": "Validate selected emojis against destination image sizes, names and byte limits.",
    "emoji-export": "Write a ready-to-upload PNG/SVG pack with manifest, licenses, preview and editable sources.",
    "emoji-template": "Create a transparent editable emoji template: blank, face, symbol or a 4×4 sheet.",
    "emoji-replace": "Embed one custom replacement or new shortcode in the document, preserving its source.",
    "emoji-pack-install": "Install every entry in a VIXL emoji pack as one undoable atomic document edit.",
    "emoji-settings": "Inspect emoji rendering preferences or switch between VIXL and font preference.",
    "emoji-reset": "Restore one bundled emoji or remove all document overrides.",
}


def dispatch(session, action, request, document=None):
    from jsonschema import Draft202012Validator

    errors = list(
        Draft202012Validator(
            {
                "type": "object",
                "properties": {k: FIELDS[k] for k in ACTIONS[action][0]},
                "required": sorted(ACTIONS[action][1]),
                "additionalProperties": False,
            }
        ).iter_errors(request)
    )
    require(not errors, str(errors[0].message) if errors else "", "invalid_request")
    if action == "emoji-destinations":
        return {
            "destinations": emojis.DESTINATIONS,
            "checked": "2026-10-08",
            "help": "Profiles describe static custom emoji uploads; slot counts and permissions depend on the destination.",
        }
    if action == "emoji-template":
        output = session.resolve(request["output"])
        require(output.suffix.lower() == ".vixl", "Emoji template output must end in .vixl")
        project = emojis.template(
            request.get("kind", "blank"), request.get("destination", "images"), session.limits
        )
        project.save(output, overwrite=request.get("overwrite", False))
        return {"output": session.relative(output), **project.state["emoji_template"]}
    if (
        action in ("emoji-replace", "emoji-pack-install", "emoji-reset")
        or action == "emoji-settings"
        and "mode" in request
    ):
        with session.project(write=True, document=document) as project:
            if action == "emoji-pack-install":
                from .assets import read_bounded

                return emojis.install_pack(
                    project,
                    read_bounded(session.resolve(request["source"]), session.limits.max_project_bytes),
                )
            if action == "emoji-replace":
                from .assets import read_bounded

                path = session.resolve(request["source"])
                format = path.suffix.lower().lstrip(".")
                require(
                    format in ("vixl", "svg", "png"), "Emoji replacement source must be .vixl, .svg or .png"
                )
                op = {
                    "type": "emoji-set",
                    "emoji": request["emoji"],
                    "format": format,
                    "data": base64.b64encode(read_bounded(path, session.limits.max_asset_bytes)).decode(),
                    **{k: request[k] for k in ("name", "license") if k in request},
                }
            elif action == "emoji-reset":
                op = {"type": "emoji-reset", **request}
            else:
                op = {"type": "emoji-mode", "mode": request["mode"]}
            project.apply([op], detail="compact")
            return {
                "mode": project.state["emojis"]["mode"],
                "overrides": len(project.state["emojis"]["overrides"]),
            }
    if document or session.path:
        with session.project(document=document) as project:
            return read(session, action, request, project)
    return read(session, action, request, None)


def read(session, action, request, project):
    if action == "emoji-list":
        return emojis.catalog(project=project, **request)
    if action == "emoji-settings":
        return deepcopy_settings(project)
    if action == "emoji-get":
        key = emojis.identifier(request["emoji"])
        info = emojis._entries().get(key, {"id": key, "name": key.strip(":"), "emoji": key})
        result = {
            **info,
            "editable": emojis.artwork(project, key, "vixl") is not None,
            "custom": bool(project and key in project.state.get("emojis", {}).get("overrides", {})),
        }
        if "output" in request:
            format = request.get("format", "vixl")
            output = session.resolve(request["output"])
            require(output.suffix.lower() == "." + format, "Emoji output suffix must match format")
            data = (
                emojis.png(emojis.artwork(project, key), 128)
                if format == "png"
                else emojis.artwork(project, key, format)
            )
            require(data is not None, "This custom emoji has no editable master; use its SVG or PNG")
            from .production import write_bytes

            require(
                request.get("overwrite", False) or not output.exists(),
                "Output already exists",
                "output_exists",
            )
            write_bytes(output, data, replace=request.get("overwrite", False))
            result["output"] = session.relative(output)
        return result
    if action == "emoji-requirements":
        return emojis.requirements(project=project, **request)
    if action == "emoji-export":
        result = emojis.export_pack(
            session.resolve(request["output"]),
            project=project,
            **{k: v for k, v in request.items() if k != "output"},
        )
        result["output"] = session.relative(Path(result["output"]))
        return result
    raise VixlError("invalid_request", "Unknown emoji action")


def deepcopy_settings(project):
    from copy import deepcopy

    return (
        deepcopy(project.state.get("emojis", {"mode": "vixl", "overrides": {}}))
        if project
        else {"mode": "vixl", "overrides": {}}
    )


def cli(args, options, limits):
    from .commands import Parser
    from .interfaces import Session

    parser = Parser(
        prog="vixl emoji", description="Offline emoji catalog, editable masters, custom packs and exports"
    )
    parser.add_argument("--workspace", default=str(Path.cwd()))
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--query", default="")
    listing.add_argument("--group")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=100)
    get = sub.add_parser("get")
    get.add_argument("emoji")
    get.add_argument("--out", dest="output")
    get.add_argument("--format", choices=["vixl", "svg", "png"], default="vixl")
    get.add_argument("--overwrite", action="store_true")
    sub.add_parser("destinations")
    for name in ("requirements", "export"):
        p = sub.add_parser(name)
        p.add_argument("--destination", choices=list(emojis.DESTINATIONS), default="images")
        p.add_argument("--emojis", nargs="+")
        if name == "export":
            p.add_argument("--out", dest="output", required=True)
            p.add_argument("--size", type=int)
            p.add_argument("--no-sources", dest="sources", action="store_false")
            p.add_argument("--overwrite", action="store_true")
    p = sub.add_parser("template")
    p.add_argument("kind", choices=["blank", "face", "symbol", "sheet"], nargs="?", default="blank")
    p.add_argument("--out", dest="output", required=True)
    p.add_argument("--destination", choices=list(emojis.DESTINATIONS), default="images")
    p.add_argument("--overwrite", action="store_true")
    p = sub.add_parser("replace")
    p.add_argument("emoji")
    p.add_argument("source")
    p.add_argument("--name")
    p.add_argument("--license")
    p = sub.add_parser("install")
    p.add_argument("source")
    p = sub.add_parser("settings")
    p.add_argument("--mode", choices=["vixl", "font"])
    p = sub.add_parser("reset")
    p.add_argument("--emoji")
    a = parser.parse_args(args)
    request = {k: v for k, v in vars(a).items() if k not in ("command", "workspace") and v is not None}
    action = "emoji-pack-install" if a.command == "install" else "emoji-" + a.command
    return dispatch(Session(options.project, limits, workspace=Path(a.workspace)), action, request)
