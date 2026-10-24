"""Workflow actions for portable character packages: character-package, -discover, -inspect and -place."""

from pathlib import Path

from ...errors import require

PLACE_FIELDS = {"package", "name", "x", "y", "scale", "width", "height", "pose", "expression", "motion", "colors",
                "outfit", "scale_parts"}
ACTIONS = {
    "character-package": ({"target", "output", "name", "description", "tags", "version", "expressions", "poses",
                           "motions", "checks", "overwrite"}, {"target", "output"}),
    "character-discover": ({"query"}, set()),
    "character-inspect": ({"package"}, {"package"}),
    "character-place": (PLACE_FIELDS, {"package"}),
}
PACKAGE = {"type": "string", "description": "A .vixlchar file in the workspace, user:FILE in the user character "
           "library, or the name of a package character-discover finds (the workspace first)."}
NAMED = "Leave it out for the built-in ones the character can use; {} packages none."
FIELD_TYPES = {
    "character-package": {
        "target": {"type": "string", "description": "The rigged character group to package (character, then "
                   "character-rig for bound artwork)."},
        "output": {"type": "string", "description": "Workspace path of the new package, ending in .vixlchar."},
        "name": {"type": "string", "description": "Package name, 1-64 letters, digits, hyphens or underscores "
                 "(default: the group's name)."},
        "description": {"type": "string", "maxLength": 2000, "description": "What the character is, for discovery."},
        "tags": {"type": "array", "maxItems": 32, "items": {"type": "string"}, "description": "Discovery tags."},
        "version": {"type": "string", "description": "The character's own release, such as 1.2.0 (default 1.0.0)."},
        "expressions": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": {
            "type": "string"}}, "description": "Named expressions {name: {part: variant}} over left/right-eye "
            "(open, wide, closed, squint, happy), left/right-brow (neutral, raised, lowered, angry, sad, tilted) and "
            "mouth (neutral, smile, grin, frown, open, o, flat, smirk). " + NAMED},
        "poses": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": {
            "type": "number"}}, "description": "Named poses {name: {joint: degrees}} on the character's rig. " + NAMED},
        "motions": {"type": "object", "additionalProperties": {"type": "object"}, "description": "Named motions: "
                    "{name: {cycle: walk|run|idle|ride|react|wave, duration?, period?, amount?, samples?, view?}} or "
                    "{name: {keys: [{time, angles, easing?}]}}; a cycle needs the bones it drives. " + NAMED},
        "checks": {"type": "array", "maxItems": 16, "items": {"type": "string"}, "description": "Checks to run on "
                   "each placed copy (default character, plus object when the group is a declared object)."},
        "overwrite": {"type": "boolean", "default": False, "description": "Replace an existing output file."},
    },
    "character-discover": {
        "query": {"type": "string", "description": "Words that must all appear in a package's name, kind, "
                  "description or tags (default: every package)."},
    },
    "character-inspect": {"package": PACKAGE},
    "character-place": {
        "package": PACKAGE,
        "name": {"type": "string", "description": "Name of the placed character group (default the package name, "
                 "made unique)."},
        "x": {"type": "number", "description": "Left edge of the placed character on the page (default 0)."},
        "y": {"type": "number", "description": "Top edge of the placed character on the page (default 0)."},
        "scale": {"type": "number", "exclusiveMinimum": 0, "maximum": 100, "description": "Uniform scale factor."},
        "width": {"type": "number", "exclusiveMinimum": 0, "description": "Scale the character to this width "
                  "(keeps its proportions)."},
        "height": {"type": "number", "exclusiveMinimum": 0, "description": "Scale the character to this height "
                   "(keeps its proportions)."},
        "pose": {"type": ["string", "object"], "description": "A pose of the package by name, or inline joint "
                 "angles {joint: degrees}."},
        "expression": {"type": ["string", "object"], "description": "An expression of the package by name, or an "
                       "inline {part: variant}."},
        "motion": {"type": "string", "description": "A motion of the package by name, written as timeline keys."},
        "colors": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Colours by colour "
                   "role of the standard character (skin, outfit, hair, eyes)."},
        "outfit": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Fill colours by "
                   "character part, such as {torso: '#2a6'}."},
        "scale_parts": {"type": "object", "additionalProperties": {"type": "number"}, "description": "Change "
                        "proportions on purpose: {part: factor} (0.25-4) scales parts about their pivots, and bones on "
                        "them lengthen. Without it a placed character keeps the package's proportions."},
    },
}
SUMMARIES = {
    "character-package": "Write a rigged character as a versioned .vixlchar package: its document, rig, named "
                         "expressions, poses and motions, checks, fonts and assets, with SHA-256s.",
    "character-discover": "List the .vixlchar packages in the workspace and the user character library, and the "
                          "characters saved in the open document.",
    "character-inspect": "Verify a .vixlchar package and return its manifest: parts, rig, expressions, poses, "
                         "motions, checks, fonts and assets.",
    "character-place": "Place a character package as an editable character with new IDs, in a pose, with an "
                       "expression and a motion; colors and outfit override, scale_parts changes proportions.",
}


def dispatch(session, action, request, document=None):
    from . import package as packages

    if action == "character-package":
        require(type(request.get("overwrite", False)) is bool, "overwrite must be true or false", field="overwrite")
        output = session.resolve(request["output"])
        session.make_parent(output)
        with session.project(document=document) as project:
            result = packages.build(project, request["target"], output, name=request.get("name"),
                                    description=request.get("description", ""), tags=request.get("tags"),
                                    version=request.get("version", "1.0.0"), expressions=request.get("expressions"),
                                    poses=request.get("poses"), motions=request.get("motions"),
                                    checks=request.get("checks"), overwrite=request.get("overwrite", False))
        result["output"] = session.relative(Path(result["output"]))
        return result
    if action == "character-discover":
        query = request.get("query")
        require(query is None or isinstance(query, str), "query is text", field="query")
        result = packages.discover(session.workspace, query, limits=session.limits)
        if document is not None or getattr(session, "path", None) is not None:
            from .characters import library_characters

            with session.project(document=document) as project:
                saved = library_characters(project)
            if saved:
                result["document"] = saved
        return result
    path, label = packages.locate(request["package"], session.workspace, session.resolve, session.limits)
    package = packages.read(path, limits=session.limits, label=label)
    if action == "character-inspect":
        return packages.summary(package, full=True)
    with session.project(write=True, document=document) as project:
        return packages.place(project, package, request)
