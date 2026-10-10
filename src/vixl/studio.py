"""Consolidated resource, reuse, testing and collaborative production commands."""

from copy import deepcopy

from .errors import require

ACTIONS = {
    "resource-list": ({"kind"}, {"kind"}),
    "resource-get": ({"kind", "name"}, {"kind", "name"}),
    "resource-save": ({"kind", "name", "value"}, {"kind", "name", "value"}),
    "shape-save": ({"target", "name"}, {"target", "name"}),
    "suite-use": ({"name", "as", "reference"}, {"name"}),
    "suite-infer": ({"name", "apply", "replace", "group", "from_group"}, set()),
    "effect-run": ({"name", "variables", "dry_run"}, {"name"}),
    "palette-check": ({"palette", "colors", "tolerance", "max_fraction", "alpha_min", "region"}, set()),
    "branch-list": (set(), set()),
    "group-list": (set(), set()),
    "branch-fork": ({"branch", "output", "author"}, {"branch", "output"}),
    "branch-status": ({"branch"}, {"branch"}),
    "branch-merge": ({"branch", "resolutions", "dry_run", "expected_head"}, {"branch"}),
    "group-define": ({"name", "documents", "shared", "facts", "profiles", "suites"}, {"name", "documents"}),
    "group-show": ({"name"}, {"name"}),
    "group-apply": ({"name", "operations", "suites", "profile", "dry_run", "repair", "accept", "reject", "decisions",
                     "review", "overwrite"}, {"name"}),
    "group-check": ({"name", "documents", "reference", "checks", "layers", "facts", "required", "tolerance"}, set()),
    "group-recover": ({"name"}, {"name"}),
    "plugin-list": (set(), set()),
    "plugin-install": ({"manifest", "replace"}, {"manifest"}),
    "plugin-remove": ({"name"}, {"name"}),
}

# Only these actions are appropriate for a fixed-document REST server.
REST_ACTIONS = {
    "resource-list",
    "resource-get",
    "resource-save",
    "shape-save",
    "suite-use",
    "effect-run",
    "palette-check",
}


def dispatch(session, action, request, document=None):
    from .resources import catalog, get, register

    if action.startswith("branch-"):
        from .collaboration import dispatch as collaborate

        return collaborate(session, action, request, document)
    if action == "group-check":
        from .group_consistency import run as group_check

        return group_check(session, request)
    if action.startswith("group-"):
        from .project_groups import dispatch as groups

        return groups(session, action, request)
    if action == "suite-infer":
        from .suite_infer import dispatch as infer

        return infer(session, request, document)
    if action.startswith("plugin-"):
        from .plugins import package

        return package(session, action, request)
    if action.startswith("resource-"):
        kind = request["kind"]
        if action == "resource-list":
            return {"kind": kind, "names": sorted(catalog(kind, workspace=session.workspace))}
        if action == "resource-get":
            return {
                "kind": kind,
                "name": request["name"],
                "value": get(kind, request["name"], workspace=session.workspace),
            }
        return register(kind, request["name"], request["value"], workspace=session.workspace)
    if action == "shape-save":
        from .design_schema import SHAPES
        from .design import resolve_color

        with session.project(document=document) as project:
            layer = project.layer(request["target"])
            require(
                layer["type"] == "shape" and layer["shape"] in SHAPES,
                "Save a shape/path layer; use library-save for full components",
            )
            fields = {
                "shape",
                "path",
                "width",
                "height",
                "fill",
                "stroke",
                "stroke_width",
                "radius",
                "sides",
                "inner_radius",
                "start_angle",
                "end_angle",
            }
            value = {"type": "shape", **{k: deepcopy(v) for k, v in layer.items() if k in fields}}
            if layer["shape"] == "path":
                from .geometry import parse_path

                sx, sy = layer["width"] / layer["path_view"][0], layer["height"] / layer["path_view"][1]
                value["path"] = " ".join(
                    command + " ".join(f"{v * (sx if i % 2 == 0 else sy):.8g}" for i, v in enumerate(coords))
                    for command, coords in parse_path(layer["path"])
                )
            for key in ("fill", "stroke"):
                if key in value:
                    value[key] = resolve_color(value[key], project.state)
        return register("shapes", request["name"], value, workspace=session.workspace)
    with session.project(
        write=action in ("suite-use", "effect-run") and not request.get("dry_run", False), document=document
    ) as project:
        if action == "suite-use":
            suite = get("suites", request["name"], workspace=session.workspace)
            require(type(request.get("reference", False)) is bool, "reference must be true or false", field="reference")
            if request.get("reference"):
                # Attach by reference: every check runs the library's current rules (local rules can be added later).
                suite = {"version": 1, "extends": request["name"], "rules": []}
            return project.apply(
                {"type": "suite-set", "name": request.get("as", request["name"]), "suite": suite},
                detail="compact",
            )
        if action == "effect-run":
            from .effect_workflows import apply

            return apply(
                project,
                get("workflows", request["name"], workspace=session.workspace),
                request.get("variables"),
                request.get("dry_run", False),
            )
        from .palette_checks import measure

        return measure(project, **request)
