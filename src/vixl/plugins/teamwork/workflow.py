"""Workflow actions for branches, document groups and suite inference."""

from ...errors import VixlError

ACTIONS = {
    "suite-infer": ({"name", "apply", "replace", "group", "from_group"}, set()),
    "branch-list": (set(), set()),
    "group-list": (set(), set()),
    "branch-fork": ({"branch", "output", "author"}, {"branch", "output"}),
    "branch-status": ({"branch"}, {"branch"}),
    "branch-merge": ({"branch", "resolutions", "dry_run", "expected_head"}, {"branch"}),
    "group-define": ({"name", "documents", "shared", "facts", "profiles", "suites"}, {"name", "documents"}),
    "group-show": ({"name"}, {"name"}),
    "group-apply": ({"name", "operations", "suites", "profile", "dry_run", "repair", "accept", "reject", "decisions",
                     "review", "overwrite"}, {"name"}),
    "group-recover": ({"name"}, {"name"}),
}


def dispatch(session, action, request, document=None):
    try:
        if action.startswith("branch-"):
            from .collaboration import dispatch as collaborate

            return collaborate(session, action, request, document)
        if action.startswith("group-"):
            from .project_groups import dispatch as groups

            return groups(session, action, request)
        from .suite_infer import dispatch as infer

        return infer(session, request, document)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise VixlError("invalid_request", f"Invalid {action} request: {exc}") from exc
